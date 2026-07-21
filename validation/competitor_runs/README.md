# Competitor Comparison Runs

## Purpose

This directory contains results from running the same test programs on
competing simulators, to ground Table I in the paper with hands-on evidence.

## Status

| Tool | Status | Notes |
|------|--------|-------|
| **HexaLogic** | ✅ Automated | Results in `hexalogic/` |
| **EdSim51** | ❌ Manual | Java applet — requires manual testing |
| **MCU 8051 IDE** | ❌ Manual | Tcl/Tk desktop app — requires manual install |
| **Keil µVision** | ❌ Manual | Windows-only, commercial license required |
| **Proteus VSM** | ❌ Manual | Windows-only, commercial license required |

## Reference Programs

Three programs are used for comparison:

1. **LED rotate** — `test_programs/led_rotate.asm`: bit-rotation on P1 with delay loop
2. **Timer 0 overflow** — `test_programs/timer0_overflow.asm`: Mode 1, count to overflow
3. **UART TX** — `test_programs/uart_tx_9600.asm`: 9600 baud, transmit "HI"

## Manual Comparison Protocol

### EdSim51

1. Open https://edsim51.com/ in a browser with Java support
2. Paste the LED rotate program source
3. Click "Assemble," then "Run"
4. Observe: Does P1 display LED rotation? Are LEDs visible?
5. Record: features observed, limitations encountered
6. Save results to `edsim51/results.md`

### MCU 8051 IDE

1. Download from https://sourceforge.net/projects/mcu8051ide/
2. Install (requires Tcl/Tk)
3. Create new project, paste LED rotate program
4. Assemble and run
5. Record: cycle counter values, UI capabilities, peripheral display
6. Save results to `mcu8051ide/results.md`

### Keil µVision (Windows required)

1. Install Keil µVision 5 with C51 toolchain
2. Create project targeting AT89C51
3. Add test program, build, enter debug mode
4. Run to completion, record cycle counter
5. Screenshot the register window showing final cycle count
6. Save to `keil/results.md` + screenshots

### Proteus VSM (Windows required)

1. Install Proteus Design Suite
2. Create schematic with AT89C51 + LEDs on P1
3. Load the hex file, run simulation
4. Record: timing accuracy, LED behavior, oscilloscope traces
5. Save to `proteus/results.md` + screenshots

## Table I Footnote Convention

After collecting results:
- ✝ = feature verified by direct hands-on testing
- * = feature claimed based on official documentation only
- — = feature not available
