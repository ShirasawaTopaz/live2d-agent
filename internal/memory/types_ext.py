from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"input": self.input_tokens, "output": self.output_tokens, "total": self.total_tokens}

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "TokenUsage":
        return cls(
            input_tokens=data.get("input", 0),
            output_tokens=data.get("output", 0),
            total_tokens=data.get("total", 0),
        )


@dataclass
class ImageAttachment:
    path: str
    mime_type: str
    alt_text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "mime_type": self.mime_type, "alt_text": self.alt_text}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "ImageAttachment":
        return cls(
            path=data["path"],
            mime_type=data["mime_type"],
            alt_text=data.get("alt_text", ""),
        )


def make_image_message(msg: dict[str, Any], images: list[ImageAttachment]) -> dict[str, Any]:
    msg["images"] = [img.to_dict() for img in images]
    return msg


def add_token_usage(msg: dict[str, Any], usage: TokenUsage) -> dict[str, Any]:
    msg["token_count"] = usage.to_dict()
    return msg
