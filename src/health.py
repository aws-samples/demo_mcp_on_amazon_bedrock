"""
Health check endpoint for the FastAPI application
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/api/health")
async def health_check():
    """Health check endpoint for load balancer"""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "mcp-backend",
            "version": "1.0.0"
        },
        status_code=200
    )
