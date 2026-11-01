import os, sys, getpass
import bcrypt
import psycopg
from dotenv import load_dotenv

load_dotenv()
email = input("email: ").strip().lower()
if "@" not in email or len(email) > 200:
    sys.exit("please enter a valid email")
password = getpass.getpass("password (8-64 characters): ")
if not 8 <= len(password) <= 64:
    sys.exit("password must be 8-64 characters")
role = input("role [planner/admin] (default planner): ").strip() or "planner"
if role not in ("planner", "admin"):
    sys.exit("role must be planner or admin")
pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    conn.execute("INSERT INTO users (email, password_hash, role) VALUES (%s, %s, %s)", (email, pw_hash, role))
print("created", email, "as", role)