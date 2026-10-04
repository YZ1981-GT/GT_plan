"""D1 整册门根因判据：entry 模块必须向 registry 暴露**全部** 18 组 instrumentation 声明。

═══ 这组判据守的是什么 ═══

`d1-sync-row-table-engine-and-d1-coverage` 的整册 representation 发布长期失败，报的是
`ContractDriftError`（首个点名 `d110-managed / inventory_count_rows/{row_uuid}/acceptor`）。
表面看像「数据没准备好」，实测证明是**结构上从来不可能成功**：

扩容面（12 受管 sheet / 18 行表）声明在伴生模块 `phase5_d1_expansion`，但平台的两个
读取点 **只读 registry 解析出的 entry 模块**（`phase5_d1_notes_receivable`）：

  1. `projection_first_publication.stage_instrumented_substrate` 的分派顺序是
     「先看 `instrumentation_specs`（复数），没有才回落 `instrumentation_spec`（单数）」；
  2. `instrumentation_definition_payload` 是**请求时刻**锚点的唯一来源
     （`load_frozen_structure_anchors` → `frozen_anchors_from_instrumentation`）。

entry 模块此前只有单数入口，于是实测形态是（逐阶段 Table 数）：

    authoritative     0 表（未 instrument，正常）
    instrumented     18 表  ← `instrument_workbook_bytes_multi` 本身是对的
    openpyxl 重保存   18 表  ← 重保存也不丢表
    staged substrate  **1 表**  🔴 只剩 `GT_D13_ROWS`

`observe_structure_inventory` 因此只认到 1 张受管 sheet，相对契约声明的 248 字段
少给绝大部分 → `assert_no_structure_drift` 抛 `ContractDriftError`。

═══ 变异方向（这些判据必须能打红下列每一种退化）═══

  * 删掉 entry 模块的 `instrumentation_specs` 复数入口 → `test_provider_surfaces_plural_entry`
    与 `test_staged_substrate_carries_every_declared_table` 双双转红；
  * 把 `instrumentation_definition_payload` 改回单数 `build_instrumentation_payload`
    → `test_frozen_request_time_anchors_cover_every_managed_sheet` 转红；
  * 复数入口只返回主 spec（`return (instrumentation_spec(),)`）
    → `test_provider_surfaces_plural_entry` 的数量断言转红；
  * 伴生模块少声明一张表 → `test_contract_and_specs_agree_on_managed_surface` 转红。

这四条**不是**「跑一次全绿就收」：数量断言写的是现算等式（契约 ↔ specs ↔ staged 产物
三方相等），任一侧单独改都会打破等式，而不是三方一起漂移还恒绿。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.excel_structure_fingerprint import structure_fingerprint
from app.services.workpaper_sync import phase5_d1_expansion as EXP
from app.services.workpaper_sync import phase5_d1_notes_receivable as D1
from app.services.workpaper_sync import projection_first_publication as PUB
from app.services.workpaper_sync.contracts import declared_structure_inventory
from app.services.workpaper_sync.excel_instrumentation import (
    build_instrumentation_payload,
    build_instrumentation_payload_for_sheets,
)
from app.services.workpaper_sync.publish_time_structure_hash import (
    anchors_from_instrumentation_spec,
    anchors_from_instrumentation_specs,
)
# 🔴 请求时刻的复数锚点读取口是 `_frozen_sheet_anchors`（`load_frozen_structure_anchors`
#    内部就调它），**不是** `frozen_anchors_from_instrumentation` —— 后者返回的是
#    单个 anchor dict（4 个键），对它取 `len()` 会得到 4 这个与 sheet 数无关的常量。
#    第一版判据踩过这个坑：18 组 specs 的 payload 被读成「4 组锚点」。
from app.services.workpaper_sync.published_identity_observer import _frozen_sheet_anchors

ENTRY_ID = "xlsx/gt-d1-notes-receivable"


@pytest.fixture(scope="module")
def contract():
    return D1.load_contract_from_disk()


@pytest.fixture(scope="module")
def staged_tables() -> frozenset[str]:
    """真实走一遍 `stage_instrumented_substrate`，取产物里的 Excel Table displayName。

    这是**产物级**证据，不是「调用了某个函数」级证据 —— 只验接线的断言查不出
    「分派落进回落臂」这类缺陷（回落臂也是一次正常调用）。
    """
    contract = D1.load_contract_from_disk()
    with tempfile.TemporaryDirectory(prefix="d1-specs-fwd-") as tmp:
        staged = PUB.stage_instrumented_substrate(
            entry_id=ENTRY_ID, staging_dir=Path(tmp), contract=contract
        )
        data = Path(staged.staged_path).read_bytes()
    fp = structure_fingerprint(data)
    return frozenset(str(t.get("display_name")) for t in fp.tables)


# ═══════════════════════════════════════════════════════════════════════════
# 1. registry 解析到的 provider 必须暴露复数入口
# ═══════════════════════════════════════════════════════════════════════════


def test_registry_resolves_entry_module_not_expansion_module() -> None:
    """先钉死前提：registry 解析出的是 entry 模块，伴生模块不在平台视野里。

    这条是其余判据的**归因前提** —— 如果平台其实读的是伴生模块，那本组修复方向就错了。
    """
    provider = PUB._provider_for(ENTRY_ID)
    assert getattr(provider, "__name__", "") == D1.__name__, (
        "registry 解析出的 provider 不是 entry 模块 —— 本组判据的归因前提不再成立，"
        "请先重新确认平台从哪个模块取 instrumentation 声明"
    )
    assert getattr(provider, "__name__", "") != EXP.__name__


def test_provider_surfaces_plural_entry() -> None:
    """provider 必须暴露复数 `instrumentation_specs` 且返回**全部** 18 组。"""
    provider = PUB._provider_for(ENTRY_ID)
    specs_fn = getattr(provider, "instrumentation_specs", None)
    assert callable(specs_fn), (
        "entry 模块缺复数入口 `instrumentation_specs` —— "
        "`stage_instrumented_substrate` 会回落到单数臂，只注 1 张 Table"
    )
    specs = tuple(specs_fn())
    expected = tuple(EXP.instrumentation_specs())
    assert len(specs) == len(expected), (
        f"复数入口返回 {len(specs)} 组，伴生模块声明 {len(expected)} 组 —— "
        "薄转发必须整体转发，不得只返回主 spec"
    )
    assert [s.table_name for s in specs] == [s.table_name for s in expected]


def test_plural_first_spec_resolves_same_anchor_as_singular() -> None:
    """复数第一组与单数入口必须解析出**同一组锚点**。

    🔴 判的是「解析后」而不是 dataclass 逐字段相等：伴生模块显式写了
    `sheet_key='d13-managed'`，entry 模块的单数 spec 留 `None` 由
    `anchors_from_instrumentation_spec` 回落成 `f"{template_id.lower()}-managed"`。
    两者**字段不等但解析后同值**，按 dataclass 相等断言会得到假红。
    """
    plural_first = tuple(D1.instrumentation_specs())[0]
    singular = D1.instrumentation_spec()
    assert anchors_from_instrumentation_spec(plural_first) == anchors_from_instrumentation_spec(
        singular
    ), "复数首组与单数入口解析出的锚点不同值 —— 主表身份在两条通路上会漂"


# ═══════════════════════════════════════════════════════════════════════════
# 2. staged 产物必须带齐每一张声明表（产物级证据）
# ═══════════════════════════════════════════════════════════════════════════


def test_staged_substrate_carries_every_declared_table(staged_tables) -> None:
    """staged substrate 里的 Table 集合 == 复数 specs 声明的 Table 集合。"""
    declared = {
        str(a["table_name"])
        for a in anchors_from_instrumentation_specs(D1.instrumentation_specs())
        if a.get("table_name")
    }
    assert declared, "声明侧算出 0 张表 —— 空分母，断言无意义"
    missing = sorted(declared - staged_tables)
    assert not missing, (
        f"staged substrate 缺 {len(missing)}/{len(declared)} 张声明表: {missing} —— "
        "这正是整册发布抛 ContractDriftError 的根因形态"
    )


def test_staged_substrate_table_count_is_eighteen(staged_tables) -> None:
    """现算数量等式：18 张受管行表全部落进产物。

    写死 18 是因为它同时被契约（`declared_structure_inventory`）与伴生模块声明，
    三方相等由 `test_contract_and_specs_agree_on_managed_surface` 钉；此处只防
    「产物侧静默少表」这一种退化（缺表时产物数会掉到 1）。
    """
    declared = {
        str(a["table_name"])
        for a in anchors_from_instrumentation_specs(D1.instrumentation_specs())
        if a.get("table_name")
    }
    assert len(declared) == 18
    assert len(staged_tables & declared) == 18


# ═══════════════════════════════════════════════════════════════════════════
# 3. 请求时刻锚点（冻结 payload）必须覆盖每一张受管 sheet —— BP-30
# ═══════════════════════════════════════════════════════════════════════════


def test_frozen_request_time_anchors_cover_every_managed_sheet() -> None:
    """`instrumentation_definition_payload` 必须走复数入口，否则两个时刻锚点不可比。

    请求时刻锚点 = `frozen_anchors_from_instrumentation(该 payload)`；
    发布时刻锚点 = `anchors_from_instrumentation_specs(provider.instrumentation_specs())`。
    BP-30 要求两者**同值**。
    """
    payload = D1.instrumentation_definition_payload()
    frozen = tuple(_frozen_sheet_anchors(payload))
    assert frozen, "冻结 payload 里取不到锚点 —— 请求时刻会 fail-closed"
    publish_time = anchors_from_instrumentation_specs(D1.instrumentation_specs())
    assert len(frozen) == len(publish_time), (
        f"请求时刻 {len(frozen)} 组锚点 vs 发布时刻 {len(publish_time)} 组 —— "
        "BP-30：两个时刻必须同源，否则 structure_hash 不可比"
    )
    assert [a["table_name"] for a in frozen] == [a["table_name"] for a in publish_time]
    assert [a["sheet_key"] for a in frozen] == [a["sheet_key"] for a in publish_time]


def test_singular_payload_would_lose_all_but_primary_sheet() -> None:
    """反向钉死缺陷形态本身：单数 payload 只带主 sheet。

    这条**不是**多余的重复 —— 它证明上一条的等式不是「两边都恒等于同一个常量」，
    而是真的会因为走单数入口而破裂（否则上一条可能在两侧同时退化时仍然全绿）。
    """
    singular_payload = build_instrumentation_payload(
        spec=D1.instrumentation_spec(),
        template_definition_sha256=D1.canonical_digest(D1.template_definition_payload()),
        template_sha256=D1.TEMPLATE_SHA256,
        gate=D1.excel_carrier_gate(),
    )
    singular_frozen = tuple(_frozen_sheet_anchors(singular_payload))
    plural_frozen = tuple(_frozen_sheet_anchors(D1.instrumentation_definition_payload()))
    assert len(singular_frozen) < len(plural_frozen), (
        "单数 payload 与复数 payload 给出同样多的锚点 —— 说明复数入口没起作用，"
        "或者伴生模块其实只声明了一张 sheet"
    )
    assert len(singular_frozen) == 1
    assert {a["table_name"] for a in singular_frozen} == {D1.TABLE_NAME}


def test_plural_payload_delegates_identically_for_single_spec() -> None:
    """框架层等价关系：单 spec 时复数入口 == 单数入口（本改造的 digest 影响只来自数量）。"""
    spec = D1.instrumentation_spec()
    kwargs = dict(
        template_definition_sha256=D1.canonical_digest(D1.template_definition_payload()),
        template_sha256=D1.TEMPLATE_SHA256,
        gate=D1.excel_carrier_gate(),
    )
    assert build_instrumentation_payload_for_sheets(specs=(spec,), **kwargs) == (
        build_instrumentation_payload(spec=spec, **kwargs)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 三方相等：契约 ↔ specs ↔ 受管面
# ═══════════════════════════════════════════════════════════════════════════


def test_contract_and_specs_agree_on_managed_surface(contract, staged_tables) -> None:
    """契约声明的受管 sheet/table 数与 specs、staged 产物三方相等。"""
    inventory = declared_structure_inventory(contract)
    assert inventory, "契约结构清册为空 —— 空分母"
    contract_sheets = {item[0] for item in inventory}
    spec_anchors = anchors_from_instrumentation_specs(D1.instrumentation_specs())
    spec_sheets = {a["sheet_key"] for a in spec_anchors}
    spec_tables = {a["table_name"] for a in spec_anchors if a.get("table_name")}

    assert contract_sheets == spec_sheets, (
        "契约 sheet_key 集合与 specs 解析出的 sheet_key 集合不等：\n"
        f"  契约独有 = {sorted(contract_sheets - spec_sheets)}\n"
        f"  specs 独有 = {sorted(spec_sheets - contract_sheets)}"
    )
    assert spec_tables <= staged_tables
    assert len(contract_sheets) == 12
    assert len(spec_tables) == 18
