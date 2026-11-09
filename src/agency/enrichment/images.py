"""Image source adapters: local owner assets, clean stock, and composites."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from agency.config import get_settings
from agency.enrichment.models import ImageInfo

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


class ImageSourceAdapter(ABC):
    @abstractmethod
    def get_images(self, lead_id: int, category: str | None = None) -> list[ImageInfo]:
        """Return list of valid, license-clean images for the given lead."""


class LocalAssetSource(ImageSourceAdapter):
    """Owner-supplied photos stored locally at data/assets/<lead_id>/."""

    def __init__(self, assets_dir: Path | str | None = None):
        self.assets_dir = Path(assets_dir) if assets_dir else get_settings().assets_dir

    def get_images(self, lead_id: int, category: str | None = None) -> list[ImageInfo]:
        folder = self.assets_dir / str(lead_id)
        if not folder.exists() or not folder.is_dir():
            return []

        images: list[ImageInfo] = []
        for file in sorted(folder.iterdir()):
            if file.is_file() and file.suffix.lower() in VALID_IMAGE_EXTENSIONS:
                clean_name = file.stem.replace("-", " ").replace("_", " ").title()
                images.append(
                    ImageInfo(
                        url_or_path=str(file.resolve()),
                        caption=clean_name,
                        source_type="local",
                        attribution=None,
                    )
                )
        return images


class StockImageSource(ImageSourceAdapter):
    """Optional free-license stock image source. Only returns images if explicitly configured.
    
    Safe default: never hotlinks random web images or scrapes.
    """

    def __init__(self, provider: str | None = None):
        self.provider = provider

    def get_images(self, lead_id: int, category: str | None = None) -> list[ImageInfo]:
        if not self.provider:
            return []
        # In future phases, clean CC0 / Unsplash API with client attribution can be plugged in.
        return []


class CompositeImageSource(ImageSourceAdapter):
    """Chains adapters, prioritizing owner-supplied photos over fallback sources."""

    def __init__(self, sources: list[ImageSourceAdapter] | None = None):
        self.sources = sources or [LocalAssetSource(), StockImageSource()]

    def get_images(self, lead_id: int, category: str | None = None) -> list[ImageInfo]:
        for src in self.sources:
            imgs = src.get_images(lead_id, category=category)
            if imgs:
                return imgs
        return []
