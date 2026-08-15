from io import BytesIO

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.errors import AppError

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_ALLOWED_FORMATS = {"JPEG", "PNG"}


async def read_valid_image(image: UploadFile, max_bytes: int) -> bytes:
    if image.content_type not in _ALLOWED_CONTENT_TYPES:
        raise _invalid_image()

    image_bytes = await image.read(max_bytes + 1)
    if not image_bytes or len(image_bytes) > max_bytes:
        raise _invalid_image()

    try:
        with Image.open(BytesIO(image_bytes)) as decoded_image:
            if decoded_image.format not in _ALLOWED_FORMATS:
                raise _invalid_image()
            decoded_image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise _invalid_image() from exc

    return image_bytes


def _invalid_image() -> AppError:
    return AppError(400, "INVALID_IMAGE", "A valid JPEG or PNG image is required.")
