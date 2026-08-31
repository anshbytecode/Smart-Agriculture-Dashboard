"""
LoRa Gateway Receiver & Packet Decoder.
Receives compact binary frames over RF, verifies CRC16 checksums,
and unpacks structured metrics for telemetry storage and web dashboard display.
"""

import struct
import time
from typing import Dict, Any, Optional
from edge.lora_module import LoRaProtocol, LoRaTransmitter

class LoRaGatewayReceiver:
    """
    Decodes incoming LoRa RF frames from agricultural edge nodes.
    Validates protocol headers, node IDs, and CRC integrity.
    """
    def __init__(self):
        self.packets_received_count: int = 0
        self.corrupted_packets_count: int = 0

    def decode_binary_packet(self, packet_bytes: bytes, rssi_dbm: float = -85.0, snr_db: float = 9.5) -> Optional[Dict[str, Any]]:
        """
        Unpacks 16-byte binary payload:
        [Header:1][NodeID:1][Moisture:2][Temp:2][Humid:2][Valve:1][Score:1][Depletion:2][Seq:2][CRC16:2]
        """
        if len(packet_bytes) != LoRaProtocol.FRAME_SIZE_BYTES:
            print(f"[Gateway] Invalid packet length ({len(packet_bytes)} bytes, expected 16).")
            self.corrupted_packets_count += 1
            return None

        # Verify CRC16 checksum
        payload_14 = packet_bytes[:14]
        received_crc = struct.unpack(">H", packet_bytes[14:16])[0]
        calculated_crc = LoRaTransmitter.calculate_crc16(payload_14)

        if received_crc != calculated_crc:
            print(f"[Gateway] CRC Mismatch! Rx: {hex(received_crc)}, Calc: {hex(calculated_crc)}")
            self.corrupted_packets_count += 1
            return None

        # Unpack payload fields
        header, node_id, m_uint, t_int, h_uint, valve_code, score_uint, dep_int, seq_num = struct.unpack(
            ">BBHHHBBhH",
            payload_14
        )

        if header != LoRaProtocol.HEADER_BYTE:
            print(f"[Gateway] Invalid Header Byte: {hex(header)}")
            self.corrupted_packets_count += 1
            return None

        # Reconstruct scaled values
        moisture_pct = round(m_uint / 100.0, 2)
        temp_c = round(t_int / 100.0, 2)
        humidity_pct = round(h_uint / 100.0, 2)
        valve_state = "OPEN" if valve_code == 1 else "CLOSED"
        health_score = float(score_uint)
        depletion_rate = round(dep_int / 100.0, 2)

        self.packets_received_count += 1

        decoded_record = {
            "node_id": node_id,
            "sequence_number": seq_num,
            "moisture_pct": moisture_pct,
            "temperature_c": temp_c,
            "ambient_humidity_pct": humidity_pct,
            "valve_state": valve_state,
            "health_score": health_score,
            "depletion_rate_pct_hr": depletion_rate,
            "rssi_dbm": rssi_dbm,
            "snr_db": snr_db,
            "received_at": time.time(),
            "crc_valid": True
        }

        print(f"[Gateway RX] Node #{node_id} Frame #{seq_num} Decoded: Moisture={moisture_pct}%, Valve={valve_state}, Score={health_score}")
        return decoded_record
