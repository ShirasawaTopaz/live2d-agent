import re


PLACEHOLDER = "\x00CODE\x00"


class MarkdownRenderer:
    def to_html(self, text: str) -> str:
        if not text:
            return ""
        html = self._escape_html(text)
        placeholders: dict[str, str] = {}
        html = self._protect_code_blocks(html, placeholders)
        html = self._protect_inline_code(html, placeholders)
        html = self._render_lists(html)
        html = self._render_links(html)
        html = self._render_bold_italic(html)
        html = self._render_paragraphs_and_breaks(html)
        html = self._restore_placeholders(html, placeholders)
        return html

    def _escape_html(self, text: str) -> str:
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

    def _protect_code_blocks(self, html: str, placeholders: dict[str, str]) -> str:
        def replacer(m: re.Match) -> str:
            lang = m.group(1) or ""
            code = m.group(2)
            unescaped = code.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            rendered = f"<pre><code{(' class=\"lang-' + lang + '\"') if lang else ''}>{self._escape_html(unescaped)}</code></pre>"
            key = f"{PLACEHOLDER}{len(placeholders)}{PLACEHOLDER}"
            placeholders[key] = rendered
            return key
        return re.sub(r"```(\w*)\n(.*?)```", replacer, html, flags=re.DOTALL)

    def _protect_inline_code(self, html: str, placeholders: dict[str, str]) -> str:
        def replacer(m: re.Match) -> str:
            code = m.group(1)
            rendered = f"<code>{code}</code>"
            key = f"{PLACEHOLDER}{len(placeholders)}{PLACEHOLDER}"
            placeholders[key] = rendered
            return key
        return re.sub(r"`([^`\n]+)`", replacer, html)

    def _render_lists(self, html: str) -> str:
        lines = html.split("\n")
        result: list[str] = []
        in_list = False
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                result.append(f"<li>{stripped[2:]}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ul>")
        return "\n".join(result)

    def _render_links(self, html: str) -> str:
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

    def _render_bold_italic(self, html: str) -> str:
        html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
        html = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", html)
        return html

    def _render_paragraphs_and_breaks(self, html: str) -> str:
        parts = html.split("\n\n")
        rendered: list[str] = []
        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            if stripped.startswith("<ul>") or stripped.startswith("<pre>"):
                rendered.append(stripped)
            else:
                with_breaks = stripped.replace("\n", "<br>")
                rendered.append(f"<p>{with_breaks}</p>")
        return "\n".join(rendered)

    def _restore_placeholders(self, html: str, placeholders: dict[str, str]) -> str:
        for key, value in placeholders.items():
            html = html.replace(key, value)
        return html
