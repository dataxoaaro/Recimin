# Security policy

## Reporting

Use GitHub's private vulnerability reporting: **Security → Report a
vulnerability** on this repository. Please do not open a public issue for
anything exploitable. You can expect an acknowledgement within a few days;
this is a one-person household project, not a security team.

## Scope, honestly stated

The threat model is documented in the README's *Security model* section.
Things that look like findings but are decisions:

- **Every authenticated user can read, edit and delete every recipe.** One
  household, one shared library — there is no per-recipe ownership on purpose.
- **Sessions are stateless 30-day JWTs**; logout clears the cookie rather
  than revoking it server-side. Device tokens, by contrast, are individually
  revocable.
- **The worker updates yt-dlp at runtime** (`pip install --pre` on an
  extractor-breakage signal). That is a deliberate supply-chain exposure,
  accepted because a stale extractor breaks the product weekly. It runs in
  the worker container, which holds no secret beyond the OpenRouter key.

Reports about those are welcome as discussions, not vulnerabilities.

Very much in scope: authentication bypasses, injection of any kind, path
traversal, SSRF that defeats the private-address guard in
`src/recimin/importer/web.py`, and anything an *unauthenticated* caller can
do that they should not be able to.
