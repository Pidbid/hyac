from fastapi import APIRouter, HTTPException
from starlette import status

from core.database import mongodb_manager
from core.s3_manager import s3_manager

router = APIRouter()


@router.get("/__server_health__", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the status of critical services.
    """
    try:
        # 1. Check MongoDB connection
        await mongodb_manager.db.command("ping")

        # 2. Check S3 connection
        if not s3_manager.client:
            raise Exception("S3 client not initialized")
        s3_manager.client.list_buckets()

        return {"status": "ready"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {str(e)}",
        )
