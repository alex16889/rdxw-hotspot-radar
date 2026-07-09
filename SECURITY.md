# Security Policy

## Supported Versions

The public repository currently supports the latest `main` branch.

## Reporting A Vulnerability

Please open a private security advisory on GitHub if available, or contact the
maintainer through the repository profile.

Do not publish working exploits, secrets, private tokens, or private deployment
details in public issues.

## Secret Handling

This project should never commit:

- `.env` files
- API keys or bot tokens
- cookies or session tokens
- SSH keys or certificates
- generated logs containing private feedback

Run `python3 scripts/open_source_audit.py` before publishing or submitting a PR.
