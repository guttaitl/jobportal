import pdfplumber
import docx
import re

# ==========================================================
# TEXT EXTRACTION
# ==========================================================

def extract_text(file_path: str) -> str:
    text = ""

    try:
        # PDF
        if file_path.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""

        # DOCX
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"

    except Exception as e:
        print(f"Error extracting text: {e}")

    return text.strip()


# ==========================================================
# SKILLS EXTRACTION (NO HARDCODING)
# ==========================================================

def extract_skills(text: str) -> str:
    if not text:
        return None

    text = text.lower()

    # Extract "word-like" tokens (tech terms allowed)
    pattern = r"\b[a-zA-Z][a-zA-Z0-9\+\#\.]{1,}\b"
    words = re.findall(pattern, text)

    # Remove common noise
    stop_words = {
        "the", "and", "with", "for", "from", "this", "that",
        "have", "has", "using", "over", "years", "experience",
        "worked", "team", "project", "client", "role",
        "responsible", "developed", "application", "system"
    }

    candidates = [
        w for w in words
        if w not in stop_words and len(w) > 2
    ]

    # Frequency scoring
    freq = {}
    for word in candidates:
        freq[word] = freq.get(word, 0) + 1

    # Sort by importance
    sorted_skills = sorted(freq.items(), key=lambda x: x[1], reverse=True)

    # Take top 10
    top_skills = [skill for skill, _ in sorted_skills[:10]]

    return ", ".join(top_skills) if top_skills else None


# ==========================================================
# JOB TITLE EXTRACTION (SMART HEURISTIC)
# ==========================================================

def extract_job_title(text: str):
    lines = text.split("\n")

    for line in lines[:15]:
        clean = line.strip()

        # Likely title: short line, not too many words
        if 2 <= len(clean.split()) <= 8:
            if not any(x in clean.lower() for x in ["email", "phone", "resume"]):
                return clean

    return None


# ==========================================================
# LOCATION EXTRACTION (PATTERN-BASED)
# ==========================================================

def extract_location(text: str):
    # Pattern: City, ST
    match = re.search(r"\b[A-Z][a-z]+,\s*[A-Z]{2}\b", text)

    if match:
        parts = match.group().split(",")
        return parts[0], parts[1].strip()

    # Fallback: country detection
    if "india" in text.lower():
        return None, "India"

    if "usa" in text.lower() or "united states" in text.lower():
        return None, "USA"

    return None, None


# ==========================================================
# TEXT → HTML (FOR PREVIEW)
# ==========================================================

def text_to_html(text: str):
    if not text:
        return None

    # Split into paragraphs
    paragraphs = re.split(r"\n\s*\n", text)

    html = ""

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue

        # Clean spacing
        p = re.sub(r"\s+", " ", p)

        html += f"<p>{p}</p>"

    return html