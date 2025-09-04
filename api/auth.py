from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import httpx
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import GetAccessTokenError
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests
from typing import Optional, Dict
from dotenv import load_dotenv
import json

security = HTTPBearer()

load_dotenv(override=True)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
PROJECT_ID = os.getenv("PROJECT_ID")

# Validate credentials
if not all((
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    REDIRECT_URI,
    PROJECT_ID
)):
    print(f"Missing environment variables:")
    print(f"GOOGLE_CLIENT_ID: {'SET' if GOOGLE_CLIENT_ID else 'MISSING'}")
    print(f"GOOGLE_CLIENT_SECRET: {'SET' if GOOGLE_CLIENT_SECRET else 'MISSING'}")
    print(f"REDIRECT_URI: {'SET' if REDIRECT_URI else 'MISSING'}")
    print(f"PROJECT_ID: {'SET' if PROJECT_ID else 'MISSING'}")
    raise ValueError("Missing required environment variables. Check .env file.")

oauth_client = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

router = APIRouter()

@router.get("/google/url")
async def get_google_url():
    """Get Google OAuth authorization URL"""
    try:
        callback_uri = os.getenv("REDIRECT_URI", "https://conv-api-vercel-backend.vercel.app/api/auth/callback")
        auth_url = await oauth_client.get_authorization_url(
            callback_uri,
            scope=SCOPES,
            extras_params={"access_type": "offline"}
        )
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get auth URL: {str(e)}")

from fastapi import Request, Query

@router.get("/callback")
async def google_callback_get(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None)
):
    """Handle OAuth callback from Google"""
    if error:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_url}/?error={error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required")
        
    # Redirect to frontend with the code
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/?code={code}")

@router.post("/google/callback")
async def google_callback_post(request: Request):
    """Handle callback code exchange from frontend"""
    try:
        data = await request.json()
        code = data.get('code')
        error = data.get('error')
        
        print(f"Received POST callback with code: {code[:10]}..." if code else "No code received")
        
        if error:
            raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

        if not code:
            raise HTTPException(status_code=400, detail="Authorization code is required")

        callback_uri = os.getenv("REDIRECT_URI", "https://conv-api-vercel-backend.vercel.app/api/auth/callback")
        print(f"Using callback URI: {callback_uri}")
        
        token = await oauth_client.get_access_token(code, callback_uri)

        if not token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        creds = Credentials(
            token=token["access_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES,
        )

        # Convert credentials to dict for query string
        creds_dict = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": ",".join(creds.scopes),
            "expiry": creds.expiry.isoformat() if creds.expiry else ""
        }

        # Return access token directly
        return {
            "access_token": creds.token,
            "token_type": "Bearer",
            "expires_in": 3600  # Google's default expiration time
        }

    except GetAccessTokenError as e:
        raise HTTPException(status_code=401, detail="Failed to get access token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate a token using Google's tokeninfo endpoint"""
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("validate_token")

    try:
        token = credentials.credentials
        logger.info(f"Raw credentials: {credentials}")
        logger.info(f"Token extracted: {token[:20]}...")
        logger.info(f"Token length: {len(token)}")

        # Verify the token with Google's tokeninfo endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'https://www.googleapis.com/oauth2/v1/tokeninfo',
                params={'access_token': token}
            )

            logger.info(f"Tokeninfo response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Token validation failed with status: {response.status_code}")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token"
                )

            token_info = response.json()
            logger.info(f"Token info received: {token_info}")

            # Verify the token belongs to our application
            expected_aud = GOOGLE_CLIENT_ID
            actual_aud = token_info.get('aud')
            logger.info(f"GOOGLE_CLIENT_ID: {expected_aud}")
            logger.info(f"Token audience: {actual_aud}")

            if actual_aud != expected_aud:
                logger.error(f"Token audience mismatch. Expected: {expected_aud}, Got: {actual_aud}")
                raise HTTPException(
                    status_code=401,
                    detail="Token was not issued for this application"
                )

            logger.info("Token validation successful")
            return token_info

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except httpx.RequestError as e:
        logger.error(f"HTTP request error during token validation: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail=f"Failed to validate token: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )@router.get("/logout")
async def logout():
    """Handle logout (client-side token clearing)"""
    return {"message": "Logged out successfully"}

__all__ = ["router", "validate_token"]
