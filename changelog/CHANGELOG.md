# Changelog [中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.0.13] - 2026-08-07

### Added
- Added a unified `ctx.cloud` resource facade for application databases, object storage, and common function calls.
- Added runtime log streaming, function exception capture, and real-time console log rendering.
- Added database collection index management and complete storage/database operation interfaces.
- Added a production GitHub Actions release pipeline that builds and pushes `linux/amd64` and `linux/arm64` images and runs a real Chrome smoke test before release.

### Fixed
- Fixed editor drafts, layout persistence, Python formatting, and Monaco localization asset loading.
- Fixed application runtime lifecycle, task recovery, container observation, and deletion retry reliability.
- Fixed local HTTPS development login, database index listing, and LSP dependency health checks.
- Fixed the release gate misclassifying annotated tags after GitHub Actions checks out a tag.
- Fixed production smoke tests creating anonymous Playwright pages from an owner context.
- Fixed production web image releases depending on an unstable npm mirror.
- Hardened user sessions, function authorization, runtime credential isolation, dynamic CORS, and object-storage permission boundaries.

### Refactored
- Migrated the server database driver from Motor to PyMongo Async and added Beanie 2 compatibility.
- Refactored the function executor, task worker, runtime control plane, and application storage management.
- Completed the Pydantic V2 settings migration and unified frozen Python dependency sources for production images.
- Refactored cloud resource, database, function, log, and application page interactions and layouts.

### Documentation
- Added bilingual documentation sites, deployment and development guides, and user documentation.
- Expanded production deployment, version release, Docker Hub, and LSP sidecar image reuse guidance.

## [v0.0.12] - 2026-05-10

### Added
- Added RustFS-compatible S3 storage support and related context handling.
- Added a sidecar-based runtime LSP pipeline with Pyright-backed editor intelligence.
- Added Monaco Editor support for the cloud function editor and LSP smoke test helpers.

### Fixed
- Fixed frontend and runtime LSP initialization, formatting, and fallback behavior.
- Fixed database page refresh/delete/edit responses and improved S3 error handling.
- Fixed password hashing security and several frontend field issues.

### Refactored
- Replaced MinIO integration with RustFS-compatible storage across server and app modules.
- Refactored frontend function editing and application pages, including login/home/apps UI refreshes.

### Chore
- Synced changelog history from `dev-0.0.8` through `dev-0.0.11`.
- Cleaned lint issues, updated ignore rules, and aligned related project configuration.

## [dev-0.0.11] - 2025-08-12

### Added
- Add faas function templates.
- Add S3 context.

### Fixed
- Delete webhook notification input payload.
- Improve notification module.

### Chore
- Context modify as ctx.

## [dev-0.0.10] - 2025-08-06

### Added
- Support for background tasks.

### Fixed
- WebSocket connection for logs.
- App runtime dependencies installer.
- Function code editor space resizable issue.
- Issue where multiple files cannot be deleted.
- Improved database collection statistics handling.

### Performance
- Restart app container after installing/uninstalling dependencies.
- Set starting status after inserting a restart task.

### Docs
- Updated README and features documentation.

## [dev-0.0.9] - 2025-08-03
- Modify the dynamic startup tag for the app runtime
- Improve the web app homepage

## [dev-0.0.8] - 2025-08-02
- Move the dynamic app runtime container under the main project
- Refactor the web application overview content
- Refactor the dynamic injection of functions in the application environment

## [dev-0.0.7] - 2025-08-01
- Added [Scheduled Task] feature for functions
- Fixed a bug where the app runtime was initialized multiple times in the startup logic
- Optimized the display effect of the web homepage

## [dev-0.0.6] - 2025-07-30
- Fixed the issue where function logs could not be displayed in development mode.
- Refactored the web-side code editor, replacing monaco with codemirror.
- Refactored the server-side LSP: removed the separate LSP service and integrated LSP into the corresponding app runtime.

## [dev-0.0.5] - 2025-07-26
- Fixed the configuration of the LSP service.
- Added the online update view section on the web side (update function is temporarily unavailable).
- Optimized the display effect of the verification code on the login page.
- Added personal information editing function on the web page (modify username, password).
- Added AI agent in the AI assistant function.
- Added basic request limiting functionality.
- Added a preview mode, where users cannot modify their account and password.

## [dev-0.0.4] - 2025-07-25

### Added
- Basic web python lsp service (known bugs: no highlighting on first load, and no context suggestions, etc.)

### Fixed
- Package dependencies for the lsp service.

### Refactored
- Removed pyright-based lsp files.
- Removed some useless console function editors.

## [dev-0.0.3] - 2025-07-23

### Added
- Support for multiple file deletion.

### Fixed
- Dependency package display issue.
- Logic related to environment variables in the container.
- Webpage logic for deleting application containers.
- Log query logic.
- Web function test panel.

### Refactored
- File preview and page layout.
- Added FastAPI token expired exception handling.
- Dependencies manager and web dependencies list info.

### Chore
- Added build script.
