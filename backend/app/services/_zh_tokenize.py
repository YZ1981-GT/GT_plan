"""中文分词辅助模块 — 供 BM25 兜底与知识库文档词法检索使用。

V119：jieba 分词 + 审计领域自定义词典（``backend/data/jieba_audit_dict.txt``），
保证审计复合词作为单一 token（如「应收账款」）。

🔴 jieba 是**可选**依赖（spec knowledge-base-retrieval-and-authz-closure Req 1.4）：
2026-09-29 实测仓库 ``.venv`` 未装 jieba，旧版顶层 ``import jieba`` 让 BM25 兜底直接
``ModuleNotFoundError``，检索整条降级链随之断掉。缺失时降级为「CJK 连续段切二元组 +
ASCII 词」—— 召回略粗但不崩，且对 LIKE 子串匹配同样有效。

用法：
  from app.services._zh_tokenize import zh_tokenize, query_terms
  zh_tokenize("应收账款坏账准备 receivable")   # BM25 用，保留重复（词频）
  query_terms("应收账款的坏账准备如何计提")      # 检索词：去停用词/单字/重复
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 取决于运行环境
    import jieba  # type: ignore[import-not-found]

    JIEBA_AVAILABLE = True
except ImportError:  # pragma: no cover - 取决于运行环境
    jieba = None  # type: ignore[assignment]
    JIEBA_AVAILABLE = False
    logger.warning("[zh_tokenize] jieba 未安装，降级为 CJK 二元组切分（requirements.txt 已声明 jieba）")

# ─── 词典加载 (模块级单次) ────────────────────────────────────────────────────

_DICT_LOADED = False


def _ensure_dict() -> None:
    """确保审计领域词典只加载一次（jieba 不可用时无操作）。"""
    global _DICT_LOADED
    if _DICT_LOADED or not JIEBA_AVAILABLE:
        return

    dict_path = Path(__file__).resolve().parent.parent.parent / "data" / "jieba_audit_dict.txt"
    if dict_path.exists():
        jieba.load_userdict(str(dict_path))
        logger.info(f"[zh_tokenize] loaded audit dict: {dict_path}")
    else:
        logger.warning(f"[zh_tokenize] audit dict not found: {dict_path}")

    _DICT_LOADED = True


# CJK 连续段 / ASCII 词（字母数字开头，可含 _ . -）
_SEGMENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[A-Za-z0-9][A-Za-z0-9_.\-]*")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _fallback_tokens(text: str) -> List[str]:
    """jieba 缺失时的切分：CJK 段切重叠二元组（单字段保留单字），ASCII 词整体保留。"""
    out: List[str] = []
    for match in _SEGMENT_RE.finditer(text):
        seg = match.group(0)
        if _CJK_RE.match(seg):
            if len(seg) == 1:
                out.append(seg)
            else:
                out.extend(seg[i : i + 2] for i in range(len(seg) - 1))
        else:
            out.append(seg.lower())
    return out


# ─── 公共接口 ─────────────────────────────────────────────────────────────────


def zh_tokenize(text: str) -> List[str]:
    """对混合中英文文本分词，返回小写 token（可能重复，BM25 需要词频）。"""
    if not text:
        return []
    if not JIEBA_AVAILABLE:
        return _fallback_tokens(text)
    _ensure_dict()
    return [w.strip().lower() for w in jieba.cut(text) if w.strip()]


def zh_tokenize_batch(texts: List[str]) -> List[List[str]]:
    """批量分词，供 bm25s 建索引时使用。"""
    _ensure_dict()
    return [zh_tokenize(t) for t in texts]


#: 检索词停用表（单字停用词由「有多字词时丢单字」规则覆盖，这里只列多字/英文虚词）
_STOPWORDS: frozenset[str] = frozenset({
    "以及", "如何", "什么", "哪些", "及其", "关于", "有关", "怎么", "为什么", "是否", "请问",
    "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "is", "are", "be", "by", "with",
})
#: 只由标点/符号构成的 token
_PUNCT_ONLY_RE = re.compile(r"^[\W_]+$")


def query_terms(text: str, *, max_terms: int = 12) -> List[str]:
    """把查询文本转成检索词（spec Req 2.2）。

    规则：分词 → 小写 → 去纯标点/停用词 → 去重（保序）→ 有多字词时丢弃单字词
    （整句只剩单字时保留，保证「税」这类单字查询可用）→ 超过 ``max_terms`` 时优先保留长词，
    输出仍按原顺序（确定性：同输入同输出）。
    """
    raw = (text or "").strip()
    if not raw:
        return []
    terms: List[str] = []
    seen: set[str] = set()
    for token in zh_tokenize(raw):
        t = token.strip().lower()
        if not t or _PUNCT_ONLY_RE.match(t) or t in _STOPWORDS or t in seen:
            continue
        seen.add(t)
        terms.append(t)
    multi = [t for t in terms if len(t) > 1]
    if multi:
        terms = multi
    if len(terms) > max_terms:
        keep = set(sorted(range(len(terms)), key=lambda i: (-len(terms[i]), i))[:max_terms])
        terms = [t for i, t in enumerate(terms) if i in keep]
    return terms
