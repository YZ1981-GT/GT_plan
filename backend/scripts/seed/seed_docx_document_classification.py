"""补充 seed：docx 文档类底稿归类（A18/A26/A27 系列等）

背景
----
主 seed 脚本 ``seed_workpaper_sheet_classification.py`` 从
``workpaper_template_analysis.json`` 灌数据，而该 JSON 由 xlsx 扫描器生成，
**不含 docx 模板**。导致 A18/A26/A27 系列（函件 / 清单 / 备忘录，均为 docx）
在 ``workpaper_sheet_classification`` 表无任何记录 → render-config 返回空 sheets
→ 底稿点开是空白页。

本脚本补齐这些 docx 文档底稿的最小分类行（每 wp_code 一条），让 render-config
的 per-sheet dispatch 循环能产出 sheet 条目；具体 componentType 由
``wp_code_overrides.json`` 决定（A18-2=regulatory-letter，其余=word-template）。

幂等：按 (wp_code, sheet_name, template_version_id) UPSERT，可重复运行。

用法：
    python -m scripts.seed.seed_docx_document_classification
"""
from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy import text

from app.core.database import async_session
from app.models.workpaper_models import WorkpaperSheetClassification


# ─── docx 文档底稿补充清单 ───────────────────────────────────────────────────
# sheet_name 用 wp_code（与保存时 parsed_data.html_data 的键一致），
# componentType 由 _WP_CODE_OVERRIDE 指定，故此处 class_code 仅用于语义归属。
# 这些是真底稿（需编制的函件/清单/备忘录），is_real_workpaper=True。
DOCX_DOCS: list[dict] = [
    {"wp_code": "A18", "wp_name": "向监管部门报送审计小结的函"},
    {"wp_code": "A18-1", "wp_name": "向监管部门报送审计小结的函"},
    {"wp_code": "A18-2", "wp_name": "与监管层沟通函"},
    {"wp_code": "A26", "wp_name": "专业技术委员会业务报告审核提交资料清单"},
    {"wp_code": "A26-1", "wp_name": "专业技术委员会业务报告审核提交资料清单"},
    {"wp_code": "A26-2", "wp_name": "专业技术委员会委员审核记录"},
    {"wp_code": "A26-3", "wp_name": "专业技术委员会会议记录"},
    {"wp_code": "A26-4", "wp_name": "专业技术委员会重大业务咨询意见或分歧会议记录"},
    {"wp_code": "A27", "wp_name": "IT审计总结备忘录"},
    {"wp_code": "A27-1", "wp_name": "IT审计总结备忘录"},
    # B 循环 docx 文档控制表（同样未被 xlsx 扫描器收录 → 分类缺失 → 空白页）
    {"wp_code": "B5", "wp_name": "业务约定书控制表", "class_code": "B-报告文档", "class": "B"},
    # K 循环损益类审定表（标准模板库无 K14~K18 编码 / 模板缺失 → 分类缺失 → 空白页）。
    # componentType 由 override(audit-sheet) 决定，audit-sheet 无模板时优雅降级空表+TB取数+手动加行。
    {"wp_code": "K14", "wp_name": "资产处置收益审定表", "class_code": "K-审定表", "class": "K"},
    {"wp_code": "K15", "wp_name": "其他收益审定表", "class_code": "K-审定表", "class": "K"},
    {"wp_code": "K16", "wp_name": "投资收益审定表", "class_code": "K-审定表", "class": "K"},
    {"wp_code": "K17", "wp_name": "公允价值变动收益审定表", "class_code": "K-审定表", "class": "K"},
    {"wp_code": "K18", "wp_name": "递延收益审定表", "class_code": "K-审定表", "class": "K"},
    # S 专项：S17 非经常性损益模板是旧版 .xls（analyze 脚本只扫 .xlsx → 漏）。override 已配 audit-sheet。
    {"wp_code": "S17", "wp_name": "非经常性损益", "class_code": "S-审定表", "class": "S"},
]

# 默认 class_code：A 报告循环文档（语义归属 A），componentType 由 class_code 前缀派生
_CLASS_CODE = "A-报告文档"
_CLASS = "A"


async def _current_version_id(s) -> str | None:
    r = await s.execute(
        text("SELECT id FROM workpaper_template_version WHERE is_current = TRUE LIMIT 1")
    )
    row = r.first()
    return str(row[0]) if row else None


async def main() -> None:
    async with async_session() as s:
        version_id = await _current_version_id(s)
        print(f"[DB] template_version_id = {version_id}")

        inserted, updated = 0, 0
        for doc in DOCX_DOCS:
            wp_code = doc["wp_code"]
            sheet_name = wp_code  # 与 parsed_data.html_data 键一致
            cls_code = doc.get("class_code", _CLASS_CODE)
            cls = doc.get("class", _CLASS)
            existing = (
                await s.execute(
                    sa.select(WorkpaperSheetClassification).where(
                        WorkpaperSheetClassification.wp_code == wp_code,
                        WorkpaperSheetClassification.sheet_name == sheet_name,
                    )
                )
            ).scalars().first()

            if existing:
                existing.class_code = cls_code
                existing.class_ = cls
                existing.is_real_workpaper = True
                existing.scope = "standalone"
                existing.template_version_id = version_id
                updated += 1
            else:
                s.add(
                    WorkpaperSheetClassification(
                        wp_code=wp_code,
                        sheet_name=sheet_name,
                        class_code=cls_code,
                        class_=cls,
                        is_real_workpaper=True,
                        exclude_from_archive=False,
                        exclude_from_progress=False,
                        is_static_doc=False,
                        scope="standalone",
                        template_version_id=version_id,
                    )
                )
                inserted += 1

        await s.commit()
        print(f"[OK] docx 文档分类补充完成：新增 {inserted}，更新 {updated}")

        # 校验
        rows = (
            await s.execute(
                sa.select(
                    WorkpaperSheetClassification.wp_code,
                    WorkpaperSheetClassification.sheet_name,
                    WorkpaperSheetClassification.class_code,
                ).where(
                    WorkpaperSheetClassification.wp_code.in_(
                        [d["wp_code"] for d in DOCX_DOCS]
                    )
                )
            )
        ).all()
        print("[CHECK] 补充后分类行：")
        for r in rows:
            print(f"  {r[0]:<8} {r[1]:<8} {r[2]}")


if __name__ == "__main__":
    asyncio.run(main())
