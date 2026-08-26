import io
import hashlib
from PIL import Image

TUNESHINE_SIZE = (64, 64)


def process_image_to_webp(image_data: bytes) -> bytes:
    """
    Decodes an image (JPEG/PNG/WebP), resizes it to 64x64 using bilinear filtering,
    and encodes it as lossless WebP.
    """
    with Image.open(io.BytesIO(image_data)) as img:
        # Convert to RGBA for consistent color handling
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # Resize to 64x64
        resized = img.resize(TUNESHINE_SIZE, resample=Image.Resampling.BILINEAR)

        # Encode to WebP lossless
        output = io.BytesIO()
        resized.save(output, format="WEBP", lossless=True)
        return output.getvalue()


def compute_image_hash(data: bytes) -> str:
    """Computes a SHA-256 hash string for deduplicating artwork uploads."""
    return hashlib.sha256(data).hexdigest()
