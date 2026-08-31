"""
LoRa Communication Module & Telemetry Transmitter.
Implements a compact binary protocol framing layer to minimize RF airtime,
energy consumption, and duty-cycle overhead for remote agricultural deployment.
Includes hardware transceiver drivers and a high-fidelity LoRa PHY simulator.
"""

import time
import struct
import math
import random
from typing import Dict, Any, Tuple, Optional
from edge.config import Config

class LoRaProtocol:
    HEADER_BYTE = 0xA5
    NODE_ID = 0x01
    FRAME_SIZE_BYTES = 16

class LoRaTransmitter:
    """
    Encodes edge analytics telemetry into compact binary packets and transmits
    via physical LoRa module or high-fidelity simulated RF channel.
    """
    def __init__(self, is_mock: bool = Config.MOCK_HARDWARE):
        self.is_mock = is_mock
        self.sequence_number: int = 0
        self.total_packets_sent: int = 0
        self.total_bytes_transmitted: int = 0
        self.total_energy_consumed_joules: float = 0.0
        
        # LoRa Radio Configuration Parameters
        self.frequency_mhz = Config.LORA_FREQUENCY_MHZ
        self.spreading_factor = Config.LORA_SPREADING_FACTOR
        self.bandwidth_khz = Config.LORA_BANDWIDTH_KHZ
        self.tx_power_dbm = Config.LORA_TX_POWER_DBM
        self.distance_meters = 450.0  # Simulated distance between RPi node & Gateway

        # Serial / Hardware handles
        self.serial_port = None
        if not self.is_mock:
            self._init_hardware()

    def _init_hardware(self):
        """Initializes physical LoRa Serial AT / SPI interface."""
        try:
            import serial
        except ImportError:
            print("[LoRa] pyserial library not installed. Operating in high-fidelity LoRa RF Channel Simulator mode.")
            self.is_mock = True
            return

        possible_ports = [
            Config.LORA_SERIAL_PORT,
            "/dev/ttyS0",
            "/dev/ttyAMA0",
            "/dev/ttyUSB0",
            "/dev/ttyUSB1",
            "COM3", "COM4", "COM5"
        ]
        
        for port in possible_ports:
            try:
                self.serial_port = serial.Serial(port, Config.LORA_BAUDRATE, timeout=1.0)
                print(f"[LoRa] Physical LoRa Radio Hardware CONNECTED on Serial Port '{port}' ({Config.LORA_BAUDRATE} baud).")
                self.is_mock = False
                return
            except Exception:
                continue

        print("[LoRa] Physical LoRa Radio port unavailable. Operating in high-fidelity LoRa RF Channel Simulator mode.")
        self.is_mock = True

    @staticmethod
    def calculate_crc16(data: bytes) -> int:
        """Calculates standard CCITT-FALSE CRC16 checksum for payload validation."""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc

    def encode_binary_frame(
        self,
        moisture_pct: float,
        temp_c: float,
        humidity_pct: float,
        valve_state: str,
        health_score: float,
        depletion_rate: float
    ) -> bytes:
        """
        Packs telemetry into ultra-compact 16-byte binary payload:
        [Header:1][NodeID:1][Moisture:2][Temp:2][Humid:2][Valve:1][Score:1][Depletion:2][Seq:2][CRC16:2]
        """
        valve_code = 1 if valve_state == "OPEN" else 0
        
        m_uint = int(round(clamp(moisture_pct, 0.0, 100.0) * 100))
        t_int = int(round(clamp(temp_c, -40.0, 85.0) * 100))
        h_uint = int(round(clamp(humidity_pct, 0.0, 100.0) * 100))
        score_uint = int(round(clamp(health_score, 0.0, 100.0)))
        dep_int = int(round(clamp(depletion_rate, -50.0, 50.0) * 100))

        # Pack payload without CRC first (14 bytes)
        payload_14 = struct.pack(
            ">BBHHHBBhH",
            LoRaProtocol.HEADER_BYTE,
            LoRaProtocol.NODE_ID,
            m_uint,
            t_int,
            h_uint,
            valve_code,
            score_uint,
            dep_int,
            self.sequence_number & 0xFFFF
        )

        crc = self.calculate_crc16(payload_14)
        full_frame = payload_14 + struct.pack(">H", crc)
        return full_frame

    def calculate_lora_airtime_ms(self, payload_bytes: int) -> float:
        """
        Calculates exact Semtech LoRa RF Transmission Airtime (Time-on-Air) in milliseconds
        based on Spreading Factor (SF), Bandwidth (BW), and Preamble symbols.
        """
        sf = self.spreading_factor
        bw = self.bandwidth_khz * 1000.0  # Hz
        cr = 1  # Coding rate 4/5 -> CR=1
        explicit_header = 1
        low_data_rate_opt = 1 if (sf >= 11 and bw == 125000) else 0

        # Symbol duration T_s (seconds)
        t_sym = (2 ** sf) / bw

        # Preamble duration (8 symbols + 4.25 sync)
        n_preamble = 8.0 + 4.25
        t_preamble = n_preamble * t_sym

        # Payload symbol count calculation formula
        payload_bits = 8 * payload_bytes - 4 * sf + 28 + 16  # 16-bit CRC
        denom = 4 * (sf - 2 * low_data_rate_opt)
        n_payload_sym = 8 + max(math.ceil(payload_bits / denom) * (cr + 4), 0)

        t_payload = n_payload_sym * t_sym
        total_airtime_sec = t_preamble + t_payload
        return total_airtime_sec * 1000.0  # ms

    def calculate_rf_link(self) -> Tuple[float, float]:
        """
        Simulates Sub-GHz RF propagation path loss (Log-Distance Path Loss Model)
        to calculate RSSI (dBm) and Signal-to-Noise Ratio (SNR dB).
        """
        # Free Space Path Loss at 868 MHz
        # FSPL(dB) = 20*log10(d) + 20*log10(f_MHz) - 27.55
        d_km = max(0.01, self.distance_meters / 1000.0)
        fspl = 20.0 * math.log10(self.distance_meters) + 20.0 * math.log10(self.frequency_mhz) - 27.55
        
        # Add foliage / obstacles attenuation in agricultural field (~5-15 dB)
        foliage_attenuation = random.uniform(4.0, 10.0)
        total_loss = fspl + foliage_attenuation

        rssi = self.tx_power_dbm - total_loss
        noise_floor = -115.0  # Typical thermal noise floor for 125 kHz BW
        snr = rssi - noise_floor + random.uniform(-1.5, 1.5)

        return round(rssi, 1), round(snr, 1)

    def transmit(self, edge_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Packs edge data into a binary LoRa payload and transmits over physical
        or simulated LoRa channel.
        """
        self.sequence_number += 1
        
        sensor_data = edge_summary["sensor"]
        valve_data = edge_summary["valve"]
        analytics_data = edge_summary["analytics"]

        binary_payload = self.encode_binary_frame(
            moisture_pct=sensor_data["moisture_pct"],
            temp_c=sensor_data["temperature_c"],
            humidity_pct=sensor_data["ambient_humidity_pct"],
            valve_state=valve_data["state"],
            health_score=analytics_data["health_score"],
            depletion_rate=analytics_data["depletion_rate_pct_hr"]
        )

        payload_len = len(binary_payload)
        airtime_ms = self.calculate_lora_airtime_ms(payload_len)

        # Transmit Energy calculation: P_TX = 25mW (+14dBm), Current ~120mA @ 3.3V = 0.396 W
        tx_power_watts = 0.396
        energy_joules = (airtime_ms / 1000.0) * tx_power_watts
        self.total_energy_consumed_joules += energy_joules
        self.total_packets_sent += 1
        self.total_bytes_transmitted += payload_len

        rssi, snr = self.calculate_rf_link()

        # Hardware transmission
        if not self.is_mock and self.serial_port:
            try:
                # AT command protocol format (e.g. AT+SEND=<len>\r\n)
                self.serial_port.write(binary_payload)
            except Exception as e:
                print(f"[LoRa] Serial TX error: {e}")

        packet_info = {
            "node_id": LoRaProtocol.NODE_ID,
            "sequence_number": self.sequence_number,
            "payload_hex": binary_payload.hex().upper(),
            "payload_bytes": payload_len,
            "frequency_mhz": self.frequency_mhz,
            "spreading_factor": self.spreading_factor,
            "airtime_ms": round(airtime_ms, 2),
            "rssi_dbm": rssi,
            "snr_db": snr,
            "energy_joules": round(energy_joules, 6),
            "timestamp": time.time()
        }

        print(f"[LoRa TX] Packet #{self.sequence_number} Sent ({payload_len}B, Airtime: {airtime_ms:.1f}ms, RSSI: {rssi}dBm, SNR: {snr}dB)")
        return packet_info

def clamp(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, val))
