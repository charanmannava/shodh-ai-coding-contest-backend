from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.organization import Membership
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        subject = decode_access_token(credentials.credentials).get("sub")
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from exc
    user = db.scalar(select(User).where(User.id == subject))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token")
    return user


def require_membership(
    db: Session, user_id: str, organization_id: str, roles: set[str] | None = None
) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None or (roles is not None and membership.role not in roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient organization permissions")
    return membership
