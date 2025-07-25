# Changelog [中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
