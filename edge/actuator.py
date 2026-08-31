"""
Water Valve Actuator Driver & Interlock Controller.
Manages solenoid valve / relay operations with hardware safety shutoff timers,
water volume calculations, and manual override controls.
"""

import time
from typing import Dict, Any
from edge.config import Config

class ValveState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"

class WaterValveActuator:
    """
    Controls water valve hardware (relay / solenoid) with automatic
    safety timeouts, flow metering, and operational logging.
    """
    def __init__(self, is_mock: bool = Config.MOCK_HARDWARE):
        self.is_mock = is_mock
        self.state: str = ValveState.CLOSED
        self.last_state_change: float = time.time() - Config.MIN_VALVE_OFF_SECONDS
        self.open_duration_seconds: float = 0.0
        self.total_water_cycles: int = 0
        self.total_open_time_seconds: float = 0.0
        self.total_water_delivered_liters: float = 0.0
        self.manual_override: bool = False
        self.safety_triggered: bool = False
        self.safety_reason: str = ""

        if not self.is_mock:
            self._init_hardware()

    def _init_hardware(self):
        """Initializes RPi GPIO output for relay control."""
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(Config.GPIO_VALVE_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
            print(f"[Actuator] Physical Relay Valve Hardware CONNECTED on GPIO Pin {Config.GPIO_VALVE_RELAY_PIN}.")
            return
        except Exception:
            pass

        try:
            from gpiozero import OutputDevice
            self.relay_device = OutputDevice(Config.GPIO_VALVE_RELAY_PIN, active_high=True, initial_value=False)
            print(f"[Actuator] Physical gpiozero Relay Valve Hardware CONNECTED on GPIO {Config.GPIO_VALVE_RELAY_PIN}.")
            return
        except Exception as e:
            print(f"[Actuator] Physical GPIO relay init unavailable ({e}). Using mock actuator mode.")
            self.is_mock = True

    def _set_gpio(self, is_high: bool):
        """Applies signal to physical relay."""
        if not self.is_mock:
            try:
                import RPi.GPIO as GPIO
                GPIO.output(Config.GPIO_VALVE_RELAY_PIN, GPIO.HIGH if is_high else GPIO.LOW)
                return
            except Exception:
                pass
            if hasattr(self, 'relay_device') and self.relay_device:
                if is_high:
                    self.relay_device.on()
                else:
                    self.relay_device.off()

    def open_valve(self, reason: str = "Threshold Triggered") -> bool:
        """
        Opens the water valve if minimum off-time restriction is met
        and safety interlock is clear.
        """
        now = time.time()
        
        # Check minimum off-time restriction to prevent relay rapid cycling
        if self.state == ValveState.CLOSED:
            time_since_closed = now - self.last_state_change
            if time_since_closed < Config.MIN_VALVE_OFF_SECONDS and not self.manual_override:
                print(f"[Actuator] Cannot open valve: Resting (wait {Config.MIN_VALVE_OFF_SECONDS - time_since_closed:.1f}s)")
                return False

        if self.state != ValveState.OPEN:
            self.state = ValveState.OPEN
            self.last_state_change = now
            self.open_duration_seconds = 0.0
            self.total_water_cycles += 1
            self.safety_triggered = False
            self.safety_reason = ""
            self._set_gpio(True)
            print(f"[Actuator] Valve OPENED. Reason: {reason}")
        return True

    def close_valve(self, reason: str = "Target Reached") -> bool:
        """Closes the water valve."""
        now = time.time()
        if self.state != ValveState.CLOSED:
            duration = now - self.last_state_change
            self.total_open_time_seconds += duration
            
            # Calculate water delivered based on flow rate
            flow_per_sec = Config.VALVE_FLOW_RATE_LPM / 60.0
            self.total_water_delivered_liters += (duration * flow_per_sec)

            self.state = ValveState.CLOSED
            self.last_state_change = now
            self.open_duration_seconds = 0.0
            self._set_gpio(False)
            print(f"[Actuator] Valve CLOSED after {duration:.1f}s. Reason: {reason}")
        return True

    def update_safety_checks(self, dt: float) -> bool:
        """
        Periodically called to check valve runtime. Automatically shuts off valve
        if continuous runtime exceeds MAX_VALVE_ON_SECONDS to prevent flooding.
        """
        if self.state == ValveState.OPEN:
            self.open_duration_seconds += dt
            # Increment water delivered continuously
            flow_per_sec = Config.VALVE_FLOW_RATE_LPM / 60.0
            self.total_water_delivered_liters += (dt * flow_per_sec)

            if self.open_duration_seconds >= Config.MAX_VALVE_ON_SECONDS:
                self.safety_triggered = True
                self.safety_reason = f"Safety timeout exceeded ({Config.MAX_VALVE_ON_SECONDS}s)"
                self.close_valve(reason=self.safety_reason)
                return True
        return False

    def toggle_manual_override(self, enable: bool, force_open: bool = False):
        """Allows dashboard / operator to manually override local automatic engine."""
        self.manual_override = enable
        if enable:
            if force_open:
                self.open_valve(reason="Manual Override ON")
            else:
                self.close_valve(reason="Manual Override OFF")
        else:
            print("[Actuator] Manual Override disabled. Returning control to local edge analytics.")

    def get_status(self) -> Dict[str, Any]:
        """Returns current valve state and operation stats."""
        now = time.time()
        current_run = (now - self.last_state_change) if self.state == ValveState.OPEN else 0.0
        return {
            "state": self.state,
            "is_open": (self.state == ValveState.OPEN),
            "manual_override": self.manual_override,
            "current_run_seconds": round(current_run, 1),
            "total_open_seconds": round(self.total_open_time_seconds, 1),
            "total_cycles": self.total_water_cycles,
            "total_water_liters": round(self.total_water_delivered_liters, 1),
            "flow_rate_lpm": Config.VALVE_FLOW_RATE_LPM,
            "safety_triggered": self.safety_triggered,
            "safety_reason": self.safety_reason
        }
