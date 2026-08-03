# API Reference

`rhiza_hooks` ships a console script per module, each a standalone module with a `main()` entry point. All but one are also published as pre-commit hooks — see the note below the table.

| Module | Entry point | Purpose |
|---|---|---|
| [`check_bumpversion_config`](check_bumpversion_config.md) | `check-bumpversion-config` | Assert a bumpversion section exists where bump-my-version searches, and agrees with `pyproject.toml` |
| [`check_go_version`](check_go_version.md) | `check-go-version-consistency` | Assert the `go.mod` directives and `.go-version` agree |
| [`check_license_metadata`](check_license_metadata.md) | `check-license-metadata` | Reject a PEP 639 license expression declared alongside a `License ::` trove classifier |
| [`check_makefile_targets`](check_makefile_targets.md) | `check-makefile-targets` | Verify required Makefile targets are present |
| [`check_managed_files`](check_managed_files.md) | `check-managed-files` | Refuse edits to files listed in `.rhiza/template.lock`, which the next sync overwrites |
| [`check_python_version`](check_python_version.md) | `check-python-version-consistency` | Assert Python version is consistent across project files |
| [`check_rhiza_config`](check_rhiza_config.md) | `check-rhiza-config` | Validate `.rhiza/template.yml` |
| [`check_rust_version`](check_rust_version.md) | `check-rust-version-consistency` | Assert the pinned Rust toolchain is not older than the declared MSRV |
| [`check_template_bundles`](check_template_bundles.md) | `check-template-bundles` | Validate `template-bundles.yml` structure |
| [`check_workflow_make_targets`](check_workflow_make_targets.md) | `check-workflow-make-targets` | Assert every make target a CI workflow runs is defined in the Makefile or its includes |
| [`check_workflow_names`](check_workflow_names.md) | `check-rhiza-workflow-names` | Enforce `(RHIZA)` prefix on GitHub Actions workflow names |
| [`render_precommit`](render_precommit.md) | `render-precommit` | Render a `.pre-commit-config.yaml` from fragments; checks for drift unless given `--write` |
| [`update_readme_help`](update_readme_help.md) | `update-readme-help` | Embed `make help` output into `README.md` |

`render_precommit` is the one module that is **not** a pre-commit hook. It renders a
`.pre-commit-config.yaml`, and pre-commit reads that file once before any hook runs — so
a render can only ever affect the *next* invocation. It belongs in the build step ahead
of pre-commit, and ships here as a console script only.

## Internal modules

These modules hold shared logic used by the hooks above. They have no `main()` entry point and are not part of the public CLI surface, but are documented here for contributors.

| Module | Purpose |
|---|---|
| [`_bundles_config`](_bundles_config.md) | Read the project's `.rhiza/template.yml` configuration |
| [`_bundles_fetch`](_bundles_fetch.md) | Load/fetch a template-bundles document (local, bytes, or remote) into a typed result |
| [`_bundles_validate`](_bundles_validate.md) | Structural validation of a template-bundles document |
| [`_bumpversion_config`](_bumpversion_config.md) | Locate and parse the bumpversion config bump-my-version would read, in either format |
| [`_config_schema`](_config_schema.md) | Canonical `.rhiza/template.yml` keys, aliases, and config normalization |
| [`_makefile`](_makefile.md) | Shared Makefile parsing: target extraction and `include` expansion |
| [`_managed`](_managed.md) | Resolve the template-owned paths — `.rhiza/template.lock`'s `files:` minus `template.yml`'s `exclude:` |
| [`_repo`](_repo.md) | Shared helpers (e.g. locating the repository root) |
| [`_version`](_version.md) | Shared dotted-numeric version parsing and comparison, used by the Rust and Go hooks |
| [`_yaml`](_yaml.md) | Shared helper for loading a YAML file into a top-level mapping |
