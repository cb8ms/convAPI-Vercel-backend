from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
import os
import time

from .token_verification import verify_google_token

security = HTTPBearer()

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        
        # Use our token verification module
        token_info = await verify_google_token(token)
        return token_info
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Failed to validate token: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )
