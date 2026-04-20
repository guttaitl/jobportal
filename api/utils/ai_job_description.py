import os
import json
from openai import OpenAI

client = None

try:
    if os.getenv("OPENAI_API_KEY"):
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print("✅ OpenAI ready")
except Exception as e:
    print("❌ OpenAI init failed:", e)


# ==========================================================
# MAIN FUNCTION (FULLY AI DRIVEN)
# ==========================================================
def generate_structured_job_content(
    job_title: str,
    experience: str,
    rate: str = None,
    company_name: str = None,
    location: str = None,
    employment_type: str = None,
    industry: str = None,
):
    """
    FULLY AI DRIVEN — NO HARDCODING
    """

    if not client:
        print("❌ No AI client")
        return None

    try:
        prompt = f"""
You are a senior enterprise technical recruiter.

Generate a HIGH-QUALITY, REALISTIC job posting.

-----------------------------------
INPUT
-----------------------------------
Role: {job_title}
Experience: {experience}
Rate: {rate}
Company: {company_name}
Location: {location}
Employment Type: {employment_type}
Industry (if known): {industry}

-----------------------------------
CRITICAL INSTRUCTIONS
-----------------------------------

1. NO GENERIC OUTPUT
- Do NOT reuse common templates
- Do NOT repeat phrases across jobs

2. ROLE ACCURACY (VERY IMPORTANT)
- Skills MUST strictly match the role
- Example:
  - Mainframe → ONLY mainframe technologies
  - .NET → ONLY Microsoft stack
  - Java → ONLY Java ecosystem
- NEVER mix unrelated technologies

3. NO ASSUMPTIONS
- Do NOT assume BFSI unless clearly implied by company
- Do NOT inject Cloud/Microservices unless role requires it

4. RATE + EXPERIENCE INTELLIGENCE
- Higher experience or rate → more advanced tools + architecture
- Lower experience → simpler tools

5. SKILLS QUALITY
- Minimum 8 skills
- Maximum 12 skills
- Each skill must be:
  ✔ specific
  ✔ relevant
  ✔ non-generic

6. RESPONSIBILITIES QUALITY
- Minimum 8 responsibilities
- Each must follow:
  ACTION + TECHNOLOGY + PURPOSE
- Must reflect real-world work

7. DESCRIPTION QUALITY
- 4–6 lines
- Must include experience level
- Must match company + role context
- No fluff

-----------------------------------
STRICT OUTPUT FORMAT
-----------------------------------
Return ONLY valid JSON:

{{
  "description": "...",
  "required_skills": ["..."],
  "responsibilities": ["..."]
}}

DO NOT include any extra text.
"""

        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt
        )

        text = response.output_text

        start = text.find("{")
        end = text.rfind("}") + 1

        data = json.loads(text[start:end])

        print("✅ AI SUCCESS")

        # ==========================================================
        # LIGHT VALIDATION (NO HARDCODING)
        # ==========================================================
        skills = data.get("required_skills", [])
        responsibilities = data.get("responsibilities", [])

        # Clean duplicates
        skills = list(dict.fromkeys([s.strip() for s in skills if s]))
        responsibilities = list(dict.fromkeys([r.strip() for r in responsibilities if r]))

        # Retry if weak output (AI self-correction)
        if len(skills) < 6 or len(responsibilities) < 6:
            print("⚠️ Weak AI output — retrying...")
            return generate_structured_job_content(
                job_title,
                experience,
                rate,
                company_name,
                location,
                employment_type,
                industry
            )

        return {
            "description": data.get("description", ""),
            "skills": skills[:12],
            "responsibilities": responsibilities[:12]
        }

    except Exception as e:
        print("❌ AI FAILED:", e)
        return None