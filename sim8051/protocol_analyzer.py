"""Rule-based UART protocol analyzer for the 8051 emulator.

Infers UART configuration from live SFR values, decodes serial frames,
and provides intelligent diagnostics — a knowledge-driven automated
protocol analysis engine.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .cpu import CPU8051

# Standard baud rates for reference / proximity matching.
STANDARD_BAUD_RATES = (
    300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800,
    38400, 57600, 76800, 115200, 230400, 460800, 921600,
)

_SERIAL_MODE_NAMES = {
    0: "Mode 0 — Shift Register (synchronous)",
    1: "Mode 1 — 8-bit UART (variable baud)",
    2: "Mode 2 — 9-bit UART (fixed baud)",
    3: "Mode 3 — 9-bit UART (variable baud)",
}

_SERIAL_MODE_FRAME_FORMATS = {
    0: "8N0",   # 8 data bits, no start/stop (shift register)
    1: "8N1",   # start + 8 data + stop
    2: "9N1",   # start + 9 data + stop
    3: "9N1",   # start + 9 data + stop
}

_SERIAL_MODE_FRAME_BITS = {
    0: 8,    # 8 clock pulses per byte
    1: 10,   # start + 8 data + stop
    2: 11,   # start + 9 data + stop
    3: 11,   # start + 9 data + stop
}


@dataclass
class UARTConfig:
    """Inferred UART configuration from live SFR values."""
    serial_mode: int
    serial_mode_name: str
    frame_format: str
    data_bits: int
    baud_rate: float
    baud_rate_nearest_standard: int
    baud_rate_error_pct: float
    baud_source: str
    smod: bool
    receiver_enabled: bool
    frame_bits: int
    frame_time_us: float
    clock_hz: int
    sfr_snapshot: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecodedFrame:
    """A single decoded serial byte (TX or RX)."""
    index: int
    raw_byte: int
    hex_str: str
    ascii_char: str | None
    direction: str              # "TX" or "RX"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolDiagnostic:
    """A diagnostic message from the protocol analyzer."""
    severity: str               # "info", "warning", "error"
    code: str                   # e.g. "NON_STANDARD_BAUD"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolAnalysisResult:
    """Complete protocol analysis result."""
    config: UARTConfig
    decoded_tx: list[DecodedFrame]
    decoded_rx: list[DecodedFrame]
    diagnostics: list[ProtocolDiagnostic]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "decoded_tx": [frame.to_dict() for frame in self.decoded_tx],
            "decoded_rx": [frame.to_dict() for frame in self.decoded_rx],
            "diagnostics": [diag.to_dict() for diag in self.diagnostics],
            "summary": self.summary,
        }


def _read_sfr_safe(cpu: "CPU8051", name: str) -> int:
    """Read an SFR value, returning 0 if not available."""
    try:
        return int(cpu.memory.read_sfr(name)) & 0xFF
    except Exception:
        return 0


def _nearest_standard_baud(baud: float) -> tuple[int, float]:
    """Find the nearest standard baud rate and compute the error percentage."""
    if baud <= 0:
        return 0, 0.0
    nearest = min(STANDARD_BAUD_RATES, key=lambda s: abs(s - baud))
    error_pct = abs(baud - nearest) / nearest * 100.0
    return nearest, round(error_pct, 3)


def _infer_baud_rate(cpu: "CPU8051", mode: int, smod: bool) -> tuple[float, str]:
    """Infer baud rate from SFR values for the given serial mode.

    Returns (baud_rate_hz, source_description).
    """
    clock_hz = cpu.clock_hz or 12_000_000
    smod_factor = 2 if smod else 1

    # Mode 0: Shift register — baud = f_osc / 12
    if mode == 0:
        baud = clock_hz / 12.0
        return baud, "oscillator (f_osc / 12)"

    # Mode 2: Fixed baud — f_osc / 64 (or / 32 if SMOD=1)
    if mode == 2:
        divisor = 32 if smod else 64
        baud = clock_hz / divisor
        return baud, f"oscillator (f_osc / {divisor}, SMOD={'1' if smod else '0'})"

    # Mode 1 or 3: Variable baud — from Timer1 or Timer2
    # Check if Timer2 is used as baud generator (TCLK or RCLK set in T2CON)
    t2con = _read_sfr_safe(cpu, "T2CON")
    tclk = bool(t2con & 0x10)
    rclk = bool(t2con & 0x20)

    if tclk or rclk:
        # Timer2 baud generation
        rcap2h = _read_sfr_safe(cpu, "RCAP2H")
        rcap2l = _read_sfr_safe(cpu, "RCAP2L")
        reload_value = (rcap2h << 8) | rcap2l
        span = (0x10000 - reload_value) & 0xFFFF
        if span == 0:
            span = 0x10000
        # Baud = f_osc / (32 × (65536 − [RCAP2H, RCAP2L]))
        baud = clock_hz / (32.0 * span)
        return baud, f"Timer2 (RCAP2H:RCAP2L=0x{rcap2h:02X}{rcap2l:02X}, reload span={span})"

    # Timer1 baud generation — check TMOD for Timer1 mode
    tmod = _read_sfr_safe(cpu, "TMOD")
    timer1_mode = (tmod >> 4) & 0x03

    if timer1_mode == 2:
        # Mode 2: 8-bit auto-reload — most common for baud generation
        th1 = _read_sfr_safe(cpu, "TH1")
        reload_value = th1
        divisor = 256 - reload_value
        if divisor == 0:
            divisor = 256
        # Baud = (2^SMOD / 32) × (f_osc / (12 × (256 − TH1)))
        baud = (smod_factor / 32.0) * (clock_hz / (12.0 * divisor))
        return baud, f"Timer1 Mode 2 (TH1=0x{th1:02X}, divisor={divisor}, SMOD={'1' if smod else '0'})"

    if timer1_mode == 1:
        # Mode 1: 16-bit — unusual for baud generation but possible
        th1 = _read_sfr_safe(cpu, "TH1")
        tl1 = _read_sfr_safe(cpu, "TL1")
        initial = (th1 << 8) | tl1
        overflow_count = 0x10000 - initial
        if overflow_count == 0:
            overflow_count = 0x10000
        baud = (smod_factor / 32.0) * (clock_hz / (12.0 * overflow_count))
        return baud, f"Timer1 Mode 1 (TH1:TL1=0x{th1:02X}{tl1:02X}, overflow every {overflow_count} counts)"

    if timer1_mode == 0:
        # Mode 0: 13-bit — also unusual
        th1 = _read_sfr_safe(cpu, "TH1")
        tl1 = _read_sfr_safe(cpu, "TL1")
        initial = (th1 << 5) | (tl1 & 0x1F)
        overflow_count = 0x2000 - initial
        if overflow_count == 0:
            overflow_count = 0x2000
        baud = (smod_factor / 32.0) * (clock_hz / (12.0 * overflow_count))
        return baud, f"Timer1 Mode 0 (13-bit, overflow every {overflow_count} counts)"

    # Fallback: cannot determine
    return 0.0, "unknown (Timer1 mode 3 or unconfigured)"


def _decode_byte(index: int, raw_byte: int, direction: str) -> DecodedFrame:
    """Decode a single byte into a DecodedFrame."""
    hex_str = f"0x{raw_byte:02X}"
    ascii_char = chr(raw_byte) if 0x20 <= raw_byte <= 0x7E else None
    return DecodedFrame(
        index=index,
        raw_byte=raw_byte,
        hex_str=hex_str,
        ascii_char=ascii_char,
        direction=direction,
    )


def _run_diagnostics(
    cpu: "CPU8051",
    config: UARTConfig,
    tx_count: int,
    rx_count: int,
) -> list[ProtocolDiagnostic]:
    """Generate intelligent diagnostics based on the UART configuration."""
    diagnostics: list[ProtocolDiagnostic] = []

    # Check baud rate proximity to standard values
    if config.baud_rate > 0 and config.baud_rate_error_pct > 3.0:
        diagnostics.append(ProtocolDiagnostic(
            severity="warning",
            code="NON_STANDARD_BAUD",
            message=(
                f"Computed baud rate ({config.baud_rate:.1f} Hz) deviates "
                f"{config.baud_rate_error_pct:.1f}% from nearest standard rate "
                f"({config.baud_rate_nearest_standard} baud). "
                f"Communication errors may occur with real hardware."
            ),
        ))

    # Check if receiver is enabled
    if not config.receiver_enabled:
        diagnostics.append(ProtocolDiagnostic(
            severity="warning",
            code="RECEIVER_DISABLED",
            message=(
                "UART receiver is disabled (REN=0 in SCON). "
                "Incoming data will not be processed. Set REN=1 to enable reception."
            ),
        ))

    # Check if serial interrupt is enabled
    ie = _read_sfr_safe(cpu, "IE")
    ea = bool(ie & 0x80)
    es = bool(ie & 0x10)
    if not ea:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="GLOBAL_INTERRUPTS_DISABLED",
            message=(
                "Global interrupts are disabled (EA=0 in IE). "
                "Serial interrupt service routine will not execute. "
                "TX/RX completion must be polled via TI/RI flags."
            ),
        ))
    elif not es:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="SERIAL_INTERRUPT_DISABLED",
            message=(
                "Serial interrupt is disabled (ES=0 in IE, EA=1). "
                "TX/RX completion must be polled via TI/RI flags."
            ),
        ))

    # Check Timer1 run bit for mode 1/3 baud generation
    if config.serial_mode in {1, 3} and "Timer1" in config.baud_source:
        tcon = _read_sfr_safe(cpu, "TCON")
        tr1 = bool(tcon & 0x40)
        if not tr1:
            diagnostics.append(ProtocolDiagnostic(
                severity="error",
                code="TIMER1_NOT_RUNNING",
                message=(
                    "Timer1 is used for baud rate generation but TR1=0 (timer not running). "
                    "Set TR1=1 in TCON to start the baud clock."
                ),
            ))

    # Check Timer1 mode for baud generation
    if config.serial_mode in {1, 3} and "Timer1" in config.baud_source:
        tmod = _read_sfr_safe(cpu, "TMOD")
        timer1_mode = (tmod >> 4) & 0x03
        if timer1_mode != 2:
            diagnostics.append(ProtocolDiagnostic(
                severity="warning",
                code="TIMER1_NON_AUTORELOAD",
                message=(
                    f"Timer1 is in mode {timer1_mode} (not auto-reload mode 2). "
                    f"For stable baud rate generation, Timer1 should typically be in mode 2 "
                    f"(8-bit auto-reload). Current mode may cause baud rate drift."
                ),
            ))

    # Check for zero baud rate
    if config.baud_rate == 0 and config.serial_mode in {1, 3}:
        diagnostics.append(ProtocolDiagnostic(
            severity="error",
            code="ZERO_BAUD_RATE",
            message=(
                "Computed baud rate is 0 Hz. The timer configuration for baud "
                "generation may be incorrect or the timer reload value is zero."
            ),
        ))

    # Informational: TX/RX activity summary
    if tx_count > 0:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="TX_ACTIVITY",
            message=f"{tx_count} byte(s) transmitted via SBUF.",
        ))

    if rx_count > 0:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="RX_ACTIVITY",
            message=f"{rx_count} byte(s) received / pending in RX queue.",
        ))

    if tx_count == 0 and rx_count == 0:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="NO_SERIAL_ACTIVITY",
            message="No serial data transmitted or received yet.",
        ))

    # Mode-specific notes
    if config.serial_mode == 0:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="SYNC_MODE_NOTE",
            message=(
                "Mode 0 is a synchronous shift register mode using P3.0 (RXD) for data "
                "and P3.1 (TXD) for the shift clock. Baud rate is fixed at f_osc/12."
            ),
        ))
    elif config.serial_mode == 2:
        diagnostics.append(ProtocolDiagnostic(
            severity="info",
            code="FIXED_BAUD_NOTE",
            message=(
                "Mode 2 uses a fixed baud rate derived from the oscillator. "
                "No timer configuration is needed for baud generation."
            ),
        ))

    return diagnostics


def _build_summary(config: UARTConfig, tx_count: int, rx_count: int, diagnostics: list[ProtocolDiagnostic]) -> str:
    """Build a human-readable summary of the protocol analysis."""
    lines = [
        f"UART Protocol Analysis Summary",
        f"══════════════════════════════",
        f"",
        f"Serial Mode: {config.serial_mode_name}",
        f"Frame Format: {config.frame_format} ({config.frame_bits} bits/frame)",
        f"Baud Rate: {config.baud_rate:.1f} Hz",
    ]
    if config.baud_rate > 0:
        lines.append(f"  Nearest Standard: {config.baud_rate_nearest_standard} baud (error: {config.baud_rate_error_pct:.1f}%)")
    lines.extend([
        f"Baud Source: {config.baud_source}",
        f"SMOD: {'Enabled (2×)' if config.smod else 'Disabled'}",
        f"Receiver: {'Enabled' if config.receiver_enabled else 'Disabled'}",
        f"Frame Time: {config.frame_time_us:.1f} µs" if config.frame_time_us > 0 else "Frame Time: N/A",
        f"",
        f"Activity: {tx_count} TX, {rx_count} RX bytes",
    ])

    errors = [d for d in diagnostics if d.severity == "error"]
    warnings = [d for d in diagnostics if d.severity == "warning"]
    if errors:
        lines.append(f"")
        lines.append(f"⚠ {len(errors)} error(s) detected:")
        for diag in errors:
            lines.append(f"  • [{diag.code}] {diag.message}")
    if warnings:
        lines.append(f"")
        lines.append(f"⚡ {len(warnings)} warning(s):")
        for diag in warnings:
            lines.append(f"  • [{diag.code}] {diag.message}")

    return "\n".join(lines)


def analyze_protocol(cpu: "CPU8051") -> ProtocolAnalysisResult:
    """Perform a complete protocol analysis on the current CPU state.

    Reads live SFR values to infer UART configuration, decodes any
    transmitted/received bytes, and generates diagnostic messages.
    """
    clock_hz = cpu.clock_hz or 12_000_000

    # Read core SFRs
    scon = _read_sfr_safe(cpu, "SCON")
    pcon = _read_sfr_safe(cpu, "PCON")
    tmod = _read_sfr_safe(cpu, "TMOD")
    tcon = _read_sfr_safe(cpu, "TCON")
    th1 = _read_sfr_safe(cpu, "TH1")
    tl1 = _read_sfr_safe(cpu, "TL1")
    ie = _read_sfr_safe(cpu, "IE")
    sbuf = _read_sfr_safe(cpu, "SBUF")
    t2con = _read_sfr_safe(cpu, "T2CON")
    rcap2h = _read_sfr_safe(cpu, "RCAP2H")
    rcap2l = _read_sfr_safe(cpu, "RCAP2L")

    sfr_snapshot = {
        "SCON": scon, "PCON": pcon, "TMOD": tmod, "TCON": tcon,
        "TH1": th1, "TL1": tl1, "IE": ie, "SBUF": sbuf,
        "T2CON": t2con, "RCAP2H": rcap2h, "RCAP2L": rcap2l,
    }

    serial_mode = (scon >> 6) & 0x03
    smod = bool(pcon & 0x80)
    receiver_enabled = bool(scon & 0x10)  # REN bit
    data_bits = 9 if serial_mode in {2, 3} else 8

    # Infer baud rate
    baud_rate, baud_source = _infer_baud_rate(cpu, serial_mode, smod)
    nearest_standard, baud_error_pct = _nearest_standard_baud(baud_rate)

    # Frame timing
    frame_bits = _SERIAL_MODE_FRAME_BITS[serial_mode]
    frame_time_us = (frame_bits / baud_rate * 1_000_000.0) if baud_rate > 0 else 0.0

    config = UARTConfig(
        serial_mode=serial_mode,
        serial_mode_name=_SERIAL_MODE_NAMES[serial_mode],
        frame_format=_SERIAL_MODE_FRAME_FORMATS[serial_mode],
        data_bits=data_bits,
        baud_rate=round(baud_rate, 3),
        baud_rate_nearest_standard=nearest_standard,
        baud_rate_error_pct=baud_error_pct,
        baud_source=baud_source,
        smod=smod,
        receiver_enabled=receiver_enabled,
        frame_bits=frame_bits,
        frame_time_us=round(frame_time_us, 3),
        clock_hz=clock_hz,
        sfr_snapshot=sfr_snapshot,
    )

    # Decode TX log
    decoded_tx = [
        _decode_byte(i, byte, "TX")
        for i, byte in enumerate(cpu.serial.tx_log)
    ]

    # Decode RX queue (pending bytes)
    decoded_rx = [
        _decode_byte(i, byte, "RX")
        for i, byte in enumerate(cpu.serial.rx_queue)
    ]

    # Run diagnostics
    diagnostics = _run_diagnostics(cpu, config, len(decoded_tx), len(decoded_rx))

    # Build summary
    summary = _build_summary(config, len(decoded_tx), len(decoded_rx), diagnostics)

    return ProtocolAnalysisResult(
        config=config,
        decoded_tx=decoded_tx,
        decoded_rx=decoded_rx,
        diagnostics=diagnostics,
        summary=summary,
    )
