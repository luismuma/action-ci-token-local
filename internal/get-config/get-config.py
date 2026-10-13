#!/usr/bin/env python3
"""
get-config.py — Load GitHub App pool configuration and platform repositories list.

Reads config/apps.yaml and config/repos.yml, applying filtering logic based
on include-cap-repos and platform-repo inputs.

Required environment variables:
  CONFIG_PATH          — path to the config directory containing apps.yaml and repos.yml
  INCLUDE_CAP_REPOS   — "true" to include cap-repositories section, "false" otherwise
  PLATFORM_REPO_INPUT — optional comma-separated list of platform repositories to filter; if set, must be in the allowed list
  GITHUB_OUTPUT        — path to GitHub Actions output file
"""

import os
import sys

import yaml


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def main():
    config_path = os.environ.get("CONFIG_PATH", "")
    include_cap_repos = os.environ.get("INCLUDE_CAP_REPOS", "false").lower() == "true"
    platform_repo_input = os.environ.get("PLATFORM_REPO_INPUT", "").strip()
    github_output = os.environ.get("GITHUB_OUTPUT", "")

    if not config_path:
        fail("CONFIG_PATH env var is not set")

    apps_path = os.path.join(config_path, "apps.yaml")
    repos_path = os.path.join(config_path, "repos.yml")

    # --- Validate files exist ---
    if not os.path.isfile(apps_path):
        fail(f"Config file not found: {apps_path}")
    if not os.path.isfile(repos_path):
        fail(f"Repos file not found: {repos_path}")

    # --- Read apps.yaml content ---
    with open(apps_path, "r", encoding="utf-8") as f:
        apps_content = f.read()

    # --- Parse repos.yml ---
    with open(repos_path, "r", encoding="utf-8") as f:
        repos_data = yaml.safe_load(f)

    platform_repos = repos_data.get("platform-repositories", []) or []
    cap_repos = repos_data.get("cap-repositories", []) or []

   
    # Filter by platform-repo if specified (accepts comma-separated list)
    if platform_repo_input:
        platform_repo_list = [r for r in (repo.strip() for repo in platform_repo_input.split(",")) if r]
        if not platform_repo_list:
            fail("Invalid platform-repo input: empty after trimming blank entries")
        for repo in platform_repo_list:
            if repo not in platform_repos:
                allowed_csv = ",".join(platform_repos)
                fail(f"Invalid platform-repo '{repo}'. Allowed values: {allowed_csv}")
        platform_repos = platform_repo_list


    # Build allowed repos list
    if include_cap_repos:
        allowed_repos = platform_repos + cap_repos
    else:
        allowed_repos = list(platform_repos) 

    repos_output = ",".join(allowed_repos)  

    # --- Write outputs ---
    if not github_output:
        fail("GITHUB_OUTPUT env var is not set")

    with open(github_output, "a", encoding="utf-8") as out:
        out.write("apps<<EOFAPPS\n")
        out.write(apps_content)
        if not apps_content.endswith("\n"):
            out.write("\n")
        out.write("EOFAPPS\n")
        out.write(f"repos={repos_output}\n")


if __name__ == "__main__":
    main()
