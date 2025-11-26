"""Security primitives and authentication helpers."""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> Any:
    """Placeholder dependency that will later validate JWTs or API keys."""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    # TODO: implement JWT decoding & user lookup.
    return {"sub": "placeholder-user"}

