import os
import json
import logging
from typing import Optional, List
from openai import OpenAI

logger = logging.getLogger(__name__)

# ==========================================================
# OPENAI CLIENT (lazy singleton)
# ==========================================================

_openai_client: Optional[OpenAI] = None


def get_openai_client() -> Optional[OpenAI]:
    """Lazy-initialized OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                _openai_client = OpenAI(api_key=api_key)
                logger.info("✅ OpenAI client initialized")
            except Exception as e:
                logger.error(f"❌ OpenAI init failed: {e}")
    return _openai_client


# ==========================================================
# PYDANTIC OUTPUT SCHEMA
# ==========================================================

class JobContentOutput:
    """Expected AI response shape."""
    description: str
    required_skills: List[str]
    responsibilities: List[str]


# ==========================================================
# MAIN FUNCTION
# ==========================================================

def generate_structured_job_content(
    job_title: str,
    experience: str,
    rate: Optional[str] = None,
    company_name: Optional[str] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    industry: Optional[str] = None,
) -> Optional[dict]:
    """
    Fully AI-driven job posting generator.
    Uses OpenAI Responses API with strict JSON output.
    Includes lightweight validation and one auto-retry.
    """

    client = get_openai_client()
    if not client:
        logger.error("No OpenAI client available")
        return None

    # ── Build prompt ──────────────────────────────────────
    prompt = _build_prompt(
        job_title=job_title,
        experience=experience,
        rate=rate,
        company_name=company_name,
        location=location,
        employment_type=employment_type,
        industry=industry,
    )

    try:
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        response = client.responses.create(
            model=model,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "job_posting",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "4-6 line job description matching seniority and role"
                            },
                            "required_skills": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "8-12 specific, real technologies. No generic soft skills."
                            },
                            "responsibilities": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "8-10 detailed responsibilities following ACTION + TECHNOLOGY + PURPOSE"
                            }
                        },
                        "required": ["description", "required_skills", "responsibilities"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            }
        )

        raw = response.output_text
        data = json.loads(raw)

        # ── Validate & clean ──────────────────────────────
        return _validate_and_clean(data, job_title, experience, rate, company_name, location, employment_type, industry)

    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        return None


def _build_prompt(
    job_title: str,
    experience: str,
    rate: Optional[str],
    company_name: Optional[str],
    location: Optional[str],
    employment_type: Optional[str],
    industry: Optional[str],
) -> str:
    """Construct the recruiter prompt with strict rules."""

    return f"""You are a senior enterprise technical recruiter.

Generate a HIGH-QUALITY, REALISTIC job posting.

-----------------------------------
INPUT
-----------------------------------
Role: {job_title}
Experience: {experience}
Rate: {rate or 'Not specified'}
Company: {company_name or 'Not specified'}
Location: {location or 'Not specified'}
Employment Type: {employment_type or 'Not specified'}
Industry: {industry or 'Not specified'}

-----------------------------------
STRICT EXPERIENCE LOGIC
-----------------------------------
- 0–3 years  → junior developer, learning focus, simpler tools
- 4–8 years  → strong hands-on engineer
- 9–12 years → senior engineer, ownership + optimization
- 13+ years  → architect / lead, system design + scalability + mentoring

-----------------------------------
CRITICAL RULES
-----------------------------------
1. ROLE ACCURACY
   - Skills MUST strictly match the role ecosystem
   - Mainframe → ONLY mainframe technologies
   - .NET → ONLY Microsoft stack
   - Java → ONLY Java ecosystem
   - NEVER mix unrelated technologies

2. NO ASSUMPTIONS
   - Do NOT assume BFSI unless clearly implied by company/industry
   - Do NOT inject Cloud/Microservices unless role requires it

3. RATE + EXPERIENCE INTELLIGENCE
   - Higher experience or rate → advanced tools + architecture
   - Lower experience → simpler, foundational tools

4. SKILLS QUALITY
   - 8–12 skills only
   - Each must be: specific, relevant, non-generic
   - NO soft skills like "problem solving" or "communication"
   - Senior roles MUST include: architecture, cloud, distributed systems, or performance tuning

5. RESPONSIBILITIES QUALITY
   - 8–10 responsibilities
   - Each MUST follow: ACTION + TECHNOLOGY + PURPOSE
   - Example: "Design scalable microservices using Spring Boot to support high-volume transactions"
   - Must reflect real-world enterprise work

6. DESCRIPTION QUALITY
   - 4–6 lines
   - MUST include years of experience explicitly
   - MUST reflect seniority correctly
   - NEVER say "entry-level" or "recent graduate"
   - Use enterprise tone for senior roles

7. NO GENERIC OUTPUT
   - Do NOT reuse common templates
   - Do NOT repeat phrases across jobs
"""


def _validate_and_clean(
    data: dict,
    job_title: str,
    experience: str,
    rate: Optional[str],
    company_name: Optional[str],
    location: Optional[str],
    employment_type: Optional[str],
    industry: Optional[str],
) -> Optional[dict]:
    """Deduplicate, enforce bounds, and auto-retry once on weak output."""

    skills = list(dict.fromkeys([s.strip() for s in data.get("required_skills", []) if s and len(s) > 1]))
    responsibilities = list(dict.fromkeys([r.strip() for r in data.get("responsibilities", []) if r and len(r) > 10]))

    # Retry once if AI produced weak output
    if len(skills) < 6 or len(responsibilities) < 6:
        logger.warning("Weak AI output detected — attempting one retry")
        # Force a different model or just retry with same params
        return _generate_with_retry(
            job_title, experience, rate, company_name, location, employment_type, industry
        )

    return {
        "description": (data.get("description") or "").strip(),
        "skills": skills[:12],
        "responsibilities": responsibilities[:12],
    }


def _generate_with_retry(
    job_title: str,
    experience: str,
    rate: Optional[str],
    company_name: Optional[str],
    location: Optional[str],
    employment_type: Optional[str],
    industry: Optional[str],
) -> Optional[dict]:
    """One-shot retry with stricter instructions (no recursion)."""

    client = get_openai_client()
    if not client:
        return None

    strict_prompt = f"""You are a senior enterprise technical recruiter.

PREVIOUS ATTEMPT FAILED QUALITY CHECK.

Generate a PREMIUM job posting with STRICT compliance.

Role: {job_title}
Experience: {experience}
Rate: {rate or 'Not specified'}
Company: {company_name or 'Not specified'}
Location: {location or 'Not specified'}

MANDATORY:
- MINIMUM 8 specific technical skills (real technologies only)
- MINIMUM 8 detailed responsibilities (ACTION + TECHNOLOGY + PURPOSE)
- Description MUST explicitly state experience level
- Skills MUST match the role ecosystem exactly
"""

    try:
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        response = client.responses.create(
            model=model,
            input=strict_prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "job_posting",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "required_skills": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 8,
                                "maxItems": 12
                            },
                            "responsibilities": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 8,
                                "maxItems": 10
                            }
                        },
                        "required": ["description", "required_skills", "responsibilities"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            }
        )

        data = json.loads(response.output_text)
        skills = list(dict.fromkeys([s.strip() for s in data.get("required_skills", []) if s]))
        responsibilities = list(dict.fromkeys([r.strip() for r in data.get("responsibilities", []) if r]))

        return {
            "description": (data.get("description") or "").strip(),
            "skills": skills[:12],
            "responsibilities": responsibilities[:12],
        }

    except Exception as e:
        logger.error(f"Retry failed: {e}")
        return None