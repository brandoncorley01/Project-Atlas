from fastapi import APIRouter, Depends

from app.dependencies import get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
    }
