# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| n-1     | :white_check_mark: |
| older   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **GitHub Security Advisories** (Preferred)
   - Go to the Security Advisories page of this repository
   - Click "New draft security advisory"
   - Fill in the details and submit

2. **Email**
   - Send details to the repository maintainers
   - Include "SECURITY" in the subject line

### What to Include

Please include the following information in your report:

- **Description**: A clear description of the vulnerability
- **Impact**: The potential impact of the vulnerability
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Affected Versions**: Which versions are affected
- **Suggested Fix**: If you have one (optional)

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Initial Assessment**: We will provide an initial assessment within 7 days
- **Resolution Timeline**: We aim to resolve critical issues within 30 days
- **Credit**: We will credit reporters in the security advisory (unless you prefer to remain anonymous)

### Scope

This security policy applies to:

- The source code and configuration files in this repository
- GitHub Actions workflows provided by this repository
- Python utilities and scripts maintained in this repository

### Out of Scope

The following are generally out of scope:

- Vulnerabilities in upstream dependencies (report these to the respective projects)
- Issues that require physical access to a user's machine
- Social engineering attacks
- Denial of service attacks that require significant resources

## Security Measures

This project implements several security measures:

### Code Scanning
- **CodeQL**: Automated code scanning for Python and GitHub Actions
- **Bandit**: Python security linter integrated in CI and pre-commit
- **pip-audit**: Dependency vulnerability scanning
- **Secret Scanning**: GitHub secret scanning enabled on this repository

### Supply Chain Security
- **SLSA Provenance**: Build attestations for release artifacts (public repositories only)
- **SBOM**: Software Bill of Materials attached to every GitHub Release (see [SBOM Retrieval](#sbom-retrieval) below)
- **Locked Dependencies**: `uv.lock` ensures reproducible builds
- **Dependabot**: Automated dependency updates with security patches (version and security updates)
- **Renovate**: Additional automated dependency update management

### Release Security
- **OIDC Publishing**: PyPI trusted publishing without stored credentials
- **Signed Commits**: GPG signing supported for releases
- **Tag Protection**: Releases require version tag validation

## SBOM Retrieval

Every release of this project includes a **Software Bill of Materials (SBOM)** so that consumers can audit the exact dependency tree used to build the package.

### Format

SBOMs are generated using [CycloneDX](https://cyclonedx.org/) — an industry-standard format for software supply chain security — in two machine-readable representations:

| File | Format | Use case |
|------|--------|----------|
| `sbom.cdx.json` | CycloneDX JSON | Primary / canonical format |
| `sbom.cdx.xml`  | CycloneDX XML  | Compatibility with XML-based tooling |

### Where to Find the SBOM

**GitHub Release assets** (recommended)

The SBOM files are attached directly to each [GitHub Release](../../releases). To download them:

1. Go to the **Releases** page of this repository.
2. Open the release you are interested in (e.g. `v1.2.3`).
3. Under **Assets**, download `sbom.cdx.json` or `sbom.cdx.xml`.

You can also download them with `curl` or `gh`:

```bash
# Using the GitHub CLI
gh release download v1.2.3 --repo Jebel-Quant/rhiza-hooks --pattern 'sbom.*'

# Using curl (replace <tag> and <org/repo> as needed)
curl -L https://github.com/Jebel-Quant/rhiza-hooks/releases/download/v1.2.3/sbom.cdx.json -o sbom.cdx.json
```

**SBOM attestations** (public repositories only)

For public releases an attestation is also created via [`actions/attest`](https://github.com/actions/attest), which cryptographically binds the SBOM to the release workflow run. You can verify the attestation with the GitHub CLI:

```bash
gh attestation verify sbom.cdx.json --repo Jebel-Quant/rhiza-hooks
```

### Consuming the SBOM

The CycloneDX JSON/XML files can be ingested by any tool that supports the CycloneDX schema (v1.6+), including:

- [OWASP Dependency-Track](https://dependencytrack.org/)
- [Grype](https://github.com/anchore/grype)
- [Trivy](https://trivy.dev/)
- [cdxgen](https://github.com/CycloneDX/cdxgen)
- Any tool that understands the [CycloneDX specification](https://cyclonedx.org/specification/overview/)

## Security Best Practices

1. **Keep Updated**: Regularly update dependencies and review security advisories
2. **Review Changes**: Review dependency update PRs before merging
3. **Enable Security Features**: Enable CodeQL, secret scanning, and Dependabot in your repositories
4. **Use Locked Dependencies**: Always commit `uv.lock` for reproducible builds
5. **Configure Branch Protection**: Require PR reviews and status checks

## Acknowledgments

We thank the security researchers and community members who help keep this project secure.
