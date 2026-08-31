"""
Soil Moisture & Multi-Sensor Hardware Driver.
Supports physical analog reading (ADS1115 / MCP3008 / GPIO PWM) and 
interactive physical simulation modeling soil hydrology, pH, EC, and NPK metrics.
"""

import time
import random
import math
from typing import Dict, Any, Tuple
from edge.config import Config

class SoilMoistureSensor:
    """
    Soil multi-sensor driver with noise filtering, calibration,
    and environmental dynamic simulation.
    """
    def __init__(self, is_mock: bool = Config.MOCK_HARDWARE, alpha_ema: float = 0.2):
        self.is_mock = is_mock
        self.alpha_ema = alpha_ema  # Exponential Moving Average filter weight
        
        # State variables
        self._current_moisture_pct: float = 45.0  # Start at moderate moisture
        self._raw_voltage_mv: float = 2100.0       # Simulated ADC mV (3300mV dry -> 1100mV wet)
        self._filtered_moisture_pct: float = 45.0
        self.temperature_c: float = 24.5
        self.ambient_humidity_pct: float = 60.0
        self.soil_ph: float = Config.TARGET_PH
        self.electrical_conductivity_ec: float = Config.TARGET_EC_MS_CM
        self.nitrogen_ppm: float = 42.0
        self.phosphorus_ppm: float = 26.0
        self.potassium_ppm: float = 38.0
        
        # Calibration constants (Typical capacitive soil sensor v1.2)
        # Dry air voltage = 3100 mV (0% moisture), Water voltage = 1200 mV (100% moisture)
        self.V_DRY_MV = 3100.0
        self.V_WET_MV = 1200.0

        # Environmental simulation rates (% per second)
        self.base_drying_rate: float = 0.05  # Natural evapotranspiration rate
        self.irrigation_rate: float = 1.2   # Moisture gain rate when valve is open
        self.rain_rate: float = 0.0         # Active rain rate

        # Hardware connection handles
        self.adc_device = None
        self.spi = None
        self.ads = None
        if not self.is_mock:
            self._init_hardware()

    def _init_hardware(self):
        """Attempts to initialize physical SPI / I2C ADC hardware on RPi."""
        # 1. Try ADS1115 I2C ADC
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn
            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=Config.ADS1115_I2C_ADDRESS)
            self.chan = AnalogIn(self.ads, ADS.P0)
            print("[Sensor] Physical ADS1115 I2C Soil Sensor Hardware CONNECTED successfully.")
            return
        except Exception:
            pass

        # 2. Try MCP3008 SPI ADC
        try:
            import spidev
            self.spi = spidev.SpiDev()
            self.spi.open(0, Config.GPIO_SOIL_ADC_SPI_CHANNEL)
            self.spi.max_speed_hz = 1350000
            print("[Sensor] Physical MCP3008 SPI Soil Sensor Hardware CONNECTED successfully.")
            return
        except Exception as e:
            print(f"[Sensor] Physical ADC hardware init (I2C/SPI) unavailable ({e}). Using high-fidelity sensor simulator.")
            self.is_mock = True

    def _read_raw_adc(self) -> float:
        """Reads raw ADC voltage in millivolts from physical hardware."""
        if not self.is_mock:
            if self.ads:
                try:
                    return self.chan.voltage * 1000.0
                except Exception as e:
                    print(f"[Sensor] I2C read error: {e}")
            elif self.spi:
                try:
                    r = self.spi.xfer2([1, (8 + Config.GPIO_SOIL_ADC_SPI_CHANNEL) << 4, 0])
                    adc_code = ((r[1] & 3) << 8) + r[2]
                    return (adc_code / 1023.0) * 3300.0
                except Exception as e:
                    print(f"[Sensor] SPI read error: {e}")
        return self._raw_voltage_mv

    def _voltage_to_percentage(self, voltage_mv: float) -> float:
        """Maps raw ADC voltage to Volumetric Water Content percentage (0% - 100%)."""
        if voltage_mv >= self.V_DRY_MV:
            return 0.0
        elif voltage_mv <= self.V_WET_MV:
            return 100.0
        
        # Linear calibration curve (higher voltage = lower moisture)
        pct = (self.V_DRY_MV - voltage_mv) / (self.V_DRY_MV - self.V_WET_MV) * 100.0
        return max(0.0, min(100.0, pct))

    def update_simulation_step(self, dt: float, is_valve_open: bool):
        """
        Updates simulated soil moisture physics based on evapotranspiration,
        irrigation valve status, and simulated rain.
        """
        if not self.is_mock:
            return

        # Temperature-dependent evapotranspiration multiplier
        temp_factor = max(0.5, 1.0 + (self.temperature_c - 25.0) * 0.04)
        
        net_rate = 0.0
        if is_valve_open:
            net_rate += self.irrigation_rate
        if self.rain_rate > 0:
            net_rate += self.rain_rate
        
        # Drying occurs continuously
        net_rate -= (self.base_drying_rate * temp_factor)

        # Update moisture with bounds
        self._current_moisture_pct += (net_rate * dt)
        self._current_moisture_pct = max(5.0, min(95.0, self._current_moisture_pct))

        # Dynamic pH and EC fluctuations with moisture
        self.soil_ph = round(6.8 + (self._current_moisture_pct - 50.0) * 0.005 + random.uniform(-0.02, 0.02), 2)
        self.electrical_conductivity_ec = round(1.4 + (self._current_moisture_pct - 45.0) * 0.01 + random.uniform(-0.03, 0.03), 2)

        # Re-calculate simulated ADC voltage (with slight sensor noise +/- 5mV)
        noise = random.uniform(-5.0, 5.0)
        fraction = self._current_moisture_pct / 100.0
        self._raw_voltage_mv = self.V_DRY_MV - fraction * (self.V_DRY_MV - self.V_WET_MV) + noise

    def read_moisture(self, is_valve_open: bool = False, dt: float = 1.0) -> Dict[str, Any]:
        """
        Reads soil moisture, applies EMA exponential moving average filter,
        and returns sensor metrics.
        """
        if self.is_mock:
            self.update_simulation_step(dt, is_valve_open)
            raw_mv = self._raw_voltage_mv
            instant_pct = self._voltage_to_percentage(raw_mv)
        else:
            raw_mv = self._read_raw_adc()
            instant_pct = self._voltage_to_percentage(raw_mv)

        # Apply EMA filter to smooth out high-frequency noise spikes
        self._filtered_moisture_pct = (self.alpha_ema * instant_pct) + ((1.0 - self.alpha_ema) * self._filtered_moisture_pct)

        return {
            "moisture_pct": round(self._filtered_moisture_pct, 2),
            "raw_instant_pct": round(instant_pct, 2),
            "raw_voltage_mv": round(raw_mv, 1),
            "temperature_c": round(self.temperature_c, 1),
            "ambient_humidity_pct": round(self.ambient_humidity_pct, 1),
            "soil_ph": round(self.soil_ph, 2),
            "electrical_conductivity_ec": round(self.electrical_conductivity_ec, 2),
            "npk": {
                "n_ppm": round(self.nitrogen_ppm, 1),
                "p_ppm": round(self.phosphorus_ppm, 1),
                "k_ppm": round(self.potassium_ppm, 1)
            },
            "timestamp": time.time()
        }

    def set_environment_params(self, rain_rate: float = None, temp_c: float = None, forced_moisture: float = None):
        """Allows dashboard / simulator to dynamically alter environment."""
        if rain_rate is not None:
            self.rain_rate = rain_rate
        if temp_c is not None:
            self.temperature_c = temp_c
        if forced_moisture is not None:
            self._current_moisture_pct = max(0.0, min(100.0, forced_moisture))
            self._filtered_moisture_pct = self._current_moisture_pct
