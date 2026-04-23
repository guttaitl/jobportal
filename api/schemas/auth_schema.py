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
<<<<<<< HEAD
    email: EmailStr
=======
    email: EmailStr
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
