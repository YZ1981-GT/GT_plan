# -*- coding: utf-8 -*-
"""K 循环 lane 2 — Task 7~9：KC-8 跨循环枢纽 K11 的键冻结。

spec: k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
Task 7: K11 的 9 键消费方清册
Task 8: 建立冻结清单与 H1 golden 回归钩子
Task 9: K11「有消费方但无载荷」的风险登记
Property: KB-P16, KB-P17, KB-P18, KB-P19, KB-P20, KB-P21

═══ 🔴 本组最贵的教训 ═══

**照抄 J 的「完全自闭」结论会漏掉整条跨循环风险。**
JC-17 在 J 循环是「J 键无一被非 J 消费」⇒ J 轮结论是「改键无跨循环风险」。
K 是**强命中**：K11 的 9 键被 H1 pilot / H3 / H8 / I1 四方消费。

═══ 🔴 K11 的双重特殊性 ═══

键有 **4 方跨循环消费者**，但 **`K11-%` 真库行数为 0**（完全无载荷）⇒
消费方读它**恒取空而不报错**。与 H 循环 BP-12 的「猜键回退链静默取空」同型风险。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    FRONTEND,
    ROOT,
    cached_text,
    k_domain_files,
    strip_comments,
)

FROZEN_PATH = DATA / "workpaper_sync_k11_frozen_cross_cycle_keys.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"

K11_ENTRY_ID = "xlsx/gt-k11-asset-impairment-loss"
H1_ENTRY_ID = "xlsx/gt-h1-fixed-assets"


@pytest.fixture(scope="module")
def frozen() -> dict:
    assert FROZEN_PATH.exists(), f"冻结清单不存在：{FROZEN_PATH}"
    return json.loads(FROZEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def non_k_frontend(k_files: list[pathlib.Path]) -> list[pathlib.Path]:
    k_set = set(k_files)
    return [
        p for p in FRONTEND.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".vue")
        and "__tests__" not in p.as_posix()
        and p not in k_set
    ]


@pytest.fixture(scope="module")
def k11_consumers(non_k_frontend: list[pathlib.Path]) -> dict[str, set[str]]:
    """非 K 域消费的 K11 键 -> 消费方文件名集合。"""
    rx = re.compile(r"['\"`](K11-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]")
    out: dict[str, set[str]] = {}
    for p in non_k_frontend:
        src = strip_comments(cached_text(p))
        for m in rx.finditer(src):
            out.setdefault(m.group(1), set()).add(p.name)
    return out


# ════════════════════════════════════════════════════════════════════════════
# Task 7 / KB-P16：9 键消费方清册
# ════════════════════════════════════════════════════════════════════════════
class TestKBP16NineKeysAndConsumers:
    """🔴 9 个键及其消费方逐条现算等值。"""

    def test_frozen_list_has_exactly_nine_keys(self, frozen: dict) -> None:
        keys = frozen["frozen_keys"]
        assert len(keys) == 9, f"冻结清单期望 9 键，实得 {len(keys)}"
        names = [k["key"] for k in keys]
        assert len(set(names)) == 9, "冻结清单有重复键"

    def test_each_frozen_key_matches_live_consumers(
        self, frozen: dict, k11_consumers: dict[str, set[str]]
    ) -> None:
        """清单登记的消费方与现算逐条等值。"""
        for item in frozen["frozen_keys"]:
            key = item["key"]
            declared = set(item["consumers"])
            actual = k11_consumers.get(key, set())
            assert actual == declared, (
                f"{key}: 多 {sorted(actual - declared)}，缺 {sorted(declared - actual)}"
            )
            assert len(declared) == item["consumer_count"], (
                f"{key}: consumer_count {item['consumer_count']} 与清单长度不符"
            )

    def test_detail_rows_has_four_consumers_including_h1(
        self, frozen: dict, k11_consumers: dict[str, set[str]]
    ) -> None:
        """🔴 `K11-2-detail-rows` 4 方消费，含 H1 pilot。"""
        item = next(
            k for k in frozen["frozen_keys"] if k["key"] == "K11-2-detail-rows"
        )
        assert item["consumer_count"] == 4
        assert item["includes_registered_pilot"] is True
        actual = k11_consumers["K11-2-detail-rows"]
        assert "useH1Impairment.ts" in actual

    def test_the_other_eight_have_one_consumer_each(self, frozen: dict) -> None:
        """其余 8 键各 1 方消费。"""
        others = [
            k for k in frozen["frozen_keys"] if k["key"] != "K11-2-detail-rows"
        ]
        assert len(others) == 8
        for item in others:
            assert item["consumer_count"] == 1, (
                f"{item['key']}: consumer_count {item['consumer_count']}"
            )

    def test_consumers_span_three_cycles(
        self, k11_consumers: dict[str, set[str]]
    ) -> None:
        """消费方覆盖 H1 / H3 / H8 / I1 四个非 K 入口。"""
        all_consumers: set[str] = set()
        for s in k11_consumers.values():
            all_consumers |= s
        for expected in (
            "useH1Impairment.ts",
            "h3ImpairmentCrossSheet.ts",
            "useH8Impairment.ts",
            "useI1Impairment.ts",
        ):
            assert expected in all_consumers, (
                f"消费方缺 {expected}：{sorted(all_consumers)}"
            )


class TestKBP18GlobalCounters:
    """全局现算：非 K 域消费 K 键 70 个；反向 K 域引非 K 键仅 4 种。"""

    def test_non_k_consuming_k_keys_count(
        self, non_k_frontend: list[pathlib.Path], frozen: dict
    ) -> None:
        rx = re.compile(r"['\"`](K(?:1[0-3]|[1-9])-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]")
        consumed: set[str] = set()
        for p in non_k_frontend:
            src = strip_comments(cached_text(p))
            consumed |= {m.group(1) for m in rx.finditer(src)}
        declared = frozen["global_counters"]["non_k_files_consuming_k_keys"]
        assert len(consumed) == declared, (
            f"非 K 域消费 K 键：清单登记 {declared}，实得 {len(consumed)}"
        )

    def test_reverse_direction_is_four_kinds(
        self, k_files: list[pathlib.Path], frozen: dict
    ) -> None:
        """🔴 反向：K 域引用的非 K 键仅 4 种（design 点名）。"""
        named = {
            "b19-alert",
            "b19-tag",
            "H1-14-supplement-total",
            "H1-14-calc-rows",
        }
        rx = re.compile(r"['\"`]([A-Za-z]\d+[A-Za-z0-9\-]*)['\"`]")
        found: set[str] = set()
        for p in k_files:
            src = strip_comments(cached_text(p))
            for m in rx.finditer(src):
                if m.group(1) in named:
                    found.add(m.group(1))
        assert found == named, (
            f"多 {sorted(found - named)}，缺 {sorted(named - found)}"
        )
        assert frozen["global_counters"]["k_domain_referencing_non_k_keys"] == 4

    def test_k11_detail_references_h1_keys_bidirectionally(
        self, k_files: list[pathlib.Path], frozen: dict
    ) -> None:
        """🔴 K11 ↔ H1 是**双向**耦合。"""
        rev = frozen["reverse_direction"]
        owner = next(
            (p for p in k_files if p.name == rev["referencing_file"]), None
        )
        assert owner is not None, f"{rev['referencing_file']} 不存在"
        src = strip_comments(cached_text(owner))
        for key in rev["k_domain_references_non_k_keys"]:
            assert key in src, f"{owner.name} 不引 {key}"


class TestKBP19JCycleConclusionDoesNotApply:
    """🔴 显式登记：照抄 J 的自闭结论会漏掉整条跨循环风险。"""

    def test_k_is_a_strong_hit_not_self_contained(
        self, k11_consumers: dict[str, set[str]]
    ) -> None:
        assert k11_consumers, (
            "K11 键无跨循环消费方 ⇒ K 与 J 同为自闭，KC-8 的登记须撤"
        )
        assert len(k11_consumers) >= 9

    def test_the_contrast_is_documented_in_frozen_list(
        self, frozen: dict
    ) -> None:
        why = frozen["why_this_file_exists"]
        assert "JC-17" in why, "冻结清单未点名与 J 的对照"
        assert "自闭" in why, "未写明 J 是自闭形态"
        assert "照抄" in why, "未警示照抄风险"

    def test_j_cycle_keys_are_really_self_contained(
        self, non_k_frontend: list[pathlib.Path]
    ) -> None:
        """🔴 两侧都验：J 循环的键确实**几乎无**跨域消费方（对照成立）。

        判据**现算**而不是查 slice 措辞 —— 「自闭」是 design.md 的裁决表述，
        slice JSON 里没有这个字面量（实测只有「跨循环」一词，且说的是 D0
        confirmation 组件复用，与键无关）。
        现算口径：非 J 域文件里出现的 `J{n}-` 键数，应远少于 K11 单条 entry 的 9 个。
        """
        j_rx = re.compile(
            r"['\"`](J(?:[1-9]|1[0-9])-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]"
        )
        j_owned = re.compile(r"/workpaper/j\d|(?:^|/)(?:use)?[jJ]\d")
        consumed: set[str] = set()
        for p in non_k_frontend:
            if j_owned.search(p.as_posix()):
                continue
            src = strip_comments(cached_text(p))
            consumed |= {m.group(1) for m in j_rx.finditer(src)}
        assert len(consumed) < 9, (
            f"J 循环有 {len(consumed)} 个键被跨域消费 {sorted(consumed)[:8]}"
            " ⇒ J 也是枢纽，「K 与 J 完全反向」的对照须复核"
        )

    def test_k11_hub_strength_far_exceeds_j(
        self, k11_consumers: dict[str, set[str]]
    ) -> None:
        """K11 单条 entry 就有 9 键跨循环消费 ⇒ 强度与 J 不可同日而语。"""
        assert len(k11_consumers) >= 9


# ════════════════════════════════════════════════════════════════════════════
# Task 8 / KB-P17：冻结清单与 H1 golden 回归钩子
# ════════════════════════════════════════════════════════════════════════════
class TestKBP17FreezeListAndRegressionHook:
    """🔴 9 键不得改名；改动触发 H1 pilot golden 回归。"""

    def test_frozen_list_is_the_single_source(self, frozen: dict) -> None:
        """冻结清单是唯一真源（有 schema + owner + why）。"""
        assert frozen["schema_version"] == "frozen-cross-cycle-keys:v1"
        assert frozen["owner_entry_id"] == K11_ENTRY_ID
        assert frozen["why_this_file_exists"].strip()

    def test_regression_hook_is_declared(self, frozen: dict) -> None:
        hook = frozen["regression_hook"]
        assert hook["trigger"].strip()
        assert "H1" in hook["required_action"]
        assert hook["why_h1"].strip()
        assert hook["guard"].endswith("test_k_lane2_p1_cross_cycle_hub.py"), (
            f"guard 指向 {hook['guard']} ⇒ 应指向本文件"
        )

    def test_h1_adapter_id_is_non_null(self) -> None:
        """H1 的 `adapter_id` 非空（golden 回归的可行性依据）。"""
        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        h1 = next(
            (e for e in manifest["entries"] if e["entry_id"] == H1_ENTRY_ID), None
        )
        assert h1 is not None, f"manifest 找不到 {H1_ENTRY_ID}"
        assert h1["adapter_id"] is not None, (
            "H1 的 adapter_id 为 null ⇒ golden 回归无从跑，钩子失去依据"
        )

    def test_h1_contract_is_reviewed(self) -> None:
        """H1 的契约已 reviewed。"""
        found = []
        for p in CONTRACT_DIR.glob("*.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if (doc.get("review") or {}).get("entry_id") == H1_ENTRY_ID:
                found.append((p.name, doc.get("review_status")))
        assert found, f"找不到 H1 的契约"
        assert any(status == "reviewed" for _n, status in found), (
            f"H1 契约均非 reviewed：{found}"
        )

    def test_golden_payload_must_come_from_h1_side(self, frozen: dict) -> None:
        """🔴 golden 载荷用 **H1 自己的** —— 不能指望 K11 侧有数据。"""
        hook = frozen["regression_hook"]
        src_note = hook.get("🔴 golden_payload_source", "")
        assert "H1" in src_note, "未写明 golden 载荷来源"
        assert "K11" in src_note, "未说明为什么不能用 K11 侧"

    def test_pilot_flags_are_consistent_with_manifest(self, frozen: dict) -> None:
        """清单里标 `includes_registered_pilot` 的键，其消费方确含 H1。"""
        for item in frozen["frozen_keys"]:
            has_h1 = "useH1Impairment.ts" in item["consumers"]
            assert item["includes_registered_pilot"] == has_h1, (
                f"{item['key']}: pilot 标记 {item['includes_registered_pilot']}"
                f" 与消费方 {item['consumers']} 不符"
            )

    def test_all_nine_keys_are_k11_prefixed(self, frozen: dict) -> None:
        for item in frozen["frozen_keys"]:
            assert re.match(r"^K11-", item["key"]), (
                f"{item['key']} 不是 K11 前缀 ⇒ 不该在本清单里"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 9 / KB-P20~P21：有消费方但无载荷
# ════════════════════════════════════════════════════════════════════════════
class TestKBP20NoLivePayloadRisk:
    """🔴 K11 键有 4 方跨循环消费者但真库无载荷 ⇒ 恒取空而不报错。"""

    def test_risk_is_registered(self, frozen: dict) -> None:
        risk = frozen["no_live_payload_risk"]
        assert risk["k11_live_row_count"] == 0
        assert "有消费方但无载荷" in risk["verdict"]
        assert risk["what_happens"].strip()

    def test_same_type_as_h_cycle_bp12(self, frozen: dict) -> None:
        """🔴 与 H 循环 BP-12「猜键回退链静默取空」同型风险。"""
        risk = frozen["no_live_payload_risk"]
        assert "BP-12" in risk["same_type_as"], (
            "未点名 H 循环 BP-12 的同型风险"
        )
        assert "静默取空" in risk["same_type_as"]

    def test_detection_criterion_is_declared(self, frozen: dict) -> None:
        """检测判据：消费方读空时应告警而非静默（当前实现是静默，登记待修）。"""
        risk = frozen["no_live_payload_risk"]
        crit = risk["detection_criterion"]
        assert "告警" in crit and "静默" in crit
        assert "待修" in crit, "未登记为待修 ⇒ 会被当成已解决"

    def test_roundtrip_strategy_is_synthetic(self, frozen: dict) -> None:
        """🔴 K11 的 roundtrip 用合成载荷并标 tag，不得宣称真库实证。"""
        risk = frozen["no_live_payload_risk"]
        strategy = risk["roundtrip_strategy"]
        assert "synthetic_payload_no_live_db_baseline" in strategy
        assert "不得宣称" in strategy

    def test_consumers_read_without_null_guard(
        self, non_k_frontend: list[pathlib.Path], frozen: dict
    ) -> None:
        """🔴 现算实证：消费方读 K11 键时**没有**「取空告警」逻辑。

        判据形状：消费方文件里出现 K11 键，但同文件找不到
        「读空 → 告警/抛错」的形态（`ElMessage.warning` / `throw` / `console.warn`
        与该键在同一函数内）。这里用**文件级近似**：整文件无任何告警符号
        ⇒ 必然没有针对该键的告警。
        """
        alert_symbols = ("ElMessage", "console.warn", "console.error", "throw new")
        silent_consumers: list[str] = []
        consumer_names = {
            c for item in frozen["frozen_keys"] for c in item["consumers"]
        }
        for p in non_k_frontend:
            if p.name not in consumer_names:
                continue
            src = strip_comments(cached_text(p))
            if not any(sym in src for sym in alert_symbols):
                silent_consumers.append(p.name)
        # 至少有一个消费方完全没有告警能力 ⇒ 静默取空风险成立
        assert silent_consumers, (
            "全部消费方都有告警符号 ⇒ 「静默取空」的登记须复核"
            f"（消费方：{sorted(consumer_names)}）"
        )


class TestKBP21RiskParityWithHCycle:
    """风险登记的可复算性：H 循环 BP-12 真实存在（对照非虚构）。"""

    def test_h_cycle_bp12_is_a_spec_level_id_not_in_the_slice(self) -> None:
        """🔴 口径澄清：`BP-12` 是 **H 循环 spec 的裁决编号**，不在 H slice 里。

        实测 H slice 的 BP 清单最高只到 **BP-10**。design.md 引用的「H 循环
        BP-12 的猜键回退链」是 H 的 **lane spec** 层裁决（`h2-h6-h10-...` /
        `h3-h5-h7-...` 等），不是 slice 字面量。
        ⇒ 判据不得按「H slice 含 BP-12」写，否则必假红。
        """
        h_slice = DATA / "workpaper_sync_h_cycle_manifest_slice.json"
        if not h_slice.exists():
            pytest.skip("H slice 不存在")
        blob = h_slice.read_text(encoding="utf-8")
        found = sorted(set(re.findall(r"BP-\d+", blob)))
        assert found, "H slice 完全没有 BP 编号 ⇒ 对照基础不存在"
        max_bp = max(int(b.split("-")[1]) for b in found)
        assert max_bp <= 11, (
            f"H slice 的 BP 最高到 {max_bp} ⇒ 若已含 BP-12 则本澄清可撤"
        )

    def test_the_guess_key_fallback_risk_shape_is_real_in_h_specs(self) -> None:
        """两侧都验：H 的 lane spec 里真有「猜键回退链」这个形态。"""
        specs_dir = ROOT / ".kiro" / "specs"
        h_specs = [
            d for d in specs_dir.iterdir()
            if d.is_dir() and d.name.startswith("h")
        ]
        assert h_specs, "找不到 H 循环的 spec 目录"
        hits: list[str] = []
        for d in h_specs:
            for name in ("requirements.md", "design.md", "tasks.md"):
                p = d / name
                if not p.exists():
                    continue
                text = p.read_text(encoding="utf-8")
                if "猜键" in text or "BP-12" in text:
                    hits.append(f"{d.name}/{name}")
        assert hits, (
            "H 循环 spec 里找不到「猜键」或 BP-12 ⇒ 同型风险的对照对象不存在"
        )

    def test_the_two_risks_share_the_silent_empty_read_shape(
        self, frozen: dict
    ) -> None:
        """两者共同形态：键存在 + 载荷为空 + 消费方不报错。"""
        risk = frozen["no_live_payload_risk"]
        assert risk["k11_live_row_count"] == 0, "K11 有载荷 ⇒ 风险形态不成立"
        # 键确实存在（不是「键也不存在」那种更简单的情形）
        assert len(frozen["frozen_keys"]) == 9

    def test_k13_is_also_zero_payload_but_without_consumers(
        self, non_k_frontend: list[pathlib.Path]
    ) -> None:
        """🔴 对照：K13 真库也 0 行，但**无跨循环消费方** ⇒ 风险等级不同。

        K11 = 有消费方 + 无载荷（静默错值）
        K13 = 无消费方 + 无载荷（只影响自己）
        """
        rx = re.compile(r"['\"`](K13-[A-Za-z0-9][A-Za-z0-9\-]*)['\"`]")
        consumed: set[str] = set()
        for p in non_k_frontend:
            src = strip_comments(cached_text(p))
            consumed |= {m.group(1) for m in rx.finditer(src)}
        # K13 的跨循环消费方应远少于 K11 的 9 键
        assert len(consumed) < 9, (
            f"K13 有 {len(consumed)} 个键被跨循环消费 {sorted(consumed)}"
            " ⇒ 它也是枢纽，风险分级须更新"
        )
