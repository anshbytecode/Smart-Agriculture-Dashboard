"""
Configuration settings for Smart Agriculture Edge Node, LoRa Transceiver, and System parameters.
"""

import os
from typing import Dict, Any

def is_raspberry_pi() -> bool:
    """Checks if running on Linux/Raspberry Pi hardware."""
    try:
        if os.name != 'posix':
            return False
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo or 'aarch64' in cpuinfo or 'arm' in cpuinfo
    except Exception:
        return os.path.exists('/dev/ttyS0') or os.path.exists('/dev/ttyAMA0') or os.path.exists('/dev/spidev0.0')

class Config:
    # Hardware Connection Status (Set to False for physical connected state display)
    MOCK_HARDWARE: bool = os.getenv("MOCK_HARDWARE", "false").lower() == "true" if os.getenv("MOCK_HARDWARE") else False
    HARDWARE_CONNECTED_STATUS: str = "PHYSICAL IoT CONNECTED"

    # Soil Moisture Thresholds (% Volumetric Water Content)
    DRY_THRESHOLD_PCT: float = 30.0       # Moisture level below which irrigation turns ON
    TARGET_MOISTURE_PCT: float = 65.0     # Moisture level at which irrigation turns OFF (Hysteresis)
    CRITICAL_LOW_PCT: float = 15.0        # Severe drought alert threshold
    CRITICAL_HIGH_PCT: float = 85.0       # Waterlogging alert threshold

    # Soil Health Default Targets
    TARGET_PH: float = 6.8                # Optimal Soil pH
    TARGET_EC_MS_CM: float = 1.4          # Optimal Electrical Conductivity (mS/cm)
    VALVE_FLOW_RATE_LPM: float = 12.5     # Solenoid valve flow rate (Liters per minute)

    # Valve Safety Settings
    MAX_VALVE_ON_SECONDS: int = 600       # Safety maximum continuous valve runtime (10 mins)
    MIN_VALVE_OFF_SECONDS: int = 60       # Minimum rest duration between irrigation cycles

    # Edge Sampling & Analytics Loop
    SENSOR_SAMPLE_INTERVAL_SEC: float = 2.0  # Moisture reading frequency
    LORA_TELEMETRY_INTERVAL_SEC: float = 10.0 # LoRa RF summary transmission frequency

    # LoRa PHY / Module Settings
    LORA_FREQUENCY_MHZ: float = 868.1     # Operating Frequency (EU868 / US915 / IN865)
    LORA_BANDWIDTH_KHZ: float = 125.0
    LORA_SPREADING_FACTOR: int = 7         # SF7 for low airtime / low power
    LORA_CODING_RATE: str = "4/5"
    LORA_TX_POWER_DBM: int = 14           # Transmit power (+14 dBm ~ 25 mW)
    LORA_SERIAL_PORT: str = os.getenv("LORA_PORT", "/dev/ttyS0" if os.name == 'posix' else "COM3")
    LORA_BAUDRATE: int = 9600

    # Physical Raspberry Pi Hardware Pin Definitions
    GPIO_VALVE_RELAY_PIN: int = 18          # GPIO 18 (Pin 12) for Water Valve Relay / Solenoid
    GPIO_SOIL_ADC_SPI_CHANNEL: int = 0      # Channel 0 for MCP3008 ADC or ADS1115 I2C (0x48)
    ADS1115_I2C_ADDRESS: int = 0x48         # I2C Address for ADS1115 ADC
    GPIO_LORA_CS_PIN: int = 8
    GPIO_LORA_RESET_PIN: int = 25
    GPIO_LORA_DIO0_PIN: int = 24

    # Storage Settings
    DATABASE_PATH: str = os.getenv("DB_PATH", "agricultural_data.db")

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        return {
            "MOCK_HARDWARE": cls.MOCK_HARDWARE,
            "HARDWARE_CONNECTED_STATUS": cls.HARDWARE_CONNECTED_STATUS,
            "DRY_THRESHOLD_PCT": cls.DRY_THRESHOLD_PCT,
            "TARGET_MOISTURE_PCT": cls.TARGET_MOISTURE_PCT,
            "CRITICAL_LOW_PCT": cls.CRITICAL_LOW_PCT,
            "CRITICAL_HIGH_PCT": cls.CRITICAL_HIGH_PCT,
            "TARGET_PH": cls.TARGET_PH,
            "TARGET_EC_MS_CM": cls.TARGET_EC_MS_CM,
            "VALVE_FLOW_RATE_LPM": cls.VALVE_FLOW_RATE_LPM,
            "MAX_VALVE_ON_SECONDS": cls.MAX_VALVE_ON_SECONDS,
            "MIN_VALVE_OFF_SECONDS": cls.MIN_VALVE_OFF_SECONDS,
            "SENSOR_SAMPLE_INTERVAL_SEC": cls.SENSOR_SAMPLE_INTERVAL_SEC,
            "LORA_TELEMETRY_INTERVAL_SEC": cls.LORA_TELEMETRY_INTERVAL_SEC,
            "LORA_FREQUENCY_MHZ": cls.LORA_FREQUENCY_MHZ,
            "LORA_SPREADING_FACTOR": cls.LORA_SPREADING_FACTOR,
            "LORA_TX_POWER_DBM": cls.LORA_TX_POWER_DBM,
        }
