---
trigger: always_on
---

# Project Rules & Guidelines

## 1. Environment & Architecture Constraints
- **Hosting:** Render.com Free Tier (Web Service).
- **Database:** Render.com Free Tier PostgreSQL 18.
- **Resource Optimization:** Keep background processes lightweight and strictly manage connection pooling to avoid free-tier memory and connection exhaustion.

## 2. Testing Discipline
- **No Python Tests by Default:** Do NOT write, execute, or trigger Python test suites automatically.
- **Exception:** Execute tests ONLY when an explicit bug/issue is reported or when explicitly instructed in the prompt.

## 3. Versioning Protocol (Beta Phase: `0.x.x`)
- **Beta Version Format:** All releases must use the `0.x.x` versioning scheme while the project remains in Beta.
  - **Patch Increment (`0.x.Y`):** Bump for bug fixes, performance tweaks, or minor refactoring (e.g., `0.1.0` ➔ `0.1.1`).
  - **Minor Increment (`0.X.0`):** Bump for new user-facing features, schema additions, or breaking changes (e.g., `0.1.3` ➔ `0.2.0`).
- **About Route (`/about`):** Display the current version (`0.x.x`) dynamically or statically on the `/about` route/view.
- **Changelog Maintenance:** Maintain `CHANGELOG.md` at the project root.
  - Append every new version tag with its release details.
  - Explanations in `CHANGELOG.md` **MUST be written in Persian (Farsi)**.

## 4. Git & Commit Discipline
- **Auto-Commit:** ALWAYS execute a Git commit immediately after making requested updates or finishing a task.
- **Commit Message Standard:** Include the new version tag directly in the commit message (e.g., `feat(api): add dynamic stats endpoint [v0.2.0]` or `fix(db): optimize connection pool [v0.1.2]`).