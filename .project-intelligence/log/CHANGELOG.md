# Changelog

## 2026-08-31 — NK architecture completion verification
- Changed: hardened generated Cookiecutter branches, identity/CSRF/account-status enforcement, tenant membership wiring, agent action execution, collision-safe state keys, and Helm runtime defaults.
- Verified: five profile generations, focused generator contracts, Ruff, mypy, generated SaaS/agentic compilation, and Helm lint/template rendering.
- Caveat: Docker-backed cleanup/failure drills remain pending while the local Docker daemon is unresponsive.

## 2026-08-31 — Global NK generator CLI
- Changed: `pyproject.toml`, `uv.lock`, generator CLI, README/wiki, and CLI tests.
- Summary: Added globally installable `nk` and `fastapi-template` commands with Next.js-style `nk init NAME` handling while retaining legacy aliases.
- Next: Publish the package and verify `uv tool install` from the published artifact.

## 2026-08-27 — SCIM 2.0 stack
- Canonical core/scim* + services/api + SqlalchemyScimRepository; identity/providers/scim* removed; tests/test_scim.py 11 passed.
