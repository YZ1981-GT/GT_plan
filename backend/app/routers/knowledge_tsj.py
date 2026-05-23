"""K-2 审计复核提示词（TSJ）路由

spec proposal-remaining-18 task 2.5

提供 GET /api/knowledge/tsj/{cycle_name} 端点，按 cycle_name 返回对应的
审计复核提示词 Markdown 内容。

cycle_name 支持两种形式（前端按 wp_code 前缀映射后传入）：
  1. 字母代号：D / E / F / G / H / I / J / K / L / M / N / S（按 cycle 字母）
  2. 中文名：货币资金 / 应收账款 / 存货 等（直接业务名称匹配 TSJ 文件名前缀）

Markdown 文件位于仓库根 `TSJ/` 目录，部署时可通过环境变量
`TSJ_KNOWLEDGE_DIR` 覆盖。

Validates: requirements §二 K-2 / design.md ADR-5
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-tsj"])


# ─── 路径解析 ────────────────────────────────────────────────────────────────

# 仓库根 / TSJ 目录（默认）
# backend/app/routers/knowledge_tsj.py → parents[3] = 仓库根
_TSJ_DIR_DEFAULT = Path(__file__).resolve().parents[3] / "TSJ"


def _resolve_tsj_dir() -> Path:
    """返回 TSJ 目录路径。

    覆盖优先级：
      1. 环境变量 TSJ_KNOWLEDGE_DIR
      2. <仓库根>/TSJ (默认)
    """
    env_path = os.environ.get("TSJ_KNOWLEDGE_DIR")
    if env_path:
        return Path(env_path)
    return _TSJ_DIR_DEFAULT


# ─── 字母代号 → 关键字映射 ──────────────────────────────────────────────────
#
# 当 cycle_name 是单字母代号时，按以下关键词列表逐个尝试在 TSJ 目录中
# fuzzy 匹配文件名（按出现顺序优先）。若多个关键词命中同一字母代号，
# 取列表第 1 个匹配到文件的作为优先；若全部未命中返回 404。
#
# 数据来源：致同 2025 修订版 D/F/K/N 循环（详见 memory.md）
#   D = 销售收入循环
#   E = 货币资金
#   F = 采购存货
#   G = 投资
#   H = 固定资产 / 在建工程 / 使用权资产
#   I = 无形资产 / 商誉 / 开发支出
#   J = 职工薪酬 / 股份支付
#   K = 其他/费用类（销售费用/管理费用/财务费用等）
#   L = 筹资（短期借款/长期借款/应付债券/租赁负债等）
#   M = 股东权益（实收资本/资本公积/其他综合收益）
#   N = 税费（应交税费/递延所得税资产/递延所得税负债/所得税费用）
#   S = 专项程序（如审计方案）
#
# 注意：返回的是字母代号下"首选"的文件，不代表覆盖全部该循环底稿。
# 复杂场景（多张审定表分别对应不同 TSJ）由前端按 wp_code 直接传中文 cycle_name。
_LETTER_KEYWORDS: dict[str, list[str]] = {
    "D": ["收入", "应收账款"],
    "E": ["货币资金"],
    "F": ["存货", "应付账款"],
    "G": ["长期股权投资", "投资性房地产", "交易性金融资产", "债权投资"],
    "H": ["固定资产", "在建工程", "使用权资产"],
    "I": ["无形资产", "商誉", "开发支出"],
    "J": ["应付职工薪酬"],
    "K": ["管理费用", "销售费用", "财务费用"],
    "L": ["短期借款", "长期借款", "应付债券", "租赁负债"],
    "M": ["实收资本或股本", "资本公积", "其他综合收益"],
    "N": ["应交税费", "所得税费用", "递延所得税资产", "递延所得税负债"],
    "S": ["审计方案"],
}


def _list_tsj_files(tsj_dir: Path) -> list[Path]:
    """列出 TSJ 目录下的所有 .md 文件。"""
    if not tsj_dir.exists() or not tsj_dir.is_dir():
        return []
    return sorted(tsj_dir.glob("*.md"))


def _match_by_keyword(files: list[Path], keyword: str) -> Path | None:
    """在文件列表中查找文件名包含 keyword 的第一个文件。"""
    kw = keyword.strip()
    if not kw:
        return None
    for f in files:
        if kw in f.stem:
            return f
    return None


def _resolve_tsj_file(cycle_name: str) -> Path | None:
    """根据 cycle_name 解析出对应的 TSJ Markdown 文件。

    匹配顺序：
      1. 单字母代号（如 D / E / F …） → 按 _LETTER_KEYWORDS 关键字列表
         逐个尝试，取首个命中的文件
      2. 中文/其他字符串（如 "货币资金"） → 直接做子串匹配
      3. 都未命中 → None（路由层抛 404）
    """
    if not cycle_name:
        return None
    tsj_dir = _resolve_tsj_dir()
    files = _list_tsj_files(tsj_dir)
    if not files:
        return None

    name = cycle_name.strip()

    # 单字母代号匹配（不区分大小写）
    if len(name) == 1 and name.upper() in _LETTER_KEYWORDS:
        for kw in _LETTER_KEYWORDS[name.upper()]:
            hit = _match_by_keyword(files, kw)
            if hit is not None:
                return hit
        return None

    # 中文/业务名匹配
    return _match_by_keyword(files, name)


# ─── 路由 ───────────────────────────────────────────────────────────────────


@router.get("/api/knowledge/tsj/{cycle_name}")
async def get_tsj_prompt(
    cycle_name: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回指定 cycle 的审计复核提示词 Markdown。

    Args:
        cycle_name: 循环代号（D/E/F/...）或中文业务名（货币资金/存货 等）

    Returns:
        {markdown: str, source_file: str, cycle_name: str}

    Raises:
        404: cycle_name 未匹配到任何 TSJ 文件，或 TSJ 目录缺失
    """
    file_path = _resolve_tsj_file(cycle_name)
    if file_path is None:
        logger.info("TSJ prompt not found for cycle_name=%s", cycle_name)
        raise HTTPException(
            status_code=404,
            detail=f"未找到 cycle '{cycle_name}' 对应的审计复核提示词",
        )

    try:
        markdown = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Failed to read TSJ file %s: %s", file_path, e)
        raise HTTPException(
            status_code=503,
            detail=f"读取审计复核提示词失败：{e}",
        ) from e

    return {
        "cycle_name": cycle_name,
        "source_file": file_path.name,
        "markdown": markdown,
    }


@router.get("/api/knowledge/tsj")
async def list_tsj_prompts(
    current_user: User = Depends(get_current_user),
) -> dict:
    """列出 TSJ 目录下所有可用的提示词文件名（供调试/索引使用）。"""
    tsj_dir = _resolve_tsj_dir()
    files = _list_tsj_files(tsj_dir)
    return {
        "directory": str(tsj_dir),
        "count": len(files),
        "files": [f.name for f in files],
    }
