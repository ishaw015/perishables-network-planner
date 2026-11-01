import datetime as dt
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from .config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_MINUTES
from .database import get_conn

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_token(user_id: int, role: str) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=ACCESS_TOKEN_MINUTES)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)

def current_user(token: str = Depends(oauth2), conn=Depends(get_conn)):
    err = HTTPException(status_code=401, detail="Invalid or expired token",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise err
    user = conn.execute("SELECT id, email, role FROM users WHERE id = %s", (user_id,)).fetchone()
    if user is None:
        raise err
    return user