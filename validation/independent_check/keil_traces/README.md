# Keil µVision Trace Import Protocol

## Purpose

This directory holds real cycle-count traces captured from Keil µVision or
physical AT89C51 hardware. These are the **independent oracle** needed to
replace the self-referential validation in the original paper.

## Status: [PENDING_KEIL_DATA]

No traces have been imported yet. All `results.csv` entries in the parent
directory show `[PENDING_KEIL_DATA]` in the Keil/expected column.

## How to Capture Traces

### From Keil µVision (Windows)

1. Open Keil µVision 5 (C51 toolchain).
2. Create a new project targeting AT89C51.
3. Add the test program (e.g., `led_rotate.asm`) to the project.
4. Build (F7).
5. Start Debug Session (Ctrl+F5).
6. Open the **Registers** window and note initial `CYCLES` value.
7. Set a breakpoint at the measurement endpoint (see table below).
8. Run (F5) until the breakpoint hits.
9. Record final `CYCLES` value. The difference is the measured cycle count.
10. Export the trace to a `.json` file with this schema:

```json
{
  "program": "led_rotate.asm",
  "keil_version": "µVision V5.xx",
  "target_device": "AT89C51",
  "clock_hz": 12000000,
  "start_cycles": 0,
  "end_cycles": 100609,
  "measured_cycles": 100609,
  "breakpoint_description": "A returns to 0x01 after full rotation",
  "captured_by": "YOUR_NAME",
  "capture_date": "YYYY-MM-DD"
}
```

### From Physical AT89C51 Hardware

1. Program the AT89C51 with the test binary.
2. Connect an oscilloscope to P1.0.
3. Measure the period of the first full rotation.
4. Convert: cycles = period_seconds × (clock_hz / 12).
5. Record in the same JSON schema with `"source": "hardware"`.

## Measurement Endpoints by Program

| Program | Breakpoint / Measurement Point |
|---------|-------------------------------|
| `led_rotate.asm` | A returns to 0x01 after cycling through 0x02→0x80 |
| `timer0_overflow.asm` | TF0 flag is set (Timer 0 overflow) |
| `uart_tx_9600.asm` | Both bytes transmitted (TI set twice) |
| `interrupt_entry.asm` | PC enters ISR at 0x0003 after SETB P3.2 |

## Importing Traces

After capturing, place the `.json` files in this directory and re-run:

```bash
python3 validation/independent_check/run_comparison.py --keil-dir validation/independent_check/keil_traces/
```

The comparison script will automatically pick up the Keil measurements and
compute real error percentages, replacing the `[PENDING_KEIL_DATA]` placeholders.
