"""WpConversionGenerateMixin — 底稿生成相关方法（从 wp_standard_conversion_service 拆出）。

承载"目标准则独有底稿创建"链路：``_create_target_only_workpapers`` 编排，逐个
委托 ``_generate_one_workpaper``（建 WpIndex + WorkingPaper + 模板文件 + parsed_data），
配套模板库加载（名称候选）/ parsed_data 填充 / 年度派生 helper。模板文件经
``wp_generate_file.materialize_workpaper_file`` 与链路编排 / 按编码生成同一解析（spec
formula-fetch-and-wp-generation-defect-closure R5.3；此前按模板库精确匹配，多页底稿落成空白册）。

设计（pass4 大文件拆分）：这些方法均含 ``self`` 且通过 ``self.db`` 访问会话，
以 mixin 形式被 ``WpStandardConversionService`` 多继承组合，保持方法仍挂在实例上、
签名与行为逐字不变。本模块**不导入**主 class，避免循环导入。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa

from app.models.workpaper_models import (
    WorkingPaper,
    WpIndex,
    WpSourceType,
    WpStatus,
)
from app.services.wp_parsed_data_service import ensure_parsed_data_placeholder

logger = logging.getLogger(__name__)

# 致同标准底稿模板库目录（与 wp_template.generate_from_codes 同源；只作名称 / 循环候选）
# 注意：本模块比主文件深一层（services/wp_conversion/），故较主文件多一个 .parent
# 以保持解析后的绝对路径与原 wp_standard_conversion_service 完全一致。
_TEMPLATE_LIBRARY_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "gt_template_library.json"
)


class WpConversionGenerateMixin:
    """底稿生成相关方法 mixin（供 WpStandardConversionService 组合）。"""

    async def _create_target_only_workpapers(
        self,
        project_id: UUID,
        target_only_codes: list[str],
        new_standard: dict,
        changed_by: UUID | None = None,
    ) -> int:
        """目标准则独有底稿创建逻辑（复用 generate_from_codes 子逻辑）。

        目标准则独有底稿是只适用于新准则、不适用旧准则的底稿。切换时这些底稿
        必须被**创建**出来，使新准则下应有的底稿齐全（Requirement 2.1）。

        复用 ``wp_template.generate_from_codes`` 端点已验证的单底稿创建逻辑
        （见 design.md D1）：建 ``WpIndex`` + ``WorkingPaper`` + 模板文件
        + ``parsed_data``。本方法加载一次模板库目录后，逐个 wp_code 委托
        ``_generate_one_workpaper`` 完成创建，返回实际新建的底稿数。

        关于 ``parsed_data``（与 generate_from_codes 的差异，关键）：
        wp-generation-pipeline spec 发现 ``generate_from_codes`` 创建
        ``WorkingPaper`` 后**从不设置 ``parsed_data``**（保持 NULL），导致 HTML
        渲染器显示"有记录无内容"。本任务的验收（Requirement 2.1）明确要求
        "+ parsed_data"，故本方法在创建 ``WorkingPaper`` 后**必定**填充非空
        ``parsed_data``（优先调用 ``wp_parsed_data_service.populate_parsed_data``
        若存在；否则写入最小非空占位 dict），确保新建底稿不为空。

        事务：不调用 ``db.commit()``（提交由编排器 ``convert_workpapers`` 统一
        处理）；仅在需要拿生成主键时 ``flush``。

        Args:
            project_id: 项目 ID
            target_only_codes: 目标准则独有底稿的 wp_code 列表
                （来自 ``classify_workpapers``）
            new_standard: 目标结构化准则（暂未直接消费，保留以对齐其他 helper 签名）
            changed_by: 触发切换的用户（作为新建 WorkingPaper.created_by，可选）

        Returns:
            实际新建的底稿数；``target_only_codes`` 为空时返回 0。
        """
        if not target_only_codes:
            return 0

        # 模板库目录加载一次（降级为空 dict，不阻塞创建——仍会兜底建空模板）
        template_lib = self._load_template_library()
        from app.services.wp_generate_file import load_generation_scenario

        scenario = await load_generation_scenario(self.db, project_id)

        created = 0
        for wp_code in target_only_codes:
            try:
                # 单条 savepoint：失败时该底稿的 WpIndex / WorkingPaper 一并回滚，不留无文件的底稿行
                async with self.db.begin_nested():
                    made = await self._generate_one_workpaper(
                        project_id,
                        wp_code,
                        template_lib.get(wp_code, {}),
                        new_standard,
                        changed_by,
                        scenario=scenario,
                    )
                if made:
                    created += 1
            except Exception as exc:  # 单条失败隔离，不破坏整批切换
                logger.warning(
                    "_create_target_only_workpapers: 创建底稿 %s 失败，跳过: %s",
                    wp_code,
                    exc,
                )

        logger.info(
            "_create_target_only_workpapers: project=%s created=%d/%d",
            project_id,
            created,
            len(target_only_codes),
        )
        return created

    def _load_template_library(self) -> dict[str, dict]:
        """加载致同标准底稿模板库目录为 ``{code: entry}`` 映射（D2）。

        与 ``wp_template.generate_from_codes`` 同源：读取
        ``backend/data/gt_template_library.json``（``encoding="utf-8-sig"`` 以
        兼容 BOM），顶层 ``templates`` 列表中每个条目按 ``code``/``wp_code`` 建索引。
        文件缺失或解析失败时降级为 ``{}``（不阻塞创建，逐条仍可兜底建空模板）。
        """
        if not _TEMPLATE_LIBRARY_PATH.exists():
            logger.info(
                "_load_template_library: 模板库文件不存在(%s)，降级为空映射",
                _TEMPLATE_LIBRARY_PATH,
            )
            return {}
        try:
            with open(_TEMPLATE_LIBRARY_PATH, "r", encoding="utf-8-sig") as f:
                lib_data = json.load(f)
        except Exception as exc:
            logger.warning(
                "_load_template_library: 读取模板库失败，降级为空映射: %s", exc
            )
            return {}

        if isinstance(lib_data, dict):
            entries = lib_data.get("templates", [])
        else:
            entries = lib_data or []

        mapping: dict[str, dict] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            code = item.get("code") or item.get("wp_code") or ""
            if code:
                mapping[code] = item
        return mapping

    async def _generate_one_workpaper(
        self,
        project_id: UUID,
        wp_code: str,
        lib_entry: dict,
        new_standard: dict,
        changed_by: UUID | None,
        *,
        scenario: tuple[str, bool] = ("normal", False),
    ) -> bool:
        """为单个 wp_code 创建底稿（建 WpIndex + WorkingPaper + 模板文件 + parsed_data）。

        复用 ``wp_template.generate_from_codes`` 的单底稿创建子逻辑（design.md D1）：

        1. 若项目已有同 ``wp_code`` 的 ``WpIndex``（含已软删 = 在回收站）→ 跳过（返回 False）。
        2. ``uq_wp_index_project_code (project_id, wp_code)`` 与 ``uq_working_paper_project_index
           (project_id, wp_index_id)`` 都**不含 ``is_deleted``**：原先在此「复活软删索引 + 新插一份
           WorkingPaper」必撞后者（单条保存点回滚后静默跳过）。在回收站的同码底稿由
           ``convert_workpapers`` 先分流（因准则切换移入的两层一起恢复，其余在回执 ``in_recycle_codes`` 注明），
           本方法不再复活（spec procedure-trim-generation-delegation-chain 批 3）。
        3. 否则新建 ``WpIndex``（``status=not_started``）并 ``flush`` 取主键。
        4. 创建 ``WorkingPaper``（``source_type=template`` / ``file_version=1``）并 ``flush`` 取 id。
        5. 模板文件经 ``materialize_workpaper_file``（模板目录索引 + 多文件合并 + 按 ``scenario``
           裁剪，落 ``wp_storage/{pid}/{wp_id}.*``；找不到模板建空白册）。
        6. 尽力（try/except 非致命）绑定 active dataset + 填充表头。
        7. **填充 ``parsed_data``** 使其非空（见 wp-generation-pipeline 发现）。

        Returns:
            True 表示实际新建了一份底稿；False 表示同码已有（含在回收站）而跳过。
        """
        # 1+2. 同码已有任何一行（含软删 = 在回收站）即跳过：唯一索引不含 is_deleted，不复活、不覆盖
        existing_id = (await self.db.execute(
            sa.select(WpIndex.id).where(
                WpIndex.project_id == project_id,
                WpIndex.wp_code == wp_code,
            ).limit(1)
        )).scalar_one_or_none()
        if existing_id is not None:
            return False

        from app.services.wp_name_source import resolve_wp_name
        wp_name = resolve_wp_name(wp_code, lib_entry.get("name"), lib_entry.get("wp_name"))
        cycle = lib_entry.get("cycle_prefix") or (wp_code[0] if wp_code else "X")

        # 3. 新建 WpIndex
        wp_index = WpIndex(
            project_id=project_id,
            wp_code=wp_code,
            wp_name=wp_name,
            audit_cycle=cycle,
            status=WpStatus.not_started,
        )
        self.db.add(wp_index)
        await self.db.flush()  # 取 wp_index.id

        # 4. 创建 WorkingPaper（先落行取 id：文件按 wp_storage/{项目}/{底稿 id} 存放）
        wp = WorkingPaper(
            project_id=project_id,
            wp_index_id=wp_index.id,
            file_path="",
            source_type=WpSourceType.template,
            file_version=1,
            created_by=changed_by,
        )
        self.db.add(wp)
        await self.db.flush()  # 取 wp.id，供文件/表头/绑定/parsed_data 使用

        # 5. 模板文件（与链路编排 / 按编码生成同一解析）
        from app.services.wp_generate_file import materialize_workpaper_file

        generated = materialize_workpaper_file(
            project_id, wp.id, wp_code, wp_name,
            scenario=scenario[0], has_foreign_currency=scenario[1],
        )
        wp.file_path = str(generated.path)
        dest_file = generated.path

        # 6a. 尽力绑定 active dataset（非致命）
        bind_year = await self._derive_year(new_standard, project_id)
        try:
            from app.services.dataset_query import bind_to_active_dataset

            await bind_to_active_dataset(self.db, wp, project_id, bind_year)
        except Exception as exc:
            logger.warning(
                "_generate_one_workpaper: dataset 绑定失败 wp=%s: %s", wp_code, exc
            )

        # 6b. 尽力填充底稿表头（非致命；只动 xlsx，见 fill_generated_workpaper_header）
        from app.services.wp_header_service import fill_generated_workpaper_header

        header_issue = await fill_generated_workpaper_header(
            self.db,
            project_id=project_id,
            wp_id=wp.id,
            path=dest_file,
            wp_code=wp_code,
            wp_name=wp_name,
            cycle=cycle,
            from_template=generated.from_template,
        )
        if header_issue:
            logger.warning("_generate_one_workpaper: 表头未填上 wp=%s: %s", wp_code, header_issue)

        # 7. 填充 parsed_data 使其非空
        #    （wp-generation-pipeline 发现：generate_from_codes 从不设
        #     parsed_data → HTML 渲染器"有记录无内容"；本任务验收要求 +parsed_data）
        await self._populate_parsed_data(wp, wp_code, wp_name, cycle)

        return True

    async def _derive_year(self, new_standard: dict, project_id) -> int:
        """派生用于 dataset 绑定/表头的审计年度；缺省走单一来源。"""
        year = (new_standard or {}).get("year")
        if isinstance(year, int) and year > 0:
            return year
        from app.services.project_audit_year import fetch_project_audit_year
        resolved = await fetch_project_audit_year(self.db, project_id)
        return resolved if resolved is not None else 0

    async def _populate_parsed_data(
        self,
        wp: WorkingPaper,
        wp_code: str,
        wp_name: str,
        cycle: str,
    ) -> None:
        """填充 ``WorkingPaper.parsed_data`` 使其非空（非致命）。

        优先调用 ``wp_parsed_data_service.populate_parsed_data``（若该服务已存在，
        由 wp-generation-pipeline spec 提供，从 xlsx 读 sheet 结构）；该服务尚未
        实现时，回退为写入最小非空占位 dict，保证 ``parsed_data`` 字段非 NULL
        （验收的核心是 parsed_data 被填充，而非 NULL）。
        """
        # 🔴 用 getattr 显式探测而非「调用 + except ImportError」：
        #    `wp_parsed_data_service` 模块**已存在**（有 4 个别的函数），缺的只是
        #    `populate_parsed_data` 这一个属性 → 直接调用抛的是 AttributeError，
        #    落进下面的 `except Exception` 打一条 WARNING，而注释声称的是
        #    「尚未实现 ⇒ ImportError ⇒ 静默回退」。两者行为不同：每生成一张底稿
        #    都会刷一条误导性告警，且把「未实现」与「实现了但跑挂了」混为一谈。
        #    （平台守卫 test_service_call_wiring_integrity.py 抓出此处）
        populate = None
        try:
            from app.services import wp_parsed_data_service  # type: ignore

            populate = getattr(wp_parsed_data_service, "populate_parsed_data", None)
        except ImportError:
            # 模块本身不存在（见 wp-generation-pipeline spec）→ 静默回退占位
            populate = None

        if populate is not None:
            try:
                await populate(self.db, wp, wp_code, wp_name, cycle)
                return
            except Exception as exc:
                # 已实现但执行失败：这才是真需要告警的情形
                logger.warning(
                    "_populate_parsed_data: populate_parsed_data 失败 wp=%s，回退占位: %s",
                    wp_code,
                    exc,
                )

        # 回退：写入最小非空占位，确保 parsed_data 非 NULL（避免 HTML 渲染器
        # "有记录无内容"）。与按编码生成（generate-from-codes）共用同一兜底。
        ensure_parsed_data_placeholder(wp, wp_code=wp_code, created_by="standard_conversion")
