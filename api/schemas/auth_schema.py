from pydantic import BaseModel, EmailStr


# =========================================
# LOGIN REQUEST
# =========================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# =========================================
# EMAIL CHECK (REGISTER STEP 1)
# =========================================
class EmailCheckRequest(BaseModel):
    email: EmailStr