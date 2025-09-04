from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .token_verification import verify_google_token

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency that verifies the Bearer token and returns the token info."""
    token = credentials.credentials
    token_info = await verify_google_token(token)
    return token_info
