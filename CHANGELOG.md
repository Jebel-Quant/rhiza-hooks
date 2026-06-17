# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com),
and entries are generated from [Conventional Commits](https://www.conventionalcommits.org).

## [0.6.3] - 2026-06-17

### Documentation
- *(contributing)* Document release flow and PyPI publish kill-switch (#186)
- *(contributing)* Document OpenSSF Scorecard target and sub-8 checks (#187)
- Add per-hook troubleshooting sections to README (#188)
- Document --retries/--timeout flags and add Unreleased changelog (#193)

### Maintenance
- *(#191)* Split check_template_bundles into fetch/validate/config modules (#192)
- Chore(deps)(deps): bump the github-actions group with 10 updates (#196)
- Add Rhiza Claude commands (/rhiza_quality, /rhiza_update) (#194)
- Chore(deps-dev)(deps-dev): bump the python-dependencies group with 2 updates (#195)

### Other Changes
- Harden hooks + dedupe: find_repo_root, workflow-name block scalars, Makefile regex, bundle validation (#171)
- Address remaining hook issues: makefile targets, fetch retry/offline, docs (#161, #163, #166, #167, #168, #169, #170) (#172)
- Address #175, #177, #180: gitignore mypy cache, SHA-pin workflows, compound requires-python (#185)
- Refactor #173: typed BundlesDoc result, remove all cast() calls (#189)
- Address open enhancement issues (#174, #179, #184) (#190)
- Sync Rhiza template v0.18.8 → v0.19.3 (#197)
- Install rhiza_hooks into the book build env for mkdocstrings (#201)

## [0.6.2] - 2026-06-13

### Other Changes
- Bump version 0.6.1 → 0.6.2

## [0.6.1] - 2026-06-13

### Other Changes
- Bump version 0.6.0 → 0.6.1

## [0.6.0] - 2026-06-13

### New Features
- Add py.typed marker for PEP 561 type distribution (#138)
- Add OpenSSF Scorecard workflow and README badge (#146)

### Bug Fixes
- *(ci)* Correct unresolvable scorecard-action SHA pin (#148)

### Documentation
- Update README pre-commit rev example to v0.5.1 (#137)
- Document SBOM retrieval for consumers in SECURITY.md (#139)
- Surface changelog in MkDocs nav (#144)
- Surface CHANGELOG.md in MkDocs nav (#140)
- Surface CODE_OF_CONDUCT and CONTRIBUTING at .github/ path (#143)
- Add Getting help section to README (#156)

### Maintenance
- Chore(deps-dev)(deps-dev): bump ruff in the python-dependencies group (#116)
- Chore(deps)(deps): bump the github-actions group with 9 updates (#117)
- Add Hypothesis property-based tests for pure helpers (#141)
- Collapse repetitive field validators into a rule table (#145)
- Add uv.lock integrity gate to CI (#155)
- Add advisory mutation-testing signal (mutmut) (#147)

### Other Changes
- Tighten tooling rigor: type checking, coverage gate, warnings-as-errors (#118)
- Address open issues #119–#123 (#124)
- Add explicit no-funding metadata for community profile completeness (#159)
- Remove duplicate Changelog item from MkDocs navigation (#158)
- Advertise enforced 100% mutation score in README and testing docs (#157)
- Bump version 0.5.1 → 0.6.0

## [0.5.1] - 2026-06-08

### Maintenance
- Update rhiza to v0.18.4 (#112)
- Chore(deps)(deps): bump the github-actions group with 8 updates (#113)
- Chore(deps)(deps): bump the github-actions group with 9 updates (#114)
- Update rhiza to v0.18.8 (#115)

### Other Changes
- Bump version 0.5.0 → 0.5.1

## [0.5.0] - 2026-05-28

### Maintenance
- Chore(deps-dev)(deps-dev): bump types-pyyaml (#101)
- Update Rhiza template to v0.10.9 (#102)
- Update rhiza to v0.15.2 (#106)
- Update rhiza to v0.15.3 (#108)
- Update rhiza to v0.17.0 (#109)
- Update rhiza to v0.18.2 (#111)

### Other Changes
- Bump version 0.4.0 → 0.5.0

## [0.4.0] - 2026-05-19

### Bug Fixes
- Serve coverage badge from GitHub Pages instead of gh-pages branch (#100)

### Documentation
- Add API reference and CI/CD reports to book

### Dependencies
- *(deps)* Update pre-commit hook jebel-quant/rhiza-hooks to v0.3.3 (#82)
- *(deps)* Lock file maintenance (#83)

### Maintenance
- Update rhiza template version to v0.9.5
- Sync rhiza template v0.9.5
- Update rhiza template version to v0.10.1 (#87)
- Chore(deps)(deps): bump the github-actions group with 2 updates (#89)
- Sync rhiza template to latest (#88)
- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#92)
- Chore(deps-dev)(deps-dev): bump types-pyyaml (#93)
- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#94)
- Update Rhiza template to v0.10.7 (#97)

### Other Changes
- Ensure _book/ exists before touching .nojekyll when mkdocs.yml is absent
- Update template.yml to reference version v0.9.4 (#84)
- Add root-level mkdocs.yml inheriting from docs/mkdocs-base.yml (#86)
- Tschm patch 1 (#90)
- Update mkdocs.yml
- Update reference version to v0.10.3 (#91)
- Remove Guides section from mkdocs.yml (#98)
- Accept `profiles` in `.rhiza/template.yml` for `check-rhiza-config` (#96)
- Bump version 0.3.3 → 0.4.0

## [0.3.3] - 2026-04-12

### Maintenance
- Chore(deps)(deps): bump docker/login-action in the github-actions group (#79)

### Other Changes
- Update template.yml to use ref v0.9.2 (#80)
- Bump version 0.3.2 → 0.3.3

## [0.3.2] - 2026-04-02

### Maintenance
- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#77)

### Other Changes
- Update ref version to v0.8.20 and add renovate template (#78)
- Bump version 0.3.1 → 0.3.2

## [0.3.1] - 2026-03-22

### Dependencies
- *(deps)* Update pre-commit hook astral-sh/uv-pre-commit to v0.10.3 (#43)
- *(deps)* Update dependency astral-sh/uv to v0.10.3 (#42)
- *(deps)* Update pre-commit hook python-jsonschema/check-jsonschema to v0.36.2 (#44)
- *(deps)* Update pre-commit hook rhysd/actionlint to v1.7.11 (#45)
- *(deps)* Update actions/download-artifact action to v7 (#47)
- *(deps)* Update dependency jebel-quant/rhiza to v0.8.0 (#46)
- *(deps)* Update dependency astral-sh/uv to v0.10.4 (#48)
- *(deps)* Update pre-commit hook astral-sh/uv-pre-commit to v0.10.4 (#49)
- *(deps)* Update pre-commit hook astral-sh/ruff-pre-commit to v0.15.2 (#50)
- *(deps)* Update github/codeql-action action to v4.32.4 (#51)
- *(deps)* Update dependency astral-sh/uv to v0.10.5 (#53)
- *(deps)* Update pre-commit hook astral-sh/uv-pre-commit to v0.10.5 (#55)
- *(deps)* Update dependency jebel-quant/rhiza to v0.8.3 (#54)
- *(deps)* Update astral-sh/setup-uv action to v7.3.1 (#56)
- *(deps)* Update docker/login-action action to v4 (#66)
- *(deps)* Update actions/download-artifact action to v8 (#61)
- *(deps)* Update actions/upload-artifact action to v7 (#62)
- *(deps)* Update github/codeql-action action to v4.33.0 (#65)

### Other Changes
- Update template repository and version reference
- Sync
- Update .cfg.toml (#52)
- Update template.yml to reference version v0.8.12 (#67)
- Update template.yml to use ref v0.8.13 (#71)
- Tschm patch 200 (#72)
- Update __init__.py (#73)
- [WIP] Add coverage badge pointing to gh-pages (#75)
- Add license-files to pyproject.toml (#76)
- Bump version 0.3.0 → 0.3.1

## [0.3.0] - 2026-02-13

### Dependencies
- *(deps)* Update dependency astral-sh/uv to v0.10.1 (#36)
- *(deps)* Update pre-commit hook jebel-quant/rhiza-hooks to v0.2.1 (#38)
- *(deps)* Update pre-commit hook astral-sh/uv-pre-commit to v0.10.2 (#37)

### Other Changes
- Fix broken link to non-existent book/README.md
- Fix pdoc documentation including __pycache__ directories
- Sync
- Sync (#39)
- Add `repository` and `ref` as aliases for template configuration keys (#41)
- Bump version 0.2.1 → 0.3.0

## [0.2.1] - 2026-02-08

### Other Changes
- Do not push to pypi
- Bump version 0.2.0 → 0.2.1

## [0.2.0] - 2026-02-08

### Maintenance
- Tests (#29)

### Other Changes
- Update pre commit (#26)
- Delete .rhiza/template-bundles.yml
- Tschm patch 1 (#27)
- Sync (#28)
- Adopt src layout for package structure (#30)
- Delete .github/workflows/hooks_release.yml (#31)
- Hooks (#32)
- Add CodeFactor badge to README (#33)
- Achieve 100% test coverage for rhiza-hooks (#34)
- Refactor complex functions to reduce cyclomatic complexity (#35)
- Fix linting issues and apply code formatting
- Bump version 0.1.6 → 0.2.0

## [0.1.6] - 2026-02-05

### Other Changes
- Fix check-template-bundles hook path resolution and add template filtering (#25)
- Bump version 0.1.5 → 0.1.6

## [0.1.5] - 2026-02-05

### Other Changes
- Add template-bundles.yml validator with dependency checking (#19)
- Delete .github/workflows/rhiza_book.yml (#21)
- Delete .github/workflows/rhiza_benchmarks.yml (#20)
- Delete book/marimo/notebooks directory (#22)
- Delete .rhiza/make.d/02-book.mk (#23)
- Bump version 0.1.4 → 0.1.5

## [0.1.4] - 2026-02-05

### Bug Fixes
- Patch subprocess directly in module execution test

### Dependencies
- *(deps)* Update dependency python to 3.14 (#4)
- *(deps)* Update actions/setup-python action to v6 (#6)
- *(deps)* Update actions/checkout action to v6 (#5)
- *(deps)* Update astral-sh/setup-uv action to v7 (#7)
- *(deps)* Update github/codeql-action action to v4.32.1 (#8)
- *(deps)* Update pre-commit hook abravalheri/validate-pyproject to v0.25 (#9)
- *(deps)* Update ghcr.io/astral-sh/uv docker tag to v0.9.30 (#12)
- *(deps)* Update dependency astral-sh/uv to v0.9.30 (#11)
- *(deps)* Update pre-commit hook astral-sh/uv-pre-commit to v0.9.30 (#13)

### Maintenance
- Increase test coverage to 100%

### Other Changes
- Fmt
- Revert "fmt"
- Sync
- Sync
- Fmt
- Deactivate the make help output
- Make "include" and "templates" optional in template.yml validation (with mutual requirement) (#15)
- Update README.md
- Bump version 0.1.3 → 0.1.4

## [0.1.3] - 2026-02-02

### Bug Fixes
- Fix relesae

### Other Changes
- Bump version 0.1.2 → 0.1.3

## [0.1.2] - 2026-02-01

### Other Changes
- Update template
- Use make test
- Bump version 0.1.1 → 0.1.2

## [0.1.1] - 2026-02-01

### Bug Fixes
- Fix bugs and override source

### Other Changes
- Add release pipeline and README update
- Make sync exclude cfg
- Bring coverage > 90%
- Make fmt
- Add yaml types for mypy
- Make fmt
- Configure bumpversion for hooks
- Bump version 0.1.0 → 0.1.1

## [0.1.0] - 2026-02-01

### Other Changes
- Initial

<!-- generated by git-cliff -->
