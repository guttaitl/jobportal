# ==========================================================
# HIRING CIRCLE USA
# ==========================================================
import os
import logging
import threading
import warnings
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from api.db import engine
from api.models import Base

# ==========================================================
# LOAD ENV
# ==========================================================

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

warnings.filterwarnings("ignore", category=FutureWarning)
logging.basicConfig(level=logging.INFO)

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(
    title="Hiring Circle API",
    version="2.3.0",
    description="AI-Powered Recruitment Platform API",
)

# Force HTTPS (optional)
class ForceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.scope["scheme"] = "https"
        return await call_next(request)

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://hiringcircleusa.vercel.app",
        "https://hiringcircle.us",
        "https://www.hiringcircle.us",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# ROUTES
# ==========================================================

from api.auth_routes import router as auth_router
from routers.verify import router as verify_router
from api.routes.job_routes import router as job_router
from api.routes.employer_routes import router as employer_router
from api.routes.password_routes import router as password_router
from api.routes.resume_routes import router as resume_router
from api.routes.ai_match_routes import router as ai_match_router
from api.routes.vector_search_routes import router as vector_search_router
from api.routes.match_routes import router as match_router

app.include_router(auth_router, prefix="/api")
app.include_router(verify_router, prefix="/api")
app.include_router(job_router, prefix="/api")
app.include_router(employer_router, prefix="/api")
app.include_router(password_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(ai_match_router, prefix="/api")
app.include_router(vector_search_router, prefix="/api")
app.include_router(match_router, prefix="/api")

# ==========================================================
# HEALTH
# ==========================================================

@app.get("/")
def root():
    return {"message": "Hiring Circle API", "version": "2.3.0"}

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
# STARTUP
# ==========================================================

from services.resume_indexer import start_pipeline_background, start_scheduler

@app.on_event("startup")
def startup():
    print("🚀 Starting application...")

    Base.metadata.create_all(bind=engine)
    print("✅ Database ready")

    start_pipeline_background()
    threading.Thread(target=start_scheduler, daemon=True).start()

    print("🚀 Application started")