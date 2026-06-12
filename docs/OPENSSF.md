# OpenSSF Best Practices badge — application pack

The badge is applied for at https://www.bestpractices.dev — sign in with
the GitHub account that owns the repo, click *Get Your Badge Now*, enter
`https://github.com/bcllcc/modulor`, then answer the questionnaire. The
answers below map our reality to the **passing** criteria; everything is
already in place, so this is a paste-through exercise (~20 minutes).

When granted, add to README:
`[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/<ID>/badge)](https://www.bestpractices.dev/projects/<ID>)`

## Basics

| criterion | answer | evidence |
|---|---|---|
| Project/homepage URL | Met | https://github.com/bcllcc/modulor |
| Description | Met | README (bilingual) |
| Contribution process | Met | CONTRIBUTING.md |
| Contribution requirements | Met | CONTRIBUTING.md (quality bar, contract workflow) |
| FLOSS license | Met | MIT, LICENSE file, SPDX-recognized |
| License location | Met | /LICENSE |
| Documentation: basics | Met | README, AGENT_GUIDE.md, integrations/COOKBOOK.md |
| Documentation: interface | Met | docs/API.md + docs/api.json (generated reference), docs/FORMAT.md |
| HTTPS | Met | GitHub + PyPI |
| Discussion | Met | GitHub Issues + Discussions enabled |
| English | Met | all specs/docs in English (README bilingual) |
| Maintained | Met | active releases |

## Change control

| criterion | answer | evidence |
|---|---|---|
| Public VCS | Met | GitHub |
| Version numbering | Met | semver; GOVERNANCE.md §2 |
| Unique version per release | Met | tags v0.1.0 … v1.0.0rc1; PyPI |
| Release notes | Met | CHANGELOG.md |
| Release notes identify fixes | Met | CHANGELOG.md per series |

## Reporting

| criterion | answer | evidence |
|---|---|---|
| Bug reporting process | Met | .github/ISSUE_TEMPLATE/bug_report.yml |
| Bug tracker | Met | GitHub Issues |
| Responses to bugs | Met | maintainer responds; recent history in Issues |
| Vulnerability report process | Met | SECURITY.md (private vulnerability reporting enabled) |
| Private vulnerability reports | Met | GitHub Security Advisories, no public disclosure needed |
| Response time ≤ 14 days | Met | SECURITY.md commits to 7 days |

## Quality

| criterion | answer | evidence |
|---|---|---|
| Working build system | Met | pip/setuptools (`pip install -e .`), `python -m build` |
| Automated test suite | Met | pytest, 165 tests, runs in CI |
| Tests invoked standardly | Met | `pytest tests` |
| New functionality has tests | Met | CONTRIBUTING.md requires it; contract tests enforce interface coverage |
| Tests as policy | Met | CONTRIBUTING.md "Quality bar for PRs" |
| Warning flags / linters | Met | strict JSON schema validation in CI; contract drift fails CI |
| CI | Met | GitHub Actions, 3 OS × 2 Python + manifest validation job |

## Security

| criterion | answer | evidence |
|---|---|---|
| Secure development knowledge | Met | input validation everywhere (finite-number checks, resource budgets, AST-whitelisted expressions — modulor/expr.py) |
| No unencrypted auth / no network | N/A → Met | the kernel performs no network I/O and stores no credentials |
| Crypto criteria | N/A | no cryptography used |
| Delivered via HTTPS | Met | PyPI |
| Known vulnerabilities fixed | Met | none known; process in SECURITY.md |
| No leaked credentials | Met | public history is a clean noreply-authored tree |

## Analysis

| criterion | answer | evidence |
|---|---|---|
| Static analysis | Met | contract tests + JSON-schema validation of all artifacts in CI |
| Static analysis often | Met | every push |
| Dynamic analysis | Met | behavioral fuzzer (scripts/fuzz.py): random+adversarial op batches; bounded deterministic slice runs in CI (tests/test_fuzz.py); 64k-command campaigns across seeds |
| Dynamic analysis on releases | Met | fuzz slice in CI gates every release tag |
