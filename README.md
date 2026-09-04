# 🌱 Smart Agriculture Dashboard

A smart agriculture monitoring and irrigation management system built with **Python, FastAPI, IoT/Edge Analytics concepts, LoRa communication, and a web-based dashboard**.

The system is designed to monitor agricultural conditions, analyze sensor data at the edge, manage irrigation valves, track zones and schedules, and provide real-time information through a web dashboard.

## 🚀 Live Demo

🔗 **Live Dashboard:**  
https://smart-agriculture-dashboard-s360.onrender.com/

> The application is deployed on Render. Since it uses a free hosting instance, the service may sleep after inactivity and take a little time to wake up when accessed again.

---

## ✨ Features

### 📊 Dashboard
- Real-time agriculture monitoring dashboard
- Soil moisture monitoring
- Environmental condition monitoring
- Irrigation status
- Zone management
- System status information
- Power consumption analysis

### 💧 Smart Irrigation
- Automatic irrigation control
- Manual valve control
- Soil-moisture-based irrigation
- Irrigation schedules
- Multiple agricultural zones
- Valve status monitoring

### 🧠 Edge Analytics
- Local sensor-data processing
- Agricultural condition analysis
- Irrigation decision support
- Edge-based analytics architecture
- Simulation/mock hardware mode for cloud deployment

### 📡 LoRa Communication
- LoRa transmitter component
- LoRa gateway/receiver component
- Wireless sensor communication architecture
- Gateway-side data handling

### 🚨 Alerts & Monitoring
- Agriculture alerts
- System status monitoring
- Historical sensor information
- Event monitoring
- Real-time updates using Server-Sent Events (SSE)

### 📝 Additional Features
- Notes management
- Configuration management
- Agricultural zones
- Irrigation schedules
- Environment simulation
- Power consumption calculator

---

## 🏗️ System Architecture

```text
                ┌──────────────────────┐
                │   Agricultural Field │
                └──────────┬───────────┘
                           │
                    Sensor Data
                           │
                           ▼
                ┌──────────────────────┐
                │    Edge Computing    │
                │                      │
                │ Soil Moisture Sensor │
                │ Analytics Engine     │
                │ Valve Actuator       │
                └──────────┬───────────┘
                           │
                           │ LoRa
                           ▼
                ┌──────────────────────┐
                │    LoRa Gateway      │
                │      Receiver        │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │      FastAPI         │
                │      Backend         │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   SQLite Database    │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Web Dashboard      │
                │   HTML / CSS / JS    │
                └──────────────────────┘
https://smart-agriculture-dashboard-s360.onrender.com/
