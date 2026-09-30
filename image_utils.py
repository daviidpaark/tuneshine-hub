import io
import hashlib
from PIL import Image, ImageOps

TUNESHINE_SIZE = (64, 64)


def process_image_to_webp(image_data: bytes) -> bytes:
    """
    Decodes an image (JPEG/PNG/WebP), center-crops it to a square and resizes it to 64x64
    using bilinear filtering, and encodes it as lossless WebP.
    """
    with Image.open(io.BytesIO(image_data)) as img:
        # Convert to RGBA for consistent color handling
        if img.mode != "RGBA":
            converted = img.convert("RGBA")
        else:
            converted = img

        try:
            # Center-crop non-square art instead of stretching it
            with ImageOps.fit(converted, TUNESHINE_SIZE, method=Image.Resampling.BILINEAR) as resized:
                output = io.BytesIO()
                resized.save(output, format="WEBP", lossless=True)
                return output.getvalue()
        finally:
            if converted is not img:
                converted.close()


def compute_image_hash(data: bytes) -> str:
    """Computes a SHA-256 hash string for deduplicating artwork uploads."""
    return hashlib.sha256(data).hexdigest()
