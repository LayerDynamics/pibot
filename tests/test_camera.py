"""T8.2 — the USB-UVC camera module: grab -> resize-to-square, fail-loud on read error.

The real cv2 grab + openpi resize are injectable seams (they need cv2/numpy/openpi, which
live only in the `pibot[ml]` extra), so the unit tests drive the pipeline + error handling
with fakes. The actual 224×224 uint8 pixels are openpi's tested `image_tools`, verified on
hardware in the T8.6 open-loop run.
"""

from __future__ import annotations

import pytest

from pibot.ml.camera import Camera, CameraError


def test_capture_grabs_then_resizes_to_square() -> None:
    seen: dict = {}

    def grab() -> str:
        return "RAWFRAME"

    def resize(frame: object, size: int) -> str:
        seen.update(frame=frame, size=size)
        return "IMG-224-uint8"

    cam = Camera(capture_fn=grab, resize_fn=resize)
    cam.open()
    assert cam.is_open is True
    assert cam.capture() == "IMG-224-uint8"
    assert seen == {"frame": "RAWFRAME", "size": 224}  # squared to 224
    cam.close()
    assert cam.is_open is False


def test_capture_before_open_errors() -> None:
    cam = Camera(capture_fn=lambda: "x", resize_fn=lambda f, s: f)
    with pytest.raises(CameraError):
        cam.capture()


def test_read_failure_raises_not_a_silent_black_frame() -> None:
    cam = Camera(device="/dev/video9", capture_fn=lambda: None, resize_fn=lambda f, s: f)
    cam.open()
    with pytest.raises(CameraError, match="/dev/video9"):
        cam.capture()


def test_info_reports_device_and_size() -> None:
    cam = Camera(device="/dev/video1", size=256, capture_fn=lambda: "x", resize_fn=lambda f, s: f)
    assert cam.info == {"device": "/dev/video1", "size": 256, "open": False}
