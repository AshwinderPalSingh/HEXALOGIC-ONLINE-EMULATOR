"""End-to-end verification for Protocol Analyzer and UART Network features."""

from __future__ import annotations
import json
import sys

from sim8051 import Assembler8051, CPU8051, analyze_protocol
from sim8051.uart_network import UARTNetwork
from sim8051.session import SimulatorSession, SessionStore, InMemorySessionBackend

passed = 0
failed = 0
total = 0


def test(label, condition, detail=""):
    global passed, failed, total
    total += 1
    status = "✅" if condition else "❌"
    print(f"  {status} {label}" + (f" — {detail}" if detail else ""))
    if condition:
        passed += 1
    else:
        failed += 1


# ═══════════════════════════════════════════════════════════════════════
# 1. PROTOCOL ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════════

print("\n╔══════════════════════════════════════════════════╗")
print("║  1. Protocol Analyzer — UART Configuration       ║")
print("╚══════════════════════════════════════════════════╝\n")

# --- Test 1a: Default state (no UART configured) ---
cpu = CPU8051(code_size=0x1000)
result = analyze_protocol(cpu)
test("Default serial mode is 0", result.config.serial_mode == 0)
test("Default baud source is oscillator", "oscillator" in result.config.baud_source)
test("Receiver disabled by default", not result.config.receiver_enabled)
test("Has diagnostics", len(result.diagnostics) > 0)
test("Has summary text", len(result.summary) > 50)
test("result.to_dict() works", isinstance(result.to_dict(), dict))

# --- Test 1b: Mode 1 with Timer1 auto-reload @ 9600 baud ---
print("\n  --- Mode 1 + Timer1 @ 9600 baud ---")
cpu2 = CPU8051(code_size=0x1000)
cpu2.set_clock_hz(11_059_200)
cpu2.memory.write_sfr("SCON", 0x50)   # Mode 1, REN=1
cpu2.memory.write_sfr("TMOD", 0x20)   # Timer1 mode 2 (8-bit auto-reload)
cpu2.memory.write_sfr("TH1", 0xFD)    # Reload for 9600 baud
cpu2.memory.write_sfr("TCON", 0x40)   # TR1=1

result2 = analyze_protocol(cpu2)
test("Serial mode is 1", result2.config.serial_mode == 1)
test("Frame format is 8N1", result2.config.frame_format == "8N1")
test("Baud source mentions Timer1", "Timer1" in result2.config.baud_source)
test("Receiver enabled", result2.config.receiver_enabled)
baud_err = abs(result2.config.baud_rate - 9600) / 9600 * 100
test(f"Baud rate ≈ 9600 (got {result2.config.baud_rate:.1f}, err={baud_err:.1f}%)", baud_err < 5.0)
test("Nearest standard is 9600", result2.config.baud_rate_nearest_standard == 9600)
test("Frame time computed", result2.config.frame_time_us > 0)

# --- Test 1c: Mode 2 fixed baud ---
print("\n  --- Mode 2 fixed baud ---")
cpu3 = CPU8051(code_size=0x1000)
cpu3.set_clock_hz(12_000_000)
cpu3.memory.write_sfr("SCON", 0x80)   # Mode 2 (SM0=1, SM1=0)

result3 = analyze_protocol(cpu3)
test("Serial mode is 2", result3.config.serial_mode == 2)
test("Frame format is 9N1", result3.config.frame_format == "9N1")
test("Data bits is 9", result3.config.data_bits == 9)
test("Baud source is oscillator", "oscillator" in result3.config.baud_source)
expected_baud = 12_000_000 / 64
test(f"Baud rate is f_osc/64 = {expected_baud}", result3.config.baud_rate == expected_baud)

# --- Test 1d: TX decoding ---
print("\n  --- TX byte decoding ---")
cpu4 = CPU8051(code_size=0x1000)
asm = Assembler8051(code_size=0x1000)
source = """
ORG 0000H
MOV SBUF,#041H
NOP
END
""".strip()
program = asm.assemble(source)
cpu4.load_program(program)
cpu4.run(max_steps=4)

result4 = analyze_protocol(cpu4)
test("1 TX byte decoded", len(result4.decoded_tx) == 1)
if result4.decoded_tx:
    frame = result4.decoded_tx[0]
    test("TX byte is 0x41", frame.raw_byte == 0x41)
    test("TX hex is 0x41", frame.hex_str == "0x41")
    test("TX ASCII is 'A'", frame.ascii_char == "A")
    test("TX direction is TX", frame.direction == "TX")

# --- Test 1e: Diagnostics quality ---
print("\n  --- Diagnostics quality ---")
cpu5 = CPU8051(code_size=0x1000)
cpu5.memory.write_sfr("SCON", 0x40)   # Mode 1, REN=0
cpu5.memory.write_sfr("TMOD", 0x20)   # Timer1 mode 2
cpu5.memory.write_sfr("TH1", 0xFD)
# TR1 = 0 (timer not running!)

result5 = analyze_protocol(cpu5)
diag_codes = [d.code for d in result5.diagnostics]
test("Detects receiver disabled", "RECEIVER_DISABLED" in diag_codes)
test("Detects Timer1 not running", "TIMER1_NOT_RUNNING" in diag_codes)
test("Detects global interrupts disabled", "GLOBAL_INTERRUPTS_DISABLED" in diag_codes)

# --- Test 1f: SimulatorSession integration ---
print("\n  --- SimulatorSession integration ---")
session = SimulatorSession(session_id="test-protocol")
session.assemble(source)
session.run(max_steps=4)
payload = session.protocol_analysis()
test("Session protocol_analysis returns dict", isinstance(payload, dict))
test("Has session_id", payload.get("session_id") == "test-protocol")
test("Has config", payload.get("config") is not None)
test("Has decoded_tx", isinstance(payload.get("decoded_tx"), list))
test("Has diagnostics", isinstance(payload.get("diagnostics"), list))


# ═══════════════════════════════════════════════════════════════════════
# 2. MULTI-NODE UART NETWORK TESTS
# ═══════════════════════════════════════════════════════════════════════

print("\n╔══════════════════════════════════════════════════╗")
print("║  2. Multi-Node UART Network                      ║")
print("╚══════════════════════════════════════════════════╝\n")

# Setup: two sessions with programs
store = SessionStore(backend=InMemorySessionBackend())

session_a = store.create(architecture="8051")
session_b = store.create(architecture="8051")

tx_source = """
ORG 0000H
MOV SBUF,#048H
NOP
MOV SBUF,#049H
NOP
END
""".strip()

rx_source = """
ORG 0000H
LJMP MAIN
ORG 0023H
ISR:
MOV A,SBUF
CLR RI
RETI
ORG 0030H
MAIN:
MOV A,#00H
SETB ES
SETB EA
MOV SCON,#050H
WAIT: SJMP WAIT
END
""".strip()

session_a.assemble(tx_source)
session_b.assemble(rx_source)

# --- Test 2a: Network creation ---
print("  --- Link management ---")
network = UARTNetwork()
test("Network starts empty", network.status()["total_links"] == 0)

# --- Test 2b: Create link ---
link = network.link(session_a.session_id, session_b.session_id)
test("Link created", link is not None)
test("Link has ID", len(link.link_id) > 0)
test("Source matches", link.source_session_id == session_a.session_id)
test("Target matches", link.target_session_id == session_b.session_id)
test("Network has 1 link", network.status()["total_links"] == 1)

# --- Test 2c: Prevent self-link ---
print("\n  --- Validation ---")
try:
    network.link(session_a.session_id, session_a.session_id)
    test("Self-link rejected", False)
except ValueError:
    test("Self-link rejected", True)

# --- Test 2d: Prevent duplicate link ---
try:
    network.link(session_a.session_id, session_b.session_id)
    test("Duplicate link rejected", False)
except ValueError:
    test("Duplicate link rejected", True)

# --- Test 2e: Run TX program and transfer ---
print("\n  --- Byte transfer ---")
session_a.run(max_steps=10)
store.save(session_a)
store.save(session_b)

tx_log = session_a.cpu.serial.tx_log
test(f"Session A transmitted {len(tx_log)} bytes", len(tx_log) >= 1, f"tx_log={tx_log}")

# Transfer bytes
transferred = network.transfer(store, session_id=session_a.session_id)
test(f"Transferred {transferred} byte(s)", transferred > 0)

# Check that bytes arrived in session B
session_b_updated = store.backend.get(session_b.session_id)
rx_queue_len = len(session_b_updated.cpu.serial.rx_queue)
test(f"Session B has {rx_queue_len} byte(s) in RX queue", rx_queue_len > 0)

# --- Test 2f: Transfer is idempotent ---
transferred2 = network.transfer(store, session_id=session_a.session_id)
test("Second transfer sends 0 (idempotent)", transferred2 == 0)

# --- Test 2g: Bidirectional link ---
print("\n  --- Bidirectional ---")
link_ba = network.link(session_b.session_id, session_a.session_id)
test("Reverse link created", link_ba is not None)
test("Network has 2 links", network.status()["total_links"] == 2)

# --- Test 2h: Get links by session ---
links_a = network.get_links(session_a.session_id)
test("Session A involved in 2 links", len(links_a) == 2)

# --- Test 2i: Unlink ---
print("\n  --- Unlink ---")
removed = network.unlink(link.link_id)
test("Link removed", removed)
test("Network has 1 link", network.status()["total_links"] == 1)

removed_again = network.unlink(link.link_id)
test("Double-remove returns False", not removed_again)

# --- Test 2j: Unlink session ---
network.link(session_a.session_id, session_b.session_id)
count = network.unlink_session(session_a.session_id)
test(f"Unlink session removed {count} links", count == 2)
test("Network is empty", network.status()["total_links"] == 0)

# --- Test 2k: Network status ---
print("\n  --- Status ---")
status = network.status()
test("Status has total_links", "total_links" in status)
test("Status has total_bytes_transferred", "total_bytes_transferred" in status)
test("Status has links list", isinstance(status["links"], list))


# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 52}")
print(f"  Passed: {passed} ✅")
print(f"  Failed: {failed} ❌")
print(f"  Total:  {total}")
print(f"{'═' * 52}")

if failed > 0:
    print(f"\n  ⚠️  {failed} test(s) need attention.")
else:
    print("\n  🎉 All tests passed!")

sys.exit(0 if failed == 0 else 1)
