"""契约字段 `row_convergence`：默认与分流 / 开启前提 / 覆盖面普查。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 16.1 · 16.2 · 16.3 · 16.4
Requirements: 8.1 ~ 8.5

═══ 这个键为什么必须存在 ═══

删物理行是**不可逆的数据丢失**，且要求本表的全部工作簿级引用（definedName / 跨 sheet 公式 /
兄弟 Table ref / `_GT_SYNC` 冻结值 / 结构块）都已接上声明。这些前提是**逐表**核验的事实，
不是全平台一致的事实 ⇒ 开关必须逐表给，默认关。

🔴 判据的重点不在「键能解析」，而在三件事：
① **未声明即 `clear`** —— 全部既有契约的语义一个字都不变（Requirement 8.2 / 8.5）；
② **开启前提齐备** —— 缺行身份或删除策略一律拒（Requirement 8.3），且要证明这条判据
   **不是** CS-14 的重复（否则它可以整条删掉而测试仍绿）；
③ **默认值本身**被钉死 —— 改 dataclass 默认值会让全部契约在一次部署里同时开始删行。
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402

# 🔴 复用**既有**的合法 xlsx 契约构造件（动态行 + 两级表头 + formula mask + footer +
#    动态列 + row_identity + delete_policy 全齐），不在本文件另造一份 payload：
#    另造一份就会与解析器的真实要求漂移，而漂移的症状是「判据在自己造的 payload 上绿」。
from test_task13_contract_registry import (  # noqa: E402
    first_table,
    xlsx_payload,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Property 17：契约门控的默认与分流
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty17GateDefaultAndDispatch:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 17: 契约门控的默认与分流**

    **Validates: Requirements 8.1, 8.2, 8.4**
    """

    def test_unspecified_defaults_to_clear(self) -> None:
        """🔴 未声明 ⇒ `clear`。这条是「既有契约逐字不变」的全部依据。"""
        payload = xlsx_payload()
        assert "row_convergence" not in first_table(payload), (
            "构造件里已经写了这个键 ⇒ 本条测的就不是「未声明」了"
        )
        table = C.parse_contract(payload).sheets[0].tables[0]
        assert table.row_convergence is C.RowConvergenceMode.clear
        assert table.deletes_physical_rows is False

    @pytest.mark.parametrize(
        ("declared", "expected", "deletes"),
        [
            ("clear", C.RowConvergenceMode.clear, False),
            ("delete", C.RowConvergenceMode.delete, True),
        ],
    )
    def test_declared_value_round_trips(
        self, declared: str, expected: C.RowConvergenceMode, deletes: bool
    ) -> None:
        payload = xlsx_payload()
        first_table(payload)["row_convergence"] = declared
        table = C.parse_contract(payload).sheets[0].tables[0]
        assert table.row_convergence is expected
        assert table.deletes_physical_rows is deletes

    @pytest.mark.parametrize("bad", ["Delete", "remove", "", "tombstone", None, 1, True])
    def test_unknown_value_is_a_closed_enum(self, bad: Any) -> None:
        """🔴 闭枚举：拼错的值必须抛，不得静默落到默认值上。

        `"tombstone"` 是刻意放进来的 —— 它是 `DeletePolicy` 的合法值。两个键的值域
        混用时必须打红，否则「本以为开了删行、实际落到 clear」会静默发生。
        `None` 与 `""` 也在里面：前者在解析器里走「未声明」分支（应得默认值），
        后者是真的非法值 ⇒ 两者行为**必须不同**，本参数化把这个区别钉住。
        """
        payload = xlsx_payload()
        first_table(payload)["row_convergence"] = bad
        if bad is None:
            # `None` 等同未声明（`raw.get(...) is not None` 分支）⇒ 取默认
            table = C.parse_contract(payload).sheets[0].tables[0]
            assert table.row_convergence is C.RowConvergenceMode.clear
            return
        with pytest.raises(C.ContractSchemaError, match="row_convergence"):
            C.parse_contract(payload)

    def test_dataclass_default_is_pinned(self) -> None:
        """🔴 钉死 dataclass 默认值本身。

        改它 = 全部既有契约在一次部署里同时开始删物理行。这条判据不看解析结果、
        直接看**字段声明**，于是「把默认值改了但某个 payload 恰好显式声明了 clear」
        这种局部掩盖不会让它变绿。
        """
        field = next(
            f for f in dataclasses.fields(C.TableSpec) if f.name == "row_convergence"
        )
        assert field.default is C.RowConvergenceMode.clear, (
            f"`TableSpec.row_convergence` 的默认值变成了 {field.default!r} —— "
            "默认必须是 clear（Requirement 8.2）"
        )

    def test_enum_value_domain_is_exactly_two(self) -> None:
        assert {m.value for m in C.RowConvergenceMode} == {"clear", "delete"}

    def test_dispatch_goes_through_a_single_property(self) -> None:
        """🔴 分流入口单一：`deletes_physical_rows` 是唯一判定点。

        分流会在 planner / apply 纵深防御 / 判据多处发生；各处自己写
        `spec.row_convergence is RowConvergenceMode.delete` 就会漂（漏一处 = 一处
        静默按 clear 走或反之）。这里断言属性存在且与枚举**两个方向**都一致。
        """
        assert isinstance(
            C.TableSpec.deletes_physical_rows, property
        ), "`deletes_physical_rows` 不是 property ⇒ 分流入口没收口"
        payload = xlsx_payload()
        for declared, expected in (("clear", False), ("delete", True)):
            first_table(payload)["row_convergence"] = declared
            table = C.parse_contract(payload).sheets[0].tables[0]
            assert table.deletes_physical_rows is expected


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 18：开启删行必须同时具备行身份与删除策略
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty18DeleteNeedsIdentityAndPolicy:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 18: 开启删行必须同时具备行身份与删除策略**

    **Validates: Requirement 8.3**
    """

    #: 🔴 构造件的 `tables[0]` 是**动态行**表（row_identity + delete_policy 全齐），
    #: `tables[1]` 是**静态**表（两者都没有）。要测「两个前提都缺」就用后者 ——
    #: 首版试图从 tables[0] 上把动态声明摘掉，但它的字段**全是行域**的
    #: （pointer 带 `{row_uuid}`），摘完一个字段都不剩，当场打红。
    #: 用既有的静态表比改造动态表更接近真实形态，也不用碰 CS-9。
    STATIC_TABLE_INDEX = 1

    def _static_table(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload["sheets"][0]["tables"][self.STATIC_TABLE_INDEX]

    def test_static_table_without_the_key_still_parses(self) -> None:
        """🔴 非空转前提：静态表（两个前提都缺）**不声明** `row_convergence` 是合法的。

        这条是下一条的对照组 —— 它证明「两个键都缺」本身并不违法，
        于是下一条打红的原因只能是 CS-21。
        """
        payload = xlsx_payload()
        raw = self._static_table(payload)
        assert "row_identity" not in raw and "delete_policy" not in raw, (
            f"tables[{self.STATIC_TABLE_INDEX}] 不再是静态表：{sorted(raw)}"
        )
        table = C.parse_contract(payload).sheets[0].tables[self.STATIC_TABLE_INDEX]
        assert table.row_identity is None
        assert table.delete_policy is None
        assert table.row_convergence is C.RowConvergenceMode.clear

    def test_delete_without_identity_and_policy_is_rejected(self) -> None:
        """🔴 CS-21 主判据：`delete` + 两个前提都缺 ⇒ 抛，且错误文案点名两者。

        这也是 CS-21 **不与 CS-14 重复**的证明：CS-14 只在「有 row_identity 而缺
        delete_policy」时说话，两者都缺时它一句话都不说（上一条已实证那种 payload
        合法）⇒ 拦住这个组合的只能是 CS-21。
        """
        payload = xlsx_payload()
        self._static_table(payload)["row_convergence"] = "delete"
        with pytest.raises(C.ContractSchemaError) as err:
            C.parse_contract(payload)
        text = str(err.value)
        assert "row_identity" in text and "delete_policy" in text, text
        assert "CS-21" in text, f"错误文案没点名规则编号，归因要翻代码：{text}"

    def test_delete_with_identity_but_no_policy_is_rejected_by_cs14(self) -> None:
        """有 row_identity 而缺 delete_policy ⇒ 仍然拒（由 **CS-14** 先拦）。

        归因写清楚是哪条规则说的话：两条规则的覆盖面**相邻但不相等**。
        """
        payload = xlsx_payload()
        first_table(payload).pop("delete_policy")
        first_table(payload)["row_convergence"] = "delete"
        with pytest.raises(C.ContractSchemaError, match="delete_policy"):
            C.parse_contract(payload)

    def test_delete_with_reject_policy_is_self_contradictory(self) -> None:
        """🔴 `delete_policy=reject` + `row_convergence=delete` 直接矛盾 ⇒ 抛。

        前者说「一行都不许删」，后者说「删物理行」。两个键同时声明必须自洽 ——
        不拦的话运行时要在两个声明里挑一个，而挑哪个都是猜。
        """
        payload = xlsx_payload()
        first_table(payload)["delete_policy"] = "reject"
        first_table(payload)["row_convergence"] = "delete"
        with pytest.raises(C.ContractSchemaError, match="矛盾"):
            C.parse_contract(payload)

    def test_delete_with_tombstone_and_identity_is_accepted(self) -> None:
        """🔴 正面：前提齐备时**必须放行**。

        只有反面判据的话，「把 CS-21 写成无条件抛」也是全绿的。
        """
        payload = xlsx_payload()
        assert first_table(payload)["delete_policy"] == "tombstone", (
            f"构造件的 delete_policy 变了：{first_table(payload).get('delete_policy')}"
        )
        first_table(payload)["row_convergence"] = "delete"
        table = C.parse_contract(payload).sheets[0].tables[0]
        assert table.deletes_physical_rows is True
        assert table.row_identity is not None
        assert table.delete_policy is C.DeletePolicy.tombstone

    def test_cs21_is_registered_in_the_rule_table(self) -> None:
        """🔴 规则表是 CS 判据的真源 —— 新规则必须登记进去，否则下一个人看不到它。"""
        doc = C.__doc__ or ""
        assert "CS-21" in doc, "模块头的 CS 规则表里没有 CS-21"
        assert "row_convergence" in doc, "规则表里没写这条规则管的是哪个键"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Task 16.4 覆盖面普查：全部既有契约解析后均为 clear
# ═══════════════════════════════════════════════════════════════════════════

#: 允许解析失败的**已知类**。每一项都必须能被错误文案验证，不是「随便失败都放过」。
#:
#: 🔴 这不是豁免名单而是**分类**：普查的问题是「既有契约会不会因为这个新键而变化」，
#: 而本来就解析不了的文件（generator 候选 / 非契约的映射文件）根本进不了生产，
#: 它们的 `row_convergence` 无从谈起。分类 + 计数对齐让「哪天有文件从可解析变成不可解析」
#: 立刻可见。
KNOWN_UNPARSEABLE_REASONS: dict[str, str] = {
    "review_status": "generator 候选（CS-1：未经人工审核不得注册生产）",
    "template_definition_sha256": "candidate 契约尚未单向引用已发布 definition",
    "schema_version": "不是契约文件（L 循环位置键映射表，无 schema_version）",
}


#: 已**授权开启物理删行**的表 → 开表依据。
#:
#: 🔴 这张表的存在方式本身就是判据：开表要么出现在这里、要么打红。它**不是**豁免名单
#: （豁免名单只需要一个名字就能变绿），而是「可伪证声明」—— 每条都要带得出
#: 「凭什么认为这张表删得动」的实测依据，且上面三条判据会两个方向对齐：
#:
#:   * 契约 payload 里显式声明该键的表集合 == 本表的键集合（多一张或少一张都红）；
#:   * `modes["delete"]` 的计数 == 本表条数；
#:   * 两处 dataclass 默认值仍是 `clear`（否则全平台被一次开表而本表照样绿）。
#:
#: 🔴 删行**不可逆**。开表前必须先跑
#: `backend/scripts/check/check_row_deletion_readiness.py --table <table_key>`
#: 并把现算结论写进理由里。
OPENED_TABLES: dict[str, str] = {
    "endorse_discount_rows": (
        "D1-8 应收票据贴现/背书明细表·贴现区（受管数据区 14..21）。"
        "2026-09-30 用户授权的**第一张** canary。"
        "开表准入体检现算：8 行受管、`--count 1` 与 `--count 3` 均 8/8 可删、0 锁死 "
        "⇒ 无跨 sheet 单格引用指着这些行，门面不会 fail-closed。"
        "选它还因为本 sheet 是双区（兄弟区 `endorse_transfer_rows` 26..33 刻意仍为 clear）"
        "⇒ 删行会真实触发「兄弟 Table ref 收缩」这条 G2 症状链第一环，"
        "而不是在退化的单区表上验空壳；同 sheet 保留 clear 对照便于逐字节比对。"
        "CS-21 两个前提本就齐备：row_identity=field(/rows/*/rowId) + delete_policy=tombstone。"
    ),
}


def _census() -> dict[str, Any]:
    files = sorted(C.CONTRACTS_DIR.glob("*.json"))
    modes: Counter[str] = Counter()
    tables = 0
    parsed = 0
    visited = 0
    unparseable: dict[str, str] = {}
    declared: list[str] = []
    for path in files:
        visited += 1
        raw = json.loads(path.read_text(encoding="utf-8"))
        for sheet in raw.get("sheets") or []:
            for table in sheet.get("tables") or []:
                if "row_convergence" in table:
                    declared.append(f"{path.name}:{table.get('table_key')}")
        try:
            contract = C.parse_contract(raw)
        except Exception as exc:  # noqa: BLE001 - 普查要看**全部**失败形态
            unparseable[path.name] = f"{type(exc).__name__}: {exc}"
            continue
        parsed += 1
        for sheet in contract.sheets:
            for table in sheet.tables:
                tables += 1
                modes[table.row_convergence.value] += 1
    return {
        "files": files,
        "visited": visited,
        "parsed": parsed,
        "tables": tables,
        "modes": modes,
        "unparseable": unparseable,
        "declared": declared,
    }


@pytest.fixture(scope="module")
def census() -> dict[str, Any]:
    return _census()


class TestCoverageCensusAllExistingContractsAreClear:
    """**Validates: Requirement 8.5**（分母现算，禁写死）"""

    def test_visited_equals_the_live_denominator(self, census: dict[str, Any]) -> None:
        """🔴 遍历数 == 现算分母。不写死 62：契约文件会增长，写死就会静默漏掉新文件。"""
        live = len(list(C.CONTRACTS_DIR.glob("*.json")))
        assert census["visited"] == live == len(census["files"]), (
            f"遍历 {census['visited']} 个、现算 {live} 个 —— 普查漏了文件"
        )
        assert live > 40, f"契约文件只有 {live} 个 ⇒ 分母异常，普查可能指错了目录"

    def test_only_whitelisted_tables_are_open(self, census: dict[str, Any]) -> None:
        """🔴 主判据：除**已登记开表**的那几张，其余每一张表都是 `clear`。

        原判据是「每一张表都是 clear」。2026-09-30 用户授权开了第一张 canary
        （D1-8 贴现区），那条判据于是必须改 —— 但**不是**放宽成「允许有表不是 clear」，
        而是改成「开表必须在 :data:`OPENED_TABLES` 里登记且带理由」。
        差别在于：前者之后任何人开表都不会被看见，后者每开一张都要改这个文件。
        """
        assert census["tables"] > 100, f"表总数 {census['tables']} ⇒ 分母异常"
        modes = dict(census["modes"])
        opened = modes.get("delete", 0)
        assert opened == len(OPENED_TABLES), (
            f"现算 {opened} 张表开着删行，而登记清单有 {len(OPENED_TABLES)} 条 —— "
            f"两侧必须逐张对齐；现算 modes={modes}，清单={sorted(OPENED_TABLES)}"
        )
        assert modes.get("clear", 0) == census["tables"] - opened, (
            f"clear + delete != 表总数：{modes} / 总 {census['tables']} —— "
            "出现了第三种收敛方式"
        )

    def test_opened_tables_are_declared_explicitly_with_a_reason(
        self, census: dict[str, Any]
    ) -> None:
        """🔴 开表必须是**显式声明**的，且每条登记都带得出理由。

        两个方向一起锁：

        * 磁盘 payload 里**显式写过**该键的表集合，必须恰等于登记清单 ——
          「默认恰好是 clear」与「经判断选择 delete」不是一回事，后者必须在 JSON 里看得见；
        * 登记清单里每条都要有非空理由。只留一个表名等于没有依据。
        """
        declared_keys = {entry.split(":", 1)[-1] for entry in census["declared"]}
        assert declared_keys == set(OPENED_TABLES), (
            f"磁盘显式声明 {sorted(declared_keys)} ≠ 登记清单 {sorted(OPENED_TABLES)} —— "
            "要么有表被开了却没登记（最危险），要么登记了却没真写进契约（假开表）"
        )
        for table_key, reason in OPENED_TABLES.items():
            assert reason and len(reason) > 20, (
                f"{table_key} 的开表理由太短或为空：{reason!r} —— "
                "删行不可逆，理由必须写得下「凭什么认为这张表删得动」"
            )

    def test_no_table_is_open_by_default(self) -> None:
        """🔴 反向：两处 dataclass 默认值必须仍是 `clear`。

        这条是「开表逐张显式」的地基：默认值一旦被改成 `delete`，全平台在一次部署里
        同时开始删物理行，而上面两条判据**照样绿**（它们比的是契约 payload，
        而默认值不写进 payload）。
        """
        import dataclasses

        from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

        table_default = next(
            f.default for f in dataclasses.fields(C.TableSpec) if f.name == "row_convergence"
        )
        assert table_default is C.RowConvergenceMode.clear, (
            f"contracts.TableSpec.row_convergence 默认值变成了 {table_default!r}"
        )
        spec_default = next(
            f.default
            for f in dataclasses.fields(RowTableSheetSpec)
            if f.name == "row_convergence"
        )
        assert spec_default == "clear", (
            f"RowTableSheetSpec.row_convergence 默认值变成了 {spec_default!r} —— "
            "这一处才是「一改就全平台开表」的那个开关"
        )

    def test_unparseable_files_are_classified_not_skipped(
        self, census: dict[str, Any]
    ) -> None:
        """🔴 解析失败的文件逐条归类，不是静默跳过。

        分类而不是豁免：本来就进不了生产的文件（generator 候选 / 非契约映射表）
        谈不上 `row_convergence`。每条失败都必须命中一个已知类，
        出现新类别时立刻打红，逼迫重新判断而不是默默少算一个分母。
        """
        unparseable = census["unparseable"]
        assert unparseable, (
            "一个解析失败的都没有 ⇒ 与现算不符（本轮实测 11 个），"
            "或者普查把异常吞掉了"
        )
        unclassified = {
            name: err
            for name, err in unparseable.items()
            if not any(token in err for token in KNOWN_UNPARSEABLE_REASONS)
        }
        assert not unclassified, (
            f"出现未归类的解析失败：{ {k: v[:120] for k, v in unclassified.items()} } —— "
            "要么是并发会话在飞的改动，要么是真缺陷；两种都不该静默少算分母"
        )
        assert census["parsed"] + len(unparseable) == census["visited"], (
            f"成功 {census['parsed']} + 失败 {len(unparseable)} != 遍历 {census['visited']}"
        )

    def test_each_known_reason_class_is_actually_used(self, census: dict[str, Any]) -> None:
        """🔴 反向：已知类清单里不得有**失效条目**（豁免须可伪证）。

        某一类哪天不再出现（比如 candidate 契约全部转正）就该把它删掉，
        留着就是一条谁也不知道还管不管用的规则。
        """
        errors = list(census["unparseable"].values())
        unused = [
            token
            for token in KNOWN_UNPARSEABLE_REASONS
            if not any(token in err for err in errors)
        ]
        assert not unused, (
            f"已知类 {unused} 在现算里一次都没命中 ⇒ 失效条目，请删掉"
            f"（现存失败：{[e[:80] for e in errors]}）"
        )
