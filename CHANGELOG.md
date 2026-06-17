# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `check-template-bundles`: `--retries` and `--timeout` flags to make the remote-fetch
  retry/backoff configurable, and per-attempt logging so CI failures are diagnosable (#179)
- End-to-end test that runs a hook through `pre-commit try-repo`, exercising the
  `.pre-commit-hooks.yaml` ↔ `[project.scripts]` wiring (#184)

### Changed

- `check-template-bundles`: replace union return types with a typed `BundlesDoc` result and
  remove all `cast()` calls (#173)
- `check-template-bundles`: split the module into focused `_bundles_fetch` / `_bundles_validate` /
  `_bundles_config` units behind an unchanged public surface (#191)
- `check-python-version-consistency`: narrow the broad `except Exception` in
  `get_pyproject_requires_python` to `(tomllib.TOMLDecodeError, OSError)` so unexpected errors
  surface (#174)

## [0.6.2] - 2026-06-13

### Added

- Add OpenSSF Scorecard workflow and README badge (#146)
- Add py.typed marker for PEP 561 type distribution (#138)

### Changed

- Advertise enforced 100% mutation score in README and testing docs (#157)
- Remove duplicate Changelog item from MkDocs navigation (#158)
- Add explicit no-funding metadata for community profile completeness (#159)
- Collapse repetitive field validators into a rule table (#145)
- Address open issues #119–#123 (#124)
- Tighten tooling rigor: type checking, coverage gate, warnings-as-errors (#118)

### Fixed

- Correct unresolvable scorecard-action SHA pin (#148)

### Documentation

- Add Getting help section to README (#156)
- Surface CODE_OF_CONDUCT and CONTRIBUTING at .github/ path (#143)
- Surface CHANGELOG.md in MkDocs nav (#140)
- Surface changelog in MkDocs nav (#144)
- Document SBOM retrieval for consumers in SECURITY.md (#139)
- Update README pre-commit rev example to v0.5.1 (#137)

### Maintenance

- Add advisory mutation-testing signal (mutmut) (#147)
- Add uv.lock integrity gate to CI (#155)
- Add Hypothesis property-based tests for pure helpers (#141)

### Dependencies

- Chore(deps)(deps): bump the github-actions group with 9 updates (#117)
- Chore(deps-dev)(deps-dev): bump ruff in the python-dependencies group (#116)

## [0.5.1] - 2026-06-08

### Maintenance

- Update rhiza to v0.18.8 (#115)
- Update rhiza to v0.18.4 (#112)

### Dependencies

- Chore(deps)(deps): bump the github-actions group with 9 updates (#114)
- Chore(deps)(deps): bump the github-actions group with 8 updates (#113)

## [0.5.0] - 2026-05-28

### Maintenance

- Update rhiza to v0.18.2 (#111)
- Update rhiza to v0.17.0 (#109)
- Update rhiza to v0.15.3 (#108)
- Bump rhiza to v0.15.2 (#107)
- Update rhiza to v0.15.2 (#106)
- Bump rhiza to v0.14.1 with github-project profile (#103)
- Update Rhiza template to v0.10.9 (#102)

### Dependencies

- Chore(deps-dev)(deps-dev): bump types-pyyaml (#101)

## [0.4.0] - 2026-05-19

### Changed

- Accept `profiles` in `.rhiza/template.yml` for `check-rhiza-config` (#96)
- Remove Guides section from mkdocs.yml (#98)
- Update reference version to v0.10.3 (#91)
- Update mkdocs.yml
- Tschm patch 1 (#90)
- Add root-level mkdocs.yml inheriting from docs/mkdocs-base.yml (#86)

### Fixed

- Serve coverage badge from GitHub Pages instead of gh-pages branch (#100)
- Ensure _book/ exists before touching .nojekyll when mkdocs.yml is absent

### Documentation

- Add API reference and CI/CD reports to book

### Maintenance

- Update Rhiza template to v0.10.7 (#97)
- Sync rhiza template to latest (#88)
- Update rhiza template version to v0.10.1 (#87)
- Sync rhiza template v0.9.5
- Update rhiza template version to v0.9.5
- Update template.yml to reference version v0.9.4 (#84)

### Dependencies

- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#94)
- Chore(deps-dev)(deps-dev): bump types-pyyaml (#93)
- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#92)
- Chore(deps)(deps): bump the github-actions group with 2 updates (#89)
- Lock file maintenance (#83)
- Update pre-commit hook jebel-quant/rhiza-hooks to v0.3.3 (#82)

## [0.3.3] - 2026-04-12

### Maintenance

- Update template.yml to use ref v0.9.2 (#80)

### Dependencies

- Chore(deps)(deps): bump docker/login-action in the github-actions group (#79)

## [0.3.2] - 2026-04-02

### Maintenance

- Update ref version to v0.8.20 and add renovate template (#78)

### Dependencies

- Chore(deps)(deps): bump github/codeql-action in the github-actions group (#77)

## [0.3.1] - 2026-03-22

### Changed

- Add license-files to pyproject.toml (#76)
- [WIP] Add coverage badge pointing to gh-pages (#75)
- Update __init__.py (#73)
- Tschm patch 200 (#72)
- Update .cfg.toml (#52)
- Sync

### Maintenance

- Update template.yml to use ref v0.8.13 (#71)
- Update template.yml to reference version v0.8.12 (#67)
- Update template repository and version reference

### Dependencies

- Update github/codeql-action action to v4.33.0 (#65)
- Update actions/upload-artifact action to v7 (#62)
- Update actions/download-artifact action to v8 (#61)
- Update docker/login-action action to v4 (#66)
- Update astral-sh/setup-uv action to v7.3.1 (#56)
- Update dependency jebel-quant/rhiza to v0.8.3 (#54)
- Update pre-commit hook astral-sh/uv-pre-commit to v0.10.5 (#55)
- Update dependency astral-sh/uv to v0.10.5 (#53)
- Update github/codeql-action action to v4.32.4 (#51)
- Update pre-commit hook astral-sh/ruff-pre-commit to v0.15.2 (#50)
- Update pre-commit hook astral-sh/uv-pre-commit to v0.10.4 (#49)
- Update dependency astral-sh/uv to v0.10.4 (#48)
- Update dependency jebel-quant/rhiza to v0.8.0 (#46)
- Update actions/download-artifact action to v7 (#47)
- Update pre-commit hook rhysd/actionlint to v1.7.11 (#45)
- Update pre-commit hook python-jsonschema/check-jsonschema to v0.36.2 (#44)
- Update dependency astral-sh/uv to v0.10.3 (#42)
- Update pre-commit hook astral-sh/uv-pre-commit to v0.10.3 (#43)

## [0.3.0] - 2026-02-13

### Changed

- Add `repository` and `ref` as aliases for template configuration keys (#41)
- Sync (#39)
- Sync

### Fixed

- Fix pdoc documentation including __pycache__ directories
- Fix broken link to non-existent book/README.md

### Dependencies

- Update pre-commit hook astral-sh/uv-pre-commit to v0.10.2 (#37)
- Update pre-commit hook jebel-quant/rhiza-hooks to v0.2.1 (#38)
- Update dependency astral-sh/uv to v0.10.1 (#36)

## [0.2.1] - 2026-02-08

### Changed

- Do not push to pypi

## [0.2.0] - 2026-02-08

### Changed

- Refactor complex functions to reduce cyclomatic complexity (#35)
- Achieve 100% test coverage for rhiza-hooks (#34)
- Add CodeFactor badge to README (#33)
- Hooks (#32)
- Delete .github/workflows/hooks_release.yml (#31)
- Adopt src layout for package structure (#30)
- Sync (#28)
- Tschm patch 1 (#27)
- Delete .rhiza/template-bundles.yml
- Update pre commit (#26)

### Fixed

- Fix linting issues and apply code formatting

### Maintenance

- Tests (#29)

## [0.1.6] - 2026-02-05

### Fixed

- Fix check-template-bundles hook path resolution and add template filtering (#25)

## [0.1.5] - 2026-02-05

### Changed

- Delete .rhiza/make.d/02-book.mk (#23)
- Delete book/marimo/notebooks directory (#22)
- Delete .github/workflows/rhiza_benchmarks.yml (#20)
- Delete .github/workflows/rhiza_book.yml (#21)
- Add template-bundles.yml validator with dependency checking (#19)

## [0.1.4] - 2026-02-05

### Changed

- Update README.md
- Make "include" and "templates" optional in template.yml validation (with mutual requirement) (#15)
- Deactivate the make help output
- Fmt
- Sync
- Sync
- Revert "fmt"
- Fmt

### Fixed

- Patch subprocess directly in module execution test

### Maintenance

- Increase test coverage to 100%

### Dependencies

- Update pre-commit hook astral-sh/uv-pre-commit to v0.9.30 (#13)
- Update dependency astral-sh/uv to v0.9.30 (#11)
- Update ghcr.io/astral-sh/uv docker tag to v0.9.30 (#12)
- Update pre-commit hook abravalheri/validate-pyproject to v0.25 (#9)
- Update github/codeql-action action to v4.32.1 (#8)
- Update astral-sh/setup-uv action to v7 (#7)
- Update actions/checkout action to v6 (#5)
- Update actions/setup-python action to v6 (#6)
- Update dependency python to 3.14 (#4)

## [0.1.3] - 2026-02-02

### Fixed

- Fix relesae

## [0.1.2] - 2026-02-01

### Changed

- Use make test

### Maintenance

- Update template

## [0.1.1] - 2026-02-01

### Changed

- Configure bumpversion for hooks
- Make fmt
- Add yaml types for mypy
- Make fmt
- Bring coverage > 90%
- Make sync exclude cfg
- Add release pipeline and README update

### Fixed

- Fix bugs and override source

## [0.1.0] - 2026-02-01

### Changed

- Initial


