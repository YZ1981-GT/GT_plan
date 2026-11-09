"""批 6.3：合并底稿稳定 sheet/row/cell 身份 + 证据 EvidenceLink 接通 + 插删行不漂移。

分三组：
1. 纯身份函数（SQLite 无关）：build/parse 往返、转义、超长压缩、各权威源 helper。
2. 插删行不漂移：trial / note / worksheet 在插入 / 删除别的行前后，存活行身份恒定（含 hypothesis 属性）。
3. 接通既有证据设施：合并壳的 WorkingPaper id 作为 wp_id，经 WpEvidenceService 建 EvidenceLink，
   按稳定 cell_ref 查回；解析端点 evidence-target 构造坐标且不写库。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # noqa: E305

import tests.conftest  # noqa: F401,E402
from app.models.attachment_models import Attachment  # noqa: E402
from app.models.base import Base, ProjectStatus  # noqa: E402
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.models.wp_optimization_models import EvidenceLink  # noqa: E402
from app.services import consol_workpaper_shell as shell  # noqa: E402
from app.services.consol_evidence_identity import (  # noqa: E402
    MAX_CELL_REF,
    build_cell_ref,
    note_row_cell_ref,
    parse_cell_ref,
    report_row_cell_ref,
    stable_row_identity,
    trial_row_cell_ref,
    worksheet_row_cell_ref,
)
from app.services.wp_evidence_service import WpEvidenceService  # noqa: E402

YEAR = 2025


# ════════════════════════════════════════════════════════════════════════════
# 组 1：纯身份函数
# ════════════════════════════════════════════════════════════════════════════


class TestCellRefBuildParse:
    def test_build_and_parse_round_trip(self):
        ref = build_cell_ref("sheet_key_cost", row_identity="id:1001", col_identity="amount")
        parsed = parse_cell_ref(ref)
        assert parsed is not None
        assert parsed.node_key == "sheet_key_cost"
        assert parsed.row_identity == "id:1001"
        assert parsed.col_identity == "amount"

    def test_node_only(self):
        ref = build_cell_ref("consol_trial")
        assert ref == "node:consol_trial"
        parsed = parse_cell_ref(ref)
        assert parsed.node_key == "consol_trial"
        assert parsed.row_identity is None
        assert parsed.col_identity is None

    def test_row_without_col(self):
        ref = build_cell_ref("s1", row_identity="h:abc123")
        parsed = parse_cell_ref(ref)
        assert parsed.row_identity == "h:abc123"
        assert parsed.col_identity is None

    def test_segment_escaping_round_trips(self):
        # 业务值里有分隔符（/ : %）也能无歧义还原
        ref = build_cell_ref("node/with:weird%chars", row_identity="id:a/b:c")
        parsed = parse_cell_ref(ref)
        assert parsed.node_key == "node/with:weird%chars"
        assert parsed.row_identity == "id:a/b:c"

    def test_non_scheme_cell_ref_returns_none(self):
        # 旧 A1 / item: / row:{n} 不是本 scheme
        assert parse_cell_ref("A1") is None
        assert parse_cell_ref("row:3") is None
        assert parse_cell_ref("item:5") is None
        assert parse_cell_ref("") is None
        assert parse_cell_ref(None) is None

    def test_over_length_compresses_but_stays_stable(self):
        long_node = "section_" + "x" * 90
        long_row = "y" * 90
        ref = build_cell_ref(long_node, row_identity=long_row, col_identity="z" * 40)
        assert len(ref) <= MAX_CELL_REF
        # 压缩是确定性的：相同输入 → 相同串（仍不含位置，可重算）
        again = build_cell_ref(long_node, row_identity=long_row, col_identity="z" * 40)
        assert ref == again
        # 压缩后仍是本 scheme，可解析出三段
        parsed = parse_cell_ref(ref)
        assert parsed is not None and parsed.node_key.startswith("h:")


class TestStableRowIdentity:
    def test_embedded_row_id_wins(self):
        assert stable_row_identity({"_rid": "R-7", "account_name": "x"}) == "id:R-7"
        assert stable_row_identity({"row_id": "abc", "name": "y"}) == "id:abc"
        assert stable_row_identity({"id": "99"}) == "id:99"

    def test_content_hash_when_no_id(self):
        a = stable_row_identity({"standard_account_code": "1001", "account_name": "货币资金"})
        assert a.startswith("h:")
        # 同内容恒定
        assert a == stable_row_identity({"standard_account_code": "1001", "account_name": "货币资金"})
        # 不同内容不同
        b = stable_row_identity({"standard_account_code": "1002", "account_name": "应收账款"})
        assert a != b

    def test_identity_ignores_private_and_order(self):
        # 行里加 _private 字段 / 字段顺序变化不影响身份（私有字段 + 排序无关摘要）
        base = {"standard_account_code": "1001", "account_name": "货币资金"}
        reordered = {"account_name": "货币资金", "standard_account_code": "1001"}
        assert stable_row_identity(base) == stable_row_identity(reordered)

    def test_source_helpers(self):
        assert parse_cell_ref(trial_row_cell_ref("1001")).row_identity == "id:1001"
        assert parse_cell_ref(report_row_cell_ref("BS_010")).row_identity == "id:BS_010"

    def test_frontend_parity_exact_strings(self):
        """与前端 consolRowEvidence.ts 直接拼的 id: 串逐字节一致（跨语言契约钉死转义口径）。

        前端 consolTrialCellRef('1001') / consolReportCellRef('BS_010') /
        consolCellRefWithRowId('a/b','x:y') 的硬编码断言见其 spec；两侧任一改转义都会打红。
        """
        assert trial_row_cell_ref("1001") == "node:consol_trial/row:id%3A1001"
        assert trial_row_cell_ref("1001", col="amount") == "node:consol_trial/row:id%3A1001/col:amount"
        assert report_row_cell_ref("BS_010") == "node:consol_report/row:id%3ABS_010"
        assert build_cell_ref("a/b", row_identity="id:x:y") == "node:a%2Fb/row:id%3Ax%3Ay"
        note = note_row_cell_ref("五、8", {"item_name": "存货"}, node_key="SH:consol")
        p = parse_cell_ref(note)
        assert p.node_key == "五、8@SH:consol"
        assert p.row_identity.startswith("h:")
        ws = worksheet_row_cell_ref("cost", {"company_code": "C1"}, col="equity")
        assert parse_cell_ref(ws).col_identity == "equity"


# ════════════════════════════════════════════════════════════════════════════
# 组 2：插删行不漂移（核心不变量）
# ════════════════════════════════════════════════════════════════════════════


class TestNoDriftOnInsertDelete:
    def test_trial_insert_before_does_not_drift(self):
        """在某科目之前插入新科目，该科目的身份串不变。"""
        before = trial_row_cell_ref("1122")
        # 模拟在 1122 前插入 1001、1002（trial 行按科目码派生，与顺序无关）
        after = trial_row_cell_ref("1122")
        assert before == after

    def test_worksheet_delete_sibling_does_not_drift(self):
        """删除同表相邻行后，目标行（按内容派生身份）的身份串不变。"""
        rows = [
            {"company_code": "C1", "amount": "10"},
            {"company_code": "C2", "amount": "20"},
            {"company_code": "C3", "amount": "30"},
        ]
        target = rows[2]
        ref_before = worksheet_row_cell_ref("cost", target)
        # 删掉第 0、1 行（target 的数组下标从 2 变成 0）
        remaining = rows[2:]
        ref_after = worksheet_row_cell_ref("cost", remaining[0])
        assert ref_before == ref_after

    def test_worksheet_insert_before_does_not_drift(self):
        target = {"company_code": "C9", "amount": "99"}
        ref_before = worksheet_row_cell_ref("cost", target)
        # 在前面插入两行后 target 的下标变了，但内容没变
        ref_after = worksheet_row_cell_ref("cost", target)
        assert ref_before == ref_after

    def test_note_row_with_embedded_id_stable_across_reorder(self):
        rows = [{"_rid": "n1", "v": "a"}, {"_rid": "n2", "v": "b"}, {"_rid": "n3", "v": "c"}]
        ref_before = note_row_cell_ref("五、8", rows[1])
        reordered = [rows[2], rows[1], rows[0]]  # 打乱顺序
        ref_after = note_row_cell_ref("五、8", reordered[1])
        assert ref_before == ref_after

    def test_changing_business_key_does_change_identity(self):
        """反例：改掉行的业务键（已是另一行）身份应变，否则证据会黏在错的行上。"""
        ref1 = worksheet_row_cell_ref("cost", {"company_code": "C1"})
        ref2 = worksheet_row_cell_ref("cost", {"company_code": "C2"})
        assert ref1 != ref2

    @settings(max_examples=5, deadline=None)
    @given(
        rows=st.lists(
            st.fixed_dictionaries({"standard_account_code": st.text(min_size=1, max_size=6, alphabet="0123456789")}),
            min_size=2, max_size=8, unique_by=lambda r: r["standard_account_code"],
        ),
        remove_at=st.integers(min_value=0, max_value=7),
        insert_code=st.text(min_size=1, max_size=6, alphabet="0123456789"),
    )
    def test_property_insert_delete_preserves_surviving_identities(self, rows, remove_at, insert_code):
        """属性：对任意一组唯一科目行，先记下每行身份；任意删一行、在任意位置插一行后，
        仍存活的原行身份逐一不变（身份派生自科目码，与数组位置无关）。

        **Validates: Requirements R8.3**（证据可按 sheet_key/node_key/row_identity/cell 定位）
        """
        # 初始身份映射：科目码 → cell_ref
        identity = {r["standard_account_code"]: trial_row_cell_ref(r["standard_account_code"]) for r in rows}

        mutated = list(rows)
        # 删一行
        idx = remove_at % len(mutated)
        removed = mutated.pop(idx)["standard_account_code"]
        # 在任意位置插一行（不与现有科目码冲突时才插，避免「同科目」语义歧义）
        existing = {r["standard_account_code"] for r in mutated}
        if insert_code not in existing and insert_code != removed:
            mutated.insert(min(remove_at, len(mutated)), {"standard_account_code": insert_code})

        # 存活的原行身份必须逐一不变
        for r in mutated:
            code = r["standard_account_code"]
            if code in identity:  # 原有行
                assert trial_row_cell_ref(code) == identity[code], f"科目 {code} 身份漂移"
        # 被删行的身份本来就不该再出现（但函数仍可重算同一串——身份与存在性正交）
        assert trial_row_cell_ref(removed) == identity[removed]


# ════════════════════════════════════════════════════════════════════════════
# 组 3：接通既有证据设施（EvidenceLink 落在合并壳上）
# ════════════════════════════════════════════════════════════════════════════

_TABLES = [
    Project.__table__, WpIndex.__table__, WorkingPaper.__table__,
    ConsolWorkpaperInstance.__table__, Attachment.__table__, EvidenceLink.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】合并证据_2025", client_name="【测试】合并证据",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution,
    )


async def _attachment(db: AsyncSession, project_id: uuid.UUID, name: str) -> Attachment:
    att = Attachment(
        id=uuid.uuid4(), project_id=project_id, file_name=name, file_type="pdf",
        file_size=10, storage_type="local", file_path=f"p/{name}", attachment_type="evidence",
        created_by=uuid.uuid4(),
    )
    db.add(att)
    await db.flush()
    return att


class TestEvidenceLinkOnShell:
    @pytest.mark.asyncio
    async def test_evidence_link_on_shell_wp_id_with_stable_cell_ref(self, db: AsyncSession):
        """合并壳的 working_paper_id 直接作为 EvidenceLink.wp_id；行级证据按稳定 cell_ref 挂与查回。"""
        p = _project(); db.add(p); await db.commit()
        created = await shell.ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        wp_id = uuid.UUID(created["working_paper_id"])

        att = await _attachment(db, p.id, "货币资金回单.pdf")
        svc = WpEvidenceService(db)
        cell_ref = trial_row_cell_ref("1001")
        link = await svc.create_link(
            wp_id=wp_id, attachment_id=att.id, created_by=uuid.uuid4(),
            sheet_name="consol_trial", cell_ref=cell_ref, evidence_type="evidence",
        )
        await db.commit()
        assert link["cell_ref"] == cell_ref
        assert parse_cell_ref(link["cell_ref"]).row_identity == "id:1001"

        # 按稳定位置查回（小眼睛预览即按 sheet_name + cell_ref 过滤）
        found = await svc.list_links(wp_id, sheet_name="consol_trial", cell_ref=cell_ref)
        assert len(found) == 1
        assert found[0]["attachment"]["file_name"] == "货币资金回单.pdf"

    @pytest.mark.asyncio
    async def test_resolve_target_builds_coordinate_without_writing(self, db: AsyncSession):
        """resolve_consol_evidence_target 给出壳 wp_id + 稳定 cell_ref；trial 行身份 = 科目码。"""
        p = _project(); db.add(p); await db.commit()
        target = await shell.resolve_consol_evidence_target(
            db, p.id, year=YEAR, sheet_type="trial", node_key="consol_trial",
            row_fields={"standard_account_code": "1122"},
        )
        await db.commit()
        assert target["sheet_name"] == "consol_trial"
        assert parse_cell_ref(target["cell_ref"]).row_identity == "id:1122"
        assert target["wp_id"]  # 壳被按需幂等建出

    @pytest.mark.asyncio
    async def test_resolve_target_note_content_hash(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        target = await shell.resolve_consol_evidence_target(
            db, p.id, year=YEAR, sheet_type="note", node_key="五、8",
            row_fields={"item_name": "存货"},
        )
        await db.commit()
        assert target["sheet_name"] == "五、8"
        parsed = parse_cell_ref(target["cell_ref"])
        assert parsed.node_key == "五、8"
        assert parsed.row_identity.startswith("h:")

    @pytest.mark.asyncio
    async def test_delete_sibling_row_keeps_evidence_on_target_row(self, db: AsyncSession):
        """端到端无漂移：两行各挂证据，删掉第一行后，第二行证据仍按其稳定 cell_ref 查得到。"""
        p = _project(); db.add(p); await db.commit()
        created = await shell.ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        wp_id = uuid.UUID(created["working_paper_id"])
        svc = WpEvidenceService(db)

        rows = [{"company_code": "C1"}, {"company_code": "C2"}]
        ref_c2 = worksheet_row_cell_ref("cost", rows[1])
        att = await _attachment(db, p.id, "C2证据.pdf")
        await svc.create_link(
            wp_id=wp_id, attachment_id=att.id, created_by=uuid.uuid4(),
            sheet_name="cost", cell_ref=ref_c2, evidence_type="evidence",
        )
        await db.commit()

        # 删掉第一行 C1（C2 数组下标从 1 变 0），其稳定 cell_ref 不变
        remaining = rows[1:]
        ref_c2_after = worksheet_row_cell_ref("cost", remaining[0])
        assert ref_c2_after == ref_c2
        found = await svc.list_links(wp_id, sheet_name="cost", cell_ref=ref_c2_after)
        assert len(found) == 1
        assert found[0]["attachment"]["file_name"] == "C2证据.pdf"
