from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
import os
import time

security = HTTPBearer()

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        
        # Create credentials object
        creds = Credentials(
            token=token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
        )
        
        # Refresh the token if necessary
        if creds.expired:
            try:
                creds.refresh(GoogleRequest())
            except Exception as e:
                raise HTTPException(
                    status_code=401,
                    detail="Token expired and refresh failed"
                )
                
        # Validate the token by making a test request
        auth_request = GoogleRequest()
        creds.before_request(auth_request, 'GET', 'https://www.googleapis.com/oauth2/v1/userinfo')
        
        return {
            "access_token": token,
            "token_type": "Bearer"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )
