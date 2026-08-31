"""
SQLite Telemetry & Operational Database Storage.
Provides persistent recording of soil moisture samples, valve actuation events,
LoRa RF signal metrics, multi-zone field plots, irrigation schedules, and field notes.
"""

import sqlite3
import time
from typing import Dict, Any, List, Optional
from edge.config import Config

class DatabaseStorage:
    """
    Manages SQLite database schema and analytical queries.
    """
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates table schemas if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Telemetry records
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                node_id INTEGER NOT NULL,
                sequence_number INTEGER,
                moisture_pct REAL NOT NULL,
                temperature_c REAL,
                ambient_humidity_pct REAL,
                health_score REAL,
                depletion_rate_pct_hr REAL,
                valve_state TEXT NOT NULL,
                rssi_dbm REAL,
                snr_db REAL,
                airtime_ms REAL
            );
            """)

            # Valve Actuation Events
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS valve_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                valve_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                duration_seconds REAL DEFAULT 0.0
            );
            """)

            # Multi-Zone Agricultural Fields
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                crop_type TEXT NOT NULL,
                soil_type TEXT NOT NULL,
                dry_threshold_pct REAL NOT NULL,
                target_moisture_pct REAL NOT NULL,
                valve_pin INTEGER DEFAULT 18,
                created_at REAL NOT NULL
            );
            """)

            # Irrigation Schedules
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                days_of_week TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            );
            """)

            # Custom Alert Rules
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                condition TEXT NOT NULL,
                threshold_value REAL NOT NULL,
                alert_message TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            );
            """)

            # Field Inspection Notes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author TEXT NOT NULL,
                note_text TEXT NOT NULL,
                category TEXT DEFAULT 'INSPECTION',
                timestamp REAL NOT NULL
            );
            """)

            # Seed default Zone if table is empty
            cursor.execute("SELECT COUNT(*) FROM zones")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                INSERT INTO zones (name, crop_type, soil_type, dry_threshold_pct, target_moisture_pct, valve_pin, created_at)
                VALUES ('Zone 1 - Main Crop', 'Tomatoes', 'Loam', 30.0, 65.0, 18, ?)
                """, (time.time(),))

            conn.commit()

    # --- Telemetry & Events ---
    def log_telemetry(self, data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO telemetry (
                timestamp, node_id, sequence_number, moisture_pct,
                temperature_c, ambient_humidity_pct, health_score,
                depletion_rate_pct_hr, valve_state, rssi_dbm, snr_db, airtime_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("timestamp", time.time()),
                data.get("node_id", 1),
                data.get("sequence_number", 0),
                data.get("moisture_pct", 0.0),
                data.get("temperature_c", 0.0),
                data.get("ambient_humidity_pct", 0.0),
                data.get("health_score", 100.0),
                data.get("depletion_rate_pct_hr", 0.0),
                data.get("valve_state", "CLOSED"),
                data.get("rssi_dbm", -85.0),
                data.get("snr_db", 9.0),
                data.get("airtime_ms", 36.0)
            ))
            conn.commit()

    def log_valve_event(self, event_type: str, valve_state: str, reason: str, duration_sec: float = 0.0):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO valve_events (timestamp, event_type, valve_state, reason, duration_seconds)
            VALUES (?, ?, ?, ?, ?)
            """, (time.time(), event_type, valve_state, reason, duration_sec))
            conn.commit()

    def get_recent_telemetry(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in reversed(rows)]

    # --- Zone Management (CRUD) ---
    def create_zone(self, name: str, crop_type: str, soil_type: str, dry_thresh: float, target_moisture: float, valve_pin: int = 18) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO zones (name, crop_type, soil_type, dry_threshold_pct, target_moisture_pct, valve_pin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, crop_type, soil_type, dry_thresh, target_moisture, valve_pin, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_zones(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM zones ORDER BY id ASC")
            return [dict(r) for r in cursor.fetchall()]

    def delete_zone(self, zone_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
            conn.commit()

    # --- Schedule Management (CRUD) ---
    def create_schedule(self, zone_id: int, name: str, start_time: str, duration_minutes: int, days_of_week: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO schedules (zone_id, name, start_time, duration_minutes, days_of_week, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (zone_id, name, start_time, duration_minutes, days_of_week, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_schedules(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    def toggle_schedule(self, schedule_id: int, enabled: bool):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE schedules SET enabled = ? WHERE id = ?", (1 if enabled else 0, schedule_id))
            conn.commit()

    def delete_schedule(self, schedule_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()

    # --- Custom Alert Rules (CRUD) ---
    def create_alert_rule(self, metric_name: str, condition: str, threshold_value: float, alert_message: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO alert_rules (metric_name, condition, threshold_value, alert_message, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """, (metric_name, condition, threshold_value, alert_message, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_alert_rules(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alert_rules ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    def delete_alert_rule(self, rule_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            conn.commit()

    # --- Field Notes (CRUD) ---
    def create_field_note(self, author: str, note_text: str, category: str = "INSPECTION") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO field_notes (author, note_text, category, timestamp)
            VALUES (?, ?, ?, ?)
            """, (author, note_text, category, time.time()))
            conn.commit()
            return cursor.lastrowid

    def get_field_notes(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM field_notes ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def delete_field_note(self, note_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM field_notes WHERE id = ?", (note_id,))
            conn.commit()
