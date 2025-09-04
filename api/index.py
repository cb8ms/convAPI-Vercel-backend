from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

app = FastAPI()

# CORS middleware
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers after app creation
from .auth import router as auth_router
from .agents import router as agents_router  
from .chat import router as chat_router

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(agents_router, prefix="/agents", tags=["agents"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])

@app.get("/")
async def root():
    return {"message": "Conversational Analytics API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Handler for Vercel
from mangum import Mangum
handler = Mangum(app)
