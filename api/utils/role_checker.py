from fastapi import Depends, HTTPException
from api.utils.security import get_current_user


def require_role(required_role: str):
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("role") or "").upper()

        if user_role != required_role.upper():
            raise HTTPException(
                status_code=403,
                detail=f"{required_role} access required"
            )

        return current_user

    return role_checker