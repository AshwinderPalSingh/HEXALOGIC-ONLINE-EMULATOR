#!/usr/bin/env python3
"""Comprehensive hardware test for ARM mode via the live API."""
import json
import time
import urllib.request
import urllib.error
import sys

BASE = "http://127.0.0.1:5000/api/v2"
SESSION_ID = None

def api(method, path, body=None):
    global SESSION_ID
    url = f"{BASE}{path}"
    if SESSION_ID:
        url += ("&" if "?" in url else "?") + f"session_id={SESSION_ID}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not SESSION_ID and "session_id" in result:
                SESSION_ID = result["session_id"]
            return result
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  ❌ HTTP {e.code}: {body_text[:300]}")
        return None

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

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
    return condition


def gpio_out_from_pins(r):
    """Extract GPIO output value from hardware pin states in the response."""
    hw = r.get("state", {}).get("hardware", {})
    if not hw:
        return None
    pins = hw.get("pins", {})
    if not pins:
        return None
    value = 0
    for bit in range(8):
        pin = pins.get(f"GPIOA.{bit}", {})
        if pin.get("direction") == "output" and pin.get("level"):
            value |= (1 << bit)
    return value


def led_array_value(r):
    """Extract LED array value from hardware devices in the response."""
    hw = r.get("state", {}).get("hardware", {})
    if not hw:
        # Try diff
        hw_diff = r.get("diff", {}).get("hardware", {})
        devs = hw_diff.get("devices", {})
        for did, dstate in devs.items():
            if "led_array" in did:
                return dstate.get("state", {}).get("value", None)
        return None
    devices = hw.get("devices", [])
    for d in devices:
        if d.get("type") == "led_array":
            return d.get("state", {}).get("value", None)
    return None


# ─── ARM LED Blink Code ─────────────────────────────────────
LED_BLINK_CODE = """\
.syntax unified
.cpu cortex-a9
.global _start

_start:
    LDR R12, =0x40000000
    MOV R0,#0xFF
    STR R0,[R12,#0x08]
    MOV R4,#1

loop:
    STR R4,[R12,#0x00]
    BL delay
    LSL R4,R4,#1
    CMP R4,#0x100
    MOVEQ R4,#1
    B loop

delay:
    MOV R1,#50000
d:
    SUBS R1,R1,#1
    BNE d
    BX LR
"""

GPIO_WRITE_CODE = """\
.syntax unified
.cpu cortex-a9
.global _start
_start:
    LDR R12, =0x40000000
    MOV R0, #0xFF
    STR R0, [R12, #0x08]
    MOV R0, #0xAA
    STR R0, [R12, #0x00]
    MOV R0, #0x55
    STR R0, [R12, #0x00]
    MOV R0, #0xFF
    STR R0, [R12, #0x00]
    MOV R0, #0x00
    STR R0, [R12, #0x00]
"""

COUNTER_CODE = """\
.syntax unified
.cpu cortex-a9
.global _start
_start:
    LDR R12, =0x40000000
    MOV R0, #0xFF
    STR R0, [R12, #0x08]
    MOV R4, #0
count_loop:
    STR R4, [R12, #0x00]
    ADD R4, R4, #1
    CMP R4, #256
    BNE count_loop
"""

# ═══════════════════════════════════════════════════════════════
section("1. SESSION & ARCHITECTURE")
# ═══════════════════════════════════════════════════════════════

r = api("GET", "/state")
test("Session created", r is not None)
test("Session ID assigned", SESSION_ID is not None, f"id={SESSION_ID}")

r = api("POST", "/architecture", {"architecture": "arm"})
test("Architecture set to ARM", r is not None and r.get("architecture") == "arm")

# ═══════════════════════════════════════════════════════════════
section("2. ASSEMBLE ARM CODE")
# ═══════════════════════════════════════════════════════════════

r = api("POST", "/assemble", {"code": LED_BLINK_CODE})
test("Assembly succeeded", r is not None and r.get("has_program"))
listing = r.get("program", {}).get("listing", []) if r else []
test("Listing generated", len(listing) > 0, f"{len(listing)} statements")

# ═══════════════════════════════════════════════════════════════
section("3. HARDWARE DEVICES — ADD & VERIFY AUTO-CONNECT")
# ═══════════════════════════════════════════════════════════════

# Add LED Array (should auto-connect to GPIOA_LOW)
r = api("POST", "/hardware/device", {"type": "led_array"})
test("LED Array added", r is not None and "session_id" in (r or {}))
led_array_id = r.get("created_device_id") if r else None
test("LED Array ID", led_array_id is not None, f"id={led_array_id}")

# Verify auto-connection
r = api("GET", "/state")
devices = r.get("hardware", {}).get("devices", []) if r else []
led_dev = next((d for d in devices if d.get("type") == "led_array"), None)
led_connections = led_dev.get("connections", {}) if led_dev else {}
test("LED Array auto-connected", led_connections.get("bus") == "GPIOA_LOW",
     f"bus={led_connections.get('bus')}")

# Add Seven-Segment Display
r = api("POST", "/hardware/device", {"type": "seven_segment"})
test("7-Segment added", r is not None)
seven_seg_id = r.get("created_device_id") if r else None
test("7-Segment ID", seven_seg_id is not None, f"id={seven_seg_id}")

# Add Stepper Motor (using the 'stepper_motor' alias)
r = api("POST", "/hardware/device", {"type": "stepper_motor"})
test("Stepper Motor added", r is not None)
stepper_id = r.get("created_device_id") if r else None
test("Stepper Motor ID", stepper_id is not None, f"id={stepper_id}")

# Add Switch
r = api("POST", "/hardware/device", {"type": "switch"})
test("Switch added", r is not None)

# Count all devices
r = api("GET", "/state")
devices = r.get("hardware", {}).get("devices", []) if r else []
device_count = len(devices)
test("All devices present", device_count >= 4, f"{device_count} devices")
device_types = [d.get("type") for d in devices]
test("All types correct", "led_array" in device_types and "seven_segment" in device_types
     and "stepper" in device_types and "switch" in device_types,
     f"types: {device_types}")

# ═══════════════════════════════════════════════════════════════
section("4. LED ARRAY — REALTIME MODE BLINK")
# ═══════════════════════════════════════════════════════════════

api("POST", "/execution-mode", {"mode": "realtime"})
api("POST", "/clock", {"hz": 11059200})

gpio_values = set()
led_values = set()
for i in range(20):
    r = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 6.0})
    if r:
        gv = gpio_out_from_pins(r)
        if gv is not None:
            gpio_values.add(gv)
        lv = led_array_value(r)
        if lv is not None:
            led_values.add(lv)
    time.sleep(0.016)

test("GPIO pin output values seen", len(gpio_values) > 1,
     f"unique: {sorted(gpio_values)}")
test("Walking-one pattern visible",
     any(v in gpio_values for v in [1, 2, 4, 8, 16, 32, 64, 128]),
     f"values: {sorted(gpio_values)}")
test("LED array shows values", len(led_values) > 1,
     f"unique: {sorted(led_values)}")

# ═══════════════════════════════════════════════════════════════
section("5. LED ARRAY — FAST MODE")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": LED_BLINK_CODE})
api("POST", "/execution-mode", {"mode": "fast"})

gpio_values_fast = set()
led_values_fast = set()
cycles_list = []
for i in range(10):
    r = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 1.0})
    if r:
        gv = gpio_out_from_pins(r)
        if gv is not None:
            gpio_values_fast.add(gv)
        lv = led_array_value(r)
        if lv is not None:
            led_values_fast.add(lv)
        cycles_list.append(r.get("metrics", {}).get("cycles_executed", 0))

test("Fast mode - GPIO outputs", len(gpio_values_fast) > 1,
     f"unique: {sorted(gpio_values_fast)}")
test("Fast mode - LED array values", len(led_values_fast) > 1,
     f"unique: {sorted(led_values_fast)}")
avg_cycles = sum(cycles_list) / len(cycles_list) if cycles_list else 0
test("Fast mode - high throughput", avg_cycles > 50000,
     f"avg {avg_cycles:,.0f} cycles/req")

# ═══════════════════════════════════════════════════════════════
section("6. SPEED CONTROL VERIFICATION")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": LED_BLINK_CODE})
api("POST", "/execution-mode", {"mode": "realtime"})
time.sleep(0.05)

r1 = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 1.0})
cycles_1x = r1.get("metrics", {}).get("cycles_executed", 0) if r1 else 0
time.sleep(0.05)

r6 = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 6.0})
cycles_6x = r6.get("metrics", {}).get("cycles_executed", 0) if r6 else 0

test("Speed 1x works", cycles_1x > 0, f"{cycles_1x:,} cycles")
test("Speed 6x works", cycles_6x > 0, f"{cycles_6x:,} cycles")
test("Speed scaling: 6x > 1x", cycles_6x > cycles_1x,
     f"ratio: {cycles_6x/max(1,cycles_1x):.1f}x")

# ═══════════════════════════════════════════════════════════════
section("7. SINGLE-STEP GPIO PATTERN")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": GPIO_WRITE_CODE})

gpio_sequence = []
for i in range(20):
    r = api("POST", "/step")
    if r:
        gv = gpio_out_from_pins(r)
        if gv is not None and (not gpio_sequence or gpio_sequence[-1] != gv):
            gpio_sequence.append(gv)

test("GPIO sequence captured", len(gpio_sequence) >= 3,
     f"sequence: {[hex(v) for v in gpio_sequence]}")
expected = [0xAA, 0x55, 0xFF, 0x00]
found = sum(1 for v in expected if v in gpio_sequence)
test("Expected GPIO values present", found >= 3,
     f"{found}/4 expected: {[hex(v) for v in gpio_sequence]}")

# ═══════════════════════════════════════════════════════════════
section("8. COUNTER CODE — FAST EXECUTION")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": COUNTER_CODE})
api("POST", "/execution-mode", {"mode": "fast"})

final_gpio = 0
halt_reason = ""
for i in range(50):
    r = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 1.0})
    if r:
        halt_reason = r.get("result", {}).get("reason", "")
        gv = gpio_out_from_pins(r)
        if gv is not None:
            final_gpio = gv
        if halt_reason == "halted":
            break

test("Counter reached halt", halt_reason == "halted", f"reason={halt_reason}")
test("Final GPIO = 0xFF (counter=255)", final_gpio == 0xFF, f"GPIO=0x{final_gpio:02X}")

# ═══════════════════════════════════════════════════════════════
section("9. STEP / STEP-OVER / STEP-BACK")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": LED_BLINK_CODE})

r = api("POST", "/step")
test("Step works", r is not None and r.get("trace") is not None)
regs = r.get("state", {}).get("registers") or {} if r else {}
pc1 = regs.get("PC", 0)
test("PC after step 1", pc1 > 0, f"PC=0x{pc1:08X}")

r2 = api("POST", "/step")
pc2 = r2.get("state", {}).get("registers", {}).get("PC", 0) if r2 else 0
test("PC after step 2", pc2 > pc1, f"PC=0x{pc2:08X}")

# Step back
r3 = api("POST", "/step-back")
test("Step-back works", r3 is not None)
pc3 = r3.get("state", {}).get("registers", {}).get("PC", 0) if r3 else 0
test("PC reversed by step-back", pc3 <= pc2, f"PC=0x{pc3:08X}")

# Step-over
api("POST", "/reset")
api("POST", "/assemble", {"code": LED_BLINK_CODE})
for _ in range(5):  # Step to BL delay (instruction #5)
    api("POST", "/step")
r_so = api("POST", "/step-over")
test("Step-over works", r_so is not None)
if r_so and r_so.get("result"):
    so_count = r_so.get("result", {}).get("step_count", 0)
    test("Step-over skipped delay", so_count > 10,
         f"count={so_count}")

# ═══════════════════════════════════════════════════════════════
section("10. TRACE & METRICS")
# ═══════════════════════════════════════════════════════════════

api("POST", "/reset")
api("POST", "/assemble", {"code": LED_BLINK_CODE})
api("POST", "/execution-mode", {"mode": "realtime"})
time.sleep(0.02)

r = api("POST", "/run", {"max_steps": 100000, "speed_multiplier": 6.0})
if r:
    result = r.get("result", {})
    steps = result.get("steps", [])
    step_count = result.get("step_count", 0)
    test("Trace data returned", len(steps) > 0 or step_count > 0,
         f"steps={len(steps)}, count={step_count}")

    if steps:
        s = steps[0]
        test("Trace has pc", "pc" in s)
        test("Trace has mnemonic", "mnemonic" in s, f"{s.get('mnemonic','?')}")
        test("Trace has cycles", "cycles" in s)

    metrics = r.get("metrics", {})
    test("Metrics present", bool(metrics))
    if metrics:
        test("Cycles executed", metrics.get("cycles_executed", 0) > 0,
             f"{metrics.get('cycles_executed',0):,}")

# ═══════════════════════════════════════════════════════════════
section("11. HARDWARE DEVICE REMOVAL")
# ═══════════════════════════════════════════════════════════════

if stepper_id:
    r = api("DELETE", "/hardware/device", {"id": stepper_id})
    test("Stepper removed", r is not None)
    new_count = len(r.get("hardware", {}).get("devices", [])) if r else -1
    test("Device count decreased", new_count < device_count, f"{new_count} devices")

# ═══════════════════════════════════════════════════════════════
section("12. RESET & CLEAN STATE")
# ═══════════════════════════════════════════════════════════════

r = api("POST", "/reset")
test("Reset works", r is not None)
if r:
    pc = r.get("registers", {}).get("PC", -1)
    test("PC reset to 0", pc == 0, f"PC={pc}")
    test("Cycles reset", r.get("cycles", -1) == 0)

# ═══════════════════════════════════════════════════════════════
section("13. 8051 MODE — BACKWARDS COMPATIBILITY")
# ═══════════════════════════════════════════════════════════════

api("POST", "/architecture", {"architecture": "8051"})
r = api("POST", "/assemble", {"code": "MOV A, #55H\nMOV P1, A"})
test("8051 assembly works", r is not None and r.get("has_program"))
r = api("POST", "/run", {"max_steps": 10, "speed_multiplier": 1.0})
test("8051 run works", r is not None)
reason = r.get("result", {}).get("reason", "") if r else ""
test("8051 halts correctly", reason == "halted", f"reason={reason}")

api("POST", "/architecture", {"architecture": "arm"})

# ═══════════════════════════════════════════════════════════════
section("RESULTS SUMMARY")
# ═══════════════════════════════════════════════════════════════

print(f"\n  Total:  {total} tests")
print(f"  Passed: {passed} ✅")
print(f"  Failed: {failed} ❌")
print(f"  Rate:   {passed/total*100:.0f}%")

if failed > 0:
    print(f"\n  ⚠️  {failed} test(s) need attention.")
else:
    print(f"\n  🎉 All tests passed!")

sys.exit(0 if failed == 0 else 1)
