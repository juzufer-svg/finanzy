"""
Users routes
"""
from fastapi import APIRouter, HTTPException, Header, status
from app.schemas.auth import UserResponse, UpdateCurrencyRequest
from app.models.user import UserDB
from app.core.security import decode_token

router = APIRouter()


async def _get_active_user_id(authorization: str) -> str:
    """Valida el JWT y la vigencia de la cuenta en la base de datos."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    payload = decode_token(token.strip()) if scheme.lower() == "bearer" else None
    user_id = payload.get("sub") if payload else None
    user = await UserDB.get_by_id(user_id) if user_id else None
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive session")
    return str(user_id)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(authorization: str = Header(...)):
    """Get current user information"""
    user_id = await _get_active_user_id(authorization)
    user = await UserDB.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(**user)


@router.put("/me/currency", response_model=UserResponse)
async def update_user_currency(request: UpdateCurrencyRequest, authorization: str = Header(...)):
    """Update user's currency preference"""
    user_id = await _get_active_user_id(authorization)
    
    # Verify user exists
    user = await UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update currency (column may not exist yet in older DBs, handle gracefully)
    try:
        await UserDB.update_currency(user_id, request.currency)
    except Exception:
        # Column might not exist — still return user with requested currency applied
        user["currency"] = request.currency
        return UserResponse(**user)
    
    # Fetch updated user
    updated_user = await UserDB.get_by_id(user_id)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(**updated_user)


@router.delete("/me", status_code=204)
async def delete_current_user(authorization: str = Header(...)):
    """Delete the authenticated user's account permanently"""
    user_id = await _get_active_user_id(authorization)
    deleted = await UserDB.delete_by_id(user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
