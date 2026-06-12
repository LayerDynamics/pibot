"""USB-UVC camera capture for the VLA observation pipeline (SPEC-2 / M8).

``capture()`` grabs a frame and squares it to ``size × size`` ``uint8`` — the shape π₀.₅
expects. The raw grab (cv2) and the resize (openpi ``image_tools``) are injectable seams
so the pipeline + failure handling are unit-tested without cv2/numpy/openpi (the
``pibot[ml]`` extra); their real implementations are imported lazily on the robot. A read
failure raises loudly — a frozen/black frame would silently feed garbage to the policy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pibot.errors import PibotError


class CameraError(PibotError):
    """The camera could not be opened or returned no frame."""


class Camera:
    def __init__(
        self,
        device: str = "/dev/video0",
        *,
        size: int = 224,
        capture_fn: Callable[[], Any] | None = None,
        resize_fn: Callable[[Any, int], Any] | None = None,
    ) -> None:
        self._device = device
        self._size = size
        self._capture_fn = capture_fn
        self._resize_fn = resize_fn
        self._open = False

    def open(self) -> None:
        if self._capture_fn is None:
            self._capture_fn = self._default_capture()
        if self._resize_fn is None:
            self._resize_fn = self._default_resize
        self._open = True

    def capture(self) -> Any:
        """Return one ``uint8[size,size,3]`` frame (raises on a read failure)."""
        if not self._open or self._capture_fn is None or self._resize_fn is None:
            raise CameraError("camera not open")
        frame = self._capture_fn()
        if frame is None:
            raise CameraError(f"camera read failed on {self._device}")
        return self._resize_fn(frame, self._size)

    def close(self) -> None:
        self._open = False
        cap = getattr(self, "_cap", None)
        if cap is not None:
            cap.release()
            self._cap = None

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def info(self) -> dict[str, Any]:
        return {"device": self._device, "size": self._size, "open": self._open}

    def _default_capture(self) -> Callable[[], Any]:  # pragma: no cover - real cv2/hardware
        import cv2

        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            raise CameraError(f"could not open camera {self._device}")

        def grab() -> Any:
            ok, frame = cap.read()
            return frame if ok else None

        self._cap = cap  # keep a reference so it isn't GC'd
        return grab

    def _default_resize(self, frame: Any, size: int) -> Any:  # pragma: no cover - real openpi/numpy
        from openpi_client import image_tools

        return image_tools.convert_to_uint8(image_tools.resize_with_pad(frame, size, size))
