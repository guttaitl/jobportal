#!/usr/bin/env python3
"""
Database table creation script for Hiring Circle platform
Includes: pgvector extension, vector(1536) embeddings, HNSW indexes, full-text search
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Always try loading .env (safe)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set")

# Fix old postgres:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("📦 Using DATABASE_URL:", DATABASE_URL)

def create_tables():
    """Create all required database tables with pgvector support"""
    
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        
        # ============================================================
        # 1. EXTENSIONS
        # ============================================================
        
        # Enable pgvector for vector similarity search
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        
        # Enable pg_trgm for trigram/fuzzy text search (optional but useful)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        
        print("✅ Extensions enabled (vector, pg_trgm)")
        
        # ============================================================
        # 2. TABLES
        # ============================================================
        
        # Create usersdata table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usersdata (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                contact VARCHAR(50),
                company VARCHAR(255),
                role VARCHAR(100),
                password_hash TEXT NOT NULL,
                verified BOOLEAN DEFAULT FALSE,
                verification_token VARCHAR(255),
                created_date TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP
            )
        """))
        
        # Create job_postings table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_postings (
                id SERIAL PRIMARY KEY,
                jobid VARCHAR(10) UNIQUE NOT NULL,
                created_date DATE,
                job_title TEXT NOT NULL,
                job_description TEXT,
                location TEXT,
                experience TEXT,
                skills TEXT,
                employment_type TEXT,
                salary TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                client_name TEXT,
                work_authorization TEXT DEFAULT 'Any',
                visa_transfer TEXT DEFAULT 'No',
                posted_by TEXT,
                applicants_count INTEGER DEFAULT 0
            )
        """))
        
        # Create candidate_resumes table (main resume storage)
        # NOTE: embedding changed from JSONB → vector(1536) for pgvector similarity search
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS candidate_resumes (
                id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(50),
                file_path TEXT,
                original_file_name TEXT,
                resume_hash VARCHAR(64),
                resume_text TEXT,
                formatted_html TEXT,
                full_name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                skills TEXT,
                experience TEXT,
                location TEXT,
                visa_status TEXT,
                embedding vector(1536),
                embedding_model VARCHAR(50),
                parse_hash VARCHAR(64),
                parsed_successfully BOOLEAN DEFAULT FALSE,
                parse_error TEXT,
                parser_version VARCHAR(50),
                parsing_confidence_score DECIMAL(5,4),
                last_parsed_at TIMESTAMP,
                indexed_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP
            )
        """))
        
        # Create search_vector column for full-text search
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'candidate_resumes' 
                    AND column_name = 'search_vector'
                ) THEN
                    ALTER TABLE candidate_resumes ADD COLUMN search_vector tsvector;
                END IF;
            END $$;
        """))
        
        # Create function to update search_vector
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION update_resume_search_vector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.search_vector := 
                    setweight(to_tsvector('english', COALESCE(NEW.resume_text, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.full_name, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE(NEW.skills, '')), 'C') ||
                    setweight(to_tsvector('english', COALESCE(NEW.experience, '')), 'C');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        
        # Create trigger for search_vector updates
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger 
                    WHERE tgname = 'trigger_update_resume_search_vector'
                ) THEN
                    CREATE TRIGGER trigger_update_resume_search_vector
                    BEFORE INSERT OR UPDATE ON candidate_resumes
                    FOR EACH ROW
                    EXECUTE FUNCTION update_resume_search_vector();
                END IF;
            END $$;
        """))
        
        # Create submissions table (for job applications / resume processing pipeline)
        # FIXED: Added all columns your app actually inserts + vector(1536) embedding
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS submissions (
                submission_id VARCHAR(50) PRIMARY KEY,
                candidate_name VARCHAR(255),
                full_name VARCHAR(255),
                resume_text TEXT,
                embedding vector(1536),
                resume_hash VARCHAR(64),
                job_id VARCHAR(50),
                skills TEXT,
                city VARCHAR(100),
                state VARCHAR(100),
                job_title VARCHAR(255),
                formatted_html TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                
                -- Optional scoring/matching columns (nullable for backward compat)
                resume_id VARCHAR(50),
                user_id VARCHAR(50),
                job_description TEXT,
                match_score DECIMAL(5,2),
                semantic_similarity DECIMAL(5,4),
                score_breakdown JSONB,
                fit_summary TEXT,
                confidence_band VARCHAR(20),
                final_recommendation TEXT,
                skill_matrix JSONB,
                fabrication_observations TEXT,
                scoring_status VARCHAR(50) DEFAULT 'PENDING',
                processed_at TIMESTAMP,
                report_path TEXT
            )
        """))
        
        # Create scoring_queue table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scoring_queue (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'PENDING',
                attempts INTEGER DEFAULT 0,
                locked_at TIMESTAMP,
                next_attempt_at TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        
        # Create job_matching_queue table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_matching_queue (
                id SERIAL PRIMARY KEY,
                job_title TEXT,
                job_description TEXT,
                poster_email TEXT,
                resume_id VARCHAR(50),
                status VARCHAR(50) DEFAULT 'PENDING',
                attempts INTEGER DEFAULT 0,
                locked_at TIMESTAMP,
                locked_by VARCHAR(255),
                next_attempt_at TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        
        # Create ai_matches table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_matches (
                match_id VARCHAR(50) PRIMARY KEY,
                job_id VARCHAR(10),
                resume_id VARCHAR(20),
                match_score DECIMAL(5,2),
                skill_match_score DECIMAL(5,2),
                experience_match_score DECIMAL(5,2),
                overall_fit VARCHAR(20),
                reasoning TEXT,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES job_postings(jobid)
            )
        """))
        
        # Create job_applications table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_applications (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(10) NOT NULL,
                resume_id VARCHAR(20) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                match_score DECIMAL(5,2),
                applied_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES job_postings(jobid)
            )
        """))
        
        # Create password_reset_tokens table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(email)
            )
        """))
        
        # ============================================================
        # 3. INDEXES
        # ============================================================
        
        # --- Standard B-tree indexes ---
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_posted_by ON job_postings(posted_by)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON job_postings(created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_candidate_resumes_email ON candidate_resumes(email)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_candidate_resumes_created_at ON candidate_resumes(created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_candidate_resumes_user_id ON candidate_resumes(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_candidate_resumes_parsed ON candidate_resumes(parsed_successfully)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_submissions_job_id ON submissions(job_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_submissions_resume_id ON submissions(resume_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(scoring_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_submissions_hash ON submissions(resume_hash)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scoring_queue_status ON scoring_queue(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_matching_queue_status ON job_matching_queue(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_matches_job ON ai_matches(job_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_matches_resume ON ai_matches(resume_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_applications_job ON job_applications(job_id)"))
        
        # --- Full-text search GIN index ---
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_candidate_resumes_search_vector 
            ON candidate_resumes USING GIN(search_vector)
        """))
        
        # --- Vector similarity search indexes (HNSW = fastest for high-dim vectors) ---
        # HNSW index on candidate_resumes embedding for cosine similarity
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_candidate_resumes_embedding_hnsw 
            ON candidate_resumes USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        
        # HNSW index on submissions embedding for cosine similarity
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_submissions_embedding_hnsw 
            ON submissions USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        
        # --- Trigram index for fuzzy text search (optional but fast for name matching) ---
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_candidate_resumes_name_trgm 
            ON candidate_resumes USING gin (full_name gin_trgm_ops)
        """))
        
        conn.commit()
        
        print("✅ All tables & indexes created successfully!")
        print("📊 Tables:")
        print("   - usersdata")
        print("   - job_postings")
        print("   - candidate_resumes  (vector(1536) + HNSW index + full-text search)")
        print("   - submissions        (vector(1536) + HNSW index)")
        print("   - scoring_queue")
        print("   - job_matching_queue")
        print("   - ai_matches")
        print("   - job_applications")
        print("   - password_reset_tokens")
        print("🔍 Indexes: B-tree, GIN (full-text), HNSW (vector similarity), Trigram")

if __name__ == "__main__":
    create_tables()