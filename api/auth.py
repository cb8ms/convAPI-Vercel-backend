from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import os
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.oauth2 import GetAccessTokenError
from google.oauth2.credentials import Credentials
from typing import Optional
from dotenv import load_dotenv
import json

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
    data = await request.json()
    code = data.get('code')
    error = data.get('error')
    try:
        if error:
            # Handle OAuth error
            return RedirectResponse(url="http://localhost:3000/?error=" + error)

        if not code:
            raise HTTPException(status_code=400, detail="Authorization code is required")

        token = await oauth_client.get_access_token(code, REDIRECT_URI)

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

        # Return the access token directly
        return {
            "access_token": creds.token,
            "token_type": "Bearer",
            "expires_in": 3600  # Google's default expiration time
        }

    except GetAccessTokenError as e:
        raise HTTPException(status_code=401, detail="Failed to get access token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logout")
async def logout():
    """Handle logout (client-side token clearing)"""
    return {"message": "Logged out successfully"}
