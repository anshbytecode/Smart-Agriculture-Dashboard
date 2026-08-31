"""
Edge Analytics Engine & Autonomous Local Decision Loop.
Executes completely offline on the Raspberry Pi without requiring cloud connectivity.
Computes soil health diagnostics, moisture depletion rates, and controls valve actuation.
"""

import time
from collections import deque
from typing import Dict, Any, List, Tuple
from edge.config import Config
from edge.sensor import SoilMoistureSensor
from edge.actuator import WaterValveActuator, ValveState

class SoilHealthStatus:
    OPTIMAL = "OPTIMAL"
    MILD_STRESS = "MILD_STRESS"
    SEVERE_DROUGHT = "SEVERE_DROUGHT"
    WATERLOGGED = "WATERLOGGED"

class EdgeAnalyticsEngine:
    """
    Local analytics engine running directly on edge hardware.
    Performs autonomous moisture threshold control with hysteresis band,
    soil health diagnostics, and water consumption estimations.
    """
    def __init__(self, sensor: SoilMoistureSensor, actuator: WaterValveActuator):
        self.sensor = sensor
        self.actuator = actuator
        
        # Sliding window history for depletion rate calculation (timestamp, moisture_pct)
        self.moisture_history = deque(maxlen=60)
        
        # Analytics state
        self.depletion_rate_pct_per_hr: float = 0.0
        self.health_status: str = SoilHealthStatus.OPTIMAL
        self.health_score: float = 100.0
        self.estimated_hours_to_wilting: float = 99.0
        self.last_decision_reason: str = "System Initialized"
        self.offline_mode_active: bool = True  # Always True - local autonomy

    def update_history(self, moisture_pct: float, timestamp: float):
        """Records telemetry samples into sliding window."""
        self.moisture_history.append((timestamp, moisture_pct))
        self._calculate_depletion_rate()

    def _calculate_depletion_rate(self):
        """Calculates moisture change rate (% change per hour)."""
        if len(self.moisture_history) < 5:
            self.depletion_rate_pct_per_hr = 0.0
            return

        t_first, m_first = self.moisture_history[0]
        t_last, m_last = self.moisture_history[-1]
        
        time_diff_hours = (t_last - t_first) / 3600.0
        if time_diff_hours <= 0:
            return

        # Positive value means drying (depletion)
        rate = (m_first - m_last) / time_diff_hours
        self.depletion_rate_pct_per_hr = round(rate, 2)

        # Estimate hours until critical low (wilting point)
        current_m = m_last
        if current_m > Config.CRITICAL_LOW_PCT and self.depletion_rate_pct_per_hr > 0.01:
            hours = (current_m - Config.CRITICAL_LOW_PCT) / self.depletion_rate_pct_per_hr
            self.estimated_hours_to_wilting = round(min(999.0, max(0.0, hours)), 1)
        else:
            self.estimated_hours_to_wilting = 999.0

    def evaluate_soil_health(self, moisture_pct: float) -> Tuple[str, float]:
        """Determines soil health status and 0-100 score."""
        if moisture_pct >= Config.CRITICAL_HIGH_PCT:
            self.health_status = SoilHealthStatus.WATERLOGGED
            score = max(30.0, 100.0 - (moisture_pct - Config.CRITICAL_HIGH_PCT) * 3.0)
        elif moisture_pct < Config.CRITICAL_LOW_PCT:
            self.health_status = SoilHealthStatus.SEVERE_DROUGHT
            score = max(0.0, (moisture_pct / Config.CRITICAL_LOW_PCT) * 40.0)
        elif moisture_pct < Config.DRY_THRESHOLD_PCT:
            self.health_status = SoilHealthStatus.MILD_STRESS
            score = 60.0 + (moisture_pct - Config.CRITICAL_LOW_PCT) / (Config.DRY_THRESHOLD_PCT - Config.CRITICAL_LOW_PCT) * 25.0
        else:
            self.health_status = SoilHealthStatus.OPTIMAL
            score = 85.0 + min(15.0, (moisture_pct - Config.DRY_THRESHOLD_PCT) / (Config.TARGET_MOISTURE_PCT - Config.DRY_THRESHOLD_PCT) * 15.0)

        self.health_score = round(score, 1)
        return self.health_status, self.health_score

    def process_edge_logic(self, dt: float = 1.0) -> Dict[str, Any]:
        """
        Main autonomous edge control loop step:
        1. Reads sensor data.
        2. Evaluates hysteresis thresholds.
        3. Actuates valve locally without network dependency.
        4. Updates safety timers and diagnostics.
        """
        # 1. Read sensor
        sensor_data = self.sensor.read_moisture(
            is_valve_open=(self.actuator.state == ValveState.OPEN),
            dt=dt
        )
        current_moisture = sensor_data["moisture_pct"]
        now = time.time()
        
        self.update_history(current_moisture, now)
        self.evaluate_soil_health(current_moisture)

        # 2. Check actuator safety shutoffs
        self.actuator.update_safety_checks(dt)

        # 3. Autonomous Hysteresis Decision Logic (Local Decision Making)
        if not self.actuator.manual_override:
            if current_moisture < Config.DRY_THRESHOLD_PCT:
                if self.actuator.state == ValveState.CLOSED:
                    reason = f"Local Decision: Soil dry ({current_moisture}% < {Config.DRY_THRESHOLD_PCT}%)"
                    opened = self.actuator.open_valve(reason=reason)
                    if opened:
                        self.last_decision_reason = reason
            elif current_moisture >= Config.TARGET_MOISTURE_PCT:
                if self.actuator.state == ValveState.OPEN:
                    reason = f"Local Decision: Target moisture reached ({current_moisture}% >= {Config.TARGET_MOISTURE_PCT}%)"
                    self.actuator.close_valve(reason=reason)
                    self.last_decision_reason = reason

        valve_status = self.actuator.get_status()

        return {
            "sensor": sensor_data,
            "valve": valve_status,
            "analytics": {
                "health_status": self.health_status,
                "health_score": self.health_score,
                "depletion_rate_pct_hr": self.depletion_rate_pct_per_hr,
                "estimated_hours_to_wilting": self.estimated_hours_to_wilting,
                "last_decision_reason": self.last_decision_reason,
                "offline_autonomy": self.offline_mode_active
            }
        }
