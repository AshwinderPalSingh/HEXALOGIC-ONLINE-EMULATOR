# Independent Validation Check

## Purpose

This directory contains the validation infrastructure for comparing HexaLogic's
machine-cycle counts against an **independent oracle** (Keil µVision or physical
AT89C51 hardware measurements).

## Why This Exists

The original paper's Tables V and VI reported 0.000% error on all rows. As
acknowledged in the paper itself (Section XI-B): *"This zero-error result is
expected for an interpretive ISS where cycle costs are assigned per the MCS-51
specification."* The "expected" values were derived from the same Intel MCS-51
specification used to implement the simulator's cycle cost tables — the
validation was checking the code against itself.

This directory replaces that self-referential approach with infrastructure for
genuine independent validation.

## Current Status

| Column | Status |
|--------|--------|
| HexaLogic measurements | ✅ Recorded by `run_comparison.py` |
| Keil µVision traces (these 4 fixtures) | ❌ `[PENDING_KEIL_DATA]` — see note below |
| Physical hardware traces | ❌ `[PENDING_KEIL_DATA]` — requires AT89C51 dev board |

**A real Keil µVision 5 / AT89C51 comparison now exists** — see Table V in
`docs/hexlogic_paper_ieee.tex` (and the condensed version in
`hexlogic_paper_softwarex.tex`). That comparison uses nine smaller,
single-instruction/single-event programs (MUL/DIV cost, CJNE carry
semantics, interrupt latency, one LED-rotate iteration, one UART frame,
etc.), not the four broader fixtures in this directory (full 8-step LED
rotation, timer overflow including setup, a 2-byte UART transmission,
edge-to-first-full-instruction interrupt latency). The two measurement sets
answer related but distinct questions, so the numbers here are intentionally
left as `[PENDING_KEIL_DATA]` rather than back-filled with the paper's
numbers, which were measured against different programs. Table V's
comparison is real: it agreed to within 0.104% across all nine rows, and
it directly caught a genuine defect — the serial-port model only computed
a real UART frame duration when Timer 2 drove the baud clock, silently
returning a 1-cycle frame for the far more common Timer-1 case. That is now
fixed in `sim8051/cpu.py`, and this directory's own `uart_tx_9600.asm`
result reflects the corrected timing (1930 cycles for two bytes, not the
previous incorrect 12).

## Directory Structure

```
independent_check/
├── README.md                    ← This file
├── run_comparison.py            ← Runs test programs, records HexaLogic measurements
├── smell_check.py               ← Flags suspiciously perfect (all 0.000%) results
├── results.csv                  ← Output: HexaLogic + [PENDING_KEIL_DATA]
├── results.json                 ← Same data in JSON
├── test_programs/               ← Assembly source for each test case
│   ├── led_rotate.asm
│   ├── timer0_overflow.asm
│   ├── uart_tx_9600.asm
│   └── interrupt_entry.asm
└── keil_traces/                 ← Import real Keil/hardware traces here
    └── README.md                ← Capture protocol
```

## Usage

```bash
# Record HexaLogic measurements
python3 validation/independent_check/run_comparison.py

# Run methodology smell check
python3 validation/independent_check/smell_check.py
```

## Honest Disclosure

Until real Keil or hardware traces are imported, all comparisons are labeled
`[PENDING_KEIL_DATA]`. The paper must state this honestly — no synthetic data
is fabricated to fill these columns.
