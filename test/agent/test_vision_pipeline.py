from internal.agent.vision import build_vision_messages


def test_build_vision_messages_text_only():
    result = build_vision_messages("hello")
    assert result == [{"role": "user", "content": "hello"}]


def test_build_vision_messages_empty_text():
    result = build_vision_messages("")
    assert result == [{"role": "user", "content": ""}]


def test_build_vision_messages_with_images(tmp_path):
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"fake_png_bytes")
    images = [{"path": str(img_path), "mime_type": "image/png"}]
    result = build_vision_messages("what is this?", images)
    assert len(result) == 1
    content = result[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_build_vision_messages_image_not_found():
    images = [{"path": "/nonexistent/img.png", "mime_type": "image/png"}]
    result = build_vision_messages("where?", images)
    assert "Image not found" in str(result)


def test_build_vision_messages_no_images_none():
    result = build_vision_messages("hello", None)
    assert result == [{"role": "user", "content": "hello"}]
