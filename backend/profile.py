import io
import unicodedata

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_AVATAR_BYTES = 1024 * 1024


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=1, max_length=80)

    @field_validator("nickname")
    @classmethod
    def valid_nickname(cls, value):
        value = value.strip()
        if not value or any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
            raise ValueError("Enter a nickname without control characters")
        return value


def normalize_avatar(data):
    if not data or len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "Avatar must be at most 1 MB")
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as source:
            if source.width * source.height > 4_000_000 or max(source.size) > 4096:
                raise HTTPException(422, "Avatar dimensions must not exceed 4 million pixels or 4096 px per side")
            source.load()
            image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGBA"), (256, 256))
            clean = Image.frombytes("RGBA", image.size, image.tobytes())
            output = io.BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Upload a valid PNG, JPEG or WebP image") from error
