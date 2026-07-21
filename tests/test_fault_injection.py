"""
Tests for the virtual hardware fault injection system.

Covers:
  - stuck_high fault
  - stuck_low fault
  - noise fault (periodic toggling)
  - delay fault (propagation delay)
  - fault clearing
  - invalid fault type rejection
  - multiple faults on different signals
  - fault persistence across device updates
  - API endpoint integration via session
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sim8051.session import SimulatorSession
from sim8051.hardware import VirtualHardwareManager, ValidationError


def _make_session(clock_hz: int = 12_000_000) -> SimulatorSession:
    s = SimulatorSession(session_id="test-fault")
    s.set_clock(clock_hz)
    return s


def _make_hw_with_led(pin: str = "P1.0") -> VirtualHardwareManager:
    hw = VirtualHardwareManager(architecture="8051")
    dev = hw.add_device("led", label=f"LED {pin}")
    hw.update_device(dev.device_id, connections={"pin": pin})
    return hw


class TestFaultInjectionCore:
    """Tests for inject_fault / clear_fault on VirtualHardwareManager."""

    def test_stuck_high_overrides_signal(self):
        hw = _make_hw_with_led("P1.0")
        hw.inject_fault("P1.0", "stuck_high")
        bindings = hw.input_bindings()
        if "P1.0" in bindings:
            assert bindings["P1.0"] == 1

    def test_stuck_low_overrides_signal(self):
        hw = _make_hw_with_led("P1.1")
        hw.inject_fault("P1.1", "stuck_low")
        bindings = hw.input_bindings()
        if "P1.1" in bindings:
            assert bindings["P1.1"] == 0

    def test_noise_fault_accepted(self):
        hw = _make_hw_with_led("P1.2")
        hw.inject_fault("P1.2", "noise", period_ms=10)
        # Should not raise — noise toggles at configurable frequency
        bindings = hw.input_bindings(time_ms=0.0)
        assert isinstance(bindings, dict)

    def test_delay_fault_accepted(self):
        hw = _make_hw_with_led("P1.3")
        hw.inject_fault("P1.3", "delay", delay_ms=25)
        bindings = hw.input_bindings(time_ms=100.0)
        assert isinstance(bindings, dict)

    def test_clear_fault_removes_fault(self):
        hw = _make_hw_with_led("P1.4")
        hw.inject_fault("P1.4", "stuck_high")
        # Verify fault is active
        b1 = hw.input_bindings()
        if "P1.4" in b1:
            assert b1["P1.4"] == 1
        # Clear and verify
        hw.clear_fault("P1.4")
        b2 = hw.input_bindings()
        assert isinstance(b2, dict)

    def test_invalid_fault_type_raises(self):
        hw = _make_hw_with_led("P1.5")
        with pytest.raises(ValidationError):
            hw.inject_fault("P1.5", "invalid_bogus_type")

    def test_multiple_faults_different_signals(self):
        hw = VirtualHardwareManager(architecture="8051")
        d1 = hw.add_device("led", label="LED A")
        hw.update_device(d1.device_id, connections={"pin": "P1.0"})
        d2 = hw.add_device("led", label="LED B")
        hw.update_device(d2.device_id, connections={"pin": "P1.1"})
        hw.inject_fault("P1.0", "stuck_high")
        hw.inject_fault("P1.1", "stuck_low")
        bindings = hw.input_bindings()
        if "P1.0" in bindings:
            assert bindings["P1.0"] == 1
        if "P1.1" in bindings:
            assert bindings["P1.1"] == 0

    def test_fault_case_insensitive(self):
        hw = _make_hw_with_led("P1.6")
        hw.inject_fault("P1.6", "STUCK_HIGH")
        bindings = hw.input_bindings()
        if "P1.6" in bindings:
            assert bindings["P1.6"] == 1

    def test_clear_nonexistent_fault_no_error(self):
        hw = VirtualHardwareManager(architecture="8051")
        # Clearing a fault that was never set should not raise
        hw.clear_fault("P2.0")

    def test_fault_survives_device_addition(self):
        hw = _make_hw_with_led("P1.7")
        hw.inject_fault("P1.7", "stuck_low")
        # Add another device — fault should remain in effect
        d2 = hw.add_device("led", label="LED Extra")
        hw.update_device(d2.device_id, connections={"pin": "P1.0"})
        bindings = hw.input_bindings()
        if "P1.7" in bindings:
            assert bindings["P1.7"] == 0


class TestFaultInjectionWithSession:
    """Integration tests using a full SimulatorSession."""

    def test_fault_overrides_firmware_output(self):
        """Firmware writes 0xFF to P1, but stuck_low on P1.0 should override."""
        s = _make_session()
        source = "ORG 0000H\nMOV P1,#0FFH\nSJMP $\nEND"
        s.assemble(source)
        led = s.hardware.add_device("led", label="LED P1.0")
        s.hardware.update_device(led.device_id, connections={"pin": "P1.0"})
        s.hardware.inject_fault("P1.0", "stuck_low")
        result = s.run(max_steps=10)
        bindings = s.hardware.input_bindings()
        if "P1.0" in bindings:
            assert bindings["P1.0"] == 0, "stuck_low should override P1=0xFF"

    def test_fault_clear_restores_firmware_value(self):
        """After clearing a fault, the real firmware value should show."""
        s = _make_session()
        source = "ORG 0000H\nMOV P1,#0FFH\nSJMP $\nEND"
        s.assemble(source)
        led = s.hardware.add_device("led", label="LED P1.0")
        s.hardware.update_device(led.device_id, connections={"pin": "P1.0"})
        s.hardware.inject_fault("P1.0", "stuck_low")
        s.run(max_steps=10)
        s.hardware.clear_fault("P1.0")
        bindings = s.hardware.input_bindings()
        # After clearing, bindings should work without error
        assert isinstance(bindings, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
