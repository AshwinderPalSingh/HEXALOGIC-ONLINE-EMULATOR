# Changelog

All notable changes to HexaLogic are documented in this file.

## [Unreleased] — Research Upgrade

### Added
- `/validation/independent_check/` — validation harness with test programs,
  comparison runner, and methodology smell check
- `/validation/competitor_runs/` — placeholder for hands-on competitor comparison
- `CONTRIBUTING.md` — contribution guidelines
- `CHANGELOG.md` — this file
- `.github/ISSUE_TEMPLATE/bug_report.md` — bug report template
- `.github/ISSUE_TEMPLATE/feature_request.md` — feature request template

### Fixed
- Removed ~107 duplicate files (macOS "filename 2.ext" copies)
- Paper Table IV test count corrected from 256 to 214

### Changed
- Validation methodology documented honestly: self-referential timing tables
  replaced with `[PENDING_KEIL_DATA]` placeholders pending independent oracle

## [1.0.0] — 2026-06-05

### Added
- Multi-architecture support (8051 + ARM educational sandbox)
- Time-travel debugging via reverse-delta state capture
- Virtual hardware simulation (LEDs, 7-seg, switches, stepper motor)
- Hardware fault injection (stuck-high, stuck-low, delay, noise)
- Automated UART protocol analyzer (all 4 serial modes)
- Multi-node virtual UART network (session bridging)
- Session import/export
- 150 pytest tests, 54 standalone feature tests, 10 regression audit checks
- Browser-based UI with Monaco editor, dark mode, waveform view
- IEEE-format paper: `docs/hexlogic_paper_ieee.tex`
