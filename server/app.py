import asyncio
import json
import time
import io
import csv
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from edge.config import Config
from edge.sensor import SoilMoistureSensor
from edge.actuator import WaterValveActuator
from edge.analytics_engine import EdgeAnalyticsEngine
from edge.lora_module import LoRaTransmitter
from gateway.lora_receiver import LoRaGatewayReceiver
from server.storage import DatabaseStorage


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="Smart Agriculture Edge Analytics & LoRa Dashboard",
    version="1.0.0"
)


# =========================================================
# PROJECT PATH
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# =========================================================
# STATIC FILES
# =========================================================

app.mount(
    "/static",
    StaticFiles(
        directory=str(BASE_DIR / "dashboard" / "static")
    ),
    name="static"
)


# =========================================================
# TEMPLATES
# =========================================================

templates = Jinja2Templates(
    directory=str(BASE_DIR / "dashboard" / "templates")
)


# =========================================================
# GLOBAL SUBSYSTEM SINGLETONS
# =========================================================

sensor: Optional[SoilMoistureSensor] = None
actuator: Optional[WaterValveActuator] = None
analytics_engine: Optional[EdgeAnalyticsEngine] = None
lora_tx: Optional[LoRaTransmitter] = None
lora_rx: Optional[LoRaGatewayReceiver] = None
db: Optional[DatabaseStorage] = None

subscribers = set()


# =========================================================
# INITIALIZE COMPONENTS
# =========================================================

def initialize_components():

    global sensor
    global actuator
    global analytics_engine
    global lora_tx
    global lora_rx
    global db

    if sensor is None:

        sensor = SoilMoistureSensor()

        actuator = WaterValveActuator()

        analytics_engine = EdgeAnalyticsEngine(
            sensor,
            actuator
        )

        lora_tx = LoRaTransmitter()

        lora_rx = LoRaGatewayReceiver()

        db = DatabaseStorage()


# =========================================================
# REQUEST MODELS
# =========================================================

class ConfigUpdate(BaseModel):

    dry_threshold_pct: Optional[float] = None

    target_moisture_pct: Optional[float] = None

    max_valve_on_seconds: Optional[int] = None

    lora_spreading_factor: Optional[int] = None

    lora_frequency_mhz: Optional[float] = None

    mock_hardware: Optional[bool] = None


class ManualValveControl(BaseModel):

    manual_override: bool

    force_open: bool = False


class EnvironmentSimulationRequest(BaseModel):

    rain_rate: Optional[float] = None

    temp_c: Optional[float] = None

    forced_moisture: Optional[float] = None


class PowerCalcRequest(BaseModel):

    battery_capacity_mah: float = 2500.0

    interval_minutes: float = 15.0


class ZoneCreate(BaseModel):

    name: str

    crop_type: str

    soil_type: str = "Loam"

    dry_threshold_pct: float = 30.0

    target_moisture_pct: float = 65.0

    valve_pin: int = 18


class ScheduleCreate(BaseModel):

    zone_id: int = 1

    name: str

    start_time: str

    duration_minutes: int

    days_of_week: str = "Daily"


class AlertRuleCreate(BaseModel):

    metric_name: str

    condition: str

    threshold_value: float

    alert_message: str


class FieldNoteCreate(BaseModel):

    author: str = "Agronomist"

    note_text: str

    category: str = "INSPECTION"


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup_event():

    initialize_components()


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": Config.to_dict()
        }
    )


# =========================================================
# STATUS
# =========================================================

@app.get("/api/status")
async def get_current_status():

    if not analytics_engine:

        initialize_components()

    summary = analytics_engine.process_edge_logic(
        dt=1.0
    )

    tx_stats = {

        "sequence_number":
            lora_tx.sequence_number,

        "total_packets":
            lora_tx.total_packets_sent,

        "total_bytes":
            lora_tx.total_bytes_transmitted,

        "total_energy_joules":
            round(
                lora_tx.total_energy_consumed_joules,
                4
            ),

        "tx_power_dbm":
            lora_tx.tx_power_dbm,

        "spreading_factor":
            lora_tx.spreading_factor,

        "frequency_mhz":
            lora_tx.frequency_mhz
    }

    return {

        "edge_summary":
            summary,

        "lora":
            tx_stats,

        "config":
            Config.to_dict(),

        "timestamp":
            time.time()
    }


# =========================================================
# TELEMETRY HISTORY
# =========================================================

@app.get("/api/history")
async def get_telemetry_history(
    limit: int = 40
):

    if not db:

        initialize_components()

    records = db.get_recent_telemetry(
        limit=limit
    )

    return {
        "history": records
    }


# =========================================================
# CONFIGURATION
# =========================================================

@app.post("/api/config/update")
async def update_system_config(
    req: ConfigUpdate
):

    if (
        req.dry_threshold_pct is not None
        and req.target_moisture_pct is not None
    ):

        if (
            req.dry_threshold_pct
            >= req.target_moisture_pct
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Dry threshold must be strictly "
                    "less than target moisture."
                )
            )

        Config.DRY_THRESHOLD_PCT = (
            req.dry_threshold_pct
        )

        Config.TARGET_MOISTURE_PCT = (
            req.target_moisture_pct
        )

    if req.max_valve_on_seconds is not None:

        Config.MAX_VALVE_ON_SECONDS = (
            req.max_valve_on_seconds
        )

    if req.lora_spreading_factor is not None:

        Config.LORA_SPREADING_FACTOR = (
            req.lora_spreading_factor
        )

        if lora_tx:

            lora_tx.spreading_factor = (
                req.lora_spreading_factor
            )

    if req.lora_frequency_mhz is not None:

        Config.LORA_FREQUENCY_MHZ = (
            req.lora_frequency_mhz
        )

        if lora_tx:

            lora_tx.frequency_mhz = (
                req.lora_frequency_mhz
            )

    if req.mock_hardware is not None:

        Config.MOCK_HARDWARE = (
            req.mock_hardware
        )

        if sensor:

            sensor.is_mock = (
                req.mock_hardware
            )

        if actuator:

            actuator.is_mock = (
                req.mock_hardware
            )

    return {

        "status": "success",

        "config":
            Config.to_dict()
    }


# =========================================================
# CSV EXPORT
# =========================================================

@app.get("/api/export/csv")
async def export_telemetry_csv():

    if not db:

        initialize_components()

    records = db.get_recent_telemetry(
        limit=200
    )

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Timestamp",
        "ISO_Time",
        "Node_ID",
        "Sequence_No",
        "Moisture_VWC_Pct",
        "Temperature_C",
        "Ambient_Humidity_Pct",
        "Health_Score",
        "Depletion_Rate_Pct_Hr",
        "Valve_State",
        "RSSI_dBm",
        "SNR_dB",
        "Airtime_ms"
    ])

    for r in records:

        iso_t = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(
                r["timestamp"]
            )
        )

        writer.writerow([
            r["timestamp"],
            iso_t,
            r["node_id"],
            r["sequence_number"],
            r["moisture_pct"],
            r["temperature_c"],
            r["ambient_humidity_pct"],
            r["health_score"],
            r["depletion_rate_pct_hr"],
            r["valve_state"],
            r["rssi_dbm"],
            r["snr_db"],
            r["airtime_ms"]
        ])

    response = Response(
        content=output.getvalue(),
        media_type="text/csv"
    )

    response.headers[
        "Content-Disposition"
    ] = (
        "attachment; "
        "filename=agricultural_telemetry.csv"
    )

    return response


# =========================================================
# ZONES
# =========================================================

@app.get("/api/zones")
async def get_zones():

    if not db:

        initialize_components()

    return {
        "zones": db.get_zones()
    }


@app.post("/api/zones/create")
async def create_zone(
    req: ZoneCreate
):

    if not db:

        initialize_components()

    zone_id = db.create_zone(

        req.name,

        req.crop_type,

        req.soil_type,

        req.dry_threshold_pct,

        req.target_moisture_pct,

        req.valve_pin
    )

    return {

        "status": "success",

        "zone_id": zone_id
    }


@app.delete("/api/zones/{zone_id}")
async def delete_zone(
    zone_id: int
):

    if not db:

        initialize_components()

    db.delete_zone(
        zone_id
    )

    return {

        "status": "success",

        "deleted_id": zone_id
    }


# =========================================================
# SCHEDULES
# =========================================================

@app.get("/api/schedules")
async def get_schedules():

    if not db:

        initialize_components()

    return {

        "schedules":
            db.get_schedules()
    }


@app.post("/api/schedules/create")
async def create_schedule(
    req: ScheduleCreate
):

    if not db:

        initialize_components()

    schedule_id = db.create_schedule(

        req.zone_id,

        req.name,

        req.start_time,

        req.duration_minutes,

        req.days_of_week
    )

    return {

        "status": "success",

        "schedule_id":
            schedule_id
    }


@app.post(
    "/api/schedules/{schedule_id}/toggle"
)
async def toggle_schedule(
    schedule_id: int,
    enabled: bool
):

    if not db:

        initialize_components()

    db.toggle_schedule(
        schedule_id,
        enabled
    )

    return {

        "status": "success",

        "schedule_id":
            schedule_id,

        "enabled":
            enabled
    }


@app.delete(
    "/api/schedules/{schedule_id}"
)
async def delete_schedule(
    schedule_id: int
):

    if not db:

        initialize_components()

    db.delete_schedule(
        schedule_id
    )

    return {

        "status": "success",

        "deleted_id":
            schedule_id
    }


# =========================================================
# ALERT RULES
# =========================================================

@app.get("/api/alerts")
async def get_alert_rules():

    if not db:

        initialize_components()

    return {

        "alert_rules":
            db.get_alert_rules()
    }


@app.post("/api/alerts/create")
async def create_alert_rule(
    req: AlertRuleCreate
):

    if not db:

        initialize_components()

    rule_id = db.create_alert_rule(

        req.metric_name,

        req.condition,

        req.threshold_value,

        req.alert_message
    )

    return {

        "status": "success",

        "rule_id":
            rule_id
    }


@app.delete(
    "/api/alerts/{rule_id}"
)
async def delete_alert_rule(
    rule_id: int
):

    if not db:

        initialize_components()

    db.delete_alert_rule(
        rule_id
    )

    return {

        "status": "success",

        "deleted_id":
            rule_id
    }


# =========================================================
# FIELD NOTES
# =========================================================

@app.get("/api/notes")
async def get_field_notes():

    if not db:

        initialize_components()

    return {

        "notes":
            db.get_field_notes()
    }


@app.post("/api/notes/create")
async def create_field_note(
    req: FieldNoteCreate
):

    if not db:

        initialize_components()

    note_id = db.create_field_note(

        req.author,

        req.note_text,

        req.category
    )

    return {

        "status": "success",

        "note_id":
            note_id
    }


@app.delete(
    "/api/notes/{note_id}"
)
async def delete_field_note(
    note_id: int
):

    if not db:

        initialize_components()

    db.delete_field_note(
        note_id
    )

    return {

        "status": "success",

        "deleted_id":
            note_id
    }


# =========================================================
# VALVE CONTROL
# =========================================================

@app.post("/api/valve/control")
async def control_valve(
    req: ManualValveControl
):

    if not actuator:

        initialize_components()

    actuator.toggle_manual_override(

        req.manual_override,

        req.force_open
    )

    if db:

        db.log_valve_event(

            "MANUAL_OVERRIDE",

            actuator.state,

            (
                "User Control "
                f"(Override={req.manual_override})"
            )
        )

    return {

        "status": "success",

        "valve_status":
            actuator.get_status()
    }


# =========================================================
# ENVIRONMENT SIMULATION
# =========================================================

@app.post("/api/simulate/environment")
async def simulate_environment(
    req: EnvironmentSimulationRequest
):

    if not sensor:

        initialize_components()

    sensor.set_environment_params(

        rain_rate=req.rain_rate,

        temp_c=req.temp_c,

        forced_moisture=req.forced_moisture
    )

    return {

        "status": "success",

        "rain_rate":
            sensor.rain_rate,

        "temperature_c":
            sensor.temperature_c
    }


# =========================================================
# POWER CALCULATOR
# =========================================================

@app.post("/api/power-calculator")
async def calculate_power_comparison(
    req: PowerCalcRequest
):

    v_nominal = 3.7

    battery_joules = (

        req.battery_capacity_mah

        * (1.0 / 1000.0)

        * v_nominal

        * 3600.0
    )

    cycles_per_day = (

        (24.0 * 60.0)

        / max(
            0.1,
            req.interval_minutes
        )
    )

    e_lora_active = (

        3.3

        * (120.0 / 1000.0)

        * 0.050
    )

    e_lora_sleep = (

        3.3

        * (5.0 / 1000000.0)

        * max(
            0.0,
            (
                req.interval_minutes
                * 60.0
            ) - 0.050
        )
    )

    e_lora_cycle = (
        e_lora_active
        + e_lora_sleep
    )

    lora_days = (

        battery_joules

        / max(
            0.0001,
            e_lora_cycle
            * cycles_per_day
        )
    )

    e_wifi_active = (

        3.3

        * (180.0 / 1000.0)

        * 3.500
    )

    e_wifi_sleep = (

        3.3

        * (15.0 / 1000000.0)

        * max(
            0.0,
            (
                req.interval_minutes
                * 60.0
            ) - 3.500
        )
    )

    e_wifi_cycle = (
        e_wifi_active
        + e_wifi_sleep
    )

    wifi_days = (

        battery_joules

        / max(
            0.0001,
            e_wifi_cycle
            * cycles_per_day
        )
    )

    ratio = round(

        lora_days
        / max(
            0.1,
            wifi_days
        ),

        1
    )

    return {

        "battery_capacity_mah":
            req.battery_capacity_mah,

        "interval_minutes":
            req.interval_minutes,

        "lora": {

            "daily_joules":
                round(
                    e_lora_cycle
                    * cycles_per_day,
                    3
                ),

            "lifespan_years":
                round(
                    lora_days / 365.25,
                    2
                )
        },

        "wifi": {

            "daily_joules":
                round(
                    e_wifi_cycle
                    * cycles_per_day,
                    3
                ),

            "lifespan_years":
                round(
                    wifi_days / 365.25,
                    2
                ),

            "lifespan_days":
                round(
                    wifi_days,
                    1
                )
        },

        "efficiency_multiplier":
            (
                f"{ratio}x longer lifespan "
                "using LoRa"
            )
    }


# =========================================================
# SERVER-SENT EVENTS
# =========================================================

@app.get("/api/stream")
async def event_stream(
    request: Request
):

    async def event_generator():

        queue = asyncio.Queue()

        subscribers.add(queue)

        try:

            while True:

                if await request.is_disconnected():

                    break

                data = await queue.get()

                yield (
                    "data: "
                    f"{json.dumps(data)}"
                    "\n\n"
                )

        except asyncio.CancelledError:

            pass

        finally:

            subscribers.discard(
                queue
            )

    return StreamingResponse(

        event_generator(),

        media_type="text/event-stream"
    )


# =========================================================
# BROADCAST TELEMETRY
# =========================================================

async def broadcast_telemetry(
    payload: Dict[str, Any]
):

    for queue in list(
        subscribers
    ):

        await queue.put(
            payload
        )

