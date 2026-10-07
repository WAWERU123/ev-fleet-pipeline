import logging
import os
import time
from datetime import datetime
from uuid import UUID

import psycopg
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
logger = logging.getLogger("uvicorn.error")

app = FastAPI()


class Reading(BaseModel):
    event_id: UUID
    bus_id: str
    ts: datetime
    soc: float = Field(ge=0, le=100)
    battery_temp_c: float = Field(ge=-40, le=120)
    odometer_km: float = Field(ge=0)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def with_retries(func, *args, attempts=3, base_delay=1):
    """Call func; on failure wait 1s, then 2s, and try again. Raise after the last attempt."""
    for attempt in range(1, attempts + 1):
        try:
            return func(*args)
        except Exception as e:
            logger.warning("%s failed (attempt %s/%s): %s", func.__name__, attempt, attempts, e)
            if attempt == attempts:
                raise
            time.sleep(base_delay * 2 ** (attempt - 1))


def record_failure(event_id, step, error, attempts=3):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "insert into failed_calls (event_id, step, error, attempts) values (%s, %s, %s, %s)",
                (event_id, step, str(error)[:500], attempts),
            )
    except Exception as e:
        logger.error("Could not record failure for %s: %s", event_id, e)


def get_ambient_temp(lat, lon):
    response = requests.get(
        "https://api.open-meteo.com/v1/forecastx",
        params={"latitude": lat, "longitude": lon, "current": "temperature_2m"},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["current"]["temperature_2m"]


def create_work_order(reading, ambient):
    ambient_text = f"{ambient} C" if ambient is not None else "unknown"
    body = (
        f"**Bus:** {reading.bus_id}\n"
        f"**Rule:** high_battery_temp\n"
        f"**Battery temp:** {reading.battery_temp_c} C\n"
        f"**Ambient temp:** {ambient_text}\n"
        f"**SOC:** {reading.soc}%\n"
        f"**Location:** {reading.lat}, {reading.lon}\n"
        f"**Reading time:** {reading.ts.isoformat()}\n"
        f"**Event ID:** {reading.event_id}\n"
    )
    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": f"[ALERT] {reading.bus_id}: battery temp {reading.battery_temp_c} C",
            "body": body,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["html_url"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest(reading: Reading):
    with psycopg.connect(DATABASE_URL) as conn:
        result = conn.execute(
            """
            insert into telemetry
              (event_id, bus_id, ts, soc, battery_temp_c, odometer_km, lat, lon)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (event_id) do nothing
            """,
            (reading.event_id, reading.bus_id, reading.ts, reading.soc,
             reading.battery_temp_c, reading.odometer_km, reading.lat, reading.lon),
        )
        stored = result.rowcount == 1

        alert_raised = False
        if stored and reading.battery_temp_c > 45:
            conn.execute(
                """
                insert into alerts (event_id, bus_id, rule, value)
                values (%s, %s, %s, %s)
                on conflict (event_id, rule) do nothing
                """,
                (reading.event_id, reading.bus_id, "high_battery_temp", reading.battery_temp_c),
            )
            alert_raised = True

    # The alert is now committed. Everything below is best-effort.
    ambient = None
    issue_url = None
    if alert_raised:
        try:
            ambient = with_retries(get_ambient_temp, reading.lat, reading.lon)
            with psycopg.connect(DATABASE_URL) as conn:
                conn.execute(
                    "update alerts set ambient_temp_c = %s where event_id = %s and rule = %s",
                    (ambient, reading.event_id, "high_battery_temp"),
                )
        except Exception as e:
            ambient = None
            record_failure(reading.event_id, "weather", e)

        try:
            issue_url = with_retries(create_work_order, reading, ambient)
            with psycopg.connect(DATABASE_URL) as conn:
                conn.execute(
                    "update alerts set issue_url = %s where event_id = %s and rule = %s",
                    (issue_url, reading.event_id, "high_battery_temp"),
                )
        except Exception as e:
            issue_url = None
            record_failure(reading.event_id, "work_order", e)

    return {
        "event_id": reading.event_id,
        "status": "stored" if stored else "duplicate",
        "alert": alert_raised,
        "ambient_temp_c": ambient,
        "issue_url": issue_url,
    }
