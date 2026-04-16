-- =========================================================
-- PGVECTOR SETUP - AI Resume Search System
-- =========================================================

-- 1. ENABLE PGVECTOR EXTENSION
-- Run this first (requires superuser or appropriate permissions)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. ADD EMBEDDING COLUMN TO SUBMISSIONS TABLE
-- 1536 dimensions = OpenAI text-embedding-3-small
ALTER TABLE submissions 
ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- 3. CREATE HNSW INDEX FOR FAST VECTOR SEARCH
-- HNSW = Hierarchical Navigable Small World (best for high-dim vectors)
-- ef_construction = 64 (build quality), m = 16 (connections per node)
CREATE INDEX IF NOT EXISTS idx_submissions_embedding_hnsw
ON submissions USING hnsw (embedding vector_cosine_ops)
WITH (ef_construction = 64, m = 16);

-- 4. CREATE GIN INDEX FOR HYBRID SEARCH (text + vector)
-- For when you need to combine vector similarity with text filters
CREATE INDEX IF NOT EXISTS idx_submissions_embedding_gin
ON submissions USING gin (embedding vector_cosine_ops);

-- 5. CREATE FUNCTION FOR VECTOR SEARCH (OPTIONAL - for raw SQL queries)
CREATE OR REPLACE FUNCTION search_resumes_by_vector(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    submission_id uuid,
    full_name text,
    job_id text,
    match_score float,
    similarity float
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.submission_id,
        s.full_name,
        s.job_id,
        s.match_score,
        1 - (s.embedding <=> query_embedding) AS similarity
    FROM submissions s
    WHERE s.embedding IS NOT NULL
      AND 1 - (s.embedding <=> query_embedding) > match_threshold
    ORDER BY s.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 6. CREATE FUNCTION FOR HYBRID SEARCH (text + vector combined)
CREATE OR REPLACE FUNCTION hybrid_search_resumes(
    query_embedding vector(1536),
    query_text text DEFAULT NULL,
    vector_weight float DEFAULT 0.7,
    text_weight float DEFAULT 0.3,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    submission_id uuid,
    full_name text,
    job_id text,
    semantic_score float,
    text_score float,
    combined_score float
) AS $$
BEGIN
    RETURN QUERY
    WITH vector_scores AS (
        SELECT 
            s.submission_id,
            s.full_name,
            s.job_id,
            s.resume_text,
            1 - (s.embedding <=> query_embedding) AS similarity
        FROM submissions s
        WHERE s.embedding IS NOT NULL
        ORDER BY s.embedding <=> query_embedding
        LIMIT match_count * 3
    ),
    text_scores AS (
        SELECT 
            s.submission_id,
            CASE 
                WHEN query_text IS NULL THEN 0
                WHEN s.resume_text ILIKE '%' || query_text || '%' THEN 1.0
                WHEN s.full_name ILIKE '%' || query_text || '%' THEN 0.8
                ELSE 0
            END AS text_match
        FROM submissions s
        WHERE query_text IS NOT NULL
    )
    SELECT 
        vs.submission_id,
        vs.full_name,
        vs.job_id,
        vs.similarity AS semantic_score,
        COALESCE(ts.text_match, 0) AS text_score,
        (vs.similarity * vector_weight + COALESCE(ts.text_match, 0) * text_weight) AS combined_score
    FROM vector_scores vs
    LEFT JOIN text_scores ts ON vs.submission_id = ts.submission_id
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 7. VERIFY SETUP
SELECT 
    'pgvector extension installed' AS status,
    COUNT(*) AS total_resumes,
    COUNT(embedding) AS resumes_with_embeddings
FROM submissions;
