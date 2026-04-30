# ==========================================================
# HIRING CIRCLE USA
# ==========================================================
import os
import logging
import threading
import warnings
from pathlib import Path
from dotenv import load_dotenv

# ==========================================================
# HARD SILENCE (ADD THIS)
# ==========================================================
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.ERROR)

for lib in [
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "httpx",
    "urllib3",
    "transformers",
    "sentence_transformers",
    "huggingface_hub",
    "faiss",
]:
    logging.getLogger(lib).setLevel(logging.ERROR)

# ==========================================================
# LOAD ENV (MUST COME BEFORE EVERYTHING)
# ==========================================================

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

# HF cache
os.environ["HF_HOME"] = os.getenv("HF_HOME", "./.cache/huggingface")
os.environ["TRANSFORMERS_CACHE"] = os.getenv("TRANSFORMERS_CACHE", "./.cache/huggingface")

# ==========================================================
# CORE IMPORTS
# ==========================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from transformers.utils import logging as hf_logging

from api.db import engine
from api.models import Base

# Silence HF internals
hf_logging.set_verbosity_error()

# ==========================================================
# CLEAN LOGGER (YOUR ONLY OUTPUT)
# ==========================================================

def log(msg):
    print(f"🚀 {msg}")

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
from sentence_transformers import SentenceTransformer

_model = None

def load_model():
    global _model
    if _model is None:
        log("Loading AI model")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        log("AI model loaded")
    return _model

@app.on_event("startup")
async def startup():
    log("Starting application")

    Base.metadata.create_all(bind=engine)
    log("Database ready")

    load_model()

    start_pipeline_background()
    threading.Thread(target=start_scheduler, daemon=True).start()
    log("Resume pipeline started")

    log("Application ready")