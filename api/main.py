import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from . import database
from .routes_auth import router as auth_router
from .routes_plans import router as plans_router

log = logging.getLogger("api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.pool.open()
    yield
    database.pool.close()

app = FastAPI(title="Perishables Network Planner API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(plans_router)

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}