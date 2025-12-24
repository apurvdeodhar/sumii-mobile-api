"""
Sumii Mobile API - FastAPI Application
Backend for Sumii Mobile App (User-Facing)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import anwalt, auth, conversations, documents, events, status, summaries, users, webhooks, websocket
from app.utils.logging_config import setup_logging

# Configure logging from environment variables (one-time setup)
setup_logging()

app = FastAPI(
    title="Sumii Mobile API",
    version="0.1.0",
    description=(
        "Backend API for Sumii Mobile App - "
        "Intelligent lawyer assistant for empathetic fact-gathering and lawyer connections"
    ),
)

# CORS for mobile app (MVP - allow all origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "service": "sumii-mobile-api",
    }


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
app.include_router(documents.router)  # Documents endpoints (upload, download, delete)
app.include_router(summaries.router, prefix="/api/v1", tags=["summaries"])  # Summary endpoints
app.include_router(status.router, tags=["status"])  # Status endpoints (health, agents, progress)
app.include_router(anwalt.router)  # Anwalt endpoints (lawyer search and connection)
app.include_router(events.router)  # SSE events endpoint (notifications)
app.include_router(users.router)  # Users endpoints (push token, profile)
app.include_router(webhooks.router)  # Webhook endpoints (receive events from sumii-anwalt)
app.include_router(websocket.router, tags=["websocket"])
