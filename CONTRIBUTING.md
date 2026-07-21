# Contributing to HexaLogic

Thank you for your interest in contributing to HexaLogic! This document provides
guidelines for contributing to the project.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend build)
- Git

### Local Setup

```bash
git clone https://github.com/AshwinderPalSingh/HEXALOGIC-ONLINE-EMULATOR.git
cd HEXALOGIC-ONLINE-EMULATOR
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Run tests
python3 -m pytest tests/ -v

# Run the dev server
python3 scripts/run_local_flask.py
```

### Running the Full Test Suite

```bash
# Core pytest tests (154 tests)
python3 -m pytest tests/ -v

# Standalone feature tests (54 tests)
python3 test_new_features.py

# Regression audit (10 checks)
python3 scripts/regression_audit.py

# Validation harness
python3 validation/independent_check/run_comparison.py
python3 validation/independent_check/smell_check.py
```

218 automated checks total (154 pytest + 10 regression audit + 54 standalone).

## How to Contribute

### Reporting Bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) to file issues.
Include:
- Steps to reproduce
- Expected vs actual behavior
- Browser and OS version
- Assembly program that triggers the bug (if applicable)

### Suggesting Features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

### Submitting Code

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make your changes
4. Run the full test suite (see above)
5. Submit a pull request

### Code Style

- Python: follow PEP 8, use type hints
- JavaScript: use modern ES6+ syntax
- Assembly test programs: include comments explaining expected behavior

### Adding Tests

- **8051/ARM core tests**: add to `tests/test_sim8051_core.py` (both architectures
  run through the same session/CPU-factory layer, so cases are shared)
- **Instruction-set/opcode-table tests**: add to `tests/test_instruction_set.py`
- **API tests**: add to `tests/test_sandbox_api.py`
- **Hardware tests**: add to `tests/test_virtual_hardware.py`
- **Protocol/UART tests**: add to `test_new_features.py`

### Validation

If you change cycle costs, timer logic, or serial timing:
1. Run `validation/independent_check/run_comparison.py`
2. Run `validation/independent_check/smell_check.py`
3. Document any changes to expected cycle counts

## Architecture Overview

See the paper at `docs/hexlogic_paper_ieee.tex` and `docs/sim8051_redesign.md`
for architectural documentation.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License (see [LICENSE](LICENSE)).
