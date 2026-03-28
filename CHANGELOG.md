# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-03-28

### Fixed
- Ticket close-log URL now points to `/dashboard/tickets/{id}`.
- Ticket close-log URL base is now configurable via `FRONTEND_URL` (fallback to `APP_URL`).

### Docs
- Added `APP_URL` and `FRONTEND_URL` examples to `.env.example`.
- Documented `APP_URL` and `FRONTEND_URL` in setup guide.
