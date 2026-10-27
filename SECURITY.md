# Security Policy

## Supported Versions

| Version | Supported | Notes |
| --- | --- | --- |
| 0.4.x | Yes | Current supported release line |
| 0.3.x | Limited | Critical security fixes only |
| < 0.3 | No | Unsupported; please upgrade |

## Reporting Security Issues

**Do not open public GitHub issues for security vulnerabilities.**

Report suspected vulnerabilities privately to **security@steadfast.dev**. Include as much of the following as you can:

- Description of the vulnerability and affected versions
- Steps to reproduce, including a minimal proof of concept where safe
- Potential impact and severity assessment
- Suggested fix, if available
- Your name and a contact method (optional)

Please do not include real credentials, private keys, or sensitive repository data in the report.

### Response expectations

We aim to:
1. Acknowledge reports within 24 hours.
2. Triage the report and, where feasible, provide an initial assessment within 7 days.
3. Coordinate remediation and a patched release based on severity and complexity.
4. Publish a security advisory and coordinate disclosure when appropriate.

These are response goals, not guaranteed remediation or release deadlines. We will coordinate disclosure with the reporter.

You can also use [GitHub Security Advisories](https://github.com/rllibo833-sudo/Steadfast/security/advisories) if private vulnerability reporting is enabled for the repository.

## Security Best Practices

### For Steadfast users

1. **Keep Python and Steadfast updated.** Use a supported Python release (Python 3.10 or later is required by the current package) and install updates from a trusted source:
   `python -m pip install --upgrade steadfast-governance`
2. **Local-first does not mean risk-free.** Steadfast is designed to run locally and does not require a Steadfast-hosted service. Review configured integrations and pipeline commands before running them; tools and dependencies may make their own network requests.
3. **Restrict access.** Limit access to the repository and its `.steadfast/` governance files to trusted users. Treat policy, work-order, and evidence files as potentially sensitive.
4. **Protect integrity records.** If using the session ledger, protect its files and signing secret. HMAC integrity checks can detect certain changes but do not provide non-repudiation or protect against an attacker who can access the signing key.
5. **Review agent integrations.** Only configure agents you trust. Inspect generated `.agents/` files and other repository-local instructions before allowing an agent to act on them.
6. **Handle evidence carefully.** Verify evidence bundles before sharing them. Bundles may reveal repository structure, paths, or other confidential metadata.

### For Steadfast developers

1. **Secure implementation.** Use type hints where practical, avoid unsafe dynamic execution, prefer `subprocess.run(..., shell=False)`, and validate untrusted input before filesystem operations.
2. **Secret handling.** Generate tokens with Python's `secrets` module. Never commit credentials or real secrets, including in tests; use environment variables or an appropriate secret store.
3. **Dependencies.** Keep direct and transitive dependencies updated, review security advisories, and run dependency vulnerability checks such as `pip-audit`.
4. **Security regression tests.** Add tests for discovered vulnerabilities, secret scanning, workflow trust boundaries, and relevant edge cases. Use synthetic test secrets only.

## Known Limitations

- **Pattern-based detection:** Security checks may rely on patterns and heuristics rather than semantic analysis. False positives and false negatives are possible; review findings manually.
- **Heuristic impact analysis:** Change-impact results are guidance, not definitive proof that every affected component has been identified.
- **Dashboard exposure:** Do not expose a local dashboard to untrusted networks. Verify its bind address, authentication, and origin checks for your deployment.
- **Ledger integrity:** HMAC-based integrity checks are not digital signatures and do not provide non-repudiation. Their guarantees depend on protecting the signing key and filesystem.
- **Not a sandbox:** Steadfast governance checks do not isolate untrusted code or guarantee that an agent, configured command, or dependency is safe.

## Incident Response

For confirmed or suspected incidents, maintainers should:

1. **Triage:** Assess severity, affected versions, exploitability, and potential impact.
2. **Reproduce and remediate:** Create a regression test, implement a fix, and verify the relevant tests and checks.
3. **Review:** Request independent review when practical, especially for high-impact changes.
4. **Release:** Publish a patched release and update the changelog and release notes as appropriate.
5. **Communicate:** Notify the reporter and publish a GitHub Security Advisory when appropriate, coordinating disclosure timing.

## Security Research

- Report vulnerabilities privately before public disclosure.
- Test only repositories and systems you own or have explicit permission to assess.
- Do not attempt to access data or bypass controls outside the authorized scope.
- Coordinate publication with maintainers; after remediation, researchers may publish findings and link to the relevant advisory.

## Compliance and References

Steadfast uses these references as guidance; this does not imply formal certification or compliance:

- [Python PEP 440](https://peps.python.org/pep-0440/) for version-specifier conventions
- [SLSA framework](https://slsa.dev/) for software supply-chain security concepts
- [OWASP Top 10](https://owasp.org/Top10/) for application-security risk categories
- [pip-audit](https://pypi.org/project/pip-audit/) for Python dependency vulnerability auditing

## Security Contacts

- **Security email:** security@steadfast.dev
- **GitHub Security Advisories:** [Report a vulnerability](https://github.com/rllibo833-sudo/Steadfast/security/advisories)
- **PGP key:** Not currently published in this policy; request details through the security contact if needed.

---

**Last reviewed:** October 27, 2026  
**Maintained by:** Steadfast contributors
