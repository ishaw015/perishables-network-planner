import os, pathlib
import psycopg
from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"]
statements = [s.strip() for s in pathlib.Path("db/schema.sql").read_text().split(";") if s.strip()]

with psycopg.connect(url) as conn:
    for s in statements:
        conn.execute(s)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY 1").fetchall()
print("tables:", [t[0] for t in tables])