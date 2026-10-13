# Scenarios

Each `*.env` file defines one scenario run by `test/local-test.sh`.

## Variables

| Var | Required | Purpose |
|---|---|---|
| `DESCRIPTION` | yes | Short human summary printed in the header. |
| `PROFILE` | yes | `reader`, `deployer`, or `secrets`. |
| `CALLER_REPO` | yes | Repo that "hosts" the workflow run. |
| `REPOSITORIES` | yes | Comma-separated scope for the token. |
| `GITHUB_ACTOR` | yes | Actor passed as `caller-actor` (may be a human login or a `[bot]` account). |
| `EXPECT` | yes | `pass` (token must be minted) or `fail` (must be denied). |
| `EXPECT_LOG` | no | Substring that must appear in the tool's log (asserted alongside `EXPECT`). |
| `PLATFORM_REPOSITORIES` | no | Override the platform-repos list (defaults to empty). |
| `GITHUB_ORG` | no | Defaults to `mapfre-tech`. |
| `AWS_REGION` | no | Defaults to `eu-west-1`. |

## Naming convention

`NN-short-slug.env` — the leading number keeps a stable execution order.

## Running

```bash
bash test/local-test.sh                # all scenarios
bash test/local-test.sh 02             # scenarios whose name matches '02'
bash test/local-test.sh 02 04          # multiple patterns
bash test/local-test.sh --list         # list available scenarios
bash test/local-test.sh --full         # after scenarios, run the legacy
                                       # end-to-end steps (refresh + Zeus)
```

Exit codes: `0` all matched scenarios passed, `1` at least one failed, `2` usage error.
