from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

# Import your existing routers
from .auth import router as auth_router
from .agents import router as agents_router  
from .chat import router as chat_router

app = FastAPI(
    title="Conversational Analytics API",
    description="REST API for Conversational Analytics application", 
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure with your actual domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers without /api prefix since Vercel handles that
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(agents_router, prefix="/agents", tags=["agents"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])

@app.get("/")
async def root():
    return {"message": "Conversational Analytics API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

handler = Mangum(app)
