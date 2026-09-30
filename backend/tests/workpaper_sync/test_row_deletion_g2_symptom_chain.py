"""G2 症状链的**沿链**复现：兄弟 ref → 尾行 UUID → mint → extra（Requirement 11）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 21.1
Requirements: 11.1 ~ 11.5

═══ 这条链是什么 ═══

上游 G2 的实测症状（写在 `excel_materialize` 6.8b 那段注释里）：

    只补了自己的 Table ref 收缩（未补兄弟 ref）
      → other 区出现 uuid 空行
      → 反读时 `_scan_row_identities` 按 tombstone 策略给它**重新 mint** 一个身份
      → 新身份不在 intended
      → 又一轮 `extra`（`roundtrip_projection_mismatch` 500）

🔴 **为什么必须沿链断言而不是只断最后一环**：四个环各自都有判据（A1 有自己的 Property 7、
mint 有 Property 8、extra 有 Property 65），但**各环判据各自绿而链条仍通**是可能的 ——
每条判据都在自己的输入上成立，却没人验证「上一环的产物就是下一环的输入」。
本文件用**同一份产物**把四环串起来跑。

═══ 靶子：D4-1 真实双区（不是合成固件）═══

requirements 11.1 的原文是「合成的同 sheet 双区工作簿」。这里用的是**真实权威模板**
`D/D4 收入底稿.xlsx` 的 D4-1 sheet（main `GT_D41_MAIN_ROWS` 8..11 uuid=W /
other `GT_D41_OTHER_ROWS` 14..17 uuid=X）—— 它比合成固件更强：
* 就是 G2 症状原本发生的那张表（6.8b 注释点名「D4-1 是 main / other 双区，删 main 区
  一行就动 other 区」）；
* 契约 / instrumentation / 行身份全套都是生产路径产出的，不是我拼的；
* 仍然**不依赖 live 数据、不造假业务数据**（instrumentation 从权威模板现场生成）。
合成固件的价值在于「造一个平台上没有的形态」，而这个形态平台上真实存在 ⇒ 用真的。
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync.adapters.base import SubstrateRole  # noqa: E402
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState  # noqa: E402

import test_sibling_table_ref_row_shift as SIB  # noqa: E402

A = SIB.A

#: main 区里被改成**非骨架**身份的那一行（区 8..11，取中间行避开区首/区末边界）。
STALE_ROW = 10
STALE_IDENTITY = "GTROW-MINTED-G2CHAIN0001"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 固件
# ═══════════════════════════════════════════════════════════════════════════


def _entries(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def _table_ref(entries: dict[str, bytes], *, table_name: str) -> str:
    part = M._managed_table_part(entries, table_name=table_name)
    assert part, f"定位不到 Table part：{table_name}"
    import re

    match = re.search(r'\bref="([A-Z]+\d+:[A-Z]+\d+)"', entries[part].decode("utf-8"))
    assert match, f"{part} 里没有 ref="
    return match.group(1)


def _uuid_at(entries: dict[str, bytes], *, sheet_part: str, coord: str) -> str:
    """读某个坐标上的字面值（inlineStr / sharedString / 裸 `<v>` 三种形态都要取到）。

    🔴 `_CellView` 现读字段是 `coord/raw/attrs/body/formula_text/shared_ref/formula_attrs`
    —— **没有** `value` / `cell_type`（首版按名字猜了这两个，当场 AttributeError）。
    值要从 `body` 里自己取，类型从 `attrs` 里取。
    """
    import re

    xml = entries[sheet_part].decode("utf-8")
    view = M._cell_view(xml, coord)
    if view is None:
        return ""
    body = view.body or ""
    inline = re.search(r"<is>.*?<t[^>]*>(.*?)</t>.*?</is>", body, re.S)
    if inline:
        return inline.group(1)
    raw = re.search(r"<v>(.*?)</v>", body, re.S)
    if raw is None:
        return ""
    text = raw.group(1)
    if re.search(r'\bt="s"', view.attrs or "") and text.isdigit():
        shared = M._shared_strings(entries)
        return str(shared[int(text)]) if int(text) < len(shared) else ""
    return text


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return build_d41_world(tmp_path_factory.mktemp("g2-chain"))


def build_d41_world(workdir: Path) -> dict[str, Any]:
    """D4-1 双区世界：权威模板 → instrumentation → main 区一行换成非骨架身份 → extract。

    🔴 做成**普通函数**（fixture 只是薄壳）：Task 23.2 的验收判据在另一个测试模块里要用
    同一个世界，而 module 级 fixture 跨文件拿不到。本 spec 已为同一原因抽过一次。
    """
    from test_task37_excel_extract import patch_cells

    provider = SIB._provider_of_sheet(A.MANAGED_SHEET_D41)
    base_bytes = SIB._instrumented_bytes_for_provider(provider)
    with zipfile.ZipFile(io.BytesIO(base_bytes)) as zf:
        sheet_part = X._sheet_parts(zf).get(A.MANAGED_SHEET_D41)
    assert sheet_part, A.MANAGED_SHEET_D41
    substrate_bytes = patch_cells(
        base_bytes, sheet_part, {f"{A.UUID_COL_MAIN}{STALE_ROW}": STALE_IDENTITY}
    )

    base = workdir / "base.xlsx"
    base.write_bytes(substrate_bytes)

    from app.services.workpaper_sync import phase5_d1_notes_receivable  # noqa: F401

    contract = _contract(delete=False)
    entries = _entries(substrate_bytes)
    with zipfile.ZipFile(base) as zf:
        runtime_binding = X.read_runtime_binding_pairs(zf)
    return {
        "workdir": workdir,
        "base": base,
        "bytes": substrate_bytes,
        "entries": entries,
        "sheet_part": sheet_part,
        "contract": contract,
        "runtime_binding": runtime_binding,
        "outcome_main": _extract(base, contract, SIB.BINDING_MAIN, substrate_bytes),
        "outcome_other": _extract(base, contract, SIB.BINDING_OTHER, substrate_bytes),
    }


def _contract(*, delete: bool) -> Any:
    """D4-1 契约；`delete=True` 时把 **main** 区那张表的 `row_convergence` 打开。"""
    provider_module = SIB._provider_of_sheet(A.MANAGED_SHEET_D41)
    import importlib

    module = importlib.import_module(
        f"app.services.workpaper_sync.{provider_module}"
    )
    payload = module.build_contract_payload()
    touched = 0
    for sheet in payload.get("sheets") or []:
        for table in sheet.get("tables") or []:
            if table.get("table_key") == A.ROWS_TABLE_KEY_MAIN:
                if delete:
                    table["row_convergence"] = "delete"
                else:
                    table.pop("row_convergence", None)
                touched += 1
    assert touched == 1, f"按 table_key={A.ROWS_TABLE_KEY_MAIN!r} 命中 {touched} 张表"
    return C.parse_contract(payload, adapter_id=module.ADAPTER_ID)


def _extract(path: Path, contract: Any, binding: Any, data: bytes) -> Any:
    inventory = identity_inventory(
        data, expected_table=binding.table_name, uuid_column_letter=binding.uuid_column
    )
    from test_task37_excel_extract import make_definitions

    return X.extract_projection(
        artifact=path,
        definitions=make_definitions(contract, inventory),
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )


def _delete_product(world: dict[str, Any]) -> tuple[bytes, Any]:
    """打开 main 区的 `row_convergence=delete`，把那一行 stale 掉并落出产物。"""
    import dataclasses

    contract = _contract(delete=True)
    outcome = world["outcome_main"]
    projection = outcome.projection
    row_keys = dict(projection.row_keys)
    table_key = next(
        (k for k, rows in row_keys.items() if STALE_IDENTITY in rows), None
    )
    assert table_key is not None, (
        f"projection 里找不到非骨架身份 {STALE_IDENTITY}，实测 "
        f"{ {k: list(v)[:3] for k, v in row_keys.items()} }"
    )
    row_keys[table_key] = tuple(r for r in row_keys[table_key] if r != STALE_IDENTITY)
    values = {
        key: value
        for key, value in dict(getattr(projection, "values", {}) or {}).items()
        if f"/{STALE_IDENTITY}/" not in str(key)
    }
    projection = dataclasses.replace(projection, row_keys=row_keys)
    if hasattr(projection, "values"):
        projection = dataclasses.replace(projection, values=values)

    plan = M.plan_managed_writes(
        projection=projection,
        contract=contract,
        binding=SIB.BINDING_MAIN,
        region=outcome.region,
        scan=outcome.scan,
        substrate_entries=world["entries"],
        substrate_formulas=outcome.formula_inventory,
        runtime_binding=world["runtime_binding"],
    )
    product, _report = M.apply_plan_zip_with_report(world["bytes"], plan)
    return product, plan


# ═══════════════════════════════════════════════════════════════════════════
# 2. 前提非退化
# ═══════════════════════════════════════════════════════════════════════════


def test_fixture_is_a_real_dual_region_sheet(world: dict[str, Any]) -> None:
    """🔴 四条前提：两个区在同一 sheet、other 在 main **下方**、区间与 uuid 列如现算。"""
    entries = world["entries"]
    main_ref = _table_ref(entries, table_name=A.TABLE_NAME_MAIN)
    other_ref = _table_ref(entries, table_name=A.TABLE_NAME_OTHER)
    main_head = int("".join(c for c in main_ref.split(":")[0] if c.isdigit()))
    other_head = int("".join(c for c in other_ref.split(":")[0] if c.isdigit()))
    assert other_head > main_head, (
        f"other 区不在 main 区下方（main {main_ref} / other {other_ref}）⇒ "
        "删 main 区的行不会动 other 区，整条症状链不成立"
    )
    assert M._managed_table_part(entries, table_name=A.TABLE_NAME_MAIN) != (
        M._managed_table_part(entries, table_name=A.TABLE_NAME_OTHER)
    ), "两个区指向同一个 Table part ⇒ 不是双区"
    # 两个区都真的有行身份（否则 mint 那一环无从发生）
    assert world["outcome_main"].projection.row_keys, "main 区没有行身份"
    assert world["outcome_other"].projection.row_keys, "other 区没有行身份"
    assert not world["outcome_other"].scan.minted_by_row, (
        f"substrate 上 other 区就已经有 mint：{world['outcome_other'].scan.minted_by_row}"
        " ⇒ 第三环的判据在起点就不干净"
    )


def test_deletion_really_happens(world: dict[str, Any]) -> None:
    """🔴 非空转前提：契约打开后真的产出删行计划（否则四环全在「什么都没发生」上绿）。"""
    _product, plan = _delete_product(world)
    assert plan.stale_deleted == (STALE_ROW,), (
        f"被删行实得 {plan.stale_deleted}，应为 ({STALE_ROW},)"
    )
    assert plan.row_deletion is not None and plan.deletion_change is not None


# ═══════════════════════════════════════════════════════════════════════════
# 3. 四环：修复后全绿
# ═══════════════════════════════════════════════════════════════════════════


def _four_links(world: dict[str, Any]) -> dict[str, Any]:
    """跑一次删行并沿链取四个环的观测值 —— 四环共用**同一份产物**。"""
    product, plan = _delete_product(world)
    out = _entries(product)
    after = world["workdir"] / f"after-{len(list(world['workdir'].iterdir()))}.xlsx"
    after.write_bytes(product)

    before_other = _table_ref(world["entries"], table_name=A.TABLE_NAME_OTHER)
    after_other = _table_ref(out, table_name=A.TABLE_NAME_OTHER)
    tail_row = int("".join(c for c in after_other.split(":")[1] if c.isdigit()))
    tail_uuid = _uuid_at(
        out, sheet_part=world["sheet_part"], coord=f"{A.UUID_COL_OTHER}{tail_row}"
    )

    contract = _contract(delete=True)
    # 🔴 反读 other 区可能**抛在更早的门上**（identity 保留门），那本身就是环③④ 的红。
    #    这里把异常也当成一种观测值收下，而不是让它把整条链的取样打断 ——
    #    否则「修复前」态的判据会红在一个与症状链无关的 traceback 上。
    minted: dict[int, str] | None = None
    extracted_other: Any | None = None
    extract_error: Exception | None = None
    try:
        outcome_other_after = _extract(after, contract, SIB.BINDING_OTHER, product)
    except Exception as exc:  # noqa: BLE001 - 沿链取样要看**全部**失败形态
        extract_error = exc
    else:
        minted = dict(outcome_other_after.scan.minted_by_row)
        extracted_other = outcome_other_after.projection
    return {
        "plan": plan,
        "before_other_ref": before_other,
        "after_other_ref": after_other,
        "tail_row": tail_row,
        "tail_uuid": tail_uuid,
        "minted": minted,
        "extracted_other": extracted_other,
        "extract_error": extract_error,
        "contract": contract,
    }


def _production_extra(
    *, intended: Any, extracted: Any, contract: Any
) -> list[str]:
    """用**生产**的 `extra` 口径算（禁自造裸差集，Requirement 11.4）。

    受管字段过滤（`word_only` / `PROTECTED_MODES` 的模板展开）、骨架行豁免（合取两条件）
    全部走生产那一份，测试侧不复刻任何一行。

    🔴 此前这里 unbound 调 `ContentMutationService._assert_roundtrip_equivalent` 并传
    `self=None`，依赖「函数体一个 `self` 都没用到」这个前提 —— 复盘时该前提只由一个
    **脚本**里的自检守着（`measure_d4_materialize_baseline._replica_fidelity`），
    测试侧无保护。哪天有人在那函数里加一行 `self.xxx`，本判据就崩在
    `AttributeError: 'NoneType' ...` 上，traceback 与被测的 G2 症状链毫无关系。
    现在实现已搬成模块级纯函数，直接调它，前提消失。
    """
    try:
        CM.assert_roundtrip_equivalent(
            intended=intended,
            extracted=extracted,
            contract=contract,
        )
    except CM.RoundtripEquivalenceError as exc:
        return [str(exc)]
    return []


class TestG2ChainIsBrokenAfterTheFix:
    """**Validates: Requirements 11.1, 11.2, 11.4**"""

    def test_link1_sibling_ref_shrinks_by_one(self, world: dict[str, Any]) -> None:
        """环①：兄弟 Table `ref` 整体上移 1 行。"""
        links = _four_links(world)
        before, after = links["before_other_ref"], links["after_other_ref"]

        def rows(ref: str) -> tuple[int, int]:
            a, b = ref.split(":")
            return (
                int("".join(c for c in a if c.isdigit())),
                int("".join(c for c in b if c.isdigit())),
            )

        bh, bt = rows(before)
        ah, at = rows(after)
        assert (ah, at) == (bh - 1, bt - 1), (
            f"兄弟 ref 应整体上移 1：{before} → 实得 {after}"
        )

    def test_link2_tail_row_uuid_is_not_empty(self, world: dict[str, Any]) -> None:
        """环②：收缩后 other 区**尾行**的 UUID 非空。

        这是整条链的关键一环：ref 没缩时 ref 仍覆盖到旧尾行，而内容已整体上移一行
        ⇒ 旧尾行落在 ref 内且 UUID 列为空。
        """
        links = _four_links(world)
        assert links["tail_uuid"], (
            f"other 区尾行 {links['tail_uuid']!r}（第 {links['tail_row']} 行，列 "
            f"{A.UUID_COL_OTHER}）UUID 为空 ⇒ 下一次反读会给它 mint 一个新身份"
        )
        assert links["tail_uuid"].startswith("GTROW-"), links["tail_uuid"]

    def test_link3_no_new_identity_is_minted(self, world: dict[str, Any]) -> None:
        """环③：反读 other 区时**不**产出新 mint（且反读本身不抛）。"""
        links = _four_links(world)
        assert links["extract_error"] is None, (
            f"反读 other 区抛了 {type(links['extract_error']).__name__}："
            f"{links['extract_error']}"
        )
        assert links["minted"] == {}, (
            f"other 区被重新 mint 了身份 {links['minted']} —— "
            "那些身份不在 intended 里，下一环必然变成 extra"
        )

    def test_link4_production_extra_is_empty(self, world: dict[str, Any]) -> None:
        """环④：用**生产口径**算 other 区的 `extra` —— 必须为空。

        `intended` 取 substrate 上 other 区的 projection：main 区删行**不该**改变
        other 区的任何业务内容，只改它的行号。
        """
        links = _four_links(world)
        assert links["extracted_other"] is not None, (
            f"反读没拿到 projection（抛了 {links['extract_error']}）⇒ 环④ 无从计算"
        )
        problems = _production_extra(
            intended=world["outcome_other"].projection,
            extracted=links["extracted_other"],
            contract=links["contract"],
        )
        assert not problems, (
            "other 区反读与 substrate 不等值（生产口径）：\n  " + "\n  ".join(problems)
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 「修复前」态：兄弟收缩被短路 ⇒ 四环**全红**
# ═══════════════════════════════════════════════════════════════════════════


class TestG2ChainIsFullyRedWhenSiblingShrinkIsShortCircuited:
    """**Validates: Requirements 11.3, 11.5**

    🔴 用**进程内** `monkeypatch` 制造「修复前」态，不改磁盘上的生产文件
    （归档 README 教训 6：变异 harness 自身会假绿 —— 改盘上文件的 harness 一旦忘了还原，
    后续所有用例都在被改过的代码上跑）。

    🔴 四环必须**全红**。只有一环红说明链条在别处就断了，那样这份沿链判据证明不了
    「是这一环把链条串起来的」。
    """

    @staticmethod
    def _short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        # 🔴 返回值形态必须与生产一致：现读签名是
        #    `(entries, *, plan, own_part) -> tuple[dict[str, bytes], int]`。
        #    首版返 `0`，调用方 `entries, _n = ...` 当场 `TypeError: cannot unpack` ——
        #    那样「四环全红」红在 TypeError 上，测的就不是症状链了。
        def _noop(
            entries: dict[str, bytes], *, plan: Any, own_part: str
        ) -> tuple[dict[str, bytes], int]:
            calls.append(1)
            return entries, 0

        monkeypatch.setattr(M, "_shrink_sibling_table_refs", _noop)
        # 🔴 断言短路真的生效：被 patch 的函数在本次 apply 里必须被调到，
        #    否则「四环全红」可能是别的原因造成的。
        return calls  # type: ignore[return-value]

    def test_all_four_links_go_red(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._short_circuit(monkeypatch)
        links = _four_links(world)
        assert calls, "短路函数一次都没被调到 ⇒ 变异没生效，本条判据空转"

        failures: list[str] = []

        # 环①：兄弟 ref 没缩
        if links["after_other_ref"] != links["before_other_ref"]:
            failures.append(
                f"环① 竟然缩了：{links['before_other_ref']} → {links['after_other_ref']}"
            )
        # 环②：尾行 UUID 为空
        if links["tail_uuid"]:
            failures.append(f"环② 尾行 UUID 仍非空：{links['tail_uuid']!r}")
        # 环③④：🔴 **如实记录实测形态** —— 今天它们被一个**更早**的门抢先打红：
        #   `assert_identity_inventory_retained` 抛 `IdentityRetentionError`
        #   （「OO 往返后丢失 1 个 row identity 'GTROW-D41OTHER-0014'」）。
        #
        # G2 原叙事的尾巴是「mint 新身份 → extra → roundtrip_projection_mismatch 500」，
        # 那是**当时**的症状；此后平台加了 identity 保留门（Property 23/66），它在
        # mint 之前就拦住了「身份清册少了一个」。所以今天这条链的红是保留门给的。
        #
        # ⚠ 不把它写成「环③④ 也红了」就完事：那会让人以为 mint/extra 那两条判据在
        # 「修复前」态被执行过。实际是**没执行到**，因为反读根本没返回。这个区别必须留在案上。
        error = links["extract_error"]
        if error is None:
            failures.append(
                f"环③④ 反读竟然成功了（mint={links['minted']}）—— 预期被 identity "
                "保留门拦住；若平台真的改成允许这种反读，请重判这两环的形态"
            )
        elif not isinstance(error, X.IdentityRetentionError):
            failures.append(
                f"环③④ 抛的是 {type(error).__name__} 而不是 IdentityRetentionError：{error}"
            )
        elif "row identity" not in str(error):
            failures.append(f"环③④ 的错误文案不像身份丢失：{error}")

        assert not failures, (
            "兄弟收缩被短路后，这些环**没有**打红 ⇒ 链条在别处就断了，"
            "本沿链判据证明不了「是兄弟收缩把链条串起来的」：\n  "
            + "\n  ".join(failures)
            + f"\n（实测：ref {links['before_other_ref']} → {links['after_other_ref']}，"
            f"尾行 {links['tail_row']} UUID={links['tail_uuid']!r}，"
            f"mint={links['minted']}，extract_error={links['extract_error']}）"
        )

    def test_the_retention_gate_preempts_the_mint_tail(
        self, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 把「G2 尾巴今天被抢先」这件事单独立成判据（可伪证）。

        断言两件事：
        ① 「修复前」态下反读**抛** `IdentityRetentionError`，点名丢失的那个身份；
        ② 因此 `scan.minted_by_row` 在该态下**取不到值**（不是取到空值）——
           环③④ 的原始形态（mint → extra）在今天的平台上不可达。

        哪天保留门被改动（或该形态变成可反读），本条当场打红，逼迫重新判断 G2 的尾巴
        到底停在哪里，而不是让一段过时的叙事继续留在测试注释里。
        """
        self._short_circuit(monkeypatch)
        links = _four_links(world)
        error = links["extract_error"]
        assert isinstance(error, X.IdentityRetentionError), (
            f"预期被 identity 保留门拦住，实得 {type(error).__name__ if error else None}"
        )
        assert "GTROW-D41OTHER-" in str(error), (
            f"丢失的身份不是 other 区的：{error}"
        )
        assert links["minted"] is None and links["extracted_other"] is None, (
            "反读抛异常却拿到了 mint/projection ⇒ 取样逻辑自相矛盾"
        )

    def test_the_short_circuit_target_is_the_real_production_function(self) -> None:
        """🔴 变异靶心必须是**生产**调用的那个函数（patch 错对象 = 变异不生效而全绿）。"""
        import ast
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(M._shrink_managed_table_ref))
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        assert "_shrink_sibling_table_refs" in called, (
            f"`_shrink_managed_table_ref` 不再调兄弟收缩了：{sorted(c for c in called if c)}"
        )
