# Power Consumption Analysis: LoRa vs. Wi-Fi for Remote Agricultural Deployment

## Executive Summary

Deploying automated irrigation and soil moisture monitoring systems in remote agricultural fields presents unique energy and communication challenges. Agricultural plots frequently lack fixed electrical infrastructure, requiring edge sensor nodes to run on small batteries or solar-harvesting setups. 

This document analyzes why **LoRa (Long Range sub-GHz RF)** is vastly superior to **Wi-Fi (802.11 b/g/n)** for remote soil moisture telemetry and automated irrigation edge devices, focusing on:
1. **Power Consumption & Battery Lifespan Models**
2. **Protocol Overhead & Airtime Efficiency**
3. **Range & RF Propagation in Agricultural Environments**

---

## 1. Electrical & Protocol Architecture Comparison

| Metric / Parameter | LoRa (SX1276 / SX1262 @ 868 MHz) | Wi-Fi (IEEE 802.11b/g/n @ 2.4 GHz) |
| :--- | :--- | :--- |
| **Operating Frequency** | 865 - 915 MHz (Sub-GHz ISM) | 2.4 GHz / 5 GHz ISM |
| **Deep Sleep Current** | **0.2 µA - 5.0 µA** | **15.0 µA - 50.0 µA** |
| **Active TX Current (+14 dBm)** | **120 mA @ 3.3V** (396 mW) | **180 - 240 mA @ 3.3V** (792 mW) |
| **Connection Overhead** | **Zero (Stateless P2P / Unconfirmed Uplink)** | **Heavy (WPA2 Handshake, DHCP, ARP, TCP/TLS)** |
| **Average Connection Setup Time** | **0 ms** (Instant TX) | **2,500 ms - 4,500 ms** |
| **Payload Size (Optimized)** | 16-byte packed binary frame | > 150-byte JSON over HTTP/MQTT |
| **Time-on-Air (Airtime)** | **~36 ms** (SF7, BW 125kHz) | **~3,500 ms** (including handshake) |
| **Outdoor Range (Line-of-Sight)** | **5 km - 15 km** | **50 m - 100 m** |

---

## 2. Protocol Overhead & Connection Dynamics

### Why Wi-Fi Consumes Excessive Energy in Remote Fields
Wi-Fi is a high-bandwidth, connection-oriented protocol designed for continuous data throughput. When an edge sensor node wakes up from deep sleep to send a reading via Wi-Fi:
1. **RF Synthesizer & Calibration**: Node powers up 2.4 GHz radio (~100 ms).
2. **Network Association**: Scans channels, associates with Access Point (AP), performs WPA2 4-way cryptographic handshake (~1,500 ms @ 180 mA).
3. **Network Configuration**: Requests IP address via DHCP (~1,000 ms @ 180 mA).
4. **Data Transmission**: Resolves DNS, establishes TCP/TLS socket, posts MQTT/HTTP payload (~500 ms).
5. **Total Active Window**: **~3,500 ms** consuming peak active current.

### The LoRa Zero-Association Advantage
LoRa operates as a stateless RF protocol (P2P RF or LoRaWAN unconfirmed uplinks):
1. **Instant Boot**: Node wakes MCU and loads 16-byte binary payload into radio FIFO (~10 ms).
2. **Instant Transmission**: Radio transmits Chirp Spread Spectrum frame at 868 MHz (~36 ms).
3. **Immediate Sleep**: Radio returns to ultra-low 0.2 µA deep sleep mode.
4. **Total Active Window**: **~50 ms** total active time.

$$\text{Active Time Reduction} = \frac{3,500\text{ ms} - 50\text{ ms}}{3,500\text{ ms}} = 98.57\% \text{ reduction in active RF duty cycle}$$

---

## 3. Mathematical Battery Lifespan Model

### System Assumptions
- **Energy Storage**: Single 3.7V 2500 mAh LiPo Battery ($E_{total} = 2.5\text{ Ah} \times 3.7\text{ V} \times 3600\text{ s} = 33,300\text{ Joules}$).
- **Reporting Interval**: Every 15 minutes (96 reporting cycles per day).
- **Operating Voltage**: 3.3V DC regulated.

### A. LoRa Energy Calculation per 15-Minute Cycle ($T = 900\text{ s}$)
- **Active Phase**: $t_{active} = 0.050\text{ s}$, $I_{active} = 120\text{ mA} = 0.120\text{ A}$
  $$E_{active} = V \times I_{active} \times t_{active} = 3.3\text{ V} \times 0.120\text{ A} \times 0.050\text{ s} = 0.01980\text{ Joules}$$

- **Sleep Phase**: $t_{sleep} = 899.950\text{ s}$, $I_{sleep} = 5\text{ µA} = 0.000005\text{ A}$
  $$E_{sleep} = V \times I_{sleep} \times t_{sleep} = 3.3\text{ V} \times 0.000005\text{ A} \times 899.950\text{ s} = 0.01485\text{ Joules}$$

- **Total Energy per Cycle**: 
  $$E_{cycle\_LoRa} = E_{active} + E_{sleep} = 0.01980 + 0.01485 = 0.03465\text{ Joules}$$

- **Daily Energy Consumption**:
  $$E_{daily\_LoRa} = 96 \times 0.03465\text{ J} = 3.3264\text{ Joules / day}$$

- **Calculated Battery Lifespan**:
  $$\text{Lifespan}_{LoRa} = \frac{33,300\text{ Joules}}{3.3264\text{ Joules/day}} = 10,010\text{ days} \approx \mathbf{27.4\text{ years}}$$
  *(Note: Practical lifespan is governed by lithium battery self-discharge rate, yielding ~5 to 10 years real-world maintenance-free operation).*

---

### B. Wi-Fi Energy Calculation per 15-Minute Cycle ($T = 900\text{ s}$)
- **Active Phase**: $t_{active} = 3.500\text{ s}$, $I_{active} = 180\text{ mA} = 0.180\text{ A}$
  $$E_{active} = V \times I_{active} \times t_{active} = 3.3\text{ V} \times 0.180\text{ A} \times 3.500\text{ s} = 2.07900\text{ Joules}$$

- **Sleep Phase**: $t_{sleep} = 896.500\text{ s}$, $I_{sleep} = 15\text{ µA} = 0.000015\text{ A}$
  $$E_{sleep} = V \times I_{sleep} \times t_{sleep} = 3.3\text{ V} \times 0.000015\text{ A} \times 896.500\text{ s} = 0.04438\text{ Joules}$$

- **Total Energy per Cycle**:
  $$E_{cycle\_WiFi} = E_{active} + E_{sleep} = 2.07900 + 0.04438 = 2.12338\text{ Joules}$$

- **Daily Energy Consumption**:
  $$E_{daily\_WiFi} = 96 \times 2.12338\text{ J} = 203.844\text{ Joules / day}$$

- **Calculated Battery Lifespan**:
  $$\text{Lifespan}_{WiFi} = \frac{33,300\text{ Joules}}{203.844\text{ Joules/day}} = 163.3\text{ days} \approx \mathbf{0.45\text{ years (\approx 5.4 months)}}$$

---

### C. Comparison Summary Graph Representation

```
Battery Lifespan Comparison (2500 mAh LiPo @ 15-min reporting):

LoRa   : [==================================================] ~10000 Days (27+ Years Theoretical / 7+ Years Practical)
Wi-Fi  : [==] 163 Days (5.4 Months)
Continuous Wi-Fi (No Sleep): [|] 2 Days
```

---

## 4. Sub-GHz RF Propagation in Agriculture

1. **Foliage & Moisture Attenuation**:
   - 2.4 GHz signals (Wi-Fi) suffer severe absorption by water molecules in dense crop foliage and humid soil (water resonant frequency is close to 2.4 GHz).
   - 868 MHz sub-GHz signals (LoRa) penetrate crop canopy and soil structures with significantly lower path loss ($\sim 15\text{ dB}$ better link margin).

2. **Infrastructure Cost Reduction**:
   - Covering a 100-hectare agricultural farm via Wi-Fi requires dozens of outdoor AP repeaters with dedicated power lines.
   - Covering the same 100-hectare farm via LoRa requires **1 single central gateway** connected to the monitoring dashboard.

---

## 5. Conclusion & Architectural Recommendation

For remote agricultural soil moisture monitoring and automated plant irrigation:
- **Local Edge Autonomy** ensures plant survival regardless of network connectivity.
- **LoRa Communication** provides an **~85x to 100x improvement in battery operational lifespan** compared to Wi-Fi.
- **Packed Binary Payload Framing (16 Bytes)** maximizes spectrum efficiency, keeps duty cycle well below ETSI 1% legal limits, and minimizes solar panel sizing costs for field edge nodes.
