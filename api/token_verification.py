import httpx
import os
from fastapi import HTTPException
from typing import Dict

async def verify_google_token(token: str) -> Dict:
    """Verify a Google OAuth token using Google's tokeninfo endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": token}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired token"
                )
                
            token_info = response.json()
            
            # Verify the token was issued for our client
            if token_info.get("aud") != os.getenv("GOOGLE_CLIENT_ID"):
                raise HTTPException(
                    status_code=401,
                    detail="Token was not issued for this application"
                )
                
            return token_info
            
    except httpx.RequestError:
        raise HTTPException(
            status_code=500,
            detail="Failed to verify token with Google"
        )
