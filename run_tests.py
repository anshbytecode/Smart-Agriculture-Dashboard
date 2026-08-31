"""
Standard library test runner for Smart Agriculture system.
Executes all unit and integration tests without external dependencies.
"""

import sys
import time
from edge.config import Config
from edge.sensor import SoilMoistureSensor
from edge.actuator import WaterValveActuator, ValveState
from edge.analytics_engine import EdgeAnalyticsEngine, SoilHealthStatus
from edge.lora_module import LoRaTransmitter, LoRaProtocol
from gateway.lora_receiver import LoRaGatewayReceiver

def run_all_tests():
    print("==========================================================================")
    print(" Running Automated Verification Suite for Smart Agriculture System")
    print("==========================================================================")
    
    passed = 0
    failed = 0

    def test(name, func):
        nonlocal passed, failed
        try:
            func()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # 1. Test Offline Autonomy
    def t1():
        sensor = SoilMoistureSensor(is_mock=True)
        actuator = WaterValveActuator(is_mock=True)
        engine = EdgeAnalyticsEngine(sensor, actuator)

        sensor.set_environment_params(forced_moisture=20.0)
        res1 = engine.process_edge_logic(dt=1.0)
        assert res1["sensor"]["moisture_pct"] < 30.0, f"Expected < 30%, got {res1['sensor']['moisture_pct']}"
        assert res1["valve"]["is_open"] is True, "Valve should open when moisture < 30%"
        assert actuator.state == ValveState.OPEN

        sensor.set_environment_params(forced_moisture=70.0)
        res2 = engine.process_edge_logic(dt=1.0)
        assert res2["sensor"]["moisture_pct"] >= 65.0, f"Expected >= 65%, got {res2['sensor']['moisture_pct']}"
        assert res2["valve"]["is_open"] is False, "Valve should close when moisture >= 65%"
        assert actuator.state == ValveState.CLOSED

    test("Offline Autonomous Hysteresis Decision Logic", t1)

    # 2. Test Safety Interlock
    def t2():
        actuator = WaterValveActuator(is_mock=True)
        opened = actuator.open_valve(reason="Test Safety")
        assert opened is True
        assert actuator.state == ValveState.OPEN

        trig1 = actuator.update_safety_checks(dt=500.0)
        assert trig1 is False
        assert actuator.state == ValveState.OPEN

        trig2 = actuator.update_safety_checks(dt=150.0)
        assert trig2 is True
        assert actuator.state == ValveState.CLOSED
        assert actuator.safety_triggered is True

    test("Water Valve Safety Timeout Shutoff Interlock", t2)

    # 3. Test Binary LoRa Framing & CRC
    def t3():
        tx = LoRaTransmitter(is_mock=True)
        rx = LoRaGatewayReceiver()

        sample_summary = {
            "sensor": {"moisture_pct": 42.5, "temperature_c": 26.8, "ambient_humidity_pct": 58.2},
            "valve": {"state": "CLOSED"},
            "analytics": {"health_score": 92.0, "depletion_rate_pct_hr": 1.25}
        }

        tx_info = tx.transmit(sample_summary)
        payload_bytes = bytes.fromhex(tx_info["payload_hex"])

        assert len(payload_bytes) == 16, f"Payload size must be 16 bytes, got {len(payload_bytes)}"
        assert payload_bytes[0] == LoRaProtocol.HEADER_BYTE

        decoded = rx.decode_binary_packet(payload_bytes, rssi_dbm=-80.0, snr_db=10.0)
        assert decoded is not None, "Gateway failed to decode packet"
        assert decoded["moisture_pct"] == 42.5
        assert decoded["temperature_c"] == 26.8
        assert decoded["ambient_humidity_pct"] == 58.2
        assert decoded["valve_state"] == "CLOSED"
        assert decoded["health_score"] == 92.0

    test("LoRa 16-Byte Binary Framing & Gateway CRC Checksum", t3)

    # 4. Test Airtime Math
    def t4():
        tx = LoRaTransmitter(is_mock=True)
        airtime = tx.calculate_lora_airtime_ms(16)
        assert 30.0 < airtime < 60.0, f"Airtime for 16B @ SF7 should be ~51.5ms, got {airtime}"

    test("LoRa SF7 Time-on-Air (Airtime) Math", t4)

    # 5. Test Power Calculator Math
    def t5():
        v_nominal = 3.7
        battery_joules = 2.5 * v_nominal * 3600.0  # 33300 Joules
        lora_e_cycle = 3.3 * 0.120 * 0.050 + 3.3 * 0.000005 * 899.95
        wifi_e_cycle = 3.3 * 0.180 * 3.500 + 3.3 * 0.000015 * 896.50

        lora_days = battery_joules / (96 * lora_e_cycle)
        wifi_days = battery_joules / (96 * wifi_e_cycle)

        assert lora_days > 5000, f"LoRa lifespan should be > 5000 days, got {lora_days}"
        assert wifi_days < 200, f"Wi-Fi lifespan should be < 200 days, got {wifi_days}"
        assert (lora_days / wifi_days) > 40.0

    test("LoRa vs Wi-Fi Battery Lifespan Mathematical Model", t5)

    # 6. Test DB CRUD Operations
    def t6():
        from server.storage import DatabaseStorage
        db = DatabaseStorage(db_path="test_agri.db")
        
        # Zone CRUD
        zid = db.create_zone("Test Zone 2", "Corn", "Clay", 25.0, 60.0)
        zones = db.get_zones()
        assert any(z["id"] == zid for z in zones)
        db.delete_zone(zid)

        # Schedule CRUD
        sid = db.create_schedule(1, "Test Morning", "07:00", 20, "Daily")
        schedules = db.get_schedules()
        assert any(s["id"] == sid for s in schedules)
        db.delete_schedule(sid)

        # Field Note CRUD
        nid = db.create_field_note("Tester", "Soil looks optimal", "INSPECTION")
        notes = db.get_field_notes()
        assert any(n["id"] == nid for n in notes)

    test("Multi-Zone, Schedule, and Field Note CRUD Database Persistence", t6)

    print("--------------------------------------------------------------------------")
    print(f" Test Results: {passed} PASSED, {failed} FAILED")
    print("==========================================================================")
    
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
