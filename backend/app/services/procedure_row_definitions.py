"""程序行定义：按当前程序表模板导入 —— spec procedure-chain-followup-closure R2.1。

原先定义只有裁剪服务在用户裁剪某一行时顺带写入（``procedure_row_trim_service``），``ProcedureBackfillRunner`` 没有
调用方 ⇒ 新项目在委派预览里恒 0 个目标、也不说为什么。委派预览前按所选底稿的程序表，从
``procedure_table_templates.json`` 现取当前版本的定义：

- 写入：``INSERT … ON CONFLICT (definition_key) DO NOTHING``。``definition_key`` 内容寻址 ⇒ 幂等、并发安全，
  已有的定义（含旧版本）一律不动。
- 物化只用当前版本：返回各底稿编码的当前定义键集合。库里同模板码还可能有旧版本 / 别的来源（测试、旧导入）的定义，
  按 ``template_revision_hash`` 过滤不行 —— 内容没变的行沿用旧行、旧 revision（导入器约定），按 hash 过滤会把它们漏掉；
  按定义键集合过滤才对。
- 底稿 → 程序表：模板编码的底稿基码等于底稿编码（D2A → D2、A1 → A1，与物化服务同一口径 ``_base_wp_code``）。

只 flush 不 commit。
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowDefinition


def template_codes_for(wp_code: str) -> list[str]:
    """这个底稿编码在程序表模板库里的程序表编码（可能 0 个：不是每张底稿都有程序表）。"""
    from app.services.procedure_table_auto_service import list_table_codes
    from app.services.procedure_task_materialization_service import _base_wp_code

    if not wp_code:
        return []
    return sorted(code for code in list_table_codes() if _base_wp_code(code) == wp_code)


def current_definitions(template_code: str) -> list[dict]:
    """当前模板版本的全部程序行定义（纯计算，与裁剪服务建单行定义同一算法）。"""
    from app.services.procedure_definition_importer import ProcedureDefinitionImporter
    from app.services.procedure_table_auto_service import get_template

    template = get_template(template_code)
    if not template or not template.get("items"):
        return []
    return ProcedureDefinitionImporter.build_from_json_template(template_code, template_code, template).definitions


async def ensure_current_definitions(
    db: AsyncSession, wp_codes: Iterable[str],
) -> tuple[int, dict[str, frozenset[str]]]:
    """按底稿编码导入当前版本定义（已有的不动）。返回 (新建定义数, {底稿编码: 当前定义键集合})。"""
    created = 0
    keys_by_wp_code: dict[str, frozenset[str]] = {}
    for wp_code in sorted({c for c in wp_codes if c}):
        keys: set[str] = set()
        for code in template_codes_for(wp_code):
            defs = current_definitions(code)
            if not defs:
                continue
            stmt = pg_insert(ProcedureRowDefinition).values([
                {
                    "definition_key": d["definition_key"],
                    "template_code": d["template_code"],
                    "template_revision_hash": d["template_revision_hash"],
                    "sheet_key": d["sheet_key"],
                    "source_locator": d["source_locator"],
                    "program_no": d.get("program_no"),
                    "procedure_text": d["procedure_text"],
                    "ref_snapshot": d["ref_snapshot"],
                    "legacy_aliases": d["legacy_aliases"],
                    "normalized_content": d["normalized_content"],
                }
                for d in defs
            ]).on_conflict_do_nothing(index_elements=[ProcedureRowDefinition.definition_key]).returning(
                ProcedureRowDefinition.definition_key
            )
            created += len((await db.execute(stmt)).all())
            keys.update(d["definition_key"] for d in defs)
        keys_by_wp_code[wp_code] = frozenset(keys)
    await db.flush()
    return created, keys_by_wp_code
