"""中文分词辅助模块 — 供 bm25s 检索降级使用。

分词决策（2026-06-04）：
  中文分词用 2-gram bigram 切分（仓库无 jieba），英文 split；不引入额外分词依赖。
  理由：
  - 仓库无 jieba/pkuseg 等中文分词库，bm25s 内置 tokenizer 仅支持英文空格分词
  - 中文审计文本（科目名/底稿内容）多为 2~4 字词，bigram 覆盖率可接受
  - 优于 ilike 的朴素子串匹配（BM25 有 TF-IDF 加权）
  - 后续可升级为 jieba 或 bm25s 自定义 tokenizer，无需改接口

用法：
  from app.services._zh_tokenize import zh_tokenize
  tokens = zh_tokenize("应收账款坏账准备 receivable allowance")
  # → ["应收", "收账", "账款", "款坏", "坏账", "账准", "准备", "receivable", "allowance"]
"""

from __future__ import annotations

import re
import unicodedata
from typing import List


# 匹配连续中文字符（CJK Unified Ideographs 基本区 + 扩展 A/B 常用范围）
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")

# 匹配连续英文/数字 token（含下划线，视为一个 token）
_LATIN_TOKEN = re.compile(r"[a-zA-Z0-9_]+")


def zh_tokenize(text: str) -> List[str]:
    """对混合中英文文本进行分词。

    - 中文部分：滑动窗口 2-gram bigram 切分
    - 英文/数字部分：按空格/标点 split + 小写化
    - 标点符号丢弃

    返回 token 列表（可能有重复，BM25 需要词频信息）。
    """
    if not text:
        return []

    tokens: List[str] = []
    # 按字符类型分段处理
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # 尝试匹配中文段
        cjk_match = _CJK_RANGE.match(text, i)
        if cjk_match:
            segment = cjk_match.group()
            # 2-gram bigram 切分
            if len(segment) == 1:
                tokens.append(segment)
            else:
                for j in range(len(segment) - 1):
                    tokens.append(segment[j : j + 2])
            i = cjk_match.end()
            continue

        # 尝试匹配英文/数字段
        latin_match = _LATIN_TOKEN.match(text, i)
        if latin_match:
            tokens.append(latin_match.group().lower())
            i = latin_match.end()
            continue

        # 跳过标点/空格等
        i += 1

    return tokens


def zh_tokenize_batch(texts: List[str]) -> List[List[str]]:
    """批量分词，供 bm25s 建索引时使用。"""
    return [zh_tokenize(t) for t in texts]
