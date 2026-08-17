from __future__ import annotations

import asyncio
from functools import lru_cache
from importlib import import_module
from io import BytesIO
from typing import Any

from PIL import Image

from app.providers.recognition import RecognitionProviderError


class OpenCLIPImageEmbedder:
    """Lazy OpenCLIP ViT-B/32 image embedder with one model per process/device."""

    def __init__(
        self,
        *,
        model_name: str,
        pretrained: str,
        device: str,
        expected_dimension: int,
    ) -> None:
        self._model_name = model_name
        self._pretrained = pretrained
        self._device_name = device
        self._expected_dimension = expected_dimension

    async def embed(self, image_bytes: bytes) -> list[float]:
        return await asyncio.to_thread(self._embed_sync, image_bytes)

    async def warmup(self) -> None:
        await asyncio.to_thread(self._warmup_sync)

    def embed_sync(self, image_bytes: bytes) -> list[float]:
        return self._embed_sync(image_bytes)

    def _warmup_sync(self) -> None:
        try:
            import torch
        except ImportError as exc:
            raise RecognitionProviderError("OpenCLIP dependencies are not installed.") from exc
        _load_model(
            self._model_name,
            self._pretrained,
            _resolve_device(torch, self._device_name),
        )

    def _embed_sync(self, image_bytes: bytes) -> list[float]:
        try:
            import torch
        except ImportError as exc:
            raise RecognitionProviderError("OpenCLIP dependencies are not installed.") from exc

        try:
            model, _, preprocess = _load_model(
                self._model_name,
                self._pretrained,
                _resolve_device(torch, self._device_name),
            )
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            device = next(model.parameters()).device
            tensor = preprocess(image).unsqueeze(0).to(device)
            with torch.inference_mode():
                features = model.encode_image(tensor, normalize=True)
            vector = features[0].detach().cpu().tolist()
        except RecognitionProviderError:
            raise
        except Exception as exc:
            raise RecognitionProviderError("OpenCLIP image embedding failed") from exc

        if len(vector) != self._expected_dimension:
            raise RecognitionProviderError(
                f"OpenCLIP returned {len(vector)} dimensions; expected {self._expected_dimension}."
            )
        if not bool(torch.isfinite(features[0]).all()):
            raise RecognitionProviderError("OpenCLIP returned non-finite values")
        return [float(value) for value in vector]


@lru_cache(maxsize=4)
def _load_model(
    model_name: str,
    pretrained: str,
    device_name: str,
) -> tuple[Any, Any, Any]:
    open_clip = import_module("open_clip")

    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name,
        pretrained=pretrained,
        device=device_name,
    )
    model.eval()
    return model, _, preprocess


def _resolve_device(torch: Any, configured_device: str) -> str:
    if configured_device != "auto":
        return configured_device
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
