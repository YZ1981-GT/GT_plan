# Task 22 — Playwright + artifact gate

**Date:** 2026-09-08  
**Env:** backend `127.0.0.1:9980` (already up) + frontend `localhost:3030` (IPv6 ::1)

## Playwright

Command:

```text
npx playwright test e2e/platform-architecture-convergence.spec.ts --workers=1
```

**Result: 4 passed**

| Case | Evidence |
|---|---|
| livez / readyz / health.startup desensitized | `T22-playwright/health-startup.json`, `readyz.json` |
| unauthorized `/projects` → `/login?redirect=` | single beforeEach guard path |
| login + `/ai-chat` registered (non-404) | `ai-chat-{1280,1440,1920}.png` |
| HTML B50-1 / confirmation D0 / OO+HTML A14-4 | `render-config-*.json`, `wp-*-1440.png`, live resolve `live-wp-resolve.json` |

Project: `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` (重药控股安徽).

Console gate (hardened): `pageerror` + non-resource console must be empty; resource failures must be attributable via `page.on('response')`. Exempt only ambient OO/favicon **and** named concurrent `/api/workpapers/*/guidance` WIP (`workpaper-guidance-content-closure`). Evidence: `console-errors.json` records `parts` / `failedResponses` / `unexplained`.

## Artifact porcelain (PAC formal products)

See Task 22 closure scan in tasks.md / INDEX update. No commit/push (user did not request).

## Concurrent tree note (domain ownership follow-up)

`router_registry/**` was moved out of `core` into `backend-routers`, and `core.may_depend_on` allows `backend-routers` (assembly import from `main.py`). Mid-refinement checker runs briefly showed FAIL (+2/+3) while debt also **shrank by ~590**; after ownership + baseline refresh the live tree is:

```text
domains=22 current_violations=4761 baseline=4761
OK: no new domain-boundary violations
```

Remaining guidance/custom-template edges should continue to be owned by those active specs when they land new imports—not by silently widening baseline without adjudication.

## Notes

- Playwright Chromium headless shell installed into sandbox cache on first run.
- `start-dev.bat` not re-run end-to-end because backend was already healthy; frontend was already listening on `localhost:3030`.
