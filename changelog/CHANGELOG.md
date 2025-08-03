# Changelog [中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
