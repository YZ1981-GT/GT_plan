"""底稿模板引擎 — 模板上传/版本管理/模板集/项目底稿生成

Validates: Requirements 1.1-1.8, 6.2, 6.3
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any
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
            "description": "适用于一般企业（国企）年度审计的完整底稿模板集（致同2025修订版）",
        },
        {
            "set_name": "上市公司",
            "template_codes": all_codes,
            "applicable_audit_type": "annual",
            "applicable_standard": "CAS_LISTED",
            "description": "适用于上市公司年度审计的完整底稿模板集（致同2025修订版）",
        },
        {
            "set_name": "精简版",
            "template_codes": compact_codes,
            "applicable_audit_type": "annual",
            "applicable_standard": "CAS",
            "description": "适用于小型企业年度审计的精简底稿模板集（仅核心循环一级底稿）",
        },
        {
            "set_name": "IPO",
            "template_codes": all_codes,
            "applicable_audit_type": "ipo",
            "applicable_standard": "CAS",
            "description": "适用于IPO审计的底稿模板集（全量+专项循环）",
        },
        {
            "set_name": "国企附注",
            "template_codes": sorted(c for c in all_codes if c[0] == "A"),
            "applicable_audit_type": "annual",
            "applicable_standard": "CAS_SOE",
            "description": "适用于国有企业附注编制的底稿模板集",
        },
        {
            "set_name": "上市附注",
            "template_codes": sorted(c for c in all_codes if c[0] == "A"),
            "applicable_audit_type": "annual",
            "applicable_standard": "CAS_LISTED",
            "description": "适用于上市公司附注编制的底稿模板集",
        },
    ]


# 模块加载时初始化
BUILTIN_TEMPLATE_SETS = _load_builtin_sets()


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
            sa.select(WpTemplate).where(WpTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise ValueError("模板不存在")

        # Check if any working_paper references this template's code
        ref_result = await db.execute(
            sa.select(sa.func.count()).select_from(WorkingPaper).where(
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.file_path.contains(template.template_code),
            )
        )
        ref_count = ref_result.scalar() or 0
        if ref_count > 0:
            raise ValueError(
                f"模板 {template.template_code} 已被 {ref_count} 个项目底稿引用，无法删除"
            )

        template.soft_delete()
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
    ) -> list[WorkingPaper]:
        """Generate project workpapers from a template set.

        1. Iterate template codes in the set
        2. For each code, find the latest published (or draft) template
        3. Create wp_index record
        4. Create working_paper record with file_path in project dir
        5. Copy template .xlsx to project workpaper directory

        Validates: Requirements 1.8, 6.2, 6.3
        """
        import json
        import shutil
        from pathlib import Path

        ts_result = await db.execute(
            sa.select(WpTemplateSet).where(WpTemplateSet.id == template_set_id)
        )
        template_set = ts_result.scalar_one_or_none()
        if template_set is None:
            raise ValueError("模板集不存在")

        template_codes = template_set.template_codes or []
        workpapers: list[WorkingPaper] = []

        # 加载程序裁剪结果（跳过被裁剪的底稿）
        from app.models.procedure_models import ProcedureInstance
        trimmed_q = sa.select(ProcedureInstance.wp_code, ProcedureInstance.status).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.is_deleted == sa.false(),
            ProcedureInstance.status.in_(["skip", "not_applicable"]),
        )
        trimmed_codes = set()
        for wp_code, status in (await db.execute(trimmed_q)).all():
            if wp_code:
                trimmed_codes.add(wp_code)

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

        # 项目底稿目录（按审计循环分子目录）
        project_wp_dir = Path("storage") / "projects" / str(project_id) / "workpapers"
        project_wp_dir.mkdir(parents=True, exist_ok=True)

        # ── 性能优化：批量预加载 WpTemplate（避免 N+1 查询） ──
        from sqlalchemy import func as sa_func
        # 子查询：每个 template_code 的最新版本 id
        latest_subq = (
            sa.select(
                WpTemplate.template_code,
                sa_func.max(WpTemplate.id).label("max_id"),
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
                latest_subq, WpTemplate.id == latest_subq.c.max_id
            )
        )
        tpl_map: dict[str, Any] = {t.template_code: t for t in tpl_result.scalars().all()}

        # ── 批量检查已存在的 wp_index（幂等：跳过已有编码） ──
        existing_codes_result = await db.execute(
            sa.select(WpIndex.wp_code).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code.in_(template_codes),
            )
        )
        existing_codes = set(r[0] for r in existing_codes_result.all())

        for code in template_codes:
            # 跳过被裁剪的底稿
            if code in trimmed_codes:
                continue
            # 幂等：跳过已存在的
            if code in existing_codes:
                continue

            # 从预加载 map 取模板（无 N+1）
            tpl = tpl_map.get(code)

            # Determine wp_name from template or fallback
            lib_entry = template_lib.get(code, {})
            wp_name = tpl.template_name if tpl else lib_entry.get("name", lib_entry.get("wp_name", f"底稿{code}"))
            audit_cycle = (tpl.audit_cycle if tpl else lib_entry.get("cycle_prefix", lib_entry.get("audit_cycle"))) or None
            # 确定循环代号（从编码首字母推导）
            if not audit_cycle:
                audit_cycle = code[0] if code and code[0].isalpha() else None

            # 模板文件路径（引用模板库原始路径，不复制到项目目录）
            template_file_path: str | None = None
            if code in project_template_map:
                template_file_path = project_template_map[code]
            elif lib_entry.get("file_path"):
                template_file_path = lib_entry["file_path"]
            elif tpl and tpl.file_path:
                template_file_path = tpl.file_path

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
            _pending_wps.append((wp_index, template_file_path))

        # ── 批量 flush 所有 wp_index（一次 round-trip） ──
        await db.flush()

        # ── 批量创建 working_paper（引用 wp_index.id） ──
        for wp_index, template_file_path in _pending_wps:
            wp = WorkingPaper(
                project_id=project_id,
                wp_index_id=wp_index.id,
                file_path=template_file_path,  # 引用模板库路径，不复制文件
                source_type=WpSourceType.template,
                file_version=1,
                created_by=created_by,
            )
            db.add(wp)
            workpapers.append(wp)

        # 二次 flush working_paper 批量
        await db.flush()

        # F50 / Sprint 8.17: 底稿快照绑定 — 所有新建底稿都绑定当前 active dataset
        # 没有 active dataset（账套未导入）时，字段保持 None；允许先建底稿后导账套
        try:
            from app.services.dataset_query import bind_to_active_dataset
            for wp in workpapers:
                await bind_to_active_dataset(db, wp, project_id, year)
        except Exception as _bind_err:
            logger.warning("dataset binding failed for project=%s: %s", project_id, _bind_err)

        await db.flush()
        logger.info("generate_project_workpapers: project=%s codes=%d files=%d", project_id, len(template_codes), len(workpapers))
        return workpapers
