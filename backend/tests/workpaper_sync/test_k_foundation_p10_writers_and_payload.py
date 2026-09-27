# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 2 Task 24~25：写入方集合与合成载荷。

spec: k-cycle-sync-foundation-and-first-canary
Task 24: 写入方集合与 roundtrip 骨架
Task 25: 合成载荷补金额维度
Property: KF-P46, KF-P47, KF-P9

═══ 🔴 两处与 design.md 的偏差（承接 Task 20 的发现）═══

1. **canary 没有 footer SUM**（Task 20 已两侧验证）⇒ Task 25 的
   「断言金额维度的 footer 重算一致」**无对象**。本文件把该判据改为
   「数据区行的写入与读回结构一致」+「金额字段类型与精度不失真」。

2. **真库载荷是测试骨架**（`description="测试确认政府补助"` / 金额全 0 /
   五字段空串）⇒ roundtrip **只能验结构**。本文件交付合成载荷生成器
   + 标 `synthetic_payload_for_amount_dimension`。

═══ roundtrip 骨架的真实边界 ═══

🔴 完整 roundtrip（HTML → 服务端 → OO → 服务端 → HTML）需要**已注册的
adapter**，而 K 循环 13 条的 `adapter_id` 全 null（BP-1/BP-2 未交付）。
⇒ 本文件交付的是**骨架与判据**，不是跑通的 roundtrip。实际跑通归 Task 23
（标 `[ ]*`）。这一点显式登记，不宣称通过。
"""
from __future__ import annotations

import json
import pathlib
import re
from decimal import Decimal

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    K_INDEXES,
    ROOT,
    WP_COMPONENTS,
    cached_text,
    endpoint_index,
    form_data_path,
    k_domain_files,
    literal_hits,
    strip_comments,
)

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_k_cycle_manifest_slice.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"

CANARY_ENTRY_ID = "xlsx/gt-k10-other-income"
CANARY_KEY = "K10-3-entries"
EP_CHECKLIST = "/api/workpapers/{X}/checklist-responses"

#: canary 载荷的 8 个字段（design.md 逆风①逐字段登记）
CANARY_PAYLOAD_FIELDS = (
    "description",
    "category",
    "reportItem",
    "noteItem",
    "debitAmount",
    "creditAmount",
    "refIndex",
    "remark",
)

#: 真库载荷是测试骨架 —— 五个空串字段
SKELETON_EMPTY_FIELDS = (
    "category",
    "reportItem",
    "noteItem",
    "refIndex",
    "remark",
)


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(MANIFEST_SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canary_tab(k_files: list[pathlib.Path]) -> pathlib.Path:
    p = next((x for x in k_files if x.name == "K10TabAdjustment.vue"), None)
    assert p is not None, "K10TabAdjustment.vue 不存在"
    return p


# ════════════════════════════════════════════════════════════════════════════
# Task 24 / KF-P47：写入方集合必须含 useAdjustmentCentralSync
# ════════════════════════════════════════════════════════════════════════════
class TestKFP47WriterSetIncludesCentralSync:
    """🔴 `useAdjustmentCentralSync` 是 roundtrip 的**第二写入方**。"""

    def test_central_sync_hits_13_files_3_sites_each(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """13 条各 3 处（全 K 一致）。"""
        hits = literal_hits(k_files, "useAdjustmentCentralSync")
        assert len(hits) == 13, (
            f"useAdjustmentCentralSync 文件数期望 13，实得 {len(hits)}"
        )
        for name, count in hits.items():
            assert count == 3, f"{name}: 期望 3 处，实得 {count}"

    def test_all_13_are_tab_adjustment_components(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """全部落在 `K{n}TabAdjustment.vue`（载体层一致）。"""
        hits = literal_hits(k_files, "useAdjustmentCentralSync")
        for name in hits:
            assert re.match(r"^K(1[0-3]|[1-9])TabAdjustment\.vue$", name), (
                f"{name} 不是 TabAdjustment 组件 ⇒ 载体层登记须更新"
            )
        covered = {
            int(re.match(r"^K(1[0-3]|[1-9])", n).group(1)) for n in hits
        }
        assert covered == set(K_INDEXES), (
            f"未覆盖的 entry：{sorted(set(K_INDEXES) - covered)}"
        )

    def test_canary_tab_uses_central_sync(self, canary_tab: pathlib.Path) -> None:
        src = strip_comments(cached_text(canary_tab))
        assert len(re.findall(r"useAdjustmentCentralSync", src)) == 3

    def test_canary_tab_also_emits_save(self, canary_tab: pathlib.Path) -> None:
        """第一写入方：`emit('save')` → 宿主 → `useK10FormData` → checklist 端点。"""
        src = strip_comments(cached_text(canary_tab))
        assert re.search(r"emit\(\s*['\"]save['\"]", src), (
            "K10TabAdjustment.vue 没有 emit('save') ⇒ 第一写入方链路断了"
        )

    def test_writer_set_has_exactly_two_members(
        self, canary_tab: pathlib.Path
    ) -> None:
        """🔴 写入方集合 = {checklist 持久化链, useAdjustmentCentralSync}。"""
        src = strip_comments(cached_text(canary_tab))
        has_emit = bool(re.search(r"emit\(\s*['\"]save['\"]", src))
        has_central = "useAdjustmentCentralSync" in src
        assert has_emit and has_central, (
            f"写入方缺失：emit={has_emit} central={has_central}"
        )


class TestKFP9CanaryCarrierFamily:
    """canary 的读写载体属 `formdata_composable_bare_endpoint` 族。"""

    def test_use_k10_form_data_has_two_checklist_endpoints(self) -> None:
        p = form_data_path(10)
        src = strip_comments(cached_text(p))
        assert len(re.findall(r"checklist-responses", src)) == 2, (
            "useK10FormData.ts 的 checklist 端点数不是 2 ⇒ 载体族判定须复核"
        )

    def test_use_k10_form_data_has_the_tb_publish_gate(self) -> None:
        """K10 的 TB 发布门在 `useK10FormData.ts`（四层里的 FormData 层）。"""
        p = form_data_path(10)
        src = strip_comments(cached_text(p))
        assert len(re.findall(r"publish-to-tb", src)) == 1

    def test_canary_key_is_referenced_in_the_tab(
        self, canary_tab: pathlib.Path
    ) -> None:
        src = strip_comments(cached_text(canary_tab))
        assert CANARY_KEY in src, (
            f"{canary_tab.name} 不引 {CANARY_KEY} ⇒ 键归属须复核"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 24：roundtrip 骨架的真实边界（不宣称跑通）
# ════════════════════════════════════════════════════════════════════════════
class TestRoundtripSkeletonBoundary:
    """🔴 完整 roundtrip 需已注册 adapter；K 循环 13 条全 null ⇒ 不宣称通过。"""

    def test_no_k_entry_has_a_registered_adapter(self) -> None:
        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        k_with_adapter = [
            e["entry_id"] for e in manifest["entries"]
            if e.get("adapter_id")
            and any(
                str(p).startswith("K")
                for p in ((e.get("wp_match") or {}).get("wp_code_patterns") or [])
            )
        ]
        assert k_with_adapter == [], (
            f"K 循环有 entry 已注册 adapter：{k_with_adapter}"
            " ⇒ roundtrip 可真跑，本条边界登记须撤"
        )

    def test_roundtrip_is_blocked_by_bp1_and_bp2(
        self, manifest_slice: dict
    ) -> None:
        """canary 的 blocked_by 含 BP-1 / BP-2 ⇒ roundtrip 卡外部供给。"""
        k10 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == CANARY_ENTRY_ID
        )
        blocked = set(k10["capability_target_blocked_by"])
        assert {"BP-1", "BP-2"} <= blocked, (
            f"BP-1/BP-2 不在 blocked_by 里：{sorted(blocked)}"
        )

    def test_the_write_path_endpoint_really_exists(self) -> None:
        """写路径末端的后端 PUT 处理器真实存在（非 404）⇒ 骨架有对端。"""
        router = ROOT / "backend" / "app" / "routers" / "checklist_responses.py"
        assert router.exists(), f"checklist 路由不存在：{router}"
        src = strip_comments(router.read_text(encoding="utf-8"))
        assert re.search(r"@router\.put\(", src), (
            "checklist_responses.py 没有 PUT 处理器 ⇒ 写路径无对端"
        )

    def test_structural_roundtrip_is_verifiable_without_adapter(
        self, canary_tab: pathlib.Path
    ) -> None:
        """结构 roundtrip（payload 形状）可在无 adapter 时验。"""
        src = strip_comments(cached_text(canary_tab))
        for field in CANARY_PAYLOAD_FIELDS:
            assert re.search(rf"\b{field}\b", src), (
                f"载荷字段 {field} 在 canary Tab 里 0 命中 ⇒ 结构不完整"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 25 / KF-P46：真库载荷是测试骨架 + 合成载荷补金额维度
# ════════════════════════════════════════════════════════════════════════════
class TestKFP46SkeletonPayloadAndSyntheticAmount:
    """🔴 如实登记真库载荷是测试骨架，roundtrip 只能验结构。"""

    #: 真库实测载荷（design.md 逆风① 逐字段登记）
    LIVE_SKELETON = {
        "id": "entry-1784790231509-wlnkon",
        "description": "测试确认政府补助",
        "category": "",
        "reportItem": "",
        "noteItem": "",
        "debitAmount": 0,
        "creditAmount": 0,
        "refIndex": "",
        "remark": "",
    }

    def test_live_payload_is_a_test_skeleton(self) -> None:
        """金额全 0 + 五字段空串 ⇒ 只能验结构不能验金额。"""
        assert self.LIVE_SKELETON["debitAmount"] == 0
        assert self.LIVE_SKELETON["creditAmount"] == 0
        for f in SKELETON_EMPTY_FIELDS:
            assert self.LIVE_SKELETON[f] == "", (
                f"字段 {f} 在真库载荷里非空 ⇒ 骨架登记须更新"
            )
        assert self.LIVE_SKELETON["description"].startswith("测试"), (
            "description 不是测试串 ⇒ 骨架登记须更新"
        )

    def test_id_pattern_is_entry_timestamp_base36(self) -> None:
        """id 形态 `entry-{13位时间戳}-{6位base36}`。"""
        assert re.match(
            r"^entry-\d{13}-[0-9a-z]{6}$", self.LIVE_SKELETON["id"]
        ), f"id 形态不符：{self.LIVE_SKELETON['id']!r}"

    def test_id_generator_in_source_matches_the_pattern(
        self, canary_tab: pathlib.Path
    ) -> None:
        """前端生成器与真库形态一致（两侧都验）。"""
        src = strip_comments(cached_text(canary_tab))
        assert re.search(
            r"entry-\$\{Date\.now\(\)\}-\$\{Math\.random\(\)\.toString\(36\)",
            src,
        ), "找不到 `entry-${Date.now()}-${Math.random().toString(36)...}` 生成器"

    def test_synthetic_payload_generator_produces_valid_amounts(self) -> None:
        """合成载荷生成器：带真实金额，标 `synthetic_payload_for_amount_dimension`。"""
        synthetic = _make_synthetic_payload()
        assert synthetic["_evidence_tag"] == "synthetic_payload_for_amount_dimension"
        rows = synthetic["rows"]
        assert rows, "合成载荷为空 ⇒ 金额维度无对象"
        for row in rows:
            # id 走安全族
            assert re.match(r"^entry-\d{13}-[0-9a-z]{6}$", row["id"])
            # 金额非 0
            assert row["debitAmount"] != 0 or row["creditAmount"] != 0, (
                f"合成行金额全 0 {row} ⇒ 与真库骨架无区别，补金额维度失去意义"
            )
            # 八字段齐备
            for f in CANARY_PAYLOAD_FIELDS:
                assert f in row, f"合成行缺字段 {f}"

    def test_synthetic_amounts_are_debit_credit_balanced(self) -> None:
        """合成载荷借贷平衡（调整分录的业务不变式）。"""
        synthetic = _make_synthetic_payload()
        debit = sum(Decimal(str(r["debitAmount"])) for r in synthetic["rows"])
        credit = sum(Decimal(str(r["creditAmount"])) for r in synthetic["rows"])
        assert debit == credit, (
            f"合成载荷借贷不平：借 {debit} vs 贷 {credit}"
        )

    def test_synthetic_amounts_survive_decimal_roundtrip(self) -> None:
        """金额维度判据：`Decimal` 序列化往返不失真（含两位小数）。"""
        synthetic = _make_synthetic_payload()
        blob = json.dumps(synthetic, ensure_ascii=False)
        back = json.loads(blob)
        for a, b in zip(synthetic["rows"], back["rows"]):
            assert Decimal(str(a["debitAmount"])) == Decimal(str(b["debitAmount"]))
            assert Decimal(str(a["creditAmount"])) == Decimal(str(b["creditAmount"]))

    def test_amount_dimension_criterion_is_row_level_not_footer_level(self) -> None:
        """🔴 承接 Task 20 的发现：canary 无 footer ⇒ 金额判据按**行级**。

        design.md 的「断言 footer 重算（连续区间 SUM 族）一致」在 canary 上
        无对象（13 册「调整分录汇总」SUM 数全 0）。改为：
          - 行级：每行 debitAmount / creditAmount 写入与读回相等
          - 汇总级：借贷合计在应用层校验（不依赖模板 SUM）
        """
        from openpyxl import load_workbook

        wb = load_workbook(
            ROOT / "backend" / "wp_templates" / "K" / "K10 其他收益.xlsx",
            read_only=False,
            data_only=False,
        )
        try:
            ws = wb["调整分录汇总K10-3"]
            has_sum = any(
                isinstance(c.value, str) and "SUM(" in c.value.upper()
                for row in ws.iter_rows()
                for c in row
            )
            assert not has_sum, "canary 有 SUM ⇒ 可用 footer 判据，本条登记须撤"
        finally:
            wb.close()
        # 行级判据可用：合成载荷的行级金额校验（上面两条已验）
        synthetic = _make_synthetic_payload()
        assert len(synthetic["rows"]) >= 2, (
            "合成载荷行数 < 2 ⇒ 行级判据的分母太小"
        )

    def test_evidence_must_be_tagged_synthetic(self) -> None:
        """🔴 合成载荷的 evidence 必须标记，不得宣称真库实证。"""
        synthetic = _make_synthetic_payload()
        assert synthetic["_evidence_tag"] == "synthetic_payload_for_amount_dimension"
        assert synthetic.get("_is_live_db_evidence") is False, (
            "合成载荷未显式标注「非真库实证」⇒ 会被误当真库证据"
        )


# ════════════════════════════════════════════════════════════════════════════
# 合成载荷生成器
# ════════════════════════════════════════════════════════════════════════════
def _make_synthetic_payload() -> dict:
    """产出带金额的合成载荷（标 `synthetic_payload_for_amount_dimension`）。

    🔴 id 走**安全族**（`entry-{13位ts}-{6位base36}`，含熵无兜底）。
    🔴 借贷平衡是调整分录的业务不变式。
    """
    return {
        "_evidence_tag": "synthetic_payload_for_amount_dimension",
        "_is_live_db_evidence": False,
        "_why": (
            "真库 canary 载荷是测试骨架（金额全 0 + 五字段空串），"
            "roundtrip 只能验结构；本载荷补金额维度。"
        ),
        "rows": [
            {
                "id": "entry-1784790231509-abc123",
                "description": "政府补助分类纠正：6117 其他收益转 6301 营业外收入",
                "category": "报表调整",
                "reportItem": "其他收益",
                "noteItem": "政府补助",
                "debitAmount": 1250000.50,
                "creditAmount": 0,
                "refIndex": "K10-3-1",
                "remark": "合成载荷 - 金额维度",
            },
            {
                "id": "entry-1784790231510-def456",
                "description": "政府补助分类纠正：对方科目",
                "category": "报表调整",
                "reportItem": "营业外收入",
                "noteItem": "政府补助",
                "debitAmount": 0,
                "creditAmount": 1250000.50,
                "refIndex": "K10-3-2",
                "remark": "合成载荷 - 金额维度",
            },
        ],
    }
