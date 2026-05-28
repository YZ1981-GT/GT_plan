"""Sprint A.4.1 — 附注文字段落 Jinja 渲染引擎.

提供一个全局 Jinja Environment + 自定义 filter，用于渲染附注章节文字段落
（如「公司基本情况」「会计政策」），让段落不再写死字符串，而按企业类型/
规模/上市状态等动态变量填充。

主要 API:
- ``render_text_paragraph(template_str, vars, *, rendered_numbers=None) -> str``
- ``get_jinja_env(rendered_numbers=None) -> Environment``  # 测试 / Word 导出共用
- ``extract_template_variables(template_str) -> set[str]``  # CI-11 用

支持的 filter:
- ``format_amount``  数字 → "1,234,567.89"（千分位 + 2 位小数；None → ""）
- ``cn_number``      整数 → 中文数字（复用 note_section_numbering_service.cn_number）
- ``date_cn``        ISO 日期/datetime → "2025年12月31日"

支持的全局函数:
- ``ref(section_id)``  解析章节内部引用（注入 rendered_numbers）

设计原则：
- strict 模式：未声明变量抛 UndefinedError（CI-11 卡点）
- 纯函数 / 无 DB / 无副作用
- env autoescape 关闭（输出到 Word docx 不需要 HTML escape）
- env trim_blocks=True / lstrip_blocks=True（让 Jinja 控制结构不引入多余空白）
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from jinja2 import (
    BaseLoader,
    ChainableUndefined,
    Environment,
    StrictUndefined,
    meta,
)

from app.services.note_section_numbering_service import (
    cn_number as _cn_number_int,
    make_jinja_ref_function,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def format_amount(value: Any) -> str:
    """数字 → 千分位字符串（保留 2 位小数）.

    - ``None`` → ``""``
    - ``Decimal`` / ``int`` / ``float`` → ``"1,234,567.89"``
    - 数字字符串 → 同上（先 cast 成 Decimal）
    - 非数字字符串 → 原样返回
    - 异常一律吞掉（永不抛错）
    """
    if value is None:
        return ""
    try:
        if isinstance(value, bool):
            # bool 是 int 的子类，但语义上不该走数字格式
            return str(value)
        if isinstance(value, Decimal):
            num = value
        elif isinstance(value, (int, float)):
            num = Decimal(str(value))
        elif isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ""
            try:
                num = Decimal(stripped.replace(",", ""))
            except (InvalidOperation, ValueError):
                return value  # 非数字字符串原样返回
        else:
            return str(value)
        # 千分位 + 2 位小数（用 Python 内建 format，Decimal 直接支持）
        return f"{num:,.2f}"
    except Exception as exc:  # pragma: no cover - 防御性
        logger.warning("format_amount failed for %r: %s", value, exc)
        return str(value) if value is not None else ""


def jinja_cn_number_filter(value: Any) -> str:
    """整数 → 中文数字（复用 note_section_numbering_service.cn_number）.

    - ``1``  → ``"一"``
    - ``35`` → ``"三十五"``
    - ``99`` → ``"九十九"``
    - 100+ 回退原数字字符串
    - ``None`` / 非数 → ``""``
    """
    if value is None:
        return ""
    try:
        i = int(value)
    except (TypeError, ValueError):
        return ""
    return _cn_number_int(i)


def format_date_cn(value: Any) -> str:
    """日期 → ``"YYYY年MM月DD日"``.

    支持入参：
    - ``date`` / ``datetime`` 实例
    - ``"YYYY-MM-DD"`` 字符串
    - ``"YYYY-MM-DDTHH:MM:SS"`` ISO datetime 字符串

    非法 / ``None`` → ``""``。
    """
    if value is None:
        return ""
    dt: date | None = None
    if isinstance(value, datetime):
        dt = value.date()
    elif isinstance(value, date):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        # 尝试 datetime.fromisoformat（支持 YYYY-MM-DD 与 ISO datetime）
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            dt = parsed.date()
        except ValueError:
            # 尝试常见 fallback
            for fmt in ("%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
                try:
                    dt = datetime.strptime(s, fmt).date()
                    break
                except ValueError:
                    continue
    if dt is None:
        return ""
    return f"{dt.year}年{dt.month}月{dt.day}日"


# ---------------------------------------------------------------------------
# Environment 工厂
# ---------------------------------------------------------------------------


def get_jinja_env(
    rendered_numbers: dict[str, str] | None = None,
    *,
    strict: bool = True,
) -> Environment:
    """生成 Jinja Environment（每次调用新建，避免 globals 污染）.

    Args:
        rendered_numbers: 章节序号字典（来自 NoteSectionNumberingService）。
            若给出则注入 ``ref()`` 全局函数；否则注入占位 ``ref()``。
        strict: True=未声明变量抛 UndefinedError（CI-11）；False=未声明变量
            按 ChainableUndefined 渲染为空（向下兼容旧模板）。
    """
    env = Environment(
        loader=BaseLoader(),
        undefined=StrictUndefined if strict else ChainableUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    env.filters["format_amount"] = format_amount
    env.filters["cn_number"] = jinja_cn_number_filter
    env.filters["date_cn"] = format_date_cn

    if rendered_numbers is not None:
        env.globals["ref"] = make_jinja_ref_function(rendered_numbers)
    else:
        # 默认 ref — 警告 + 占位（避免崩，但提示注入缺失）
        def _placeholder_ref(sid: str) -> str:
            logger.debug("ref() called without rendered_numbers, sid=%s", sid)
            return f"[未注入序号: {sid}]"
        env.globals["ref"] = _placeholder_ref

    return env


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_text_paragraph(
    template_str: str,
    vars: dict[str, Any] | None = None,
    *,
    rendered_numbers: dict[str, str] | None = None,
    strict: bool = True,
) -> str:
    """渲染单个文字段落.

    Args:
        template_str: Jinja 模板字符串
        vars: 模板变量字典
        rendered_numbers: 章节序号字典（用于 ``ref()`` 函数）
        strict: True=未声明变量抛错（CI-11）；False=未声明变量替换为空字符串

    Returns:
        渲染后的字符串。

    Raises:
        UndefinedError: strict=True 且模板用了 vars 中没有的变量
        TemplateSyntaxError: 模板语法错误
    """
    if not template_str:
        return ""
    env = get_jinja_env(rendered_numbers=rendered_numbers, strict=strict)
    tmpl = env.from_string(template_str)
    return tmpl.render(**(vars or {}))


def extract_template_variables(template_str: str) -> set[str]:
    """从 Jinja 模板提取所有引用的变量名（用于 CI-11）.

    支持 ``{{ var }}`` / ``{% if var %}`` / ``{% for x in var %}`` 等标准用法。
    自带的全局函数（``ref``）和 filter 名（``format_amount`` / ``cn_number`` /
    ``date_cn``）不会出现在结果中（meta.find_undeclared_variables 已排除）。
    """
    if not template_str:
        return set()
    env = get_jinja_env(strict=False)
    parsed = env.parse(template_str)
    return meta.find_undeclared_variables(parsed)
