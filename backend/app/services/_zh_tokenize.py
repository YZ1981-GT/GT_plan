"""中文分词辅助模块 — 供 bm25s 检索降级使用。

V119 升级: 使用 jieba 分词 + 审计领域自定义词典。
  - 加载 backend/data/jieba_audit_dict.txt (500+ 审计术语)
  - 确保审计复合词作为单一 token (如 "应收账款" → ["应收账款"])
  - 保留向后兼容接口: zh_tokenize / zh_tokenize_batch

用法：
  from app.services._zh_tokenize import zh_tokenize
  tokens = zh_tokenize("应收账款坏账准备 receivable allowance")
  # → ["应收账款", "坏账", "准备", "receivable", "allowance"]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import jieba

logger = logging.getLogger(__name__)

# ─── 词典加载 (模块级单次) ────────────────────────────────────────────────────

_DICT_LOADED = False


def _ensure_dict() -> None:
    """确保审计领域词典只加载一次。"""
    global _DICT_LOADED
    if _DICT_LOADED:
        return

    dict_path = Path(__file__).resolve().parent.parent.parent / "data" / "jieba_audit_dict.txt"
    if dict_path.exists():
        jieba.load_userdict(str(dict_path))
        logger.info(f"[zh_tokenize] loaded audit dict: {dict_path}")
    else:
        logger.warning(f"[zh_tokenize] audit dict not found: {dict_path}")

    _DICT_LOADED = True


# ─── 公共接口 ─────────────────────────────────────────────────────────────────


def zh_tokenize(text: str) -> List[str]:
    """对混合中英文文本进行分词。

    - 使用 jieba 精确模式切分
    - 加载审计领域自定义词典保证专业术语为单一 token
    - 过滤空白 token

    返回 token 列表（可能有重复，BM25 需要词频信息）。
    """
    if not text:
        return []

    _ensure_dict()
    return [w.strip().lower() for w in jieba.cut(text) if w.strip()]


def zh_tokenize_batch(texts: List[str]) -> List[List[str]]:
    """批量分词，供 bm25s 建索引时使用。"""
    _ensure_dict()
    return [zh_tokenize(t) for t in texts]
