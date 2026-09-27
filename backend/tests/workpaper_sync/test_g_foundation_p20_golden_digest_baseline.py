# -*- coding: utf-8 -*-
"""GF-P20：零回归基线**现算逐项**比对（GC-10：不断言集合大小）。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 4　Requirements 7.1, 7.2

═══ 为什么不能写死数字 ═══

spec design §GC-10 写「`PROVIDERS` 已含 b60/d1/d2/d3/d4/d5/d6/d7/e1(+g7/h1)、契约目录现 12 个 json」。
2026-09-27 现算：`PROVIDERS` 实为 **b60 d1 d2 d3 d4 d5 d6 d7 e1 f1** ——
**g7 / h1 不在**（它们有契约但未纳入该 digest 门），而 **f1 在**（并发会话本轮交付）。
这恰好实证 GC-10 本身：任何写死的成员快照都会 stale。
⇒ 本判据只断言「**非 G** 的 digest 逐项不变」，成员清单现算。
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

CONTRACT_DIR = _BACKEND / "data" / "workpaper_sync_contracts"
DIGEST_BASELINE = _BACKEND / "scripts" / "check" / "_sync_provider_golden_digest.json"


@pytest.fixture(scope="module")
def checker():
    return importlib.import_module("scripts.check.check_sync_provider_golden_digest")


def _non_g(names):
    """过滤掉 G 循环成员（G7 是已归档 spec，也按 G 处理 —— 它不在 PROVIDERS 里）。"""
    return sorted(n for n in names if not str(n).lower().startswith("g"))


class TestGfP20ZeroRegressionIsComputedNotHardcoded:
    """Validates: 7.1, 7.2"""

    def test_providers_tuple_is_readable_and_nonempty(self, checker) -> None:
        assert getattr(checker, "PROVIDERS", None), "PROVIDERS 读不到 ⇒ 零回归门的分母缺失"

    def test_non_g_provider_membership_is_recorded_not_counted(self, checker) -> None:
        """🔴 判据形态：记录**逐项成员**，不断言集合大小。

        基线只钉「这些非 G 成员必须仍在」（单调不减），新增非 G 成员不打红 ——
        那是别的 spec 的交付，本 spec 不该阻塞它。
        """
        must_stay = {"b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "e1"}
        got = {p[0] for p in checker.PROVIDERS}
        missing = sorted(must_stay - got)
        assert not missing, (
            f"以下既有非 G provider 从零回归门里消失了: {missing}\n"
            "删 provider 必须是显式裁决，不得因加 G 而顺手掉"
        )

    def test_baseline_file_has_no_g_cycle_entries_yet(self) -> None:
        """现状锚点：digest 基线文件里还没有 G 条目（G 循环零 provider）。

        Task 14 交付 G2 后本条会变 —— 那时应改为「G2 在且其余非 G 逐项不变」。
        """
        assert DIGEST_BASELINE.exists(), f"digest 基线文件不存在: {DIGEST_BASELINE}"
        doc = json.loads(DIGEST_BASELINE.read_text(encoding="utf-8"))
        keys = doc.get("providers", doc) if isinstance(doc, dict) else {}
        g_keys = sorted(k for k in keys if str(k).lower().startswith("g"))
        # g7 有契约但不在 PROVIDERS ⇒ 基线里也不该有
        assert g_keys == [], (
            f"digest 基线里出现 G 条目: {g_keys}\n"
            "若是本 spec 的 Task 14 刚交付，请把本判据改成「G2 在 + 非 G 逐项不变」"
        )

    def test_contract_dir_inventory_is_listed_not_counted(self) -> None:
        """契约目录：登记**逐项清单**，不断言「共 N 个」。"""
        found = sorted(
            p.stem
            for p in CONTRACT_DIR.glob("*.json")
            if not p.stem.startswith("_")
        )
        must_stay = [
            "b60.hour_budget",
            "d1.notes_receivable_detail",
            "d2.receivable_detail",
            "d3.prepaid_receipts_detail",
            "d4.revenue_detail",
            "d5.receivables_financing_detail",
            "d6.contract_assets_detail",
            "d7.contract_liabilities_detail",
            "e1.monetary_fund_detail",
            "f1.prepayment_detail",
            "g7.soe_subsidiary_disclosure",
            "h1.disposal_check",
            # ── 本 spec Task 14 交付 ──
            "g2.interest_receivable_detail",
        ]
        missing = [c for c in must_stay if c not in found]
        assert not missing, f"以下既有契约消失: {missing}\n现有: {found}"

    def test_mutation_size_assertion_is_fragile(self) -> None:
        """自省变异：证明「断言集合大小」这种写法**当下就已经**会 stale。

        spec 写的是 12 个 json；现算含 `_example.candidate.json` 时是 13、
        排除下划线前缀时是 12 —— 同一句话在两种过滤口径下给出不同数字，
        正是 GC-10 要禁掉的脆弱形态。
        """
        all_json = len(list(CONTRACT_DIR.glob("*.json")))
        real = len([p for p in CONTRACT_DIR.glob("*.json") if not p.stem.startswith("_")])
        assert all_json != real, (
            "两种过滤口径给出同一个数 ⇒ 本变异失去说明力（可能 _example 被删了），"
            "改用别的脆弱性证据"
        )

    def test_g_provider_whitelist_contains_exactly_the_delivered_ones(self) -> None:
        """登记点②：`_ALLOWED_PROVIDER_MODULES` 里的 `phase5_g*` 恰是**已交付**的那些。

        白名单是**安全边界**（不得从登记表任意 import）⇒ 多一条都要有 provider 文件对应。

        🔴 **改为现算**（GC-10「零回归基线一律现算不写死」）：期望值从
        `DELIVERED_PER_ENTRY_CONTRACTS` 取，不再写死名单。首版写死
        `["…phase5_g2_interest_receivable"]` 并留了「新增 G lane 时在此追加」的指引 ——
        实际效果是 `g-cycle-single-region-detail-lanes` Task 8/9/9b/10/11 交付
        G9/G10/G8/G14/G11 后本判据必红，而那五条都是合法交付。写死的是**分母**，
        每条 lane 都得来手改一次，改的人还得判断「该不该改」⇒ 判据在教人放宽自己。
        现算之后守的是真正要守的那件事：**白名单 ↔ 交付台账双向配平**
        （白名单多一条而台账没登记、或台账登记了而白名单漏了，都红）。
        `pilot_g7_two_level_dynamic` 走 pilot 段、不含 `phase5_g` ⇒ 天然不在此列
        （裁决 GF-H3：G7 是旧先导范式）。
        """
        from app.services.workpaper_sync.adapters import registry  # type: ignore

        allowed = getattr(registry, "_ALLOWED_PROVIDER_MODULES", None)
        assert allowed is not None, "_ALLOWED_PROVIDER_MODULES 读不到 ⇒ 登记点判据无基础"
        g_mods = sorted(m for m in allowed if "phase5_g" in str(m))
        delivered = sorted(
            str(r["provider_module"])
            for r in registry.DELIVERED_PER_ENTRY_CONTRACTS
            if "phase5_g" in str(r.get("provider_module") or "")
        )
        assert g_mods == delivered, (
            "白名单的 phase5_g* 与交付台账不配平。\n"
            f"  白名单有而台账缺：{sorted(set(g_mods) - set(delivered))}\n"
            f"  台账有而白名单缺：{sorted(set(delivered) - set(g_mods))}\n"
            "追加台账条目时**必须同步白名单**，否则 provider 会在 "
            "`build_manifest_registration_plan` 里被判「不得从登记表任意 import」而拒绝注册"
        )
        assert "app.services.workpaper_sync.phase5_g2_interest_receivable" in g_mods, (
            "G2 canary 掉出白名单 ⇒ foundation 的交付面被回退了"
        )
        # 白名单条目必须真能 import（否则注册路径会在运行时炸）
        import importlib

        for m in g_mods:
            importlib.import_module(m)

    def test_g2_contract_and_registration_entry_are_delivered(self) -> None:
        """登记点①④：契约文件在盘 + `DELIVERED_PER_ENTRY_CONTRACTS` 有 G2 条目。"""
        from app.services.workpaper_sync.adapters import registry  # type: ignore

        path = CONTRACT_DIR / "g2.interest_receivable_detail.json"
        assert path.is_file(), f"G2 契约未落盘: {path}"
        rows = [
            r
            for r in registry.DELIVERED_PER_ENTRY_CONTRACTS
            if r.get("contract_id") == "g2.interest_receivable_detail"
        ]
        assert len(rows) == 1, f"G2 的交付登记条目数 ={len(rows)}（应恰 1）"
        row = rows[0]
        assert row["entry_id"] == "xlsx/gt-g2-interest-receivable"
        assert row["provider_module"] == (
            "app.services.workpaper_sync.phase5_g2_interest_receivable"
        )
        assert row["template_relative_path"] == "G/G2 应收利息.xlsx"
        # 🔴 供给未就绪 ⇒ 如实 False（不伪造注册成功）
        assert row["adapter_registered"] is False, (
            "G2 声称 adapter_registered=True ⇒ 须有真栈注册证据（BP-1~BP-3 供给就绪）"
        )
        assert "BP-61-1" in row["reason"] or "BP-1" in row["reason"], (
            "reason 未写明卡在哪个平台级缺口 ⇒ `upstream_gap` 不可复核"
        )

    def test_g2_store_merge_plan_declares_neutralization(self) -> None:
        """登记点③：`STORE_MERGE_REGISTRY` 有 G2 的 plan 且带中性化（GC-2）。"""
        from app.services.workpaper_sync.store_item_registry import (  # type: ignore
            STORE_MERGE_REGISTRY,
        )

        plan = STORE_MERGE_REGISTRY.get("g2.interest_receivable_detail")
        assert plan is not None, "G2 没有 StoreMergePlan"
        assert plan.provider_module == "phase5_g2_interest_receivable"
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas", (
            f"G2 的 plan 未挂中性化: {plan.oo_crash_neutralization_fn!r}（GC-2 per-file 保守策略）"
        )
        assert [i.item_id for i in plan.items] == ["G2-2-detail-rows"]


# ═══════════════════════════════════════════════════════════════════════════
# Task 14 之后：G2 已入零回归门 —— 逐 provider 核「digest 可现算」
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 **已登记的既存阻塞**：`label -> (归属 spec, 根因)`。
#:
#: `check_sync_provider_golden_digest.run()` 是「全 PROVIDERS 一次性算完」的形态 ——
#: 任一家抛异常整个门就红。实测该门**自并发会话把 f1 加进 PROVIDERS 起就一直红**
#: （baseline 文件里只有 b60/d1..d7/e1 共 9 家，没有 f1 ⇒ 他们加了成员但没能跑 `--update`）。
#:
#: 本 spec **不修 F1**（`phase5_f1_prepayment.py` 与 `f1.prepayment_detail.json` 都是
#: 并发会话的未跟踪新文件，属 `f1-sync-coverage-and-first-canary` 作业面，
#: 改它会与在飞工作冲突），但也**不接受一个红着的门当基线** ⇒ 逐 provider 核可算性，
#: 把 F1 的失败登记为具名例外。F1 修好后本判据会打红，提示把登记移除。
KNOWN_PRE_EXISTING_BLOCKERS: dict[str, tuple[str, str]] = {
    "f1": (
        "f1-sync-coverage-and-first-canary",
        "契约 table payload 是手写形态（缺 anchor / header_rows / "
        "row_identity.json_pointer），`parse_contract` 抛 "
        "「table anchor 必须是 A1 单元格，实得 None」⇒ 该 entry 的 "
        "`assert_contract_file_matches_source()` 从未能通过。"
        "并发会话已在 registry.py 的 F3 条目注释里独立记录过同一根因，"
        "并把 F3/F4/F5 改成走框架层 `spec_to_contract_sheet_payload`，但没回头修 F1。"
        "另：F1 的 `build_store_projection(store_item_id, payload, *, contract)` 是"
        "**两位置参**形态，与本门 `mod.build_store_projection(rows, contract=...)` 的"
        "调用不兼容（`TypeError: missing 1 required positional argument: 'payload'`）——"
        "即便契约修好，签名也要一起改成单位置参（照 E1）。",
    ),
}


class TestGfP20PerProviderDigestComputable:
    """Validates: 7.1, 7.2（Task 14 之后的形态）"""

    def test_g2_is_registered_in_providers(self, checker) -> None:
        labels = [p[0] for p in checker.PROVIDERS]
        assert "g2" in labels, f"G2 未进零回归门: {labels}"
        row = next(p for p in checker.PROVIDERS if p[0] == "g2")
        assert row[1] == "phase5_g2_interest_receivable", row
        assert row[2] == "ADAPTER_ID", row
        # 🔴 `plural_instr=True`（末位）：注册路径读 instrumentation_specs() 复数，
        #    留 False 会让扩容面对判据不可见（D2 注释警告过的假绿）
        assert row[-1] is True, f"G2 的 plural_instr 必须为 True: {row}"

    def test_every_provider_digest_is_computable_except_registered_blockers(
        self, checker
    ) -> None:
        """逐 provider 现算 digest；只有**已登记**的既存阻塞允许失败。"""
        failures: dict[str, str] = {}
        computed: list[str] = []
        for label, mod_name, const, has_proj, plural in checker.PROVIDERS:
            try:
                got = checker._digests_for(label, mod_name, const, has_proj, plural)
            except Exception as exc:  # noqa: BLE001
                failures[label] = f"{type(exc).__name__}: {exc}"
                continue
            assert got["label"] == label
            assert got["contract_payload_sha256"]
            assert got["instrumentation_sha256"]
            computed.append(label)

        unexpected = {k: v for k, v in failures.items() if k not in KNOWN_PRE_EXISTING_BLOCKERS}
        assert not unexpected, (
            "以下 provider 的 digest 算不出来且**未登记**为既存阻塞:\n"
            + "\n".join(f"  {k}: {v}" for k, v in unexpected.items())
        )
        healed = sorted(set(KNOWN_PRE_EXISTING_BLOCKERS) - set(failures))
        assert not healed, (
            f"以下既存阻塞已修好: {healed} ⇒ 请从 KNOWN_PRE_EXISTING_BLOCKERS 移除，"
            "并跑 `check_sync_provider_golden_digest.py --update` 重建 baseline"
        )
        assert "g2" in computed, "G2 的 digest 算不出来"

    def test_blocker_registry_entries_have_owner_and_substantive_reason(self) -> None:
        """登记项必须有归属 spec + 实质根因（防「暂不处理」式空话登记）。"""
        thin = [
            (label, len(reason))
            for label, (owner, reason) in KNOWN_PRE_EXISTING_BLOCKERS.items()
            if not owner or len(reason) < 60
        ]
        assert not thin, f"登记理由过短或无归属: {thin}"

    def test_baseline_lacks_g2_until_blocker_cleared(self) -> None:
        """现状锚点：baseline 里还没有 g2 —— 因为 `--update` 被 F1 卡住跑不了。

        F1 修好后应跑 `--update`，那时本判据会打红，提示改成「g2 在 baseline 里」。
        """
        doc = json.loads(DIGEST_BASELINE.read_text(encoding="utf-8"))
        labels = [p["label"] for p in doc.get("providers", [])]
        assert "g2" not in labels, (
            "baseline 已含 g2 ⇒ 说明 `--update` 跑通了（F1 阻塞已清）；"
            "请把本判据改成断言 g2 在 baseline 内，并移除 KNOWN_PRE_EXISTING_BLOCKERS"
        )
        # 既有 9 家必须仍在（零回归：加 G2 不得把别人挤掉）
        must_stay = {"b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "e1"}
        missing = sorted(must_stay - set(labels))
        assert not missing, f"baseline 里既有 provider 消失: {missing}"
