---
title: 'HexaLogic: A Browser-Based Multi-Architecture Microcontroller Simulator with Time-Travel Debugging and Hardware Fault Injection'
tags:
  - Python
  - JavaScript
  - microcontroller simulation
  - 8051
  - ARM
  - embedded systems education
  - time-travel debugging
  - discrete-event simulation
authors:
  - name: Ashwinder Pal Singh
    affiliation: 1
affiliations:
  - name: Thapar Institute of Engineering and Technology, India
    index: 1
date: 8 July 2026
bibliography: paper.bib
---

# Summary

HexaLogic is an open-source, browser-based simulator for the Intel/Atmel
MCS-51 (8051) microcontroller family [@intel_mcs51], with a functional
teaching subset for ARM (A32). It runs entirely in a web browser against a Python/Flask backend,
requiring no local installation, license, or operating-system-specific
tooling. Students and instructors write assembly source in an in-browser
editor, assemble and step through it instruction-by-instruction, and observe
registers, flags, memory, timers, and serial peripherals update live.
Beyond standard instruction-level simulation, HexaLogic adds five
capabilities not commonly found together in existing 8051 tools:
deterministic time-travel debugging (step backward through execution
history), virtual hardware fault injection (stuck-high/low, propagation
delay, and noise faults on simulated pins), an automated rule-based UART
protocol analyzer that infers baud rate and frame configuration directly
from live special-function-register (SFR) state, a multi-node virtual UART
network that lets independently running sessions exchange serial bytes
(modeling inter-processor communication), and session-isolated multi-user
support so a single deployment can serve many students concurrently.

# Statement of need

The 8051 remains one of the most widely taught microcontroller
architectures, valued in laboratory courses for its small, fully transparent
register model and explicit machine-cycle timing [@mazidi_8051]. The
dominant simulation tools for it, however, present real barriers for
students: Keil $\mu$Vision [@keil_uvision] is accurate and full-featured but
requires a Windows installation and a commercial license; Proteus VSM
[@proteus_vsm] adds circuit-level co-simulation at the same desktop-bound,
proprietary cost; EdSim51 [@edsim51] is browser-accessible but ships as a
Java applet, which most current browsers no longer run without extra
configuration, and offers no reverse/step-backward debugging; MCU 8051 IDE
[@mcu8051ide] is open source but desktop-only with limited peripheral
modeling. None of these combines zero-installation browser access with
backward-stepping debugging, hardware fault injection, or automated protocol
analysis. HexaLogic is aimed at students and instructors who need a
free, cross-platform 8051/ARM lab environment reachable from any device with
a browser, and at educators who want to demonstrate hardware fault
conditions or serial-protocol debugging without physical lab equipment.

# State of the field

\autoref{fig:architecture} contextualizes HexaLogic against the four tools
above on two axes that most affect classroom adoption: deployment
accessibility (Windows, Java, or a license required?) and debugging depth
(can students inspect *and reverse* execution history?). None of the
compared tools offers backward stepping; only Proteus and HexaLogic model
hardware-level fault injection; only HexaLogic infers UART configuration
automatically. Prior work on internet-accessible 8051 emulation has focused
on multiuser *in-circuit* emulator designs that still require physical
target hardware behind the network layer [@ibarguengoitia2016internet];
HexaLogic's multi-node UART network instead bridges fully
software-simulated sessions. HexaLogic began as a fork of an existing
open-source, single-architecture 8051 simulator [@shukla_8051sim], which
provided an initial execution core and Flask API scaffold. The present work
replaced and substantially extended that base: a second target architecture
(ARM), and -- more centrally -- the reverse-delta state capture,
fault-injection model, protocol analyzer, and multi-node session bridge
described below [@engblom2002iss], none of which the original project
provided.

# Software design

The backend is a Flask REST API over which the browser frontend (Monaco
editor plus custom register/memory/hardware/waveform views) communicates in
JSON; state lives entirely server-side, isolated per session. The core
engine is organized into five cooperating layers: a **session store** that
isolates concurrent users (in-memory or Redis-backed); an **assembler
factory** and **CPU factory** that select the 8051 or ARM implementation; a
**virtual hardware manager** that turns CPU pin/MMIO state into device
behavior, signal logs, and fault effects; and a **UART network manager**
that bridges serial bytes between linked sessions
(\autoref{fig:architecture}).

Two design choices are central to the added capabilities. First, the
simulator is interpretive rather than compiled or JIT-translated
[@engblom2002iss]: each instruction is fetched, decoded, and executed one at
a time, which costs raw throughput (roughly 2$\times10^5$
instructions/second) but keeps the full programmer-visible state
inspectable at every step. Second, time-travel debugging -- also called
reverse or omniscient debugging [@pothier2007omniscient] -- is implemented
via *reverse deltas* rather than full-state snapshots: before each
instruction executes, the simulator records only the state elements about
to change (a register, a memory byte, the previous program counter),
typically 20-80 bytes. Reversing a step applies the delta backward, giving
$O(k)$ storage per step ($k$ = elements modified) instead of $O(|S|)$ for a
full snapshot -- the difference between reversing thousands of instructions
in a browser tab and not.

![HexaLogic system architecture: the browser frontend communicates with the Flask REST API over JSON/HTTP; the API layer manages sessions, assemblers, CPU cores, virtual hardware, protocol analysis, and the UART network; the simulation core provides instruction-level execution, memory modeling, timer/serial peripherals, and reverse-delta capture.\label{fig:architecture}](system_architecture.png){ width=95% }

# Research impact statement

HexaLogic is newly released and does not yet have external citations or
reported classroom adoption to point to. Its credible near-term
significance rests on three concrete, verifiable properties rather than
projected use: a public, free, zero-installation deployment
(<https://www.hexalogic.xyz>) that removes the Windows/license barrier
documented above for the target student audience; a validation suite of
218 automated tests plus a machine-cycle comparison against a physical Keil
$\mu$Vision 5/AT89C51 [@atmel_at89c51] reference (agreement within 0.104%
across nine representative programs), giving instructors a basis for trusting its
timing behavior before adopting it; and a companion methodology paper
[@hexalogic_ieee_paper] documenting the simulation model, reverse-delta
mechanism, and validation results in full, submitted for peer review
alongside this software description.

# AI usage disclosure

Portions of this project's development, verification, and documentation
were produced with the assistance of an AI coding assistant (Claude,
Anthropic), used for code review, bug identification and fixing, test
authoring, and editing of this paper and its companion manuscript. All
AI-suggested changes were directed, reviewed, and accepted or rejected by
the author, and all functional and timing claims in this paper and its
companion paper were independently verified by the author: the 218-test
suite and regression audit were re-executed to confirm results, and the
physical Keil $\mu$Vision 5/AT89C51 comparison measurements were performed
by hand by the author on real hardware/tooling, not generated or simulated
by the AI assistant.

# Acknowledgements

HexaLogic's `core/` execution engine and initial project scaffold began as
a fork of Devansh Shukla's open-source `8051-Simulator` [@shukla_8051sim]
(MIT license). The multi-architecture `sim8051/` runtime, ARM support,
time-travel debugger, virtual hardware fault injection, automated UART
protocol analyzer, multi-node UART network, and the session/REST API layer
described in this paper are contributions of the present work. No external
funding was received for this work.

# References
