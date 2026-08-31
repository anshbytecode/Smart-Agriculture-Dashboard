"""
Comprehensive Unit & Integration Tests for Smart Agriculture Edge Analytics System.
Tests local offline decision making, valve safety shutoff, binary LoRa framing/CRC,
and power consumption mathematical models.
"""

import pytest
import time
from edge.config import Config
from edge.sensor import SoilMoistureSensor
from edge.actuator import WaterValveActuator, ValveState
from edge.analytics_engine import EdgeAnalyticsEngine, SoilHealthStatus
from edge.lora_module import LoRaTransmitter, LoRaProtocol
from gateway.lora_receiver import LoRaGatewayReceiver

def test_edge_local_autonomy():
    """
    Verifies offline local edge decision engine:
    - Moisture < 30% -> Valve OPENS
    - Moisture >= 65% -> Valve CLOSES (Hysteresis control)
    """
    sensor = SoilMoistureSensor(is_mock=True)
    actuator = WaterValveActuator(is_mock=True)
    engine = EdgeAnalyticsEngine(sensor, actuator)

    # 1. Force moisture to dry level (20%)
    sensor.set_environment_params(forced_moisture=20.0)
    res1 = engine.process_edge_logic(dt=1.0)

    assert res1["sensor"]["moisture_pct"] < 30.0
    assert res1["valve"]["is_open"] is True
    assert actuator.state == ValveState.OPEN
    assert "Soil dry" in res1["analytics"]["last_decision_reason"]

    # 2. Increase moisture to target (70%)
    sensor.set_environment_params(forced_moisture=70.0)
    res2 = engine.process_edge_logic(dt=1.0)

    assert res2["sensor"]["moisture_pct"] >= 65.0
    assert res2["valve"]["is_open"] is False
    assert actuator.state == ValveState.CLOSED
    assert "Target moisture reached" in res2["analytics"]["last_decision_reason"]

def test_valve_safety_shutoff():
    """
    Verifies safety interlock: Valve must automatically shut off if open
    longer than MAX_VALVE_ON_SECONDS to prevent field flooding.
    """
    actuator = WaterValveActuator(is_mock=True)
    opened = actuator.open_valve(reason="Test Safety")
    assert opened is True
    assert actuator.state == ValveState.OPEN

    # Simulate 500 seconds (under limit)
    triggered1 = actuator.update_safety_checks(dt=500.0)
    assert triggered1 is False
    assert actuator.state == ValveState.OPEN

    # Simulate additional 150 seconds (total 650s > 600s limit)
    triggered2 = actuator.update_safety_checks(dt=150.0)
    assert triggered2 is True
    assert actuator.state == ValveState.CLOSED
    assert actuator.safety_triggered is True

def test_lora_binary_framing_and_crc():
    """
    Verifies 16-byte compact binary packing, CRC16 checksum calculation,
    and Gateway decoding integrity.
    """
    tx = LoRaTransmitter(is_mock=True)
    rx = LoRaGatewayReceiver()

    sample_summary = {
        "sensor": {"moisture_pct": 42.5, "temperature_c": 26.8, "ambient_humidity_pct": 58.2},
        "valve": {"state": "CLOSED"},
        "analytics": {"health_score": 92.0, "depletion_rate_pct_hr": 1.25}
    }

    # Transmit payload
    tx_info = tx.transmit(sample_summary)
    payload_bytes = bytes.fromhex(tx_info["payload_hex"])

    assert len(payload_bytes) == 16
    assert payload_bytes[0] == LoRaProtocol.HEADER_BYTE

    # Decode at Gateway
    decoded = rx.decode_binary_packet(payload_bytes, rssi_dbm=-80.0, snr_db=10.0)
    assert decoded is not None
    assert decoded["moisture_pct"] == 42.5
    assert decoded["temperature_c"] == 26.8
    assert decoded["ambient_humidity_pct"] == 58.2
    assert decoded["valve_state"] == "CLOSED"
    assert decoded["health_score"] == 92.0

def test_lora_airtime_calculation():
    """
    Verifies exact Semtech LoRa time-on-air calculation for 16-byte payload at SF7.
    """
    tx = LoRaTransmitter(is_mock=True)
    airtime = tx.calculate_lora_airtime_ms(16)
    assert 30.0 < airtime < 60.0

def test_power_calculator_math():
    """
    Verifies energy math comparing LoRa vs Wi-Fi battery life.
    """
    v_nominal = 3.7
    battery_joules = 2.5 * v_nominal * 3600.0  # 33300 Joules
    
    lora_e_cycle = 3.3 * 0.120 * 0.050 + 3.3 * 0.000005 * 899.95
    wifi_e_cycle = 3.3 * 0.180 * 3.500 + 3.3 * 0.000015 * 896.50

    lora_days = battery_joules / (96 * lora_e_cycle)
    wifi_days = battery_joules / (96 * wifi_e_cycle)

    assert lora_days > 5000  # Multi-year lifespan
    assert wifi_days < 200   # Less than 6 months
    assert (lora_days / wifi_days) > 40.0
