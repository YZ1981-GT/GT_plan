"""spec wp-sync-conflict-adjudication-and-d4-32-modeling §1：schema 冲突可裁决性对拍。

缺陷原貌（两处叠加，合起来让**全平台任何 entry** 的 schema 冲突都成死路）：

1. `working_paper_sync_conflict` 没有 `schema_anomaly` 列 —— `ConflictRecord.to_row()`
   的列投影漏了它（`digest_payload()` 一直带着），成因在写库那一刻丢失；
2. 读侧 `ConflictPreviewItem.adjudicable_by_value_choice` 自己写了
   `return self.kind is not ConflictKind.schema`，把**全部** schema 冲突一律判成不可
   裁决；而域内 `ConflictRecord.adjudicable_by_value_choice` 是按 `SchemaAnomalyKind`
   分两类的。两份实现口径分叉 ⇒ 同一条冲突上 `suggested_action=manual_merge` 与
   `adjudicable_by_value_choice=false` 并存，前端据后者把它从所有裁决入口排除。

本模块的判据按「分母是枚举全集」写：逐成员对拍读侧与域内，而不是挑两个样本。挑样本
的写法在新增 anomaly 成员时不会打红，而新增成员恰好是最容易再次分叉的时刻。
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from typing import Any

import pytest

from app.models.workpaper_sync_models import WorkpaperSyncConflict
from app.services.workpaper_sync import conflict_resolution as CR
from app.services.workpaper_sync import conflicts as CF

# ═══════════════════════════════════════════════════════════════════════════
# 夹具：读侧 DTO 与 DB 行
# ═══════════════════════════════════════════════════════════════════════════


def _item(
    *,
    kind: CF.ConflictKind = CF.ConflictKind.schema,
    anomaly: CF.SchemaAnomalyKind | None = None,
) -> CR.ConflictPreviewItem:
    """一个读侧预览项。只有 `kind` / `schema_anomaly` 是本模块的被测维度。"""
    return CR.ConflictPreviewItem(
        conflict_id=uuid.uuid4(),
        stable_field_key="d4_32_groups/GTROW-D432-0001/group_label",
        business_label="分组",
        sheet_key="D4-32",
        table_key="d4_32_groups",
        row_key="GTROW-D432-0001",
        json_pointer="/d4_32_groups/0/group_label",
        oo_location="D4-32!A13",
        kind=kind,
        field_source=CF.FieldSource.onlyoffice_cell,
        protection_policy=CF.ProtectionPolicy.editable,
        suggested_action=CF.SuggestedAction.manual_merge,
        value_type="text",
        base=None,
        current=None,
        incoming=None,
        client_edit_epoch=7,
        incoming_sequence=3,
        resolved=False,
        schema_anomaly=anomaly,
    )


def _row(anomaly_raw: str | None) -> WorkpaperSyncConflict:
    """一行 DB 冲突（真实 ORM 实例，不落库）。

    用 ORM 而非 `SimpleNamespace`：列名写错时构造就会失败，替身不会悄悄偏离真实表。
    """
    return WorkpaperSyncConflict(
        id=uuid.uuid4(),
        operation_id=uuid.uuid4(),
        client_edit_epoch=7,
        stable_field_key="d4_32_groups/GTROW-D432-0001/group_label",
        business_label="分组",
        sheet_key="D4-32",
        table_key="d4_32_groups",
        row_key="GTROW-D432-0001",
        json_pointer="/d4_32_groups/0/group_label",
        oo_location="D4-32!A13",
        field_source=CF.FieldSource.onlyoffice_cell.value,
        protection_policy=CF.ProtectionPolicy.editable.value,
        suggested_action=CF.SuggestedAction.manual_merge.value,
        conflict_kind=CF.ConflictKind.schema.value,
        schema_anomaly=anomaly_raw,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Property 1：读侧判据 == 域内判据（分母 = SchemaAnomalyKind 全集）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1ReadSideMatchesDomain:
    """读侧与域内对同一成因必须给出同一结论。"""

    def test_the_denominator_is_not_empty_and_has_both_classes(self) -> None:
        """先证分母有效 —— 否则下面的逐成员对拍会恒绿。

        若某天两类合一（全可裁决或全不可裁决），本条立刻打红，提醒重新审视读侧是否
        还需要委派域内（而不是让对拍在一个退化的分母上空转）。
        """
        members = list(CF.SchemaAnomalyKind)
        assert members, "SchemaAnomalyKind 是空枚举 —— 对拍没有分母"
        verdicts = {m.adjudicable_by_value_choice for m in members}
        assert verdicts == {True, False}, (
            f"两类必须都非空，实际 {verdicts}；"
            "若枚举退化成一类，读侧的委派就失去了可观测性"
        )

    @pytest.mark.parametrize("anomaly", list(CF.SchemaAnomalyKind), ids=lambda m: m.value)
    def test_every_anomaly_member_agrees_with_the_domain(
        self, anomaly: CF.SchemaAnomalyKind
    ) -> None:
        """逐成员对拍。这是「读侧改回一刀切」时必须打红的那一条。"""
        item = _item(kind=CF.ConflictKind.schema, anomaly=anomaly)
        assert item.adjudicable_by_value_choice is anomaly.adjudicable_by_value_choice, (
            f"{anomaly.value}: 读侧判 {item.adjudicable_by_value_choice}，"
            f"域内判 {anomaly.adjudicable_by_value_choice} —— 两份实现又分叉了"
        )

    def test_the_value_adjudicable_members_are_actually_reachable(self) -> None:
        """可裁决的 schema 成因在读侧真的为 True（修复前这里全是 False）。"""
        adjudicable = [m for m in CF.SchemaAnomalyKind if m.adjudicable_by_value_choice]
        assert adjudicable, "没有可裁决成因 —— 本缺陷的修复无从验证"
        for anomaly in adjudicable:
            assert _item(anomaly=anomaly).adjudicable_by_value_choice is True

    def test_non_schema_conflicts_stay_adjudicable(self) -> None:
        """非 schema 冲突不受影响（修复不得把别的冲突类型带下水）。"""
        for kind in CF.ConflictKind:
            if kind is CF.ConflictKind.schema:
                continue
            item = _item(kind=kind, anomaly=None)
            assert item.adjudicable_by_value_choice is True, kind
            assert item.schema_anomaly_known is True, kind


# ═══════════════════════════════════════════════════════════════════════════
# 2. 读侧不得自己维护第二份名单
# ═══════════════════════════════════════════════════════════════════════════


class TestReadSideDelegatesInsteadOfReimplementing:
    """口径只能有一份 —— 读侧必须读域内的属性，不能自己列成因名单。

    否决过的方案正是「读侧照抄域内两类名单」：那是把一份分叉换成两份要同步维护的
    清单，下次加成员照样分叉。
    """

    @staticmethod
    def _body() -> ast.AST:
        src = textwrap.dedent(
            inspect.getsource(CR.ConflictPreviewItem.adjudicable_by_value_choice.fget)
        )
        return ast.parse(src)

    def test_it_reads_the_domain_property(self) -> None:
        tree = self._body()
        reads = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "adjudicable_by_value_choice"
        }
        assert reads, (
            "读侧没有引用域内的 adjudicable_by_value_choice —— "
            "它又在自己算了（本缺陷的原始形态）"
        )

    def test_it_does_not_enumerate_anomaly_members(self) -> None:
        """读侧的**代码**不得出现成因名 —— 那就是第二份名单。

        判据只看 AST 的代码节点：docstring 是函数体第一条 `Expr(Constant)`、`#` 注释
        根本不进 AST，两者都讲解释性的话（本函数的 docstring 就举了那两个可裁决成因
        当例子）。用文本匹配会把说明文字当成名单 —— 那是另一种形态的假阳。
        """
        tree = ast.parse(
            textwrap.dedent(
                inspect.getsource(CR.ConflictPreviewItem.adjudicable_by_value_choice.fget)
            )
        )
        fn = tree.body[0]
        assert isinstance(fn, ast.FunctionDef)
        nodes = list(fn.body)
        if nodes and isinstance(nodes[0], ast.Expr) and isinstance(nodes[0].value, ast.Constant):
            nodes = nodes[1:]  # 去掉 docstring
        literals: set[str] = set()
        names: set[str] = set()
        for stmt in nodes:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literals.add(node.value)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
                elif isinstance(node, ast.Name):
                    names.add(node.id)
        leaked = sorted(
            m.value
            for m in CF.SchemaAnomalyKind
            if m.value in literals or m.value in names or m.name in names
        )
        assert not leaked, f"读侧代码里出现了成因名单 {leaked} —— 口径必须只有域内一份"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 成因未知 vs 成因不可裁决（R1.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownCauseIsDistinctFromUnadjudicableCause:
    """两者都不可按值裁决，含义完全不同 —— 读侧若不分开，修没修都看不出。"""

    def test_history_row_without_cause_fails_closed(self) -> None:
        """V264 之前落的 schema 冲突没有成因。不拿「不知道」当「可以」。"""
        item = _item(kind=CF.ConflictKind.schema, anomaly=None)
        assert item.adjudicable_by_value_choice is False
        assert item.schema_anomaly_known is False

    def test_structural_cause_is_known_but_still_not_adjudicable(self) -> None:
        """行身份类异常：成因已知（要先修结构），不是「数据缺失」。"""
        structural = [
            m for m in CF.SchemaAnomalyKind if not m.adjudicable_by_value_choice
        ]
        assert structural, "没有不可裁决成因 —— 本条无分母"
        for anomaly in structural:
            item = _item(anomaly=anomaly)
            assert item.adjudicable_by_value_choice is False, anomaly
            assert item.schema_anomaly_known is True, anomaly

    def test_the_two_states_are_not_collapsed(self) -> None:
        """同样 adjudicable=False 的两种情形，必须靠 known 区分开。"""
        unknown = _item(anomaly=None)
        structural = _item(anomaly=CF.SchemaAnomalyKind.empty_row_identity)
        assert unknown.adjudicable_by_value_choice == structural.adjudicable_by_value_choice
        assert unknown.schema_anomaly_known != structural.schema_anomaly_known


# ═══════════════════════════════════════════════════════════════════════════
# 4. 生产路径：DB 列 → DTO（被调函数全绿 ≠ 调用方接上了）
# ═══════════════════════════════════════════════════════════════════════════


class TestPreviewItemCarriesTheCauseFromTheRow:
    """`_preview_item` 必须把列值真的传进 DTO。

    上面几组只证明 DTO 的属性算得对。若 `_preview_item` 漏传 `schema_anomaly=`，
    DTO 对拍依旧全绿而生产路径恒 `None` —— 整个修复等于没做。
    """

    def test_the_contract_index_signature_is_unchanged(self) -> None:
        """替身只提供 value_type。签名漂移时本条打红，免得替身悄悄偏离真实接口。"""
        sig = inspect.signature(CR.ContractIndex.resolve)
        assert list(sig.parameters) == ["self", "stable_key", "declared_row_key"]

    @staticmethod
    def _preview(row: WorkpaperSyncConflict) -> CR.ConflictPreviewItem:
        class _Index:
            def resolve(self, stable_key: str, *, declared_row_key: str | None = None) -> Any:
                class _L:
                    class value_type:  # noqa: N801
                        value = "text"

                return _L

        service = CR.ConflictResolutionService.__new__(CR.ConflictResolutionService)
        return service._preview_item(row, index=_Index())  # noqa: SLF001

    @pytest.mark.parametrize("anomaly", list(CF.SchemaAnomalyKind), ids=lambda m: m.value)
    def test_each_stored_cause_round_trips(self, anomaly: CF.SchemaAnomalyKind) -> None:
        item = self._preview(_row(anomaly.value))
        assert item.schema_anomaly is anomaly
        assert item.adjudicable_by_value_choice is anomaly.adjudicable_by_value_choice

    def test_null_cause_round_trips_as_unknown(self) -> None:
        item = self._preview(_row(None))
        assert item.schema_anomaly is None
        assert item.schema_anomaly_known is False

    @pytest.mark.parametrize("raw", ["", "not_a_member", "TYPE_NORMALIZATION_FAILURE"])
    def test_unparsable_cause_fails_closed_without_exploding(self, raw: str) -> None:
        """一行脏数据不该让整个冲突预览 500 —— 其余可裁决的冲突还得给人看。"""
        item = self._preview(_row(raw))
        assert item.schema_anomaly is None
        assert item.adjudicable_by_value_choice is False
        assert item.schema_anomaly_known is False

    def test_as_dict_exposes_cause_and_known_flag(self) -> None:
        """前端据此把「要先修结构」与「这是历史行」说清楚，而不是都显示「不可裁决」。"""
        payload = self._preview(
            _row(CF.SchemaAnomalyKind.type_normalization_failure.value)
        ).as_dict()
        assert payload["schema_anomaly"] == "type_normalization_failure"
        assert payload["schema_anomaly_known"] is True
        assert payload["adjudicable_by_value_choice"] is True

        unknown = self._preview(_row(None)).as_dict()
        assert unknown["schema_anomaly"] is None
        assert unknown["schema_anomaly_known"] is False
        assert unknown["adjudicable_by_value_choice"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. 写侧闭合性：to_row() 的键必须都是真实列
# ═══════════════════════════════════════════════════════════════════════════


class TestWriteSideProjectionIsClosedOverRealColumns:
    """`record_conflicts` 把 `to_row()` 的 payload 直接展开成 ORM 关键字参数。

    所以 payload 里出现一个不存在的列名不是「少写一列」，是写库当场 TypeError。
    """

    @staticmethod
    def _projection_keys() -> set[str]:
        src = textwrap.dedent(inspect.getsource(CF.ConflictRecord.to_row))
        tree = ast.parse(src)
        keys: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.add(k.value)
        return keys

    def test_every_projected_key_is_a_real_column(self) -> None:
        columns = {c.key for c in WorkpaperSyncConflict.__table__.columns}
        keys = self._projection_keys()
        assert keys, "没从 to_row() 里解析出键 —— 判据失效了（函数形态变了？）"
        assert keys <= columns, f"投影了不存在的列：{sorted(keys - columns)}"

    def test_the_cause_column_is_projected(self) -> None:
        """这就是根因：成因此前只在 digest_payload 里，列投影漏了它。"""
        assert "schema_anomaly" in self._projection_keys()

    def test_the_cause_is_also_in_the_digest(self) -> None:
        """摘要侧本来就带它。两处都带，才说明「落库」与「摘要」同口径。"""
        src = inspect.getsource(CF.ConflictRecord.digest_payload)
        assert "schema_anomaly" in src
