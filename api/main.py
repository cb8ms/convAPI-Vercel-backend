from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
from typing import Optional
import uvicorn

# Import our API modules
from .auth import router as auth_router
from .agents import router as agents_router
from .chat import router as chat_router

load_dotenv(override=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting CA API Backend")
    yield
    # Shutdown
    print("Shutting down CA API Backend")

app = FastAPI(
    title="Conversational Analytics API",
    description="REST API for Conversational Analytics application",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
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
    return {"message": "Conversational Analytics API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
