import base64

from audit_v2.extraction.preview import generate_preview

# 1x1 red PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_preview_from_image_returns_base64_jpeg():
    out = generate_preview(PNG, "image/png")
    assert out != ""
    raw = base64.b64decode(out)
    assert raw[:3] == b"\xff\xd8\xff"  # JPEG magic
    assert len(raw) < 200_000


def test_preview_empty_on_garbage():
    assert generate_preview(b"not a document", "application/pdf") == ""
    assert generate_preview(b"", "image/png") == ""
