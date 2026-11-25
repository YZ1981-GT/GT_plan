"""
R8/AC-14、AC-15：单位检测摘要、严格合同解析与三端点一致性。

判据来源：`.kiro/specs/platform-global-display-settings-closure`
design §5 + requirements R8。

本文件只测 **本 spec 新增的运行时单源**
（`app/services/ledger_import/unit_normalization.py`）与
「三条 preview/detect 返回同一 UnitDetectionSummary」的接线，
不重复既有 `test_ledger_unit_contract_schema.py` 对 Pydantic 合同的覆盖。
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from app.schemas.ledger_unit_contract import (
    UnitConfirmationInput,
    UnitDetectionSummary,
)
from app.services.ledger_import.unit_normalization import (
    DETECTOR_VERSION,
    UnitContractError,
    build_confirmed_unit_contract,
    classify_unit_label,
    factor_for,
    parse_persisted_unit_contract,
    summarize_detected_units,
)

_BACKEND = Path(__file__).resolve().parents[1]
_USER = UUID("33333333-4444-5555-6666-777777777777")


# ── 1. 标签映射闭集 ───────────────────────────────────────


class TestLabelClassification:
    """`classify_unit_label` 必须闭集：不猜、不静默当元。"""

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("元", "yuan"),
            ("人民币元", "yuan"),
            ("千元", "qian"),
            ("万元", "wan"),
            ("金额单位：万元", "wan"),
            ("单位:千元", "qian"),
            ("单位（万元）", "wan"),
        ],
    )
    def test_supported_labels_map_to_three_enums(self, label: str, expected: str) -> None:
        assert classify_unit_label(label) == expected

    @pytest.mark.parametrize("label", ["百元", "亿元", "美元", "港币", "外币", "原币", "角"])
    def test_unsupported_labels_are_not_guessed(self, label: str) -> None:
        """百元/亿元/外币必须进 unsupported —— 绝不「猜一个最近的」。"""
        assert classify_unit_label(label) == "unsupported"

    def test_unsupported_set_and_supported_set_are_disjoint(self) -> None:
        """两个闭集必须互斥且都非空。

        这条是 M3 变异的**正面判据**：只靠「百元 → unsupported」的断言时，
        把 `"百元"` 从 `UNSUPPORTED_UNIT_LABELS` 里删掉是**等价变异**
        （它落到兜底 `return "unsupported"` 分支，行为完全不变）。
        必须直接断言集合本身，才能把「谁在闭集里」钉住。
        """
        from app.services.ledger_import.unit_normalization import (
            SUPPORTED_UNIT_LABELS,
            UNSUPPORTED_UNIT_LABELS,
        )

        assert SUPPORTED_UNIT_LABELS, "受支持标签集不能为空"
        assert UNSUPPORTED_UNIT_LABELS, "不支持标签集不能为空"
        assert not (set(SUPPORTED_UNIT_LABELS) & set(UNSUPPORTED_UNIT_LABELS))
        assert "百元" in UNSUPPORTED_UNIT_LABELS
        assert "亿元" in UNSUPPORTED_UNIT_LABELS
        assert "外币" in UNSUPPORTED_UNIT_LABELS

    @pytest.mark.parametrize("label", [None, "", "   ", "\t\n"])
    def test_blank_label_is_none_not_unsupported(self, label: str | None) -> None:
        """「没写单位」与「写了不支持的单位」是两种业务事实，不能混。"""
        assert classify_unit_label(label) is None


# ── 2. 检测摘要状态判定 ───────────────────────────────────


class TestSummarizeDetectedUnits:
    def test_single_supported_unit_is_detected(self) -> None:
        det = summarize_detected_units(
            sheets=[("a.xlsx", "Sheet1", "万元"), ("a.xlsx", "Sheet2", "万元")]
        )
        assert det.summary.status == "detected"
        assert det.summary.suggested_unit == "wan"
        assert det.summary.candidates == ["wan"]
        assert det.summary.detector_version == DETECTOR_VERSION

    def test_two_different_supported_units_is_conflict(self) -> None:
        det = summarize_detected_units(
            sheets=[("a.xlsx", "S1", "万元"), ("b.xlsx", "S2", "千元")]
        )
        assert det.summary.status == "conflict"
        assert det.summary.suggested_unit is None
        assert det.summary.candidates == ["qian", "wan"]

    def test_unsupported_dominates_even_if_others_are_yuan(self) -> None:
        """写了不支持的标签时，不能因为「其它 sheet 都是元」就当成 detected。"""
        det = summarize_detected_units(
            sheets=[("a.xlsx", "S1", "元"), ("a.xlsx", "S2", "亿元")]
        )
        assert det.summary.status == "unsupported"
        assert det.summary.unsupported_labels == ["亿元"]
        assert det.summary.suggested_unit is None

    def test_no_labels_at_all_is_missing(self) -> None:
        det = summarize_detected_units(sheets=[("a.xlsx", "S1", None), ("a.xlsx", "S2", "  ")])
        assert det.summary.status == "missing"
        assert det.summary.candidates == []
        assert det.summary.suggested_unit is None

    def test_evidence_digest_is_deterministic_and_order_independent(self) -> None:
        a = summarize_detected_units(
            sheets=[("a.xlsx", "S1", "万元"), ("b.xlsx", "S2", "元")]
        )
        b = summarize_detected_units(
            sheets=[("b.xlsx", "S2", "元"), ("a.xlsx", "S1", "万元")]
        )
        assert a.summary.evidence_digest == b.summary.evidence_digest

    def test_evidence_digest_changes_with_label(self) -> None:
        a = summarize_detected_units(sheets=[("a.xlsx", "S1", "万元")])
        b = summarize_detected_units(sheets=[("a.xlsx", "S1", "千元")])
        assert a.summary.evidence_digest != b.summary.evidence_digest

    def test_evidence_digest_changes_with_file_hash(self) -> None:
        """文件 hash 参与 digest —— 换文件内容必须换摘要。"""
        sheets = [("a.xlsx", "S1", "万元")]
        a = summarize_detected_units(
            sheets=sheets, file_hashes={"a.xlsx": ("a" * 64, 100)}
        )
        b = summarize_detected_units(
            sheets=sheets, file_hashes={"a.xlsx": ("b" * 64, 100)}
        )
        assert a.summary.evidence_digest != b.summary.evidence_digest

    def test_evidence_digest_is_64_lowercase_hex(self) -> None:
        det = summarize_detected_units(sheets=[("a.xlsx", "S1", "元")])
        digest = det.summary.evidence_digest
        assert len(digest) == 64
        assert digest == digest.lower()
        assert all(c in "0123456789abcdef" for c in digest)

    def test_evidence_digest_matches_manual_computation(self) -> None:
        """手工按同一口径重算，证明 digest 不是随机数（可伪证）。"""
        sheets = [("a.xlsx", "S1", "万元")]
        det = summarize_detected_units(
            sheets=sheets, file_hashes={"a.xlsx": ("c" * 64, 7)}
        )
        payload = {
            "detector_version": DETECTOR_VERSION,
            "files": {"a.xlsx": {"sha256": "c" * 64, "size": 7}},
            "labels": [
                {"file": "a.xlsx", "sheet": "S1", "raw_label": "万元", "verdict": "wan"}
            ],
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        assert det.summary.evidence_digest == expected


# ── 3. 严格合同构造与持久化复验 ───────────────────────────


def _detection(status: str = "detected", unit: str = "wan") -> UnitDetectionSummary:
    return UnitDetectionSummary(
        status=status,  # type: ignore[arg-type]
        candidates=[unit],  # type: ignore[list-item]
        unsupported_labels=[],
        suggested_unit=unit,  # type: ignore[arg-type]
        detector_version=DETECTOR_VERSION,
        evidence_digest="e" * 64,
    )


def _confirmation(digest: str = "e" * 64, unit: str = "wan") -> UnitConfirmationInput:
    return UnitConfirmationInput(
        source_amount_unit=unit,  # type: ignore[arg-type]
        source_unit_confirmed=True,
        unit_evidence_digest=digest,
    )


class TestBuildConfirmedContract:
    def test_builds_contract_with_derived_factor(self) -> None:
        contract = build_confirmed_unit_contract(
            detection=_detection(),
            confirmation=_confirmation(),
            confirmed_by=_USER,
        )
        assert contract.source_unit == "wan"
        assert contract.factor == factor_for("wan")
        assert contract.storage_unit == "yuan"
        assert len(contract.contract_digest) == 64

    def test_digest_mismatch_is_rejected(self) -> None:
        """确认必须绑定到「本次看到的检测结果」。"""
        with pytest.raises(UnitContractError) as exc:
            build_confirmed_unit_contract(
                detection=_detection(),
                confirmation=_confirmation(digest="f" * 64),
                confirmed_by=_USER,
            )
        assert exc.value.code == "UNIT_DETECTION_CHANGED"

    def test_job_created_by_mismatch_is_rejected(self) -> None:
        with pytest.raises(UnitContractError) as exc:
            build_confirmed_unit_contract(
                detection=_detection(),
                confirmation=_confirmation(),
                confirmed_by=_USER,
                job_created_by=UUID("44444444-5555-6666-7777-888888888888"),
            )
        assert exc.value.code == "UNIT_CONTRACT_INVALID"

    def test_unsupported_detection_cannot_build_contract(self) -> None:
        with pytest.raises(Exception):  # pydantic ValueError 或 UnitContractError
            build_confirmed_unit_contract(
                detection=_detection(status="unsupported"),
                confirmation=_confirmation(),
                confirmed_by=_USER,
            )


class TestParsePersistedContract:
    def test_roundtrip_succeeds(self) -> None:
        contract = build_confirmed_unit_contract(
            detection=_detection(),
            confirmation=_confirmation(),
            confirmed_by=_USER,
        )
        raw = contract.model_dump(mode="json")
        parsed = parse_persisted_unit_contract(raw, job_created_by=_USER)
        assert parsed.contract_digest == contract.contract_digest

    def test_missing_contract_raises_confirmation_required(self) -> None:
        with pytest.raises(UnitContractError) as exc:
            parse_persisted_unit_contract(None)
        assert exc.value.code == "SOURCE_UNIT_CONFIRMATION_REQUIRED"

    def test_tampered_digest_is_rejected(self) -> None:
        contract = build_confirmed_unit_contract(
            detection=_detection(),
            confirmation=_confirmation(),
            confirmed_by=_USER,
        )
        raw = contract.model_dump(mode="json")
        raw["contract_digest"] = "0" * 64
        with pytest.raises(UnitContractError) as exc:
            parse_persisted_unit_contract(raw)
        assert exc.value.code == "UNIT_CONTRACT_INVALID"

    def test_tampered_source_unit_is_rejected(self) -> None:
        """改 source_unit 但不动 digest —— 必须因 digest 重算不符被拒。"""
        contract = build_confirmed_unit_contract(
            detection=_detection(),
            confirmation=_confirmation(),
            confirmed_by=_USER,
        )
        raw = contract.model_dump(mode="json")
        raw["source_unit"] = "qian"
        raw["factor"] = "1000"
        with pytest.raises(UnitContractError) as exc:
            parse_persisted_unit_contract(raw)
        assert exc.value.code == "UNIT_CONTRACT_INVALID"

    def test_confirmed_by_mismatch_is_rejected(self) -> None:
        contract = build_confirmed_unit_contract(
            detection=_detection(),
            confirmation=_confirmation(),
            confirmed_by=_USER,
        )
        with pytest.raises(UnitContractError) as exc:
            parse_persisted_unit_contract(
                contract.model_dump(mode="json"),
                job_created_by=UUID("55555555-6666-7777-8888-999999999999"),
            )
        assert exc.value.code == "UNIT_CONTRACT_INVALID"

    def test_garbage_type_is_rejected(self) -> None:
        with pytest.raises(UnitContractError) as exc:
            parse_persisted_unit_contract("not-a-contract")
        assert exc.value.code == "UNIT_CONTRACT_INVALID"


# ── 4. 三端点返回同一份 unit_detection（接线判据）─────────


class TestThreeEndpointsShareBuilder:
    """三条正式 preview/detect 必须返回**同一** `UnitDetectionSummary`。

    这里用 AST 而不是「跑三个真实端点」：三条端点各自的 multipart 夹具不同，
    端到端跑通是 B-V 的职责；本类只钉住「同一 builder」这一结构性事实，
    防止有人日后在某一处手写第二套映射（memory 铁律：同一判据合成一处）。
    """

    def _source(self, rel: str) -> str:
        return (_BACKEND / rel).read_text(encoding="utf-8")

    def test_builder_is_single_definition(self) -> None:
        """`build_unit_detection_payload` 全仓必须**恰好一处**定义。

        🔴 位置演进（保留）：本函数原在 `ledger_import_application_service.py`，
        因文件行数门（该文件已在白名单基线 883 行、上限 927）按「超限优先抽模块
        不抬白名单」纪律抽到 `services/ledger_import/unit_detection_wire.py`。
        判据只钉「唯一」，不钉文件名 —— 钉文件名会让纯重构打红（本轮实测）。
        """
        hits = []
        for path in (_BACKEND / "app").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "def build_unit_detection_payload" in text:
                hits.append(path.name)
        assert len(hits) == 1, f"builder 必须唯一，实际 {hits}"

    def test_account_chart_preview_goes_through_service_preview(self) -> None:
        """`/account-chart/preview` 直接调 `LedgerImportApplicationService.preview`。"""
        text = self._source("app/routers/account_chart.py")
        assert "LedgerImportApplicationService.preview(" in text
        # 该端点自己不构造 unit_detection（构造点只有 service 一处）
        assert "unit_detection" not in text

    def test_smart_preview_goes_through_service_preview(self) -> None:
        text = self._source("app/routers/ledger_penetration.py")
        assert "LedgerImportApplicationService.preview(" in text
        assert "unit_detection" not in text

    def test_detect_endpoint_calls_shared_builder(self) -> None:
        """v2 `/ledger-import/detect` 走同一 builder，且不自己写映射规则。"""
        text = self._source("app/routers/ledger_import_v2.py")
        assert "build_unit_detection_payload(" in text
        tree = ast.parse(text)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                getattr(node.func, "attr", None) == "build_unit_detection_payload"
                or getattr(node.func, "id", None) == "build_unit_detection_payload"
            )
        ]
        assert len(calls) == 1, f"detect 端点必须恰好调用一次共享 builder，实际 {len(calls)}"
        keywords = {kw.arg for kw in calls[0].keywords}
        assert {"diagnostics", "project_id", "upload_token"} <= keywords

    def test_service_preview_returns_unit_detection_key(self) -> None:
        text = self._source("app/services/ledger_import_application_service.py")
        tree = ast.parse(text)
        # 找到 preview 的 return 字典，断言含 "unit_detection" 键。
        # 🔴 preview 是 `async def`（ast.AsyncFunctionDef）—— 只查 FunctionDef
        #    会恒找不到，判据变成永远打红的假守卫。
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "preview":
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Return) or not isinstance(inner.value, ast.Dict):
                    continue
                keys = [
                    k.value
                    for k in inner.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                ]
                if "upload_token" in keys:
                    assert "unit_detection" in keys, keys
                    found = True
        assert found, "preview 的 return 字典里找不到 upload_token 键（夹具失锚）"


# ── 5. bundle 证据（旧 bundle 缺 hash 必须拒绝）────────────


class TestBundleEvidence:
    def test_create_bundle_records_sha256_per_file(self) -> None:
        """`create_bundle` 必须在流式落盘时算 hash 并写 manifest。"""
        text = (_BACKEND / "app/services/ledger_import_upload_service.py").read_text(
            encoding="utf-8"
        )
        assert "hashlib.sha256()" in text
        assert "MANIFEST_HASH_KEY: hasher.hexdigest()" in text
        # 必须有「旧 bundle 缺 hash 即拒绝」的机器码
        assert "UPLOAD_BUNDLE_INTEGRITY_FAILED" in text

    def test_evidence_loader_rejects_missing_hash(self) -> None:
        from fastapi import HTTPException

        from app.services.ledger_import_upload_service import LedgerImportUploadService

        manifest = {
            "created_at": "2999-01-01T00:00:00+00:00",
            "files": [{"filename": "a.xlsx", "stored_name": "00_a.xlsx", "size": 3}],
        }
        tmp_dir = _BACKEND / "tmp_bundle_evidence_probe"
        tmp_dir.mkdir(exist_ok=True)
        try:
            (tmp_dir / "00_a.xlsx").write_bytes(b"abc")
            with pytest.raises(HTTPException) as exc:
                LedgerImportUploadService._bundle_evidence_from(
                    tmp_dir, manifest, require_hashes=True
                )
            assert exc.value.status_code == 400
            assert exc.value.detail["error_code"] == "UPLOAD_BUNDLE_INTEGRITY_FAILED"
        finally:
            for child in tmp_dir.iterdir():
                child.unlink()
            tmp_dir.rmdir()

    def test_evidence_loader_detects_tampered_file(self) -> None:
        from fastapi import HTTPException

        from app.services.ledger_import_upload_service import LedgerImportUploadService

        tmp_dir = _BACKEND / "tmp_bundle_evidence_probe2"
        tmp_dir.mkdir(exist_ok=True)
        try:
            (tmp_dir / "00_a.xlsx").write_bytes(b"abc")
            manifest = {
                "created_at": "2999-01-01T00:00:00+00:00",
                "files": [
                    {
                        "filename": "a.xlsx",
                        "stored_name": "00_a.xlsx",
                        "size": 3,
                        "sha256": "0" * 64,  # 与实际内容不符
                    }
                ],
            }
            with pytest.raises(HTTPException) as exc:
                LedgerImportUploadService._bundle_evidence_from(
                    tmp_dir, manifest, require_hashes=True
                )
            assert exc.value.detail["error_code"] == "UPLOAD_BUNDLE_INTEGRITY_FAILED"
        finally:
            for child in tmp_dir.iterdir():
                child.unlink()
            tmp_dir.rmdir()

    def test_evidence_loader_accepts_matching_hash(self) -> None:
        from app.services.ledger_import_upload_service import LedgerImportUploadService

        tmp_dir = _BACKEND / "tmp_bundle_evidence_probe3"
        tmp_dir.mkdir(exist_ok=True)
        try:
            payload = b"abc"
            (tmp_dir / "00_a.xlsx").write_bytes(payload)
            manifest = {
                "created_at": "2999-01-01T00:00:00+00:00",
                "files": [
                    {
                        "filename": "a.xlsx",
                        "stored_name": "00_a.xlsx",
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
            evidence, _ = LedgerImportUploadService._bundle_evidence_from(
                tmp_dir, manifest, require_hashes=True
            )
            assert evidence["a.xlsx"][0] == hashlib.sha256(payload).hexdigest()
        finally:
            for child in tmp_dir.iterdir():
                child.unlink()
            tmp_dir.rmdir()
