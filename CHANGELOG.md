# Changelog

All notable changes to this project will be documented in this file.

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
