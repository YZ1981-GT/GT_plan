"""附注富文本 HTML 消毒器 — 最小白名单，canonical 输出。

spec: disclosure-note-doc-upload-and-batch-fill Phase 2 Task 11

🔴 禁止 script/iframe/object/embed/on*，禁止 style 属性和危险 URL。
   所有文本/属性重新转义；未知标签/属性被剥离。
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from io import StringIO

__all__ = [
    "ALLOWED_TAGS",
    "ALLOWED_ATTRS",
    "sanitize_note_html",
]

ALLOWED_TAGS: frozenset[str] = frozenset({
    "p", "br", "strong", "em",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "th", "td",
    "h1", "h2", "h3", "h4", "h5",
    "blockquote", "span", "hr",
})

ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
    "span": frozenset({"class", "data-placeholder", "contenteditable"}),
}

_ALLOWED_CLASS_VALUES: frozenset[str] = frozenset({
    "gt-note-placeholder",
})

_VOID_TAGS: frozenset[str] = frozenset({"br", "hr"})


class _Sanitizer(HTMLParser):
    """单遍流式解析 + 重建。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._buf = StringIO()
        self._open_stack: list[str] = []
        self._strip_depth: int = 0  # 在被剥离标签内时 > 0，吞掉内部一切内容

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            self._strip_depth += 1
            return
        if self._strip_depth > 0:
            return
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        safe_attrs: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed:
                continue
            val = escape(value or "", quote=True)
            if name == "class" and val not in _ALLOWED_CLASS_VALUES:
                continue
            if name == "contenteditable" and val not in ("true", "false"):
                continue
            safe_attrs.append(f' {name}="{val}"')
        attr_str = "".join(safe_attrs)
        if tag in _VOID_TAGS:
            self._buf.write(f"<{tag}{attr_str} />")
        else:
            self._buf.write(f"<{tag}{attr_str}>")
            self._open_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            if self._strip_depth > 0:
                self._strip_depth -= 1
            return
        if self._strip_depth > 0:
            return
        if tag in _VOID_TAGS:
            return
        if tag in self._open_stack:
            idx = len(self._open_stack) - 1 - self._open_stack[::-1].index(tag)
            for unclosed in reversed(self._open_stack[idx + 1:]):
                self._buf.write(f"</{unclosed}>")
            self._buf.write(f"</{tag}>")
            self._open_stack = self._open_stack[:idx]

    def handle_data(self, data: str) -> None:
        if self._strip_depth > 0:
            return
        self._buf.write(escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._strip_depth > 0:
            return
        self._buf.write(f"&{escape(name)};")

    def handle_charref(self, name: str) -> None:
        if self._strip_depth > 0:
            return
        self._buf.write(f"&#{escape(name)};")

    def close(self) -> None:
        super().close()
        for tag in reversed(self._open_stack):
            self._buf.write(f"</{tag}>")
        self._open_stack.clear()
        self._strip_depth = 0

    def get_result(self) -> str:
        return self._buf.getvalue()


def sanitize_note_html(html: str) -> str:
    """对附注富文本做 canonical 消毒。

    - 只保留 ALLOWED_TAGS / ALLOWED_ATTRS 中声明的标签和属性。
    - class 属性值必须精确等于白名单项之一。
    - 所有文本和属性值重新转义。
    - 消毒幂等：``sanitize(sanitize(x)) == sanitize(x)``。
    """
    if not html:
        return ""
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return parser.get_result()
