# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.1] - 2026-06-30

### Added
- GitHub Actions CI workflow (`.github/workflows/ci.yml`)
- pytest configuration (`pytest.ini`)
- 24 unit tests covering:
  - DID Manager (soul anchor, format validation)
  - Conflict resolver (LWW strategy)
  - Scene adapter (three scene presets, transition logic)
  - Storage abstraction (NAS paths, file locks, vector clocks)
- Encrypted private key storage (Fernet + PBKDF2) in DID Manager

### Changed
- CI workflow simplified to core test + lint checks
- pytest runs in parallel across Python 3.10/3.11/3.12

## [0.1.0] - 2026-06-30

### Added
- Initial MVP release
- `did/manager.py` - DID generation and management
- `sync/engine.py` - Memory sync engine with vector clocks
- `resolve/conflict.py` - LWW conflict resolution
- `scene/adapter.py` - Scene-based behavior adaptation
- `storage/nas_storage.py` - NAS storage abstraction
- `cli/main.py` - Command-line interface
- Documentation (README.md, architecture.md)
- `setup.py` and `requirements.txt`
