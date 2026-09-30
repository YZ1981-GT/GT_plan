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

    def test_every_parseable_table_is_clear(self, census: dict[str, Any]) -> None:
        """🔴 主判据：可解析契约的**每一张表**都是 `clear`。"""
        assert census["tables"] > 100, f"表总数 {census['tables']} ⇒ 分母异常"
        assert dict(census["modes"]) == {"clear": census["tables"]}, (
            f"有表不是 clear：{dict(census['modes'])} —— "
            "本 spec 落地时不得有任何既有表被默认开启删行"
        )

    def test_no_existing_payload_declares_the_key_yet(self, census: dict[str, Any]) -> None:
        """🔴 没有任何既有 payload 显式写过这个键 ⇒ 上一条的 `clear` 全部来自**默认值**。

        少了这条，上一条可能是因为「每份契约都显式写了 clear」而绿 ——
        那样默认值就没被测到。
        """
        assert census["declared"] == [], (
            f"已有 payload 显式声明 row_convergence：{census['declared']} —— "
            "开启某张表时请同步更新本判据（改成允许该表出现在清单里）"
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
