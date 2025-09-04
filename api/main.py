from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import os
from dotenv import load_dotenv
from typing import Optional

# Import our API modules
from .auth import router as auth_router
from .agents import router as agents_router
from .chat import router as chat_router

load_dotenv(override=True)

app = FastAPI(
    title="Conversational Analytics API",
    description="REST API for Conversational Analytics application",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://conv-api-vercel-backend.vercel.app",
        "https://conv-api-quickstarts.vercel.app",
        "https://conv-api-frontend.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["authentication"])
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])

@app.get("/")
async def root():
    return RedirectResponse(url="/api/auth/google/url")
