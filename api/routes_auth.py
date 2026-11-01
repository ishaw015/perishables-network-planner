from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from psycopg.types.json import Jsonb
from .database import get_conn
from .schemas import TokenOut, UserOut
from .security import verify_password, create_token, current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_conn)):
    user = conn.execute("SELECT id, password_hash, role FROM users WHERE email = %s",
                        (form.username.strip().lower(),)).fetchone()
    if user is None or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    conn.execute("INSERT INTO audit_log (user_id, action, entity, entity_id, detail) VALUES (%s, 'login', 'user', %s, %s)",
                 (user["id"], user["id"], Jsonb({})))
    conn.commit()
    return TokenOut(access_token=create_token(user["id"], user["role"]))

@router.get("/me", response_model=UserOut)
def me(user=Depends(current_user)):
    return user