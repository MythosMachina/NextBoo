# Security Policy

## Scope

NextBoo is a self-hosted image index with:

- invite-only account creation
- privileged admin and moderation workflows
- authenticated uploads
- worker-based media processing
- automatic tagging and rating
- potentially sensitive or explicit media under access controls

Security reports are in scope when they affect confidentiality, integrity, availability, or access control in the shipped application.

Examples:

- authentication or session bypass
- refresh token or JWT handling flaws
- invite redemption abuse
- privilege escalation into moderator or admin capabilities
- authorization flaws on posts, moderation, users, or account settings
- upload pipeline abuse, path traversal, unsafe file handling, or worker escapes
- exposure of hidden, restricted, or explicit media to unauthorized viewers
- data leaks from API responses, storage paths, or background jobs
- denial-of-service paths that can realistically degrade the service

Out of scope:

- general model-quality complaints
- tagging accuracy disagreements
- UI-only issues without security impact
- problems caused solely by unsafe operator configuration after deployment

## Reporting

Do not open public GitHub issues for security vulnerabilities.

Report privately to the project maintainer and include:

- affected version or commit
- deployment context if relevant
- exact reproduction steps
- impact
- logs, screenshots, or request samples when useful

If the issue involves explicit or otherwise sensitive media, do not publish sample content publicly. Describe the case privately and minimally.

## Expected Handling

The project aims to:

- acknowledge legitimate reports promptly
- reproduce and validate impact
- prepare a fix or mitigation
- avoid public disclosure before a fix is available

## Operator Notes

For self-hosted deployments:

- keep `.env` private
- rotate `JWT_SECRET` for real deployments
- do not expose bootstrap or rescue workflows publicly
- run bootstrap and rescue scripts only on the host that controls Docker
- treat uploaded media, database backups, and logs as sensitive operational data
