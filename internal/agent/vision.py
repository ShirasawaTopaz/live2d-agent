import base64
from pathlib import Path
from typing import Any


def build_vision_messages(text: str, images: list[dict] | None = None) -> list[dict[str, Any]]:
    """Build OpenAI-compatible vision format messages.

    Text-only: returns standard format [{role: user, content: text}]
    With images: returns content array with text + image_url blocks.

    Each image dict must have 'path' and 'mime_type' keys.
    """
    if not images:
        return [{"role": "user", "content": text or ""}]

    content: list[dict[str, Any]] = []
    content.append({"type": "text", "text": text or ""})

    for img in images:
        img_path = img.get("path", "")
        mime = img.get("mime_type", "image/png")
        try:
            data = Path(img_path).read_bytes()
            b64 = base64.b64encode(data).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        except (FileNotFoundError, OSError):
            content.append({"type": "text", "text": f"[Image not found: {img_path}]"})

    return [{"role": "user", "content": content}]
