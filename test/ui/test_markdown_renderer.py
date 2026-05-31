import pytest
pytest.importorskip("PySide6")

from internal.ui.markdown_renderer import MarkdownRenderer


def test_bold_text():
    md = MarkdownRenderer()
    result = md.to_html("**hello**")
    assert "<b>hello</b>" in result


def test_italic_text():
    md = MarkdownRenderer()
    result = md.to_html("*hello*")
    assert "<i>hello</i>" in result


def test_inline_code():
    md = MarkdownRenderer()
    result = md.to_html("use `code` here")
    assert "<code>code</code>" in result


def test_code_block():
    md = MarkdownRenderer()
    result = md.to_html("```python\nprint('hi')\n```")
    assert "<pre>" in result
    assert "print('hi')" in result


def test_unordered_list():
    md = MarkdownRenderer()
    result = md.to_html("- item1\n- item2")
    assert "<ul>" in result
    assert "<li>item1</li>" in result
    assert "<li>item2</li>" in result


def test_link():
    md = MarkdownRenderer()
    result = md.to_html("[text](http://example.com)")
    assert '<a href="http://example.com">text</a>' in result


def test_plain_text_passthrough():
    md = MarkdownRenderer()
    result = md.to_html("hello world")
    assert "hello world" in result


def test_empty_string():
    md = MarkdownRenderer()
    assert md.to_html("") == ""


def test_newlines_preserved():
    md = MarkdownRenderer()
    result = md.to_html("line1\nline2")
    assert "<br>" in result
