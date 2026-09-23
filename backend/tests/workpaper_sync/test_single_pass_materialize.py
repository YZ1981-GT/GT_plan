"""多 binding 底稿物化的**趟数判据**（spec oo-single-pass-materialize-and-room-leave）。

Requirements: 1.1 / 1.5　　Property: **P1**

═══ 为什么判据是调用计数 ═══

单趟化的收益只能与「少写了东西」区分开一次：把调用计数固定下来。判据是**调用计数**而不是
耗时 —— 耗时在不同机器上必然漂移（同一台机器上开着 tracemalloc 跑就从 20s 变 69s）。

═══ 真库实测（entry `xlsx/gt-d4-operating-revenue`，46 sheet / **39 个 binding**）═══

| 量 | 链式（改动前 / 现回落路径） | 单趟（任务 3 落地后的默认路径） |
|---|---|---|
| 写入趟数 | **39**（一 binding 一趟） | **1** |
| `openpyxl.load_workbook` 合计 | **83** | **7** |
| 其中 substrate 链（文件） | **78** = 39 趟 × `data_only` 两视图 | **2** = 两视图各一次，39 binding 共享 |
| 其中 BytesIO（固定开销） | **5** = 转置 sheet 4 + 整簿指纹 1 | **5**（不随 binding 数变，单趟带不走） |
| `Workbook.save` | **2**（全来自转置 sheet；主写入是 zip 级字节改写，不过 openpyxl） | **2**（同上，未变） |
| 墙钟 | 16.7s | **5.3s** |
| tracemalloc 峰值 | 118.1MiB | **26.0MiB** |

证据：`docs/operations/evidence/oo-single-pass-materialize/`（`baseline-chained.json` /
`current-default.json`）。

🔴 **实测纠正了两处原始估算**（触发 requirements 1.1 改写为「与 binding 数解耦」）：
`load_workbook` 总数是 83 不是 39，随 binding 数线性增长的只有那 78 次；`Workbook.save`
是 2 且与 binding 数**无关** ⇒「save 降到 1」对本 entry 本就不成立。需求 1.1 要解耦的、
也是本文件钉住的，是 substrate 链上那 78 → 2。

═══ 链式路径为什么还在 ═══

它**不是**死代码，而是 decline 三条的正式回落路径（插行 / openpyxl 全量重写 / 同格
payload 冲突）。因此 `force_chained_path()` 与 `test_chained_fallback_path_call_counts`
继续留着当回归网：谁把回落路径的趟数从 39 改成别的（不管变多变少），这里立刻红。
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.contracts import FieldMode
from app.services.workpaper_sync.excel_extract import (
    ExcelIdentityBinding,
    workbook_read_scope,
)
from app.services.workpaper_sync.excel_materialize import (
    CellWrite,
    CellWriteKind,
    MaterializePlan,
    MaterializePlanStep,
    _cross_binding_payload_conflicts,
    _payload_conflict_decline_reason,
    _plan_materialize_step,
    coord_sort_key,
)
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    MaterializeCallCounter,
    build_world,
    force_chained_path,
)

#: 链式（回落）路径实测。改这些数必须同时刷新 `baseline-chained.json`。
BASELINE_BINDINGS = 39
BASELINE_LOADS = 83
BASELINE_SAVES = 2
#: 落在**文件**上的解析 = substrate 链（需求 1.1 说的就是这一项）：39 趟 × 两视图。
BASELINE_SUBSTRATE_LOADS = 78
#: 落在 BytesIO 上的固定开销：转置 sheet 4 次 + 整簿指纹 1 次，不随 binding 数变。
BASELINE_IN_MEMORY_LOADS = 5

#: 单趟路径实测（需求 1.1 的上界是 `≤ 2`，实测**恰好** 2 —— 两个 data_only 视图各一次）。
SINGLE_PASS_SUBSTRATE_LOADS = 2
SINGLE_PASS_LOADS = SINGLE_PASS_SUBSTRATE_LOADS + BASELINE_IN_MEMORY_LOADS

#: 真库 D4 的**完整**跨 binding 坐标碰撞集合（design 附录 A.3 实测）：D4-9 的表级标量表
#: `customer_totals` 被同 sheet 两个行 binding 共同持有 ⇒ 同 4 格各写一遍，payload 全同。
D4_BENIGN_COLLISIONS = (
    "xl/worksheets/sheet14.xml!C24",
    "xl/worksheets/sheet14.xml!E24",
    "xl/worksheets/sheet14.xml!C38",
    "xl/worksheets/sheet14.xml!E38",
)
D4_COLLIDING_BINDINGS = ("customer_current_rows", "customer_prior_rows")


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    """真 D4 模板 + 真契约 + 真 39 binding；module 作用域（铺一次 world 要十几秒）。

    projection 取自 substrate 自身的反读结果 ⇒ 必然覆盖**每个** binding 的受管区。
    """
    return build_world(tmp_path_factory.mktemp("d4-single-pass"))


@pytest.fixture(scope="module")
def d4_steps(world: D4World) -> list[MaterializePlanStep]:
    """全部 39 个 binding 的写入计划，都算在**原始** substrate 字节上（= 单趟路径的做法）。

    走生产内核 `_plan_materialize_step`（与 `materialize_projection_single_pass` 同一份），
    不复刻 —— 复刻一份就是在测「复刻得对不对」。
    """
    adapter = world.adapter
    source_bytes = world.base.read_bytes()
    with workbook_read_scope():
        return [
            _plan_materialize_step(
                substrate=world.base,
                projection=world.projection,
                definitions=adapter.definitions,
                binding=binding,
                substrate_role=adapter.substrate_role,
                substrate_kind=adapter.substrate_kind,
                substrate_state=adapter.substrate_state,
                source_bytes=source_bytes,
                capability=adapter.capability,
                intended_formulas=None,
                limits=adapter._limits,
                retain_identity_inventory=(
                    binding.table_key == adapter.binding.table_key
                ),
            )
            for binding in adapter._all_bindings()
        ]


def test_the_real_d4_entry_really_has_many_bindings(world: D4World) -> None:
    """反向自检：harness 必须真的是**多** binding，否则下面那条趟数判据是重言式。

    单 binding 时 `ExcelSyncAdapter` 走的是完全另一条分支（`len(bindings) == 1`），
    在它上面测趟数什么都证明不了。
    """
    assert world.binding_count == BASELINE_BINDINGS, (
        f"binding 数 {world.binding_count} ≠ 基线 {BASELINE_BINDINGS} —— "
        "要么 harness 与生产路径脱钩了，要么真实契约的受管表集合变了。"
        "后者是正当变化，但必须同时刷新本文件的基线常数与 "
        "docs/operations/evidence/oo-single-pass-materialize/baseline-chained.json"
    )


def test_chained_fallback_path_call_counts(world: D4World) -> None:
    """回落路径（逐 binding 链式）上 39 趟 / 83 次 load / 2 次 save，逐个钉住。

    🔴 这条不是「改动前的历史」——链式路径是 decline 三条（插行 / openpyxl 全量重写 /
    同格 payload 冲突）的正式回落路径，仍会在真库上被走到。它是回归网：谁改了回落路径的
    趟数构成，这里立刻红。
    """
    counter = MaterializeCallCounter()
    with force_chained_path(), counter.installed():
        staged = world.materialize("chained-baseline.xlsx")

    assert staged.is_file() and staged.read_bytes()[:2] == b"PK", "产物不是 xlsx"

    # ① 趟数 == binding 数：这是链式实现的**结构事实**（一 binding 一趟），
    #    也就是「39 趟」这个说法的来源。
    assert counter.trip_count == world.binding_count == BASELINE_BINDINGS, (
        f"链式趟数 {counter.trip_count}（binding {world.binding_count}）"
        f" ≠ 基线 {BASELINE_BINDINGS}；趟数：{counter.trips[:5]}…"
    )
    assert counter.single_pass_trip_count == 0, (
        "`force_chained_path()` 应当把单趟入口摘掉，但计数器看到了单趟趟次 "
        f"{counter.single_pass_trips} ⇒ 回落路径的基线被单趟污染了"
    )

    # ② load/save 的实测总数。按**实际调用计数**断言（需求 1.1），一个数都不许约等于。
    assert counter.load_count == BASELINE_LOADS, (
        f"load_workbook {counter.load_count} ≠ 基线 {BASELINE_LOADS}；"
        f"调用点分布：{dict(counter.load_sites.most_common())}"
    )
    assert counter.save_count == BASELINE_SAVES, (
        f"Workbook.save {counter.save_count} ≠ 基线 {BASELINE_SAVES}；"
        f"调用点分布：{dict(counter.save_sites.most_common())}"
    )

    # ③ 83 不是一个魔数：拆成「随 binding 数线性增长的」与「固定的」两段。需求 1.1 要
    #    解耦的是前者（substrate 链上的解析），单趟化带不走后者。
    assert counter.substrate_load_count == BASELINE_SUBSTRATE_LOADS, (
        f"substrate 链解析 {counter.substrate_load_count} ≠ 基线 "
        f"{BASELINE_SUBSTRATE_LOADS}；调用点分布：{dict(counter.load_sites.most_common())}"
    )
    assert counter.substrate_load_count == 2 * counter.trip_count, (
        f"substrate 链解析 {counter.substrate_load_count} ≠ 趟数×2"
        f"（{2 * counter.trip_count}）—— 「每趟两个 data_only 视图」这条构成变了，"
        "基线拆解需重新实证"
    )
    assert counter.in_memory_load_count == BASELINE_IN_MEMORY_LOADS, (
        f"BytesIO 上的固定解析 {counter.in_memory_load_count} ≠ 基线 "
        f"{BASELINE_IN_MEMORY_LOADS}（转置 4 + 指纹 1）；"
        f"调用点分布：{dict(counter.load_sites.most_common())}"
    )


def test_default_path_is_single_pass_and_decoupled_from_binding_count(
    world: D4World, caplog: pytest.LogCaptureFixture
) -> None:
    """**P1 / 需求 1.1**：默认路径一趟写完，substrate 解析与 binding 数**解耦**（`≤ 2`）。

    四条一起断言，少一条就能被绕过：

    * 趟数 1 **且**这一趟走的是单趟入口 —— 只断趟数 1 的话，「契约被改成只剩 1 个 binding」
      也会让它绿；
    * substrate 解析 `≤ 2` **且**远小于 binding 数 —— 这是需求 1.1 的正文；
    * BytesIO 上那 5 次固定开销**不变** —— 提速不得来自「顺手少算了整簿指纹/转置 sheet」；
    * 日志里有「单趟物化命中」、**没有**「回落逐趟链式」—— 判据与可观测面同源。
    """
    counter = MaterializeCallCounter()
    with caplog.at_level("INFO", logger="app.services.workpaper_sync.adapters.excel"):
        with counter.installed():
            staged = world.materialize("default-path.xlsx")

    logs = [
        record.getMessage()
        for record in caplog.records
        if "[single_pass]" in record.getMessage()
    ]
    declines = [message for message in logs if "回落逐趟链式" in message]
    assert staged.is_file() and staged.read_bytes()[:2] == b"PK", "产物不是 xlsx"

    assert counter.trip_count == 1 and counter.single_pass_trip_count == 1, (
        f"默认路径趟数 {counter.trip_count}（其中单趟 {counter.single_pass_trip_count}）"
        f" —— 期望恰 1 趟且走单趟入口。趟次：{counter.trips}；日志：{logs}"
    )
    assert counter.substrate_load_count <= 2, (
        f"substrate 解析 {counter.substrate_load_count} > 2（需求 1.1 的上界）；"
        f"调用点分布：{dict(counter.load_sites.most_common())}；日志：{logs}"
    )
    assert counter.substrate_load_count == SINGLE_PASS_SUBSTRATE_LOADS, (
        f"substrate 解析 {counter.substrate_load_count} ≠ 实测 "
        f"{SINGLE_PASS_SUBSTRATE_LOADS}（data_only 两视图各一次，39 binding 共享）"
    )
    # 「解耦」的直接判据：耦合形态是「每 binding 两个视图」= `2 × binding 数`。实测必须
    # 远小于它。写成与 `world.binding_count` 比而不是与写死的 78 比，是为了让「契约加了
    # 受管表」这种正当变化不会把本条判成红 —— 解耦是结构性质，不是某个具体数字。
    coupled = 2 * world.binding_count
    assert counter.substrate_load_count < coupled, (
        f"substrate 解析 {counter.substrate_load_count} 未与 binding 数解耦："
        f"耦合形态（每 binding 两视图）会是 {coupled} 次"
    )
    assert counter.in_memory_load_count == BASELINE_IN_MEMORY_LOADS, (
        f"BytesIO 上的固定解析 {counter.in_memory_load_count} ≠ {BASELINE_IN_MEMORY_LOADS}"
        "（转置 4 + 指纹 1）—— 单趟化不该改变这一项；变了说明少算了东西"
    )
    assert counter.load_count == SINGLE_PASS_LOADS, (
        f"load_workbook 合计 {counter.load_count} ≠ 实测 {SINGLE_PASS_LOADS}；"
        f"调用点分布：{dict(counter.load_sites.most_common())}"
    )
    assert counter.save_count == BASELINE_SAVES, (
        f"Workbook.save {counter.save_count} ≠ {BASELINE_SAVES}（转置 sheet 的固定开销，"
        f"与 binding 数无关）；调用点分布：{dict(counter.save_sites.most_common())}"
    )
    assert declines == [], f"默认路径回落了：{declines}"
    assert any("单趟物化命中" in message for message in logs), (
        f"没看到单趟命中日志 ⇒ 可观测面与判据脱钩。日志：{logs}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# decline 判据：「同坐标 **且** payload 冲突」（design 附录 A.6 第 1~2 条）
# ═══════════════════════════════════════════════════════════════════════════


def _step(table_key: str, *writes: CellWrite, part: str = "xl/worksheets/sheet1.xml") -> Any:
    """一个只填冲突判据**真会读**的三项的计划步骤。

    `_cross_binding_payload_conflicts` 只读 `plan.sheet_part` / `plan.writes` /
    `binding.table_key`；其余两项（`substrate_view` / `runtime_binding`）在真实路径上来自
    整本 zip 的解析，与本判据无关。`CellWrite` / `MaterializePlan` / `ExcelIdentityBinding`
    都用**生产类型**构造 —— 自己造一个「像写入的东西」就测不到真实 payload 面了。
    """
    return MaterializePlanStep(
        binding=ExcelIdentityBinding(
            table_key=table_key, table_name=f"GT_{table_key.upper()}", uuid_column="A"
        ),
        plan=MaterializePlan(
            sheet_part=part,
            sheet_name="Sheet1",
            writes=tuple(writes),
            preserved_formulas={},
            dynamic_column_columns={},
        ),
        strategy=None,
        substrate_view=None,
        runtime_binding={},
    )


def _num(coord: str, value: Any, *, field_key: str = "t/total") -> CellWrite:
    return CellWrite(
        coord=coord,
        kind=CellWriteKind.number_literal,
        value=value,
        stable_field_key=field_key,
        mode=FieldMode.auto_source,
    )


class TestDeclineCriterion:
    """判据必须双向可反证：良性重叠放行、真冲突拦住。

    **Validates: Requirements 1.1**
    """

    def test_identical_payload_at_same_coord_is_not_a_conflict(self) -> None:
        """D4 的形态：同格、同字段、同值 ⇒ 恒等覆盖 ⇒ 放行。

        这正是旧判据（坐标相交即 decline）误杀的那一类。
        """
        conflicts = _cross_binding_payload_conflicts(
            [
                _step("customer_current_rows", _num("C38", 0)),
                _step("customer_prior_rows", _num("C38", 0)),
            ]
        )
        assert conflicts == (), f"良性重叠被误判成冲突：{conflicts}"

    def test_row_key_alone_never_makes_a_conflict(self) -> None:
        """`row_key` 不进判据面：它不落盘字节，两方不同也仍是恒等覆盖。"""
        left = _num("C38", 0)
        conflicts = _cross_binding_payload_conflicts(
            [
                _step("a", left),
                _step("b", dataclasses.replace(left, row_key="row-uuid-2")),
            ]
        )
        assert conflicts == (), f"row_key 不同被误判成冲突：{conflicts}"

    @pytest.mark.parametrize(
        "other,expected_field",
        [
            (_num("C38", 1), "value"),
            (_num("C38", 0, field_key="t/other"), "stable_field_key"),
            (
                CellWrite(
                    coord="C38",
                    kind=CellWriteKind.inline_text,
                    value=0,
                    stable_field_key="t/total",
                    mode=FieldMode.auto_source,
                ),
                "kind",
            ),
            (
                CellWrite(
                    coord="C38",
                    kind=CellWriteKind.number_literal,
                    value=0,
                    stable_field_key="t/total",
                    mode=FieldMode.editable,
                ),
                "mode",
            ),
            (
                CellWrite(
                    coord="C38",
                    kind=CellWriteKind.number_literal,
                    value=0,
                    stable_field_key="t/total",
                    mode=FieldMode.auto_source,
                    formula_text="=SUM(C1:C37)",
                ),
                "formula_text",
            ),
        ],
        ids=["value", "stable_field_key", "kind", "mode", "formula_text"],
    )
    def test_each_payload_field_alone_triggers_decline(
        self, other: CellWrite, expected_field: str
    ) -> None:
        """判据面的**每一项**都单独可反证：只改它一个就必须 decline，且原因指名它。

        逐项参数化而不是只测一个字段：漏掉任一项 ⇒ 那一项的差异会被静默合并。
        """
        conflicts = _cross_binding_payload_conflicts(
            [_step("a", _num("C38", 0)), _step("b", other)]
        )
        assert len(conflicts) == 1, f"期望恰 1 处冲突，实得：{conflicts}"
        assert "!C38" in conflicts[0] and expected_field in conflicts[0], (
            f"原因没指名差异字段 {expected_field}：{conflicts[0]}"
        )

    def test_number_zero_and_float_zero_are_not_the_same_write(self) -> None:
        """`0` 与 `0.0` 在 `==` 下相等、落盘字节不同 ⇒ 必须算冲突。

        判据用 `repr` 就是为了这个；改成 `==` 比这条立刻红。
        """
        conflicts = _cross_binding_payload_conflicts(
            [_step("a", _num("C38", 0)), _step("b", _num("C38", 0.0))]
        )
        assert len(conflicts) == 1 and "value" in conflicts[0], conflicts

    def test_same_binding_writing_one_coord_twice_is_its_own_business(self) -> None:
        """同一个 binding 在同格写两次值不同 ⇒ 不是跨 binding 冲突。

        链式路径里那也只是它自己覆盖自己（last-writer-wins），单趟同此 ⇒ 不该 decline。
        """
        conflicts = _cross_binding_payload_conflicts(
            [_step("a", _num("C38", 0), _num("C38", 7))]
        )
        assert conflicts == (), f"binding 内部覆盖被误判成跨 binding 冲突：{conflicts}"

    def test_same_coord_on_different_sheet_parts_is_not_a_collision(self) -> None:
        """坐标相同但不在同一个 sheet part ⇒ 根本不是同一格。"""
        conflicts = _cross_binding_payload_conflicts(
            [
                _step("a", _num("C38", 0), part="xl/worksheets/sheet1.xml"),
                _step("b", _num("C38", 1), part="xl/worksheets/sheet2.xml"),
            ]
        )
        assert conflicts == (), conflicts


class TestDeclineReasonIsDeterministicAndComplete:
    """旧实现按 `set(plan.coords)` 抽样报一格 ⇒ 列号随进程 hash 种子变、其余碰撞看不见。

    真库要统计回落比例与回落**原因**（需求 3.3），原因就必须确定、完整。

    **Validates: Requirements 1.1, 3.3**
    """

    @staticmethod
    def _three_conflicts() -> list[Any]:
        return [
            _step("a", _num("E38", 0), _num("C38", 0), _num("C24", 0)),
            _step("b", _num("E38", 1), _num("C38", 2), _num("C24", 3)),
        ]

    def test_every_conflicting_cell_is_reported(self) -> None:
        """三格冲突就报三格 —— 不是「抛第一处就走」。"""
        conflicts = _cross_binding_payload_conflicts(self._three_conflicts())
        assert len(conflicts) == 3, f"报少了：{conflicts}"
        for coord in ("C24", "C38", "E38"):
            assert any(f"!{coord}" in item for item in conflicts), (
                f"{coord} 没进原因清单：{conflicts}"
            )

    def test_reported_order_is_row_then_column(self) -> None:
        """排序键是「先行后列」，与 `analyze_d4_binding_dependencies.py` 的 D1 报告同口径。"""
        conflicts = _cross_binding_payload_conflicts(self._three_conflicts())
        coords = [item.split("!", 1)[1].split(" ", 1)[0] for item in conflicts]
        assert coords == ["C24", "C38", "E38"], coords
        assert coords == sorted(coords, key=coord_sort_key), coords

    def test_output_is_independent_of_input_order(self) -> None:
        """打乱 step 顺序与 plan 内写入顺序 ⇒ 原因清单**逐字相同**。

        这条直接钉「不依赖 `set`/`dict` 的偶然序」：换成遍历 `set(plan.coords)` 时，同一批
        碰撞在不同顺序下报出来的第一格就不同 ⇒ 红。
        """
        forward = _cross_binding_payload_conflicts(self._three_conflicts())
        shuffled = _cross_binding_payload_conflicts(
            [
                _step("b", _num("C24", 3), _num("E38", 1), _num("C38", 2)),
                _step("a", _num("C38", 0), _num("C24", 0), _num("E38", 0)),
            ]
        )
        assert forward == shuffled, f"顺序影响了输出：\n{forward}\n{shuffled}"

    def test_reason_carries_the_complete_set_into_the_exception(self) -> None:
        """`SinglePassDeclined.reason` 必须带完整集合 —— 日志里看不见的碰撞等于没统计。

        断言的是**生产**那一份格式化（`_payload_conflict_decline_reason`），不是测试里抄的
        副本：抄一份的话「原因里漏了一格」两边会一起错。
        """
        conflicts = _cross_binding_payload_conflicts(self._three_conflicts())
        reason = _payload_conflict_decline_reason(conflicts)
        for coord in ("C24", "C38", "E38"):
            assert coord in reason, reason
        assert "3 格" in reason, reason


# ═══════════════════════════════════════════════════════════════════════════
# 属性：报出来的冲突格集合 **恰好** 等于「跨 binding payload 不同」的那些格
# ═══════════════════════════════════════════════════════════════════════════

#: 写入值域刻意含 `0` / `0.0` / `Decimal('0')`：它们 `==` 相等而落盘字节不同，是判据最容易
#: 被写松的地方。字符串域含空串（identity 写入的 `stable_field_key` 形态）。
_VALUES = st.sampled_from([0, 1, 0.0, 1.0, True, False, "", "x", None])
_COORDS = st.sampled_from(["C24", "E24", "C38", "E38", "A1", "AA100"])


@st.composite
def _two_binding_writes(draw: Any) -> tuple[list[CellWrite], list[CellWrite]]:
    """两个 binding 各自的写入清单（坐标可重叠，payload 随机）。

    生成器刻意**约束**在小坐标域上：坐标域太大就几乎不会重叠，属性会退化成「空集恒等于
    空集」这种恒真命题。
    """
    def _writes() -> list[CellWrite]:
        return draw(
            st.lists(
                st.builds(
                    _num,
                    coord=_COORDS,
                    value=_VALUES,
                    field_key=st.sampled_from(["t/total", "t/other"]),
                ),
                min_size=1,
                max_size=5,
            )
        )

    return _writes(), _writes()


@settings(max_examples=5, deadline=None)
@given(pair=_two_binding_writes())
def test_conflict_set_is_exactly_the_cells_whose_payloads_differ(
    pair: tuple[list[CellWrite], list[CellWrite]]
) -> None:
    """**Validates: Requirements 1.1**

    判据不是「有碰撞就报」也不是「有碰撞就放」：报出来的格集合必须**恰好**是
    「两个 binding 都写、且各自最后一次写的 payload 不同」的那些格。

    期望值由测试**独立**算（按 last-writer-wins 取每个 binding 在该坐标的最后一次写入，
    再逐 payload 面比对），不复用生产的索引构造 —— 复用就变成「自己和自己比」。
    """
    left, right = pair
    steps = [_step("a", *left), _step("b", *right)]

    def _effective(writes: list[CellWrite]) -> dict[str, tuple[Any, ...]]:
        last: dict[str, CellWrite] = {}
        for write in writes:
            last[write.coord] = write
        return {
            coord: (
                write.kind.value,
                repr(write.value),
                write.stable_field_key,
                "" if write.mode is None else str(write.mode),
                write.formula_text,
            )
            for coord, write in last.items()
        }

    left_payloads, right_payloads = _effective(left), _effective(right)
    expected = {
        coord
        for coord in left_payloads.keys() & right_payloads.keys()
        if left_payloads[coord] != right_payloads[coord]
    }

    reported = {
        item.split("!", 1)[1].split(" ", 1)[0]
        for item in _cross_binding_payload_conflicts(steps)
    }
    assert reported == expected, (
        f"报出来的冲突格 {sorted(reported)} ≠ 应报的 {sorted(expected)}；"
        f"左 {left_payloads}；右 {right_payloads}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 真库前提：D4 的跨 binding 重叠恰为那 4 格、且 payload 全同（design 附录 A.3 / A.6）
# ═══════════════════════════════════════════════════════════════════════════


def test_d4_cross_binding_collisions_are_exactly_the_four_benign_cells(
    d4_steps: list[MaterializePlanStep],
) -> None:
    """单趟对 D4 生效的**前提**，钉在真契约真计划上而不是注释里。

    **Validates: Requirements 1.1**

    契约层若把静态表归属改了（例如让 `customer_totals` 只归一个 binding），这条会红 ——
    届时 D4 连碰撞都没有，判据要相应更新（design 附录 A.6 的配套判据建议）。
    """
    # part → coord → 写它的 table_key 集合。测试自己从计划里数，不问生产要结论。
    writers: dict[str, set[str]] = {}
    for step in d4_steps:
        part = str(step.plan.sheet_part)
        for write in step.plan.writes:
            writers.setdefault(f"{part}!{write.coord}", set()).add(
                str(step.binding.table_key)
            )

    collisions = sorted(cell for cell, keys in writers.items() if len(keys) > 1)
    assert collisions == sorted(D4_BENIGN_COLLISIONS), (
        f"D4 的跨 binding 碰撞集合变了：实测 {collisions}，"
        f"附录 A.3 实证 {sorted(D4_BENIGN_COLLISIONS)}"
    )
    for cell in collisions:
        assert sorted(writers[cell]) == sorted(D4_COLLIDING_BINDINGS), (
            f"{cell} 的碰撞方变了：{sorted(writers[cell])}"
        )


def test_d4_benign_collisions_produce_zero_payload_conflicts(
    d4_steps: list[MaterializePlanStep],
) -> None:
    """这 4 格两方 payload 逐字段相同 ⇒ 判据报零冲突 ⇒ D4 才走得上单趟。

    **Validates: Requirements 1.1**

    与上一条分开写：上一条说「碰撞在哪」，这一条说「碰撞是良性的」。合并成一条的话，
    「碰撞消失了」与「碰撞变良性了」在失败信息里分不开。
    """
    conflicts = _cross_binding_payload_conflicts(d4_steps)
    assert conflicts == (), (
        "D4 出现了 payload 冲突 ⇒ 单趟会 decline、需求 1.5 的 ≤10s 对 D4 不可达。"
        f"冲突：{_payload_conflict_decline_reason(conflicts)}"
    )


def test_payload_conflict_really_falls_back_to_the_chained_path(
    world: D4World,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """把 D4 的一格良性重叠**变成**真冲突 ⇒ 整趟回落逐趟链式。

    **Validates: Requirements 1.1**

    这条测的是 decline 分支在**端到端**上真的通：单元判据只证明「判据函数会报冲突」，不证明
    「adapter 会因此回落」。它同时是「链式路径不是死代码」的直接证据 —— 任务 3 的任务文本
    禁止把旧实现留成**不可达分支**，而这里实测它可达：真库上任一 entry 一旦出现插行或同格
    payload 冲突就走它。

    注入方式：拦 `_plan_materialize_step`（生产内核），只把 `customer_prior_rows` 在 `C24`
    的写入值改掉 —— 于是它与 `customer_current_rows` 在同一格上写不同值。不改判据、不改
    adapter，只改输入。
    """
    from decimal import Decimal

    from app.services.workpaper_sync import excel_materialize as EM

    original = EM._plan_materialize_step
    victim, coord = D4_COLLIDING_BINDINGS[1], "C24"

    def poisoned(**kwargs: Any) -> Any:
        step = original(**kwargs)
        if str(step.binding.table_key) != victim:
            return step
        writes = tuple(
            dataclasses.replace(write, value=Decimal("111111"))
            if write.coord == coord
            else write
            for write in step.plan.writes
        )
        assert writes != step.plan.writes, (
            f"{victim} 没有在 {coord} 写入 ⇒ 注入失效，本判据会变成空转"
        )
        return dataclasses.replace(
            step, plan=dataclasses.replace(step.plan, writes=writes)
        )

    monkeypatch.setattr(EM, "_plan_materialize_step", poisoned)

    counter = MaterializeCallCounter()
    with caplog.at_level("INFO", logger="app.services.workpaper_sync.adapters.excel"):
        with counter.installed():
            world.materialize("payload-conflict.xlsx")

    logs = [
        record.getMessage()
        for record in caplog.records
        if "[single_pass]" in record.getMessage()
    ]
    declines = [message for message in logs if "回落逐趟链式" in message]
    assert len(declines) == 1, f"期望恰一条回落日志，实得：{logs}"
    assert coord in declines[0] and "value" in declines[0], (
        f"回落原因没指名冲突格与差异字段：{declines[0]}"
    )
    assert counter.single_pass_trip_count == 0, (
        f"decline 了却记了单趟趟次：{counter.single_pass_trips}"
    )
    assert counter.trip_count == BASELINE_BINDINGS, (
        f"回落后趟数 {counter.trip_count} ≠ {BASELINE_BINDINGS} ⇒ 回落路径没真正接上"
    )
