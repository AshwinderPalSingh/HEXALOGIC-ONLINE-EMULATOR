"""run_comparison.py — Run validation test programs through HexaLogic and record results.

This script:
1. Assembles each test program using the HexaLogic assembler
2. Runs each program on the HexaLogic CPU simulator
3. Records the machine-cycle counts and key state values
4. Outputs results.csv with HexaLogic measurements + [PENDING_KEIL_DATA] placeholders

IMPORTANT: This does NOT fabricate an independent oracle. The "expected" column
contains [PENDING_KEIL_DATA] placeholders that must be filled with real Keil µVision
or physical AT89C51 measurements. See keil_traces/README.md for the capture protocol.

Usage:
    cd <repo-root>
    python3 validation/independent_check/run_comparison.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

# Add repo root to path so we can import sim8051
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sim8051 import Assembler8051, CPU8051

PROGRAMS_DIR = Path(__file__).resolve().parent / "test_programs"
OUTPUT_DIR = Path(__file__).resolve().parent


@dataclass
class TestResult:
    program: str
    description: str
    hexalogic_cycles: int
    hexalogic_detail: str
    keil_cycles: str  # "[PENDING_KEIL_DATA]" until real data supplied
    error_pct: str    # "[PENDING_KEIL_DATA]" until real data supplied
    methodology_note: str


def run_led_rotate() -> TestResult:
    """Run LED rotate and measure cycles for first full 8-step rotation."""
    src = (PROGRAMS_DIR / "led_rotate.asm").read_text()
    asm = Assembler8051(code_size=0x10000)
    prog = asm.assemble(src)
    cpu = CPU8051(code_size=0x10000)
    cpu.load_program(prog)
    cpu.set_clock_hz(12_000_000)

    # Run until P1 has cycled through 8 rotations back to 0x01
    # Initial: A=0x01, after 8 RL operations: A=0x01 again
    # Each rotation step = ACALL DELAY + RL A + MOV P1,A + SJMP ROTATE
    # We need to detect when A returns to 0x01 after going through
    # 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x01

    start_cycles = cpu.cycles
    rotation_count = 0
    prev_a = 0

    for _ in range(500_000):  # generous upper bound
        cpu.step_into()
        current_a = cpu.memory.read_direct(0xE0)  # ACC
        if prev_a != current_a:
            if current_a == 0x01 and prev_a == 0x80:
                # Completed one full rotation
                rotation_count += 1
                if rotation_count == 1:
                    break
            prev_a = current_a

    total = cpu.cycles - start_cycles
    return TestResult(
        program="led_rotate.asm",
        description="LED rotate — cycles for 1st full 8-step rotation period",
        hexalogic_cycles=total,
        hexalogic_detail=f"{total} machine cycles at 12 MHz = {total * 1e-6:.6f} s",
        keil_cycles="[PENDING_KEIL_DATA]",
        error_pct="[PENDING_KEIL_DATA]",
        methodology_note="HexaLogic measurement only. Keil/hardware comparison pending.",
    )


def run_timer0_overflow() -> TestResult:
    """Run Timer 0 Mode 1 from 0x0000, measure cycles until TF0 set."""
    src = (PROGRAMS_DIR / "timer0_overflow.asm").read_text()
    asm = Assembler8051(code_size=0x10000)
    prog = asm.assemble(src)
    cpu = CPU8051(code_size=0x10000)
    cpu.load_program(prog)
    cpu.set_clock_hz(12_000_000)

    start_cycles = cpu.cycles
    tf0_set = False

    for _ in range(200_000):
        cpu.step_into()
        tcon = cpu.memory.read_direct(0x88)
        if tcon & 0x20:  # TF0 bit
            tf0_set = True
            break

    total = cpu.cycles - start_cycles
    return TestResult(
        program="timer0_overflow.asm",
        description="Timer 0 Mode 1 — cycles from start until TF0 overflow",
        hexalogic_cycles=total,
        hexalogic_detail=f"TF0 {'set' if tf0_set else 'NOT set'} after {total} cycles",
        keil_cycles="[PENDING_KEIL_DATA]",
        error_pct="[PENDING_KEIL_DATA]",
        methodology_note="HexaLogic measurement only. Keil/hardware comparison pending.",
    )


def run_uart_tx() -> TestResult:
    """Run UART TX at 9600 baud, count cycles for two byte transmissions."""
    src = (PROGRAMS_DIR / "uart_tx_9600.asm").read_text()
    asm = Assembler8051(code_size=0x10000)
    prog = asm.assemble(src)
    cpu = CPU8051(code_size=0x10000)
    cpu.load_program(prog)
    cpu.set_clock_hz(11_059_200)  # Standard 8051 crystal for exact baud rates

    start_cycles = cpu.cycles

    # Counting "TI observed set" polling snapshots is fragile: TI can read as
    # set across more than one step_into() call (once when the frame
    # completes, again on the next poll before CLR TI executes), so a
    # >=2 threshold can be satisfied by the *first* byte alone. The TX log
    # itself is the unambiguous ground truth for "how many bytes have
    # actually completed transmission".
    for _ in range(500_000):
        cpu.step_into()
        if len(cpu.serial.tx_log) >= 2:
            break
        if cpu.halted:
            break

    total = cpu.cycles - start_cycles
    tx_log = getattr(cpu, 'serial', None)
    tx_bytes = []
    if tx_log and hasattr(tx_log, 'tx_log'):
        tx_bytes = list(tx_log.tx_log)

    return TestResult(
        program="uart_tx_9600.asm",
        description="UART TX 9600 baud — cycles to transmit 'HI' (0x48, 0x49)",
        hexalogic_cycles=total,
        hexalogic_detail=f"TX bytes: {[hex(b) for b in tx_bytes]}, {total} cycles at 11.0592 MHz",
        keil_cycles="[PENDING_KEIL_DATA]",
        error_pct="[PENDING_KEIL_DATA]",
        methodology_note="HexaLogic measurement only. Keil/hardware comparison pending.",
    )


def run_interrupt_entry() -> TestResult:
    """Measure interrupt entry latency (cycles from trigger to ISR first instruction).

    Two detection bugs were fixed here (previously this always returned -1):
    1. Trigger detection compared `trace.mnemonic` against the substring "P3",
       but this engine renders operands as raw hex addresses (e.g. "CLR 0xB2"),
       never the symbolic port name, so the substring never matched. It now
       matches the exact bit address of P3.2 (0xB0 + bit 2 = 0xB2).
    2. ISR-entry detection compared `trace.interrupt` against the substring
       "INT0", but this engine reports the *enable-bit* name that vectored
       the interrupt ("EX0"), not the source name ("INT0") — the substring
       never matched either. It now just checks `trace.interrupt` is set,
       which this engine attaches to the trace entry for the ISR's first
       fetched instruction.

    Also note: 8051 ports default to all-1s (driven high) at reset, and
    edge-triggered INT0 (IT0=1) fires on a *falling* (1->0) edge per the
    MCS-51 datasheet — so the `CLR P3.2` instruction is the real trigger
    here, not the later `SETB P3.2` the source comment originally implied.
    """
    src = (PROGRAMS_DIR / "interrupt_entry.asm").read_text()
    asm = Assembler8051(code_size=0x10000)
    prog = asm.assemble(src)
    cpu = CPU8051(code_size=0x10000)
    cpu.load_program(prog)
    cpu.set_clock_hz(12_000_000)

    P3_2_BIT_ADDRESS = "0xB2"
    trigger_cycle = None
    isr_entry_cycle = None

    for _ in range(200):
        cycles_before = cpu.cycles
        trace = cpu.step_into()
        if trigger_cycle is None and trace.mnemonic and P3_2_BIT_ADDRESS in trace.mnemonic:
            trigger_cycle = cycles_before
        if trigger_cycle is not None and trace.interrupt:
            isr_entry_cycle = cpu.cycles
            break
        if cpu.halted:
            break

    r7 = cpu.memory.read_direct(0x07)  # R7 should be 0xAA if ISR ran
    if trigger_cycle is not None and isr_entry_cycle is not None:
        latency = isr_entry_cycle - trigger_cycle
    else:
        latency = -1

    return TestResult(
        program="interrupt_entry.asm",
        description="INT0 edge-triggered — interrupt entry latency",
        hexalogic_cycles=latency,
        hexalogic_detail=(
            f"Latency={latency} cycles (edge to ISR-entry instruction retiring), "
            f"ISR ran={'yes' if r7 == 0xAA else 'no'} (R7={hex(r7)})"
        ),
        keil_cycles="[PENDING_KEIL_DATA]",
        error_pct="[PENDING_KEIL_DATA]",
        methodology_note="HexaLogic measurement only. Keil/hardware comparison pending.",
    )


def main():
    print("=" * 70)
    print("HexaLogic Validation — Independent Check Runner")
    print("=" * 70)
    print()
    print("NOTE: This records HexaLogic's own measurements.")
    print("The [PENDING_KEIL_DATA] columns require real Keil µVision or")
    print("physical AT89C51 traces. See keil_traces/README.md.")
    print()

    results = []

    tests = [
        ("LED Rotate", run_led_rotate),
        ("Timer 0 Overflow", run_timer0_overflow),
        ("UART TX 9600", run_uart_tx),
        ("Interrupt Entry", run_interrupt_entry),
    ]

    for name, func in tests:
        print(f"Running: {name}...", end=" ", flush=True)
        try:
            result = func()
            results.append(result)
            print(f"OK — {result.hexalogic_cycles} cycles")
        except Exception as e:
            print(f"ERROR — {e}")
            results.append(TestResult(
                program=name,
                description=f"ERROR: {e}",
                hexalogic_cycles=-1,
                hexalogic_detail=str(e),
                keil_cycles="[PENDING_KEIL_DATA]",
                error_pct="[PENDING_KEIL_DATA]",
                methodology_note=f"Test failed with error: {e}",
            ))

    # Write CSV
    csv_path = OUTPUT_DIR / "results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "program", "description", "hexalogic_cycles", "hexalogic_detail",
            "keil_cycles", "error_pct", "methodology_note",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))

    # Write JSON for programmatic consumption
    json_path = OUTPUT_DIR / "results.json"
    with open(json_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    print()
    print(f"Results written to:")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")
    print()

    # Summary table
    print(f"{'Program':<25} {'HexaLogic Cycles':>18} {'Keil Cycles':>20} {'Error':>15}")
    print("-" * 80)
    for r in results:
        print(f"{r.program:<25} {r.hexalogic_cycles:>18} {r.keil_cycles:>20} {r.error_pct:>15}")

    print()
    print("⚠  ALL KEIL COLUMNS SHOW [PENDING_KEIL_DATA].")
    print("   This is NOT a validated comparison until real Keil/hardware")
    print("   traces are imported. See keil_traces/README.md.")


if __name__ == "__main__":
    main()
