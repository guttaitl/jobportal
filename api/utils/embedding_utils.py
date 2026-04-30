"""
Embedding Pipeline - OpenAI text-embedding-3-small
Generates vector embeddings for semantic search
"""
print("⚡Embedding Uutils Loaded......")
import os
import asyncio
from typing import List, Optional
from openai import AsyncOpenAI
import logging

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# Model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 100  # OpenAI allows up to 2048 texts per batch


async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate a single embedding for text.
    
    Args:
        text: The text to embed (resume content, job description, etc.)
    
    Returns:
        List of 1536 floats, or None if failed
    """
    if not text or not text.strip():
        return None
    
    try:
        # Truncate if too long (OpenAI has token limits)
        truncated_text = text[:8000]  # Safe limit for ~2000 tokens
        
        response = await openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=truncated_text,
            dimensions=EMBEDDING_DIMENSIONS
        )
        
        return response.data[0].embedding
    
    except Exception as e:
        logging.error(f"Failed to generate embedding: {e}")
        return None


async def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batches.
    
    Args:
        texts: List of texts to embed
    
    Returns:
        List of embeddings (None for failed items)
    """
    if not texts:
        return []
    
    results = []
    
    # Process in batches
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        
        try:
            # Filter out empty texts
            valid_batch = [(idx, t) for idx, t in enumerate(batch) if t and t.strip()]
            
            if not valid_batch:
                results.extend([None] * len(batch))
                continue
            
            # Truncate texts
            truncated_batch = [t[:8000] for _, t in valid_batch]
            
            response = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=truncated_batch,
                dimensions=EMBEDDING_DIMENSIONS
            )
            
            # Map results back to original positions
            batch_results = [None] * len(batch)
            for (original_idx, _), embedding_data in zip(valid_batch, response.data):
                batch_results[original_idx] = embedding_data.embedding
            
            results.extend(batch_results)
        
        except Exception as e:
            logging.error(f"Failed to generate batch embeddings: {e}")
            results.extend([None] * len(batch))
    
    return results


async def generate_resume_embedding(
    resume_text: str,
    full_name: Optional[str] = None,
    skills: Optional[str] = None,
    experience: Optional[str] = None
) -> Optional[List[float]]:
    """
    Generate embedding optimized for resume search.
    Combines multiple fields for better semantic matching.
    
    Args:
        resume_text: Full resume text
        full_name: Candidate name (optional)
        skills: Skills summary (optional)
        experience: Experience summary (optional)
    
    Returns:
        Embedding vector or None
    """
    # Build combined text for better semantic representation
    combined_parts = []
    
    if skills:
        combined_parts.append(f"Skills: {skills}")
    
    if experience:
        combined_parts.append(f"Experience: {experience}")
    
    if resume_text:
        combined_parts.append(resume_text)
    
    combined_text = "\n\n".join(combined_parts)
    
    return await generate_embedding(combined_text)


async def generate_job_embedding(
    job_title: str,
    job_description: str,
    skills_required: Optional[str] = None,
    experience_required: Optional[str] = None
) -> Optional[List[float]]:
    """
    Generate embedding optimized for job-to-candidate matching.
    
    Args:
        job_title: Job title
        job_description: Full job description
        skills_required: Required skills (optional)
        experience_required: Experience requirements (optional)
    
    Returns:
        Embedding vector or None
    """
    # Build combined text for job representation
    combined_parts = [
        f"Job Title: {job_title}",
    ]
    
    if skills_required:
        combined_parts.append(f"Required Skills: {skills_required}")
    
    if experience_required:
        combined_parts.append(f"Experience Required: {experience_required}")
    
    combined_parts.append(f"Description: {job_description}")
    
    combined_text = "\n\n".join(combined_parts)
    
    return await generate_embedding(combined_text)

# =========================================================
# BACKGROUND EMBEDDING GENERATOR (for existing resumes)
# =========================================================

async def backfill_embeddings_for_submissions(
    db_session,
    batch_size: int = 50
) -> dict:
    """
    Generate embeddings for all submissions that don't have them.
    Run this as a background task to populate the database.
    
    Args:
        db_session: SQLAlchemy session
        batch_size: Number of submissions to process at once
    
    Returns:
        Dict with stats: {processed, succeeded, failed}
    """
    from sqlalchemy import text
    
    stats = {"processed": 0, "succeeded": 0, "failed": 0}
    
    while True:
        # Get batch of submissions without embeddings
        result = db_session.execute(text("""
            SELECT submission_id, resume_text, full_name, skill_matrix
            FROM submissions
            WHERE embedding IS NULL
              AND resume_text IS NOT NULL
            LIMIT :batch_size
        """), {"batch_size": batch_size})
        
        rows = result.fetchall()
        
        if not rows:
            break
        
        # Generate embeddings
        texts = []
        for row in rows:
            combined = f"Name: {row.full_name or ''}\n\n{row.resume_text or ''}"
            texts.append(combined)
        
        embeddings = await generate_embeddings_batch(texts)
        
        # Update database
        for row, embedding in zip(rows, embeddings):
            stats["processed"] += 1
            
            if embedding:
                # Convert embedding list to PostgreSQL vector string format
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                db_session.execute(text("""
                    UPDATE submissions
                    SET embedding = (:embedding)::vector
                    WHERE submission_id = :submission_id
                """), {
                    "submission_id": row.submission_id,
                    "embedding": embedding_str
                })
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
        
        db_session.commit()
    
    return stats
