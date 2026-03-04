# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by opening a GitHub issue. For sensitive issues (e.g., credential exposure), please contact the maintainer directly rather than posting publicly.

## Security Considerations

- **API keys**: Store in `.env` files (gitignored) or GitHub Secrets — never commit credentials
- **Profile data**: `profile.json` may contain personal information — it is gitignored by default
- **Docker**: The dashboard server binds to `0.0.0.0` inside the container; use Docker port mapping to control access
- **Ollama**: Communicates over HTTP on localhost — do not expose to untrusted networks
