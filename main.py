"""
Main System Orchestrator & Execution Entrypoint.
Runs the autonomous local edge analytics loop, LoRa RF transmission simulator,
LoRa gateway packet receiver, SQLite storage, and Uvicorn FastAPI web dashboard server.
"""

import sys
import time
import asyncio
import threading
import uvicorn

from edge.config import Config
from edge.sensor import SoilMoistureSensor
from edge.actuator import WaterValveActuator
from edge.analytics_engine import EdgeAnalyticsEngine
from edge.lora_module import LoRaTransmitter
from gateway.lora_receiver import LoRaGatewayReceiver
from server.storage import DatabaseStorage
from server.app import app, broadcast_telemetry, initialize_components
import server.app as server_module

running = True

def edge_loop_worker(loop):
    """
    Background worker thread running the autonomous edge analytics decision loop
    and LoRa telemetry transmitter.
    """
    print("==========================================================================")
    print("  Smart Agriculture Edge Analytics & LoRa Automated Irrigation System")
    print(f"  Mode: {'MOCK HARDWARE SIMULATION' if Config.MOCK_HARDWARE else 'PHYSICAL HARDWARE RPI'}")
    print(f"  Local Decision Thresholds: Dry < {Config.DRY_THRESHOLD_PCT}% | Target >= {Config.TARGET_MOISTURE_PCT}%")
    print(f"  LoRa PHY Config: {Config.LORA_FREQUENCY_MHZ} MHz, SF{Config.LORA_SPREADING_FACTOR}, +{Config.LORA_TX_POWER_DBM}dBm")
    print("==========================================================================")

    # Initialize shared components
    sensor = SoilMoistureSensor()
    actuator = WaterValveActuator()
    analytics_engine = EdgeAnalyticsEngine(sensor, actuator)
    lora_tx = LoRaTransmitter()
    lora_rx = LoRaGatewayReceiver()
    db = DatabaseStorage()

    # Link handles to server module
    server_module.sensor = sensor
    server_module.actuator = actuator
    server_module.analytics_engine = analytics_engine
    server_module.lora_tx = lora_tx
    server_module.lora_rx = lora_rx
    server_module.db = db

    last_lora_tx_time = 0.0

    while running:
        t0 = time.time()
        
        # 1. Run local edge analytics & autonomous valve control (Offline capability)
        summary = analytics_engine.process_edge_logic(dt=Config.SENSOR_SAMPLE_INTERVAL_SEC)

        # 2. Periodically transmit LoRa summary telemetry
        if (t0 - last_lora_tx_time) >= Config.LORA_TELEMETRY_INTERVAL_SEC:
            last_lora_tx_time = t0
            
            # Transmit via LoRa module
            packet_tx_info = lora_tx.transmit(summary)
            
            # Gateway receives RF packet
            binary_payload = bytes.fromhex(packet_tx_info["payload_hex"])
            decoded_packet = lora_rx.decode_binary_packet(
                binary_payload,
                rssi_dbm=packet_tx_info["rssi_dbm"],
                snr_db=packet_tx_info["snr_db"]
            )

            if decoded_packet:
                decoded_packet["airtime_ms"] = packet_tx_info["airtime_ms"]
                db.log_telemetry(decoded_packet)

            # Broadcast SSE update to connected web dashboard clients
            broadcast_payload = {
                "edge_summary": summary,
                "lora": packet_tx_info,
                "decoded_gateway": decoded_packet,
                "timestamp": t0
            }

            asyncio.run_coroutine_threadsafe(broadcast_telemetry(broadcast_payload), loop)

        time.sleep(Config.SENSOR_SAMPLE_INTERVAL_SEC)

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start Edge Worker Thread
    t = threading.Thread(target=edge_loop_worker, args=(loop,), daemon=True)
    t.start()

    # Start FastAPI Uvicorn Server
    print("\n[Server] Starting Remote Dashboard on http://localhost:8000 ...")
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, loop="asyncio", log_level="warning")
    server = uvicorn.Server(config)
    
    try:
        loop.run_until_complete(server.serve())
    except KeyboardInterrupt:
        print("\nShutting down Smart Agriculture System...")
        global running
        running = False

if __name__ == "__main__":
    main()
