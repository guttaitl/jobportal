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


def generate_structured_job_content(
    job_title: str,
    experience: str,
    rate: str = None,
    company_name: str = None,
    location: str = None,
    employment_type: str = None,
):
    """
    SINGLE SOURCE OF TRUTH
    No hardcoded skills.
    Always dynamic.
    """

    if not client:
        print("❌ No AI client")
        return None

    try:
        prompt = f"""
            You are a senior enterprise technical recruiter.

            Generate a PREMIUM job posting (NOT generic).

            INPUT:
            Role: {job_title}
            Experience: {experience}
            Rate: {rate}
            Company: {company_name}
            Location: {location}

            -----------------------------------
            STRICT EXPERIENCE LOGIC (MANDATORY)
            -----------------------------------
            - 0–3 years → junior developer (learning focus)
            - 4–8 years → strong hands-on engineer
            - 9–12 years → senior engineer (ownership + optimization)
            - 13+ years → architect / lead (design + scalability + leadership)

            -----------------------------------
            DESCRIPTION RULES
            -----------------------------------
            - MUST include years of experience explicitly
            - MUST reflect seniority correctly
            - NEVER say:
            ❌ "entry-level"
            ❌ "recent graduate"
            - For 13+ years:
            ✔ system design
            ✔ distributed systems
            ✔ scalability
            ✔ leadership / mentoring
            - Use enterprise tone (BFSI / large-scale systems if relevant)

            -----------------------------------
            SKILLS RULES
            -----------------------------------
            - ONLY real technologies
            - NO generic words like "problem solving"
            - For senior roles include:
            ✔ architecture
            ✔ cloud
            ✔ distributed systems
            ✔ performance tuning

            -----------------------------------
            RESPONSIBILITIES RULE (VERY IMPORTANT)
            -----------------------------------
            Each line MUST follow:

            → ACTION + TECHNOLOGY + PURPOSE

            Examples:
            - Design scalable microservices using Spring Boot to support high-volume transactions
            - Optimize Spark jobs for memory and compute efficiency in large-scale data pipelines

            -----------------------------------
            OUTPUT REQUIREMENTS
            -----------------------------------
            - Minimum 8–10 responsibilities
            - Responsibilities must be DETAILED (enterprise level)
            - Skills must be role + experience aligned
            - Description must be 4–6 lines (strong, not generic)

            -----------------------------------
            RETURN JSON:
            {{
            "description": "...",
            "required_skills": ["..."],
            "responsibilities": ["..."]
            }}
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
        return data

    except Exception as e:
        print("❌ AI FAILED:", e)
        return None
