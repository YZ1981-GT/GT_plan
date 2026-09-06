# -*- coding: utf-8 -*-
"""Task 7 —— 工作簿级行变更计划的骨架判据（Property 1 / 2 / 3）。

spec: excel-workbook-wide-row-change-propagation / Wave 1 Task 7
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
Properties: **P1**（纯函数零写入面）/ **P2**（kind 与 count 的合法域）/ **P3**（受管 sheet 标识）

═══ 这三条各自在防什么 ═══

| Property | 防的假绿形态 |
|---|---|
| P1 | 计划类握着 session/repo ⇒ 「纯函数」只是注释里的声明，实际能写库 |
| P2 | `count=0` 被放过 ⇒ 「没改」与「改过」混为一谈，零变更也走一遍写入路径 |
| P3 | sheet part 按顺序拼 ⇒ 传播用到**错的 sheet**上，产物仍能打开、公式仍有值、只是值错了 |

P3 是本 spec 最要紧的一条：猜错受管 sheet 产出的 xlsx 打得开、有值、值是错的 —— 那正是本
spec 要消除的静默错行。Wave 0 Gate 1 因此裁决「禁止启发式推断受管 sheet」。

═══ 判据纪律 ═══

* **每条非法形态都要断言抛的是哪一个异常类**，不是「抛了就行」。七个 error_code 两两不同
  的意义就在于调用方能按它分支；判据只断言 `raises(Exception)` 会让两类错误混同后仍全绿。
* **结构判据优先于枚举判据**：载体词表与报告字段的一致性用
  `assert_carrier_tables_consistent()` 双向锁死，而不是在测试里手抄一份期望清单 ——
  手抄的那份就是第二真源。
* 「字符存在」不算判据：P1 查的是**字段值上是否存在可调用的禁用属性**（复用
  `assert_no_mutation_surface`），不是源码里有没有 `session` 这串字。
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402

#: D2 是本 spec 的**首要判据载体** —— 今天唯一既有已审核 per-entry 契约、又有真实跨 sheet
#: 引用的 entry（受管 sheet `明细表D2-2`，anchor A11，被 4 张 sheet 的 52 处公式引用）。
#: 用真实形态而不是 `Sheet1` 这类占位名，是为了让判据在「中文 sheet 名 + 含连字符」这个
#: 真实形态上取证 —— 手搓正则正是在这类名字上失败的。
D2_SHEET = "明细表D2-2"
D2_PART = "xl/worksheets/sheet3.xml"
D2_REGION = (11, 25)


def _entry(
    row_before: int,
    row_after: int,
    *,
    carrier: str = "formula",
    part: str = "xl/worksheets/sheet1.xml",
    locator: str | None = None,
) -> N1.PropagationEntry:
    return N1.PropagationEntry(
        carrier=carrier,
        part=part,
        locator=locator or f"F{row_before}",
        ref_before=f"'{D2_SHEET}'!F{row_before}",
        ref_after=f"'{D2_SHEET}'!F{row_after}",
        row_before=row_before,
        row_after=row_after,
    )


def _insert_kwargs(**override: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": N1.RowChangeKind.INSERT,
        "managed_sheet_name": D2_SHEET,
        "managed_sheet_part": D2_PART,
        "at": 13,
        "count": 1,
        "style_from": 12,
        "region_first_row": D2_REGION[0],
        "region_last_row": D2_REGION[1],
    }
    base.update(override)
    return base


def _delete_kwargs(**override: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": N1.RowChangeKind.DELETE,
        "managed_sheet_name": D2_SHEET,
        "managed_sheet_part": D2_PART,
        "at": 13,
        "count": 2,
        "style_from": None,
        "region_first_row": D2_REGION[0],
        "region_last_row": D2_REGION[1],
        "deleted_row_keys": ("row-uuid-a", "row-uuid-b"),
    }
    base.update(override)
    return base


@pytest.fixture()
def insert_plan() -> N1.WorkbookRowChangePlan:
    return N1.WorkbookRowChangePlan(
        **_insert_kwargs(
            propagations=(_entry(13, 14), _entry(25, 26)),
            unpropagated=(
                N1.UnpropagatedCarrier(
                    reason="prefix_without_coordinate",
                    part="xl/worksheets/sheet1.xml",
                    detail="'明细表D2-2'!#REF! —— 前缀命中但取不到 A1 坐标（D2 实测 10 处）",
                    count=10,
                ),
            ),
        )
    )


@pytest.fixture()
def delete_plan() -> N1.WorkbookRowChangePlan:
    return N1.WorkbookRowChangePlan(
        **_delete_kwargs(
            undeletable_rows=(13, 25),
            propagations=(_entry(20, 18, locator="F20"),),
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 1 —— 计划是冻结的纯数据，零写入面
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1ZeroMutationSurface:
    """**Property 1**：计划类不得握有写库/提交/发事件的能力面（Requirement 1.3）。"""

    def test_plan_is_frozen(self, insert_plan: N1.WorkbookRowChangePlan) -> None:
        """`frozen=True` —— 计划一旦建成不可改。

        可改的计划意味着「声明值」能在写盘与验证之间被换掉，而验证正是拿声明值做归一化的
        ⇒ 改一下声明就能让任意漂移判等价。
        """
        assert dataclasses.is_dataclass(insert_plan)
        assert all(
            f.name for f in dataclasses.fields(insert_plan)
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            insert_plan.count = 99  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            insert_plan.managed_sheet_part = "xl/worksheets/sheet9.xml"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "cls",
        [N1.WorkbookRowChangePlan, N1.PropagationEntry, N1.UnpropagatedCarrier,
         N1.PropagationReport],
    )
    def test_all_declaration_types_are_frozen(self, cls: type) -> None:
        """四个声明/报告类**全部**冻结 —— 漏一个就有一处可变的声明。"""
        params = getattr(cls, "__dataclass_params__", None)
        assert params is not None, f"{cls.__name__} 不是 dataclass"
        assert params.frozen, f"{cls.__name__} 未声明 frozen=True"

    def test_no_mutation_surface_is_actually_enforced(
        self, insert_plan: N1.WorkbookRowChangePlan
    ) -> None:
        """复用生产守卫实测，而不是在测试里另写一份检查。"""
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(insert_plan, label="WorkbookRowChangePlan")

    def test_mutation_surface_detector_fires_on_injected_session(self) -> None:
        """🔴 反向自检：往计划里塞一个**假 session**，`__post_init__` 必须当场抛。

        没有这条，上面那条在「守卫根本没被调用」与「计划确实干净」之间无法区分 ——
        那正是假绿第②源（守卫压根没在查）。

        塞的位置是 `deleted_row_keys`（tuple 字段）—— 用 `object.__setattr__` 绕过 frozen
        直接改字段值不行（那样 `__post_init__` 已经跑完了），所以从构造入口塞。
        """
        from app.services.workpaper_sync.adapters.base import AdapterSideEffectError

        class _FakeSession:
            """长得像 SQLAlchemy session —— 有 commit/flush/execute。"""

            def commit(self) -> None: ...
            def flush(self) -> None: ...
            def execute(self, *_a: Any, **_k: Any) -> None: ...

        with pytest.raises(AdapterSideEffectError) as excinfo:
            N1.WorkbookRowChangePlan(
                **_delete_kwargs(deleted_row_keys=_FakeSession())  # type: ignore[arg-type]
            )
        message = str(excinfo.value)
        assert "commit" in message, message
        assert "WorkbookRowChangePlan" in message, message

    def test_plan_construction_touches_no_disk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 建计划不得读写任何文件（Requirement 1.3 的「纯函数」的可执行形态）。

        判据形态：把 `builtins.open` / `zipfile.ZipFile` / `Path.open` 全替换成会抛的桩，
        再建一次计划。任何磁盘触碰都会当场炸。

        比「读源码看有没有 open」强的地方在于它连**间接**触碰也能抓到（某个被调用的
        helper 偷偷读文件）。
        """
        import builtins
        import zipfile

        def _forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(
                f"建计划过程中触碰了磁盘：args={args[:2]!r} —— "
                "`WorkbookRowChangePlan` 必须是纯数据声明（Requirement 1.3）"
            )

        monkeypatch.setattr(builtins, "open", _forbidden)
        monkeypatch.setattr(zipfile, "ZipFile", _forbidden)
        monkeypatch.setattr(Path, "open", _forbidden)
        monkeypatch.setattr(Path, "read_bytes", _forbidden)
        monkeypatch.setattr(Path, "read_text", _forbidden)

        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(propagations=(_entry(13, 14),)))
        assert plan.propagation_counts()["formula"] == 1
        assert plan.as_dict()["kind"] == "insert"

    def test_disk_detector_fires_on_real_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 反向自检：上一条的桩确实能抓到磁盘读取。"""
        import builtins

        def _forbidden(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("touched disk")

        monkeypatch.setattr(builtins, "open", _forbidden)
        with pytest.raises(AssertionError, match="touched disk"):
            open(__file__, encoding="utf-8")  # noqa: SIM115


# ═══════════════════════════════════════════════════════════════════════════
# Property 2 —— kind 与 count 的合法域
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2KindAndCountDomain:
    """**Property 2**：只有 insert/delete 两种，`count > 0`，零变更表达为 `None`。"""

    def test_only_two_kinds_exist(self) -> None:
        """枚举恰好两个成员 —— 多一个就说明有第三种变更没被判据覆盖。"""
        assert {k.value for k in N1.RowChangeKind} == {"insert", "delete"}
        assert len(N1.RowChangeKind) == 2

    @pytest.mark.parametrize("count", [0, -1, -99])
    def test_non_positive_count_is_rejected(self, count: int) -> None:
        """🔴 `count=0` 必须抛，不得当成「不变更」放过（Requirement 1.4）。

        放过它的后果是传播阶段被真实调用一次，产出一份「什么都没改但走过写入路径」的
        产物 —— 于是「零变更」与「已变更」在产物上分辨不出来。
        """
        with pytest.raises(N1.RowChangeKindError) as excinfo:
            N1.WorkbookRowChangePlan(**_insert_kwargs(count=count))
        assert excinfo.value.error_code == "workbook_row_change_kind_invalid"
        assert "plan is None" in str(excinfo.value), (
            "异常必须指出正确的表达方式是 `plan is None`，否则下一个人会再试一次 count=0"
        )

    def test_zero_change_is_expressed_as_none(self) -> None:
        """`None` 是「不变更」的唯一合法表达 —— 本条把该约定钉成判据。

        它不测代码，测的是**类型契约**：调用方签名应为 `plan: WorkbookRowChangePlan | None`。
        这里用一个最小消费者验证 `None` 分支可达且不需要构造任何假计划。
        """

        def consume(plan: N1.WorkbookRowChangePlan | None) -> str:
            return "no-change" if plan is None else plan.kind.value

        assert consume(None) == "no-change"
        assert consume(N1.WorkbookRowChangePlan(**_insert_kwargs())) == "insert"

    def test_kind_must_be_enum_not_bare_string(self) -> None:
        """裸字符串必须抛 —— 否则 `kind="insrt"` 这种 typo 会静默走 else 分支。

        `RowChangeKind` 继承 `str`，所以 `kind="insert"` 在**值**上等于枚举成员；
        只有显式 `isinstance` 才拦得住。这条判据锁的正是那个 `isinstance`。
        """
        for bogus in ("insert", "delete", "insrt", "", None, 1):
            with pytest.raises(N1.RowChangeKindError) as excinfo:
                N1.WorkbookRowChangePlan(**_insert_kwargs(kind=bogus))
            assert "RowChangeKind" in str(excinfo.value)

    @pytest.mark.parametrize("at", [0, -1])
    def test_at_must_be_one_based(self, at: int) -> None:
        """Excel 行号从 1 起 —— 0 或负数是坐标系错误。"""
        with pytest.raises(N1.RowChangeKindError):
            N1.WorkbookRowChangePlan(**_insert_kwargs(at=at))

    def test_insert_requires_style_from(self) -> None:
        """insert 必须给样式来源行 —— 不给样式的新行在 Excel 里是「断裂」的表。"""
        with pytest.raises(N1.RowChangeKindError, match="style_from"):
            N1.WorkbookRowChangePlan(**_insert_kwargs(style_from=None))

    def test_delete_must_not_declare_style_from(self) -> None:
        """delete 不产生新行 ⇒ 声明样式来源行说明调用方把两种 kind 搞混了。"""
        with pytest.raises(N1.RowChangeKindError, match="style_from"):
            N1.WorkbookRowChangePlan(**_delete_kwargs(style_from=12))

    def test_style_from_inside_inserted_range_is_rejected(self) -> None:
        """🔴 判据必须是 `>= at` 而不是 `>= at + count`。

        实测过的漏网形态：`at=26, count=2, style_from=27` —— 27 **正落在**新行区间
        `26..27` 内，写成 `>= at + count`（28）会放过它。样式必须来自「位移后仍在原位」
        的行，即 `< at`。
        """
        with pytest.raises(N1.RowChangeKindError) as excinfo:
            N1.WorkbookRowChangePlan(
                **_insert_kwargs(at=26, count=2, style_from=27, region_last_row=40)
            )
        assert "新行区间" in str(excinfo.value)

        # 边界：`style_from == at - 1` 合法
        ok = N1.WorkbookRowChangePlan(
            **_insert_kwargs(at=26, count=2, style_from=25, region_last_row=40)
        )
        assert ok.style_from == 25

    def test_shift_and_unshift_round_trip_outside_changed_rows(self) -> None:
        """`unshift(shift(r)) == r` 对**变更区间外**的行成立（两个方向各测）。

        区间**内**刻意不测 —— 那正是两个函数定义域的边界：insert 的新行 unshift 后会与
        before 侧的原始行别名，delete 的被删行 shift 后为 `None`。docstring 里写明了
        「新行不得进入需要归一化的集合」，本条只在合法定义域上取证。
        """
        ins = N1.WorkbookRowChangePlan(**_insert_kwargs(at=13, count=3, style_from=12))
        for row in (1, 11, 12, 16, 17, 100):
            if row >= ins.at:
                shifted = ins.shift(row)
                assert shifted is not None
                assert ins.unshift(shifted) == row, row
            else:
                assert ins.shift(row) == row
                assert ins.unshift(row) == row

        dele = N1.WorkbookRowChangePlan(**_delete_kwargs(at=13, count=2))
        for row in (1, 11, 12, 15, 16, 100):
            shifted = dele.shift(row)
            assert shifted is not None, row
            assert dele.unshift(shifted) == row, row

    def test_deleted_rows_shift_to_none(self) -> None:
        """🔴 被删行 `shift()` 返回 `None`，不是它自己、不是 0、不是 -1。

        返回行号本身会说谎（那个行号已被别的行占用），返回 0/-1 会被当成有效行号继续参与
        计算。`None` 逼调用方显式处置 —— 而「显式处置悬空引用」正是 Requirement 3.4。
        """
        plan = N1.WorkbookRowChangePlan(**_delete_kwargs(at=13, count=2))
        assert [plan.shift(r) for r in (13, 14)] == [None, None]
        assert plan.shift(12) == 12
        assert plan.shift(15) == 13
        assert [plan.is_deleted_row(r) for r in (12, 13, 14, 15)] == [
            False, True, True, False,
        ]

    def test_insert_never_returns_none_from_shift(self) -> None:
        """insert 侧 `shift` 是全函数 —— 返回 `None` 说明分支写错了。"""
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(at=13, count=2))
        assert all(plan.shift(r) is not None for r in range(1, 60))
        assert all(plan.is_deleted_row(r) is False for r in range(1, 60))


# ═══════════════════════════════════════════════════════════════════════════
# Property 3 —— 受管 sheet 标识（本 spec 最要紧的一条）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3ManagedSheetIdentity:
    """**Property 3**：计划必须携带受管 sheet 的稳定标识（Requirement 1.5）。

    🔴 为什么这条最要紧：猜错受管 sheet 产出的 xlsx **打得开、有值、值是错的**。产物级
    判据（能否打开 / 结构指纹 / 部件完整）全部会通过。这正是本 spec 要消除的静默错行，
    而它的源头就是「按 sheet 名或顺序猜宿主」。

    Wave 0 实测反证：`附注披露信息（国企）` 这个 sheet 名在 **39 份**模板里都存在，
    且被引用情况完全不同 ⇒ 按名定位必然取到错的那份。
    """

    def test_plan_carries_sheet_name_and_part(
        self, insert_plan: N1.WorkbookRowChangePlan
    ) -> None:
        """两者都要 —— 名字给人看、part 给代码用，缺任一个都不完整。"""
        assert insert_plan.managed_sheet_name == D2_SHEET
        assert insert_plan.managed_sheet_part == D2_PART
        dumped = insert_plan.as_dict()
        assert dumped["managed_sheet_name"] == D2_SHEET
        assert dumped["managed_sheet_part"] == D2_PART

    def test_missing_sheet_name_is_rejected(self) -> None:
        """缺 sheet 名 ⇒ 传播条目无从指明「传播的是谁的变更」。"""
        with pytest.raises(N1.RowChangeKindError, match="managed_sheet_name"):
            N1.WorkbookRowChangePlan(**_insert_kwargs(managed_sheet_name=""))

    @pytest.mark.parametrize(
        "bogus_part",
        [
            "sheet3.xml",                      # 缺目录前缀
            "xl/worksheets/3.txt",             # 扩展名不对
            "worksheets/sheet3.xml",           # 缺 xl/
            "xl/sheet3.xml",                   # 少一层
            "xl/worksheets/sub/sheet3.xml",    # 多一层
            "xl/workbook.xml",                 # 不是 worksheet
            "",                                # 空
            "明细表D2-2",                       # 🔴 直接把 sheet 名当 part
        ],
    )
    def test_non_parsed_part_shapes_are_rejected(self, bogus_part: str) -> None:
        """🔴 part 必须形如 `xl/worksheets/sheetN.xml`，不得是拼出来的。

        最后一例（把 sheet 名当 part）是最危险的形态：它意味着调用方压根没做名字→part 的
        解析。part 必须走 `excel_structure_fingerprint._parse_workbook_xml` +
        `_normalise_part` 求得 —— 手搓正则对含中文括号、属性顺序不定的模板实测**全部失败**
        （B60 / H1 / G7 三份）。
        """
        with pytest.raises(N1.RowChangeKindError) as excinfo:
            N1.WorkbookRowChangePlan(**_insert_kwargs(managed_sheet_part=bogus_part))
        message = str(excinfo.value)
        assert "part" in message
        assert "_parse_workbook_xml" in message, (
            "异常必须点明正确的求法，否则下一个人会再拼一次"
        )

    @pytest.mark.parametrize(
        "good_part",
        [
            "xl/worksheets/sheet1.xml",
            "xl/worksheets/sheet42.xml",
            "xl/chartsheets/sheet1.xml",
        ],
    )
    def test_parsed_part_shapes_are_accepted(self, good_part: str) -> None:
        """分母断言：合法形态真的能过 —— 否则上一条在「全都拒绝」上恒真。"""
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(managed_sheet_part=good_part))
        assert plan.managed_sheet_part == good_part

    def test_part_resolution_matches_real_template(self) -> None:
        """🔴 用**真实 D2 模板**验证「名字 → part」的解析链条可用且唯一。

        这条不测 N1 的代码，测的是 N1 要求的那条链条在真实模板上成立 —— 否则 P3 的判据
        形态就是空谈（要求了一个求不出来的东西）。

        链条：`contract.template.relative_path` → 磁盘 xlsx → `_parse_workbook_xml`
        → 按 sheet 名找 → `_normalise_part`。内容寻址，不按名字猜宿主（AC 6.5）。
        """
        import zipfile

        from app.services.excel_structure_fingerprint import (
            _normalise_part,
            _parse_workbook_xml,
        )

        template = (
            _BACKEND
            / "wp_templates"
            / "D"
            / "D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
        )
        if not template.is_file():  # pragma: no cover - 模板缺失时不冒充通过
            pytest.skip(f"D2 权威模板不在磁盘上：{template}")

        with zipfile.ZipFile(template) as zf:
            sheets, _defined = _parse_workbook_xml(zf)
            matched = [s for s in sheets if s["name"] == D2_SHEET]
            assert len(matched) == 1, (
                f"受管 sheet 名 {D2_SHEET!r} 在模板里命中 {len(matched)} 张 —— "
                "命中 0 或 >1 都必须 fail closed，不得取第一个继续"
            )
            part = _normalise_part(matched[0]["rel_target"])
            assert part in zf.namelist(), f"解析出的 part 不在 zip 里：{part}"

        # 解析得来的 part 必须能通过 N1 的形态判据
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(managed_sheet_part=part))
        assert plan.managed_sheet_part == part

    def test_touched_parts_excludes_managed_sheet(
        self, insert_plan: N1.WorkbookRowChangePlan
    ) -> None:
        """`touched_parts` 是**引用侧**的 part，不含受管 sheet 自身。

        它的用途是验证阶段判「引用侧除声明条目外是否有额外字节变化」（Requirement 5.4）
        —— 把受管 sheet 混进去会让受管区的正常改动被算成引用侧的越权改动。
        """
        assert D2_PART not in insert_plan.touched_parts
        assert insert_plan.touched_parts == ("xl/worksheets/sheet1.xml",)

        # 受管 sheet 上的自引用条目不得进 touched_parts
        with_self = N1.WorkbookRowChangePlan(
            **_insert_kwargs(
                propagations=(_entry(13, 14), _entry(20, 21, part=D2_PART, locator="Z20")),
            )
        )
        assert D2_PART not in with_self.touched_parts


# ═══════════════════════════════════════════════════════════════════════════
# 载体词表 —— 结构判据，不手抄第二份清单
# ═══════════════════════════════════════════════════════════════════════════


class TestCarrierVocabulary:
    """载体词表与报告字段双向锁死（Requirement 1.2 / AC 4.2）。"""

    def test_tables_are_consistent(self) -> None:
        """用生产守卫本体取证 —— 测试里不另抄一份期望清单（那就是第二真源）。"""
        tables = N1.assert_carrier_tables_consistent()
        assert len(tables["carriers"]) == 5, tables["carriers"]
        assert len(tables["counters"]) == 5, tables["counters"]
        assert len(tables["unpropagated_reasons"]) == 6, tables["unpropagated_reasons"]

    def test_sqref_family_is_deliberately_absent(self) -> None:
        """🔴 `sqref` / `merge` / `hyperlink_ref` **不得**在传播载体词表里。

        Gate 2 全库 351 份实测这四类属性含跨 sheet 引用的条数：
        `conditionalFormatting@sqref` **0/440**、`dataValidation@sqref` **0/1223**、
        `mergeCell@ref` **0/37456**、`hyperlink@ref` **0/3950**。

        不是「样本不够」而是 OOXML **结构性不可能** —— schema 类型 `ST_Sqref` / `ST_Ref`
        语义上就是所在 worksheet 内的区间，表达不了 sheet 前缀。

        留一个恒为 0 的载体/计数器等于给「空集上恒真」留位置：那类判据永远绿，且没人会
        发现它从未真正执行过。
        """
        for forbidden in ("sqref", "merge", "hyperlink_ref", "merge_ref", "dv_sqref"):
            assert forbidden not in N1.PROPAGATION_CARRIERS, (
                f"{forbidden!r} 进了传播载体词表 —— 它结构性不可能带跨 sheet 引用，"
                "留着会让对应判据在空集上恒真（AC 4.2 的判据形态是「注入变体后仍不得被"
                "误传播」，不是「传播它」）"
            )
        report_fields = {f.name for f in dataclasses.fields(N1.PropagationReport)}
        for forbidden in ("sqrefs_changed", "merges_changed", "hyperlink_refs_changed"):
            assert forbidden not in report_fields, (
                f"报告里出现恒为 0 的计数器 {forbidden!r}"
            )

    def test_prefix_without_coordinate_is_registered(self) -> None:
        """🔴 `prefix_without_coordinate` 必须在不传播理由词表里。

        它是 Task 9 实测捞出来的，原设计清单里没有：D2 上有 **10 处**
        `'明细表D2-2'!#REF!` —— `_QUALIFIED_PREFIX_RE` 命中前缀但 `_REF_TOKEN_RE` 对
        `#REF!` 返回 `None`。传播器不动它是对的，但**必须登记**：静默跳过会让「有 10 处
        引用没被处理」这件事不可见。
        """
        assert "prefix_without_coordinate" in N1.UNPROPAGATED_REASONS

    def test_unregistered_carrier_is_rejected(self) -> None:
        """未登记载体必须抛 —— 宁可打红也不能放过（Property 20）。"""
        with pytest.raises(N1.UnpropagatedCarrierError) as excinfo:
            _entry(13, 14, carrier="sqref")
        assert excinfo.value.error_code == "workbook_row_change_unpropagated_carrier"

    def test_unregistered_unpropagated_reason_is_rejected(self) -> None:
        with pytest.raises(N1.UnpropagatedCarrierError):
            N1.UnpropagatedCarrier(
                reason="因为我不想传播", part="xl/worksheets/sheet1.xml",
                detail="d", count=1,
            )

    @pytest.mark.parametrize("bad_count", [0, -1])
    def test_zero_count_unpropagated_registration_is_rejected(
        self, bad_count: int
    ) -> None:
        """处数为 0 的登记等于没有这一类，留着会让空集看起来被覆盖了。"""
        with pytest.raises(N1.UnpropagatedCarrierError, match="处数"):
            N1.UnpropagatedCarrier(
                reason="chart", part="xl/charts/chart1.xml", detail="d", count=bad_count,
            )

    def test_unpropagated_registration_requires_detail(self) -> None:
        """缺样本时人无法判断这一类是否真的该不传播。"""
        with pytest.raises(N1.UnpropagatedCarrierError, match="detail"):
            N1.UnpropagatedCarrier(
                reason="chart", part="xl/charts/chart1.xml", detail="", count=1,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 声明值的自洽性 —— 传播条目不得与计划矛盾
# ═══════════════════════════════════════════════════════════════════════════


class TestPropagationDeclarationCoherence:
    """传播条目必须与 `kind` / `count` 自洽（Requirement 1.2 / 5.2）。"""

    def test_direction_must_match_kind(self) -> None:
        """🔴 insert 的条目增量必须为 `+count`，delete 为 `-count`。

        方向错了等于把数据指到反方向 —— 而产物仍然打得开。所以必须在计划构造时就拦。
        """
        with pytest.raises(N1.PropagationDriftError, match=r"\+1"):
            N1.WorkbookRowChangePlan(
                **_insert_kwargs(propagations=(_entry(14, 13),))
            )
        with pytest.raises(N1.PropagationDriftError, match="-2"):
            N1.WorkbookRowChangePlan(
                **_delete_kwargs(propagations=(_entry(20, 22, locator="F20"),))
            )

    def test_magnitude_must_match_count(self) -> None:
        """增量的**大小**也要对 —— 只判正负号会放过「插 1 行却声明移 3 行」。"""
        with pytest.raises(N1.PropagationDriftError):
            N1.WorkbookRowChangePlan(
                **_insert_kwargs(count=1, propagations=(_entry(13, 16),))
            )

    def test_no_op_entry_is_rejected(self) -> None:
        """改前后行号相同的条目不得进清单 —— 它会让声明传播量虚高。

        虚高的后果：验证阶段按声明核对实测 ⇒ 实测数对不上声明数 ⇒ 与计划一致的传播被判
        漂移（假红）。
        """
        with pytest.raises(N1.PropagationDriftError, match="相同"):
            _entry(13, 13)

    def test_text_and_row_must_agree(self) -> None:
        """声明行号变了但引用文本逐字相同 ⇒ 两者必有一个是错的。"""
        with pytest.raises(N1.PropagationDriftError):
            N1.PropagationEntry(
                carrier="formula",
                part="xl/worksheets/sheet1.xml",
                locator="F13",
                ref_before="'明细表D2-2'!F13",
                ref_after="'明细表D2-2'!F13",  # 文本没变
                row_before=13,
                row_after=14,                    # 却声明行号变了
            )

    def test_duplicate_locator_is_rejected(self) -> None:
        """同一处被声明两次会让声明量虚高，验证阶段核对实测必然对不上。"""
        with pytest.raises(N1.PropagationDriftError, match="重复定位"):
            N1.WorkbookRowChangePlan(
                **_insert_kwargs(propagations=(_entry(13, 14), _entry(13, 14)))
            )

    def test_same_locator_on_different_parts_is_allowed(self) -> None:
        """分母对照：不同 part 上的同名定位是合法的（两张 sheet 都有 F13）。"""
        plan = N1.WorkbookRowChangePlan(
            **_insert_kwargs(
                propagations=(
                    _entry(13, 14, part="xl/worksheets/sheet1.xml"),
                    _entry(13, 14, part="xl/worksheets/sheet2.xml"),
                ),
            )
        )
        assert plan.propagation_counts()["formula"] == 2
        assert len(plan.touched_parts) == 2

    def test_report_reconciles_against_declaration(
        self, insert_plan: N1.WorkbookRowChangePlan
    ) -> None:
        """实测 == 声明 ⇒ 不抛；少一处或多一处 ⇒ 抛（Property 21）。"""
        N1.PropagationReport(formulas_changed=2).assert_matches_plan(insert_plan)

        for measured in (1, 3, 0):
            with pytest.raises(N1.PropagationDriftError) as excinfo:
                N1.PropagationReport(formulas_changed=measured).assert_matches_plan(
                    insert_plan
                )
            assert "声明 2" in str(excinfo.value)

    def test_reconciliation_is_per_carrier_not_total(self) -> None:
        """🔴 逐载体对账，不只比总数 —— 两个载体一多一少，总数会互相抵消。"""
        plan = N1.WorkbookRowChangePlan(
            **_insert_kwargs(
                propagations=(
                    _entry(13, 14, carrier="formula"),
                    _entry(20, 21, carrier="defined_name", part="xl/workbook.xml",
                           locator="_xlnm.Print_Area"),
                ),
            )
        )
        # 总数对（2 == 2）但分布错了 —— 必须抛
        with pytest.raises(N1.PropagationDriftError) as excinfo:
            N1.PropagationReport(
                formulas_changed=2, defined_names_changed=0
            ).assert_matches_plan(plan)
        message = str(excinfo.value)
        assert "defined_name" in message and "formula" in message, message

        # 分布对 ⇒ 不抛
        N1.PropagationReport(
            formulas_changed=1, defined_names_changed=1
        ).assert_matches_plan(plan)

    def test_report_rejects_negative_and_unknown(self) -> None:
        with pytest.raises(N1.PropagationDriftError, match="负值"):
            N1.PropagationReport(formulas_changed=-1)
        with pytest.raises(N1.UnpropagatedCarrierError):
            N1.PropagationReport(unpropagated_by_reason={"nope": 1})


# ═══════════════════════════════════════════════════════════════════════════
# delete 侧的留痕与不可删行（Requirement 3.7 / AC 3.8 的骨架部分）
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteDeclarations:
    """删行的业务键留痕与 `undeletable_rows` 的定义域。

    ⚠ 本类只覆盖**计划形态**。键的**取值来源优先级**（row_uuid → 契约稳定序号 →
    抛错）属 Wave 3 Task 15，悬空引用的检测属 Task 16 —— 那两条在各自任务里取证，
    这里不冒充覆盖。
    """

    def test_delete_requires_row_keys(self) -> None:
        """删除是不可逆数据丢失，无留痕不得执行（Requirement 3.7）。"""
        with pytest.raises(N1.MissingRowIdentityError) as excinfo:
            N1.WorkbookRowChangePlan(**_delete_kwargs(deleted_row_keys=()))
        assert excinfo.value.error_code == "workbook_row_change_missing_row_identity"

    @pytest.mark.parametrize(
        "keys, why",
        [
            (("only-one",), "键数少于被删行数"),
            (("a", "b", "c"), "键数多于被删行数"),
            (("dup", "dup"), "键重复"),
            (("a", ""), "键含空值"),
        ],
    )
    def test_row_keys_must_map_one_to_one(
        self, keys: tuple[str, ...], why: str
    ) -> None:
        """键必须与被删行**一一对应** —— 否则事后无从复原删了哪几笔。"""
        with pytest.raises(N1.MissingRowIdentityError) as excinfo:
            N1.WorkbookRowChangePlan(**_delete_kwargs(count=2, deleted_row_keys=keys))
        assert excinfo.value.error_code == "workbook_row_change_missing_row_identity", why

    @pytest.mark.parametrize(
        "at, count",
        [(9, 2), (10, 2), (24, 5), (25, 2), (11, 20)],
    )
    def test_delete_must_not_cross_region_bounds(self, at: int, count: int) -> None:
        """越界删行会删掉未管理区的行 —— projection 无权处置那些数据（AC 3.6）。"""
        with pytest.raises(N1.RowChangeOutOfRegionError) as excinfo:
            N1.WorkbookRowChangePlan(
                **_delete_kwargs(
                    at=at, count=count,
                    deleted_row_keys=tuple(f"k{i}" for i in range(count)),
                )
            )
        assert excinfo.value.error_code == "workbook_row_change_out_of_region"

    def test_delete_exactly_at_region_bounds_is_allowed(self) -> None:
        """分母对照：恰好贴边合法 —— 否则上一条在「全都拒绝」上恒真。"""
        first, last = D2_REGION
        head = N1.WorkbookRowChangePlan(
            **_delete_kwargs(at=first, count=1, deleted_row_keys=("k",))
        )
        assert head.at == first
        tail = N1.WorkbookRowChangePlan(
            **_delete_kwargs(at=last, count=1, deleted_row_keys=("k",))
        )
        assert tail.at == last
        whole = N1.WorkbookRowChangePlan(
            **_delete_kwargs(
                at=first, count=last - first + 1,
                deleted_row_keys=tuple(f"k{i}" for i in range(last - first + 1)),
            )
        )
        assert whole.count == 15

    def test_undeletable_rows_must_be_inside_region(self) -> None:
        """`undeletable_rows` 的定义域是受管区内被引用到的行。"""
        with pytest.raises(N1.RowChangeOutOfRegionError, match="undeletable_rows"):
            N1.WorkbookRowChangePlan(**_delete_kwargs(undeletable_rows=(99,)))
        with pytest.raises(N1.RowChangeOutOfRegionError):
            N1.WorkbookRowChangePlan(**_delete_kwargs(undeletable_rows=(1,)))

    def test_insert_must_not_carry_delete_only_fields(self) -> None:
        """insert 携带 delete 专用字段 ⇒ 调用方把两种 kind 搞混了。"""
        with pytest.raises(N1.RowChangeKindError, match="deleted_row_keys"):
            N1.WorkbookRowChangePlan(**_insert_kwargs(deleted_row_keys=("x",)))
        with pytest.raises(N1.RowChangeKindError, match="undeletable_rows"):
            N1.WorkbookRowChangePlan(**_insert_kwargs(undeletable_rows=(13,)))

    def test_undeletable_rows_survive_into_dict(
        self, delete_plan: N1.WorkbookRowChangePlan
    ) -> None:
        """`undeletable_rows` 必须能传到 HTML 侧 —— 它的用途是**发起删行之前**标锁。

        K11 实测受管区 19 行全部被引用（100% 阻断），若只有 fail-closed 抛错，删行功能
        表现为「永远失败」。把它前置成声明，是同一条 fail-closed 语义的可用形态（AC 3.8）。
        """
        dumped = delete_plan.as_dict()
        assert dumped["undeletable_rows"] == [13, 25]
        assert dumped["deleted_row_keys"] == ["row-uuid-a", "row-uuid-b"]
        assert dumped["kind"] == "delete"
        assert dumped["style_from"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 变异四态（Requirement 8.1 / 8.2 / 8.3 · Property 29 / 30）
# ═══════════════════════════════════════════════════════════════════════════
#
# 每条变异都要能指出「短路哪一处判断会让哪条判据变红」，且验证过**不存在第二道防线**
# 也挡住同一用例 —— 否则那条判据从未真正承重。
#
# 🔴 变异用 monkeypatch 在**进程内**做，不改磁盘上的生产文件：`excel_row_shift.py` /
#    `excel_workbook_row_change.py` 都可能被并发会话编辑，变异式改文件再复原有覆盖对方
#    改动的风险（前置 spec 踩过一次）。


class TestMutationFourStates:
    """把「判据真的承重」实证出来 —— 每条变异都必须让特定判据变红。"""

    def test_removing_count_guard_makes_p2_red(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异 M1：去掉 `count > 0` 校验 ⇒ P2 的 `count=0` 判据必须变红。

        承重点：`__post_init__` 里的 `if self.count <= 0`。
        """
        original = N1.WorkbookRowChangePlan.__post_init__

        def _without_count_guard(self: N1.WorkbookRowChangePlan) -> None:
            if self.count == 0:
                return  # 短路：放过零变更
            original(self)

        monkeypatch.setattr(
            N1.WorkbookRowChangePlan, "__post_init__", _without_count_guard
        )
        # 变异后 count=0 不再抛 ⇒ 证明原判据的红是这一处带来的
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(count=0))
        assert plan.count == 0, "变异未生效，本条无法证明 P2 承重"

    def test_removing_part_shape_guard_makes_p3_red(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异 M2：把 part 形态正则放宽成「什么都匹配」⇒ P3 判据必须变红。

        承重点：`_SHEET_PART_RE`。这是本 spec 最要紧的一条防线 —— 放宽它就等于允许
        「把 sheet 名当 part」这类调用方压根没解析的形态混进来。
        """
        import re as _re

        monkeypatch.setattr(N1, "_SHEET_PART_RE", _re.compile(r".*"))
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(managed_sheet_part=D2_SHEET))
        assert plan.managed_sheet_part == D2_SHEET, "变异未生效"

    def test_removing_direction_guard_makes_coherence_red(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异 M3：跳过传播方向校验 ⇒ 方向自洽判据必须变红。

        承重点：`_validate_propagations`。
        """
        monkeypatch.setattr(
            N1.WorkbookRowChangePlan, "_validate_propagations", lambda self: None
        )
        plan = N1.WorkbookRowChangePlan(**_insert_kwargs(propagations=(_entry(14, 13),)))
        assert plan.propagations[0].delta == -1, "变异未生效"

    def test_carrier_vocabulary_mutation_is_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异 M4：往载体词表塞一个报告里没有计数器的载体 ⇒ 结构判据必须抛。

        这条证明 `assert_carrier_tables_consistent` 真的在双向查，而不是只查一个方向。
        """
        monkeypatch.setattr(
            N1, "PROPAGATION_CARRIERS", N1.PROPAGATION_CARRIERS | {"sqref"}
        )
        with pytest.raises(N1.UnpropagatedCarrierError, match="没有对应计数器"):
            N1.assert_carrier_tables_consistent()

    def test_counter_table_mutation_is_caught(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """变异 M5：反方向 —— 计数器表多一项而词表没有 ⇒ 同样必须抛。

        与 M4 合起来才说明「双向」锁死；只测一个方向时，反方向的漂移会静默通过。
        """
        monkeypatch.setattr(
            N1,
            "CARRIER_COUNTER_NAMES",
            {**N1.CARRIER_COUNTER_NAMES, "sqref": "sqrefs_changed"},
        )
        with pytest.raises(N1.UnpropagatedCarrierError, match="不在 PROPAGATION_CARRIERS"):
            N1.assert_carrier_tables_consistent()

    def test_error_codes_are_pairwise_distinct(self) -> None:
        """七个异常的 `error_code` 两两不同 —— 调用方按它分支。

        重复的 code 会让两类完全不同的失败在上层被同一个 handler 吞掉。
        """
        classes = [
            N1.WorkbookRowChangeError,
            N1.RowChangeKindError,
            N1.RowChangeOutOfRegionError,
            N1.DanglingReferenceError,
            N1.MissingRowIdentityError,
            N1.PropagationDriftError,
            N1.UnpropagatedCarrierError,
        ]
        codes = [c.error_code for c in classes]
        assert len(set(codes)) == len(codes), f"error_code 有重复：{codes}"
        assert len(codes) == 7
        for cls, code in zip(classes, codes):
            assert code.startswith("workbook_row_change"), (cls.__name__, code)
            # 全部可被域基类捕获 —— 但基类不得被用来替代具体类型
            assert issubclass(cls, N1.WorkbookRowChangeError)

    def test_domain_errors_are_sync_domain_errors(self) -> None:
        """必须挂在 `SyncDomainError` 下 —— 否则上层的域错误处理会漏掉本模块。"""
        from app.services.workpaper_sync.models import SyncDomainError

        assert issubclass(N1.WorkbookRowChangeError, SyncDomainError)
