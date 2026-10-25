"""底稿模板引擎 — 模板上传/版本管理/模板集/项目底稿生成

Validates: Requirements 1.1-1.8, 6.2, 6.3
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    WpIndex,
    WpSourceType,
    WpStatus,
    WpTemplate,
    WpTemplateMeta,
    WpTemplateSet,
    WpTemplateStatus,
    WorkingPaper,
    RegionType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6 built-in seed template sets
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATE_SETS: list[dict[str, Any]] = []  # 延迟加载，见下方 _load_builtin_sets()


def _load_builtin_sets() -> list[dict[str, Any]]:
    """从 wp_account_mapping.json 读取完整底稿编码表，构建内置模板集。

    - 标准年审（国企）：全量 206 条致同底稿编码
    - 上市公司：全量 206 条 + 上市专用标记（共享同一编码表，applicable_standard 区分）
    - 精简版：仅核心循环一级底稿（A/B/D/E/F，不含子编码和专项 S 循环）
    - IPO：全量 + S 专项循环
    - 国企附注 / 上市附注：仅 A 循环报表类底稿（附注由独立模块管理）
    """
    mapping_path = Path(__file__).resolve().parent.parent.parent / "data" / "wp_account_mapping.json"
    all_codes: list[str] = []
    if mapping_path.exists():
        try:
            raw = json.loads(mapping_path.read_text(encoding="utf-8"))
            all_codes = sorted(set(m["wp_code"] for m in raw.get("mappings", []) if m.get("wp_code")))
        except Exception:
            pass
    if not all_codes:
        # 兜底：最小 stub（不应发生）
        all_codes = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1", "I1", "J1", "K1", "L1", "M1", "N1", "S1"]

    # 精简版：仅一级编码（无 dash）且核心循环 A/B/D/E/F
    compact_codes = sorted(c for c in all_codes if "-" not in c and c[0] in "ABDEF")

    return [
        {
            "set_name": "标准年审",
            "template_codes": all_codes,
            "applicable_audit_type": "annual",
            "applicable_standard": "CAS",
            "description": "适用于一般企业年度审计的完整底稿模板集（致同2025修订版，206条编码）",
        },
    ]


# 模块加载时初始化
BUILTIN_TEMPLATE_SETS = _load_builtin_sets()


def select_generation_codes(
    template_codes: list[str], selected_codes: list[str] | None
) -> tuple[list[str], list[str]]:
    """生成范围 = 模板集编码 ∩ 用户选中（按模板集顺序、去重）。

    返回 ``(要生成的编码, 选中但不在模板集里的编码)``。

    * ``selected_codes is None``：调用方没有做裁剪（旧调用方 / 整套生成）⇒ 原样返回模板集编码。
    * 空列表：一个都没选 ⇒ 不生成（不能当成「没传」去生成整套）。
    * 选中编码按去空白后比较；不在模板集里的如实返回，由调用方回报给用户，不静默丢弃。
    """
    ordered = list(dict.fromkeys(c for c in (template_codes or []) if c))
    if selected_codes is None:
        return ordered, []
    wanted = list(dict.fromkeys(
        str(c).strip() for c in selected_codes if c is not None and str(c).strip()
    ))
    chosen = set(wanted)
    in_set = set(ordered)
    return [c for c in ordered if c in chosen], [c for c in wanted if c not in in_set]


class TemplateSetGeneration(NamedTuple):
    """模板集生成回执：新建的底稿 + 三类没生成的编码（均按模板集顺序）。"""

    workpapers: list[WorkingPaper]
    ignored_codes: list[str]          # 选中但不在模板集里
    skipped_trimmed_codes: list[str]  # 已在程序裁剪中标为不执行（含子表 / 程序表）
    in_recycle_codes: list[str]       # 底稿在回收站中（同码只能恢复，不能新建）
    blank_codes: tuple[str, ...] = ()  # 找不到模板、建了空白底稿（与按编码生成同口径单列）


class TemplateEngine:
    """底稿模板引擎

    Validates: Requirements 1.1-1.8
    """


    # ------------------------------------------------------------------
    # 6.1  upload_template
    # ------------------------------------------------------------------

    async def upload_template(
        self,
        db: AsyncSession,
        template_code: str,
        template_name: str,
        audit_cycle: str | None = None,
        applicable_standard: str | None = None,
        description: str | None = None,
        created_by: UUID | None = None,
        named_ranges: list[dict] | None = None,
    ) -> WpTemplate:
        """Upload a template: save metadata to DB, parse Named Ranges.

        In MVP mode (no actual .xlsx file), we accept metadata only and
        optionally a list of named_ranges dicts to populate wp_template_meta.

        Validates: Requirements 1.1, 1.2, 1.5
        """
        file_path = f"templates/{template_code}/1.0/{template_code}.xlsx"

        template = WpTemplate(
            template_code=template_code,
            template_name=template_name,
            audit_cycle=audit_cycle,
            applicable_standard=applicable_standard,
            version_major=1,
            version_minor=0,
            status=WpTemplateStatus.draft,
            file_path=file_path,
            description=description,
            created_by=created_by,
        )
        db.add(template)
        await db.flush()

        # Parse Named Ranges → wp_template_meta
        if named_ranges:
            for nr in named_ranges:
                meta = WpTemplateMeta(
                    template_id=template.id,
                    range_name=nr.get("range_name", ""),
                    region_type=nr.get("region_type", RegionType.manual),
                    description=nr.get("description"),
                )
                db.add(meta)

        await db.flush()
        return template

    # ------------------------------------------------------------------
    # 6.2  create_version
    # ------------------------------------------------------------------

    async def create_version(
        self,
        db: AsyncSession,
        template_code: str,
        change_type: str = "minor",
    ) -> WpTemplate:
        """Create a new version of an existing template.

        change_type="major" → major+1, minor=0
        change_type="minor" → minor+1

        Validates: Requirements 1.3
        """
        # Find latest version of this template_code
        result = await db.execute(
            sa.select(WpTemplate)
            .where(
                WpTemplate.template_code == template_code,
                WpTemplate.is_deleted == sa.false(),
            )
            .order_by(
                WpTemplate.version_major.desc(),
                WpTemplate.version_minor.desc(),
            )
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            raise ValueError(f"模板 {template_code} 不存在")

        if change_type == "major":
            new_major = latest.version_major + 1
            new_minor = 0
        else:
            new_major = latest.version_major
            new_minor = latest.version_minor + 1

        version_str = f"{new_major}.{new_minor}"
        file_path = f"templates/{template_code}/{version_str}/{template_code}.xlsx"

        new_template = WpTemplate(
            template_code=template_code,
            template_name=latest.template_name,
            audit_cycle=latest.audit_cycle,
            applicable_standard=latest.applicable_standard,
            version_major=new_major,
            version_minor=new_minor,
            status=WpTemplateStatus.draft,
            file_path=file_path,
            description=latest.description,
            created_by=latest.created_by,
        )
        db.add(new_template)
        await db.flush()
        return new_template

    # ------------------------------------------------------------------
    # 6.3  delete_template
    # ------------------------------------------------------------------

    async def delete_template(
        self,
        db: AsyncSession,
        template_id: UUID,
    ) -> None:
        """Soft-delete a template after checking no project references it.

        Validates: Requirements 1.4
        """
        result = await db.execute(
            sa.select(WpTemplate).where(WpTemplate.id == template_id, WpTemplate.is_deleted == sa.false())
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise ValueError("模板不存在")

        # 按底稿编码精确判断引用；原先按文件路径子串匹配，删除模板 H1 时 H10 的底稿也算作引用
        ref_result = await db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.wp_code == template.template_code,
            )
        )
        ref_count = ref_result.scalar() or 0
        if ref_count > 0:
            raise ValueError(
                f"模板 {template.template_code} 已被 {ref_count} 个项目底稿引用，无法删除"
            )

        # WpTemplate 继承 Base，没有 soft_delete()（原调用每次删除都抛 AttributeError ⇒ 500），表里也没有 deleted_at 列
        template.is_deleted = True
        template.updated_at = sa.func.now()
        await db.flush()

    # ------------------------------------------------------------------
    # 6.4  Template set management
    # ------------------------------------------------------------------

    async def get_template(
        self,
        db: AsyncSession,
        template_code: str,
        version: str | None = None,
    ) -> WpTemplate | None:
        """Get a template by code. Default: latest version.

        Validates: Requirements 1.1
        """
        query = sa.select(WpTemplate).where(
            WpTemplate.template_code == template_code,
            WpTemplate.is_deleted == sa.false(),
        )
        if version and "." in version:
            major, minor = version.split(".", 1)
            query = query.where(
                WpTemplate.version_major == int(major),
                WpTemplate.version_minor == int(minor),
            )
        else:
            query = query.order_by(
                WpTemplate.version_major.desc(),
                WpTemplate.version_minor.desc(),
            )
        query = query.limit(1)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        db: AsyncSession,
        audit_cycle: str | None = None,
        applicable_standard: str | None = None,
    ) -> list[WpTemplate]:
        """List templates with optional filters."""
        query = sa.select(WpTemplate).where(
            WpTemplate.is_deleted == sa.false()
        )
        if audit_cycle:
            query = query.where(WpTemplate.audit_cycle == audit_cycle)
        if applicable_standard:
            query = query.where(WpTemplate.applicable_standard == applicable_standard)
        query = query.order_by(WpTemplate.template_code, WpTemplate.version_major.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_template_sets(self, db: AsyncSession) -> list[WpTemplateSet]:
        """Get all template sets.

        Validates: Requirements 1.6
        """
        result = await db.execute(
            sa.select(WpTemplateSet)
            .where(WpTemplateSet.is_deleted == sa.false())
            .order_by(WpTemplateSet.set_name)
        )
        return list(result.scalars().all())

    async def get_template_set(
        self, db: AsyncSession, set_id: UUID
    ) -> WpTemplateSet | None:
        """Get a single template set by ID."""
        result = await db.execute(
            sa.select(WpTemplateSet).where(
                WpTemplateSet.id == set_id,
                WpTemplateSet.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    async def create_template_set(
        self,
        db: AsyncSession,
        set_name: str,
        template_codes: list[str] | None = None,
        applicable_audit_type: str | None = None,
        applicable_standard: str | None = None,
        description: str | None = None,
    ) -> WpTemplateSet:
        """Create a new template set."""
        ts = WpTemplateSet(
            set_name=set_name,
            template_codes=template_codes or [],
            applicable_audit_type=applicable_audit_type,
            applicable_standard=applicable_standard,
            description=description,
        )
        db.add(ts)
        await db.flush()
        return ts

    async def update_template_set(
        self,
        db: AsyncSession,
        set_id: UUID,
        set_name: str | None = None,
        template_codes: list[str] | None = None,
        applicable_audit_type: str | None = None,
        applicable_standard: str | None = None,
        description: str | None = None,
    ) -> WpTemplateSet:
        """Update an existing template set."""
        result = await db.execute(
            sa.select(WpTemplateSet).where(WpTemplateSet.id == set_id)
        )
        ts = result.scalar_one_or_none()
        if ts is None:
            raise ValueError("模板集不存在")
        if set_name is not None:
            ts.set_name = set_name
        if template_codes is not None:
            ts.template_codes = template_codes
        if applicable_audit_type is not None:
            ts.applicable_audit_type = applicable_audit_type
        if applicable_standard is not None:
            ts.applicable_standard = applicable_standard
        if description is not None:
            ts.description = description
        await db.flush()
        return ts

    async def seed_builtin_template_sets(self, db: AsyncSession) -> list[WpTemplateSet]:
        """Seed the 6 built-in template sets (idempotent).

        Validates: Requirements 1.7
        """
        created = []
        for data in BUILTIN_TEMPLATE_SETS:
            existing_result = await db.execute(
                sa.select(WpTemplateSet).where(
                    WpTemplateSet.set_name == data["set_name"]
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                # 已存在：如果编码数量变化则更新（保证 seed 后编码总是最新）
                old_codes = existing.template_codes or []
                new_codes = data["template_codes"]
                if len(old_codes) != len(new_codes) or set(old_codes) != set(new_codes):
                    existing.template_codes = new_codes
                    existing.description = data["description"]
                    created.append(existing)
                continue
            ts = WpTemplateSet(
                set_name=data["set_name"],
                template_codes=data["template_codes"],
                applicable_audit_type=data["applicable_audit_type"],
                applicable_standard=data.get("applicable_standard"),
                description=data["description"],
            )
            db.add(ts)
            created.append(ts)
        await db.flush()
        return created

    # ------------------------------------------------------------------
    # 6.5  generate_project_workpapers
    # ------------------------------------------------------------------

    async def generate_project_workpapers(
        self,
        db: AsyncSession,
        project_id: UUID,
        template_set_id: UUID,
        year: int = 2025,
        created_by: UUID | None = None,
        selected_codes: list[str] | None = None,
    ) -> list[WorkingPaper]:
        """从模板集生成项目底稿（只要底稿列表；要没生成的编码与原因用 *_detailed）。"""
        outcome = await self.generate_project_workpapers_detailed(
            db=db, project_id=project_id, template_set_id=template_set_id, year=year,
            created_by=created_by, selected_codes=selected_codes,
        )
        return outcome.workpapers

    async def generate_project_workpapers_detailed(
        self,
        db: AsyncSession,
        project_id: UUID,
        template_set_id: UUID,
        year: int = 2025,
        created_by: UUID | None = None,
        selected_codes: list[str] | None = None,
    ) -> TemplateSetGeneration:
        """Generate project workpapers from a template set.

        ``selected_codes``：用户在生成前裁剪弹窗里确认的编码（None = 整套生成，兼容旧调用方）。
        只生成「模板集 ∩ 选中」，返回 (底稿, 选中但不在模板集里的编码)。此前端点不收这个字段，
        用户裁剪掉的底稿照样全部生成（spec formula-fetch-and-wp-generation-defect-closure R4）。

        粗裁结果经 ``procedure_scope_retention.plan_generation`` 判定（子表 / 程序表跟随科目，读不到即抛
        ``TrimScopeUnavailable`` 停止生成）；底稿在回收站中的编码不新建、如实回报
        （spec procedure-trim-generation-delegation-chain 需求 2）。

        1. Iterate template codes in the set
        2. For each code, find the latest published (or draft) template
        3. Create wp_index record
        4. Create working_paper record
        5. 按底稿 id 落文件（``wp_generate_file.materialize_workpaper_files``，与按编码生成同一解析），
           ``file_path`` 指向本底稿自己的文件（不引用模板库路径）

        Validates: Requirements 1.8, 6.2, 6.3
        """
        import json
        from pathlib import Path

        ts_result = await db.execute(
            sa.select(WpTemplateSet).where(WpTemplateSet.id == template_set_id)
        )
        template_set = ts_result.scalar_one_or_none()
        if template_set is None:
            raise ValueError("模板集不存在")

        template_codes, ignored_codes = select_generation_codes(
            template_set.template_codes or [], selected_codes
        )
        workpapers: list[WorkingPaper] = []

        # 保留范围：已裁（含子表 / 程序表）与在回收站的编码都不新建；已存在的幂等跳过
        from app.services.procedure_scope_retention import plan_generation
        plan = await plan_generation(db, project_id, template_codes)

        # 加载模板库索引（用于查找模板文件路径）
        # Phase 17: 优先从 template_library 表查找项目已选择的模板
        from app.models.template_library_models import TemplateLibraryItem, ProjectTemplateSelection, TemplateLevel
        project_template_map: dict[str, str] = {}  # wp_code → file_path
        try:
            sel_q = (
                sa.select(TemplateLibraryItem.wp_code, TemplateLibraryItem.file_path)
                .join(ProjectTemplateSelection, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
                .where(
                    ProjectTemplateSelection.project_id == project_id,
                    ProjectTemplateSelection.is_active == sa.true(),
                    TemplateLibraryItem.wp_code.isnot(None),
                    TemplateLibraryItem.file_path.isnot(None),
                )
            )
            for wp_code, fp in (await db.execute(sel_q)).all():
                if wp_code and fp:
                    project_template_map[wp_code] = fp
        except Exception:
            pass  # 表不存在时降级

        # 降级：从 gt_template_library.json 加载
        lib_path = Path(__file__).parent.parent.parent / "data" / "gt_template_library.json"
        template_lib: dict[str, dict] = {}
        if lib_path.exists():
            try:
                with open(lib_path, "r", encoding="utf-8-sig") as f:
                    lib_raw = json.load(f)
                # 支持两种格式：直接数组 或 {templates: [...]} 包装对象
                lib_data = lib_raw.get("templates", []) if isinstance(lib_raw, dict) else lib_raw
                for item in lib_data:
                    if isinstance(item, dict):
                        template_lib[item.get("code", item.get("wp_code", ""))] = item
            except Exception:
                pass

        # 补充名称源：wp_account_mapping.json（A18~A27 等底稿只在此有 wp_name）
        mapping_path = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
        wp_name_map: dict[str, str] = {}
        if mapping_path.exists():
            try:
                with open(mapping_path, "r", encoding="utf-8-sig") as f:
                    mapping_raw = json.load(f)
                mapping_list = mapping_raw.get("mappings", []) if isinstance(mapping_raw, dict) else mapping_raw
                for item in mapping_list:
                    if isinstance(item, dict) and item.get("wp_code") and item.get("wp_name"):
                        wp_name_map[item["wp_code"]] = item["wp_name"]
            except Exception:
                pass

        # ── 性能优化：批量预加载 WpTemplate（避免 N+1 查询） ──
        # 注意：wp_template 表可能为空（模板尚未上传），此时跳过
        tpl_map: dict[str, Any] = {}
        try:
            tpl_count = (await db.execute(
                sa.select(sa.func.count()).select_from(WpTemplate).where(WpTemplate.is_deleted == sa.false())
            )).scalar() or 0
            if tpl_count > 0:
                # 用 created_at 取最新版（避免 max(uuid) 不支持）
                from sqlalchemy import func as sa_func
                latest_subq = (
                    sa.select(
                        WpTemplate.template_code,
                        sa_func.max(WpTemplate.created_at).label("max_created"),
                    )
                    .where(
                        WpTemplate.template_code.in_(template_codes),
                        WpTemplate.is_deleted == sa.false(),
                    )
                    .group_by(WpTemplate.template_code)
                    .subquery()
                )
                tpl_result = await db.execute(
                    sa.select(WpTemplate).join(
                        latest_subq,
                        sa.and_(
                            WpTemplate.template_code == latest_subq.c.template_code,
                            WpTemplate.created_at == latest_subq.c.max_created,
                        )
                    ).where(WpTemplate.is_deleted == sa.false())
                )
                tpl_map = {t.template_code: t for t in tpl_result.scalars().all()}
        except Exception:
            pass  # wp_template 表不存在或查询失败时降级为空 map

        _pending_wps: list[WpIndex] = []

        for code in plan.to_create:
            # 从预加载 map 取模板（无 N+1）
            tpl = tpl_map.get(code)

            # Determine wp_name from template or fallback
            # 查找链：WpTemplate.template_name → gt_template_library.name → wp_account_mapping.wp_name → "底稿{code}"
            lib_entry = template_lib.get(code, {})
            if tpl:
                wp_name = tpl.template_name
            elif lib_entry.get("name") or lib_entry.get("wp_name"):
                wp_name = lib_entry.get("name") or lib_entry.get("wp_name")
            elif code in wp_name_map:
                wp_name = wp_name_map[code]
            else:
                wp_name = f"底稿{code}"
            audit_cycle = (tpl.audit_cycle if tpl else lib_entry.get("cycle_prefix", lib_entry.get("audit_cycle"))) or None
            # 确定循环代号（从编码首字母推导）
            if not audit_cycle:
                audit_cycle = code[0] if code and code[0].isalpha() else None

            # Create wp_index（批量 add，延迟 flush）
            wp_index = WpIndex(
                project_id=project_id,
                wp_code=code,
                wp_name=wp_name,
                audit_cycle=audit_cycle,
                status=WpStatus.not_started,
            )
            db.add(wp_index)
            # 暂存到列表，flush 后再创建 working_paper
            _pending_wps.append(wp_index)

        # ── 批量 flush 所有 wp_index（一次 round-trip） ──
        await db.flush()

        # ── 批量创建 working_paper（引用 wp_index.id）；文件按底稿 id 落地，先占空串 ──
        for wp_index in _pending_wps:
            wp = WorkingPaper(
                project_id=project_id,
                wp_index_id=wp_index.id,
                file_path="",  # 下面落文件后改写（NOT NULL 约束）
                source_type=WpSourceType.template,
                file_version=1,
                created_by=created_by,
            )
            db.add(wp)
            workpapers.append(wp)

        # 二次 flush working_paper 批量（取底稿 id：文件按 wp_storage/{项目}/{底稿 id} 存放）
        await db.flush()

        # ── 底稿文件（spec procedure-chain-followup-closure R3.3）──
        # 与按编码生成 / 链路编排同一解析（模板目录索引 + 多文件合并 + 场景裁剪，找不到模板建空白册）。
        # 🔴 此前 file_path 直接引用模板库路径（H1 ⇒ wp_templates/H/...，在线保存会写进所有项目共用的模板），
        #    模板库里没有的编码（E1 / D2 等多页底稿）留空串。整批放线程里做（不读写库，不占事件循环）；
        #    不在这里填表头：重药安徽 737 个编码只落文件约 31 秒，逐份填表头再加约 4 分钟（超过前端 180 秒超时）。
        #    🔴 也不要在这里加回表头填充：表头写入遇到模板首几行的合并单元格会抛 AttributeError
        #    （J2A / K11-4 / B10-2 / L1-1 / J2-5 / J2-6 等约一成模板），整批全有或全无 ⇒ 含这些编码的模板集整体生成失败。
        from app.services.wp_generate_file import (
            WorkpaperFileJob,
            discard_generated_file,
            load_generation_scenario,
            materialize_workpaper_files,
        )

        scenario, has_foreign_currency = await load_generation_scenario(db, project_id)
        jobs = [
            WorkpaperFileJob(wp.id, idx.wp_code, idx.wp_name, project_template_map.get(idx.wp_code))
            for wp, idx in zip(workpapers, _pending_wps)
        ]
        generated_files = await asyncio.to_thread(
            materialize_workpaper_files, project_id, jobs,
            scenario=scenario, has_foreign_currency=has_foreign_currency,
        )
        try:
            for wp, generated in zip(workpapers, generated_files):
                wp.file_path = str(generated.path)
            await db.flush()
        except BaseException:
            for generated in generated_files:
                discard_generated_file(generated)
            raise
        blank_codes = tuple(
            idx.wp_code for idx, generated in zip(_pending_wps, generated_files) if not generated.from_template
        )

        # F50 / Sprint 8.17: 底稿快照绑定 — 所有新建底稿都绑定当前 active dataset
        # 没有 active dataset（账套未导入）时，字段保持 None；允许先建底稿后导账套
        try:
            from app.services.dataset_query import bind_to_active_dataset
            for wp in workpapers:
                await bind_to_active_dataset(db, wp, project_id, year)
        except Exception as _bind_err:
            logger.warning("dataset binding failed for project=%s: %s", project_id, _bind_err)

        await db.flush()
        logger.info(
            "generate_project_workpapers: project=%s codes=%d files=%d blank=%d trimmed=%d recycled=%d",
            project_id, len(template_codes), len(workpapers), len(blank_codes),
            len(plan.skipped_trimmed_codes), len(plan.in_recycle_codes),
        )
        return TemplateSetGeneration(
            workpapers, ignored_codes, plan.skipped_trimmed_codes, plan.in_recycle_codes, blank_codes
        )
