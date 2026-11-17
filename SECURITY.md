# Security Policy

## Supported versions

Security reports are accepted for the current default branch. Older commits and forks are not maintained by this repository, and backports to older versions are not guaranteed.

## Reporting a vulnerability

Please do not report security vulnerabilities in public issues, discussions, or pull requests.

1. Visit the repository's [Security advisories page](https://github.com/Evansbizzy/Manga-Vault/security/advisories) and use **Report a vulnerability** if private vulnerability reporting is enabled.
2. If private reporting is unavailable, open a public issue containing only a request for a private reporting contact. Do not include exploit details, affected user data, credentials, or proof-of-concept code in that issue. The maintainers will respond with a private channel.

Include a concise description, affected commit or version, impact, reproduction steps, and any suggested mitigation in the private report. Avoid accessing, changing, or retaining data that does not belong to you while investigating.

## What to report

Examples include authentication or authorization bypasses, cross-account access to libraries or downloads, remote code execution, SQL injection, server-side request forgery, unsafe file handling, exposure of credentials or private data, and security-relevant dependency or deployment mistakes that affect MangaVault.

Reports about vulnerabilities in upstream manga sources or other third-party services should be sent to their maintainers. If the issue also creates a security impact in MangaVault, describe that impact in a separate private report here.

## Response and disclosure

The maintainers aim to acknowledge a report within five business days and provide status updates about every two weeks while investigating. These are best-effort targets, not a guaranteed service-level agreement. Fix timing depends on severity, reproducibility, and maintainer availability.

Please allow time to investigate and prepare a fix before public disclosure. We will coordinate a disclosure date with the reporter when possible. If a report is out of scope or cannot be reproduced, we will explain that in the response when possible.

## Safe testing

Only test systems and accounts you own or have explicit permission to assess. Do not perform denial-of-service testing, social engineering, credential theft, or actions that disrupt MangaVault users or upstream providers.
