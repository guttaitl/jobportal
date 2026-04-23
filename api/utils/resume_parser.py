import pdfplumber
import docx

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
