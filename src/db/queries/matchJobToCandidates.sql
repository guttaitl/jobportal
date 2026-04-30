WITH job_input AS (
    SELECT 
        (:job_embedding)::vector AS embedding,
        LOWER(:job_text) AS job_text,

        -- Extract job experience
        COALESCE(
            (
                SELECT (regexp_matches(LOWER(:job_text), '(\d+)\s*\+?\s*year'))[1]::int
                LIMIT 1
            ),
            0
        ) AS job_experience
),

-- 🔥 STEP 1: VECTOR FILTER (FAST FIRST CUT)
vector_scores AS (
    SELECT 
        c.id,
        1 - (c.embedding <=> ji.embedding) AS vector_score
    FROM submissions c
    CROSS JOIN job_input ji
    ORDER BY c.embedding <=> ji.embedding
    LIMIT 120
),

-- 🔥 STEP 2: PHRASE EXTRACTION (UNIGRAM + BIGRAM + TRIGRAM)
job_skills AS (

    -- Unigrams
    SELECT DISTINCT word
    FROM (
        SELECT unnest(regexp_split_to_array(job_text, '\W+')) AS word
        FROM job_input
    ) t
    WHERE length(word) BETWEEN 3 AND 25

    UNION

    -- Bigrams
    SELECT DISTINCT (w1 || ' ' || w2)
    FROM (
        SELECT words[i] AS w1, words[i+1] AS w2
        FROM (
            SELECT regexp_split_to_array(job_text, '\W+') AS words
            FROM job_input
        ) s,
        generate_subscripts(words, 1) g(i)
        WHERE i < array_length(words, 1)
    ) t
    WHERE length(w1) > 2 AND length(w2) > 2

    UNION

    -- Trigrams
    SELECT DISTINCT (w1 || ' ' || w2 || ' ' || w3)
    FROM (
        SELECT words[i] AS w1, words[i+1] AS w2, words[i+2] AS w3
        FROM (
            SELECT regexp_split_to_array(job_text, '\W+') AS words
            FROM job_input
        ) s,
        generate_subscripts(words, 1) g(i)
        WHERE i < array_length(words, 1) - 1
    ) t
    WHERE length(w1) > 2 AND length(w2) > 2 AND length(w3) > 2
),

-- 🔥 STEP 3: CLEAN + PRIORITIZE SKILLS
filtered_skills AS (
    SELECT word
    FROM (
        SELECT DISTINCT 
            word,
            CASE 
                WHEN word LIKE '% %' THEN 2
                ELSE 1
            END AS priority,
            length(word) AS word_len
        FROM job_skills
        WHERE word ~ '^[a-z ]+$'
        AND length(word) <= 30
        AND word NOT IN (
            'and','the','with','for','are','you','this','that','from','have','has',
            'job','role','years','year','experience','developer','engineer','work',
            'using','will','our','your','all','any','who','what','where','when'
        )
    ) t
    ORDER BY priority DESC, word_len DESC
    LIMIT 40
)

-- 🔥 STEP 4: TEXT MATCHING (BALANCED + FAST)
text_scores AS (
    SELECT 
        c.id,

        LEAST(COUNT(DISTINCT fs.word), 6) * 0.4 AS skill_score,

        ARRAY_AGG(DISTINCT fs.word) AS matched_skills

    FROM submissions c
    JOIN vector_scores vs ON vs.id = c.id

    JOIN filtered_skills fs 
        ON (
            c.resume_text ILIKE '%' || fs.word || '%'
        OR (
            length(fs.word) > 4
            AND word_similarity(fs.word, lower(c.resume_text)) > 0.5
        )
                )

    GROUP BY c.id
),

-- 🔥 STEP 5: JOB ROLE DETECTION (DYNAMIC)
job_role AS (
    SELECT 
        CASE 
            WHEN COUNT(*) FILTER (
                WHERE word ~ '(front|ui)'
            ) > 0
            AND COUNT(*) FILTER (
                WHERE word ~ '(back|api|service|spring)'
            ) > 0
                THEN 'Full Stack'

            WHEN COUNT(*) FILTER (
                WHERE word ~ '(front|ui)'
            ) > 0
                THEN 'Frontend'

            WHEN COUNT(*) FILTER (
                WHERE word ~ '(api|back|service|spring)'
            ) > 0
                THEN 'Backend'

            ELSE 'General'
        END AS job_role
    FROM filtered_skills
),

-- 🔥 STEP 6: RESUME EXPERIENCE + ROLE
resume_exp AS (
    SELECT 
        c.id,

        COALESCE(
            (
                SELECT (regexp_matches(LOWER(c.resume_text), '(\d+)\s*\+?\s*year'))[1]::int
                LIMIT 1
            ),
            0
        ) AS resume_experience,

        CASE 
            WHEN c.resume_text ILIKE '%front%' AND c.resume_text ILIKE '%api%' THEN 'Full Stack'
            WHEN c.resume_text ILIKE '%front%' THEN 'Frontend'
            WHEN c.resume_text ILIKE '%api%' OR c.resume_text ILIKE '%service%' THEN 'Backend'
            ELSE 'General'
        END AS resume_role

    FROM submissions c
    JOIN vector_scores vs ON vs.id = c.id
),

-- 🔥 STEP 7: FINAL COMBINATION
combined AS (
    SELECT 
        c.id,
        c.full_name,

        re.resume_experience,
        ji.job_experience,
        jr.job_role,
        re.resume_role,

        (re.resume_experience - ji.job_experience) AS experience_gap,

        CASE 
            WHEN ji.job_experience = 0 THEN 'Not specified'
            WHEN re.resume_experience >= ji.job_experience THEN 'Good fit'
            WHEN re.resume_experience >= ji.job_experience - 2 THEN 'Close match'
            ELSE 'Underqualified'
        END AS experience_match,

        CASE 
            WHEN jr.job_role = re.resume_role THEN 'Strong match'
            WHEN jr.job_role = 'Full Stack' THEN 'Good match'
            WHEN re.resume_role = 'Full Stack' THEN 'Good match'
            ELSE 'Weak match'
        END AS role_match,

        COALESCE(ts.matched_skills, ARRAY[]::text[]) AS matched_skills,
        vs.vector_score,
        COALESCE(ts.skill_score, 0) AS text_score,

        -- ✅ BALANCED SCORING
        (0.6 * vs.vector_score + 0.4 * COALESCE(ts.skill_score, 0)) AS final_score

    FROM vector_scores vs
    JOIN submissions c ON c.id = vs.id
    JOIN resume_exp re ON re.id = c.id
    CROSS JOIN job_input ji
    CROSS JOIN job_role jr
    LEFT JOIN text_scores ts ON ts.id = c.id
)

-- 🔥 FINAL OUTPUT
SELECT *,
    CASE 
        WHEN final_score > 0.75 THEN 'HIGH'
        WHEN final_score > 0.55 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS confidence,

    CASE 
        WHEN final_score > 0.75 THEN 'Strong match'
        WHEN final_score > 0.55 THEN 'Moderate match'
        ELSE 'Weak match'
    END AS match_reason

FROM combined
ORDER BY final_score DESC
LIMIT 20;