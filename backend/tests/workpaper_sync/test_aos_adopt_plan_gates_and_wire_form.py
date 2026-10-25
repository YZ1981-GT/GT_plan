"""Task 6.1 / 6.2 判据（伴生件）—— 计划算出来**之后**：校验门 / 错误契约 / 对外形态 / 事务纪律。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 3.2 / 3.4 / 4.4 · design §4.2（三个新 `error_code`）

`test_aos_adopt_plan_wiring.py` 交付时 **1055** 行（`count_lines` 口径 = `splitlines()`）>
`.py` 门禁 **800**，按域内先例（`test_aos_property_out_of_scope_rows.py` /
`…_out_of_scope_mutants.py`）抽出本件。切在 **§4 / §5 之间** —— 不是按行数对半砍，两侧各是一个
完整关注点：主体承「**计划是怎么来的**」（§1 唯一计划路径 / §2 接线 / §3 scope 只取声明 /
§4 三态 / §10 旧的第二口径已删），本件承「**计划算出来之后**」——

| 节 | 判据 | Requirement |
| --- | --- | --- |
| §5 | `plan_digest` 不符即拒（含 router 409 映射 + 校验点必在任何写之前） | 3.4 |
| §6 | 载荷不可解析 ⇒ 422 且**带 item_id**；shape error 原样穿透 | 4.4 |
| §7 | 三个新 `error_code` 与**既有三个**同风格（规则从既有三个反推） | 3.4 / 4.4 |
| §8 | wire form 含 Requirement 3.2 要的全部字段 | 3.2 |
| §9 | service 不 commit（三条 xfail 棘轮已全部摘除并改写，见 §9 末尾指针） | —— |
| §11 | Task 6.3 源码锁：删除侧在 merge **之后**（五段全序） | 1.1 / 1.2 / 3.5 |

🔴 **工具与桩一律从主体 import，不另造第二份**（源码级变异 `_source_mutant` / AST 取件
`_module_ast`·`_func_ast`·`_callee_name`·`_stmt_index`·`_calls_named` / 桩 `_StubReader`·
`_projection` / 固定计划 `_fixed_plan` / 路由文件 `_ROUTER_PY`）—— 两边的判据工具一漂，就在测
不同的东西了。每组「判据函数 + 它的变异反证」都留在同一文件内：§8 的 `judge_wire_form` 与它的
两组变异都在本件，§1 的 `judge_shared_plan` 与 M1~M4 都在主体。拆分是**纯文件搬家**：一条断言
没删没弱化（证据见 tasks.md 6.2）。

🔴 **import 必须用顶层模块名**（`from test_aos_adopt_plan_wiring import …`）：该目录无
`__init__.py`，pytest 以 `prepend` 模式把它塞进 `sys.path`；写成 `tests.workpaper_sync.…` 会
拿到**第二个**模块实例，模块级常量（`_ROUTER_PY` / `_IDENTITY_KEY`）与工具函数就分家 ——
届时「同一个 `_source_mutant`」实际是两个对象，谁都说不清跑的是哪一份。

🔴 **变异一律进程内源码级**（`inspect.getsource` → 替换唯一锚点 → 在生产模块 `globals` 的
**副本**里 `exec`），生产文件一字不改。不用 `monkeypatch.setattr` —— 本域有并发会话，
即便自动还原，窗口期内也改了共用模块的行为（域内 4.4 / 4.6 / 4.7 同一处置）。

🔴 **本文件交付时在 §9 挂过三条 `xfail(strict=True)` 棘轮**（删除侧应用 /
`AdoptPlanVerificationError` → 500 / `changed_item_count` 取自 plan）。Task 6.3 摘了前两条、
Task 6.4 摘了最后一条 ⇒ **本文件现在零 xfail**。三条**都改写成了正面判据**，没有一条被删掉了事：
第 1 条 ⇒ 本文件 §11 · 第 2 条 ⇒ `test_aos_deletion_apply_and_verify.py` §5 ·
第 3 条 ⇒ `test_aos_changed_items_and_audit_details.py` §1（落点与理由见 §9 末尾的指针注释）。
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from app.services.workpaper_sync import adopt_substrate_response as ASR
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlan,
    OverwritePlanShapeError,
)

# 🔴 工具 / 桩 / 固定计划 / `_ROUTER_PY` 的**唯一**来源（禁抄第二份；顶层模块名形态见 docstring）。
from test_aos_adopt_plan_wiring import (  # noqa: E402
    _IDENTITY_KEY,
    _ROUTER_PY,
    _StubReader,
    _callee_name,
    _calls_named,
    _fixed_plan,
    _func_ast,
    _module_ast,
    _projection,
    _source_mutant,
    _stmt_index,
)


#: 既有三个 domain 错误类 → `error_code`（现读 `adopt_substrate_response` 得来，§7 的基准）。
LEGACY_ERROR_CODES: tuple[tuple[str, str], ...] = (
    ("AdoptContractRequiredError", "adopt_contract_required"),
    ("AdoptSubstrateNotPublishedError", "adopt_substrate_not_published"),
    ("AdoptRevisionConflictError", "adopt_revision_conflict"),
)

#: 本任务新增三个。
NEW_ERROR_CODES: tuple[tuple[str, str], ...] = (
    ("AdoptPlanDigestMismatchError", "adopt_plan_digest_mismatch"),
    ("AdoptStorePayloadUnreadableError", "adopt_store_payload_unreadable"),
    ("AdoptPlanVerificationError", "adopt_plan_verification_failed"),
)


# ═══════════════════════════════════════════════════════════════════════════════
# §5 `plan_digest` 校验（Requirement 3.4）
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlanDigestVerification:
    @pytest.mark.parametrize("expected", [None, "", "   "])
    def test_absent_digest_is_not_verified(self, expected: str | None) -> None:
        """未回传 ⇒ 不校验（运维直调 / 首次执行都没有 digest 可给）。"""
        ASR.verify_plan_digest(_fixed_plan(), expected=expected)

    def test_matching_digest_passes(self) -> None:
        plan = _fixed_plan()
        ASR.verify_plan_digest(plan, expected=plan.digest)

    def test_mismatching_digest_is_rejected(self) -> None:
        plan = _fixed_plan()
        with pytest.raises(ASR.AdoptPlanDigestMismatchError) as caught:
            ASR.verify_plan_digest(plan, expected="0" * 64)
        assert caught.value.error_code == "adopt_plan_digest_mismatch"
        assert "两侧已变化" in str(caught.value)

    def test_a_changed_plan_changes_the_verdict(self) -> None:
        """同一 digest 对**内容已变**的计划必须不通过 —— 证明它吃的是内容不是对象身份。"""
        stale = _fixed_plan().digest
        drifted = OverwritePlan(
            deltas=(
                ItemOverwriteDelta(
                    item_id="AOS61-item",
                    table_key="aos61_rows",
                    rows_added=("aos61-a1",),
                    rows_deleted=("aos61-d1",),  # 少了一条 ⇒ 计划变了
                    rows_updated=("aos61-u1",),
                ),
            ),
            store_rows_by_table={"aos61_rows": 3},
            substrate_rows_by_table={"aos61_rows": 2},
        )
        with pytest.raises(ASR.AdoptPlanDigestMismatchError):
            ASR.verify_plan_digest(drifted, expected=stale)
        # 同内容不同对象 ⇒ 仍放行（否则每次重算都会 409）
        ASR.verify_plan_digest(_fixed_plan(), expected=stale)

    def test_mutant_comparison_neutralised_is_caught(self) -> None:
        """变异：把比较中性化 ⇒ 不符也放行。生产实现抛、变异体不抛 ⇒ 判据有牙。"""
        mutant = _source_mutant(
            ASR.verify_plan_digest,
            old="if wanted != actual:",
            new="if wanted != actual and False:",
            module=ASR,
        )
        plan = _fixed_plan()
        with pytest.raises(ASR.AdoptPlanDigestMismatchError):
            ASR.verify_plan_digest(plan, expected="0" * 64)
        mutant(plan, expected="0" * 64)  # 变异体静默放行
        assert ASR.verify_plan_digest is not mutant

    def test_verification_happens_before_any_write(self) -> None:
        """🔴 校验点必须在**任何写之前** —— 放到写之后就只剩一个漂亮的错误消息。

        判据形态 = `fn.body` 下标：digest 校验语句必须早于 `mirror_projection_into_store`
        的 import 与调用（后者是本函数唯一的写入起点）。
        """
        fn = _func_ast("compute_adopt_substrate")
        verify_at = _stmt_index(fn.body, lambda s: bool(_calls_named(s, "verify_plan_digest")))
        assert verify_at >= 0, "compute_adopt_substrate 里没有 verify_plan_digest 调用点"
        write_at = _stmt_index(
            fn.body,
            lambda s: isinstance(s, ast.ImportFrom)
            and any(a.name == "mirror_projection_into_store" for a in s.names),
        )
        assert write_at >= 0, "定位不到 mirror_projection_into_store 的引入点"
        assert verify_at < write_at, (
            f"digest 校验（下标 {verify_at}）晚于写入起点（{write_at}）—— "
            "用户确认的与将执行的已经不是同一份了，报错只是事后追认"
        )

    def test_router_maps_digest_mismatch_to_409(self) -> None:
        """端点映射：`AdoptPlanDigestMismatchError` → 409（Requirement 3.4 要的是端点行为）。

        源码锁而非真发请求：端点级 TestClient 判据归 Task 8.2，本条只防「错误类建好了却
        没接进映射」这一种漏接 —— 那会让它落进兜底分支变成 422。
        """
        src = _ROUTER_PY.read_bytes().decode("utf-8")
        tree = ast.parse(src)
        handlers: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "adopt_substrate":
                continue
            for handler in (h for t in ast.walk(node) if isinstance(t, ast.Try) for h in t.handlers):
                names = [
                    n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)
                ] if handler.type is not None else []
                codes = [
                    kw.value.value
                    for call in _calls_named(handler, "HTTPException")
                    for kw in call.keywords
                    if kw.arg == "status_code" and isinstance(kw.value, ast.Constant)
                ]
                for name in names:
                    for code in codes:
                        handlers.append((name, int(code)))
        assert ("AdoptPlanDigestMismatchError", 409) in handlers, (
            f"adopt_substrate 端点没有把 AdoptPlanDigestMismatchError 映成 409，实得 {handlers}"
        )
        # 变异对照：同一扫描器对一条**已知不存在**的映射必须报否（否则它什么都没在数）
        assert ("AdoptPlanDigestMismatchError", 418) not in handlers


# ═══════════════════════════════════════════════════════════════════════════════
# §6 载荷不可解析 ⇒ 422 且**带 item_id**（Requirement 4.4）
#
# 🔴 本节直面 Task 3.6 登记的那个现状：`adopt_overwrite_plan._reject_unreadable_payload`
#    的兜底文案**不带** item_id（`M1_PLAN_RED_REASON` 三格写的就是「没有 item_id」）。
#    Task 6.2 的处置是**在调用点包装**并由 `AdoptStorePayloadUnreadableError` 自己带上
#    item_id —— 因此那张现状登记表**不动**（它登记的是那条兜底文案，本轮一字未改）。
# ═══════════════════════════════════════════════════════════════════════════════

_BAD_TABLE = "aos61_bad_rows"


def _unreadable_inputs(*, item_id: str, message: str) -> tuple[Any, dict[str, Any], Any]:
    reader = _StubReader(
        item_id=item_id,
        declared_scopes=((_BAD_TABLE, None),),
        raises=ValueError(message),
    )
    inputs = ASR.AdoptPlanInputs(
        item_ids=(item_id,),
        row_readers={item_id: reader},
        skip_reasons={},
        item_scopes={},
    )
    return _projection(**{_BAD_TABLE: ("aos61-sub",)}), {item_id: "not-json-at-all"}, inputs


class TestUnreadablePayloadFailsVisible:
    def test_native_message_without_item_id_still_yields_item_id(self) -> None:
        """原生异常文案不带 item_id ⇒ 本层仍兑现 Requirement 4.4 的「给出该 item 的 item_id」。"""
        baseline, payloads, inputs = _unreadable_inputs(
            item_id="AOS61-bad", message="payload unreadable"
        )
        with pytest.raises(ASR.AdoptStorePayloadUnreadableError) as caught:
            ASR.compute_plan_for_adopt(
                baseline=baseline, store_payloads=payloads, plan_inputs=inputs
            )
        exc = caught.value
        assert exc.error_code == "adopt_store_payload_unreadable"
        assert exc.item_id == "AOS61-bad", "错误对象没带上 item_id"
        assert "AOS61-bad" in str(exc), "错误文案里没有 item_id —— 下游无从告诉用户哪份载荷坏了"
        assert isinstance(exc.__cause__, ValueError), "原生异常没被挂成 __cause__（丢了归因）"
        # 反向对照：原生文案确实不带 item_id（否则本用例证明不了「是本层补上的」）
        assert "AOS61-bad" not in str(exc.__cause__)

    def test_not_treated_as_zero_rows(self) -> None:
        """🔴 不得当零行处理 —— 那会把 substrate 的全部身份报成新增而实际一行都不会写。"""
        baseline, payloads, inputs = _unreadable_inputs(
            item_id="AOS61-bad", message="payload unreadable"
        )
        with pytest.raises(ASR.AdoptStorePayloadUnreadableError):
            ASR.compute_plan_for_adopt(
                baseline=baseline, store_payloads=payloads, plan_inputs=inputs
            )
        # 变异对照：把同一 item 的载荷换成**可读**的 ⇒ 同一条链路必须算得出计划
        readable = ASR.AdoptPlanInputs(
            item_ids=("AOS61-bad",),
            row_readers={
                "AOS61-bad": _StubReader(
                    item_id="AOS61-bad", declared_scopes=((_BAD_TABLE, None),)
                )
            },
            skip_reasons={},
            item_scopes={},
        )
        plan = ASR.compute_plan_for_adopt(
            baseline=baseline,
            store_payloads={"AOS61-bad": json.dumps([{_IDENTITY_KEY: "aos61-store"}])},
            plan_inputs=readable,
        )
        assert plan.deltas[0].rows_deleted == ("aos61-store",)

    def test_shape_error_is_not_translated(self) -> None:
        """🔴 `OverwritePlanShapeError` **原样穿透** —— 编程错误不得伪装成用户可重试的 422。"""
        inputs = ASR.AdoptPlanInputs(
            item_ids=(), row_readers={}, skip_reasons={}, item_scopes={}
        )
        with pytest.raises(OverwritePlanShapeError):
            ASR.compute_plan_for_adopt(
                baseline=SimpleNamespace(row_keys=["not", "a", "mapping"]),
                store_payloads={},
                plan_inputs=inputs,
            )

    def test_first_unreadable_item_locates_the_offender_only(self) -> None:
        """`_first_unreadable_item`：只点名真读不动的那一个；全读得动返回空串。"""
        good = _StubReader(item_id="AOS61-a", declared_scopes=((_BAD_TABLE, None),))
        bad = _StubReader(
            item_id="AOS61-b",
            declared_scopes=((_BAD_TABLE, None),),
            raises=ValueError("boom"),
        )
        payload = json.dumps([{_IDENTITY_KEY: "aos61-store"}])
        assert (
            ASR._first_unreadable_item(
                {"AOS61-a": payload, "AOS61-b": payload},
                {"AOS61-a": good, "AOS61-b": bad},
            )
            == "AOS61-b"
        )
        assert ASR._first_unreadable_item({"AOS61-a": payload}, {"AOS61-a": good}) == ""
        # 载荷为 None（库里没这条）不算读不动
        assert ASR._first_unreadable_item({"AOS61-b": None}, {"AOS61-b": bad}) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# §7 三个新 `error_code` 与**既有三个**同风格
# ═══════════════════════════════════════════════════════════════════════════════

#: 类名去 `Error` 后 snake_case **再补 `_failed`** 的那两个 —— 理由见下方 docstring。
_FAILED_SUFFIX_CLASSES = ("AdoptSubstrateError", "AdoptPlanVerificationError")


def _snake(camel: str) -> str:
    out: list[str] = []
    for ordinal, char in enumerate(camel):
        if char.isupper() and ordinal:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


class TestErrorCodeStyleMatchesTheLegacyThree:
    def test_legacy_three_are_untouched(self) -> None:
        """基准：既有三个的 `error_code` 一字未改（本轮没有顺手重命名）。"""
        for name, code in LEGACY_ERROR_CODES:
            assert getattr(ASR, name).error_code == code

    def test_new_three_match_design_table(self) -> None:
        """三个新 code 与 design §4.2 的三行逐字相同。"""
        for name, code in NEW_ERROR_CODES:
            cls = getattr(ASR, name)
            assert cls.error_code == code
            assert issubclass(cls, ASR.AdoptSubstrateError), f"{name} 不是与既有三个并列的子类"

    def test_the_naming_rule_is_the_same_one(self) -> None:
        """🔴 风格规则**从既有三个反推**，再套到新三个上，而不是凭 `AdoptXxxError` 字面推测。

        规则 = 类名去掉 `Error` → CamelCase 转 snake_case，**不加后缀**；
        唯一例外是「类名去 `Error` 后只剩主语 / 动作名、没有状态词」的两个
        （基类 `AdoptSubstrateError` 与 `AdoptPlanVerificationError`）⇒ 补 `_failed`。
        既有三个里的状态词分别是 `required` / `not_published` / `conflict`。
        """
        exceptions: list[str] = []
        for name, code in LEGACY_ERROR_CODES + NEW_ERROR_CODES + (
            ("AdoptSubstrateError", "adopt_substrate_failed"),
        ):
            plain = _snake(name.removesuffix("Error"))
            assert code in (plain, f"{plain}_failed"), (
                f"{name} 的 error_code {code!r} 既不是 {plain!r} 也不是 {plain}_failed —— "
                "与既有三个不是同一条命名规则"
            )
            if code != plain:
                exceptions.append(name)
        assert sorted(exceptions) == sorted(_FAILED_SUFFIX_CLASSES), (
            f"补 `_failed` 的类集合变了：实得 {sorted(exceptions)} —— "
            "多一个就说明有人给自带状态词的类也加了后缀，少一个说明规则被破了"
        )

    def test_every_code_is_prefixed_and_distinct(self) -> None:
        names = [n for n, _c in LEGACY_ERROR_CODES + NEW_ERROR_CODES] + [
            "AdoptSubstrateError",
            "AdoptContractRequiredError",
        ]
        codes = [getattr(ASR, n).error_code for n in names]
        assert all(c.startswith("adopt_") for c in codes), codes
        assert len(set(codes)) == len(set(names)), f"error_code 撞车：{codes}"

    def test_payload_unreadable_carries_item_id_by_construction(self) -> None:
        """只有它带 `item_id` 构造参数 —— 那是 Requirement 4.4 逐字要求的那件事。"""
        exc = ASR.AdoptStorePayloadUnreadableError("坏了", item_id="AOS61-x")
        assert exc.item_id == "AOS61-x"
        assert ASR.AdoptStorePayloadUnreadableError("坏了").item_id == ""


# ═══════════════════════════════════════════════════════════════════════════════
# §8 wire form 含 Requirement 3.2 要的全部字段
# ═══════════════════════════════════════════════════════════════════════════════

#: Requirement 3.2 逐字：「逐 item 的待追加 / 待删除 / 待更新身份清单、四个计数、两侧行数」
#: ＋ Requirement 3.3 的 `plan_digest` ＋ Requirement 4.2 的显式跳过清单。
_REQUIRED_TOP_FIELDS = (
    "plan_digest",
    "store_row_count",
    "substrate_row_count",
    "store_rows_by_table",
    "substrate_rows_by_table",
    "deltas",
    "skipped_items",
)
_REQUIRED_DELTA_FIELDS = (
    "item_id",
    "table_key",
    "row_section",
    "rows_added",
    "rows_deleted",
    "rows_updated",
    "rows_ghost_dropped",
    "rows_added_count",
    "rows_deleted_count",
    "rows_updated_count",
    "rows_ghost_dropped_count",
    "skipped_reason",
)


def judge_wire_form(wire: Mapping[str, Any], plan: OverwritePlan) -> list[str]:
    violations: list[str] = []
    for field in _REQUIRED_TOP_FIELDS:
        if field not in wire:
            violations.append(f"顶层缺字段 {field}")
    if wire.get("plan_digest") != plan.digest:
        violations.append("plan_digest 与 plan.digest 不等")
    for ordinal, entry in enumerate(wire.get("deltas") or ()):
        for field in _REQUIRED_DELTA_FIELDS:
            if field not in entry:
                violations.append(f"deltas[{ordinal}] 缺字段 {field}")
        for field in ("rows_added", "rows_deleted", "rows_updated", "rows_ghost_dropped"):
            if field in entry and entry.get(f"{field}_count") != len(entry[field]):
                violations.append(f"deltas[{ordinal}].{field}_count 与清单长度不等")
    return violations


class TestWireForm:
    def test_production_wire_form_is_complete(self) -> None:
        plan = _fixed_plan()
        wire = ASR._plan_wire_form(plan)
        assert judge_wire_form(wire, plan) == []
        assert wire["store_row_count"] == 3 and wire["substrate_row_count"] == 2
        assert wire["skipped_items"] == [["AOS61-blind", "item_blind"]]
        assert json.loads(json.dumps(wire)) == wire, "wire form 不是纯 JSON 可序列化形态"

    def test_skipped_delta_reports_reason_and_no_rows(self) -> None:
        wire = ASR._plan_wire_form(_fixed_plan())
        skipped = [d for d in wire["deltas"] if d["skipped_reason"] is not None]
        assert len(skipped) == 1 and skipped[0]["item_id"] == "AOS61-blind"
        assert skipped[0]["table_key"] is None and skipped[0]["rows_deleted"] == []

    def test_mutant_dropping_a_list_field_is_caught(self) -> None:
        """变异：某个行清单不进 wire form ⇒ 判据打红（并证明它数的是每一个字段）。"""
        mutant = _source_mutant(
            ASR._plan_wire_form,
            old='"rows_deleted": list(delta.rows_deleted),',
            new="",
            module=ASR,
        )
        plan = _fixed_plan()
        got = judge_wire_form(mutant(plan), plan)
        assert got and all("rows_deleted" in v for v in got), got

    def test_mutant_count_from_wrong_list_is_caught(self) -> None:
        """变异：某个计数读**另一个**清单的长度 ⇒ 判据打红。"""
        mutant = _source_mutant(
            ASR._plan_wire_form,
            old='"rows_deleted_count": delta.rows_deleted_count,',
            new='"rows_deleted_count": delta.rows_added_count,',
            module=ASR,
        )
        plan = _fixed_plan()
        got = judge_wire_form(mutant(plan), plan)
        assert got == ["deltas[0].rows_deleted_count 与清单长度不等"], got


# ═══════════════════════════════════════════════════════════════════════════════
# §9 service 不 commit；6.3 / 6.4 未被提前实现
# ═══════════════════════════════════════════════════════════════════════════════

#: 本任务新增 / 改动的公开符号（§9 逐个核「不碰事务」）。
_NEW_SYNC_SYMBOLS = (
    "build_plan_inputs",
    "census_plan_inputs",
    "compute_plan_for_adopt",
    "verify_plan_digest",
    "_plan_wire_form",
    "_scope_override_from_declaration",
    "_first_unreadable_item",
)


class TestTransactionDiscipline:
    def test_commit_call_site_is_the_single_pre_existing_one(self) -> None:
        """🔴 平台铁律：service 只 flush 不 commit。

        adopt 的唯一例外是 `compute_adopt_substrate` 末尾那处**统一 commit**（它是本 adopt
        的事务边界，改动前后一字不变）。本条把「恰 1 处且在那个函数里」钉死 ⇒ 新代码里
        多出任何一次 commit / flush 都会打红。
        """
        module_ast = _module_ast()
        sites: list[str] = []
        for node in ast.walk(module_ast):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and _callee_name(call) in ("commit", "flush"):
                    sites.append(f"{node.name}:{_callee_name(call)}")
        assert sites == ["compute_adopt_substrate:commit"], (
            f"事务操作的调用点不再是唯一那一处，实得 {sites}"
        )

    @pytest.mark.parametrize("symbol", _NEW_SYNC_SYMBOLS)
    def test_new_helpers_are_sync_and_take_no_session(self, symbol: str) -> None:
        """新增计划机件全部是同步纯函数 —— 拿不到 session 就不可能 commit。"""
        fn = getattr(ASR, symbol)
        assert not inspect.iscoroutinefunction(fn), f"{symbol} 是协程 —— 它不该碰 IO"
        assert "session" not in inspect.signature(fn).parameters, f"{symbol} 收了 session"

    def test_store_payload_read_is_shared_with_the_rollback_snapshot(self) -> None:
        """计划与回滚快照建立在**同一次**读取上（否则会留下「计划与快照错版」的窗口）。"""
        fn = _func_ast("compute_adopt_substrate")
        assigns = [
            target.id
            for stmt in fn.body
            if isinstance(stmt, ast.Assign) and _calls_named(stmt, "_snapshot_store")
            for target in stmt.targets
            if isinstance(target, ast.Name)
        ]
        assert assigns == ["store_payloads"], (
            f"顶层只该有一次 `store_payloads = _snapshot_store(...)`，实得 {assigns}"
        )
        src = inspect.getsource(ASR.compute_adopt_substrate)
        assert "before_snapshot = store_payloads" in src, (
            "回滚快照不再复用计划那次读取 —— 两次读之间的窗口足够让 store 变一版"
        )


# 🔴 **本节原有的 `TestTask63And64AreNotDoneYet` 已整类摘除（Task 6.4 落地）**。
#
# 它剩下的最后一条棘轮 `test_changed_item_count_comes_from_the_plan`
# （`xfail(strict=True)`，断言 `"_diff_snapshots" not in src`）在 6.4 落地当天会 XPASS 而
# strict 使其打红 —— 这正是棘轮设计想要的效果。与它成对的现状登记
# `test_changed_item_count_still_comes_from_the_snapshot_diff`（断言
# `changed = _diff_snapshots(...)` 在场）在同一天变成**假**。
#
# 两条**都已改写**（不是删掉了事），落点 `test_aos_changed_items_and_audit_details.py` **§1**：
#   · 原棘轮 ⇒ `judge_changed_item_count_source` 的五条子判据（AST，含「实参必须是
#     `applied.plan` 而不是 merge 前那份 `plan`」这条原写法根本表达不了的加强）；
#   · 原现状登记 ⇒ `test_the_snapshot_diff_only_feeds_the_rollback_coverage`：`_diff_snapshots`
#     **仍在场**（Requirement 6.9 需要它那一半），但它的产出只许流进 `rollback_snapshot_items`
#     的 `snapshot_changed`，一步都不许流进 `changed_item_count`。
# 🔴 为什么整组搬走而不是留在本文件：行数门禁（本文件 695/800，§1 那组判据 + 5 组变异约 190 行
#    装不下），与 6.3 把 router 那组搬去 `test_aos_deletion_apply_and_verify.py` §5 同一处置。
# 🔴 为什么改成 AST：原写法是文本 `in` 匹配，docstring / `#` 注释两向都能骗过它（平台铁律 ㉖）。


# ═══════════════════════════════════════════════════════════════════════════════
# §11 Task 6.3 源码锁：删除侧在 merge **之后**（五段全序）
#
# 🔴 配套那条「router 500 映射排在兜底之前」的源码锁与它的三组变异**整组**住在
#    `test_aos_deletion_apply_and_verify.py` §5 —— 行数门禁所迫（两半同文件 802 行 > 800），
#    切口在两个 judge 之间，没有拆开任何「判据 + 变异」对。
#
# 🔴 本节是 §9 那两条 `xfail` 摘除后的**正面判据**，而且比原棘轮强 —— 原写法是
#    `prune_at = _stmt_index(fn.body, "prune_undeclared_rows" in ast.dump(s))` 与
#    `mirror_at = _stmt_index(fn.body, ImportFrom(mirror…))` 相比：mirror 的 **import** 是
#    函数顶层语句、真正的**调用点**在 `try` 块里，而 `ast.dump(try)` 递归含整块 ⇒ 那个下标
#    比较在「prune 排在 merge 之前」时**照样成立**。⇒ 本节改成在 `try` 块内逐语句定位**调用
#    点**（mirror → 删除侧 → 复读 → 抛错 → commit 五段全序），并配「交换两条语句 ⇒ 打红」。
# 🔴 端点级真发 HTTP 归 Task 8.x；本节只防「映射漏接 / 排在兜底之后被静默吞成 422」。
# ═══════════════════════════════════════════════════════════════════════════════

_DELETION_APPLY = "apply_overwrite_deletions"
_MIRROR_CALL = "mirror_projection_into_store"
_READBACK = "verify_applied_plan"
_VERIFY_ERROR = "AdoptPlanVerificationError"
_CATCH_ALL = "AdoptSubstrateError"


def _try_body(fn: Any) -> list[Any]:
    """`compute_adopt_substrate` 里那个 `try` 的语句列表（写入、复读、commit、回滚都在它内）。"""
    try_at = _stmt_index(fn.body, lambda s: isinstance(s, ast.Try))
    assert try_at >= 0, "compute_adopt_substrate 里没有 try 块 —— 回滚保护不在了"
    return fn.body[try_at].body


def judge_deletion_after_mirror(fn: Any) -> list[str]:
    """五段全序的子判据（返回违规清单，空 = 合规）。**纯函数**，变异可直接喂 AST。"""
    body = _try_body(fn)
    at = {
        name: _stmt_index(body, lambda s, n=name: bool(_calls_named(s, n)))
        for name in (
            _MIRROR_CALL,
            _DELETION_APPLY,
            "_snapshot_store",
            _READBACK,
            _VERIFY_ERROR,
            "commit",
        )
    }
    missing = sorted(n for n, i in at.items() if i < 0)
    if missing:
        return [f"定位失败：{missing} 在 try 块里找不到调用点（实得下标 {at}）"]
    violations: list[str] = []
    if at[_DELETION_APPLY] < at[_MIRROR_CALL]:
        violations.append(
            f"删除侧（{at[_DELETION_APPLY]}）排在 merge（{at[_MIRROR_CALL]}）**之前** —— "
            "前置清 base 会让 projection 每一行都变成「本次新增身份」⇒ 幽灵行门全面生效 ⇒ "
            "锚点业务名为空的行整批被剔除，「覆盖」变成大面积静默少写（ADR-AOS-001 否决方案 3）"
        )
    if at["_snapshot_store"] < at[_DELETION_APPLY]:
        violations.append(
            f"复读的那次 `_snapshot_store`（{at['_snapshot_store']}）早于删除侧"
            f"（{at[_DELETION_APPLY]}）—— 它是复读比对（Requirement 3.5）的输入，也是 "
            "`rollback_snapshot` 覆盖面里「字节差集」那一半的来源；早读两者都看不见删除侧改动"
            "（Requirement 6.9）"
        )
    if at[_READBACK] < at["_snapshot_store"]:
        violations.append(f"比对（{at[_READBACK]}）早于复读（{at['_snapshot_store']}）")
    if at[_VERIFY_ERROR] < at[_READBACK]:
        violations.append(f"抛错（{at[_VERIFY_ERROR]}）早于复读（{at[_READBACK]}）")
    if at["commit"] < at[_VERIFY_ERROR]:
        violations.append(
            f"commit（{at['commit']}）早于复读比对的抛错点（{at[_VERIFY_ERROR]}）—— "
            "Requirement 3.5 要的是**提交之前**比对，提交后再报错就回滚不了了"
        )
    return violations


class TestDeletionSideIsAppliedAfterMirror:
    def test_production_satisfies_every_clause(self) -> None:
        """对照组：生产实现下五段全序成立。"""
        assert judge_deletion_after_mirror(_func_ast("compute_adopt_substrate")) == []

    def test_mutant_deletion_before_mirror_is_caught(self) -> None:
        """变异：把删除侧与 merge 两条语句**对调** ⇒ 只打红 ADR-AOS-001 那一条。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        body = _try_body(fn)
        mirror_at = _stmt_index(body, lambda s: bool(_calls_named(s, _MIRROR_CALL)))
        prune_at = _stmt_index(body, lambda s: bool(_calls_named(s, _DELETION_APPLY)))
        assert 0 <= mirror_at < prune_at, "前提：生产实现里 merge 在删除侧之前"
        body[mirror_at], body[prune_at] = body[prune_at], body[mirror_at]
        got = judge_deletion_after_mirror(fn)
        assert len(got) == 1 and "之前" in got[0] and "幽灵行门" in got[0], got

    def test_mutant_snapshot_before_deletion_is_caught(self) -> None:
        """变异：复读那次 `_snapshot_store` 提到删除侧之前 ⇒ 打红 Requirement 6.9 那一条。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        body = _try_body(fn)
        snap_at = _stmt_index(body, lambda s: bool(_calls_named(s, "_snapshot_store")))
        prune_at = _stmt_index(body, lambda s: bool(_calls_named(s, _DELETION_APPLY)))
        assert 0 <= prune_at < snap_at, "前提：生产实现里删除侧在复读之前"
        body.insert(prune_at, body.pop(snap_at))
        got = judge_deletion_after_mirror(fn)
        assert any("rollback_snapshot" in v for v in got), got

    def test_mutant_commit_before_readback_is_caught(self) -> None:
        """变异：commit 提到复读之前 ⇒ 打红「提交后再报错回滚不了」那一条。"""
        fn = copy.deepcopy(_func_ast("compute_adopt_substrate"))
        body = _try_body(fn)
        commit_at = _stmt_index(body, lambda s: bool(_calls_named(s, "commit")))
        body.insert(0, body.pop(commit_at))
        got = judge_deletion_after_mirror(fn)
        assert any("commit" in v and "提交之前" in v for v in got), got

    def test_deletion_side_reuses_the_task41_pure_function(self) -> None:
        """删除侧必须**用** Task 4.1 那个纯函数，不得在应用层重写一份剪枝。"""
        from app.services.workpaper_sync import adopt_overwrite_apply as AOA

        fn = next(
            node
            for node in ast.walk(ast.parse(inspect.getsource(AOA)))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _DELETION_APPLY
        )
        assert len(_calls_named(fn, "prune_undeclared_rows")) == 1, (
            "删除侧没有**恰一次**调用 prune_undeclared_rows —— 0 次 = 自己重写了剪枝"
            "（第二真源，必与 Property 1/2 的判据漂移）"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 指针：另一半在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# §1~§4 与 §10 在主体 **`test_aos_adopt_plan_wiring.py`**：
#   §1 dry_run 与真实执行共用唯一计划函数（`judge_shared_plan` 与 M1~M4 变异都在那边）
#   §2 三条空 `declared_scopes` item 的接线（D4-2-rows / D2-detail-rows / H1-8-rows）
#   §3 scope 覆盖只取声明，取不到就不猜
#   §4 `build_plan_inputs` 三态（reader / 跳过 / 未裁决）
#   §10 被取代的两个私有函数已删 + 指针注释（与 §1 是同一关注点的正反两面）
#
# Task 6.3 的其余判据在 **`test_aos_deletion_apply_and_verify.py`**：幽灵观测口径 /
# 复读比对粒度 / 删除侧真落库 / 应用模块不碰事务 —— 外加 **router 500 映射那条源码锁**
# （`judge_router_verification_mapping` 与它的三组变异，整组一起搬过去的）。
# 🔴 搬家原因是行数门禁：§11 两半都留在本文件会到 **802** 行 > `.py` 上限 800。
#    切口选在「两个 judge 之间」⇒ **没有**把任何一个判据函数与它的变异反证拆开
#    （`judge_deletion_after_mirror` + 4 组变异留在本文件 §11，router 那组整组搬走）。
#
# 主体同时是两份的共用工具箱（源码级变异 / AST 取件 / 桩 reader / 桩 projection / 固定计划 /
# `_ROUTER_PY`），本文件**只 import 不另造第二份**。
