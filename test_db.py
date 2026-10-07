import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    row = conn.execute("select count(*) from telemetry").fetchone()
    print("Connected. Rows in telemetry:", row[0])