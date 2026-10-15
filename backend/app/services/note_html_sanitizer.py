"""附注富文本 HTML 消毒器 — 最小白名单，canonical 输出。

spec: disclosure-note-doc-upload-and-batch-fill Phase 2 Task 11（第二轮复盘 R-05 / R-10 修订）

三类标签分治（R-05：首版对所有非白名单标签整段吞内容，``<img>`` 这类 void 元素
没有结束标签 ⇒ 深度永不回落 ⇒ 其后全部正文被吞）：

1. 白名单标签：保留标签与校验后的属性；
2. 危险容器（script/style/iframe/object/...）：标签与其**内部全部内容**一并丢弃；
3. 其余未知标签：只剥标签、保留内部文本（``b``/``i`` 映射为 ``strong``/``em``）。

🔴 禁止任意 style/href/事件属性；所有文本与属性值重新转义；输出幂等。
"""

from __future__ import annotations

import re
from functools import lru_cache
from html import escape, unescape
from html.entities import html5 as _HTML5_ENTITIES
from html.parser import HTMLParser

__all__ = [
    "ALLOWED_TAGS",
    "ALLOWED_ATTRS",
    "APPEND_SEPARATOR",
    "append_note_html",
    "has_visible_text",
    "is_html_note_text",
    "note_text_to_html",
    "sanitize_note_html",
    "split_top_level_blocks",
]

#: 判定「正文是 HTML」：出现附注编辑器 / 消毒器认识的标签之一。``<`` 后不允许空白（真实标签没有），
#: 否则 ``a < b 且 c > d`` 会被当成 ``<b …>``；``<公司名称>`` 这类中文尖括号也不命中。
#: Word 渲染（note_text_word_render）与批量写入共用这一个判据。
_HTML_TAG = re.compile(
    r"</?(?:p|br|div|span|strong|em|b|i|u|ul|ol|li|h[1-6]|table|thead|tbody|tfoot|tr|td|th|blockquote|hr)\b[^>]*>",
    re.IGNORECASE,
)

#: ``&`` 后可能构成字符引用的部分（数字引用 / 实体名，分号可有可无）
_AMP_REF = re.compile(r"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[A-Za-z][A-Za-z0-9]*;?)?")


def is_html_note_text(text: str | None) -> bool:
    return bool(text) and bool(_HTML_TAG.search(text))


def _escape_bare_ampersands(html: str) -> str:
    """不构成字符引用的 ``&`` 是文字（``R&D``、``P&L``、``AT&T``）⇒ ``&amp;``。

    🔴 首版交给 HTMLParser：它把「&D）」当实体名 ``D`` 回调，消毒器原样补分号 ⇒ ``R&D`` → ``R&D;``（可见乱码；
    第 19 组发现，真库有「DD&A」「P&L」）。口径与浏览器一致：数字引用、已知实体（含无分号的旧式实体如
    ``&nbsp``）保留，其余 ``&`` 一律是文字。
    """
    def fix(match: re.Match[str]) -> str:
        ref = match.group(1)
        if ref and (ref.startswith("#") or ref in _HTML5_ENTITIES):
            return match.group(0)
        return "&amp;" + (ref or "")

    return _AMP_REF.sub(fix, html)

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

_ALLOWED_CLASS_VALUES: frozenset[str] = frozenset({"gt-note-placeholder"})

#: 白名单内的 void 标签（输出自闭合形式）
_VOID_TAGS: frozenset[str] = frozenset({"br", "hr"})

#: 危险容器：标签与内部全部内容一并丢弃
_DROP_CONTENT_TAGS: frozenset[str] = frozenset({
    "script", "style", "iframe", "object", "embed", "applet", "noscript",
    "noembed", "noframes", "template", "svg", "math", "head", "title",
    "textarea", "select", "frameset", "frame",
})

#: HTML void 元素：没有结束标签，绝不能参与深度计数
_HTML_VOID_ELEMENTS: frozenset[str] = frozenset({
    "area", "base", "br", "col", "embed", "frame", "hr", "img", "input",
    "keygen", "link", "meta", "param", "source", "track", "wbr",
})

#: 语义等价映射（Word/外部 HTML 常用 b/i）
_TAG_ALIASES: dict[str, str] = {"b": "strong", "i": "em"}

#: 块级标签：顶层切块（段落级去重）的边界
_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
    "h1", "h2", "h3", "h4", "h5", "blockquote", "hr",
})

_SPAN_NUMBER_RE = re.compile(r"^[1-9]\d{0,2}$")

#: 追加正文时的规范空段（不写任何来源/审计文字，AC-10.5）
APPEND_SEPARATOR = "<p>&nbsp;</p>"


class _Sanitizer(HTMLParser):
    """单遍流式解析 + canonical 重建，同时记录顶层块边界。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        self._open_stack: list[str] = []
        self._drop_depth = 0  # 位于危险容器内部时 > 0
        self._block_start = 0  # 当前未完成顶层块在 _out 中的起点
        self.blocks: list[str] = []

    # ── 块边界 ────────────────────────────────────────────────────────────
    def _cut_block(self) -> None:
        if len(self._out) > self._block_start:
            self.blocks.append("".join(self._out[self._block_start:]))
        self._block_start = len(self._out)

    # ── 标签 ──────────────────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _TAG_ALIASES.get(tag.lower(), tag.lower())
        if tag in _DROP_CONTENT_TAGS:
            if tag not in _HTML_VOID_ELEMENTS:
                self._drop_depth += 1
            return
        if self._drop_depth > 0 or tag not in ALLOWED_TAGS:
            return  # 未知标签：剥标签、保留文本
        if tag in _BLOCK_TAGS and not self._open_stack:
            self._cut_block()  # 顶层块开始前，先切出悬挂的行内内容
        attr_str = "".join(self._safe_attrs(tag, attrs))
        if tag in _VOID_TAGS:
            self._out.append(f"<{tag}{attr_str} />")
            if tag in _BLOCK_TAGS and not self._open_stack:
                self._cut_block()
            return
        self._out.append(f"<{tag}{attr_str}>")
        self._open_stack.append(tag)

    @staticmethod
    def _safe_attrs(tag: str, attrs: list[tuple[str, str | None]]) -> list[str]:
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        out: list[str] = []
        for name, value in attrs:
            name = name.lower()
            raw = value or ""
            if name not in allowed:
                continue
            if name in ("colspan", "rowspan") and not _SPAN_NUMBER_RE.match(raw):
                continue
            if name == "class" and raw not in _ALLOWED_CLASS_VALUES:
                continue
            if name == "contenteditable" and raw not in ("true", "false"):
                continue
            out.append(f' {name}="{escape(raw, quote=True)}"')
        return out

    def handle_endtag(self, tag: str) -> None:
        tag = _TAG_ALIASES.get(tag.lower(), tag.lower())
        if tag in _DROP_CONTENT_TAGS:
            if tag not in _HTML_VOID_ELEMENTS and self._drop_depth > 0:
                self._drop_depth -= 1
            return
        if self._drop_depth > 0 or tag not in ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        if tag not in self._open_stack:
            return
        idx = len(self._open_stack) - 1 - self._open_stack[::-1].index(tag)
        for unclosed in reversed(self._open_stack[idx + 1:]):
            self._out.append(f"</{unclosed}>")
        self._out.append(f"</{tag}>")
        self._open_stack = self._open_stack[:idx]
        if not self._open_stack and tag in _BLOCK_TAGS:
            self._cut_block()

    # ── 文本与实体 ────────────────────────────────────────────────────────
    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            self._out.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._drop_depth == 0:
            self._out.append(f"&{escape(name)};")

    def handle_charref(self, name: str) -> None:
        if self._drop_depth == 0:
            self._out.append(f"&#{escape(name)};")

    def close(self) -> None:
        super().close()
        for tag in reversed(self._open_stack):
            self._out.append(f"</{tag}>")
        self._open_stack.clear()
        self._drop_depth = 0
        self._cut_block()

    def get_result(self) -> str:
        return "".join(self._out)


def _run(html: str) -> _Sanitizer:
    parser = _Sanitizer()
    parser.feed(_escape_bare_ampersands(html or ""))
    parser.close()
    return parser


def sanitize_note_html(html: str) -> str:
    """对附注富文本做 canonical 消毒；幂等：``sanitize(sanitize(x)) == sanitize(x)``。"""
    if not html:
        return ""
    return _run(html).get_result()


def split_top_level_blocks(html: str) -> list[str]:
    """消毒后按顶层块切分（段落、列表、表格、标题…）；纯空白块不返回。"""
    if not html:
        return []
    return [block for block in _run(html).blocks if block.strip()]


def has_visible_text(html: str | None) -> bool:
    """HTML 去标签、反转义后是否还有非空白文字（``<p>&nbsp;</p>`` 视为空）。"""
    return bool(unescape(re.sub(r"<[^>]+>", "", html or "")).strip())


@lru_cache(maxsize=1)
def _markdown():
    from markdown_it import MarkdownIt

    # 与编辑器 renderNoteTextToHtml 的 marked(gfm, breaks) 同口径：GFM 表格 / 删除线，单换行即 <br>；
    # 纯文字里的尖括号一律按文字（html=False）
    return MarkdownIt("commonmark", {"breaks": True, "html": False}).enable(["table", "strikethrough"])


def note_text_to_html(text: str | None) -> str:
    """附注正文统一为消毒后的 HTML（编辑器口径）。幂等。

    ``text_content`` 多数是纯文字（生成链写入，含换行、markdown 表格 / 列表），编辑器加载时按 markdown 渲染
    （``DisclosureEditor.renderNoteTextToHtml``）。批量写入（第 19 组）首版把纯文字直接当 HTML：追加时存成
    「纯文字 + <p>…</p>」混合值，原有分段在差异预览与 Word 里都并成一段；模板纯文字来源同理。
    已是 HTML（:func:`is_html_note_text`）只消毒。
    """
    if not text or not text.strip():
        return ""
    if is_html_note_text(text):
        return sanitize_note_html(text)
    rendered = _markdown().render(text)
    # markdown-it 在块后、<br /> 后补换行：文字里的 > 已转义，故「>\n」「\n<」只会出现在标签边上，去掉不改内容
    return sanitize_note_html(rendered.replace(">\n", ">").replace("\n<", "<"))


def append_note_html(existing: str, new: str) -> str:
    """把 ``new`` 追加到 ``existing``（design §7.2 第 6 步 / AC-9.3 / AC-10.5）。

    - 两侧都先按编辑器口径统一为消毒后的 HTML（:func:`note_text_to_html`：纯文字的分段 / 表格 / 列表保留），
      结果即最终写入值（与 preview 逐字一致）；
    - 按顶层段落去重：``new`` 中已在 ``existing`` 出现的块不重复追加；
    - 只用规范空段 :data:`APPEND_SEPARATOR` 连接，不写来源/审计文字；
    - ``new`` 无可见内容时原样返回 ``existing``（统一后）。
    """
    base = note_text_to_html(existing or "")
    seen = set(split_top_level_blocks(base))
    kept: list[str] = []
    for block in split_top_level_blocks(note_text_to_html(new or "")):
        if block in seen or not has_visible_text(block):
            continue
        seen.add(block)
        kept.append(block)
    if not kept:
        return base
    if not base.strip():
        return "".join(kept)
    return base.rstrip() + APPEND_SEPARATOR + "".join(kept)
