"""adopt 覆盖计划 —— **Property 9: 非法载荷一律 fail visible**。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.6）
Requirements 4.4 · design § Correctness Properties / § Testing Strategy §7.4

═══ 为什么是伴生文件（域内第四次同样处置）═══

Task 3.5 在 `test_aos_property_row_identity.py` 末尾留了 Property 9 的落点，并要求「追加前先数
行数」。实测：留位时那边 **538** 行 + 本文件的 property 段（§6~§9，交付时 **521** 行）= **1059**
⇒ 远越 `.py` 门禁 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit 与
CI 的 `file-size-guard` 同源）。门禁自己给的处置顺序是「优先拆分 / 抽伴生模块」⇒ 切成伴生文件，
被切的一侧留了指针注释。拆分后两边各自达标（判据 = `python backend/scripts/check/check_file_size.py
<两个文件>` exit=0；🔴 行数本身不写进 docstring —— 那是自指计数，每次编辑都会过期）。
🔴 本文件也已过半程，**下一条 property 不要再往这里加**。
（生产侧同样处置已有三次：`phase5_g9_store_facade.py` / `adopt_row_reader.py` /
`adopt_row_reader_r3.py`。）

🔴 **建造器不复制**：`_spec` / `_readers` / `ITEM` / `IDENTITY_KEYS` / `_IDENTITY_ALPHABET` 全部
从 `test_aos_property_row_identity` import。抄第二份 `_spec()` 就是第二真源 —— 两边的合成
`RowTableSheetSpec` 一旦漂了，两条 property 就在测不同的东西。import 用**顶层模块名**形态
（`backend/tests/workpaper_sync/` 无 `__init__.py` ⇒ pytest 以 `prepend` 模式把该目录塞进
`sys.path` 并按顶层名 import）—— 与域内既有做法一致（`test_g_single_region_p9_p12.py` /
`test_excel_row_insertion_openability.py` 等）。写成 `tests.workpaper_sync.…` 会得到**第二个**
模块实例，模块级累计器就会分家。

═══ Property 9 与 Task 3.4 的 `TestUnreadablePayloadFailsVisible` 不重复 ═══

* Task 3.4（例子级）：**4** 个写死的串（`{not json` / `{"a": 1}` / `42` / `[1]`）喂**一个**真
  item（`G9-detail-rows`）的一个 reader，证「这 4 个串会抛」；
* 本文件（属性级）：**4 类**形态各随机生成，跨**全部三个** `RowReader` 实现（12 格矩阵，见
  :meth:`TestProperty9JudgesCanBeFalse.test_matrix_covered_every_form_on_every_reader`），
  证「这一**类**载荷都会抛」。

🔴 **判据不落在异常类型上**：`adopt_row_reader` 模块 docstring 的「Requirement 4.4 分工裁定」
明写本层**原样穿透** provider / 引擎的原生异常（不包装、不新建异常类），而原生类型**异构** ——
引擎 `RowTableStorePayloadError(Exception)`、多数 provider `StorePayloadError(SyncDomainError)`、
`phase5_d4_customer_structure` 的是 `StorePayloadError(ValueError)` ⇒ 按类型分流必漂（裁定原话）。
故本文件的判据是三条**可观测契约**：①抛（不是返回空）②消息带 item_id ③不当零行处理。

═══ 判据落在**三层**，不是一层 ═══

| 层 | 被测函数 | 归属任务 |
| --- | --- | --- |
| reader | `RowReader.iter_rows`（三个实现） | Task 3.4 / 3.7 |
| 删除侧剪枝 | `adopt_overwrite_plan.prune_undeclared_rows` | Task 4.1 |
| 计划聚合 | `adopt_overwrite_compute.compute_overwrite_plan` | Task 4.2（与本任务并发交付） |

🔴 三层**必须都测**：实测三者对「reader 语义被弱化」的兜底强度**各不相同**（见
:meth:`TestProperty9JudgesCanBeFalse.test_m1_silently_empty_reader_is_caught` 的逐层登记）
⇒ 只测 reader 层会漏掉「计划层把 store 既有行整批报成 rows_added」这一最有破坏性的形态。

🔴 **`OverwritePlanShapeError` 不该出现在本 property 的期望里**：它的 docstring 明写是**编程
错误**（500 + 堆栈，不映射状态码），而「store 里存着一份非法 JSON」是**数据**问题，
Requirement 4.4 要的是 422（Task 6.2 的 `AdoptStorePayloadUnreadableError`）。

═══ 现读实证：引擎 `iter_store_rows` 的**五件**校验 ═══

`phase5_row_table_sheet.iter_store_rows` + `store_row_identity`（本轮现读逐条确认）：

1. 非法 JSON ⇒ `RowTableStorePayloadError("… 的 remark 不是合法 JSON: …")`
2. 非数组 ⇒ `"… 的载荷必须是行对象数组，实得 {type}"`（文案自带「不得静默当成零行」）
3. 元素非对象 ⇒ `"… 第 {ordinal} 项不是对象，实得 {type}"`
4. 缺稳定行身份 ⇒ `"… 第 {ordinal} 行缺少稳定行身份 {key!r}"`（明写「不得退回数组下标作身份」）
5. 重复行身份 ⇒ `"… 出现重复行身份 {identity!r}"`

本 property 覆盖 **1/2/3**（即 Property 9 原文点名的四种形态：非法 JSON、JSON 对象、JSON 标量、
含非对象元素的数组 —— 后三种都落在 2/3 两条分支上）。第 4 条由 Task 3.4 的
`test_row_without_any_identity_key_raises` 与 Property 10 的诱饵行守着，第 5 条属幽灵行门域。
五条的错误消息**全部**以 `spec.store_item_id` 起头 ⇒ 判据 ② 有真实依托，不是空断言。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Iterator, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import prune_undeclared_rows
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    iter_store_rows as engine_iter_store_rows,
)

# 🔴 复用 Property 10 文件的建造器（见模块 docstring：禁抄第二份）。
from test_aos_property_row_identity import (  # noqa: E402
    IDENTITY_KEYS,
    ITEM,
    _IDENTITY_ALPHABET,
    _readers,
    _spec,
)

# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 9（Task 3.6）—— 不可解析载荷的生成器
# ═══════════════════════════════════════════════════════════════════════════

#: Property 9 原文点名的**四种**形态。🔴 用 `parametrize` 穷举而不是 `st.sampled_from`：
#: `max_examples=5`（§7.4 PBT 配置，用户明确要求禁默认 100）下抽样覆盖不到 4 类，而四类走的是
#: 引擎里**四条不同**的抛出分支（现读 `phase5_row_table_sheet.iter_store_rows` 逐条确认：
#: ①`json.loads` 的 `ValueError` ②`not isinstance(rows, list)` ③元素 `not isinstance(_, Mapping)`
#: ④`store_row_identity` 缺身份 ⑤重复身份 —— 本 property 覆盖 ①②③，④由 Task 3.4 的
#: `test_row_without_any_identity_key_raises` 与本文件 Property 10 的诱饵行守着，⑤属幽灵行门域）。
_UNREADABLE_FORMS: tuple[str, ...] = (
    "invalid_json",
    "json_object",
    "json_scalar",
    "non_object_element",
)

#: 非对象元素池。🔴 刻意含 `None` 与 `[]`：`isinstance(None, Mapping)` 与 `isinstance([], Mapping)`
#: 都为 False，而「元素是 null」在真库里就是 OO 回写丢值的常见形态。
_BAD_ELEMENTS: tuple[Any, ...] = (1, 1.5, True, None, "str-not-a-row", [1], [])

#: JSON **标量**池（不含 `None`）。🔴 `None` 被刻意排除：`_as_row_list(None)` 明写「`None` =
#: 无载荷，无从谈删除」⇒ 原生 `None` 在计划层是**早退**而不是 fail visible。这条边界由
#: `test_documented_boundaries_of_the_landed_plan_surface` 显式登记，不混进 property 的分母。
_SCALARS: tuple[Any, ...] = (0, 42, -7, 3.5, True, False, "纯文本固定项")

#: 本次运行实际跑过的 `(形态, reader 实现)` 格子 —— 12 格覆盖矩阵的累计器。
_P9_MATRIX: set[tuple[str, str]] = set()


def _force_invalid_json(seed: str) -> str:
    """把任意字符串**确定性地**弄成非法 JSON。

    🔴 不用 `hypothesis.assume` 过滤：`max_examples=5` 下拒绝式过滤很可能把一整个 example
    预算耗在重试上（甚至 `Unsatisfiable`）。改为「先验后补」——`json.loads` 能过就追加一个
    未闭合的 `{`（任何合法 JSON 文档后面跟 `{` 都会得 `Extra data`）⇒ 恒非法且无重试。
    """
    for candidate in (seed, seed + "{"):
        try:
            json.loads(candidate)
        except ValueError:
            return candidate
    raise AssertionError(  # pragma: no cover —— 追加未闭合括号后仍合法即 json 语义变了
        f"无法把 {seed!r} 造成非法 JSON ⇒ 生成器失效，Property 9 的第一类形态会变成空分母"
    )


def _legal_row(identity_key: str, identity: str) -> dict[str, Any]:
    """一行**合法**行对象（只带身份键，不带诱饵 —— 诱饵是 Property 10 的事）。"""
    return {identity_key: identity}


def _unreadable_payload(
    form: str,
    *,
    identity_key: str,
    noise: str,
    as_json_text: bool,
    lead_rows: int,
    bad_pick: int,
) -> tuple[Any, int]:
    """按形态造一份不可解析载荷。返回 `(载荷, 首个坏元素下标)`。

    `首个坏元素下标` 是「抛之前最多允许 yield 几行」的上界：前三类形态整份载荷就废了 ⇒ 上界 0；
    第四类的坏元素前面可以有合法行（实测 `[{合法}, 1]` 上 `EngineRowReader` 会先 yield 1 行再抛，
    而 `ReconcilingRowReader` 因为先 `list(primary)` 所以 yield 0 行）⇒ 上界 = 坏元素下标。
    🔴 这个上界正是「不得凭空造行」那条断言的判据，写死成 0 会把合法前缀误判成违例。
    """
    if form == "invalid_json":
        return _force_invalid_json(noise), 0
    if form == "json_object":
        obj = {"a": 1, "rows": [], "噪声": noise}
        return (json.dumps(obj, ensure_ascii=False) if as_json_text else obj), 0
    if form == "json_scalar":
        scalar = _SCALARS[bad_pick % len(_SCALARS)]
        # 🔴 原生 `str` 标量不能直接当载荷：引擎会把 str 当 JSON 文本，于是 `"纯文本固定项"`
        #    走的是**第一类**（非法 JSON）分支而不是第三类 ⇒ 形态会串味。故 str 一律先 dumps。
        if as_json_text or isinstance(scalar, str):
            return json.dumps(scalar, ensure_ascii=False), 0
        return scalar, 0
    if form == "non_object_element":
        rows: list[Any] = [
            _legal_row(identity_key, f"lead-{i}") for i in range(lead_rows)
        ]
        rows.append(_BAD_ELEMENTS[bad_pick % len(_BAD_ELEMENTS)])
        return (json.dumps(rows, ensure_ascii=False) if as_json_text else rows), lead_rows
    raise AssertionError(f"未登记的形态 {form!r} —— 形态域与 _UNREADABLE_FORMS 漂了")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 9 的三条可观测判据（抽成函数，好让 §9 的变异反证喂替身）
# ═══════════════════════════════════════════════════════════════════════════


def _assert_reader_fails_visible(
    reader: Any, payload: Any, *, label: str, first_bad_index: int
) -> BaseException:
    """判据 ①②③ 落在 reader 上。返回真被抛出的异常（供调用方再断言）。

    🔴 **「抛了」与「不当零行」分开断言**：三个 reader 实现全是生成器函数（现算实证：取
    `reader.iter_rows(payload)` 本身**不**抛，异常发生在第一次迭代）⇒ 一个「静默返回空迭代器」
    的实现在 `iter_rows(...)` 这一步与正确实现**长得一模一样**。故判据必须是
    「`list(...)` 必抛」而不是「`list(...) == []`」—— 后者对静默当零行的实现恒真。
    """
    iterator = reader.iter_rows(payload)  # 生成器：这一步不该抛，抛也不算错（更早失败）
    produced: list[Any] = []
    try:
        for item in iterator:
            produced.append(item)
    except Exception as exc:  # noqa: BLE001 —— 本函数就是在观测「抛的是什么」
        # ② 消息必带 item_id（Requirement 4.4 逐字：「并给出该 item 的 item_id」）
        assert ITEM in str(exc), (
            f"{label}：抛了 {type(exc).__name__} 但消息里没有 item_id {ITEM!r} —— "
            f"实得 {str(exc)[:160]!r}。下游（Task 6.2）要靠它定位是哪个 item 的载荷坏了"
        )
        # ③ 抛之前不得凭空造行、不得越过坏元素
        assert len(produced) <= first_bad_index, (
            f"{label}：抛之前 yield 了 {len(produced)} 行，超过首个坏元素下标 "
            f"{first_bad_index} —— 坏元素之后的行不该被读出来"
        )
        assert all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], Mapping)
            for item in produced
        ), f"{label}：抛之前 yield 出的项不是 (identity, Mapping) 二元组，实得 {produced!r}"
        return exc
    # ① 没抛 ⇒ 判据为 False。`AssertionError` 是故意的：§9 的变异反证靠它把替身钉死。
    raise AssertionError(
        f"{label}：对不可解析载荷 {payload!r} **没有抛**，返回了 {len(produced)} 行 —— "
        "「当成零行处理」正是 Requirement 4.4 点名禁止的那件事"
    )


def _assert_plan_fails_visible(reader: Any, payload: Any, *, label: str) -> BaseException:
    """判据落在**删除侧剪枝** `prune_undeclared_rows`（Task 4.1）上。

    Property 9 原文说的是「计划计算应抛出」，而计划侧现有**两个**已落地纯函数 ⇒ 两个都要过：
    本函数管 Task 4.1，:func:`_assert_compute_plan_fails_visible` 管 Task 4.2 的
    `compute_overwrite_plan`。两者的兜底强度**不同**（现算实证，见
    :meth:`TestProperty9JudgesCanBeFalse.test_m1_silently_empty_reader_is_caught`）
    ⇒ 只测一个会漏掉另一个的缺口。

    🔴 「当成零行处理」在计划层的**具体形态**是返回 `(payload, ())`（零删除、载荷原样）——
    它与「作用域外不碰一个字节」（Requirement 1.2 的正确行为）在返回值上**完全同形** ⇒
    只看返回值区分不出来，必须靠「这份载荷在作用域**内**」这个前提 + 「必抛」这条断言。
    故本判据固定把本 spec 的 table 声明进 `row_keys`。
    """
    table_key = _spec(identity_key=IDENTITY_KEYS[0]).table_key
    try:
        result = prune_undeclared_rows(
            payload, row_keys={table_key: ("declared-r1",)}, reader=reader
        )
    except Exception as exc:  # noqa: BLE001
        assert ITEM in str(exc), (
            f"{label}：prune 抛了 {type(exc).__name__} 但消息里没有 item_id {ITEM!r} —— "
            f"实得 {str(exc)[:160]!r}"
        )
        return exc
    raise AssertionError(
        f"{label}：prune_undeclared_rows 对不可解析载荷 {payload!r} 返回了 {result!r} 而**没有抛** "
        "—— 计划计算把该 item 当成了零行（Requirement 4.4 禁止）"
    )


#: 计划计算的 substrate 侧声明身份（两个计划层判据共用，值本身无意义）。
_DECLARED_IDENTITY = "declared-r1"


def _projection_declaring_table(table_key: str) -> Any:
    """最小 projection 替身：`compute_overwrite_plan` 只读它的 `row_keys`（现读确认）。"""
    return SimpleNamespace(row_keys={table_key: (_DECLARED_IDENTITY,)})


def _assert_compute_plan_fails_visible(
    reader: Any, payload: Any, *, label: str
) -> BaseException:
    """判据落在 `compute_overwrite_plan` 上 —— 它才是 Property 9 原文说的「计划计算」本体。

    🔴 **Task 4.2 与本任务并发交付**：写判据时它刚落地（`adopt_overwrite_compute.py`）⇒
    先现算实测 3 reader × 4 形态 **12 格全部**抛 `RowTableStorePayloadError` 且文案带 item_id，
    确认后才接进来，不是照签名推断。

    🔴 「当成零行」在这一层的危害最直观：喂 M1 替身（吞异常返回空）时 compute **不抛**，并且把
    substrate 侧声明的身份**全报成 `rows_added`**（实测 `added=['declared-r1']`）—— 即「store
    里明明有行，计划却说要全量新增」。删除侧是本 spec 唯一破坏性的一侧，这种错会直接落到库上。
    """
    table_key = _spec(identity_key=IDENTITY_KEYS[0]).table_key
    try:
        plan = compute_overwrite_plan(
            substrate_projection=_projection_declaring_table(table_key),
            store_payloads={ITEM: payload},
            row_readers={ITEM: reader},
        )
    except Exception as exc:  # noqa: BLE001
        assert ITEM in str(exc), (
            f"{label}：compute_overwrite_plan 抛了 {type(exc).__name__} 但消息里没有 item_id "
            f"{ITEM!r} —— 实得 {str(exc)[:160]!r}"
        )
        return exc
    added = sorted({i for delta in plan.deltas for i in delta.rows_added})
    raise AssertionError(
        f"{label}：compute_overwrite_plan 对不可解析载荷 {payload!r} 返回了计划"
        f"（deltas={len(plan.deltas)} · rows_added={added}）而**没有抛** —— 计划计算把该 item"
        " 当成了零行，store 侧既有行会被整批报成 rows_added（Requirement 4.4 禁止）"
    )


def _assert_legal_payload_enumerates(
    reader: Any, payload: Any, *, label: str, expected: list[str]
) -> None:
    """**合法对照组** —— 没有它，「一律抛」对「把所有输入都抛掉」的实现恒真（判据无区分力）。"""
    try:
        got = list(reader.iter_rows(payload))
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"{label}：把**合法**载荷 {payload!r} 也拒了（{type(exc).__name__}: "
            f"{str(exc)[:160]}）—— 那么「非法载荷一律抛」就是恒真判据，Property 9 失去区分力"
        ) from exc
    assert [identity for identity, _row in got] == expected, (
        f"{label}：合法载荷枚举出的身份 {[i for i, _ in got]} != 期望 {expected}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 9（Task 3.6）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9UnreadablePayloadFailsVisible:
    """Property 9：四类不可解析载荷 × 三个 `RowReader` 实现，一律 fail visible。"""

    @pytest.mark.parametrize("form", _UNREADABLE_FORMS)
    @settings(max_examples=5, deadline=None)
    @given(
        noise=st.text(alphabet=_IDENTITY_ALPHABET + '{}[]":,', min_size=0, max_size=12),
        as_json_text=st.booleans(),
        lead_rows=st.integers(min_value=0, max_value=3),
        bad_pick=st.integers(min_value=0, max_value=len(_BAD_ELEMENTS) * 3),
        key_pick=st.integers(min_value=0, max_value=len(IDENTITY_KEYS) * 3),
    )
    def test_property_9_unreadable_payload_always_fails_visible(
        self,
        form: str,
        noise: str,
        as_json_text: bool,
        lead_rows: int,
        bad_pick: int,
        key_pick: int,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 9: 非法载荷一律 fail visible

        **Validates: Requirements 4.4**

        随机维度：噪声文本（含 JSON 元字符，让「非法 JSON」不是同一个串）、载荷是 JSON 文本
        还是已解析对象（引擎两条入口分支都要走到）、坏元素前的合法行数、坏元素取值、身份键取值。
        形态维度**穷举**（4 类），reader 维度**穷举**（3 个实现）⇒ 12 格矩阵。
        """
        identity_key = IDENTITY_KEYS[key_pick % len(IDENTITY_KEYS)]
        payload, first_bad = _unreadable_payload(
            form,
            identity_key=identity_key,
            noise=noise,
            as_json_text=as_json_text,
            lead_rows=lead_rows,
            bad_pick=bad_pick,
        )
        spec = _spec(identity_key=identity_key)
        for label, reader in _readers(spec):
            _P9_MATRIX.add((form, label))
            where = f"{label} / 形态 {form} / 键名 {identity_key!r}"
            # ①②③ reader 层
            _assert_reader_fails_visible(
                reader, payload, label=where, first_bad_index=first_bad
            )
            # 计划计算层（Property 9 原文的「计划计算应抛出」）—— 两个已落地的计划面都要过
            _assert_plan_fails_visible(reader, payload, label=where)
            _assert_compute_plan_fails_visible(reader, payload, label=where)

    @pytest.mark.parametrize("form", _UNREADABLE_FORMS)
    @pytest.mark.parametrize("as_json_text", [True, False])
    def test_legal_control_group_is_not_rejected(self, form: str, as_json_text: bool) -> None:
        """🔴 合法对照组：同一批 reader 对**合法**载荷必须不抛且枚举出正确身份。

        与上一条**同参数化维度**（形态 × 文本/对象）跑一遍，为的是让「抛」这件事在同一坐标下
        有对照 —— 否则「非法必抛」对一个无条件抛错的实现也成立。
        """
        identity_key = IDENTITY_KEYS[_UNREADABLE_FORMS.index(form) % len(IDENTITY_KEYS)]
        spec = _spec(identity_key=identity_key)
        rows = [_legal_row(identity_key, f"legal-{i}") for i in range(3)]
        payload: Any = json.dumps(rows, ensure_ascii=False) if as_json_text else rows
        expected = [f"legal-{i}" for i in range(3)]
        for label, reader in _readers(spec):
            _assert_legal_payload_enumerates(
                reader, payload, label=f"{label} / {form}", expected=expected
            )
            # 计划侧同样必须**不**抛，且真的按声明剪枝（声明 legal-0 ⇒ 另两行被删）。
            table_key = spec.table_key
            kept, deleted = prune_undeclared_rows(
                payload, row_keys={table_key: ("legal-0",)}, reader=reader
            )
            assert [r[identity_key] for r in kept] == ["legal-0"], (label, kept)
            assert deleted == ("legal-1", "legal-2"), (label, deleted)
            # `compute_overwrite_plan` 同样不抛，且三清单是**真算出来的**（不是恒空）。
            plan = compute_overwrite_plan(
                substrate_projection=SimpleNamespace(row_keys={table_key: ("legal-0",)}),
                store_payloads={ITEM: payload},
                row_readers={ITEM: reader},
            )
            delta = plan.deltas[0]
            assert (
                sorted(delta.rows_updated) == ["legal-0"]
                and sorted(delta.rows_deleted) == ["legal-1", "legal-2"]
                and sorted(delta.rows_added) == []
            ), (label, delta)

    def test_documented_boundaries_of_the_landed_plan_surface(self) -> None:
        """🔴 两条**如实登记**的边界 —— 它们不是 Property 9 的违例，但必须被看见。

        1. **作用域外不读载荷**：`row_keys` 不含本 table 时 `prune_undeclared_rows` 在读载荷
           **之前**就早退（Requirement 1.2「一个字节都不碰」），故非法载荷在那条路上**不抛**。
           ⇒ Property 9 在计划层的判据必须先把 table 声明进 `row_keys`（`_assert_plan_fails_visible`
           已固定这么做）。🔴 这条不得「顺手修成也抛」：那会让未声明的表被读、被校验，
           Requirement 1.2 随即破。
        2. **原生 `None` 是「无载荷」不是「不可解析」**：`_as_row_list` 明写 `None` ⇒ 无从谈删除。
           reader 层仍会抛（引擎判 `not isinstance(None, list)`），计划层则早退 ⇒ 两层不同调。
           ⇒ 原生 `None` 被刻意排除在 `_SCALARS` 之外；Task 4.2 若要把「无载荷」也纳入
           fail-visible，须先在 spec 里裁决它与「该 item 本来就没行」如何区分。
        """
        spec = _spec(identity_key=IDENTITY_KEYS[0])
        _label, reader = _readers(spec)[0]
        # 边界 1：未声明本 table ⇒ 载荷原样返回（`is` 相等）、零删除、不抛
        kept, deleted = prune_undeclared_rows(
            "{not json", row_keys={"某个没被声明的表": ("r1",)}, reader=reader
        )
        assert kept == "{not json" and deleted == ()
        # 边界 2：原生 None —— reader 抛、计划层早退
        with pytest.raises(Exception) as excinfo:
            list(reader.iter_rows(None))
        assert ITEM in str(excinfo.value)
        assert prune_undeclared_rows(
            None, row_keys={spec.table_key: ("r1",)}, reader=reader
        ) == (None, ())
        # 变异对照：把 None 换成 JSON 文本 `"null"` ⇒ 计划层**会**抛（证明早退是 None 特有的）
        _assert_plan_fails_visible(reader, "null", label="JSON 文本 null")


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 9 的变异反证 —— 三条判据各必须能为 False
# ═══════════════════════════════════════════════════════════════════════════


class _SilentlyEmptyRowReader:
    """🔴 变异 M1：**静默当零行**（`try: … except: return`）—— Requirement 4.4 点名禁止的形态。

    这正是 `_FacadeRowReader.iter_rows` / `EngineRowReader.iter_rows` 的 docstring 明写「**不
    try/except**」所要防的实现。它对外长得与正确实现完全一样（同样是生成器、同样按声明取键），
    差别只在「坏载荷时返回空」⇒ 判据若写成 `list(...) == []` 就把它判绿。
    """

    def __init__(self, *, spec: RowTableSheetSpec) -> None:
        self.item_id = spec.store_item_id
        self._spec = spec
        self.section_field = spec.row_section_field
        self.declared_scopes = ((spec.table_key, spec.row_section_value or None),)

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        try:
            yield from engine_iter_store_rows(self._spec, payload)
        except Exception:  # noqa: BLE001 —— 就是那条被禁的吞异常
            return

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        return None


class _AnonymousRejectRowReader(_SilentlyEmptyRowReader):
    """🔴 变异 M2：**抛了但消息不带 item_id** —— 判据 ② 必须对它为 False。

    危害是具体的：Task 6.2 要把原生异常翻译成 `AdoptStorePayloadUnreadableError(item_id=…)`，
    而一次 adopt 覆盖多个 store item ⇒ 消息里没有 item_id 就无从告诉用户「哪份载荷坏了」，
    Requirement 4.4 的「给出该 item 的 item_id」当场落空。
    """

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        try:
            yield from engine_iter_store_rows(self._spec, payload)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("payload unreadable") from exc  # ← 原生文案被吞掉


class _RejectEverythingRowReader(_SilentlyEmptyRowReader):
    """🔴 变异 M3：**合法载荷也抛** —— 合法对照组必须对它为 False。

    没有对照组时，「非法载荷一律抛」这条 property 对本替身**恒真** ⇒ 判据没有区分力。
    """

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        raise RuntimeError(f"{self.item_id} 一律拒收")
        yield  # pragma: no cover —— 让它是生成器函数，与生产实现同形


class TestProperty9JudgesCanBeFalse:
    """三组变异反证：同一批判据喂替身，必须**打红**（这里用 `pytest.raises(AssertionError)` 钉住）。"""

    FORMS_UNDER_TEST = _UNREADABLE_FORMS

    def _payload(self, form: str, identity_key: str) -> tuple[Any, int]:
        return _unreadable_payload(
            form,
            identity_key=identity_key,
            noise="x",
            as_json_text=True,
            lead_rows=0,
            bad_pick=0,
        )

    #: 🔴 M1 在**计划层**的打红理由随载荷形态二分 —— 见
    #: :meth:`test_m1_silently_empty_reader_is_caught` docstring（现算实证，不是推演）。
    M1_PLAN_RED_REASON = {
        "invalid_json": "没有 item_id",
        "json_object": "没有 item_id",
        "json_scalar": "没有 item_id",
        "non_object_element": "没有抛",
    }

    @pytest.mark.parametrize("form", FORMS_UNDER_TEST)
    def test_m1_silently_empty_reader_is_caught(self, form: str) -> None:
        """M1：静默当零行 ⇒ 判据为 False，reader 层与计划层**都**打红（理由按形态二分）。

        🔴 **本轮实测抓到的生产现状**（首版把计划层也写成必报「没有抛」，跑出 3 红才发现）：
        计划层对「reader 的 fail-visible 语义被弱化」**有一条兜底防线**，但它只覆盖一半形态 ——

        * 载荷**不是 list**（前三形态）：`_as_row_list` 走 `_reject_unreadable_payload`，
          它发现 reader 没拒收就自己抛 `OverwritePlanShapeError` ⇒ 判据 ①（必抛）**成立**，
          但那条兜底文案是「载荷形态为 {type}，本函数无从按位置重建……」——🔴 **不带 item_id**
          ⇒ 打红的是判据 ②。Requirement 4.4 要的「给出该 item 的 item_id」在这条路上拿不到。
        * 载荷**是 list**（第四形态 `[1]`）：`_as_row_list` 原样返回它，之后**没有任何兜底** ——
          M1 吞掉引擎异常后 `doomed` 为空 ⇒ prune 返回 `(payload, ())` ⇒ 判据 ① 打红。

        🔴 而 `compute_overwrite_plan`（Task 4.2）**四形态一律没有兜底** ⇒ compute 层的打红理由
        不分形态，都是「没有抛」，且实测它会把 substrate 侧身份整批报成 `rows_added`
        （见 :func:`_assert_compute_plan_fails_visible`）。三层的差异本身就是要被看见的信息。

        ⇒ 以上现状如实登记，**不在本任务修**（Task 3.6 只写测试；`OverwritePlanShapeError`
        的文案与 422 族归属属 Task 6.2 的工作面，见 `adopt_row_reader` 的「Requirement 4.4
        分工裁定」）。若日后给那条兜底文案补上 item_id，或把兜底扩到 list 形态，本表就会打红 ——
        那是**该有的**提醒，改表前先确认是真的改好了而不是绕开。
        """
        assert set(self.M1_PLAN_RED_REASON) == set(_UNREADABLE_FORMS), (
            "形态域与打红理由表漂了 —— 少一格就会有形态没被反证覆盖"
        )
        spec = _spec(identity_key=IDENTITY_KEYS[0])
        payload, first_bad = self._payload(form, IDENTITY_KEYS[0])
        mutant = _SilentlyEmptyRowReader(spec=spec)
        # 前提对照：生产实现在同一载荷上确实抛（否则这条反证没有对照组）
        _assert_reader_fails_visible(
            _readers(spec)[0][1], payload, label="生产实现", first_bad_index=first_bad
        )
        # reader 层：四形态一律「没有抛」
        with pytest.raises(AssertionError, match="没有抛"):
            _assert_reader_fails_visible(
                mutant, payload, label="M1", first_bad_index=first_bad
            )
        # 计划层：必打红，理由按上表二分
        with pytest.raises(AssertionError, match=self.M1_PLAN_RED_REASON[form]):
            _assert_plan_fails_visible(mutant, payload, label="M1")
        # compute 层：四形态一律「没有抛」，且打红文案里能看到 rows_added 被虚报
        with pytest.raises(AssertionError, match="没有抛"):
            _assert_compute_plan_fails_visible(mutant, payload, label="M1")

    @pytest.mark.parametrize("form", FORMS_UNDER_TEST)
    def test_m2_message_without_item_id_is_caught(self, form: str) -> None:
        """M2：抛了但消息不带 item_id ⇒ 判据 ② 为 False（且 ① 仍成立，证明两条判据可分辨）。"""
        spec = _spec(identity_key=IDENTITY_KEYS[0])
        payload, first_bad = self._payload(form, IDENTITY_KEYS[0])
        mutant = _AnonymousRejectRowReader(spec=spec)
        # ① 对 M2 成立：它**确实**抛了 —— 所以「抛了」与「消息带 item_id」不是同一条判据
        with pytest.raises(ValueError, match="payload unreadable"):
            list(mutant.iter_rows(payload))
        with pytest.raises(AssertionError, match="没有 item_id"):
            _assert_reader_fails_visible(
                mutant, payload, label="M2", first_bad_index=first_bad
            )
        with pytest.raises(AssertionError, match="没有 item_id"):
            _assert_plan_fails_visible(mutant, payload, label="M2")
        with pytest.raises(AssertionError, match="没有 item_id"):
            _assert_compute_plan_fails_visible(mutant, payload, label="M2")

    def test_m3_rejecting_legal_payload_is_caught(self) -> None:
        """M3：合法载荷也抛 ⇒ 合法对照组为 False（这条就是「一律抛也能通过」的反证）。"""
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        rows = [_legal_row(identity_key, "legal-0")]
        mutant = _RejectEverythingRowReader(spec=spec)
        # 🔴 非法侧的**三条**判据对 M3 全部恒真（它连 item_id 都带对了）—— 正是它为什么必须被
        #    合法对照组抓住：只有「合法载荷不许抛」这一条能把「一律拒收」的实现判红。
        payload, first_bad = self._payload("json_scalar", identity_key)
        _assert_reader_fails_visible(mutant, payload, label="M3", first_bad_index=first_bad)
        _assert_plan_fails_visible(mutant, payload, label="M3")
        _assert_compute_plan_fails_visible(mutant, payload, label="M3")
        with pytest.raises(AssertionError, match="合法"):
            _assert_legal_payload_enumerates(
                mutant, rows, label="M3", expected=["legal-0"]
            )
        # 对照：生产实现在同一合法载荷上通过
        for label, reader in _readers(spec):
            _assert_legal_payload_enumerates(
                reader, rows, label=label, expected=["legal-0"]
            )

    def test_matrix_covered_every_form_on_every_reader(self) -> None:
        """🔴 12 格覆盖矩阵：4 形态 × 3 reader 实现，一格不缺（定义在最后，属性测试已跑过）。"""
        if not _P9_MATRIX:
            pytest.skip("本次选择未执行 Property 9（如 -k 定向）⇒ 累计器为空，本判据无从成立")
        labels = tuple(label for label, _reader in _readers(_spec(identity_key=IDENTITY_KEYS[0])))
        assert len(labels) == 3, f"reader 实现数变了（现得 {labels}）⇒ 矩阵分母须同步更新"
        expected = {(form, label) for form in _UNREADABLE_FORMS for label in labels}
        assert _P9_MATRIX == expected, (
            f"未覆盖的格子 {sorted(expected - _P9_MATRIX)}；多出的格子 "
            f"{sorted(_P9_MATRIX - expected)}（应为 {len(expected)} 格）"
        )
