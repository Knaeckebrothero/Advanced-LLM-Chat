"""
Barcode scanning API endpoints.

Provides server-side barcode decoding using pyzbar as a fallback
for browsers where the client-side ZXing JS decoder is insufficient.
"""
import base64
import logging
import time
from io import BytesIO
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from PIL import Image
from pyzbar.pyzbar import decode

from backend.models.common import ErrorResponse
from backend.security.auth import get_current_user

router = APIRouter(prefix="/api/barcode", tags=["Barcode"])
logger = logging.getLogger(__name__)


class ScanImageRequest(BaseModel):
    image: str = Field(..., description="Base64-encoded image data (JPEG or PNG)")


class BarcodeResult(BaseModel):
    data: str = Field(..., description="Decoded barcode value")
    format: str = Field(..., description="Barcode format (e.g. EAN-13, UPC-A)")


class ScanImageResponse(BaseModel):
    barcodes: List[BarcodeResult] = Field(default_factory=list)
    scan_duration_ms: float = 0.0


@router.post(
    "/scan-image",
    response_model=ScanImageResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def scan_image(
    request: ScanImageRequest,
    current_user: dict = Depends(get_current_user),
):
    """Decode barcodes from a base64-encoded image using pyzbar."""
    start = time.monotonic()

    # Decode base64
    try:
        image_bytes = base64.b64decode(request.image)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Open image with Pillow
    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode image")

    # Decode barcodes
    try:
        detected = decode(image)
    except Exception as exc:
        logger.error("pyzbar decode error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Barcode decoding failed")

    barcodes = []
    for barcode in detected:
        try:
            data = barcode.data.decode("utf-8")
        except UnicodeDecodeError:
            data = str(barcode.data)
        barcodes.append(BarcodeResult(data=data, format=barcode.type))

    duration_ms = (time.monotonic() - start) * 1000
    logger.info("Scanned image: found %d barcodes in %.1fms", len(barcodes), duration_ms)

    return ScanImageResponse(barcodes=barcodes, scan_duration_ms=duration_ms)
