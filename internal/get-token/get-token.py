#!/usr/bin/env python3
"""
get-token.py — Generate scoped GitHub App installation tokens.

Selects an app from the pool with available rate limit, verifies authorization
for deployer profile, and emits telemetry.

Security model (private key lifecycle):
  The RSA private key is fetched directly from AWS Secrets Manager inside this
  process. It is NEVER written to GITHUB_ENV or any other persistent location.
  After JWT generation the key variable is overwritten with null bytes and
  deleted so the garbage collector can reclaim the memory as soon as possible.
  The key exposure window is limited to: [boto3 call] → [JWT signed] → [zero].

Required environment variables:
  PROFILE              — reader | deployer
  REPOSITORIES         — comma-separated list of repos (owner/repo or just repo)
  PLATFORM_REPOSITORIES — comma-separated list of platform repos always added
  CALLER_REPO          — repo that invoked this workflow (github.repository)
  CALLER_ACTOR         — user/app that triggered the workflow (github.actor)
  GITHUB_ORG           — organization name
  GITHUB_RUN_ID        — workflow run id (auto-injected by the runner; used by
                         Zeus actor resolution, PTIZ-4582)
  GITHUB_OUTPUT        — path to GitHub Actions output file
  GITHUB_STEP_SUMMARY  — path to GitHub Actions step summary file
  GH_TOKEN_ENCRYPTION_PASSPHRASE — passphrase for encrypting the generated token
  AWS_REGION           — AWS region for Secrets Manager (default: eu-west-1)
"""

import gc
import json
import os
import sys
import time
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import yaml
import boto3

import jwt as pyjwt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from nacl.public import SealedBox, PublicKey

# =============================================================================
# GitHub Actions helpers
# =============================================================================

def log(msg):
    print(f"{msg}")

def notice(msg):
    print(f"::notice::{msg}")

def warn(msg):
    print(f"::warning::{msg}")

def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)

def set_output(name, value):
    output_file = os.environ["GITHUB_OUTPUT"]
    with open(output_file, "a", encoding="utf-8") as f:
        if "\n" in value:
            f.write(f"{name}<<EOF\n{value}\nEOF\n")
        else:
            f.write(f"{name}={value}\n")

def write_summary(content):
    summary_file = os.environ["GITHUB_STEP_SUMMARY"]
    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(content)

# =============================================================================
# Configuration loader
# =============================================================================

CONFIG_PATH = Path(__file__).resolve().parent.parent / "get-config" / "config" / "apps.yaml"


def load_config():
    """Load apps config from APPS_CONFIG env var, or fallback to internal/get-config/config/apps.yaml."""
    config_yaml = os.environ.get("APPS_CONFIG", "")
    if config_yaml:
        return yaml.safe_load(config_yaml)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    fail("Configuration not found: set APPS_CONFIG env var or provide internal/get-config/config/apps.yaml")

# =============================================================================
# Private key — secure fetch + lifecycle management
# =============================================================================

def fetch_private_key(aws_secret: str, region: str) -> bytearray:
    """Fetch RSA private key from AWS Secrets Manager.

    Returns a mutable bytearray so the caller can overwrite it after use.
    The key is masked in the Actions log immediately after retrieval.
    The key is NEVER written to GITHUB_ENV or any file on disk.
    """
    sm = boto3.client("secretsmanager", region_name=region)
    try:
        response = sm.get_secret_value(SecretId=aws_secret)
        key_str = response["SecretString"]
    except Exception as exc:
        fail(f"Failed to retrieve secret '{aws_secret}' from AWS Secrets Manager: {exc}")

    # Drop the response dict ASAP to avoid keeping extra references to the secret value.
    del response

    # Mask every non-empty line in Actions logs immediately.
    if os.environ.get("GITHUB_ACTIONS"):
        for line in key_str.splitlines():
            if line.strip():
                print(f"::add-mask::{line}")

    # Convert to mutable bytearray, then discard the immutable string copy.
    key_bytes = bytearray(key_str, "utf-8")
    del key_str
    gc.collect()

    return key_bytes


def zero_key(key: bytearray) -> None:
    """Overwrite key material in memory with null bytes (best-effort in CPython).

    Python strings are immutable and interned, but bytearray is mutable and not
    interned, so overwriting gives a meaningful reduction in exposure window even
    though CPython's GC does not guarantee immediate memory reclamation.
    """
    key[:] = b'\x00' * len(key)


# =============================================================================
# Helpers
# =============================================================================

def github_api(url, token, method="GET", data=None, retries=2, retry_delay=2, max_retry_wait=300):
    """Make a GitHub API request and return (status_code, response_body).

    Args:
        url: full API URL
        token: GitHub App JWT or installation token for authentication
        method: HTTP method (GET, POST, PUT, etc.)
        data: dict to send as JSON body (for POST/PUT)
        retries: number of retries on transient errors (500, 502, 503, 504, 403, 429, network errors).
        retry_delay: initial delay in seconds between retries (doubles each attempt).
        max_retry_wait: maximum delay in seconds before giving up on retrying.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    body = json.dumps(data).encode() if data else None
    last_exc = None
    for attempt in range(1 + retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                try:
                    parsed = json.loads(raw) if raw else {}
                except ValueError:
                    parsed = {"message": raw} if raw else {}
                return resp.status, parsed
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            status = e.code
            try:   
                response_body = json.loads(raw) if raw else {}
            except ValueError:                
                response_body = {"message": raw} if raw else {}

            # Retry on transient HTTP errors
            # 429 Too Many Requests may include Retry-After header to indicate when to retry
            # 403 Forbidden can occur if the app is rate limited or has insufficient permissions; retrying may help if it's a temporary rate limit issue
            # 500 Internal Server Error and other 5xx errors are often transient
            # 502 Bad Gateway can occur if GitHub's backend is temporarily unavailable
            # 503 Service Unavailable may indicate temporary overload or maintenance
            # 504 Gateway Timeout can occur if GitHub's backend is slow to respond
            retry_after = e.headers.get("Retry-After")
            remaining_header = e.headers.get("x-ratelimit-remaining")
            reset_header = e.headers.get("x-ratelimit-reset")
            msg = str(response_body.get("message", "")).lower()

            is_rate_limit_error = (
                status == 429
                or retry_after is not None
                or (status == 403 and remaining_header == "0")
                or (status == 403 and "rate limit" in msg)
            )
            should_retry = status in (500, 502, 503, 504) or is_rate_limit_error

            if should_retry and attempt < retries:

                # https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2026-03-10#exceeding-the-rate-limit
                # If you exceed a secondary rate limit, you will receive a 403 or 429 response and an error message that indicates that you exceeded a secondary rate limit. If the retry-after response header is present, you should not retry your request until after that many seconds has elapsed
                computed_delay = retry_delay * (2 ** attempt)
                delay = computed_delay
                if retry_after:
                    try:
                        delay = max(int(retry_after), delay)
                    except (TypeError, ValueError):
                        pass

                # Primary rate-limit exceeded typically returns 403 + X-RateLimit-Reset (no Retry-After)
                if status == 403 and remaining_header == "0" and reset_header:
                    try:
                        delay_until_reset = max(1, int(reset_header) - int(time.time()) + 1)
                        delay = max(delay, delay_until_reset)
                    except (TypeError, ValueError, OSError):
                        pass

                
                remaining_msg = f"[X-RateLimit-Remaining: {remaining_header}]" if remaining_header else ""
                
                if reset_header:
                    try:
                        reset_time = datetime.fromtimestamp(int(reset_header), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        ratelimit_reset_msg = f"[X-RateLimit-Reset: {reset_header} ({reset_time})]"
                    except (TypeError, ValueError, OSError):
                        ratelimit_reset_msg = f"[X-RateLimit-Reset: {reset_header}]"
                else:
                    ratelimit_reset_msg = ""

                if remaining_msg or ratelimit_reset_msg:
                    warn(f"Rate limit info: {remaining_msg} {ratelimit_reset_msg}")


                # Si el tiempo de espera es superior a max_retry_wait segundos, no vale la pena esperar 
                # Y se considera un error para poder cambiar a otro app del pool. Esto evita que el script se quede bloqueado durante mucho tiempo en un app con límite de tasa agotado.
                if delay > max_retry_wait:
                    warn(f"Rate limit exceeded for {method} {url}. Reset in {delay}s, which is longer than {max_retry_wait}s. Not retrying.")
                    return status, response_body
                
                warn(f"Transient HTTP {status} on {method} {url}, retrying in {delay}s (retry {attempt + 1}/{retries})...")                    
                time.sleep(delay)
                continue
            return status, response_body
        except OSError as e:
            last_exc = e
            if attempt < retries:
                delay = retry_delay * (2 ** attempt)
                warn(f"Network error on {method} {url}: {e}, retrying in {delay}s (attempt {attempt + 1}/{retries})...")
                time.sleep(delay)
                continue
            warn(f"Network error on {method} {url} after {retries + 1} attempts: {e}")
            return 0, {"message": str(e)}
    # Should not reach here, but safeguard
    return 0, {"message": str(last_exc) if last_exc else "unknown error"}


def generate_jwt(app_id: str, private_key: bytearray) -> str:
    """Generate a JWT for GitHub App authentication.

    Accepts bytearray to allow immediate zeroing of the key after this call.
    """
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    return pyjwt.encode(payload, bytes(private_key), algorithm="RS256")


def get_installation_id(jwt_token, org_name):
    """Get the installation ID for the app in the given org."""
    status, data = github_api("https://api.github.com/app/installations", jwt_token)
    if status != 200:
        warn(f"Failed to get installation ID (HTTP {status}): {data}")
        return None
    for installation in data:
        if installation.get("account", {}).get("login") == org_name:
            return installation["id"]
    return None


def generate_installation_token(jwt_token, installation_id, repos, permissions):
    """Generate a scoped installation token."""
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    body = {"permissions": permissions}
    if repos and repos != "ALL":
        repo_names = [
            r.strip().split("/")[-1]
            for r in repos.split(",")
            if r.strip()
        ]
        body["repositories"] = repo_names
    status, data = github_api(url, jwt_token, method="POST", data=body)
    if status != 201:
        warn(f"Failed to generate token (HTTP {status}): {data}")
        return None
    return data.get("token")


def check_rate_limit(token):
    """Check remaining rate limit for a token."""
    status, data = github_api("https://api.github.com/rate_limit", token)

    if status != 200:
        warn(f"Failed to check rate limit (HTTP {status}): {data}")
        return 0

    return data.get("rate", {}).get("remaining", 0)    


def encrypt_token_aes(token, passphrase):
    """Encrypt token with AES-256-CBC using PBKDF2 + salt (OpenSSL compatible)."""
    salt = os.urandom(8)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=48,  # 32 bytes key + 16 bytes IV
        salt=salt,
        iterations=10000,
    )
    derived = kdf.derive(passphrase.encode())
    key = derived[:32]
    iv = derived[32:48]

    padder = sym_padding.PKCS7(128).padder()
    padded_data = padder.update(token.encode()) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    # OpenSSL format: "Salted__" + salt + ciphertext
    raw = b"Salted__" + salt + ciphertext
    return base64.b64encode(raw).decode()


def create_or_update_repo_secret(token, org, repo_name, secret_name, secret_value):
    """Create or update a GitHub Actions secret on a repository."""
    repo_full = f"{org}/{repo_name}" if "/" not in repo_name else repo_name
    url_key = f"https://api.github.com/repos/{repo_full}/actions/secrets/public-key"
    status, data = github_api(url_key, token)
    if status != 200:
        warn(f"Failed to get public key for {repo_full} (HTTP {status}): {data}")
        return False, status

    pub_key_b64 = data["key"]
    key_id = data["key_id"]

    public_key = PublicKey(base64.b64decode(pub_key_b64))
    sealed_box = SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode())
    encrypted_b64 = base64.b64encode(encrypted).decode()

    url_secret = f"https://api.github.com/repos/{repo_full}/actions/secrets/{secret_name}"
    body = {"encrypted_value": encrypted_b64, "key_id": key_id}
    status, resp = github_api(url_secret, token, method="PUT", data=body)
    if status in (201, 204):
        notice(f"Repository Secret '{secret_name}' {'created' if status == 201 else 'updated'} on {repo_full}")
        return True, status
    else:
        warn(f"Failed to set Repository Secret '{secret_name}' on {repo_full} (HTTP {status}): {resp}")
        return False, status


def update_org_secret(token, org_name, secret_name, secret_value):
    """Update a GitHub Actions secret at organization level."""
    url_key = f"https://api.github.com/orgs/{org_name}/actions/secrets/public-key"
    status, data = github_api(url_key, token)
    if status != 200:
        warn(f"Failed to get org public key for {org_name} (HTTP {status}): {data}")
        return False, status

    pub_key_b64 = data["key"]
    key_id = data["key_id"]

    public_key = PublicKey(base64.b64decode(pub_key_b64))
    sealed_box = SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode())
    encrypted_b64 = base64.b64encode(encrypted).decode()

    url_secret = f"https://api.github.com/orgs/{org_name}/actions/secrets/{secret_name}"
    body = {"encrypted_value": encrypted_b64, "key_id": key_id, "visibility": "private"}
    status, resp = github_api(url_secret, token, method="PUT", data=body)
    if status in (201, 204):
        log(f"Org secret '{secret_name}' {'created' if status == 201 else 'updated'} on {org_name}")
        return True, status

    warn(f"Failed to set org secret '{secret_name}' on {org_name} (HTTP {status}): {resp}")
    return False, status


def get_entity_product(repo):
    """Extract the '<entity>-<product>' prefix from a repo following the
    '<entity>-<product>-<component>' naming convention.

    Accepts both 'org/repo' and 'repo'. Returns None when the name does not
    have at least three '-' separated parts (prefix cannot be derived).
    """
    repo_name = repo.strip().split("/")[-1]
    parts = repo_name.split("-")
    if len(parts) < 3:
        return None
    return f"{parts[0]}-{parts[1]}"


def check_trusted_actor(actor, trusted_actors, profile, caller_repo, repositories):
    """Authorize a platform CI bot (e.g. release-please pushing with a GitHub App
    identity) that legitimately re-triggers a workflow but can never be a member
    of human repo teams.

    Config entries in trusted_actors may be either:
      - a plain string (login), or
      - a dict: {actor: <login>, profiles: [<profile>...], same_entity_product_only: <bool>}

    Defaults when a field is omitted:
      profiles: ["reader"]              — restrict to read-only unless explicitly widened
      same_entity_product_only: True    — every requested repo must share the
                                          '<entity>-<product>' prefix of caller_repo

    Match on 'actor' is case-insensitive. Empty/missing list disables the feature.
    Returns True only if the actor is allowlisted AND the requested profile and
    repositories fit the entry's constraints.
    """
    if not trusted_actors:
        return False

    actor_lower = actor.lower()
    scope_repos = [r.strip() for r in repositories.split(",") if r.strip()]

    for entry in trusted_actors:
        if isinstance(entry, str):
            entry_login = entry
            allowed_profiles = ["reader"]
            same_entity_product_only = True
        else:
            entry_login = entry.get("actor", "")
            allowed_profiles = entry.get("profiles", ["reader"])
            same_entity_product_only = entry.get("same_entity_product_only", True)

        if entry_login.lower() != actor_lower:
            continue

        if profile not in allowed_profiles:
            warn(f"Trusted actor '{actor}' matched but profile '{profile}' is not in allowed profiles {allowed_profiles}. Denying bypass.")
            return False

        if same_entity_product_only:
            caller_entity_product = get_entity_product(caller_repo)
            if not caller_entity_product:
                warn(f"Trusted actor '{actor}': could not derive entity-product from caller_repo '{caller_repo}', expected format <entity-product-component>. Denying bypass.")
                return False

            outsiders = [r for r in scope_repos if get_entity_product(r) != caller_entity_product]
            if outsiders:
                warn(f"Trusted actor '{actor}' requested cross-entity-product scope {outsiders}; caller_repo='{caller_repo}' belongs to '{caller_entity_product}'. Denying bypass.")
                return False

        return True

    return False


def check_org_roles(org_name, actor, team_token, bypass_org_owner=False, bypass_org_roles=None):
    """Check if actor is org owner or has specific org roles (bypass team-membership).

    Returns (bypass: bool, is_exception: bool).
      - bypass=True  → actor should skip team-membership checks.
      - is_exception=True → unexpected HTTP error; caller should try next app in pool.
    """
    if bypass_org_roles is None:
        bypass_org_roles = {}

    # 1. Check if actor is org owner (admin)
    if bypass_org_owner:
        url = f"https://api.github.com/orgs/{org_name}/memberships/{actor}"
        status, data = github_api(url, team_token)
        if status == 200 and data.get("role") == "admin":
            notice(f"Actor '{actor}' is org owner of '{org_name}'. Bypassing team-membership check.")
            return True, False
        elif status == 200:
            log(f"Actor '{actor}' is member of '{org_name}' but not owner (role: {data.get('role')})")
        elif status == 404:
            log(f"Actor '{actor}' not found in org '{org_name}' memberships (HTTP 404)")
        else:
            warn(f"Unexpected HTTP {status} checking org membership for '{actor}': {data}")
            return False, True

    # 2. Check if actor has any of the configured organization roles
    if bypass_org_roles:
        for role_name, role_id in bypass_org_roles.items():
            url = f"https://api.github.com/orgs/{org_name}/organization-roles/{role_id}/users"
            status, data = github_api(url, team_token)
            if status == 200:
                if not isinstance(data, list):
                    warn(f"Unexpected response format for org role {role_name} (id: {role_id}): expected list")
                    # response is 200, so next github app will likely get the same response, so we treat this as a non-bypass and continue to check other roles
                    return False, False
                actor_lower = actor.lower()
                if any(u.get("login", "").lower() == actor_lower for u in data):
                    notice(f"Actor '{actor}' has org role {role_name} (id: {role_id}) in '{org_name}'. Bypassing team-membership check.")
                    return True, False
                else:
                    log(f"Actor '{actor}' does not have org role {role_name} (id: {role_id})")
            elif status == 404:
                warn(f"Org role {role_name} (id: {role_id}) not found (HTTP 404). Skipping.")
            else:
                warn(f"Unexpected HTTP {status} getting users for org role {role_name} (id: {role_id}): {data}")
                return False, True

    return False, False


def check_team_authorization(org_name, repositories, actor, suffixes, team_token, custom_teams=None):
    """Verify actor belongs to an authorized team for ALL repositories."""
    if custom_teams is None:
        custom_teams = []
    custom_prefix_map = {}
    for entry in custom_teams:
        if isinstance(entry, dict):
            for key, value in entry.items():
                custom_prefix_map[key] = value
   

    repo_names = list(dict.fromkeys(
        r.strip().split("/")[-1] for r in repositories.split(",") if r.strip()
    ))

    failed_repos = []

    for repo_name in repo_names:
        parts = repo_name.split("-")
        custom_match = custom_prefix_map.get(repo_name) or custom_prefix_map.get(parts[0]) or (custom_prefix_map.get(f"{parts[0]}-{parts[1]}") if len(parts) > 1 else None)

        if not custom_match:
            if len(parts) <= 2:
                warn(f"Could not derive team prefix from repo name '{repo_name}', expected format <entity-product-component>.")
                failed_repos.append(repo_name)
                continue

        repo_prefix = custom_match if custom_match else f"{parts[0]}-{parts[1]}"
        candidate_teams = [f"{repo_prefix}{suffix}" for suffix in suffixes]

        if custom_match:
            log(f"Checking membership in teams derived from custom repo mapping '{repo_name}': {candidate_teams}")
        else:
            repo_adm_team = f"{parts[0]}-adm"
            candidate_teams.append(repo_adm_team)
            log(f"Checking membership in teams derived from repo name <entity-product-component> '{repo_name}': {candidate_teams}")

        authorized = False
        for team in candidate_teams:
            url = f"https://api.github.com/orgs/{org_name}/teams/{team}/memberships/{actor}"
            status, resp_body = github_api(url, team_token)
            if status == 200:
                notice(f"Actor '{actor}' authorized for repo '{repo_name}' via team '{team}'")
                authorized = True
                break
            elif status == 404:
                log(f"Actor '{actor}' not a member of team '{team}' (HTTP 404)")
            else:
                warn(f"Unexpected HTTP {status} checking team '{team}' membership for '{actor}': {resp_body}")
                failed_repos.append(repo_name)
                return False, failed_repos, True  # Unexpected HTTP; signal caller to try the next app in the pool

        if not authorized:
            warn(f"Actor '{actor}' is not authorized for repo '{repo_name}' (checked teams: {candidate_teams})")
            failed_repos.append(repo_name)

    if failed_repos:
        warn(f"Authorization failed for repositories: {failed_repos}")
        return False, failed_repos, False

    notice(f"Actor '{actor}' authorized for all repositories")
    return True, [], False


# =============================================================================
# Zeus actor resolution (PTIZ-4582)
#
# When Zeus (the internal orchestrator) launches a workflow via
# arch-plat-lambda-controlplane, github.actor collapses to the controlplane's
# tech account. That account is an org owner and would silently bypass every
# authorization check and pollute telemetry.
#
# The controlplane, right after POST /dispatches, publishes a hidden ref in a
# central registry repo (<org>/arch-plat-zeus-actor-registry):
#   refs/registry/run/<owner>/<repo>/<GITHUB_RUN_ID>/<real_actor>/<timestamp>
# This code looks that ref up and rewrites caller_actor before authorization
# and telemetry run. Applies to every profile except those in skip_profiles.
# =============================================================================

def resolve_zeus_actor(caller_repo, run_id, registry_repo, ref_prefix, registry_token):
    """Fetch the real human actor from the Zeus registry.

    Contract with the controlplane:
        refs/registry/run/<owner>/<repo>/<run_id>/<actor>/<timestamp>

    Returns the actor username or None if the ref does not exist or is malformed.
    """
    prefix = ref_prefix.removeprefix("refs/")
    url = (
        f"https://api.github.com/repos/{registry_repo}"
        f"/git/matching-refs/{prefix}/{caller_repo}/{run_id}/"
    )
    status, data = github_api(url, registry_token, method="GET")
    if status != 200 or not isinstance(data, list) or not data:
        return None
    expected_prefix = f"refs/{prefix}/{caller_repo}/{run_id}/"
    for item in data:
        ref_name = item.get("ref", "")
        if ref_name.startswith(expected_prefix):
            parts = ref_name[len(expected_prefix):].split("/")
            return parts[0] if parts else None
    return None


def get_zeus_registry_repo(zeus_cfg, org):
    """Return the fully-qualified registry repo for Zeus actor resolution.

    registry_repo can be a plain string (legacy) or a dict with org-specific
    overrides and a 'default' fallback::

        registry_repo:
          default: arch-plat-zeus-actor-registry
          mapfre-test-pre: archpre-plat-zeus-actor-registry
    """
    default_repo = "arch-plat-zeus-actor-registry"
    repo_cfg = zeus_cfg.get("registry_repo", default_repo)
    if isinstance(repo_cfg, dict):
        repo_name = repo_cfg.get(org, repo_cfg.get("default", default_repo))
    else:
        repo_name = repo_cfg
    return f"{org}/{repo_name}"


def mint_registry_read_token_pool(zeus_cfg, org, aws_region, profiles):
    """Mint a Contents:Read installation token scoped to the registry repo
    using the first available app in the pool (profile: reader_app_profile).
    Returns the token string or None on failure.
    """

    reader_app_profile = zeus_cfg.get("reader_app_profile", "reader")
    profile_cfg = profiles[reader_app_profile]
    app_configs = profile_cfg.get("apps", [])
    registry_repo = get_zeus_registry_repo(zeus_cfg, org)

    for app in app_configs:
        app_id = str(app["id"])
        app_name = str(app["name"])
        aws_secret = app["aws_secret"]
        log(f"Trying app {app_name} (id: {app_id})...")
      
        private_key = fetch_private_key(aws_secret, aws_region)
        if not private_key:
            warn(f"Private key not found for app {app_name} (id: {app_id}, secret: {aws_secret}). Skipping.")
            continue

        try:
            jwt_token = generate_jwt(app_id, private_key)
        finally:
            # Zero key material immediately after JWT is signed.
            # This is the earliest possible moment to release it.
            zero_key(private_key)
            del private_key
        
        installation_id = get_installation_id(jwt_token, org)
        if not installation_id:
            warn(f"zeus_actor_resolution: App {app_id} not installed in org {org}. Skipping.")            
            continue

        installation_token = generate_installation_token(
            jwt_token, installation_id, registry_repo, {"contents": "read"}
        )

        if not installation_token:
            warn(f"Failed to generate token with app {app_name} (id: {app_id}). Trying next app...")
            continue

        return installation_token
    
    warn(f"All apps in the '{reader_app_profile}' pool are exhausted or unavailable. Add more GitHub Apps to the pool.")
    return None


def maybe_resolve_zeus_actor(caller_actor, caller_repo, profiles, profile, settings, org, aws_region):
    """Return caller_actor rewritten to the real Zeus user, if applicable.

    Runs for every profile (unless listed in skip_profiles) because
    caller_actor is used both for authorization (reader/deployer) and
    telemetry (all profiles). If disabled or the actor is not a dispatcher,
    the original caller_actor is returned unchanged.
    """
    zeus_cfg = settings.get("zeus_actor_resolution", {})
    if not zeus_cfg.get("enabled", False):
        return caller_actor
    dispatcher_accounts = [a.lower() for a in zeus_cfg.get("dispatcher_accounts", [])]
    if caller_actor.lower() not in dispatcher_accounts:
        return caller_actor
    if profile in zeus_cfg.get("skip_profiles", []):
        return caller_actor

    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id:
        warn("zeus_actor_resolution: GITHUB_RUN_ID not set; keeping caller_actor")
        return caller_actor
    if not caller_repo:
        warn("zeus_actor_resolution: caller_repo not set; keeping caller_actor")
        return caller_actor

    registry_repo = get_zeus_registry_repo(zeus_cfg, org)
    ref_prefix = zeus_cfg.get("ref_prefix", "refs/registry/run")
    on_missing = zeus_cfg.get("on_missing", "fail")

    registry_token = mint_registry_read_token_pool(zeus_cfg, org, aws_region, profiles)                                                  
    if not registry_token:
        if on_missing == "warn":
            warn("zeus_actor_resolution: could not mint registry token; keeping caller_actor")
            return caller_actor
        fail("zeus_actor_resolution: could not mint registry token")

    real_actor = resolve_zeus_actor(caller_repo, run_id, registry_repo, ref_prefix, registry_token)
    if not real_actor:
        msg = (
            f"Zeus dispatch without propagated actor "
            f"(registry={registry_repo}, caller_repo={caller_repo}, run_id={run_id})"
        )
        if on_missing == "warn":
            warn(msg)
            return caller_actor
        fail(msg)

    notice(f"Zeus dispatch: real actor resolved '{caller_actor}' -> '{real_actor}' "
        f"(caller_repo={caller_repo}, run_id={run_id})")
    return real_actor


def emit_telemetry(event, profile, app_id, app_name, repos, remaining, caller_repo, caller_actor, extra=""):
    """Emit telemetry as output and step summary."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    telemetry = json.dumps({
        "event": event,
        "profile": profile,
        "app_id": app_id,
        "app_name": app_name,
        "repositories": repos,
        "rate_limit_remaining": str(remaining),
        "caller_repo": caller_repo,
        "caller_actor": caller_actor,
        "timestamp": timestamp,
        "detail": extra,
    })
    set_output("telemetry", telemetry)

    headers = {
        "token_generated": "#### ✅ CI Token Generated",
        "token_denied": "#### ❌ CI Token Denied",
        "pool_exhausted": "#### ⚠️ Token Pool Exhausted",
    }
    summary = f"""{headers.get(event, "#### CI Token Event")}
| Field | Value |
|---|---|
| **Profile** | `{profile}` |
| **App ID** | `{app_id}` |
| **App Name** | `{app_name}` |
| **Repositories** | `{repos}` |
| **Rate Limit Remaining** | `{remaining}` |
| **Caller** | `{caller_repo}` |
| **Actor** | `{caller_actor}` |
| **Timestamp** | `{timestamp}` |
"""
    if extra:
        summary += f"| **Detail** | _{extra}_ |\n"
    write_summary(summary)


# =============================================================================
# Main
# =============================================================================

def main():
    config = load_config()
    settings = config.get("settings", {})
    profiles = config.get("profiles", {})

    rate_limit_threshold = settings.get("rate_limit_threshold", 14000)
    aws_region = os.environ.get("AWS_REGION", "eu-west-1")

    profile = os.environ.get("PROFILE", "reader")
    repositories = os.environ.get("REPOSITORIES", os.environ.get("CALLER_REPO", ""))
    platform_repos = os.environ.get("PLATFORM_REPOSITORIES", "")
    caller_repo = os.environ.get("CALLER_REPO", "")
    caller_actor = os.environ.get("CALLER_ACTOR", "")
    org = os.environ.get("GITHUB_ORG", "")
    gh_token_encryption_passphrase = os.environ.get("GH_TOKEN_ENCRYPTION_PASSPHRASE", "")
    rotate_org_secret = bool(settings.get("rotate_org_secret", False))    

    # PTIZ-4582: when Zeus dispatched the workflow, github.actor is a tech
    # account. Rewrite caller_actor to the real human before it is used for
    # authorization (reader/deployer profiles) and telemetry (every profile).
    caller_actor = maybe_resolve_zeus_actor(
        caller_actor, caller_repo, profiles, profile, settings, org, aws_region
    )

    if not repositories:
        fail("REPOSITORIES or CALLER_REPO environment variable is required to determine token scope")
    if not gh_token_encryption_passphrase:
        fail("GH_TOKEN_ENCRYPTION_PASSPHRASE is required for encrypting the generated token")

    if profile not in profiles:
        fail(f"Unknown profile: {profile}. Available: {list(profiles.keys())}")

    profile_cfg = profiles[profile]
    permissions = profile_cfg.get("permissions", {})
    app_configs = profile_cfg.get("apps", [])
    auth_mode = profile_cfg.get("authorization", "none")
    team_suffixes = profile_cfg.get("team_suffixes", [])
    custom_teams = profile_cfg.get("custom_teams", [])
    auth_bypass = settings.get("authorization_bypass", {})
    bypass_org_owner = auth_bypass.get("org_owner", False)
    bypass_org_roles = auth_bypass.get("org_roles", {})
    trusted_actors = auth_bypass.get("trusted_actors", [])

    # Build full token scope (repositories + platform repos)
    token_scope_list = []
    token_scope_seen = set()

    for repo in repositories.split(","):
        repo = repo.strip()
        if repo and repo not in token_scope_seen:
            token_scope_list.append(repo)
            token_scope_seen.add(repo)

    if platform_repos:
        for pr in platform_repos.split(","):
            pr = pr.strip()
            if pr and pr not in token_scope_seen:
                token_scope_list.append(pr)
                token_scope_seen.add(pr)

    token_scope = ",".join(token_scope_list)

    log(f"Profile: {profile} | Repos: {token_scope} | Caller: {caller_repo} | Actor: {caller_actor}")

    for app in app_configs:
        app_id = str(app["id"])
        app_name = str(app["name"])
        aws_secret = app["aws_secret"]

        log(f"Trying app {app_name} (id: {app_id})...")

        # ---------------------------------------------------------------
        # SECURITY: fetch key inline — never touches GITHUB_ENV.
        # Key lives as a mutable bytearray; zeroed immediately after JWT.
        # ---------------------------------------------------------------
        private_key = fetch_private_key(aws_secret, aws_region)
        if not private_key:
            warn(f"Private key not found for app {app_name} (id: {app_id}, secret: {aws_secret}). Skipping.")
            continue

        try:
            jwt_token = generate_jwt(app_id, private_key)
        finally:
            # Zero key material immediately after JWT is signed.
            # This is the earliest possible moment to release it.
            zero_key(private_key)
            del private_key
      
        installation_id = get_installation_id(jwt_token, org)

        if not installation_id:
            warn(f"No installation found for app {app_name} (id: {app_id}) in org {org}. Skipping.")
            continue

        if auth_mode == "team-membership":

            team_token = generate_installation_token(
                jwt_token, installation_id, "ALL", {"members": "read", "metadata": "read"}
            )

            if not team_token:
                warn(f"Failed to generate token with app {app_name} (id: {app_id}). Trying next app...")
                continue
        
            # Check rate limit for the team token before checking authorization
            remaining = check_rate_limit(team_token)

            if remaining < rate_limit_threshold:
                warn(f"App {app_name} (id: {app_id}) has low rate limit ({remaining} remaining). Trying next app...")
                continue

            # Bypass: trusted platform actor (e.g. mapfre-ci-deployer[bot])
            if check_trusted_actor(caller_actor, trusted_actors, profile, caller_repo, repositories):
                notice(f"Actor '{caller_actor}' is a trusted platform actor. Bypassing team-membership check.")
                bypassed = True
                is_exception = False
            else:
                # Bypass: check if actor is org owner or has specific org roles
                bypassed, is_exception = check_org_roles(org, caller_actor, team_token, bypass_org_owner, bypass_org_roles)

            if is_exception:
                warn(f"Exception occurred while checking org roles for app {app_name} (id: {app_id}). Trying next app...")
                continue

            if bypassed:
                log(f"Actor '{caller_actor}' bypassed team-membership check via org role/ownership.")
            else:
                is_authorized, failed_repos, is_exception = check_team_authorization(org, repositories, caller_actor, team_suffixes, team_token, custom_teams)

                # If an exception occurred during the authorization check, we treat it as a failure and try the next app in the pool.
                if is_exception:
                    warn(f"Exception occurred while checking team authorization for app {app_name} (id: {app_id}). Trying next app...")
                    continue

                if not is_authorized:
                    authorization_requirement = f"repo teams matching configured suffixes for profile '{profile}'"
                    emit_telemetry(
                        "token_denied",
                        profile,
                        app_id,
                        app_name,
                        token_scope,
                        "N/A",
                        caller_repo,
                        caller_actor,
                        f"Authorization failed: actor not in {authorization_requirement} . Failed repositories: {', '.join(failed_repos)}",
                    )
                    fail(
                        f"Authorization denied: '{caller_actor}' is not a member of {authorization_requirement} "
                        f"for repositories: {', '.join(failed_repos)}"
                    )

        token = generate_installation_token(jwt_token, installation_id, token_scope, permissions)

        if not token:
            warn(f"Failed to generate token with app {app_name} (id: {app_id}). Trying next app...")
            continue

        remaining = check_rate_limit(token)

        if remaining < rate_limit_threshold:
            warn(f"App {app_name} (id: {app_id}) has low rate limit ({remaining} remaining). Trying next app...")
            continue

        log(f"Token generated successfully with app {app_name} (id: {app_id}, rate limit remaining: {remaining})")

        # --- Profile: secrets ---
        if profile == "secrets":
            passphrase_value = os.urandom(16).hex()
            success, status_code = create_or_update_repo_secret(
                token, org, caller_repo, "GH_TOKEN_ENCRYPTION_PASSPHRASE", passphrase_value
            )
            if success and status_code == 201 and rotate_org_secret is True:
                passphrase_value = os.urandom(16).hex()
                success, status_code = update_org_secret(
                    token, org, "GH_TOKEN_ENCRYPTION_PASSPHRASE", passphrase_value
                )
                if not success:
                    warn(f"Failed to update ORG Secret GH_TOKEN_ENCRYPTION_PASSPHRASE with app {app_name} (id: {app_id}) (HTTP {status_code}).")
            elif not success:
                fail(f"Failed to create/update Repository Secret on {caller_repo} with app {app_name} (id: {app_id}) (HTTP {status_code}).")

            sys.exit(0)

        # --- Profile: reader / deployer ---
        else:
            encoded_token = encrypt_token_aes(token, gh_token_encryption_passphrase)
            set_output("encoded_token", encoded_token)
            emit_telemetry("token_generated", profile, app_id, app_name, token_scope, remaining, caller_repo, caller_actor)
            sys.exit(0)

    emit_telemetry("pool_exhausted", profile, "none", "none", token_scope, "0", caller_repo, caller_actor,
                   "All apps in pool exhausted or unavailable")
    fail(f"All apps in the '{profile}' pool are exhausted or unavailable. Add more GitHub Apps to the pool.")


if __name__ == "__main__":
    main()
