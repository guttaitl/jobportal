import os
import time
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2

# --------------------------------------------------
# LOAD ENV (ONLY FOR LOCAL)
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env.development")

# Load .env only if NOT running on Railway
if os.getenv("RAILWAY_ENVIRONMENT") is None:
    load_dotenv(ENV_PATH)

# --------------------------------------------------
# DATABASE URL
# --------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")
<<<<<<< HEAD
print("DATABASE_URL Loaded:", "YES" if DATABASE_URL else "NO")
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set")

# Fix old postgres:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Force psycopg2 driver for SQLAlchemy
if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

<<<<<<< HEAD
=======
print("📦 Using DATABASE_URL:", DATABASE_URL)

>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
# --------------------------------------------------
# CREATE ENGINE (with retry)
# --------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=5,
<<<<<<< HEAD
    max_overflow=10,
    connect_args={"sslmode": "require"}
=======
    max_overflow=10
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
)

Base = declarative_base()

# Retry DB connection (Railway DB may start slower)
for i in range(5):
    try:
        with engine.connect() as conn:
            print("✅ Database connected successfully")
            break
    except OperationalError as e:
        print(f"⏳ DB not ready (attempt {i+1}/5), retrying...")
        time.sleep(3)
else:
    print("❌ Could not connect to database after retries")

# --------------------------------------------------
# SESSION
# --------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# --------------------------------------------------
# DEPENDENCY
# --------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------------------------------------------------
# RAW PSYCOPG2 CONNECTION (if needed)
# --------------------------------------------------

def get_db_conn():
    # Remove +psycopg2 for psycopg2 compatibility
    clean_url = DATABASE_URL.replace("+psycopg2", "")
    result = urlparse(clean_url)

    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
<<<<<<< HEAD
        port=result.port,
        sslmode="require"
    )
=======
        port=result.port
    )
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
