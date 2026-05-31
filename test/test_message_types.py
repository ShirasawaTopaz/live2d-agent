from internal.memory.types_ext import TokenUsage, ImageAttachment, make_image_message, add_token_usage


class TestTokenUsage:
    def test_creates_with_all_fields(self):
        tu = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        assert tu.input_tokens == 10
        assert tu.output_tokens == 20
        assert tu.total_tokens == 30

    def test_to_dict_roundtrip(self):
        tu = TokenUsage(input_tokens=5, output_tokens=15, total_tokens=20)
        d = tu.to_dict()
        restored = TokenUsage.from_dict(d)
        assert restored.input_tokens == 5
        assert restored.output_tokens == 15
        assert restored.total_tokens == 20


class TestImageAttachment:
    def test_creates_with_minimal_fields(self):
        img = ImageAttachment(path="/tmp/test.png", mime_type="image/png")
        assert img.path == "/tmp/test.png"
        assert img.mime_type == "image/png"
        assert img.alt_text == ""

    def test_to_dict_roundtrip(self):
        img = ImageAttachment(path="/img.png", mime_type="image/png", alt_text="screenshot")
        d = img.to_dict()
        restored = ImageAttachment.from_dict(d)
        assert restored.path == "/img.png"
        assert restored.alt_text == "screenshot"


class TestMakeImageMessage:
    def test_adds_images_to_message(self):
        msg = {"role": "user", "content": "what is this?"}
        imgs = [ImageAttachment(path="/img.png", mime_type="image/png")]
        result = make_image_message(msg, imgs)
        assert result["role"] == "user"
        assert result["content"] == "what is this?"
        assert len(result["images"]) == 1
        assert result["images"][0]["path"] == "/img.png"


class TestAddTokenUsage:
    def test_adds_usage_to_message(self):
        msg = {"role": "assistant", "content": "hello"}
        tu = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        result = add_token_usage(msg, tu)
        assert result["token_count"]["input"] == 10
        assert result["token_count"]["output"] == 20
        assert result["token_count"]["total"] == 30
