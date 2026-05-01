"""
底稿操作手册服务 — 加载BCD类底稿md文件，按循环提供给AI面板

51个md文件分三类：
1. 操作手册（如"D销售循环操作手册.md"）— 审计程序步骤、检查要点、风险关注点
2. 底稿模板库（如"D收入循环底稿模板库.md"）— 底稿结构说明、填写指引
3. 控制底稿（如"B23-1销售循环业务层面控制底稿模板库.md"）— 内控测试要点

按循环前缀（D/E/F/G/H/I/J/K/L/M/Q）分组，供底稿工作台AI面板按当前循环加载。
"""
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path("致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md")

# 循环前缀 → 目录名映射
_CYCLE_DIR_MAP = {
    "D": "D销售循环",
    "E": "E货币资金循环",
    "F": "F存货循环",
    "G": "G投资循环",
    "H": "H固定资产循环",
    "I": "I无形资产循环",
    "J": "J职工薪酬循环",
    "K": "K管理循环",
    "L": "L债务循环",
    "M": "M权益循环",
    "Q": "Q关联方循环",
}

# 文件类型分类关键词
_TYPE_KEYWORDS = {
    "manual": ["操作手册"],
    "template_lib": ["底稿模板库"],
    "control_b": ["业务层面控制"],
    "control_c": ["控制测试"],
    "tool_spec": ["制作规格", "Excel工具"],
}


def _classify_file(filename: str) -> str:
    """根据文件名分类"""
    for ftype, keywords in _TYPE_KEYWORDS.items():
        if any(kw in filename for kw in keywords):
            return ftype
    return "other"


@lru_cache(maxsize=1)
def _scan_all_manuals() -> dict:
    """扫描所有md文件，构建索引（启动时缓存）"""
    index: dict[str, list[dict]] = {}

    if not _BASE_DIR.exists():
        logger.warning("BCD md directory not found: %s", _BASE_DIR)
        return index

    for cycle_prefix, dir_name in _CYCLE_DIR_MAP.items():
        cycle_dir = _BASE_DIR / dir_name
        if not cycle_dir.exists():
            continue

        files = []
        for md_file in sorted(cycle_dir.glob("*.md")):
            ftype = _classify_file(md_file.name)
            files.append({
                "filename": md_file.name,
                "path": str(md_file),
                "type": ftype,
                "cycle": cycle_prefix,
                "size_kb": round(md_file.stat().st_size / 1024, 1),
                "title": md_file.stem,
            })
        index[cycle_prefix] = files

    # 根目录的框架文件
    framework = _BASE_DIR / "审计实务操作手册-框架.md"
    if framework.exists():
        index["_framework"] = [{
            "filename": framework.name,
            "path": str(framework),
            "type": "framework",
            "cycle": "ALL",
            "size_kb": round(framework.stat().st_size / 1024, 1),
            "title": framework.stem,
        }]

    total = sum(len(v) for v in index.values())
    logger.info("wp_manual_service: scanned %d md files across %d cycles", total, len(index))
    return index


def get_cycle_manuals(cycle: str) -> list[dict]:
    """获取指定循环的所有md文件索引"""
    index = _scan_all_manuals()
    return index.get(cycle.upper(), [])


def get_all_manuals() -> dict[str, list[dict]]:
    """获取所有循环的md文件索引"""
    return _scan_all_manuals()


def get_manual_content(cycle: str, filename: str, max_chars: int = 0) -> Optional[str]:
    """读取指定md文件内容

    Args:
        max_chars: 最大字符数（0=不限制，用于LLM上下文截断）
    """
    files = get_cycle_manuals(cycle)
    target = next((f for f in files if f["filename"] == filename), None)
    if not target:
        return None

    fp = Path(target["path"])
    if not fp.exists():
        return None

    try:
        content = fp.read_text(encoding="utf-8-sig")
        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (截断，原文共 {len(content)} 字符)"
        return content
    except Exception as e:
        logger.warning("read manual failed: %s - %s", fp, e)
        return None


def get_operation_manual(cycle: str, max_chars: int = 8000) -> Optional[str]:
    """获取指定循环的操作手册内容（优先加载，供AI面板使用）"""
    files = get_cycle_manuals(cycle)
    manual = next((f for f in files if f["type"] == "manual"), None)
    if not manual:
        return None
    return get_manual_content(cycle, manual["filename"], max_chars)


def get_template_lib(cycle: str, max_chars: int = 8000) -> Optional[str]:
    """获取指定循环的底稿模板库内容"""
    files = get_cycle_manuals(cycle)
    tpl = next((f for f in files if f["type"] == "template_lib"), None)
    if not tpl:
        return None
    return get_manual_content(cycle, tpl["filename"], max_chars)


def get_context_for_llm(cycle: str, wp_code: str = "", max_total_chars: int = 12000) -> str:
    """为LLM构建审计程序上下文

    按优先级加载：操作手册 > 底稿模板库 > 控制底稿
    总字符数不超过 max_total_chars。
    """
    parts = []
    remaining = max_total_chars

    # 1. 操作手册（最重要）
    manual = get_operation_manual(cycle, min(remaining, 6000))
    if manual:
        parts.append(f"## 审计操作手册（{cycle}循环）\n\n{manual}")
        remaining -= len(parts[-1])

    # 2. 底稿模板库
    if remaining > 1000:
        tpl = get_template_lib(cycle, min(remaining, 4000))
        if tpl:
            parts.append(f"## 底稿模板指引（{cycle}循环）\n\n{tpl}")
            remaining -= len(parts[-1])

    # 3. 控制底稿（如果还有空间）
    if remaining > 1000:
        files = get_cycle_manuals(cycle)
        for f in files:
            if f["type"] in ("control_b", "control_c") and remaining > 500:
                content = get_manual_content(cycle, f["filename"], min(remaining, 2000))
                if content:
                    parts.append(f"## {f['title']}\n\n{content}")
                    remaining -= len(parts[-1])

    if not parts:
        return f"（{cycle}循环暂无操作手册资料）"

    return "\n\n---\n\n".join(parts)


def get_stats() -> dict:
    """获取操作手册统计"""
    index = _scan_all_manuals()
    by_cycle = {}
    total_files = 0
    total_size_kb = 0

    for cycle, files in index.items():
        if cycle == "_framework":
            continue
        by_cycle[cycle] = {
            "count": len(files),
            "types": {},
            "total_kb": sum(f["size_kb"] for f in files),
        }
        for f in files:
            by_cycle[cycle]["types"][f["type"]] = by_cycle[cycle]["types"].get(f["type"], 0) + 1
        total_files += len(files)
        total_size_kb += by_cycle[cycle]["total_kb"]

    return {
        "total_files": total_files,
        "total_size_kb": round(total_size_kb, 1),
        "cycles": len(by_cycle),
        "by_cycle": by_cycle,
        "has_framework": "_framework" in index,
    }
