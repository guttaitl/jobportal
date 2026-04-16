import os
import requests

# 🔥 UPDATE PATH IF NEEDED
RESUME_FOLDER = r"C:\Users\Lohitha\Desktop\Resumes"

API_URL = "http://localhost:8000/api/resumes/upload"

print(f"🚀 API URL: {API_URL}")


def upload_resume(file_path):
    try:
        file_name = os.path.basename(file_path)

        # ✅ Send file as binary (DO NOT decode here)
        with open(file_path, "rb") as f:
            files = {
                "file": (file_name, f, "application/octet-stream")
            }

            data = {
                "full_name": file_name,   # later we will fix name extraction
                "email": "bulk@import.com"
            }

            response = requests.post(
                API_URL,
                files=files,
                data=data,
                timeout=30
            )

        if response.status_code == 200:
            print(f"✅ Uploaded: {file_name}")
        else:
            print(f"❌ Failed ({response.status_code}): {file_name}")
            print(response.text)

    except Exception as e:
        print(f"❌ Error uploading {file_path}: {e}")


def run():
    if not os.path.exists(RESUME_FOLDER):
        print(f"❌ Folder not found: {RESUME_FOLDER}")
        return

    files = os.listdir(RESUME_FOLDER)
    print(f"📂 Found {len(files)} files")

    for file in files:
        if file.lower().endswith((".pdf", ".doc", ".docx")):
            file_path = os.path.join(RESUME_FOLDER, file)
            upload_resume(file_path)


if __name__ == "__main__":
    run()
