"""adopt 覆盖计划 —— 行枚举层的 **property 测试**（行身份 / 载荷形态两条）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 4.4 / 4.5

本文件承载的 property（**一条一函数**，文件按 property 归集而非按任务归集）：

| Property | 归属任务 | 状态 |
| --- | --- | --- |
| **Property 10: 行身份识别与键名无关** | Task 3.5 | ✅ 本文件已实现 |
| **Property 9: 非法载荷一律 fail visible** | Task 3.6 | ✅ 已实现，在**伴生文件**（见文末指针） |

🔴 **Task 3.6 的落点结论（实测后修正 Task 3.5 的预判）**：Task 3.5 预判「Property 9 可追加进
本文件」，并要求追加前先数行数。实测 = 本文件 **538** + Property 9 段 **521** = **1059** ⇒ 远越
`.py` 门禁 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit 与 CI 的
`file-size-guard` 同源）⇒ 按门禁自己给的处置顺序抽伴生文件
`test_aos_property_unreadable_payload.py`，它**复用**本文件的
`_spec()` / `_engine_backed_facade()` / `_provider()` / `_readers()` / `ITEM` / `IDENTITY_KEYS`
（禁抄第二份建造器 —— 两边的合成 `RowTableSheetSpec` 一漂，两条 property 就在测不同的东西）。

═══ 为什么不是追加进两个既有文件 ═══

`test_aos_row_reader_adapter.py`（Task 3.4）与 `test_aos_row_reader_r3.py`（Task 3.7）交付后分别
**483** / **542** 行，且它们守的是**例子级**契约（挑真实 item 验行为），与 property 的
「对任意取值成立」不是一回事 —— 混在一起会让「这条断言是例子还是全称」不可分辨。

═══ Property 10 与 Task 3.4 的 `TestIdentityKeyIndependence` 不重复 ═══

* Task 3.4（例子级）：挑 **4** 个真实 item，证「这几个真 item 能枚举」，并断言样本跨 ≥3 种键名；
* 本文件（属性级）：对**现算得到的全部**行身份键名取值**穷举**，证「键名不是变量」。

🔴 **为什么键名维度用 `parametrize` 穷举而不是 `st.sampled_from` 抽样**：现算 7 种取值里
`rowId` 独占 **65/103** 处，而 PBT 配置是 `max_examples=5`（用户明确要求，禁默认 100）⇒ 抽样
既覆盖不到 7 种、又极可能连续命中 `rowId`，而 `rowId` 恰是**硬编码实现也能通过**的那一个
（见 `TestHardcodedRowIdIsCaught`：同一批载荷喂给硬编码 `row["rowId"]` 的替身，只有 `rowId`
这一个键会「通过」）⇒ 抽样式生成器会把一个硬编码实现判绿。故键名穷举、载荷随机。
"""
from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adopt_row_reader import (
    _FacadeRowReader,
    diagnose_row_reader,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import (
    EngineRowReader,
    ReconcilingRowReader,
    global_spec_index,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    iter_store_rows as engine_iter_store_rows,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 现算键名取值域（🔴 禁写死：生成器的取值域从**声明**现取，不是字面量清单）
# ═══════════════════════════════════════════════════════════════════════════

#: workpaper_sync 生产目录。`__file__` = backend/tests/workpaper_sync/… ⇒ parents[2] = backend。
_WS_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "workpaper_sync"

#: 行身份键常量的名字前缀（design § Overview 的 Task 1.1 口径）。
_IDENTITY_CONST_PREFIX = "ROW_IDENTITY_STORE_KEY"

#: design §4.1b(4) 的现场反例载体：item-blind 门面所在的 D4 provider 模块。
_D4_PROVIDER = "app.services.workpaper_sync.phase5_d4_revenue_detail"

#: 本文件合成用的 store item 身份。刻意带 `AOS-P10`，万一漏进任何输出都能被搜到。
ITEM = "AOS-P10-SYNTH-rows"


def identity_key_census() -> tuple[dict[str, int], int, int]:
    """现算 `ROW_IDENTITY_STORE_KEY*` 的**字面量**取值分布。

    返回 `(取值 -> 处数, 非字面量处数, 赋值处总数)`。

    口径与 design § Overview 逐字一致，且**只用 AST**（平台铁律㉖：文本匹配会被 docstring /
    `#` 注释两向骗过 —— 本 spec 的 `row_section_field=` 那一行正是被文本匹配误报出 7 处的）：
    `ast.Assign` / `ast.AnnAssign`，目标是 `ast.Name` 且名字以前缀起，值取 `ast.Constant[str]`。
    值为 `ast.Attribute`（跨模块引用常量）的单独计数，用于对账
    `字面量处数 + 非字面量处数 == 总处数`。
    """
    literals: dict[str, int] = {}
    non_literal = 0
    total = 0
    for path in sorted(_WS_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover - 树坏了要看见
            raise AssertionError(f"{path} 解析失败：{exc} —— 现算口径失效，不得静默跳过") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            else:
                continue
            for _name in [n for n in names if n.startswith(_IDENTITY_CONST_PREFIX)]:
                total += 1
                value = getattr(node, "value", None)
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literals[value.value] = literals.get(value.value, 0) + 1
                else:
                    non_literal += 1
    return literals, non_literal, total


_CENSUS_LITERALS, _CENSUS_NON_LITERAL, _CENSUS_TOTAL = identity_key_census()

#: 🔴 **参数化取值域 = 现算域**（本轮实得 7 种；值与处数一律现算，判据不得写死）。
IDENTITY_KEYS: tuple[str, ...] = tuple(sorted(_CENSUS_LITERALS))

#: 本次运行**实际**被 Property 10 跑过的键名（反证「生成器退化成只生成 rowId」）。
_EXERCISED_KEYS: set[str] = set()


def declared_section_fields() -> tuple[str, ...]:
    """现算全域声明过的分区字段名（`RowTableSheetSpec.row_section_field` 的非空取值）。

    🔴 禁硬编码字段名（含 `"section"`）—— design § Overview 已登记合同清单里的
    `"row_section_field": "section"` 是**描述性元数据不是真源**（5 处里 4 处与功能声明不符）。
    """
    values = {
        str(getattr(spec, "row_section_field", "") or "")
        for specs in global_spec_index().values()
        for spec in specs
    }
    values.discard("")
    return tuple(sorted(values))


_SECTION_FIELDS = declared_section_fields()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 建造器（Task 3.6 可直接复用）
# ═══════════════════════════════════════════════════════════════════════════


def _spec(
    *, identity_key: str, section_field: str = "", section_value: str = ""
) -> RowTableSheetSpec:
    """造一条**真** `RowTableSheetSpec`（不是替身 dataclass）。

    🔴 用真声明类而不是 `_StubSpec`：引擎的身份提取走 `spec.row_identity_key`，用替身会把
    「引擎真的按声明取键」这件事换成「替身按声明取键」—— 那就测不到生产代码了。几何字段
    （sheet / 行号 / Table 名）与行枚举无关，给合成值即可（引擎 `iter_store_rows` 只读
    `store_item_id` / `row_identity_key` / `row_section_field` / `row_section_value`）。
    """
    return RowTableSheetSpec(
        managed_sheet="合成受管表AOS-P10",
        sheet_key="aos-p10-managed",
        table_key="aos_p10_rows",
        template_id="AOS_P10",
        table_name="AosP10Rows",
        uuid_col="Z",
        first_data_row=2,
        last_data_row=9,
        footer_row=10,
        store_item_id=ITEM,
        row_identity_key=identity_key,
        row_section_field=section_field,
        row_section_value=section_value,
    )

def _engine_backed_facade(spec: RowTableSheetSpec) -> Callable[..., Iterator[Any]]:
    """item-aware 门面 —— 形态与现算 25 个真门面同构：**薄转发到引擎**，自己不解析载荷。

    🔴 `store_item_id` 不符即抛，**不回退**到模块自己的 `STORE_ITEM_ID`（design §4.1b L3：
    真门面普遍写成 `_spec_of_store_item(store_item_id or STORE_ITEM_ID)`，那条回退正是探针 v1
    把任何假 item_id 都判成可枚举的根因）。
    """

    def iter_store_rows(payload: Any, *, store_item_id: str | None = None) -> Iterator[Any]:
        if store_item_id is not None and store_item_id != spec.store_item_id:
            raise LookupError(f"store item {store_item_id!r} 不在本合成 provider 的受管清单里")
        yield from engine_iter_store_rows(spec, payload)

    return iter_store_rows


def _provider(spec: RowTableSheetSpec) -> Any:
    """provider 模块替身：只提供**声明面** + 门面，枚举仍由真引擎做。"""
    return SimpleNamespace(
        __name__=__name__,
        iter_store_rows=_engine_backed_facade(spec),
        managed_row_table_specs=lambda: (spec,),
    )


def _readers(spec: RowTableSheetSpec) -> tuple[tuple[str, Any], ...]:
    """把**三个**已落地的 `RowReader` 实现各造一份（Property 10 要求全覆盖）。

    1. `EngineRowReader`（Task 3.7，R3 路）；
    2. `_FacadeRowReader`（Task 3.4，① 级门面路）；
    3. `ReconcilingRowReader`（Task 3.7，两路都可用时的对账包装）—— 它同时是一条**隐含判据**：
       若两路对同一载荷枚举出的身份集合不等，它会当场 `OverwritePlanShapeError`，
       于是「只有一路按声明取键」这种半对的实现也会被打红。
    """
    scopes = ((spec.table_key, spec.row_section_value or None),)
    engine = EngineRowReader(
        item_id=ITEM,
        specs=(spec,),
        section_field=spec.row_section_field,
        declared_scopes=scopes,
    )
    facade = _FacadeRowReader(
        item_id=ITEM,
        invoke=lambda payload: _engine_backed_facade(spec)(payload, store_item_id=ITEM),
        section_field=spec.row_section_field,
        declared_scopes=scopes,
    )
    return (
        ("EngineRowReader", engine),
        ("_FacadeRowReader", facade),
        ("ReconcilingRowReader", ReconcilingRowReader(item_id=ITEM, primary=facade, shadow=engine)),
    )

# ═══════════════════════════════════════════════════════════════════════════
# 2. 生成器（智能约束到合法输入空间）
# ═══════════════════════════════════════════════════════════════════════════

#: 行身份字符集。🔴 刻意**不含大写 `D`** —— 诱饵值一律以 `DECOY-` 开头，两者不得可能相撞，
#: 否则「诱饵没被采用」这条断言就有假绿的余地。含 `/` 与中文：D4-22 的身份是自由文本指标名
#: （`运输费用/营业收入` 现算含 `/`），ASCII-only 生成器测不到那一族。
_IDENTITY_ALPHABET = "abcxyz0179-/运输费用营业收入"

#: 噪声字段名池。三者均**不在**现算身份键取值域内、也不在现算分区字段名内（测试里现验，
#: 见 `test_noise_pool_cannot_masquerade_as_identity_or_section`）。
_NOISE_KEYS = ("amount", "remark", "已审金额")

_IDENTITIES = st.lists(
    st.text(alphabet=_IDENTITY_ALPHABET, min_size=1, max_size=10),
    min_size=1,
    max_size=4,
    unique=True,
)


def _row(
    identity_key: str,
    identity: str,
    *,
    noise: Mapping[str, str],
    section: tuple[str, str],
) -> dict[str, Any]:
    """造一行：身份落在 `identity_key` 上，**其余 6 个现算键名全部布成诱饵**。

    🔴 诱饵是本 property 的要害：任何「按已知键名集合嗅探」的实现（`row.get("rowId") or
    row.get("id") or …`）都会取到 `DECOY-…` 而不是真身份 ⇒ 判据当场为 False。少了这一步，
    property 只能抓「键名完全取不到」，抓不到「取到了别的键」。
    """
    row: dict[str, Any] = {k: f"DECOY-{k}" for k in IDENTITY_KEYS if k != identity_key}
    row.update(noise)
    section_field, section_value = section
    if section_field:
        row[section_field] = section_value
    row[identity_key] = identity  # 🔴 最后写：保证任何 noise/诱饵都不会盖掉真身份
    return row

# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 10（Task 3.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty10RowIdentityIsKeyNameAgnostic:
    """Property 10：以任意现算键名承载身份的载荷都应被正确枚举出**全部**行身份。"""

    @pytest.mark.parametrize("identity_key", IDENTITY_KEYS)
    @settings(max_examples=5, deadline=None)
    @given(
        identities=_IDENTITIES,
        noise=st.dictionaries(st.sampled_from(_NOISE_KEYS), st.text(max_size=6), max_size=3),
        as_json_text=st.booleans(),
        declare_section=st.booleans(),
    )
    def test_property_10_every_computed_identity_key_enumerates(
        self,
        identity_key: str,
        identities: list[str],
        noise: dict[str, str],
        as_json_text: bool,
        declare_section: bool,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 10: 行身份识别与键名无关

        **Validates: Requirements 4.5**

        四个随机维度：行身份取值（含 `/` 与中文）、噪声字段、载荷是 JSON 文本还是已解析序列
        （引擎两条分支都要走到）、是否声明分区维度。键名维度**穷举**，理由见模块 docstring。
        """
        _EXERCISED_KEYS.add(identity_key)

        section_field, section_value = "", ""
        if declare_section:
            usable = [f for f in _SECTION_FIELDS if f != identity_key and f not in noise]
            if usable:
                # 🔴 分区值必须非空：声明了 field 而 value 为空是**退化声明**，
                #    `adopt_row_reader._section_field_of` 明写要当场抛（Task 3.1 的约定）。
                section_field, section_value = usable[0], "aos-p10-seg"
        spec = _spec(
            identity_key=identity_key,
            section_field=section_field,
            section_value=section_value,
        )
        rows = [
            _row(identity_key, ident, noise=noise, section=(section_field, section_value))
            for ident in identities
        ]
        payload: Any = json.dumps(rows, ensure_ascii=False) if as_json_text else rows

        for label, reader in _readers(spec):
            got = list(reader.iter_rows(payload))
            where = f"{label} / 键名 {identity_key!r} / 分区 {section_field!r}"
            assert [i for i, _ in got] == identities, f"{where}：身份序列不等"
            assert all(isinstance(row, Mapping) for _, row in got), f"{where}：行不是 Mapping"
            assert all(
                str(row[identity_key]) == identity for identity, row in got
            ), f"{where}：yield 出的身份与该行 {identity_key!r} 字段值不一致"
            assert not [i for i, _ in got if i.startswith("DECOY-")], (
                f"{where}：采用了诱饵键的值 —— 实现在按已知键名集合嗅探，而不是按声明取键"
            )
            expected_section = section_value if section_field else None
            assert all(
                reader.section_of(row) == expected_section for _, row in got
            ), f"{where}：分区归属不等于声明值"

    @pytest.mark.parametrize("identity_key", IDENTITY_KEYS)
    def test_resolution_path_honours_every_computed_identity_key(self, identity_key: str) -> None:
        """同一条 property 走**完整判定链**（`diagnose_row_reader` 的 L2~L4 探活）。

        为什么与上面那条分开：`diagnose_row_reader` 里的 L4 正面判据会**自己**按声明合成探活行
        （`_probe_rows`），那是除引擎之外第二处可能硬编码键名的地方；而它每次都要建一次全域
        spec 索引（禁缓存，ADR-AOS-005 §5(1)），不适合塞进 `@given` 的内循环。
        故键名仍穷举、载荷固定。
        """
        spec = _spec(identity_key=identity_key)
        resolution = diagnose_row_reader(provider=_provider(spec), store_item_id=ITEM)
        assert resolution.is_enumerable, (
            f"键名 {identity_key!r} 判成不可枚举：{resolution.detail} —— L4 探活的合成行身份键"
            "必须取自 `RowTableSheetSpec.row_identity_key`，任何键名字面量都会在这里露出来"
        )
        assert resolution.reader is not None
        identities = ["a1", "b2", "运输费用/营业收入"]
        rows = [
            _row(identity_key, ident, noise={}, section=("", "")) for ident in identities
        ]
        got = list(resolution.reader.iter_rows(rows))
        assert [i for i, _ in got] == identities, identity_key
        assert not [i for i, _ in got if i.startswith("DECOY-")], identity_key


# ═══════════════════════════════════════════════════════════════════════════
# 4. 变异反证 —— 判据必须能为 False
# ═══════════════════════════════════════════════════════════════════════════


class _HardcodedRowIdReader:
    """🔴 **被 Requirement 4.5 明令禁止**的实现形态：`row["rowId"]` 兜底。

    只存在于本测试文件，用途是证明 Property 10 有区分力。它同时说明了两件事：

    1. 为什么键名维度必须**穷举**：本替身对 `rowId` 这一个键名**完全通过**，而 `rowId` 在现算
       103 处字面量里独占 65 处 ⇒ 抽样式生成器很可能只看到它，于是把硬编码实现判绿；
    2. 为什么行里要布**诱饵**：没有诱饵时本替身在非 `rowId` 键上抛 `KeyError`（还算显眼），
       有诱饵时它会**静默返回错身份** —— 后者才是真实危害（错身份 ⇒ 既有行被当成
       `rows_added`、真行被当成 `rows_deleted`，而删除侧是本 spec 唯一破坏性的一侧）。
    """

    def __init__(self, *, item_id: str) -> None:
        self.item_id = item_id

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        rows = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
        for row in rows:
            yield str(row["rowId"]), row  # ← 就是那条被禁的兜底

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        return None

class TestHardcodedRowIdIsCaught:
    """把硬编码 `rowId` 的替身喂同一批载荷 —— Property 10 的断言必须对它为 False。"""

    IDENTITIES = ("a1", "b2", "运输费用/营业收入")

    def _enumerate(self, reader: Any, rows: list[dict[str, Any]]) -> list[str] | None:
        """枚举；抛异常一律记 `None`（抛与错值都算「判据为 False」，但要能区分）。"""
        try:
            return [identity for identity, _row in reader.iter_rows(rows)]
        except Exception:  # noqa: BLE001 —— 本函数就是在观测「会不会炸」
            return None

    @pytest.mark.parametrize("identity_key", IDENTITY_KEYS)
    def test_mutant_reproduces_identities_only_for_row_id(self, identity_key: str) -> None:
        """🔴 变异反证的核心断言：替身只在 `rowId` 上通过，在其余现算键名上一律失败。"""
        rows = [
            _row(identity_key, ident, noise={}, section=("", ""))
            for ident in self.IDENTITIES
        ]
        production = _readers(_spec(identity_key=identity_key))[0][1]
        assert self._enumerate(production, rows) == list(self.IDENTITIES), (
            f"生产实现在键名 {identity_key!r} 上就枚举不出来 —— 下面的反证会失去对照组"
        )
        mutant = self._enumerate(_HardcodedRowIdReader(item_id=ITEM), rows)
        if identity_key == "rowId":
            assert mutant == list(self.IDENTITIES), (
                "硬编码替身在 `rowId` 上**必须**通过 —— 这正是「抽样式生成器会把硬编码实现"
                "判绿」的机理；它不通过说明本反证的前提变了，须重查"
            )
        else:
            assert mutant != list(self.IDENTITIES), (
                f"硬编码 `rowId` 的替身在键名 {identity_key!r} 上居然通过了 ⇒ Property 10 的"
                "断言对这类实现没有区分力（判据不能为 False = 假绿）"
            )

    def test_mutant_returns_a_wrong_identity_rather_than_raising(self) -> None:
        """诱饵在场时替身**静默返错**（不抛）—— 这是它真正的危害形态，须显式钉住。"""
        others = [k for k in IDENTITY_KEYS if k != "rowId"]
        assert others, "现算键名域只剩 rowId ⇒ 整条 Property 10 失去意义，须回 spec 登记"
        rows = [_row(others[0], "a1", noise={}, section=("", ""))]
        got = self._enumerate(_HardcodedRowIdReader(item_id=ITEM), rows)
        assert got == ["DECOY-rowId"], f"替身未静默返回诱饵值，实得 {got!r}"

class TestD4LiveCounterexample:
    """design §4.1b(4) 的**现场**反例：同一个 D4 provider 模块，一键套全部 item 必错。"""

    #: 被点名的三个 item → `(声明模块, 身份键常量名)`。🔴 键值现取，测试里不写键名字面量。
    NAMED = (
        ("D4-22-rows", "phase5_d4_ipo_related_sheets", f"{_IDENTITY_CONST_PREFIX}_D422"),
        ("D4-23-rows", "phase5_d4_ipo_related_sheets", f"{_IDENTITY_CONST_PREFIX}_D423"),
        ("D4-35-data", "phase5_d4_other_check_sheet", f"{_IDENTITY_CONST_PREFIX}_D435"),
    )

    def _d4(self) -> Any:
        return importlib.import_module(_D4_PROVIDER)

    def test_one_module_declares_several_identity_key_kinds(self) -> None:
        """现算 D4 provider 的运行时命名空间：多个常量、**多种**取值。

        🔴 口径必须是**运行时命名空间**（`dir(module)`）而不是单文件 AST —— 该 provider 把子
        模块常量 re-export 进来了，只读 `phase5_d4_revenue_detail.py` 的 AST 只能看到 1 个。
        🔴 计数现算、不写死：断言写成「种数 > 1」+ 在消息里报出现算值，design 记的是 8 个常量 /
        4 种取值（`rowId` ×5 / `metricName` / `month` / `id`）。
        """
        d4 = self._d4()
        names = sorted(n for n in dir(d4) if n.startswith(_IDENTITY_CONST_PREFIX))
        values = {name: str(getattr(d4, name)) for name in names}
        kinds = sorted(set(values.values()))
        assert len(names) > 1 and len(kinds) > 1, (
            f"现算 {len(names)} 个常量 / {len(kinds)} 种取值 {kinds}（design §4.1b(4) 记 8 / 4）"
            " —— 若真收敛成 1 种，D4 反例已失效，须回 spec 登记而不是留着这条空判据"
        )
        assert all(v in IDENTITY_KEYS for v in kinds), (
            f"D4 的取值 {kinds} 不在现算全域取值域 {list(IDENTITY_KEYS)} 内 ⇒ 两处口径漂了"
        )

    def test_the_facade_key_cannot_enumerate_the_named_items(self) -> None:
        """门面写死的那个键，对三个被点名 item 的声明键**一律取不到身份**。"""
        d4 = self._d4()
        facade_key = str(getattr(d4, _IDENTITY_CONST_PREFIX))
        for item_id, module_suffix, const in self.NAMED:
            module = importlib.import_module(f"app.services.workpaper_sync.{module_suffix}")
            declared = str(getattr(module, const))
            assert declared != facade_key, (
                f"{item_id} 的声明键与门面写死的 {facade_key!r} 相同 ⇒ 这一条不再是反例"
            )
            row = {declared: f"{item_id}-r1"}
            assert row.get(facade_key) is None, (
                f"拿 {facade_key!r} 去读 {item_id}（声明 {declared!r}）竟取到了值"
            )
            # 正面对照：按**声明**取键的生产实现读得出来。
            reader = _readers(_spec(identity_key=declared))[0][1]
            assert [i for i, _ in reader.iter_rows([row])] == [f"{item_id}-r1"], item_id

# ═══════════════════════════════════════════════════════════════════════════
# 5. 反「生成器退化」判据（现算复核 + 覆盖面）
# ═══════════════════════════════════════════════════════════════════════════


class TestKeyDomainIsLiveComputed:
    """取值域是**现算**出来的，且 Property 10 真的跑遍了它。"""

    def test_census_balances_and_matches_the_spec_table(self) -> None:
        """现算复核 design § Overview「行身份键字面量取值」那一行，并做对账等式。"""
        literals, non_literal, total = identity_key_census()
        assert tuple(sorted(literals)) == IDENTITY_KEYS, "两次现算不一致 ⇒ 口径不稳定"
        assert sum(literals.values()) + non_literal == total, (
            f"对账失败：字面量 {sum(literals.values())} + 非字面量 {non_literal} != 总数 {total}"
        )
        assert len(IDENTITY_KEYS) >= 7, (
            f"现算取值种数 {len(IDENTITY_KEYS)}（design 记 7 种：{list(IDENTITY_KEYS)}）—— "
            "少于 7 说明取值域收窄了，须回 spec 登记差异，不得默认沿用"
        )
        # 变异对照：分母非空，扫描器不是「什么都没扫到所以说没有」。
        assert total > 0 and non_literal > 0, (
            f"总处数 {total} / 非字面量 {non_literal} —— 两者任一为 0 说明 AST 口径失效"
        )

    def test_generator_domain_is_not_degenerated_to_row_id(self) -> None:
        """🔴 反证「生成器只生成 `rowId`」：参数化取值域 == 现算域，且 `rowId` 只占其中一项。"""
        assert set(IDENTITY_KEYS) == set(identity_key_census()[0])
        assert "rowId" in IDENTITY_KEYS and len(IDENTITY_KEYS) > 1
        dominant = max(_CENSUS_LITERALS.items(), key=lambda kv: kv[1])
        assert dominant[0] == "rowId" and dominant[1] * 2 > sum(_CENSUS_LITERALS.values()), (
            f"现算最高频键名是 {dominant}（design 记 rowId 65/103）—— 它过半正是"
            "「抽样必偏向 rowId」的原因，也是本文件把键名维度改成穷举的依据"
        )

    def test_noise_pool_cannot_masquerade_as_identity_or_section(self) -> None:
        """噪声字段名不得撞身份键或分区字段名（否则噪声会篡改被测语义）。"""
        assert not set(_NOISE_KEYS) & set(IDENTITY_KEYS), _NOISE_KEYS
        assert not set(_NOISE_KEYS) & set(_SECTION_FIELDS), _NOISE_KEYS
        assert _SECTION_FIELDS, "现算分区字段名为空 ⇒ 分区维度没被生成器覆盖，须查索引是否失效"

    def test_property_10_really_exercised_every_computed_key(self) -> None:
        """本次运行**实际**覆盖的键名种数 == 现算域大小（定义在最后，故属性测试已跑过）。"""
        if not _EXERCISED_KEYS:
            pytest.skip("本次选择未执行 Property 10（如 -k 定向）⇒ 累计器为空，本判据无从成立")
        assert _EXERCISED_KEYS == set(IDENTITY_KEYS), (
            f"实际覆盖 {sorted(_EXERCISED_KEYS)}（{len(_EXERCISED_KEYS)} 种）"
            f"≠ 现算域 {list(IDENTITY_KEYS)}（{len(IDENTITY_KEYS)} 种）"
        )


# ── Property 9（Task 3.6）已交付，落在**伴生文件** ────────────────────────────
# `test_aos_property_unreadable_payload.py`（Property 9: 非法载荷一律 fail visible）。
# 🔴 为什么不在本文件：Task 3.5 留位时本文件 538 行、Property 9 段实测 521 行 ⇒ 合计 1059
#    已越过 `.py` 门禁 800（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit
#    与 CI 的 `file-size-guard` 同源）。域内同样处置已有先例（`phase5_g9_store_facade.py` /
#    `adopt_row_reader.py` / `adopt_row_reader_r3.py`）。伴生文件**复用**本文件的
#    `_spec` / `_readers` / `ITEM` / `IDENTITY_KEYS` / `_IDENTITY_ALPHABET`，不另造建造器。
