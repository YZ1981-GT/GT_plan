"""TemplateFillService 集成测试（audit-report-template-integration task 7.6）.

验证两阶段流水线核心不变式：
- preview 不创建 deliverable_version / word_export_task（仅写 fill_preview_sessions）
- confirm 创建 word_export_task + 一个 version（version_no=1）
- 再次 preview→confirm（同项目）→ version_no 递增为 2
- KAM 校验（validate_kam_word_mode）单元覆盖

使用内存 SQLite + 真实 python-docx 模板 + 临时存储目录。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from docx import Document
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.phase13_models import WordExportTask, WordExportTaskVersion
from app.models.report_models import FillPreviewSession
from app.services import deliverable_service as deliverable_module
from app.services import template_fill_service as tfs_module
from app.services.template_fill_service import (
    TemplateFillService,
    validate_kam_word_mode,
)
from app.services.template_manifest_loader import TemplateManifestLoader


SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _make_template_dir(base: Path) -> Path:
    """构造临时 manifest 目录 + 含占位符/OPT/NOTE 的报告正文 docx。"""
    tpl_dir = base / "templates"
    (tpl_dir / "report_body").mkdir(parents=True, exist_ok=True)

    doc = Document()
    doc.add_paragraph("致 {{company_full_name}} 全体股东：")
    doc.add_paragraph("我们审计了 {{company_full_name}} {{audit_year}} 年度财务报表。")
    doc.add_paragraph("签字合伙人：{{signing_partner}}")
    doc.add_paragraph("##NOTE:内部提示，定稿删除##")
    # 可选段落 OPT 块
    doc.add_paragraph("##OPT:emphasis:强调事项段##")
    doc.add_paragraph("我们提醒财务报表使用者关注以下事项。")
    doc.add_paragraph("##/OPT:emphasis##")
    doc.add_paragraph("##OPT:key_audit_matters:关键审计事项段##")
    doc.add_paragraph("关键审计事项是我们根据职业判断认为最为重要的事项。")
    doc.add_paragraph("##/OPT:key_audit_matters##")
    doc.save(str(tpl_dir / "report_body" / "test_unqualified_d.docx"))

    manifest = tpl_dir / "template_manifest.json"
    manifest.write_text(
        """
{
  "version": "test-v1",
  "report_body": {
    "unqualified": {
      "type_d": {"simple": "report_body/test_unqualified_d.docx"}
    }
  },
  "financial_statements": {},
  "disclosure_notes": {}
}
""".strip(),
        encoding="utf-8",
    )
    return tpl_dir


@pytest.fixture
def patched_storage(tmp_path, monkeypatch) -> Path:
    """将 STORAGE_ROOT 指向临时目录（preview + deliverable）。"""
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(deliverable_module, "STORAGE_ROOT", storage)
    monkeypatch.setattr(tfs_module, "STORAGE_ROOT", storage)
    return storage


def _build_service(session: AsyncSession, tpl_dir: Path) -> TemplateFillService:
    loader = TemplateManifestLoader(base_dir=tpl_dir)
    svc = TemplateFillService(session, loader=loader)

    async def _fake_map(project_id, db):
        return {
            "company_full_name": "测试有限公司",
            "audit_year": "2025",
            "signing_partner": "",  # 故意留空 → missing_fields 命中
            "report_number": "[报告文号]",  # 也是占位，但模板没用到 → 不应报
        }

    # 避免依赖 ReportPlaceholderService / 真实项目数据
    svc.registry.build_placeholder_map = _fake_map  # type: ignore[assignment]
    return svc


# ---------------------------------------------------------------------------
# preview 不落库
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_does_not_create_deliverable(
    session, tmp_path, patched_storage
):
    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()

    result = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=user_id,
    )

    # 无 word_export_task / version 创建
    tasks = (await session.execute(sa.select(WordExportTask))).scalars().all()
    versions = (
        await session.execute(sa.select(WordExportTaskVersion))
    ).scalars().all()
    assert tasks == []
    assert versions == []

    # 仅写了一条 preview session
    sessions = (
        await session.execute(sa.select(FillPreviewSession))
    ).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].id == result.preview_session_id

    # OPT 扫描出 emphasis + key_audit_matters
    opt_ids = {v.section_id for v in result.optional_sections}
    assert opt_ids == {"emphasis", "key_audit_matters"}

    # missing_fields：中文、只列模板实际用到且仍为空 / 方括号占位的字段（spec deliverable-trio-generation-accuracy
    # AC-4.5；旧口径返回映射里全部空字段的英文键，含模板根本没用到的 report_number）
    assert "签字合伙人" in result.missing_fields
    assert "报告文号" not in result.missing_fields
    assert not any(k in result.missing_fields for k in ("signing_partner", "report_number"))
    assert result.company_subtype_resolved == "type_d"
    assert result.template_version == "test-v1"


# ---------------------------------------------------------------------------
# confirm 创建 version + version_no 递增
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_creates_version_and_increments(
    session, tmp_path, patched_storage
):
    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # --- 第一轮 preview → confirm ---
    preview1 = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=user_id,
    )
    confirm1 = await svc.confirm_report_body(
        project_id,
        2025,
        preview_session_id=preview1.preview_session_id,
        optional_sections={"emphasis": False, "key_audit_matters": True},
        user_id=user_id,
    )
    # create_task 预置空 v1 占位版本；render_and_store 落内容版本 → v2
    first_version = confirm1.version_no
    assert first_version >= 1

    # 创建了一个 task
    tasks = (await session.execute(sa.select(WordExportTask))).scalars().all()
    assert len(tasks) == 1
    versions_after_1 = (
        await session.execute(sa.select(WordExportTaskVersion))
    ).scalars().all()
    count_after_1 = len(versions_after_1)
    assert count_after_1 >= 1

    # preview session 已删除（confirm 时清理）
    sessions = (
        await session.execute(sa.select(FillPreviewSession))
    ).scalars().all()
    assert sessions == []

    # report_body_json schema（需求 6.8）
    body = confirm1.report_body_json
    assert body["optional_sections"] == {
        "emphasis": False,
        "key_audit_matters": True,
    }
    assert body["template_version"] == "test-v1"
    assert body["company_subtype"] == "type_d"
    assert body["template_variant"] == "simple"
    assert "签字合伙人" in body["missing_fields"]
    assert body["opinion_choice"] == "unqualified"
    # confirm 时没有 audit_report 行 → 建一行（意见 / 公司类型 / 是否公众利益实体由报告选项推得），正文 schema 落库
    from app.models.report_models import AuditReport

    report = (await session.execute(sa.select(AuditReport))).scalars().one()
    assert report.opinion_type.value == "unqualified" and report.company_type.value == "non_listed"
    assert report.is_pie is False and report.report_body_json["company_subtype"] == "type_d"
    # 交付件版本绑定了试算表快照（stale 判定依据）
    task = (await session.execute(sa.select(WordExportTask))).scalars().one()
    assert isinstance(task.source_snapshot_refs, dict) and task.source_snapshot_refs.get("doc_type") == "audit_report"
    # guidance 副本与内容版本号一致
    assert body["guidance_version_path"].endswith(
        f"with_notes_v{first_version}.docx"
    )

    # guidance 副本已落盘
    assert Path(body["guidance_version_path"]).exists()

    # --- 第二轮 preview → confirm（同项目）→ version_no 递增 ---
    preview2 = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=user_id,
    )
    confirm2 = await svc.confirm_report_body(
        project_id,
        2025,
        preview_session_id=preview2.preview_session_id,
        optional_sections={"emphasis": True, "key_audit_matters": True},
        user_id=user_id,
    )
    assert confirm2.version_no == first_version + 1

    # 仍是同一个 task（复用），版本数 +1
    tasks = (await session.execute(sa.select(WordExportTask))).scalars().all()
    assert len(tasks) == 1
    versions_after_2 = (
        await session.execute(sa.select(WordExportTaskVersion))
    ).scalars().all()
    assert len(versions_after_2) == count_after_1 + 1


# ---------------------------------------------------------------------------
# 清洁版不含 NOTE（guidance 副本含 NOTE）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_strips_notes_from_clean_copy(
    session, tmp_path, patched_storage
):
    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()

    preview = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=user_id,
    )
    confirm = await svc.confirm_report_body(
        project_id,
        2025,
        preview_session_id=preview.preview_session_id,
        optional_sections={"emphasis": False, "key_audit_matters": True},
        user_id=user_id,
    )

    # 正式版（task.file_path）不含 NOTE 标记
    task = (await session.execute(sa.select(WordExportTask))).scalars().one()
    clean_doc = Document(task.file_path)
    clean_text = "\n".join(p.text for p in clean_doc.paragraphs)
    assert "##NOTE" not in clean_text
    # 未勾选的 emphasis 段被删除，勾选的 KAM 保留
    assert "强调事项" not in clean_text
    assert "关键审计事项" in clean_text

    # guidance 副本仍含 NOTE
    guidance_doc = Document(confirm.guidance_version_path)
    guidance_text = "\n".join(p.text for p in guidance_doc.paragraphs)
    assert "##NOTE" in guidance_text


# ---------------------------------------------------------------------------
# 过期 session confirm 被拒
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_rejects_expired_session(
    session, tmp_path, patched_storage
):
    from datetime import datetime, timedelta, timezone

    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()

    preview = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=user_id,
    )
    # 人为过期
    sess = await session.get(FillPreviewSession, preview.preview_session_id)
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.flush()

    with pytest.raises(ValueError, match="过期"):
        await svc.confirm_report_body(
            project_id,
            2025,
            preview_session_id=preview.preview_session_id,
            optional_sections={"key_audit_matters": True},
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_confirm_rejects_wrong_user(session, tmp_path, patched_storage):
    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)
    project_id = uuid.uuid4()

    preview = await svc.preview_report_body(
        project_id,
        2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        user_id=uuid.uuid4(),
    )
    with pytest.raises(ValueError, match="用户"):
        await svc.confirm_report_body(
            project_id,
            2025,
            preview_session_id=preview.preview_session_id,
            optional_sections={"key_audit_matters": True},
            user_id=uuid.uuid4(),  # 不同用户
        )


# ---------------------------------------------------------------------------
# purge_expired_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_expired_sessions(session, tmp_path, patched_storage):
    from datetime import datetime, timedelta, timezone

    tpl_dir = _make_template_dir(tmp_path)
    svc = _build_service(session, tpl_dir)

    p1 = await svc.preview_report_body(
        uuid.uuid4(), 2025, opinion_type="unqualified",
        company_subtype="type_d", template_variant="simple", user_id=uuid.uuid4(),
    )
    p2 = await svc.preview_report_body(
        uuid.uuid4(), 2025, opinion_type="unqualified",
        company_subtype="type_d", template_variant="simple", user_id=uuid.uuid4(),
    )
    # p1 过期，p2 未过期
    s1 = await session.get(FillPreviewSession, p1.preview_session_id)
    s1.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.flush()

    purged = await svc.purge_expired_sessions()
    assert purged == 1

    remaining = (
        await session.execute(sa.select(FillPreviewSession))
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == p2.preview_session_id


# ---------------------------------------------------------------------------
# validate_kam_word_mode 单元
# ---------------------------------------------------------------------------


def test_validate_kam_listed_unchecked_warns():
    warning = validate_kam_word_mode(
        optional_sections={"key_audit_matters": False},
        company_type="listed",
        is_pie=False,
        opinion_type="unqualified",
    )
    assert warning is not None
    assert "关键审计事项" in warning


def test_validate_kam_listed_checked_ok():
    warning = validate_kam_word_mode(
        optional_sections={"key_audit_matters": True},
        company_type="listed",
        is_pie=False,
        opinion_type="unqualified",
    )
    assert warning is None


def test_validate_kam_non_listed_no_warning():
    warning = validate_kam_word_mode(
        optional_sections={"key_audit_matters": False},
        company_type="non_listed",
        is_pie=False,
        opinion_type="unqualified",
    )
    assert warning is None


def test_validate_kam_disclaimer_no_warning():
    warning = validate_kam_word_mode(
        optional_sections={"key_audit_matters": False},
        company_type="listed",
        is_pie=True,
        opinion_type="disclaimer",
    )
    assert warning is None


# ---------------------------------------------------------------------------
# 正文后处理接线（spec deliverable-trio-generation-accuracy §3）
# ---------------------------------------------------------------------------


def _make_heading_template_dir(base: Path) -> Path:
    """单体简版形态：中文序号章节标题 + 未闭合的「单体复核」行内 NOTE（集团审计条款）+ 写死的落款年份。"""
    tpl_dir = base / "templates_h"
    (tpl_dir / "report_body").mkdir(parents=True, exist_ok=True)
    doc = Document()
    for text in (
        "{{company_full_name}}董事会：", "一、审计意见", "我们审计了{{company_full_name}}财务报表。",
        "二、形成审计意见的基础", "我们按照中国注册会计师审计准则的规定执行了审计工作。",
        "三、管理层和治理层对财务报表的责任", "管理层负责编制财务报表。",
        "四、注册会计师对财务报表审计的责任", "（5）评价财务报表的总体列报。",
        "##NOTE:单体复核:以下涉及合并/集团审计，单体报告可能需删除或调整## （6）我们负责指导、监督和执行集团审计。",
        "二○二二年X月XX日",
    ):
        p = doc.add_paragraph()
        p.add_run(text).bold = text[:2] in ("一、", "二、", "三、", "四、")
    doc.save(str(tpl_dir / "report_body" / "h_unqualified_d.docx"))
    (tpl_dir / "template_manifest.json").write_text(
        '{"version": "test-h1", "report_body": {"unqualified": {"type_d": {"simple": "report_body/h_unqualified_d.docx"}}},'
        ' "financial_statements": {}, "disclosure_notes": {}}',
        encoding="utf-8",
    )
    return tpl_dir


@pytest.mark.asyncio
async def test_emphasis_choice_end_to_end_and_standalone_cleanup(session, tmp_path, patched_storage, monkeypatch):
    from app.models.report_models import AuditReport
    from app.services.full_deliverables_executor import FullDeliverablesExecutor

    svc = _build_service(session, _make_heading_template_dir(tmp_path))

    async def _standalone(_pid):
        return "standalone"

    monkeypatch.setattr(svc, "_resolve_report_scope", _standalone)
    project_id, user_id = uuid.uuid4(), uuid.uuid4()
    preview = await svc.preview_report_body(
        project_id, 2025, opinion_type="unqualified_with_emphasis", company_subtype="type_d",
        template_variant="simple", user_id=user_id,
    )
    assert "强调事项段（所强调的事项与附注编号）" in preview.missing_fields
    await svc.confirm_report_body(
        project_id, 2025, preview_session_id=preview.preview_session_id, optional_sections={}, user_id=user_id,
    )
    task = (await session.execute(sa.select(WordExportTask))).scalars().one()
    texts = [p.text for p in Document(task.file_path).paragraphs]
    assert [t for t in texts if t[:2] in ("一、", "二、", "三、", "四、", "五、")] == [
        "一、审计意见", "二、形成审计意见的基础", "三、强调事项", "四、管理层和治理层对财务报表的责任",
        "五、注册会计师对财务报表审计的责任",
    ]
    joined = "\n".join(texts)
    assert "集团审计" not in joined and "##" not in joined  # 单体报告删集团审计条款，标记不进交付件
    assert "二〇二六年X月XX日" in joined  # 落款年份 = 审计年度 + 1
    report = (await session.execute(sa.select(AuditReport))).scalars().one()
    assert report.opinion_type.value == "unqualified"  # 枚举只有四族
    assert report.report_body_json["opinion_choice"] == "unqualified_with_emphasis"
    # 一键生成全套沿用同一选择（否则下次全套生成就丢了强调事项段）
    assert FullDeliverablesExecutor._opinion_value(report) == "unqualified_with_emphasis"


# ---------------------------------------------------------------------------
# 报表口径回退（spec consol-autotree-residual-closure R6）
# ---------------------------------------------------------------------------


class _ProjectOnlyDB:
    """只回答 ``db.get(Project, id)`` 的桩：口径解析只读这一行。"""

    def __init__(self, project):
        self._project = project

    async def get(self, _model, _pk):
        return self._project


def _project(report_scope, wizard_state):
    from types import SimpleNamespace

    return SimpleNamespace(report_scope=report_scope, wizard_state=wizard_state)


def _steps(scope):
    return {"basic_info": {"data": {"report_scope": scope}}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("report_scope", "wizard_state", "expected"),
    [
        # 向导建项目、保存基本信息只写 steps；原实现只读平铺位置 ⇒ 单体项目的报告正文按合并口径生成
        (None, {"steps": _steps("standalone")}, "standalone"),
        (None, {"steps": _steps("consolidated"), "basic_info": {"data": {"report_scope": "standalone"}}},
         "consolidated"),  # steps 优先于旧平铺
        (None, {"basic_info": {"data": {"report_scope": "standalone"}}}, "standalone"),  # 旧数据兜底
        ("standalone", {"steps": _steps("consolidated")}, "standalone"),  # 项目列是权威源
        ("", {}, "consolidated"),
        (None, None, "consolidated"),
    ],
)
async def test_resolve_report_scope_reads_wizard_steps_first(report_scope, wizard_state, expected):
    svc = TemplateFillService(_ProjectOnlyDB(_project(report_scope, wizard_state)), loader=object(), registry=object())
    assert await svc._resolve_report_scope(uuid.uuid4()) == expected


@pytest.mark.asyncio
async def test_resolve_report_scope_missing_project_defaults_consolidated():
    svc = TemplateFillService(_ProjectOnlyDB(None), loader=object(), registry=object())
    assert await svc._resolve_report_scope(uuid.uuid4()) == "consolidated"
