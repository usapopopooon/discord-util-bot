# Changelog

All notable changes to this project will be documented in this file.

## [0.1.2] - 2026-03-28

### Added
- Added logout action in dashboard sidebar.
- Added redirect-back flow after re-login (`/login?redirect=...`).

### Fixed
- Fixed dashboard maintenance page crash by aligning frontend schema with API response.
- Updated tests to match ticket log URL path (`/dashboard/tickets/{id}`).

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
