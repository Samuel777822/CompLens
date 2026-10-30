import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from app.preprocess import decode_image, preprocess


def test_roundtrip_and_shape():
    img = np.full((600, 900, 3), 255, np.uint8)
    cv2.putText(img, "Net Wt. 100g", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 6)
    ok, buf = cv2.imencode(".png", img)
    out = preprocess(decode_image(buf.tobytes()))
    assert out.ndim == 2 and max(out.shape) >= 1000   # grayscale, small images upscaled


def test_big_images_are_downscaled():
    out = preprocess(np.zeros((4000, 3000, 3), np.uint8))
    assert max(out.shape) == 2000


def test_bad_bytes():
    with pytest.raises(ValueError):
        decode_image(b"junk")
