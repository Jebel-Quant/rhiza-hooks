# API Reference

`rhiza_hooks` ships six pre-commit hooks, each implemented as a standalone module with a `main()` entry point.

| Module | Entry point | Purpose |
|---|---|---|
| [`check_makefile_targets`](check_makefile_targets.md) | `check-makefile-targets` | Verify required Makefile targets are present |
| [`check_python_version`](check_python_version.md) | `check-python-version-consistency` | Assert Python version is consistent across project files |
| [`check_rhiza_config`](check_rhiza_config.md) | `check-rhiza-config` | Validate `.rhiza/template.yml` |
| [`check_template_bundles`](check_template_bundles.md) | `check-template-bundles` | Validate `template-bundles.yml` structure |
| [`check_workflow_names`](check_workflow_names.md) | `check-rhiza-workflow-names` | Enforce `(RHIZA)` prefix on GitHub Actions workflow names |
| [`update_readme_help`](update_readme_help.md) | `update-readme-help` | Embed `make help` output into `README.md` |
