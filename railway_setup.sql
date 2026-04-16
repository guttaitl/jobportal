-- ============================================
-- RAILWAY POSTGRESQL SETUP - RESUME MATCHING SYSTEM
-- Optimized for 50K+ Resumes
-- Version: 1.0
-- ============================================

-- 1. ENABLE EXTENSIONS (Must run first)
-- ============================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Verify extensions
SELECT * FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');

-- 2. OPTIMIZE RAILWAY POSTGRES SETTINGS
-- ============================================
-- These settings are optimized for Railway's typical 2-4GB RAM instances
ALTER SYSTEM SET work_mem = '128MB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET effective_cache_size = '2GB';
ALTER SYSTEM SET max_parallel_workers = 4;
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;
ALTER SYSTEM SET random_page_cost = 1.1;  -- For SSD storage on Railway

-- Reload config
SELECT pg_reload_conf();

-- 3. CREATE MATERIALIZED VIEW FOR FAST SEARCH
-- ============================================
DROP MATERIALIZED VIEW IF EXISTS resume_metadata CASCADE;

CREATE MATERIALIZED VIEW resume_metadata AS
WITH parsed_resumes AS (
    SELECT 
        s.id,
        s.full_name,
        s.email,
        s.resume_text,
        s.embedding,
        LOWER(s.resume_text) AS resume_lower,
        
        -- Extract years of experience (handles: "5 years", "5+ years", "5 yrs")
        COALESCE(
            (regexp_matches(LOWER(s.resume_text), '(\d+)\s*\+?\s*(?:year|yr)s?', 'i'))[1]::int,
            (regexp_matches(LOWER(s.resume_text), '(\d+)\+?', 'i'))[1]::int,
            0
        ) AS years_experience,
        
        -- Extract skills array
        array_agg(DISTINCT word) FILTER (WHERE word IS NOT NULL) AS skills
        
    FROM submissions s
    LEFT JOIN LATERAL (
        SELECT unnest(regexp_split_to_array(LOWER(s.resume_text), '\W+')) AS word
    ) words ON length(word) BETWEEN 3 AND 20 
        AND word !~ '^(and|the|for|are|you|this|that|with|from|have|has|will|job|role|work|year|years|experience|company|team)$'
    GROUP BY s.id, s.full_name, s.email, s.resume_text, s.embedding
)
SELECT 
    pr.*,
    
    -- Role detection
    CASE 
        WHEN resume_lower ~* '(react|angular|vue|frontend|ui/ux|css|html)' 
             AND resume_lower ~* '(node|python|java|api|backend|aws)' 
            THEN 'Full Stack'
        WHEN resume_lower ~* '(react|angular|vue|frontend|ui/ux|css|html|typescript)' 
            THEN 'Frontend'
        WHEN resume_lower ~* '(node|python|java|go|spring|api|backend|aws|docker|kubernetes)' 
            THEN 'Backend'
        WHEN resume_lower ~* '(mobile|ios|android|swift|flutter|react native)' 
            THEN 'Mobile'
        WHEN resume_lower ~* '(data|machine learning|ml|ai|tensorflow|pytorch)' 
            THEN 'Data/ML'
        ELSE 'General'
    END AS detected_role,
    
    -- Boolean flags for common skills (fast filtering)
    resume_lower ~* '\yreact\y' AS has_react,
    resume_lower ~* '\ypython\y' AS has_python,
    resume_lower ~* '\ynode\y' AS has_node,
    resume_lower ~* '\yaws\y' AS has_aws,
    resume_lower ~* '\ysql\y' AS has_sql

FROM parsed_resumes pr;

-- 4. CREATE INDEXES (Critical for Performance)
-- ============================================

-- Unique index for concurrent refresh (REQUIRED)
CREATE UNIQUE INDEX idx_resume_metadata_id ON resume_metadata(id);

-- HNSW Vector Index (Fast AI similarity search)
CREATE INDEX idx_resume_metadata_embedding_hnsw 
ON resume_metadata 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- GIN Index for text search (Fast ILIKE queries)
CREATE INDEX idx_resume_metadata_trgm 
ON resume_metadata 
USING gin(resume_lower gin_trgm_ops);

-- GIN Index for skills array
CREATE INDEX idx_resume_metadata_skills 
ON resume_metadata 
USING gin(skills);

-- Regular indexes for filtering
CREATE INDEX idx_resume_metadata_role ON resume_metadata(detected_role);
CREATE INDEX idx_resume_metadata_exp ON resume_metadata(years_experience);

-- Composite index for common queries
CREATE INDEX idx_resume_metadata_role_exp 
ON resume_metadata(detected_role, years_experience) 
INCLUDE (full_name, email);

-- 5. CREATE MAIN SEARCH FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION hybrid_match_resumes(
    job_embedding vector,
    job_text text,
    result_limit integer DEFAULT 20,
    min_vector_score float DEFAULT 0.6
)
RETURNS TABLE (
    id integer,
    full_name text,
    email text,
    vector_score float,
    text_score float,
    final_score float,
    confidence text,
    role_match text,
    experience_match text,
    years_exp integer,
    matched_skills text[],
    detected_role text
) AS $$
DECLARE
    v_job_years integer;
    v_job_role text;
    v_job_skills text[];
BEGIN
    -- Parse job text once
    v_job_years := COALESCE(
        (regexp_matches(LOWER(job_text), '(\d+)\s*\+?\s*(?:year|yr)s?', 'i'))[1]::int, 
        0
    );
    
    v_job_role := CASE 
        WHEN job_text ~* '(react|angular|vue).*(node|python|java|api)' OR 
             job_text ~* '(node|python|java|api).*(react|angular|vue)' 
            THEN 'Full Stack'
        WHEN job_text ~* '(react|angular|vue|frontend|ui)' THEN 'Frontend'
        WHEN job_text ~* '(python|java|node|api|backend)' THEN 'Backend'
        ELSE 'General'
    END;
    
    -- Extract job skills
    SELECT array_agg(DISTINCT skill) INTO v_job_skills
    FROM unnest(regexp_split_to_array(LOWER(job_text), '\W+')) AS skill
    WHERE length(skill) BETWEEN 3 AND 20
      AND skill !~ '^(and|the|for|are|you|this|that|with|from|have|has|will|job|role|work|year|years)$';

    RETURN QUERY
    WITH vector_matches AS (
        -- Fast vector search using HNSW index
        SELECT 
            rm.id,
            rm.full_name,
            rm.email,
            rm.years_experience,
            rm.detected_role,
            rm.skills,
            rm.resume_lower,
            1 - (rm.embedding <=> job_embedding) AS vec_score
        FROM resume_metadata rm
        WHERE 1 - (rm.embedding <=> job_embedding) > min_vector_score
        ORDER BY rm.embedding <=> job_embedding
        LIMIT 150
    ),
    text_matches AS (
        -- Skill matching using pre-extracted skills
        SELECT 
            vm.id,
            COUNT(DISTINCT js) AS skill_count,
            array_agg(DISTINCT js) AS matched
        FROM vector_matches vm
        CROSS JOIN unnest(v_job_skills) AS js
        WHERE vm.resume_lower ILIKE '%' || js || '%'
        GROUP BY vm.id
    )
    SELECT 
        vm.id,
        vm.full_name,
        vm.email,
        ROUND(vm.vec_score::numeric, 3),
        ROUND(COALESCE(tm.skill_count, 0)::numeric * 0.5, 3),
        ROUND((
            CASE 
                WHEN vm.vec_score > 0.8 THEN 0.7 * vm.vec_score + 0.3 * LEAST(COALESCE(tm.skill_count, 0) * 0.1, 0.5)
                ELSE 0.5 * vm.vec_score + 0.5 * LEAST(COALESCE(tm.skill_count, 0) * 0.1, 0.5)
            END
        )::numeric, 3),
        CASE 
            WHEN (0.7 * vm.vec_score + 0.3 * LEAST(COALESCE(tm.skill_count, 0) * 0.1, 0.5)) > 0.75 THEN 'HIGH'
            WHEN (0.7 * vm.vec_score + 0.3 * LEAST(COALESCE(tm.skill_count, 0) * 0.1, 0.5)) > 0.55 THEN 'MEDIUM'
            ELSE 'LOW'
        END,
        CASE 
            WHEN v_job_role = vm.detected_role THEN 'Strong match'
            WHEN v_job_role = 'Full Stack' OR vm.detected_role = 'Full Stack' THEN 'Good match'
            ELSE 'Weak match'
        END,
        CASE 
            WHEN v_job_years = 0 THEN 'Not specified'
            WHEN vm.years_experience >= v_job_years THEN 'Good fit'
            WHEN vm.years_experience >= v_job_years - 2 THEN 'Close match'
            ELSE 'Underqualified'
        END,
        vm.years_experience,
        COALESCE(tm.matched, ARRAY[]::text[]),
        vm.detected_role
    FROM vector_matches vm
    LEFT JOIN text_matches tm ON tm.id = vm.id
    ORDER BY 6 DESC  -- Order by final_score
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- 6. CREATE REFRESH FUNCTION
-- ============================================
CREATE OR REPLACE FUNCTION refresh_resume_metadata()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY resume_metadata;
    ANALYZE resume_metadata;
END;
$$ LANGUAGE plpgsql;

-- 7. INITIAL DATA LOAD
-- ============================================
-- Populate the materialized view for the first time
REFRESH MATERIALIZED VIEW resume_metadata;

-- Update statistics for query planner
ANALYZE resume_metadata;

-- Verify setup
SELECT 
    'Setup Complete!' as status,
    COUNT(*) as total_resumes,
    pg_size_pretty(pg_total_relation_size('resume_metadata')) as storage_used
FROM resume_metadata;