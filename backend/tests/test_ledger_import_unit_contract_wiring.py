"""R8 / AC-14~AC-17：单位合同构造、写入 staged、金额只换算一次的**接线**守卫。

本文件守的是「内核已建但从未被调用」这一类假绿（本项目已踩过多次）：
`build_confirmed_unit_contract` / `ledger_amount_kernel` / `classify_dataset_unit`
三块各自都有单测，但**没有一个生产调用方**时全部测试照样绿，而用户导进来的
万元数据会被当成元存库。所以这里只断言生产接线：

1. `execute_pipeline` 有 `unit_confirmation` 关键字参数且**可选**（历史 job 不能失败）；
2. pipeline 在 `create_staged` **之前**构造合同（否则中途失败会留下无证据 staged）；
3. 合同随 staged 的 `source_summary.unit_normalization` 落库，形状可被
   `classify_dataset_unit` 判成 `normalized_v1`；
4. `_insert`（四表写入唯一入口）在写入前按 factor 换算金额；
5. worker 真的把 `options["unit_confirmation"]` 传给 pipeline（AST 判关键字实参）；
6. detect 端点真的缓存摘要（否则 worker 现算的 digest 必与确认时不同）。
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_USER = UUID("11111111-2222-3333-4444-555555555555")


def _tree(rel: str) -> ast.Module:
    return ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str, cls: str | None = None) -> ast.FunctionDef:
    scope: list[ast.AST] = [tree]
    if cls is not None:
        scope = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == cls
        ]
        assert scope, f"找不到类 {cls}"
    for node in ast.walk(scope[0]):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if called == name:
            found.append(child)
    return found


# ── 1. pipeline 签名与顺序 ─────────────────────────────────


class TestPipelineSignature:
    def test_unit_confirmation_param_exists_and_optional(self) -> None:
        func = _func(_tree("app/services/ledger_import/pipeline.py"), "execute_pipeline")
        args = func.args
        names = [a.arg for a in args.kwonlyargs]
        assert "unit_confirmation" in names, "pipeline 缺 unit_confirmation 关键字参数"
        index = names.index("unit_confirmation")
        defaults = args.kw_defaults
        assert defaults[index] is not None, (
            "unit_confirmation 必须是可选（默认 None）—— 历史 job 没有该键，"
            "必填会让全部旧作业失败"
        )
        assert isinstance(defaults[index], ast.Constant)
        assert defaults[index].value is None

    def test_contract_built_before_create_staged(self) -> None:
        """合同必须在 create_staged 之前构造（否则中途失败留下无证据 staged 行）。"""
        func = _func(_tree("app/services/ledger_import/pipeline.py"), "execute_pipeline")
        build_calls = _calls(func, "build_staged_unit_contract")
        staged_calls = _calls(func, "create_staged")
        assert build_calls, "pipeline 从未调用 build_staged_unit_contract（合同不落库）"
        assert staged_calls, "找不到 create_staged 调用（判据失锚）"
        assert build_calls[0].lineno < staged_calls[0].lineno, (
            "build_staged_unit_contract 必须在 create_staged 之前调用"
        )

    def test_contract_passed_into_source_summary(self) -> None:
        func = _func(_tree("app/services/ledger_import/pipeline.py"), "execute_pipeline")
        calls = _calls(func, "staged_source_summary")
        assert calls, "找不到 staged_source_summary 调用（判据失锚）"
        kwargs = {kw.arg for kw in calls[0].keywords}
        assert "unit_contract" in kwargs, (
            "source_summary 构造没有传 unit_contract ⇒ 合同不会落库"
        )

    def test_insert_converts_amounts_before_write(self) -> None:
        """四表写入唯一入口 `_insert` 必须先换算再 bulk_write_staged。"""
        func = _func(_tree("app/services/ledger_import/pipeline.py"), "execute_pipeline")
        inner = [
            node
            for node in ast.walk(func)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_insert"
        ]
        assert inner, "pipeline 里找不到 _insert 内部函数（四表写入入口失锚）"
        body = inner[0]
        convert_calls = _calls(body, "normalize_row_amounts")
        write_calls = _calls(body, "bulk_write_staged")
        assert convert_calls, "四表写入入口从不换算金额（万元数据会当元存库）"
        assert write_calls, "找不到 bulk_write_staged 调用（判据失锚）"
        assert convert_calls[0].lineno < write_calls[0].lineno, (
            "normalize_row_amounts 必须在 bulk_write_staged 之前调用"
        )


# ── 2. worker 真的传参 ────────────────────────────────────


class TestRunnerWiring:
    def test_runner_passes_unit_confirmation_to_pipeline(self) -> None:
        """AST 判关键字实参（注释掉后子串仍在，不能用 `in` 文本匹配）。"""
        func = _func(
            _tree("app/services/import_job_runner.py"), "_execute_v2", "ImportJobRunner"
        )
        calls = _calls(func, "execute_pipeline")
        assert calls, "runner 未调用 execute_pipeline（判据失锚）"
        kwargs = {kw.arg for kw in calls[0].keywords}
        assert "unit_confirmation" in kwargs, (
            "runner 没有把 options['unit_confirmation'] 传给 pipeline ⇒ "
            "合同与金额换算在真实导入里永不生效"
        )


# ── 3. detect 端点缓存摘要 ────────────────────────────────


class TestDetectCachesSummary:
    def test_detect_endpoint_caches_unit_detection(self) -> None:
        """detect 必须缓存摘要本身：worker 侧的 stored_name 与 preview 的原始文件名
        不同 ⇒ 现算 digest 必不同 ⇒ 用户确认过的合同会被判 UNIT_DETECTION_CHANGED。
        """
        func = _func(_tree("app/routers/ledger_import_v2.py"), "detect_files")
        assert _calls(func, "cache_unit_detection"), (
            "detect 端点没有缓存 unit_detection ⇒ 真实导入必然 UNIT_DETECTION_CHANGED"
        )


# ── 4. 行为判据（真跑，不 mock 被测函数）─────────────────


class TestStagedSummaryShape:
    def test_normalized_contract_classifies_as_normalized_v1(self) -> None:
        """合同写入的形状必须能被分类器判成 normalized_v1。"""
        from app.schemas.ledger_unit_contract import (
            UnitConfirmationInput,
            UnitDetectionSummary,
        )
        from app.services.dataset_unit_contract import classify_dataset_unit
        from app.services.ledger_import.append_stage import staged_source_summary
        from app.services.ledger_import.unit_normalization import (
            build_confirmed_unit_contract,
        )

        detection = UnitDetectionSummary(
            status="detected",
            candidates=["wan"],
            unsupported_labels=[],
            suggested_unit="wan",
            detector_version="ledger-unit-detector-v1",
            evidence_digest="a" * 64,
        )
        contract = build_confirmed_unit_contract(
            detection=detection,
            confirmation=UnitConfirmationInput(
                source_amount_unit="wan",
                source_unit_confirmed=True,
                unit_evidence_digest="a" * 64,
            ),
            confirmed_by=_USER,
        )
        summary = staged_source_summary("万元", None, unit_contract=contract)
        assert summary is not None
        assert classify_dataset_unit(summary) == "normalized_v1"
        assert "amount_unit" not in summary, (
            "带合同时不得再写顶层 amount_unit —— 那是 legacy_declared 的判据，"
            "两套口径同时存在会让分类器与前端显示互相矛盾"
        )
        payload = summary["unit_normalization"]
        assert payload["contract"]["storage_unit"] == "yuan"
        assert payload["contract"]["factor"] == "10000"
        assert len(payload["contract"]["contract_digest"]) == 64

    def test_without_contract_keeps_legacy_amount_unit(self) -> None:
        """旧路径（无合同）行为逐字节不变。"""
        from app.services.ledger_import.append_stage import staged_source_summary

        summary = staged_source_summary("万元", None)
        assert summary == {"amount_unit": "万元"}


class TestAmountConversion:
    def test_factor_one_returns_same_list_object(self) -> None:
        """factor == 1（来源即元）必须原样返回同一 list：不复制、不量化。"""
        from app.services.ledger_import.unit_contract_apply import normalize_row_amounts

        rows = [{"debit_amount": Decimal("1234.5")}]
        assert normalize_row_amounts(rows, table_name="tb_ledger", factor=Decimal("1")) is rows

    def test_wan_factor_multiplies_amount_fields_only(self) -> None:
        from app.services.ledger_import.unit_contract_apply import normalize_row_amounts

        rows = [
            {
                "debit_amount": Decimal("1.5"),
                "credit_amount": None,
                "debit_qty": Decimal("7"),
                "summary": "收到货款",
            }
        ]
        out = normalize_row_amounts(
            rows, table_name="tb_ledger", factor=Decimal("10000")
        )
        assert out[0]["debit_amount"] == Decimal("15000.00")
        assert out[0]["credit_amount"] is None, "None 必须原样保留（缺数 ≠ 零）"
        assert out[0]["debit_qty"] == Decimal("7"), "数量列不得换算"
        assert out[0]["summary"] == "收到货款", "非金额列不得改动"
        assert rows[0]["debit_amount"] == Decimal("1.5"), "不得原地改入参"

    def test_invalid_amount_raises_with_code(self) -> None:
        from app.services.ledger_import.unit_contract_apply import normalize_row_amounts

        with pytest.raises(RuntimeError) as exc:
            normalize_row_amounts(
                [{"debit_amount": "abc"}],
                table_name="tb_ledger",
                factor=Decimal("10000"),
            )
        assert "LEDGER_AMOUNT_INVALID" in str(exc.value)

    def test_balance_table_converts_all_eight_columns(self) -> None:
        """余额表 8 个金额列都要换算（清单与只读巡检同源）。"""
        from app.services.ledger_import.unit_contract_apply import normalize_row_amounts
        from app.services.ledger_unit_inspector import AMOUNT_FIELDS

        fields = AMOUNT_FIELDS["tb_balance"]
        rows = [{name: Decimal("1") for name in fields}]
        out = normalize_row_amounts(
            rows, table_name="tb_balance", factor=Decimal("1000")
        )
        for name in fields:
            assert out[0][name] == Decimal("1000.00"), f"{name} 未按千元换算"


class TestCachedDetectionRoundTrip:
    def test_read_cached_returns_none_without_manifest(self, tmp_path: Path) -> None:
        from app.services.ledger_import.unit_detection_wire import (
            read_cached_unit_detection,
        )

        assert read_cached_unit_detection(tmp_path) is None

    def test_read_cached_returns_none_on_broken_json(self, tmp_path: Path) -> None:
        from app.services.ledger_import.unit_detection_wire import (
            read_cached_unit_detection,
        )

        (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
        assert read_cached_unit_detection(tmp_path) is None

    def test_read_cached_returns_payload(self, tmp_path: Path) -> None:
        import json

        from app.services.ledger_import.unit_detection_wire import (
            read_cached_unit_detection,
        )

        payload = {"status": "detected", "evidence_digest": "b" * 64}
        (tmp_path / "manifest.json").write_text(
            json.dumps({"unit_detection": payload}), encoding="utf-8"
        )
        assert read_cached_unit_detection(tmp_path) == payload


class TestContractBuildFailClosed:
    def test_missing_created_by_raises(self) -> None:
        """有合同但无创建人 ⇒ 无法验证确认人 ⇒ 必须抛，不能默认按元。"""
        from app.services.ledger_import.unit_contract_apply import (
            build_staged_unit_contract,
        )

        with pytest.raises(RuntimeError) as exc:
            build_staged_unit_contract(
                detections={},
                file_sources=[],
                unit_confirmation={
                    "source_amount_unit": "wan",
                    "source_unit_confirmed": True,
                    "unit_evidence_digest": "a" * 64,
                },
                created_by=None,
            )
        assert "UNIT_CONTRACT_INVALID" in str(exc.value)

    def test_invalid_confirmation_payload_raises(self) -> None:
        from app.services.ledger_import.unit_contract_apply import (
            build_staged_unit_contract,
        )

        with pytest.raises(RuntimeError) as exc:
            build_staged_unit_contract(
                detections={},
                file_sources=[],
                unit_confirmation={"source_amount_unit": "hundred"},
                created_by=_USER,
            )
        assert "UNIT_CONTRACT_INVALID" in str(exc.value)

    def test_none_confirmation_returns_none(self) -> None:
        """旧作业 / 测试直调：无合同 ⇒ 返回 None（不构造、不换算）。"""
        from app.services.ledger_import.unit_contract_apply import (
            build_staged_unit_contract,
        )

        assert (
            build_staged_unit_contract(
                detections={},
                file_sources=[],
                unit_confirmation=None,
                created_by=None,
            )
            is None
        )


# ── 5. 真跑 pipeline 的差分行为判据 ───────────────────────
#
# 🔴 为什么必须真跑：上面两条形态判据（「调了 build_staged_unit_contract」
#    「调了 normalize_row_amounts」）在磁盘变异下**双双存活** ——
#    把返回值改成 `unit_contract = None`、把守卫改成 `if False and rows:`
#    都能让 AST 判据照绿，而真实导入里合同不落库、金额不换算。
#    差分判据（同一份文件跑两遍：有合同 / 无合同）对这两类变异都会红。


async def _run_pipeline_with_bundle(
    session_factory,
    *,
    tmp_path: Path,
    project_id: UUID,
    unit_confirmation: dict | None,
):
    """在 SQLite 上真跑 v2 管线；`unit_confirmation` 给出时走合同路径。

    bundle 目录里放 `manifest.json`（含 `unit_detection` 缓存与逐文件 sha256），
    与 detect 端点写入的形状一致 —— 这样合同 digest 由缓存决定，
    测试不必自己重算检测摘要。
    """
    import hashlib
    import json
    import sys
    import uuid
    from unittest.mock import patch

    from app.services.ledger_import.pipeline import execute_pipeline

    fixture_dir = _BACKEND / "tests" / "fixtures" / "ledger_samples"
    sys.path.insert(0, str(fixture_dir))
    from minimal_balance_ledger import create_minimal_sample  # type: ignore

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    sample = create_minimal_sample(bundle_dir / "00_minimal.xlsx")
    payload = sample.read_bytes()
    manifest = {
        "upload_token": "t" * 32,
        "project_id": str(project_id),
        "created_by": str(_USER),
        "created_at": "2099-01-01T00:00:00+00:00",
        "total_size": len(payload),
        "files": [
            {
                "filename": "minimal.xlsx",
                "stored_name": sample.name,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        # detect 端点缓存的摘要（digest 由测试钉死，便于构造确认合同）
        "unit_detection": {
            "status": "detected",
            "candidates": ["wan"],
            "unsupported_labels": [],
            "suggested_unit": "wan",
            "detector_version": "ledger-unit-detector-v1",
            "evidence_digest": "a" * 64,
        },
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    async def _noop_rebuild(*_a, **_kw) -> int:
        return 0

    with patch("app.core.database.async_session", session_factory), \
         patch("app.services.ledger_import.pipeline._detect_memory_pressure",
               return_value=True), \
         patch("app.services.smart_import_engine.rebuild_aux_balance_summary",
               _noop_rebuild):
        return await execute_pipeline(
            job_id=uuid.uuid4(),
            project_id=project_id,
            year=2025,
            custom_mapping=None,
            created_by=_USER,
            file_sources=[("minimal.xlsx", sample)],
            force_activate=True,
            unit_confirmation=unit_confirmation,
        )


async def _balance_snapshot(session_factory, project_id: UUID):
    """按科目取余额表金额快照（用于两遍差分比较）。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance

    async with session_factory() as db:
        rows = (await db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.opening_balance,
                TbBalance.closing_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                TbBalance.project_id == project_id,
                TbBalance.is_deleted == sa.false(),
            ).order_by(TbBalance.account_code)
        )).all()
    return rows


@pytest.mark.asyncio
async def test_pipeline_converts_amounts_and_persists_contract(tmp_path: Path) -> None:
    """有合同时：金额 ×10000 落库，且 source_summary 判成 normalized_v1。

    差分口径：同一份文件跑两遍（无合同 = 基线、有合同 = 万元），
    逐科目比较金额 —— 这样不必假设 converter 产出的具体数值。
    """
    import uuid

    import pytest_asyncio  # noqa: F401  (保持与其他用例同风格)
    import sqlalchemy as sa
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

    import app.models.audit_platform_models  # noqa: F401
    import app.models.core  # noqa: F401
    import app.models.dataset_models  # noqa: F401
    from app.models.base import Base
    from app.models.dataset_models import LedgerDataset
    from app.services.dataset_unit_contract import classify_dataset_unit

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        baseline_project = uuid.uuid4()
        confirmed_project = uuid.uuid4()

        base_result = await _run_pipeline_with_bundle(
            factory, tmp_path=tmp_path / "base", project_id=baseline_project,
            unit_confirmation=None,
        )
        assert base_result.success and base_result.balance_rows > 0

        confirmed = await _run_pipeline_with_bundle(
            factory, tmp_path=tmp_path / "wan", project_id=confirmed_project,
            unit_confirmation={
                "source_amount_unit": "wan",
                "source_unit_confirmed": True,
                "unit_evidence_digest": "a" * 64,
            },
        )
        assert confirmed.success, confirmed.error_message

        base_rows = await _balance_snapshot(factory, baseline_project)
        wan_rows = await _balance_snapshot(factory, confirmed_project)
        assert base_rows and wan_rows
        assert len(base_rows) == len(wan_rows), "两次导入的科目行数应相同"

        compared = 0
        for base, wan in zip(base_rows, wan_rows):
            assert base.account_code == wan.account_code
            for index, field in enumerate(
                ("opening_balance", "closing_balance", "debit_amount", "credit_amount"),
                start=1,
            ):
                b, w = base[index], wan[index]
                if b is None:
                    assert w is None, (
                        f"{base.account_code}.{field}: 基线为 None 而合同路径非 None "
                        "（缺数被换算成 0）"
                    )
                    continue
                expected = (Decimal(str(b)) * Decimal("10000")).quantize(Decimal("0.01"))
                assert w == expected, (
                    f"{base.account_code}.{field}: 期望 {expected}（基线 {b} × 10000），"
                    f"实际 {w} —— 金额未按合同 factor 换算"
                )
                compared += 1
        assert compared > 0, "没有任何金额列被比较 ⇒ 差分判据空转"

        async with factory() as db:
            dataset = (await db.execute(
                sa.select(LedgerDataset).where(
                    LedgerDataset.project_id == confirmed_project,
                    LedgerDataset.status == "active",
                )
            )).scalars().first()
        assert dataset is not None
        summary = dataset.source_summary or {}
        assert classify_dataset_unit(summary) == "normalized_v1", (
            f"staged 数据集未被判成 normalized_v1（实际 source_summary={summary}）"
        )
        contract = summary["unit_normalization"]["contract"]
        assert contract["source_unit"] == "wan"
        assert contract["storage_unit"] == "yuan"
        assert contract["factor"] == "10000"
        assert len(contract["contract_digest"]) == 64
        assert "amount_unit" not in summary
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_rejects_digest_mismatch(tmp_path: Path) -> None:
    """确认 digest 与检测摘要不一致 ⇒ 整单失败，且不留下 staged 数据集。"""
    import uuid

    import sqlalchemy as sa
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

    import app.models.audit_platform_models  # noqa: F401
    import app.models.core  # noqa: F401
    import app.models.dataset_models  # noqa: F401
    from app.models.base import Base
    from app.models.dataset_models import LedgerDataset

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project_id = uuid.uuid4()
    try:
        with pytest.raises(RuntimeError) as exc:
            await _run_pipeline_with_bundle(
                factory, tmp_path=tmp_path, project_id=project_id,
                unit_confirmation={
                    "source_amount_unit": "wan",
                    "source_unit_confirmed": True,
                    # 与缓存的 evidence_digest 不一致
                    "unit_evidence_digest": "b" * 64,
                },
            )
        assert "UNIT_DETECTION_CHANGED" in str(exc.value), str(exc.value)

        async with factory() as db:
            datasets = (await db.execute(
                sa.select(LedgerDataset).where(LedgerDataset.project_id == project_id)
            )).scalars().all()
        assert not datasets, "合同校验失败后不得留下任何 dataset 行（staged 也不行）"
    finally:
        await engine.dispose()
