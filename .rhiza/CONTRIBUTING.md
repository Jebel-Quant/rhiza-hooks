# Contributing

This document is a guide to contributing to the project.

We welcome all contributions. You don't need to be an expert
to help out.

## Checklist

Contributions are made through
[pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests).
Before sending a pull request, make sure you do the following:

- If setup or tooling fails, run `make doctor` first to validate prerequisites and
  follow the install guidance.
- Run `make fmt` to make sure your code adheres to our [coding style](#code-style)
and all tests pass.
- [Write unit tests](#writing-unit-tests) for new functionality added.

## Building from source

You'll need to build the project locally to start editing code.
To install from source, clone the repository from GitHub, 
navigate to its root, and run the following command:

```bash
make install
```

### Windows quick-start (WSL)

The Makefile system requires GNU Make and a POSIX shell, so native Windows
shells (PowerShell, cmd.exe, Git Bash) fail fast with an error. Use the
Windows Subsystem for Linux instead:

1. Install WSL with an Ubuntu distribution (PowerShell, as administrator):

   ```bash
   wsl --install -d Ubuntu
   ```

2. Inside the Ubuntu shell, install the prerequisites that `make doctor` checks
   for (GNU Make and git; `make install` provisions `uv` itself):

   ```bash
   sudo apt-get update && sudo apt-get install -y make git curl
   ```

3. Clone the repository **inside the WSL filesystem** (e.g. `~/projects`), not
   under `/mnt/c/...` — cross-filesystem I/O is dramatically slower and can
   break file-permission assumptions:

   ```bash
   git clone https://github.com/jebel-quant/rhiza.git ~/projects/rhiza
   cd ~/projects/rhiza && make install
   ```

4. Run `make doctor` to confirm the toolchain is complete.

### Optional uv dependency groups

For faster, focused installs you can sync only the dependency groups you need:

```bash
uv sync --group test        # test tooling
uv sync --group docs        # docs/notebook stack (marimo, numpy, pandas, plotly)
uv sync --all-groups        # full development environment
```

There is no `lint` group: `make fmt` runs the hooks through prek, which provisions each
linter itself, so there is nothing for such a group to install.

## Contributing code

To contribute to the project, send us pull requests.
For those new to contributing, check out GitHub's
[guide](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests).

Once you've made your pull request, a member of the
development team will assign themselves to review it.
You might have a few
back-and-forths with your reviewer before it is accepted,
which is completely normal.
Your pull request will trigger continuous integration tests
for many different
Python versions and different platforms. If these tests start failing,
please
fix your code and send another commit, which will re-trigger the tests.

If you'd like to add a new feature, please propose your
change in a GitHub issue to make sure
that your priorities align with ours.

If you'd like to contribute code but don't know where to start,
try one of the
following:

- Read the source and enhance the documentation,
  or address TODOs
- Browse the open issues,
  and look for the issues tagged "help wanted".

## Release process

Releases are tag-driven. The expected flow is:

1. Create and push a version tag (for example with `make release`).
2. The tag triggers `.github/workflows/rhiza_release.yml`.
3. The workflow builds artifacts, generates an SBOM, and drafts the GitHub release.
4. The workflow then regenerates and commits `CHANGELOG.md` to the default branch.

PyPI publishing is deliberately disabled in this repository. `pyproject.toml`
includes the classifier `Private :: Do Not Upload` (`pyproject.toml:23`), and
the release workflow treats that classifier as a kill-switch to skip the PyPI
publish step. This is expected behavior, not a release failure.

## Security posture (OpenSSF Scorecard)

This project tracks its security posture with the
[OpenSSF Scorecard](https://securityscorecards.dev/). The badge in the README
reflects the latest score from the weekly CI run.

**Target:** every individual check should score ≥ 8 / 10.

The checks currently below the target are tracked as open issues (search the
[issue tracker](https://github.com/Jebel-Quant/rhiza-hooks/issues) for
`label:security` or the check name):

| Check              | Notes                                              |
|--------------------|-----------------------------------------------------|
| Token-permissions  | Workflows should declare minimum required permissions |
| Dependency-pinning | Third-party actions should be pinned by commit SHA   |
| Branch-protection  | Branch-protection rules should enforce PR reviews    |

When a check reaches ≥ 8 its row is removed from this table.
The Scorecard workflow runs on every push to `main` and weekly
(`.github/workflows/rhiza_scorecard.yml`).

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must have a
structured prefix so tooling can generate changelogs automatically.

### Format

```
<type>(<scope>): <short summary>
```

`scope` is optional but encouraged when the change is limited to a specific area.

### Types

| Type       | When to use                                      |
|------------|--------------------------------------------------|
| `feat`     | New feature or capability                        |
| `fix`      | Bug fix                                          |
| `docs`     | Documentation only                               |
| `refactor` | Code change that is neither a fix nor a feature  |
| `test`     | Adding or updating tests                         |
| `ci`       | CI / build system changes                        |
| `chore`    | Maintenance tasks (deps, tooling, config)        |
| `perf`     | Performance improvement                          |
| `security` | Security fix or hardening                        |

### Examples

```
feat(templates): add devcontainer template for Python 3.13
fix: resolve path issue in bootstrap script
docs: update CONTRIBUTING with commit conventions
ci: cache uv dependencies in GitHub Actions
```

### Breaking changes

Append `!` after the type/scope and add a `BREAKING CHANGE:` footer:

```
feat!: rename make target from `book` to `docs`

BREAKING CHANGE: the `sync` make target no longer exists; use `/rhiza:update`.
```

## Code style

We use ruff to enforce our Python coding style.
Before sending us a pull request, navigate to the project 
root and run

```bash
make fmt
```

to make sure that your changes abide by our style conventions.
Please fix any errors that are reported before sending
the pull request.

## Writing unit tests

Most code changes will require new unit tests.
Even bug fixes require unit tests,
since the presence of bugs usually indicates insufficient tests.
When adding tests, try to find a file in which your tests should belong;
if you're testing a new feature, you might want to create a new test file.

We use the popular Python [pytest](https://docs.pytest.org/en/) framework for our
tests.

## Running unit tests

We use `pytest` to run our unit tests.
To run all unit tests run the following command:

```bash
make test
```

Please make sure that your change doesn't cause any
of the unit tests to fail.
