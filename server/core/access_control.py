"""Shared application authorization checks."""

from fastapi import HTTPException

from models import Application, User


async def require_app_member(app_id: str, current_user: User) -> Application:
    """Return an application only when the current user is one of its members."""
    app = await Application.find_one(
        Application.app_id == app_id,
        Application.users == current_user.username,
    )
    if not app:
        raise HTTPException(
            status_code=404,
            detail="Application not found or permission denied",
        )
    return app
