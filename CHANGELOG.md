# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Architecture cleanup to reduce cross-feature blast radius:
  - Canonicalized pure shared helpers to `src/shared/*`.
  - Canonicalized service entrypoint to `src/services` package exports.
  - Updated cogs/UI/tests to use canonical imports directly.

### Removed
- Backward-compatibility shims were intentionally removed:
  - `src/core/builders.py`
  - `src/core/validators.py`
  - `src/core/permissions.py`
  - `src/services/db_service.py`

### Breaking Changes
- Imports from `src.core.*` no longer work. Use `src.shared.*`.
- Imports from `src.services.db_service` no longer work. Use `src.services` or concrete `*_service` modules.

### Migration
- Replace:
  - `from src.core import builders|validators|permissions`
  - with `from src.shared import builders|validators|permissions`
- Replace:
  - `from src.services import db_service`
  - with direct imports from `src.services` package exports.

## [0.1.4] - 2026-05-09

### Added
- ChatRole feature: grant a role automatically when a member posts a cumulative N times in a designated channel.
  - New `ChatRoleConfig` (guild_id, channel_id, role_id, threshold, optional duration_hours) and `ChatRoleProgress` (count + granted state) models.
  - `chatrole` cog: counts posts via `on_message`, grants role on threshold, removes role after `duration_hours` via per-minute background task; resets count on expiry so the role can be re-earned.
  - Posts authored before `config.created_at` are not counted.
  - Web admin (FastAPI HTML + JSON API at `/api/v1/chatrole`) and Next.js dashboard page.
  - Atomic `granted=False → True` claim via SQL UPDATE so multi-instance deployments avoid double-grants.
- Auto-reaction feature: automatically attach configured emoji reactions to messages in target channels.
- Gateway watchdog: exit the process when the gateway is silent for 10 minutes so the supervisor can restart a hung bot.
- AutoMod role exemption: allow specific roles to bypass AutoMod rules, with admin UI support.
- `/health` status endpoint enrichment for clearer startup diagnostics.

### Fixed
- Hardened startup against Discord 429 responses by capping gateway reconnect backoff at ~128s.
- Stopped redundant `change_presence` calls on every heartbeat.
- Voice channel kick bypass closed for `user_limit`; restrictions are now applied retroactively.
- Railway: use the frontend `Dockerfile` for the frontend service so deploys pick up the correct image.

### Performance
- Sped up lobby VC creation path.

### Chore
- CI/test cleanup after VC feature removal; lint fixes; cspell dictionary updates.

## [0.1.3] - 2026-03-31

### Added
- Role panel excluded roles: panel-level setting to block users with specific roles from acquiring roles.
  - New `excluded_role_ids` field on `RolePanel` model + migration.
  - Enforcement in both button and reaction handlers.
  - API create/update/copy support + frontend UI (detail & new pages).
- Voice channel dissolve button: owner can disband the channel with a 10-second countdown.
  - Countdown message with cancel button in channel chat.
  - Deletes DB session before channel to prevent race conditions with auto-cleanup.

### Fixed
- Fixed dissolve/auto-cleanup race condition: DB record is now deleted before channel deletion so `_handle_channel_leave` and `on_guild_channel_delete` skip already-cleaned sessions.

## [0.1.2] - 2026-03-28

### Added
- Added logout action in dashboard sidebar.
- Added redirect-back flow after re-login (`/login?redirect=...`).

### Fixed
- Fixed dashboard maintenance page crash by aligning frontend schema with API response.
- Updated tests to match ticket log URL path (`/dashboard/tickets/{id}`).
- Wrapped login page `useSearchParams()` in `Suspense` boundary to fix Next.js build error.
- Isolated config tests from local `.env` extra keys by passing `_env_file=None`.

### Docs
- Expanded `.env.example` with complete environment variable template.

### Test
- Stabilized test collection against local `.env` extra keys via test-side config initialization.

## [0.1.1] - 2026-03-28

### Fixed
- Ticket close-log URL now points to `/dashboard/tickets/{id}`.
- Ticket close-log URL base is now configurable via `FRONTEND_URL` (fallback to `APP_URL`).

### Docs
- Added `APP_URL` and `FRONTEND_URL` examples to `.env.example`.
- Documented `APP_URL` and `FRONTEND_URL` in setup guide.
