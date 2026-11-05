"""Test media for the Status tests, generated at run time (no binary files in the repo).

- Images: solid-colour PNGs of any size, written with the standard library (JPEG / WebP
  are encoded by the browser, as there is no imaging library in the project).
- Videos: a WebM with one VP8 frame (encoded by the browser's WebCodecs VideoEncoder) and
  a Duration header, so the Status preview reports exactly the width, height and length
  asked for. Videos are served to the browser through page.route() from a fake URL; the
  server only stores the URL, it never downloads the video.
"""

import struct
import zlib

from playwright.sync_api import Page

FAKE_VIDEO_HOST = "https://qa-auto.example.com"


def png(width: int, height: int, name: str = "image.png") -> dict:
    """Playwright file payload for a solid-colour RGB PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    row = b"\x00" + b"\x40\x51\x89" * width  # filter byte + one RGB pixel per column
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height, 9))
        + chunk(b"IEND", b"")
    )
    return {"name": name, "mimeType": "image/png", "buffer": data}


def png_size(data: bytes) -> tuple[int, int]:
    """(width, height) from a PNG's IHDR chunk."""
    return struct.unpack(">II", data[16:24])


def browser_image(page: Page, width: int, height: int, mime_type: str, name: str) -> dict:
    """Playwright file payload for a solid-colour image encoded by the browser
    ("image/jpeg", "image/webp", ...)."""
    data = page.evaluate(
        """async ([width, height, type]) => {
            const canvas = new OffscreenCanvas(width, height), ctx = canvas.getContext('2d');
            ctx.fillStyle = '#405189'; ctx.fillRect(0, 0, width, height);
            const blob = await canvas.convertToBlob({ type, quality: 0.9 });
            return Array.from(new Uint8Array(await blob.arrayBuffer()));
        }""",
        [width, height, mime_type],
    )
    return {"name": name, "mimeType": mime_type, "buffer": bytes(data)}


def image_size_at(page: Page, url: str) -> tuple[int, int]:
    """(width, height) of an image URL in any format the browser decodes."""
    return tuple(
        page.evaluate(
            """url => new Promise((resolve, reject) => {
                const img = new Image();
                img.onload = () => resolve([img.naturalWidth, img.naturalHeight]);
                img.onerror = () => reject(new Error('Could not load ' + url));
                img.src = url;
            })""",
            url,
        )
    )


_ENCODE_FRAME_JS = """async ([width, height]) => {
  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#405189'; ctx.fillRect(0, 0, width, height);
  const chunks = [];
  const encoder = new VideoEncoder({
    output: (chunk) => { const bytes = new Uint8Array(chunk.byteLength); chunk.copyTo(bytes); chunks.push(bytes); },
    error: (e) => { throw e; },
  });
  encoder.configure({ codec: 'vp8', width, height, bitrate: 500000, framerate: 1 });
  const frame = new VideoFrame(canvas, { timestamp: 0 });
  encoder.encode(frame, { keyFrame: true }); frame.close();
  await encoder.flush(); encoder.close();
  return Array.from(chunks[0]);
}"""


def _element(element_id: str, data: bytes) -> bytes:
    # EBML element: id + 8-byte size + data
    return bytes.fromhex(element_id) + b"\x01" + len(data).to_bytes(7, "big") + data


def _uint(element_id: str, value: int) -> bytes:
    return _element(element_id, value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big"))


def webm(page: Page, width: int, height: int, seconds: int) -> bytes:
    """A `seconds`-long WebM of `width` x `height`. `page` must be on an https page (WebCodecs)."""
    frame = bytes(page.evaluate(_ENCODE_FRAME_JS, [width, height]))
    header = _element(
        "1A45DFA3",  # EBML: version 1, max id length 4, max size length 8, doctype webm v2
        _uint("4286", 1) + _uint("42F7", 1) + _uint("42F2", 4) + _uint("42F3", 8)
        + _element("4282", b"webm") + _uint("4287", 2) + _uint("4285", 2),
    )
    info = _element(
        "1549A966",  # Info: 1 ms timecodes, muxer names, Duration (float, ms)
        _uint("2AD7B1", 1_000_000) + _element("4D80", b"qa-auto") + _element("5741", b"qa-auto")
        + _element("4489", struct.pack(">d", seconds * 1000.0)),
    )
    tracks = _element(
        "1654AE6B",  # Tracks > TrackEntry: track 1, video, VP8, pixel size
        _element(
            "AE",
            _uint("D7", 1) + _uint("73C5", 1) + _uint("83", 1) + _element("86", b"V_VP8")
            + _element("E0", _uint("B0", width) + _uint("BA", height)),
        ),
    )
    # Cluster at 0 ms with one SimpleBlock: track 1, relative time 0, keyframe
    cluster = _element("1F43B675", _uint("E7", 0) + _element("A3", b"\x81\x00\x00\x80" + frame))
    return header + _element("18538067", info + tracks + cluster)


def serve_video(page: Page, width: int, height: int, seconds: int) -> str:
    """Generate a video and serve it to this page from a fake URL; returns the URL."""
    url = f"{FAKE_VIDEO_HOST}/status/{width}x{height}-{seconds}s.webm"
    body = webm(page, width, height, seconds)
    page.route(url, lambda route: route.fulfill(status=200, body=body, content_type="video/webm"))
    return url
