# -*- coding: utf-8 -*-
"""Task 17 纯域守卫：Excel instrumentation definition 生成器与载体裁决门。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 17
Requirements: 2.1, 2.3, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 9.1, 9.8, 9.9,
9.10, 14.16
Properties: **P28** / **P66** / **P67** / **P71**

═══ 为什么本文件用**真实权威模板**而不是构造的最小 xlsx ═══

Requirement 6.17 要的等价性是「可见 sheet / 业务值 / 公式 / 样式 / merge /
drawing·chart·pivot 受保护部件」六项。一个手搓的 3 部件 xlsx 上这六项全是空集，
`equivalent == True` 于是恒真 —— 判据空转，正是假绿第③源（把错值/空值当基线锁死）。

所以：

* **K11**（`backend/wp_templates/K/K11 资产减值损失.xlsx`，7 sheet / 450 公式 /
  54 merge / 1 drawing）承担结构主线；
* **C24**（`backend/wp_templates/C/C24 会计分录 - 细节测试.xlsx`）是**全平台 351 个
  模板里唯一含 `xl/charts/` 部件的一个**（8 chart / 3 drawing / 1 media）⇒ 受保护部件
  这一格只能由它回答。

两份模板都**只读**：`test_authority_templates_are_untouched` 在跑完全部注入后重算
sha256，与 Task 5 记录的 `dc0e5434…` / `b70229f4…` 逐字比对（Requirement 9.9：
不得在运行时写回模板库）。

═══ 判据形态 ═══

* 契约门：把契约**复制**一份改字段再 load，看是否 fail closed（不改仓库里的真契约）；
* 注入：真 zip 进真 zip 出，再用生产反读函数读回来比对；
* Requirement 6.15 三形态：在 instrumented 字节上做**真实 zip 编辑**（删一行 UUID、
  复制一个 UUID、整列删掉）再反读，断言各自专属的失败/分类；
* 业务排除：调用**生产函数本体** `list_sheet_names` / `xlsx_to_univer_data`，
  不是断言「代码里有 exclude 调用」。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_metadata_sheet_policy import (  # noqa: E402
    PLATFORM_METADATA_SHEETS,
    exclude_metadata_sheets,
)
from app.services.excel_structure_fingerprint import (  # noqa: E402
    GT_SYNC_SHEET_NAME,
    identity_inventory,
    structure_fingerprint,
)
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync.definitions import (  # noqa: E402
    PublishOrderError,
    validate_instrumentation_payload,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    CandidateState,
    IdentityError,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 固定期望值（来自 Task 5 实证，两侧互锁）
# ═══════════════════════════════════════════════════════════════════════════

#: Task 5 findings.md §1 记录的权威源 digest。本文件跑完必须仍然是这两个值。
AUTHORITY_TEMPLATE_SHA: dict[str, str] = {
    "K/K11 资产减值损失.xlsx": (
        "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190"
    ),
    "C/C24 会计分录 - 细节测试.xlsx": (
        "b70229f48c13a635595b13f74aa199cb2d96ed1106a1661a66cecb7e6e87d5c6"
    ),
}

#: Task 5 契约 anchors 里 `probe_verdict != passed` 的两个（被证伪的锚点）。
DISPROVED_ANCHORS = ("sheet_id", "sheet_display_name")

K11_SPEC = EI.ExcelInstrumentationSpec(
    entry_id="k11.adjudication",
    template_id="K11",
    template_relative_path="K/K11 资产减值损失.xlsx",
    managed_sheet="审定表K11-1",
    first_data_row=7,
    last_data_row=25,
    footer_row=26,
    managed_last_col="L",
    uuid_col="N",
    table_name="GT_K11_1_ROWS",
)

C24_SPEC = EI.ExcelInstrumentationSpec(
    entry_id="c24.summary",
    template_id="C24",
    template_relative_path="C/C24 会计分录 - 细节测试.xlsx",
    managed_sheet="C24-0汇总表",
    first_data_row=8,
    last_data_row=20,
    footer_row=21,
    managed_last_col="H",
    uuid_col="N",
    table_name="GT_C24_0_ROWS",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 1. fixtures（真实权威模板一次性注入，避免每个用例重跑 C24 的 7.6s 等价比对）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def gate() -> EI.ExcelIdentityCarrierGate:
    return EI.ExcelIdentityCarrierGate.load()


@pytest.fixture(scope="module")
def contract_raw() -> dict[str, Any]:
    return json.loads(EI.GATE_CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline_raw() -> dict[str, Any]:
    return json.loads(EI.GATE_BASELINE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def instrumented(gate: EI.ExcelIdentityCarrierGate) -> dict[str, dict[str, Any]]:
    """两份真实模板各注入一次，连同等价报告与反读结果一起返回。

    采集内部**不吞异常**：任何一步抛就让整个 module fixture 失败 ⇒ 全部用例 ERROR，
    而 `test_no_collection_errors` 会显式断言 errors 为空（Task 15 复盘第 3 条：
    采集型守卫要 fail-closed 到「打红」而不是「静默无数据」）。
    """
    out: dict[str, dict[str, Any]] = {}
    for key, spec in (("k11", K11_SPEC), ("c24", C24_SPEC)):
        path = gate.assert_template_under_authority(spec.template_relative_path)
        source = path.read_bytes()
        inst = EI.instrument_workbook_bytes(source, spec, gate=gate)
        equivalence = EI.verify_visible_equivalence(
            source=source, instrumented=inst, spec=spec
        )
        inventory = EI.read_back_identity(instrumented=inst, spec=spec, gate=gate)
        out[key] = {
            "spec": spec,
            "path": path,
            "source": source,
            "source_sha": _sha(source),
            "workbook": inst,
            "equivalence": equivalence,
            "inventory": inventory,
            "before_fp": structure_fingerprint(source),
            "after_fp": structure_fingerprint(inst.instrumented_bytes),
        }
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. 载体裁决门（Requirement 6.16 / Property 66）
# ═══════════════════════════════════════════════════════════════════════════


class TestCarrierGateIsFailClosed:
    def test_allowed_sets_are_reverse_computed_from_probe_verdicts(
        self, gate: EI.ExcelIdentityCarrierGate, contract_raw: dict[str, Any]
    ) -> None:
        """allowed/forbidden 必须由逐条 `probe_verdict` 反算，且与 gate 清单一致。"""
        passed_carriers = {
            c["carrier"] for c in contract_raw["carriers"] if c["probe_verdict"] == "passed"
        }
        passed_anchors = {
            a["anchor"] for a in contract_raw["anchors"] if a["probe_verdict"] == "passed"
        }
        failed_anchors = {
            a["anchor"] for a in contract_raw["anchors"] if a["probe_verdict"] != "passed"
        }
        assert gate.allowed_carriers == passed_carriers
        assert gate.allowed_anchors == passed_anchors
        assert gate.forbidden_anchors == failed_anchors
        assert gate.forbidden_anchors == set(DISPROVED_ANCHORS), (
            "Task 5 已证伪 sheetId（OO 每次保存按 tab 顺序重编号）与 sheet 展示名两个锚点；"
            "这两个必须恒在 forbidden 里"
        )

    @pytest.mark.parametrize("anchor", DISPROVED_ANCHORS)
    def test_disproved_anchor_gets_its_own_exception_type(
        self, gate: EI.ExcelIdentityCarrierGate, anchor: str
    ) -> None:
        """被证伪的锚点必须抛 `ForbiddenAnchorError`，而不是通用的 `CarrierGateError`。

        分成两个类型是刻意的：短路掉 forbidden 分支后 allowed 分支会顶上来抛
        `CarrierGateError`，共用类型时变异检验判 GREEN（Task 12/13/14/15 连续踩过）。
        """
        with pytest.raises(EI.ForbiddenAnchorError):
            gate.assert_anchor_allowed(anchor)

    def test_unknown_anchor_is_rejected_but_not_as_disproved(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        with pytest.raises(EI.CarrierGateError) as exc:
            gate.assert_anchor_allowed("chinese_header_label")
        assert not isinstance(exc.value, EI.ForbiddenAnchorError)

    @pytest.mark.parametrize(
        "carrier", ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"]
    )
    def test_each_carrier_verdict_downgrade_is_independently_fail_closed(
        self, tmp_path: Path, carrier: str
    ) -> None:
        """把**某一个** carrier 的裁决从 passed 改成 partial ⇒ load 必须拒绝。

        逐 carrier 参数化而不是「改一个就算测过」：`_assert_gate_matches_verdicts` 的
        判据是集合相等，只改一个 carrier 时若 loader 读的是 gate 清单而不是逐条裁决，
        它会照旧放行 —— 每个合取项都要有只违反它自己的场景（Task 15 复盘第 2 条）。
        """
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(contract.read_text(encoding="utf-8"))
        for item in data["carriers"]:
            if item["carrier"] == carrier:
                item["probe_verdict"] = "partial"
        _rewrite(contract, data, baseline)
        with pytest.raises(EI.CarrierGateError) as exc:
            EI.ExcelIdentityCarrierGate.load(contract_path=contract, baseline_path=baseline)
        assert carrier in str(exc.value)

    @pytest.mark.parametrize(
        "carrier", ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"]
    )
    def test_a_consistently_retracted_carrier_blocks_the_engine_gate(
        self, tmp_path: Path, gate: EI.ExcelIdentityCarrierGate, carrier: str
    ) -> None:
        """载体裁决被**一致地**撤回（逐条 verdict 与 gate 清单同步改）⇒ 两个入口都必须拒绝。

        与上一条的分工是本条存在的全部理由：上一条只改逐条 `probe_verdict`，被
        `_assert_gate_matches_verdicts` 的集合相等判据拦在 `load()` 里，于是
        `assert_carrier_allowed` 那条门**永远走不到**；这一条模拟「Task 5 复跑后
        某载体被证伪、契约两侧都如实更新」，`load()` 合法通过、`allowed_carriers`
        真的少一个 —— 此时唯一能阻断 engine 建设的就是 `assert_carrier_allowed`
        （Property 66 的「任一缺失阻断 engine gate」）。

        没有这一条，把 `assert_carrier_allowed` 的 `raise` 删成 `pass` 不会有任何守卫
        变红（变异检验 M03/M04 实测过这个缺口）。注入与 payload 两条独立入口各自过门，
        因此只给其中一条加门也会被发现。
        """
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(contract.read_text(encoding="utf-8"))
        for item in data["carriers"]:
            if item["carrier"] == carrier:
                item["probe_verdict"] = "failed"
        node = data["gate_for_downstream_tasks"]["task_17_instrumentation_definition"]
        node["allowed_carriers"] = [c for c in node["allowed_carriers"] if c != carrier]
        _rewrite(contract, data, baseline)

        retracted = EI.ExcelIdentityCarrierGate.load(
            contract_path=contract, baseline_path=baseline
        )
        assert carrier not in retracted.allowed_carriers, (
            "前置不成立：撤回后的门里仍有该载体，本用例会在空集上恒真"
        )

        source = gate.assert_template_under_authority(
            K11_SPEC.template_relative_path
        ).read_bytes()
        with pytest.raises(EI.CarrierGateError) as inject_exc:
            EI.instrument_workbook_bytes(source, K11_SPEC, gate=retracted)
        assert carrier in str(inject_exc.value), (
            f"拒绝理由未点名 {carrier} —— 无法定位第一个不合格载体"
        )

        with pytest.raises(EI.CarrierGateError) as payload_exc:
            EI.build_instrumentation_payload(
                spec=K11_SPEC,
                template_definition_sha256=_digest("k11-template-definition"),
                template_sha256=AUTHORITY_TEMPLATE_SHA["K/K11 资产减值损失.xlsx"],
                gate=retracted,
            )
        assert carrier in str(payload_exc.value)

    @pytest.mark.parametrize("anchor", DISPROVED_ANCHORS)
    def test_promoting_a_disproved_anchor_to_passed_is_fail_closed(
        self, tmp_path: Path, anchor: str
    ) -> None:
        """把被证伪锚点的裁决手改成 passed ⇒ 与 gate 清单不一致即拒绝，且报出该锚点名。"""
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(contract.read_text(encoding="utf-8"))
        for item in data["anchors"]:
            if item["anchor"] == anchor:
                item["probe_verdict"] = "passed"
        _rewrite(contract, data, baseline)
        with pytest.raises(EI.CarrierGateError) as exc:
            EI.ExcelIdentityCarrierGate.load(contract_path=contract, baseline_path=baseline)
        assert anchor in str(exc.value), (
            "拒绝理由必须点名那个被偷偷提级的锚点，否则读者无法定位第一个不合格项"
        )

    def test_emptying_forbidden_anchors_is_fail_closed(self, tmp_path: Path) -> None:
        """两侧都被改成「没有禁用锚点」⇒ 仍必须拒绝（专属的空集判据）。

        这一条刻意把 `allowed_anchors` 也一起补齐，让集合相等的三条判据全部通过 ——
        于是唯一能拦住它的就是 `if not declared_forbidden` 那条空集判据。不补齐时
        `allowed_anchors` 不等会先抛，把空集判据永久遮蔽成不可达分支。
        """
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(contract.read_text(encoding="utf-8"))
        gate_node = data["gate_for_downstream_tasks"]["task_17_instrumentation_definition"]
        for item in data["anchors"]:
            item["probe_verdict"] = "passed"
        gate_node["allowed_anchors"] = [a["anchor"] for a in data["anchors"]]
        gate_node["forbidden_anchors"] = []
        _rewrite(contract, data, baseline)
        with pytest.raises(EI.CarrierGateError) as exc:
            EI.ExcelIdentityCarrierGate.load(contract_path=contract, baseline_path=baseline)
        assert "forbidden_anchors 为空" in str(exc.value)

    def test_missing_contract_is_stale_not_default(self, tmp_path: Path) -> None:
        with pytest.raises(EI.ProbeEvidenceStaleError):
            EI.ExcelIdentityCarrierGate.load(
                contract_path=tmp_path / "nope.json", baseline_path=EI.GATE_BASELINE_PATH
            )

    def test_required_hidden_sheet_keys_come_from_the_contract(
        self, gate: EI.ExcelIdentityCarrierGate, contract_raw: dict[str, Any]
    ) -> None:
        """`_GT_SYNC` 必备键的单一真源是契约，本模块的常量必须覆盖它。"""
        contract_keys = next(
            c for c in contract_raw["carriers"] if c["carrier"] == "hidden_sheet"
        )["required_keys"]
        assert gate.required_hidden_sheet_keys == tuple(contract_keys)
        assert set(contract_keys) <= set(EI.REQUIRED_GT_SYNC_KEYS), (
            "本模块写入的 `_GT_SYNC` 键集必须覆盖契约要求；漏一个键会让 Task 5 的"
            "required_keys_missing_anywhere=0 结论在生产 instrumentation 上不成立"
        )


class TestProbeEvidenceStaleness:
    """Property 71：环境 / runner / 实证任一变化，旧裁决自动 stale。"""

    def test_tier_a_baseline_matches_reality_today(
        self, baseline_raw: dict[str, Any]
    ) -> None:
        """基线里每一项 digest 必须与磁盘实测相等（否则本仓库当前就是 stale 状态）。"""
        for item in baseline_raw["tier_a_runtime"]["files"]:
            assert _sha((_REPO / item["path"]).read_bytes()) == item["sha256"], (
                f"{item['role']} 已漂移 —— 必须重跑 Task 5 探针并重新裁决，"
                "不得直接改基线数字"
            )
        for item in baseline_raw["tier_a_runtime"]["probed_templates"]:
            assert _sha((_REPO / item["path"]).read_bytes()) == item["sha256"]

    def test_tier_b_evidence_is_fresh(self, gate: EI.ExcelIdentityCarrierGate) -> None:
        observed = gate.assert_evidence_fresh()
        assert set(observed) == {"probe_script", "operation_matrix", "instrumentation_report"}

    def test_contract_byte_drift_makes_the_gate_stale(self, tmp_path: Path) -> None:
        """契约本体改一个字节（连语义都不变）⇒ Tier A 判 stale。"""
        contract, baseline = _copy_gate_inputs(tmp_path)
        raw = contract.read_bytes()
        contract.write_bytes(raw.replace(b'"schema_version": 1', b'"schema_version":  1', 1))
        assert _sha(contract.read_bytes()) != _sha(raw), "变异未落盘，用例无意义"
        with pytest.raises(EI.ProbeEvidenceStaleError) as exc:
            EI.ExcelIdentityCarrierGate.load(contract_path=contract, baseline_path=baseline)
        assert "carrier_contract" in str(exc.value)

    def test_probed_template_drift_makes_the_gate_stale(self, tmp_path: Path) -> None:
        """探针文档的权威源 digest 变了 ⇒ 载体裁决 stale（模板换了，实证不适用）。"""
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(baseline.read_text(encoding="utf-8"))
        data["tier_a_runtime"]["probed_templates"][0]["sha256"] = "0" * 63 + "1"
        baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(EI.ProbeEvidenceStaleError) as exc:
            EI.ExcelIdentityCarrierGate.load(contract_path=contract, baseline_path=baseline)
        assert "权威模板" in str(exc.value)

    def test_missing_evidence_file_is_stale_not_skipped(self, tmp_path: Path) -> None:
        """evidence 文件不在了 ⇒ 判 stale。**不得**降级成 skip。"""
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(baseline.read_text(encoding="utf-8"))
        data["tier_b_evidence"]["files"][1]["path"] = "evidence/gone-forever.json"
        baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        loaded = EI.ExcelIdentityCarrierGate.load(
            contract_path=contract, baseline_path=baseline
        )
        with pytest.raises(EI.ProbeEvidenceStaleError) as exc:
            loaded.assert_evidence_fresh(baseline_path=baseline)
        assert "不可复现即判 stale" in str(exc.value)

    def test_tier_b_digest_drift_makes_the_gate_stale(self, tmp_path: Path) -> None:
        """evidence 文件还在、内容变了 ⇒ 同样判 stale（与「缺文件」是两条独立分支）。

        上一条只走 `if not path.is_file()`；把 Tier B 的 digest 比对删成 `pass` 不会让它
        变红（变异检验 M10 实测的缺口）。Property 71 要求的是「evidence 任一变化即失效」，
        内容漂移必须有只违反它自己的场景。
        """
        contract, baseline = _copy_gate_inputs(tmp_path)
        data = json.loads(baseline.read_text(encoding="utf-8"))
        drifted = data["tier_b_evidence"]["files"][0]
        assert drifted["role"] == "probe_script", "基线首项已换位，用例需同步"
        drifted["sha256"] = "0" * 63 + "1"
        baseline.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        loaded = EI.ExcelIdentityCarrierGate.load(
            contract_path=contract, baseline_path=baseline
        )
        with pytest.raises(EI.ProbeEvidenceStaleError) as exc:
            loaded.assert_evidence_fresh(baseline_path=baseline)
        assert "probe_script" in str(exc.value)
        assert "自动 stale" in str(exc.value), (
            "拒绝文案必须说明「旧 test run/evidence 自动 stale」，"
            "否则读者会以为只是文件校验失败"
        )

    def test_stale_policy_inputs_all_map_to_gate_fields(
        self, baseline_raw: dict[str, Any], contract_raw: dict[str, Any]
    ) -> None:
        """契约声明的 4 项 invalidate_on 必须**逐项**在本任务的门里有落点。"""
        declared = contract_raw["gate_for_downstream_tasks"]["stale_policy"]["invalidate_on"]
        mapped = baseline_raw["maps_to_task5_stale_policy"]
        assert set(declared) == set(mapped), (
            "Task 5 的 stale_policy 与 Task 17 门的映射表不一致 —— 有一项失效条件没有落点"
        )
        enforced_roles = {i["role"] for i in baseline_raw["tier_a_runtime"]["files"]} | {
            i["role"] for i in baseline_raw["tier_b_evidence"]["files"]
        }
        assert {
            "carrier_contract",
            "fingerprint_module",
            "probe_script",
            "operation_matrix",
            "instrumentation_report",
        } <= enforced_roles


def _copy_gate_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """把契约与基线复制到 tmp（**绝不**改仓库里的真文件）。"""
    contract = tmp_path / "carrier_contract.json"
    baseline = tmp_path / "gate_baseline.json"
    shutil.copyfile(EI.GATE_CONTRACT_PATH, contract)
    shutil.copyfile(EI.GATE_BASELINE_PATH, baseline)
    return contract, baseline


def _rewrite(contract: Path, data: dict[str, Any], baseline: Path) -> None:
    """写回改过的契约，并把基线里的 carrier_contract digest 同步成新值。

    否则 Tier A stale 门会先抛 `ProbeEvidenceStaleError`，把「裁决判据」那条门
    永久遮蔽成不可达分支 —— 与 `assert_candidate_finalizable` 的顺序陷阱同源。
    """
    contract.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    b = json.loads(baseline.read_text(encoding="utf-8"))
    for item in b["tier_a_runtime"]["files"]:
        if item["role"] == "carrier_contract":
            item["sha256"] = _sha(contract.read_bytes())
    baseline.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 3. canonical payload（Requirement 6.14 / 9.1 / Property 28）
# ═══════════════════════════════════════════════════════════════════════════


class TestInstrumentationPayload:
    @pytest.fixture(scope="class")
    def payload(self, gate: EI.ExcelIdentityCarrierGate) -> dict[str, Any]:
        return EI.build_instrumentation_payload(
            spec=K11_SPEC,
            template_definition_sha256=_digest("k11-template-definition"),
            template_sha256=AUTHORITY_TEMPLATE_SHA["K/K11 资产减值损失.xlsx"],
            gate=gate,
        )

    def test_payload_passes_task12_validator(self, payload: dict[str, Any]) -> None:
        """Task 12 的校验器是单一真源，本模块**不重写**自引用/反向引用判据。"""
        validate_instrumentation_payload(payload)

    @pytest.mark.parametrize(
        "key",
        ["contract_definition_sha256", "definition_bundle_sha256", "bundle_sha256"],
    )
    def test_backward_reference_key_is_rejected(
        self, payload: dict[str, Any], key: str
    ) -> None:
        """往 payload 塞任一反向引用键 ⇒ 校验器必须拒绝（证明它真的接上了）。"""
        polluted = dict(payload)
        polluted[key] = _digest("forged-child")
        with pytest.raises(PublishOrderError):
            validate_instrumentation_payload(polluted)

    @pytest.mark.parametrize("key", ["sha256", "id", "definition_artifact_id"])
    def test_self_reference_key_is_rejected(
        self, payload: dict[str, Any], key: str
    ) -> None:
        polluted = dict(payload)
        polluted[key] = _digest("self")
        with pytest.raises(IdentityError):
            validate_instrumentation_payload(polluted)

    def test_nested_self_reference_is_also_rejected(self, payload: dict[str, Any]) -> None:
        """自引用检测必须递归 —— 只查顶层时把它藏进子对象即可绕过。"""
        polluted = json.loads(json.dumps(payload))
        polluted["managed_sheets"][0]["artifact_id"] = str(uuid.uuid4())
        with pytest.raises(IdentityError):
            validate_instrumentation_payload(polluted)

    def test_no_locator_uses_a_disproved_anchor(
        self, payload: dict[str, Any], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """逐 locator 检查 anchor 值，同时确认黑名单字段本身**保留**着两个禁用锚点。

        这两条必须同时成立，才说明判据是结构式的：payload 的 `forbidden_anchors`
        字段就写着 `sheet_id` / `sheet_display_name`（要传给下游 loader），
        全文 grep 式判据会把它误判成违规。
        """
        anchors = sorted(set(EI._iter_anchor_declarations(payload)))
        assert anchors, "payload 一个 locator anchor 都没声明"
        assert not (set(anchors) & gate.forbidden_anchors)
        assert set(payload["forbidden_anchors"]) == gate.forbidden_anchors

    def test_payload_carries_no_sheet_id_or_display_name_as_identity(
        self, payload: dict[str, Any]
    ) -> None:
        """identity 区域里不得出现 OOXML sheetId 或 sheet 展示名。

        判据落在「identity 相关子树」而不是全 payload：`cell_geometry` 明确标了
        `anchor_role: none`，它记的是注入时刻几何，不是 identity。
        """
        identity_subtree = {
            "managed_sheets": payload["managed_sheets"],
            "defined_names": payload["defined_names"],
            "identity_anchors": payload["identity_anchors"],
        }
        blob = json.dumps(identity_subtree, ensure_ascii=False)
        assert K11_SPEC.managed_sheet not in blob, (
            "identity 子树里出现了 sheet 展示名 —— Requirement 6.14 禁止 identity "
            "依赖展示名（用户可改名，Task 5 实测改名后按名定位直接失败）"
        )
        assert "sheet_id" not in json.dumps(
            identity_subtree["managed_sheets"], ensure_ascii=False
        )
        assert payload["managed_sheets"][0]["locator"] == {
            "anchor": "defined_name_ref",
            "defined_name": "GT_MANAGED_REGION_K11",
        }

    def test_payload_declares_runtime_binding_as_finalize_only(
        self, payload: dict[str, Any]
    ) -> None:
        meta = payload["hidden_metadata_sheet"]
        assert meta["runtime_binding_keys_written_at_finalize_only"] == list(
            EI.RUNTIME_BINDING_KEYS
        )
        assert len(EI.RUNTIME_BINDING_KEYS) == 5, (
            "design 要求 finalize 时写入 authority-model/template/instrumentation/"
            "contract/bundle 五个 digest"
        )

    def test_requesting_a_disproved_anchor_is_rejected(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        with pytest.raises(EI.ForbiddenAnchorError):
            EI.build_instrumentation_payload(
                spec=K11_SPEC,
                template_definition_sha256=_digest("t"),
                template_sha256=_digest("s"),
                gate=gate,
                identity_anchors=("sheet_id",),
            )

    def test_row_uuid_disposition_matches_contract_classification(
        self, payload: dict[str, Any], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """Requirement 6.15 的三类处置必须与 Task 5 契约的 contract_action 一致。"""
        classification = gate.row_uuid_classification
        assert classification, "契约缺 requirement_6_15_classification"
        mapping = {
            "empty_uuid_on_new_row": "分配新 ID",
            "duplicate_uuid_from_copy": "结构冲突",
            "user_deleted_identity_column": "拒绝",
        }
        disposition = payload["row_uuid_disposition"]
        translated = {
            "allocate_new_id": "分配新 ID",
            "structural_conflict": "结构冲突",
            "reject": "拒绝",
        }
        for form, chinese in mapping.items():
            assert classification[form]["contract_action"].startswith(chinese)
            assert translated[disposition[form]] == chinese
        assert disposition["reuse_of_deleted_uuid"] == "forbidden"

    def test_template_payload_pins_the_authority_root(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        tpl = EI.build_template_payload(
            spec=K11_SPEC,
            template_sha256=AUTHORITY_TEMPLATE_SHA["K/K11 资产减值损失.xlsx"],
            structure_hash=_digest("structure"),
        )
        assert tpl["authority_root"] == "backend/wp_templates"
        assert tpl["template_relative_path"] == (
            "backend/wp_templates/K/K11 资产减值损失.xlsx"
        )

    def test_template_outside_authority_root_is_rejected(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """参考副本路径（`基础数据/…`）与任何 `..` 逃逸都必须被拒。"""
        for rel in (
            "../../基础数据/致同通用审计程序及底稿模板（2025年修订）/K11.xlsx",
            "../data/report_config.json",
        ):
            with pytest.raises(EI.InstrumentationError):
                gate.assert_template_under_authority(rel)


class TestSpecValidation:
    """声明式清单的形态门（Requirement 6.13：不得改变业务公式/标签）。"""

    def test_uuid_column_must_be_right_of_managed_columns(self) -> None:
        with pytest.raises(EI.InstrumentationError) as exc:
            EI.ExcelInstrumentationSpec(
                entry_id="x", template_id="X", template_relative_path="K/K11 资产减值损失.xlsx",
                managed_sheet="s", first_data_row=7, last_data_row=25, footer_row=26,
                managed_last_col="L", uuid_col="H", table_name="GT_X",
            )
        assert "右侧" in str(exc.value)

    def test_footer_must_be_below_the_managed_rows(self) -> None:
        with pytest.raises(EI.InstrumentationError) as exc:
            EI.ExcelInstrumentationSpec(
                entry_id="x", template_id="X", template_relative_path="K/K11 资产减值损失.xlsx",
                managed_sheet="s", first_data_row=7, last_data_row=25, footer_row=25,
                managed_last_col="L", uuid_col="N", table_name="GT_X",
            )
        assert "footer_row" in str(exc.value)

    def test_table_display_name_must_be_ooxml_legal(self) -> None:
        with pytest.raises(EI.InstrumentationError):
            EI.ExcelInstrumentationSpec(
                entry_id="x", template_id="X", template_relative_path="K/K11 资产减值损失.xlsx",
                managed_sheet="s", first_data_row=7, last_data_row=25, footer_row=26,
                managed_last_col="L", uuid_col="N", table_name="GT X ROWS",
            )

    def test_there_is_no_switch_to_skip_the_excel_table(self) -> None:
        """Table 是生产必需项：spec 上不得存在「不注 Table」的开关。

        Task 5 契约写明 C24 未注 Table ⇒ sheet 改名后没有任何可用锚点。若这里出现
        `inject_table` 之类的字段，就会有人为省事把它关掉，改名后 identity 直接失联。
        """
        fields = set(EI.ExcelInstrumentationSpec.__dataclass_fields__)
        assert not {f for f in fields if "inject" in f or "skip" in f}
        assert "table_name" in fields


# ═══════════════════════════════════════════════════════════════════════════
# 4. 真实注入 + 可见等价（Requirement 6.13 / 6.17）
# ═══════════════════════════════════════════════════════════════════════════


class TestVisibleEquivalenceOnRealTemplates:
    def test_no_collection_errors(self, instrumented: dict[str, dict[str, Any]]) -> None:
        """采集自身零错误 —— 没有这条，「等价」可能只是因为两侧都采空了。"""
        for key, doc in instrumented.items():
            assert doc["before_fp"].errors == [], f"{key} 注入前采集报错"
            assert doc["after_fp"].errors == [], f"{key} 注入后采集报错"
            assert doc["inventory"]["errors"] == []

    @pytest.mark.parametrize("key", ["k11", "c24"])
    def test_all_six_aspects_are_equivalent(
        self, instrumented: dict[str, dict[str, Any]], key: str
    ) -> None:
        report = instrumented[key]["equivalence"]
        assert report["aspect_verdicts"] == {
            "visible_sheets": True,
            "business_values": True,
            "formulas": True,
            "styles": True,
            "merges": True,
            "protected_parts": True,
        }
        assert report["equivalent"] is True

    def test_the_aspects_are_not_vacuously_equal(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """K11 必须真的有公式/merge/受保护部件可比 —— 否则六个 True 是空集相等。"""
        fp = instrumented["k11"]["before_fp"]
        formula_count = sum(len(v) for v in fp.formulas.values())
        merge_count = sum(len(v) for v in fp.merges.values())
        assert formula_count >= 300, f"K11 公式数 {formula_count} 偏少，判据可能失真"
        assert merge_count >= 40, f"K11 merge 数 {merge_count} 偏少"
        assert len(fp.business_sheet_names()) >= 6

    def test_chart_bearing_template_keeps_protected_parts_byte_identical(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """C24 的 8 chart / 3 drawing / 1 media 必须逐部件字节未变。

        这一格只有 C24 能回答（全平台 351 个模板里唯一含 `xl/charts/` 者），
        它证明 zip 级定点注入不会破坏 chart —— 也就是为什么 design 禁止对含 chart 的
        文件做 openpyxl 全量重写。
        """
        before = instrumented["c24"]["before_fp"]
        after = instrumented["c24"]["after_fp"]
        assert {k: len(v) for k, v in before.protected_parts.items()} == {
            "chart": 8, "drawing": 3, "media": 1
        }
        assert before.protected_parts == after.protected_parts
        for parts in before.protected_parts.values():
            for part in parts:
                assert before.part_digests[part] == after.part_digests[part], part

    @pytest.mark.parametrize("key", ["k11", "c24"])
    def test_only_the_whitelisted_four_additions_appear(
        self, instrumented: dict[str, dict[str, Any]], key: str
    ) -> None:
        """白名单只有四样：隐藏 sheet / GT_ defined names / 一列隐藏 UUID / Table 部件。"""
        doc = instrumented[key]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        before, after = doc["before_fp"], doc["after_fp"]
        assert doc["equivalence"]["hidden_sheets_added"] == [GT_SYNC_SHEET_NAME]
        assert before.visible_sheet_names == after.visible_sheet_names
        added_names = {d["name"] for d in after.defined_names} - {
            d["name"] for d in before.defined_names
        }
        assert added_names == {n for n, _, _ in spec.defined_names()}
        assert all(n.startswith("GT_") for n in added_names)
        added_cols = set(after.hidden_columns.get(spec.managed_sheet, [])) - set(
            before.hidden_columns.get(spec.managed_sheet, [])
        )
        assert added_cols == {spec.uuid_col}
        added_tables = {t["display_name"] for t in after.tables} - {
            t["display_name"] for t in before.tables
        }
        assert added_tables == {spec.table_name}

    def test_metadata_sheet_is_hidden_and_out_of_business_enumeration(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        for doc in instrumented.values():
            after = doc["after_fp"]
            assert GT_SYNC_SHEET_NAME in after.hidden_sheet_names
            assert GT_SYNC_SHEET_NAME not in after.visible_sheet_names
            assert GT_SYNC_SHEET_NAME not in after.business_sheet_names()

    def test_authority_templates_are_untouched(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """跑完全部注入后，`backend/wp_templates/` 两份模板 sha256 必须仍是原值。

        Requirement 9.9：instrumentation 只能经声明式清单增加，不得在运行时写回模板库。
        期望值取自 Task 5 findings.md 记录的实证 digest ⇒ 两侧互锁。
        """
        for rel, expected in AUTHORITY_TEMPLATE_SHA.items():
            path = EI.TEMPLATE_AUTHORITY_ROOT / rel
            assert _sha(path.read_bytes()) == expected, f"{rel} 被改动了"
        for doc in instrumented.values():
            assert _sha(doc["path"].read_bytes()) == doc["source_sha"]

    def test_reinstrumenting_an_instrumented_artifact_is_rejected(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """已 instrumented 的 artifact 再注入一次 ⇒ 拒绝（否则会有两套 identity）。"""
        doc = instrumented["k11"]
        with pytest.raises(EI.InstrumentationError) as exc:
            EI.instrument_workbook_bytes(
                doc["workbook"].instrumented_bytes, doc["spec"], gate=gate
            )
        assert "已含 instrumentation 部件" in str(exc.value)

    def test_managed_row_range_outside_the_sheet_fails_closed(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """声明的受管行区间超出模板实际结构 ⇒ fail closed（Requirement 6.10）。"""
        drifted = EI.ExcelInstrumentationSpec(
            entry_id="k11.adjudication", template_id="K11",
            template_relative_path="K/K11 资产减值损失.xlsx",
            managed_sheet="审定表K11-1",
            first_data_row=7, last_data_row=9000, footer_row=9001,
            managed_last_col="L", uuid_col="N", table_name="GT_K11_1_ROWS",
        )
        source = (EI.TEMPLATE_AUTHORITY_ROOT / "K/K11 资产减值损失.xlsx").read_bytes()
        with pytest.raises(EI.InstrumentationError) as exc:
            EI.instrument_workbook_bytes(source, drifted, gate=gate)
        assert "找不到第" in str(exc.value)

    def test_equivalence_is_falsifiable(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """负对照：真的改掉一个可见业务单元格 ⇒ 等价判定必须失败。

        没有这条，「六个 aspect 全 True」可能只是判据恒真。
        """
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        tampered = _mutate_visible_cell(
            doc["workbook"].instrumented_bytes, sheet_part_hint="审定表K11-1"
        )
        fake = EI.InstrumentedWorkbook(
            source_sha256=doc["workbook"].source_sha256,
            instrumented_bytes=tampered,
            instrumented_sha256=_sha(tampered),
            managed_sheet_name_at_instrumentation=spec.managed_sheet,
            managed_sheet_id_at_instrumentation="1",
            row_uuids=doc["workbook"].row_uuids,
            gt_sync_pairs=doc["workbook"].gt_sync_pairs,
            defined_name_refs=doc["workbook"].defined_name_refs,
            table_ref=doc["workbook"].table_ref,
        )
        with pytest.raises(EI.VisibleEquivalenceError):
            EI.verify_visible_equivalence(source=doc["source"], instrumented=fake, spec=spec)


# ═══════════════════════════════════════════════════════════════════════════
# 5. identity 反读与 Requirement 6.15 三形态
# ═══════════════════════════════════════════════════════════════════════════


class TestIdentityReadback:
    @pytest.mark.parametrize("key", ["k11", "c24"])
    def test_sheet_resolution_only_uses_the_probed_anchor(
        self, instrumented: dict[str, dict[str, Any]], key: str
    ) -> None:
        """反读的 sheet 解析候选**只有** `table_sheet` 一项。

        这是「不用被证伪锚点」的结构判据：生产反读不传 `uuid_sheet_id` /
        `uuid_sheet_name`，于是那两条路径在 `sheet_resolution_candidates` 里
        根本不存在 —— 而不是「存在但我们没用」。
        """
        col = instrumented[key]["inventory"]["hidden_uuid_column"]
        assert set(col["sheet_resolution_candidates"]) == {"table_sheet"}
        assert col["resolved_sheet_by"] == "table_sheet"
        assert col["requested_sheet_id"] is None
        assert col["requested_sheet_name"] is None

    @pytest.mark.parametrize("key", ["k11", "c24"])
    def test_row_uuids_are_pregenerated_literals(
        self, instrumented: dict[str, dict[str, Any]], key: str
    ) -> None:
        doc = instrumented[key]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        col = doc["inventory"]["hidden_uuid_column"]
        assert col["row_uuid_count"] == spec.row_count
        assert col["distinct_row_uuid_count"] == spec.row_count
        assert col["duplicate_row_uuids"] == []
        assert col["empty_row_uuids"] == []
        assert col["uuid_column_hidden"] is True
        assert all(
            v == spec.row_uuid(int(r)) for r, v in col["row_uuids"].items()
        )
        # 字面量而非公式：受管 sheet 的 UUID 列不得出现在 formulas 投影里
        formulas = doc["after_fp"].formulas.get(spec.managed_sheet, {})
        assert not [c for c in formulas if re.match(rf"^{spec.uuid_col}\d+$", c)]

    def test_table_header_row_count_is_zero(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        for doc in instrumented.values():
            table = doc["inventory"]["excel_table"]
            assert table["present"] is True
            assert table["header_row_count_zero"] is True
            assert table["table_ref"] == doc["spec"].table_ref

    def test_gt_sync_has_no_runtime_binding_key(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """instrumentation 阶段 `_GT_SYNC` 一个 runtime binding 键都不许有。"""
        for doc in instrumented.values():
            pairs = doc["inventory"]["hidden_sheet"]["pairs"]
            assert not (set(pairs) & set(EI.RUNTIME_BINDING_KEYS))
            EI.assert_no_runtime_binding(pairs)

    @pytest.mark.parametrize("key", list(EI.RUNTIME_BINDING_KEYS))
    def test_each_runtime_binding_key_is_independently_rejected(self, key: str) -> None:
        """逐键参数化：五个键各自都能被拦下（避免只拦第一个就算过）。"""
        with pytest.raises(EI.RuntimeBindingForbiddenError) as exc:
            EI.assert_no_runtime_binding({"GT_TEMPLATE_ID": "K11", key: _digest("x")})
        assert key in str(exc.value)

    def test_readback_rejects_dangling_table_part(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """Table 部件被剥掉但 `<tableParts>` 引用仍在 ⇒ 采集层失败必须**上报**。

        这条锁的是「采集失败绝不降级成『无 identity』」：`identity_inventory()` 抛
        `FingerprintError` 时必须被翻成 `IdentityReadbackError`，而不是当成
        「Table 不存在」继续往下走。
        """
        doc = instrumented["k11"]
        stripped = _drop_zip_entry(
            doc["workbook"].instrumented_bytes, "xl/tables/tableGtRowId.xml"
        )
        fake = _clone_workbook(doc["workbook"], stripped)
        with pytest.raises(EI.IdentityReadbackError) as exc:
            EI.read_back_identity(instrumented=fake, spec=doc["spec"], gate=gate)
        assert "反读采集失败" in str(exc.value)
        assert "tableGtRowId.xml" in str(exc.value), "必须指出首个失效部件"

    def test_readback_rejects_missing_table(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """Table 载体整体消失（部件 + `<tableParts>` 引用都没了）⇒ 反读 fail closed。

        这是 sheet 改名后唯一可用区域边界锚点消失的形态：workbook 结构完全合法，
        采集不报错，只是 `excel_table.present is False` —— 必须由**语义判据**拒绝，
        而不是靠采集层崩掉顺带拦下（后者由上一条用例覆盖）。
        """
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        without_part = _drop_zip_entry(
            doc["workbook"].instrumented_bytes, "xl/tables/tableGtRowId.xml"
        )
        sheet_part = _managed_sheet_part(without_part, spec.managed_sheet)
        without_ref = _edit_zip_entry(
            without_part,
            sheet_part,
            lambda xml: re.sub(r"<tableParts[^>]*>.*?</tableParts>", "", xml),
        )
        fake = _clone_workbook(doc["workbook"], without_ref)
        with pytest.raises(EI.IdentityReadbackError) as exc:
            EI.read_back_identity(instrumented=fake, spec=spec, gate=gate)
        assert "反读不到" in str(exc.value)

    def test_readback_rejects_missing_defined_names(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        doc = instrumented["k11"]
        broken = _edit_zip_entry(
            doc["workbook"].instrumented_bytes,
            "xl/workbook.xml",
            lambda xml: re.sub(r"<definedName name=\"GT_FOOTER_ANCHOR_K11\">.*?</definedName>", "", xml),
        )
        fake = _clone_workbook(doc["workbook"], broken)
        with pytest.raises(EI.IdentityReadbackError) as exc:
            EI.read_back_identity(instrumented=fake, spec=doc["spec"], gate=gate)
        assert "defined name 反读不符" in str(exc.value)


class TestRequirement615Dispositions:
    """OO 内三种异常形态必须**可判定**且各自有专属判据。"""

    def test_new_row_without_uuid_is_detectable(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """Table ref 覆盖行数 − 非空 UUID 数 > 0 ⇒ 「分配新 ID」。"""
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        # 模拟 OO 插行：Table ref 扩一行，但新行没有 UUID
        widened = _edit_zip_entry(
            doc["workbook"].instrumented_bytes,
            "xl/tables/tableGtRowId.xml",
            lambda xml: xml.replace(
                f'ref="{spec.table_ref}"',
                f'ref="A{spec.first_data_row}:{spec.uuid_col}{spec.last_data_row + 1}"',
            ),
        )
        inv = identity_inventory(
            widened, expected_table=spec.table_name, uuid_column_letter=spec.uuid_col
        )
        ref = inv["excel_table"]["table_ref"]
        covered = int(ref.split(":")[1][len(spec.uuid_col):]) - spec.first_data_row + 1
        present = inv["hidden_uuid_column"]["row_uuid_count"]
        assert covered - present == 1, "插行判据失效：ref 行数减 UUID 数应恰为 1"

    def test_duplicate_uuid_from_copy_is_detectable(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """同列出现重复 UUID ⇒ 「结构冲突」。"""
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        first, second = spec.row_uuid(spec.first_data_row), spec.row_uuid(spec.first_data_row + 1)
        pasted = _edit_zip_entry(
            doc["workbook"].instrumented_bytes,
            _managed_sheet_part(doc["workbook"].instrumented_bytes, spec.managed_sheet),
            lambda xml: xml.replace(f"<t>{second}</t>", f"<t>{first}</t>", 1),
        )
        inv = identity_inventory(
            pasted, expected_table=spec.table_name, uuid_column_letter=spec.uuid_col
        )
        col = inv["hidden_uuid_column"]
        assert col["duplicate_row_uuids"] == [first]
        assert col["distinct_row_uuid_count"] == col["row_uuid_count"] - 1

    def test_deleted_identity_column_is_detectable_and_fails_closed(
        self, instrumented: dict[str, dict[str, Any]], gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """整列 identity 被删 ⇒ `row_uuid_count == 0` 且 Table ref 仍覆盖数据行 ⇒ 「拒绝」。"""
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        part = _managed_sheet_part(doc["workbook"].instrumented_bytes, spec.managed_sheet)
        wiped = _edit_zip_entry(
            doc["workbook"].instrumented_bytes,
            part,
            lambda xml: re.sub(
                rf'<c r="{spec.uuid_col}\d+" t="inlineStr"><is><t>[^<]*</t></is></c>', "", xml
            ),
        )
        inv = identity_inventory(
            wiped, expected_table=spec.table_name, uuid_column_letter=spec.uuid_col
        )
        assert inv["hidden_uuid_column"]["row_uuid_count"] == 0
        assert inv["excel_table"]["table_ref"] == spec.table_ref
        fake = _clone_workbook(doc["workbook"], wiped)
        with pytest.raises(EI.IdentityReadbackError):
            EI.read_back_identity(instrumented=fake, spec=spec, gate=gate)

    def test_deleted_row_uuid_is_never_reused(
        self, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """删行后该 UUID 不得出现在任何其他行（预生成字面量的必然结果）。"""
        doc = instrumented["k11"]
        spec: EI.ExcelInstrumentationSpec = doc["spec"]
        victim = spec.row_uuid(spec.first_data_row + 5)
        part = _managed_sheet_part(doc["workbook"].instrumented_bytes, spec.managed_sheet)
        removed = _edit_zip_entry(
            doc["workbook"].instrumented_bytes,
            part,
            lambda xml: xml.replace(
                f'<c r="{spec.uuid_col}{spec.first_data_row + 5}" t="inlineStr">'
                f"<is><t>{victim}</t></is></c>",
                "",
                1,
            ),
        )
        inv = identity_inventory(
            removed, expected_table=spec.table_name, uuid_column_letter=spec.uuid_col
        )
        values = set(inv["hidden_uuid_column"]["row_uuids"].values())
        assert victim not in values
        assert len(values) == spec.row_count - 1


# ═══════════════════════════════════════════════════════════════════════════
# 6. 业务 sheet 排除：调用**生产函数本体**（Requirement 6.17 后半句）
# ═══════════════════════════════════════════════════════════════════════════


class TestBusinessSheetExclusion:
    @pytest.fixture(scope="class")
    def instrumented_file(
        self, instrumented: dict[str, dict[str, Any]], tmp_path_factory: Any
    ) -> Path:
        target = tmp_path_factory.mktemp("task17-exclusion") / "instrumented.xlsx"
        target.write_bytes(instrumented["k11"]["workbook"].instrumented_bytes)
        return target

    def test_production_sheet_enumerator_excludes_metadata_sheet(
        self, instrumented_file: Path, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """`xlsx_read_adapter.list_sheet_names` —— 六处业务枚举的共同入口。"""
        from app.services.xlsx_read_adapter import list_sheet_names

        names = list_sheet_names(instrumented_file)
        assert GT_SYNC_SHEET_NAME not in names
        # 业务 sheet 一张不少、顺序不变
        assert names == instrumented["k11"]["before_fp"].sheet_names

    def test_univer_snapshot_excludes_metadata_sheet(
        self, instrumented_file: Path, instrumented: dict[str, dict[str, Any]]
    ) -> None:
        """编辑器快照也不得出现 `_GT_SYNC`（否则标签栏多一张无法解释的表）。"""
        from app.services.xlsx_to_univer import xlsx_to_univer_data

        data = xlsx_to_univer_data(str(instrumented_file))
        rendered = [s["name"] for s in data["sheets"].values()]
        assert GT_SYNC_SHEET_NAME not in rendered
        assert rendered == instrumented["k11"]["before_fp"].sheet_names
        assert len(data["sheetOrder"]) == len(rendered), "过滤后 sheet 编号必须连续"

    def test_offline_import_meta_sheet_is_not_swept_up(self) -> None:
        """负对照：离线导入自有的 `_meta_` **不得**被本策略排除。

        `wp_offline_import_service` / `note_offline_import_service` 都以
        「枚举不到 `_meta_` 就拒绝导入」为前置，把它加进排除名单会让离线导入全线失效。
        """
        assert "_meta_" not in PLATFORM_METADATA_SHEETS
        assert exclude_metadata_sheets(["_meta_", "审定表", GT_SYNC_SHEET_NAME]) == [
            "_meta_",
            "审定表",
        ]

    def test_policy_reuses_the_single_source_sheet_name(self) -> None:
        """排除名单必须复用 Task 5 模块里的常量，不得自己抄一份字面量。"""
        assert PLATFORM_METADATA_SHEETS == frozenset({GT_SYNC_SHEET_NAME})

    def test_exclusion_preserves_order(self) -> None:
        """过滤必须保持原顺序。

        🔴 输入刻意是**逆序**的：`["c","b","a"]` 过滤后仍须是 `["c","b","a"]`。
        原来的用例传 `["a", _GT_SYNC, "b", "c"]`，过滤结果 `["a","b","c"]` 恰好已是
        排序态 ⇒ 把 `return [...]` 改成 `sorted(...)` 它照旧全绿（变异 M29 实测 WRONG-TEST：
        真正打红的是两条走真实模板的用例，而本用例这条专职判据空转）。
        顺序判据的输入必须与排序结果不同，否则判据不可 falsify。

        顺序为什么重要：多处业务代码按「第一个 sheet」取默认表
        （`xlsx_read_adapter.read_sheet_values(sheet_name=None)`），重排会静默换表。
        """
        assert exclude_metadata_sheets(["c", GT_SYNC_SHEET_NAME, "b", "a"]) == [
            "c",
            "b",
            "a",
        ]
        # 中文 sheet 名同样不得被重排（真实底稿全是中文表名）
        assert exclude_metadata_sheets(
            ["审定表K11-1", GT_SYNC_SHEET_NAME, "明细表", "封面"]
        ) == ["审定表K11-1", "明细表", "封面"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. candidate-only 门面（Requirement 6.18 / 9.10 / Property 67）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeRepo:
    """最小仓储替身：只用来证明「哪些方法可达、哪些不可达」。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.session = object()

    def _record(self, name: str) -> str:
        self.calls.append(name)
        return name

    def create_representation(self, **_: Any) -> str:
        return self._record("create_representation")

    def set_entry_pointer(self, **_: Any) -> str:
        return self._record("set_entry_pointer")

    def finalize_candidate(self, **_: Any) -> str:
        return self._record("finalize_candidate")

    def bump_content_revision(self, **_: Any) -> str:
        return self._record("bump_content_revision")

    def set_current_content_version(self, **_: Any) -> str:
        return self._record("set_current_content_version")

    def create_content_version(self, **_: Any) -> str:
        return self._record("create_content_version")

    def create_upgrade_candidate(self, **_: Any) -> str:
        return self._record("create_upgrade_candidate")

    def register_artifact(self, **_: Any) -> str:
        return self._record("register_artifact")


class TestCandidateOnlyRepository:
    def test_forbidden_set_covers_representation_pointer_finalize_and_revision(
        self,
    ) -> None:
        """禁令集必须是「本任务三件套 ∪ Task 15 的 revision 域」，且是 import 取并集。"""
        from app.services.workpaper_sync.content_mutation import (
            REVISION_DOMAIN_WRITE_METHODS,
        )

        assert {
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
        } <= EI.CANDIDATE_FORBIDDEN_METHODS
        assert set(REVISION_DOMAIN_WRITE_METHODS) <= EI.CANDIDATE_FORBIDDEN_METHODS, (
            "revision 域禁令必须从 Task 15 import 取并集 —— 手抄会在那边新增 writer 时漏掉"
        )
        assert len(EI.CANDIDATE_FORBIDDEN_METHODS) == 3 + len(REVISION_DOMAIN_WRITE_METHODS)

    @pytest.mark.parametrize(
        "method",
        [
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
            "bump_content_revision",
            "set_current_content_version",
            "create_content_version",
        ],
    )
    def test_each_forbidden_method_is_unreachable(self, method: str) -> None:
        inner = _FakeRepo()
        facade = EI.CandidateOnlyRepository(inner)
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            getattr(facade, method)
        assert method in str(exc.value)
        assert inner.calls == [], "禁令方法不得被真正调用"

    def test_allowed_methods_pass_through(self) -> None:
        inner = _FakeRepo()
        facade = EI.CandidateOnlyRepository(inner)
        assert facade.create_upgrade_candidate() == "create_upgrade_candidate"
        assert facade.register_artifact() == "register_artifact"
        assert inner.calls == ["create_upgrade_candidate", "register_artifact"]
        assert facade.session is inner.session
        assert facade.inner is inner

    def test_upgrader_wraps_a_bare_repository_unconditionally(
        self, gate: EI.ExcelIdentityCarrierGate
    ) -> None:
        """即便调用方传裸 repository，编排器也拿不到那四类写入面。"""
        inner = _FakeRepo()
        upgrader = EI.ExcelInstrumentationUpgrader(
            session=object(),
            repository=inner,
            artifacts=object(),
            project_id=uuid.uuid4(),
            source_commit="deadbeef",
            gate=gate,
        )
        assert isinstance(upgrader.repository, EI.CandidateOnlyRepository)
        with pytest.raises(EI.CandidateSurfaceForbiddenError):
            upgrader.repository.create_representation

    def test_double_wrapping_is_idempotent(self, gate: EI.ExcelIdentityCarrierGate) -> None:
        facade = EI.CandidateOnlyRepository(_FakeRepo())
        upgrader = EI.ExcelInstrumentationUpgrader(
            session=object(), repository=facade, artifacts=object(),
            project_id=uuid.uuid4(), source_commit="deadbeef", gate=gate,
        )
        assert upgrader.repository is facade


class TestCandidateNonCurrencyAssertions:
    """`assert_candidate_is_non_current` 的每个合取项都要有只违反它自己的场景。"""

    @staticmethod
    def _outcome(**overrides: Any) -> EI.UpgradeCandidateOutcome:
        base: dict[str, Any] = {
            "candidate_id": uuid.uuid4(),
            "wp_id": uuid.uuid4(),
            "entry_id": "k11.adjudication",
            "content_version_id": uuid.uuid4(),
            "source_representation_id": uuid.uuid4(),
            "from_definition_bundle_id": None,
            "from_definition_bundle_sha256": None,
            "template_definition_id": uuid.uuid4(),
            "template_definition_sha256": _digest("t"),
            "instrumentation_definition_id": uuid.uuid4(),
            "instrumentation_definition_sha256": _digest("i"),
            "target_contract_definition_id": None,
            "target_definition_bundle_id": None,
            "state": CandidateState.awaiting_contract,
            "staged_artifact_id": uuid.uuid4(),
            "staged_artifact_sha256": _digest("a"),
            "staged_relative_path": ".upgrade-candidates/x/y/artifact.candidate.ooxml",
            "rollback_source_sha256": _digest("r"),
            "visible_equivalence_report_sha256": _digest("e"),
            "identity_inventory_sha256": _digest("v"),
            "structure_hash": _digest("s"),
            "content_revision_before": 11,
            "content_revision_after": 11,
            "entry_pointer_before": None,
            "entry_pointer_after": None,
            "representation_count_before": 2,
            "representation_count_after": 2,
            "probe_gate": {"onlyoffice_build": "9.4.0-129"},
            "actor_id": None,
        }
        base.update(overrides)
        return EI.UpgradeCandidateOutcome(**base)

    def test_clean_outcome_passes(self) -> None:
        outcome = self._outcome()
        EI.assert_candidate_is_non_current(outcome)
        assert outcome.revision_unchanged
        assert outcome.pointer_unchanged
        assert outcome.no_representation_created

    def test_revision_advance_only(self) -> None:
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(self._outcome(content_revision_after=12))
        assert "content revision" in str(exc.value)

    def test_pointer_move_only(self) -> None:
        moved = uuid.uuid4()
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(self._outcome(entry_pointer_after=moved))
        assert "entry pointer" in str(exc.value)

    def test_representation_created_only(self) -> None:
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(
                self._outcome(representation_count_after=3)
            )
        assert "representation" in str(exc.value)

    @pytest.mark.parametrize(
        "state", [CandidateState.ready, CandidateState.finalized, CandidateState.rejected]
    )
    def test_forbidden_state_only(self, state: CandidateState) -> None:
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(self._outcome(state=state))
        assert state.value in str(exc.value)

    def test_forged_contract_target_only(self) -> None:
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(
                self._outcome(target_contract_definition_id=uuid.uuid4())
            )
        assert "per-entry contract" in str(exc.value)

    def test_forged_bundle_target_only(self) -> None:
        with pytest.raises(EI.CandidateSurfaceForbiddenError) as exc:
            EI.assert_candidate_is_non_current(
                self._outcome(target_definition_bundle_id=uuid.uuid4())
            )
        assert "bundle" in str(exc.value)

    def test_outcome_records_the_full_9_10_audit_list(self) -> None:
        """Requirement 9.10 的记录清单逐项在 outcome 里可读。"""
        snapshot = self._outcome().as_dict()
        for field in (
            "template_definition_id", "template_definition_sha256",
            "instrumentation_definition_id", "instrumentation_definition_sha256",
            "target_contract_definition_id", "target_definition_bundle_id",
            "candidate_id", "source_representation_id", "staged_artifact_sha256",
            "visible_equivalence_report_sha256", "rollback_source_sha256",
            "content_revision_before", "content_revision_after", "revision_unchanged",
            "entry_pointer_before", "entry_pointer_after", "pointer_unchanged",
            "representation_count_before", "representation_count_after",
            "no_representation_created", "probe_gate", "actor_id", "structure_hash",
            "identity_inventory_sha256",
        ):
            assert field in snapshot, field


# ═══════════════════════════════════════════════════════════════════════════
# 8. zip 编辑工具（真实字节编辑，不 mock）
# ═══════════════════════════════════════════════════════════════════════════


def _read_entries(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _write_entries(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


def _edit_zip_entry(data: bytes, part: str, transform: Any) -> bytes:
    entries = _read_entries(data)
    if part not in entries:
        raise AssertionError(f"待编辑部件不存在: {part}")
    before = entries[part].decode("utf-8")
    after = transform(before)
    assert after != before, f"zip 编辑未生效: {part}（用例会变成无效变异）"
    entries[part] = after.encode("utf-8")
    return _write_entries(entries)


def _drop_zip_entry(data: bytes, part: str) -> bytes:
    entries = _read_entries(data)
    assert part in entries, part
    del entries[part]
    return _write_entries(entries)


def _managed_sheet_part(data: bytes, sheet_name: str) -> str:
    entries = _read_entries(data)
    workbook = entries["xl/workbook.xml"].decode("utf-8")
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(sheet_name) + r'"[^>]*r:id="(rId\d+)"', workbook
    )
    assert match, sheet_name
    rel = re.search(r'Id="' + match.group(1) + r'"[^>]*Target="([^"]+)"', rels)
    assert rel
    target = rel.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _clone_workbook(
    original: EI.InstrumentedWorkbook, new_bytes: bytes
) -> EI.InstrumentedWorkbook:
    return EI.InstrumentedWorkbook(
        source_sha256=original.source_sha256,
        instrumented_bytes=new_bytes,
        instrumented_sha256=_sha(new_bytes),
        managed_sheet_name_at_instrumentation=original.managed_sheet_name_at_instrumentation,
        managed_sheet_id_at_instrumentation=original.managed_sheet_id_at_instrumentation,
        row_uuids=original.row_uuids,
        gt_sync_pairs=original.gt_sync_pairs,
        defined_name_refs=original.defined_name_refs,
        table_ref=original.table_ref,
    )


def _mutate_visible_cell(data: bytes, *, sheet_part_hint: str) -> bytes:
    """改掉受管 sheet 上一个可见业务单元格的**值**，且保持 workbook 结构合法。

    🔴 只挑「无 `t=` 属性（即 `t="n"` 数字）、无 `<f>` 公式」的单元格：

    - `t="s"` 的 `<v>` 是 **sharedStrings 下标**，改成 999999 会越界，openpyxl 直接抛
      `IndexError` ⇒ 采集层报 `FingerprintError`，负对照变成「文件被写坏」而不是
      「等价判定打红」—— 与 Task 15 复盘的第 1 条通用规则同源（把判据打坏会伪造出
      「守卫没锁住」的观感）。
    - 带 `<f>` 的单元格里 `<v>` 只是缓存值，`data_only=False` 下 openpyxl 归到
      formulas 且读的是 `<f>` 文本，改缓存值**不产生任何 diff** ⇒ 负对照恒真通不过。
    """
    part = _managed_sheet_part(data, sheet_part_hint)
    entries = _read_entries(data)
    xml = entries[part].decode("utf-8")
    for match in re.finditer(r'<c r="([A-M]\d+)"([^>]*)>(<v>)([^<]+)(</v>)</c>', xml):
        open_attrs, inner_value = match.group(2), match.group(4)
        if 't="' in open_attrs:
            continue  # sharedStrings / inlineStr / bool / error：跳过
        new_value = "999999" if inner_value != "999999" else "888888"
        tampered = xml[: match.start(4)] + new_value + xml[match.end(4) :]
        assert tampered != xml
        entries[part] = tampered.encode("utf-8")
        return _write_entries(entries)
    raise AssertionError(
        f"{sheet_part_hint} 上找不到「无 t= 属性且无公式」的数字单元格，"
        "负对照无法构造（换模板或改判据，不要退化成改 sharedStrings 下标）"
    )
