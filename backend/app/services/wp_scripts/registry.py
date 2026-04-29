"""底稿精细化脚本注册表

根据底稿编号前缀匹配对应的精细化脚本。
每个脚本提供：extract_data / generate_audit_explanation / get_review_checklist
"""

from __future__ import annotations

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

# 脚本注册表：wp_code 前缀 → 模块
_SCRIPT_REGISTRY = {
    "E1": "app.services.wp_scripts.e1_cash",
    "D1": "app.services.wp_scripts.d1_receivable",
    "H1": "app.services.wp_scripts.h1_fixed_asset",
}


def get_script_module(wp_code: str):
    """根据底稿编号获取对应的精细化脚本模块"""
    import importlib
    for prefix, module_path in _SCRIPT_REGISTRY.items():
        if wp_code.startswith(prefix):
            return importlib.import_module(module_path)
    return None


async def run_extract(db: AsyncSession, project_id: UUID, year: int, wp_code: str) -> dict | None:
    """执行数据提取"""
    mod = get_script_module(wp_code)
    if mod and hasattr(mod, "extract_data"):
        return await mod.extract_data(db, project_id, year)
    return None


async def run_generate_explanation(db: AsyncSession, project_id: UUID, year: int, wp_code: str) -> str | None:
    """执行审计说明生成"""
    mod = get_script_module(wp_code)
    if mod and hasattr(mod, "generate_audit_explanation"):
        return await mod.generate_audit_explanation(db, project_id, year)
    return None


def get_review_checklist(wp_code: str) -> list[dict] | None:
    """获取复核要点清单"""
    mod = get_script_module(wp_code)
    if mod and hasattr(mod, "get_review_checklist"):
        return mod.get_review_checklist()
    return None


def list_available_scripts() -> list[dict]:
    """列出所有可用的精细化脚本"""
    import importlib
    result = []
    for prefix, module_path in _SCRIPT_REGISTRY.items():
        try:
            mod = importlib.import_module(module_path)
            doc = mod.__doc__ or ""
            first_line = doc.strip().split("\n")[0] if doc else prefix
            result.append({"prefix": prefix, "name": first_line, "module": module_path})
        except Exception:
            result.append({"prefix": prefix, "name": prefix, "module": module_path, "error": True})
    return result
