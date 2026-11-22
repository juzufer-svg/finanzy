"""
Users routes
"""
from fastapi import APIRouter, HTTPException, Header, status
from app.schemas.auth import UserResponse, UpdateCurrencyRequest
from app.models.user import UserDB
from app.core.security import decode_token

router = APIRouter()


async def _get_active_user_id(authorization: str) -> str:
    """Valida JWT y confirma que la cuenta esté activa."""
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

    updated = await UserDB.update_currency(user_id, request.currency)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la moneda.",
        )

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
    # No eliminar la fila mientras existan relaciones financieras sin política
    # de retención/cascada aprobada. Evita dejar datos huérfanos.
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="La eliminación de cuenta está temporalmente deshabilitada para proteger tus registros financieros.",
    )

