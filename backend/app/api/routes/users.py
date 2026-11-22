"""
Users routes
"""
from fastapi import APIRouter, HTTPException, Header, status
from app.schemas.auth import UserResponse, UpdateCurrencyRequest
from app.models.user import UserDB
from app.api.sesion import usuario_de_sesion

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(authorization: str = Header(...)):
    """Get current user information"""
    user_id = await usuario_de_sesion(authorization)
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
    user_id = await usuario_de_sesion(authorization)
    
    # Verify user exists
    user = await UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Si no se pudo guardar, se informa el error: nunca se simula un éxito (CHG-002)
    try:
        guardado = await UserDB.update_currency(user_id, request.currency)
    except Exception as e:
        print(f"[users.update_currency] {type(e).__name__}")
        guardado = False
    if not guardado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la moneda. Intenta de nuevo en unos minutos.",
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
    user_id = await usuario_de_sesion(authorization)
    deleted = await UserDB.delete_by_id(user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
