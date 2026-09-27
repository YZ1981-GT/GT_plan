# -*- coding: utf-8 -*-
"""K 循环 lane 2 — Task 17~19：roundtrip 二分 + 5 条 contract 草案 + 复盘。

spec: k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub
Task 17: 真库载荷三分与 roundtrip 策略
Task 18: 发 5 条 per-entry contract（`[ ]*` 依赖 BP-1 / BP-2）
Task 19: 复盘与交付边界
Property: KB-P33 ~ KB-P36, KB-P41 ~ KB-P44, KB-P20, KB-P40, KB-P43

═══ 🔴 本组最贵的发现 ═══

**「5 张调整分录汇总与 canary 完全同构 ⇒ 形态判据可直接外推」只对模板层成立。**
前端行身份实测**三种形态**：

| entry | 形态 | 安全性 |
|---|---|---|
| K10（canary） | `e.id ?? `entry-${Date.now()}-${Math.random()…}`` | family_c 安全 |
| K8 / K9 / K11 | `e.id \\|\\| `entry-${++nextId}`` | 🔴 **可碰撞**（本 spec 已修） |
| K12 / K13 | **无身份字段**，靠数组顺序 | 🔴 最弱（本 spec 不改，跨 spec 待办） |

🔴 counter 形态的碰撞是**可复现**的：`nextId` 在 load 后被重置为「当前行数 + 1」
⇒ 删行 → persist → 重新 load 时 counter 回退，新增行拿到已存在的 id。
而且 `${++nextId}` **不被** KC-6 判别式捕获（不匹配 `i|idx|index`）⇒ 从未进过
BP-8 的 48 处基线 —— 与 `${idx++}` 同类的口径盲点，第二次踩到。
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata

import pytest

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    POSITIONAL_INTERP_RX,
    ROOT,
    ROW_IDENTITY_FACTORY,
    cached_text,
    derived_total_keys,
    entry_of_path,
    k_domain_files,
    strip_comments,
)

CONTRACT_DIR = DATA / "workpaper_sync_contracts"
SPEC_DIR = (
    ROOT / ".kiro" / "specs"
    / "k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub"
)

LANE2 = (8, 9, 11, 12, 13)

#: 🔴 真库载荷三分（来源 = design 阶段对真实 PG 的现读，本测试不重连 PG）
LIVE_PAYLOAD = {
    8: {"keys": 1, "bytes": 195_960},
    9: {"keys": 3, "bytes": 15_455},
    12: {"keys": 2, "bytes": 264},
    11: {"keys": 0, "bytes": 0},
    13: {"keys": 0, "bytes": 0},
}
LIVE_TOTAL_KEYS = 6
LIVE_TOTAL_BYTES = 211_679
_LIVE_EVIDENCE_IS_FROM_DESIGN_READ = True

#: 本 lane 的 5 条契约 id
CONTRACT_IDS = {
    8: "k8.selling_expenses_adjustment",
    9: "k9.admin_expenses_adjustment",
    11: "k11.asset_impairment_loss_adjustment",
    12: "k12.non_operating_income_adjustment",
    13: "k13.non_operating_expense_adjustment",
}
CANARY_CONTRACT_ID = "k10.other_income_adjustment"

#: 行身份形态分型（现算锚点）
FIELD_IDENTITY_ENTRIES = (8, 9, 11)
ARRAY_ORDER_ENTRIES = (12, 13)

SYNTHETIC_TAG = "synthetic_payload_no_live_db_baseline"


#: counter 身份形态：`` `prefix-${++var}` ``
COUNTER_IDENTITY_RX = re.compile(r"`[a-zA-Z0-9]+-\$\{\s*\+\+\s*(\w+)\s*\}`")


def _counter_identity_vars(src: str) -> set[str]:
    """所有被用作行身份的自增 counter 变量名。"""
    return {m.group(1) for m in COUNTER_IDENTITY_RX.finditer(src)}


def _collidable_counter_vars(src: str) -> set[str]:
    """🔴 **可碰撞**的 counter：初值是小常量 ∧ load 后被重置为「行数 + 1」。

    重置是碰撞的充分条件 —— counter 回退后，`++` 会重新走到已经发出去的值。
    初值为 `Date.now()` 且无重置的那种单调递增 counter 不在此列。
    """
    out: set[str] = set()
    for var in _counter_identity_vars(src):
        v = re.escape(var)
        const_init = re.search(rf"let\s+{v}\s*=\s*\d+\s*$", src, flags=re.M)
        reset = re.search(rf"(?<![\w$]){v}\s*=\s*\w+(?:\.value)?\.length\s*\+", src)
        if const_init and reset:
            out.add(var)
    return out


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def contracts() -> dict[int, dict]:
    out: dict[int, dict] = {}
    for n, cid in CONTRACT_IDS.items():
        p = CONTRACT_DIR / f"{cid}.candidate.json"
        assert p.exists(), f"契约草案不存在：{p}"
        out[n] = json.loads(p.read_text(encoding="utf-8"))
    return out


@pytest.fixture(scope="module")
def canary_contract() -> dict:
    p = CONTRACT_DIR / f"{CANARY_CONTRACT_ID}.candidate.json"
    assert p.exists(), f"canary 契约不存在：{p}"
    return json.loads(p.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# Task 17 / KB-P33~P36：真库载荷三分与 roundtrip 策略
# ════════════════════════════════════════════════════════════════════════════
class TestKBP33LivePayloadArithmetic:
    """🔴 算术两项都现算裁定：非空键 6 / 载荷 211,679 B。"""

    def test_key_count_sums_to_six(self) -> None:
        total = sum(v["keys"] for v in LIVE_PAYLOAD.values())
        assert total == LIVE_TOTAL_KEYS == 6, (
            f"非空键 1+3+2+0+0 应为 6，实得 {total}"
        )

    def test_bytes_sum_to_211679(self) -> None:
        total = sum(v["bytes"] for v in LIVE_PAYLOAD.values())
        assert total == LIVE_TOTAL_BYTES == 211_679, (
            f"载荷 195,960 + 15,455 + 264 应为 211,679，实得 {total}"
        )

    def test_evidence_source_is_declared_not_reread(self) -> None:
        """🔴 诚实标注：本组数字是 design 阶段真库现读的留档，非本测试连 PG。"""
        assert _LIVE_EVIDENCE_IS_FROM_DESIGN_READ is True

    def test_numbers_are_traceable_to_design(self) -> None:
        design = (SPEC_DIR / "design.md").read_text(encoding="utf-8")
        for token in ("211,679", "195,960", "15,455"):
            assert token in design, f"design.md 里找不到 {token} ⇒ 来源不可追溯"

    def test_k8_dominates_the_payload(self) -> None:
        """K8 单键占 92.6% ⇒ 「大载荷与空载荷并存」的形态成立。"""
        share = LIVE_PAYLOAD[8]["bytes"] / LIVE_TOTAL_BYTES
        assert share > 0.9, f"K8 占比 {share:.1%}"


class TestKBP34RoundtripBisection:
    """roundtrip 策略按载荷二分，逐条落进契约。"""

    def test_k8_uses_live_db_for_amount_dimension(
        self, contracts: dict[int, dict]
    ) -> None:
        ev = contracts[8]["review"]["roundtrip_evidence"]
        assert ev["strategy"] == "live_db_full"
        assert "无须合成" in ev["note"]

    def test_k9_structure_only_because_amounts_are_zero(
        self, contracts: dict[int, dict]
    ) -> None:
        """🔴 K9 有真库载荷但金额全 0 ⇒ 金额维度仍须合成。"""
        ev = contracts[9]["review"]["roundtrip_evidence"]
        assert ev["strategy"] == "live_db_structure_only"
        assert "全 0" in ev["note"]
        assert "骨架已落库业务未填" in ev["note"]

    def test_k12_two_byte_payload_is_not_valid(
        self, contracts: dict[int, dict]
    ) -> None:
        """🔴 `K12-4-check-rows` 只 2 B（空数组）⇒ 不是有效载荷。"""
        ev = contracts[12]["review"]["roundtrip_evidence"]
        assert ev["strategy"] == "structure_only"
        assert "2 B" in ev["note"]
        assert "不是有效载荷" in ev["note"]

    @pytest.mark.parametrize("n", (11, 13))
    def test_zero_row_entries_use_synthetic_and_say_so(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """🔴 K11 / K13 真库 0 行 ⇒ 合成载荷 + 标 tag + 不得宣称真库实证。"""
        assert LIVE_PAYLOAD[n]["keys"] == 0
        ev = contracts[n]["review"]["roundtrip_evidence"]
        assert ev["strategy"] == "synthetic"
        assert SYNTHETIC_TAG in ev["note"]
        assert "不得宣称" in ev["note"]

    def test_no_entry_claims_live_evidence_without_payload(
        self, contracts: dict[int, dict]
    ) -> None:
        """🔴 守卫：0 载荷的 entry 不许出现 `live_db` 策略。"""
        for n, doc in contracts.items():
            strategy = doc["review"]["roundtrip_evidence"]["strategy"]
            if LIVE_PAYLOAD[n]["keys"] == 0:
                assert "live_db" not in strategy, (
                    f"K{n} 真库 0 键却标 {strategy}"
                )
            if strategy.startswith("live_db"):
                assert LIVE_PAYLOAD[n]["keys"] > 0, f"K{n} 无载荷却标 {strategy}"


class TestKBP35K9IdentityIsTheGrandfatherEvidence:
    """🔴 `K9-1-rows` 的真库行身份是 grandfather 的直接实证。"""

    K9_LIVE_ROW_KEY = "row-jil2dvsb"

    def test_shape_is_pure_random_base36(self) -> None:
        """`row-{8位base36}` —— 既非位置化也非本 lane 新工厂形态。"""
        m = re.fullmatch(r"row-([0-9a-z]{8})", self.K9_LIVE_ROW_KEY)
        assert m is not None, f"形态不符：{self.K9_LIVE_ROW_KEY}"
        assert not m.group(1).isdigit(), "全数字 ⇒ 可能是序号不是 base36"

    def test_it_is_neither_positional_nor_the_new_factory_shape(self) -> None:
        assert POSITIONAL_INTERP_RX.search(self.K9_LIVE_ROW_KEY) is None
        # 新工厂产 `prefix-{13位ts}-{rand}`，三段；真库这条只两段
        assert len(self.K9_LIVE_ROW_KEY.split("-")) == 2

    def test_why_grandfather_matters(self, contracts: dict[int, dict]) -> None:
        """🔴 若重写已落库 id，这类身份会全变 ⇒ 契约须写明 grandfather。"""
        note = contracts[9]["review"]["roundtrip_evidence"]["note"]
        assert "grandfather" in note
        assert self.K9_LIVE_ROW_KEY in note

    def test_traceable_to_design(self) -> None:
        design = (SPEC_DIR / "design.md").read_text(encoding="utf-8")
        assert self.K9_LIVE_ROW_KEY in design


class TestKBP36ExcludedNamespaces:
    """K12 的 review-session 按 KC-5 排除。"""

    def test_k12_excludes_review_session(self, contracts: dict[int, dict]) -> None:
        exc = contracts[12]["review"]["excluded_namespaces"]
        assert "review_session" in exc
        rs = exc["review_session"]
        assert rs["keys_pattern"] == "K12-review-session-{时间戳}"
        assert rs["live_bytes"] == 262
        assert "KC-5" in rs["why"]

    def test_every_contract_excludes_ai_section_id(
        self, contracts: dict[int, dict]
    ) -> None:
        """AI section-id 是 KC-5 三命名空间外的第四类（canary 契约补的）。"""
        for n, doc in contracts.items():
            exc = doc["review"]["excluded_namespaces"]
            assert "ai_section_id" in exc, f"K{n} 未排除 ai_section_id"
            assert exc["ai_section_id"]["keys"] == [f"K{n}-3-adjustment"]

    def test_publish_flag_excluded_where_it_exists(
        self, contracts: dict[int, dict], k_files: list[pathlib.Path]
    ) -> None:
        """🔴 `K{n}-3-published` 只 K12/K13 有 ⇒ 排除清单按现算分型。"""
        for n in LANE2:
            live = any(
                f"K{n}-3-published" in strip_comments(cached_text(p))
                for p in k_files
                if entry_of_path(p) == n
            )
            declared = "publish_flag" in contracts[n]["review"]["excluded_namespaces"]
            assert declared == live, (
                f"K{n}: 契约标 {declared} 但现算 {live}"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 18 / KB-P43：5 条 per-entry contract 草案
# ════════════════════════════════════════════════════════════════════════════
class TestKBP43ContractDraftsAreCandidateOnly:
    """🔴 只发 candidate 草案（依赖 BP-1 / BP-2）。"""

    def test_five_drafts_exist(self, contracts: dict[int, dict]) -> None:
        assert set(contracts) == set(LANE2)

    @pytest.mark.parametrize("n", LANE2)
    def test_entry_id_is_null(self, n: int, contracts: dict[int, dict]) -> None:
        """🔴 `review.entry_id` **必须 null**（否则打破 test_task53 两条判据）。"""
        review = contracts[n]["review"]
        assert review["entry_id"] is None, (
            f"K{n} 的 entry_id 非 null ⇒ test_task53 会红"
        )
        assert review["draft_target_entry_id"].startswith("xlsx/gt-k")
        assert "test_task53" in review["why_entry_id_is_null"]

    @pytest.mark.parametrize("n", LANE2)
    def test_status_is_candidate_with_reason(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        doc = contracts[n]
        assert doc["review_status"] == "candidate"
        why = doc["review"]["why_candidate_not_reviewed"]
        assert "BP-1" in why and "BP-2" in why
        assert "[ ]*" in why

    def test_no_lane2_contract_claims_an_entry(
        self, contracts: dict[int, dict]
    ) -> None:
        """两侧都验：全仓契约里没有一条把 entry_id 指向本 lane 的 5 条 entry。"""
        targets = {contracts[n]["review"]["draft_target_entry_id"] for n in LANE2}
        for p in CONTRACT_DIR.glob("*.json"):
            doc = json.loads(p.read_text(encoding="utf-8"))
            eid = (doc.get("review") or {}).get("entry_id")
            assert eid not in targets, (
                f"{p.name} 的 entry_id 指向本 lane 的 {eid} ⇒ 越界发了生产契约"
            )

    @pytest.mark.parametrize("n", LANE2)
    def test_nine_fields_map_the_ten_column_sheet(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """10 列里 9 列映射字段，F 列是占位（表头 `……`）。"""
        table = contracts[n]["sheets"][0]["tables"][0]
        assert len(table["fields"]) == 9
        cols = {f["cell"]["column"] for f in table["fields"]}
        assert cols == set("ABCDEGHIJ"), cols
        assert "F" not in cols
        only = contracts[n]["review"]["template_only_columns"]
        assert only[0]["column"] == "F" and only[0]["header_text"] == "……"

    @pytest.mark.parametrize("n", LANE2)
    def test_template_sha256_matches_the_real_book(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """🔴 契约里的 sha256 与真实模板逐字节等值（不是抄的）。"""
        import hashlib

        rel = contracts[n]["template"]["relative_path"]
        book = ROOT / "backend" / "wp_templates" / rel
        assert book.exists(), f"模板不存在：{book}"
        actual = hashlib.sha256(book.read_bytes()).hexdigest()
        assert contracts[n]["template"]["template_sha256"] == actual

    @pytest.mark.parametrize("n", LANE2)
    def test_four_tuple_of_row_delete_api(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """`row_delete_api_kind` 四元组齐（KC-7）。"""
        rd = contracts[n]["review"]["row_delete_api_kind"]
        assert set(rd) == {"arity", "kind", "param_name_family", "param_order"}
        assert rd["arity"] == len(rd["param_order"])

    def test_derived_total_infix_keys_match_live(
        self, contracts: dict[int, dict], k_files: list[pathlib.Path]
    ) -> None:
        """🔴 3 个仅中置命中键逐条落进对应契约。"""
        infix = derived_total_keys(k_files, include_infix=True) - derived_total_keys(
            k_files, include_infix=False
        )
        declared: set[str] = set()
        for n in LANE2:
            keys = contracts[n]["review"]["derived_total_infix_keys"]
            for k in keys:
                assert k in infix, f"K{n} 声明的 {k} 不在现算仅中置集里"
                assert k.startswith(f"K{n}-"), f"{k} 不属 K{n}"
            declared |= set(keys)
        assert len(declared) == 3, f"本 lane 仅中置键应 3 个，实得 {sorted(declared)}"

    def test_k11_carries_the_frozen_key_reference(
        self, contracts: dict[int, dict]
    ) -> None:
        """🔴 K11 契约须指向冻结清单（9 键，跨循环枢纽）。"""
        fz = contracts[11]["review"]["frozen_cross_cycle_keys"]
        assert fz["count"] == 9
        src = ROOT / fz["source_of_truth"]
        assert src.exists(), f"冻结清单不存在：{src}"
        doc = json.loads(src.read_text(encoding="utf-8"))
        assert len(doc["frozen_keys"]) == fz["count"]
        assert "KC-8" in fz["why"]

    def test_only_k11_has_frozen_keys(self, contracts: dict[int, dict]) -> None:
        """两侧都验：其余 4 条无冻结键（K11 是唯一枢纽）。"""
        for n in LANE2:
            has = "frozen_cross_cycle_keys" in contracts[n]["review"]
            assert has == (n == 11), f"K{n} 冻结键字段 {has}"


class TestKBP43CanaryExtrapolationIsTemplateOnly:
    """🔴 本组核心裁定：canary 形态判据只能外推**模板层**。"""

    @pytest.mark.parametrize("n", LANE2)
    def test_template_fingerprint_matches_canary(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        iso = contracts[n]["review"]["isomorphic_to_canary"]
        assert iso["canary_sheet"] == "调整分录汇总K10-3"
        assert iso["template_fingerprint"] == {
            "effective_columns": 10,
            "formula_cells": 7,
            "bare_if": 0,
            "merged_ranges": 3,
        }

    @pytest.mark.parametrize("n", LANE2)
    def test_caveat_says_identity_is_not_isomorphic(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """🔴 必须写明「模板层同构 ≠ 前端身份机制同构」+ 三种形态。"""
        caveat = contracts[n]["review"]["isomorphic_to_canary"]["🔴 caveat"]
        assert "模板层同构 ≠ 前端身份机制同构" in caveat
        assert "三种形态" in caveat
        for token in ("K10", "K8/K9/K11", "K12/K13"):
            assert token in caveat, f"caveat 未点名 {token}"

    def test_canary_uses_the_safe_family_c_shape(
        self, canary_contract: dict, k_files: list[pathlib.Path]
    ) -> None:
        """两侧都验：canary 的身份确实是 family_c（对照成立）。"""
        ri = canary_contract["sheets"][0]["tables"][0]["row_identity"]
        assert ri["family"] == "c"
        host = next(x for x in k_files if x.name == "K10TabAdjustment.vue")
        src = strip_comments(cached_text(host))
        assert re.search(r"Date\.now\(\).*Math\.random\(\)", src), (
            "K10 宿主已无带熵身份 ⇒ 对照基础变了"
        )

    @pytest.mark.parametrize("n", FIELD_IDENTITY_ENTRIES)
    def test_field_identity_entries_now_use_the_shared_factory(
        self, n: int, contracts: dict[int, dict], k_files: list[pathlib.Path]
    ) -> None:
        """🔴 K8/K9/K11 已修：counter 清零 + 走统一工厂 + grandfather 保留。"""
        ri = contracts[n]["sheets"][0]["tables"][0]["row_identity"]
        assert ri["kind"] == "field" and ri["family"] == "c"
        host = next(x for x in k_files if x.name == f"K{n}TabAdjustment.vue")
        src = strip_comments(cached_text(host))
        assert "nextId" not in src, f"K{n} 仍有 nextId ⇒ counter 未清"
        assert re.search(
            r"e\.id\s*\|\|\s*" + ROW_IDENTITY_FACTORY, src
        ), f"K{n} 的 grandfather 兜底未走统一工厂"

    @pytest.mark.parametrize("n", ARRAY_ORDER_ENTRIES)
    def test_array_order_entries_declare_the_risk(
        self, n: int, contracts: dict[int, dict]
    ) -> None:
        """🔴 K12/K13 无身份字段 ⇒ 契约标 risk + 写明为何本 lane 不改。"""
        ri = contracts[n]["sheets"][0]["tables"][0]["row_identity"]
        assert ri["kind"] == "array_order"
        assert ri["risk"] == "positional_row_identity_without_field"
        why = ri["why_not_field"]
        assert "本 lane 不改它" in why
        assert "后端导入导出" in why or "IE 契约" in why
        assert "跨 spec 待办" in why

    def test_counter_shape_escaped_the_discriminator(self) -> None:
        """🔴 口径盲点登记：`${++nextId}` 不被 KC-6 判别式捕获。

        与 Task 13 的 `${idx++}` 同类 —— 这是第二次踩到同一类盲点：
        判别式只认 `i|idx|index` 这三个**名字**，换个变量名（`nextId`）或
        换个写法（`++x` / `x++`）就漏掉。
        """
        assert POSITIONAL_INTERP_RX.search("`entry-${++nextId}`") is None
        assert POSITIONAL_INTERP_RX.search("`entry-${idx}`") is not None

    def test_no_collidable_counter_identity_remains_in_lane2(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 本 lane 已无**可碰撞**的 counter 身份。

        🔴 两种 counter 形态的危害等级**不同**，判据必须按两要素分型：

        | 形态 | 初值 | load 后重置 | 危害 |
        |---|---|---|---|
        | 危险 | `let nextId = 1` | ✅ `= entries.length + 1` | 🔴 counter 回退 ⇒ 撞已存 id |
        | 安全 | `let rowIdCounter = Date.now()` | ❌ 无 | 等价 family_c（起点带熵 + 单调） |

        只按 `${++x}` 正则扫会把 K12/K13 那 4 处**安全**形态一起判红。
        """
        for p in k_files:
            if entry_of_path(p) not in LANE2:
                continue
            for var in _collidable_counter_vars(strip_comments(cached_text(p))):
                pytest.fail(f"{p.name} 的 `{var}` 是可碰撞 counter 身份")

    def test_safe_counter_form_is_recognized_not_flagged(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两侧都验：K12/K13 的 4 处 `Date.now()` 起点 counter **是安全的**。"""
        safe_hosts: dict[str, list[str]] = {}
        for p in k_files:
            if entry_of_path(p) not in LANE2:
                continue
            src = strip_comments(cached_text(p))
            for var in _counter_identity_vars(src):
                if var in _collidable_counter_vars(src):
                    continue
                assert re.search(
                    rf"let\s+{re.escape(var)}\s*=\s*Date\.now\(\)", src
                ), f"{p.name} 的 `{var}` 既非 Date.now() 起点也不算可碰撞 ⇒ 分型漏了"
                safe_hosts.setdefault(p.name, []).append(var)
        assert len(safe_hosts) == 4, (
            f"安全 counter 宿主期望 4 个，实得 {sorted(safe_hosts)}"
        )
        assert all(
            n.startswith(("K12", "K13")) for n in safe_hosts
        ), f"安全 counter 出现在 K12/K13 之外：{sorted(safe_hosts)}"

    def test_collidable_form_still_exists_in_lane1(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 反向对照：lane 1 的 5 个 TabAdjustment **仍是**可碰撞形态。

        这条既是「本 lane 没越界改」的正向证明，也是留给 lane 1 的待办清单
        —— 同一个 bug 在 K2/K3/K4/K6/K7 各有一份。
        """
        hosts: set[str] = set()
        for p in k_files:
            if entry_of_path(p) not in (1, 2, 3, 4, 5, 6, 7):
                continue
            if _collidable_counter_vars(strip_comments(cached_text(p))):
                hosts.add(p.name)
        assert hosts == {
            f"K{n}TabAdjustment.vue" for n in (2, 3, 4, 6, 7)
        }, f"lane 1 可碰撞宿主 {sorted(hosts)}"


# ════════════════════════════════════════════════════════════════════════════
# Task 19 / KB-P41~P44：复盘与交付边界
# ════════════════════════════════════════════════════════════════════════════
class TestKBP41BlockersDoNotBlockTheFiveMainThings:
    """🔴 BP-1 / BP-2 / BP-3 对本 lane 的五件主线事都不是阻塞。"""

    #: 本 lane 的五件主线事（各有已交付的判据文件）
    FIVE_MAIN_THINGS = {
        "BP-6 收口（health 单源 + localStorage 统一键 + notice）":
            "test_k_lane2_p0_boundary_and_endpoints.py",
        "KC-8 跨循环枢纽 K11 的 9 键冻结":
            "test_k_lane2_p1_cross_cycle_hub.py",
        "BP-8 位置化行身份修复":
            "test_k_lane2_p2_positional_identity.py",
        "变体轴口径 + 模板层基线 + 写路径收口":
            "test_k_lane2_p3_variants_template_writepaths.py",
        "roundtrip 二分 + 契约草案":
            "test_k_lane2_p4_roundtrip_contracts_closeout.py",
    }

    def test_all_five_have_delivered_guards(self) -> None:
        here = pathlib.Path(__file__).parent
        for thing, guard in self.FIVE_MAIN_THINGS.items():
            p = here / guard
            assert p.exists(), f"「{thing}」的判据文件缺失：{guard}"
            assert p.stat().st_size > 2000, f"{guard} 过小 ⇒ 疑似空壳"

    def test_blockers_only_gate_contract_adapter_evidence(self) -> None:
        """🔴 三个阻塞项只卡「发 contract / 注册 adapter / 产 evidence」。"""
        tasks = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
        i = tasks.find("## 阻塞项归属表")
        assert i > 0, "tasks.md 缺阻塞项归属表"
        seg = tasks[i : i + 900]
        assert "BP-1 / BP-2 / BP-3" in seg
        assert "五件主线事都不是阻塞" in seg
        for kw in ("contract", "adapter", "evidence"):
            assert kw in seg, f"归属表未点名 {kw}"

    def test_contracts_are_the_only_starred_deliverable(
        self, contracts: dict[int, dict]
    ) -> None:
        """两侧都验：被卡住的确实只有契约（全 5 条 candidate 未 reviewed）。"""
        assert all(
            d["review_status"] == "candidate" for d in contracts.values()
        )

    def test_bp4_and_bp5_are_not_in_this_lane(self) -> None:
        """🔴 BP-4（只 K1）与 BP-5（K1~K7）都不落本 lane。"""
        tasks = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
        i = tasks.find("## 阻塞项归属表")
        seg = tasks[i : i + 1400]
        for bp in ("BP-4", "BP-5"):
            m = re.search(rf"\|\s*\*{{0,2}}{bp}\*{{0,2}}\s*\|([^|]*)\|", seg)
            assert m is not None, f"归属表缺 {bp} 行"
            assert "不落本 lane" in m.group(1), f"{bp} 行未写明不落本 lane"

    def test_lane2_produces_no_canary(self) -> None:
        """🔴 本 lane 不产 canary，但与 foundation canary 同属 BP-6 组。"""
        tasks = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
        assert "本 lane 不产 canary" in tasks
        i = tasks.find("| **BP-6** |")
        assert i > 0
        assert "本 lane 交付 5 条" in tasks[i : i + 200]

    def test_this_lane_has_a_canary_advantage_over_lane1(self) -> None:
        """🔴 本 lane 相对 lane 1 的优势：BP-6 组有 canary 覆盖，BP-5 组没有。"""
        tasks = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
        assert "lane 1 的 BP-5 形态完全无 canary 覆盖" in tasks


class TestKBP42SpecReferencesOnlyNeverRestates:
    """🔴 脚本核验：本 spec 只**引用** KC 编号、零复述正文。"""

    #: foundation design 里 KC 条目的标题（复述这些就是第二真源）
    @staticmethod
    def _foundation_kc_titles() -> dict[str, str]:
        fd = (
            ROOT / ".kiro" / "specs" / "k-cycle-sync-foundation-and-first-canary"
            / "design.md"
        ).read_text(encoding="utf-8")
        out: dict[str, str] = {}
        for m in re.finditer(r"^#{2,4}\s*(KC-\d+)\s+(.+)$", fd, flags=re.M):
            out[m.group(1)] = m.group(2).strip()
        return out

    def test_foundation_has_kc_catalog(self) -> None:
        titles = self._foundation_kc_titles()
        assert len(titles) >= 20, f"KC 条目只找到 {len(titles)} 条"

    def test_lane2_spec_cites_kc_numbers(self) -> None:
        blob = "\n".join(
            (SPEC_DIR / n).read_text(encoding="utf-8")
            for n in ("requirements.md", "design.md", "tasks.md")
        )
        cited = set(re.findall(r"KC-\d+", blob))
        assert len(cited) >= 8, f"只引用了 {sorted(cited)} ⇒ 复用不足"

    def test_lane2_spec_does_not_restate_kc_bodies(self) -> None:
        """🔴 判据：不得出现 `#### KC-n <标题>` 这种把 foundation 正文搬过来的段。"""
        offenders: list[str] = []
        for n in ("requirements.md", "design.md", "tasks.md"):
            text = (SPEC_DIR / n).read_text(encoding="utf-8")
            for m in re.finditer(r"^#{2,4}\s*(KC-\d+)\s+\S+", text, flags=re.M):
                offenders.append(f"{n}: {m.group(0).strip()}")
        assert offenders == [], f"复述了 KC 正文标题：{offenders}"


class TestKBP44PropertyNumberingIsClean:
    """🔴 `KB-P1` ~ `KB-P44` 无重号无缺号；无 U+FFFD。"""

    @staticmethod
    def _declared_properties() -> list[int]:
        design = (SPEC_DIR / "design.md").read_text(encoding="utf-8")
        i = design.find("| KB-P1 ")
        assert i > 0, "design.md 找不到 Property 表"
        return [
            int(m.group(1))
            for m in re.finditer(r"^\|\s*(?:\*\*)?KB-P(\d+)", design[i - 400:], flags=re.M)
        ]

    def test_no_duplicates(self) -> None:
        nums = self._declared_properties()
        dupes = {n for n in nums if nums.count(n) > 1}
        assert dupes == set(), f"重号：{sorted(dupes)}"

    def test_no_gaps_from_1_to_44(self) -> None:
        nums = set(self._declared_properties())
        assert nums, "Property 表为空"
        top = max(nums)
        assert top == 44, f"最大编号 {top} ⇒ 期望 44"
        missing = set(range(1, top + 1)) - nums
        assert missing == set(), f"缺号：{sorted(missing)}"

    def test_every_property_is_cited_by_a_task(self) -> None:
        """🔴 每条 Property 都被至少一个 Task 的 `_Property:` 行引用。"""
        tasks = (SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
        cited = {int(m.group(1)) for m in re.finditer(r"KB-P(\d+)", tasks)}
        declared = set(self._declared_properties())
        orphan = declared - cited
        assert orphan == set(), f"这些 Property 没被任何 Task 引用：{sorted(orphan)}"

    @pytest.mark.parametrize("name", ("requirements.md", "design.md", "tasks.md"))
    def test_no_replacement_character(self, name: str) -> None:
        text = (SPEC_DIR / name).read_text(encoding="utf-8")
        assert "\ufffd" not in text, f"{name} 含 U+FFFD（编码损坏）"

    @pytest.mark.parametrize("name", ("requirements.md", "design.md", "tasks.md"))
    def test_no_unassigned_or_surrogate_codepoints(self, name: str) -> None:
        text = (SPEC_DIR / name).read_text(encoding="utf-8")
        bad = [
            (i, ch)
            for i, ch in enumerate(text)
            if unicodedata.category(ch) in ("Cs", "Cn")
        ]
        assert bad == [], f"{name} 含未分配/代理码点：{bad[:5]}"

    def test_contract_files_have_no_replacement_character(
        self, contracts: dict[int, dict]
    ) -> None:
        for n, cid in CONTRACT_IDS.items():
            raw = (CONTRACT_DIR / f"{cid}.candidate.json").read_text(
                encoding="utf-8"
            )
            assert "\ufffd" not in raw, f"K{n} 契约含 U+FFFD"


class TestLane2DeliveryBoundary:
    """交付边界一览（可复算的自检清单）。"""

    def test_five_entries_all_have_a_draft(self, contracts: dict[int, dict]) -> None:
        assert len(contracts) == 5

    def test_all_guard_files_present_and_nonempty(self) -> None:
        here = pathlib.Path(__file__).parent
        files = sorted(here.glob("test_k_lane2_p*.py"))
        assert len(files) == 5, f"lane 2 判据文件应 5 个，实得 {[f.name for f in files]}"
        for f in files:
            assert f.stat().st_size > 2000

    def test_no_one_off_scripts_left_behind(self) -> None:
        """🔴 一次性脚本用完即删（`_` 前缀）。"""
        leftovers = sorted(
            p.name
            for p in (ROOT / "backend" / "scripts").glob("_k2_*.py")
        )
        assert leftovers == [], f"残留一次性脚本：{leftovers}"
