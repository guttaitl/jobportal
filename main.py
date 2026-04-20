# ==========================================================
# HIRING CIRCLE API
# ==========================================================

import os
import logging
import threading
import warnings
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

# ==========================================================
# LOAD ENV FIRST
# ==========================================================

print("🔥 New MAIN FILE LOADED")

env_path = Path(__file__).resolve().parent / ".env"
print(f"🔍 Looking for .env at: {env_path}")
print(f"🔍 File exists: {env_path.exists()}")

if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"✅ .env loaded from: {env_path}")
else:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"✅ .env loaded from: {env_path}")
    else:
        print("⚠️ WARNING: .env file not found!")

print("🔍 ENV FILE LOADED")
print(f"🔍 DATABASE_URL: {os.getenv('DATABASE_URL')}")

# ==========================================================
# ENV VALIDATION
# ==========================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is missing.")

print("✅ Environment loaded")

warnings.filterwarnings("ignore", category=FutureWarning)

# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(level=logging.INFO)

for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access", "httpx"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# ==========================================================
# IMPORTS
# ==========================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.db import engine
from api.models import Base

# Routers
from api.auth_routes import router as auth_router
from routers.verify import router as verify_router
from api.routes.job_routes import router as job_router
from api.routes.employer_routes import router as employer_router
from api.routes.password_routes import router as password_router
from api.routes.resume_routes import router as resume_router
from api.routes.ai_match_routes import router as ai_match_router
from api.routes.vector_search_routes import router as vector_search_router
from api.routes.match_routes import router as match_router

# Services
from services.resume_indexer import start_pipeline_background, start_scheduler

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(
    title="Hiring Circle API",
    version="2.3.0",
    description="AI-Powered Recruitment Platform API",
)

class ForceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)

app.add_middleware(ForceHTTPSMiddleware)

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# ROUTES
# ==========================================================

app.include_router(auth_router, prefix="/api")
app.include_router(verify_router, prefix="/api")
app.include_router(job_router, prefix="/api")
app.include_router(employer_router, prefix="/api")
app.include_router(password_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(ai_match_router, prefix="/api")
app.include_router(vector_search_router, prefix="/api")
app.include_router(match_router, prefix="/api")

print("✅ API routes registered")

# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/")
def root():
    return {
        "message": "Hiring Circle API",
        "version": "2.3.0",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {
        "version": "2.3.0",
        "env": os.getenv("RAILWAY_ENVIRONMENT"),
        "status": "running"
    }

# ==========================================================
# STATIC FILES
# ==========================================================

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# ==========================================================
# STARTUP EVENTS
# ==========================================================

@app.on_event("startup")
def startup():
    print("🚀 Starting application...")

    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables ensured")
    except Exception as e:
        print(f"❌ Database error: {e}")
        raise

    # Background tasks
    start_pipeline_background()
    threading.Thread(target=start_scheduler, daemon=True).start()

    print("🚀 Application started successfully")