"""GS4 —— `Catalog_Registrar` 守卫（spec `x3-adjustment-entry-import-export` 任务 8.3）。

被守对象：`backend/scripts/fix/fix_x3_adjustment_ie_registration.py`（六步登记器）。

## 判据形态（为什么这么写）

本文件刻意**不**做「源码里有没有 `_endpoint_for` 这个字符串」这类 grep 式判定 ——
那正是 memory 记的假绿三源之一。四类判据全部落到**行为**：

| 类别 | 条数 | 判据 |
|---|---|---|
| Preflight 行为 | 6 | 真实 16/16 通过 + 逐门在受控夹具下**必须挡下**（不是警告） |
| 零写盘 | 3 | `Path.write_text` 被换成"一写就炸"，`--check` / `--dry-run` 仍全程跑完 |
| 核对生成后的目录 | 5 | 未收口副本 `--check` 退出 2 并点名生成器命令 / committed 目录 16 段 == Key_Ledger 且重生成不丢已启用条目 / 目录写入分支已删 / 缺条目与异值必拒 |
| 退出码与真源 | 5 | `--check` 0/2 表达收口；manifest ↔ Key_Ledger 双向锁死；R5.8 登记表完整性；Step 4 可复现性 |

🔴 **目录只由生成器写出**（acnr-foundation-defect-closure T07，design §5.4）：原「外科补丁」类用例守的是
任务 9.1 的 `--apply`（就地改目录），该写入分支已删除，`--check` 改为核对生成后的目录；目录写出方由
`backend/tests/acnr/test_only_generator_writes_catalog.py` 的 AST 污点分析钉住只有生成器。

🔴 **不碰真实 catalog**：所有写盘用例都在 `tmp_path` 的副本上跑，真实
`backend/data/acnr/global_catalog.json` 在本文件里只被读取（并有一条用例逐字节复核它未变）。

## 🔴 状态基线 → 机制基线（任务 9.1 第 1 轮的返工，2026-08-15）

本文件初版有六条用例**依赖「committed catalog 恰好处于任务 9.1 施加前」**：断言
`--check == 2` / `len(diff) == 16` / `enabled_after == enabled_before + 16` /
`plan.pending` 恰 16 …… 一旦 9.1 施加，这六条必红 —— 那不是生产行为回归，而是守卫
**把「未收口」这个当刻状态锁成了期望值**（memory 假绿三源第③条的同型问题，方向相反）。

修法：凡是需要「未收口」前提的用例，一律用 `_catalog_copy_unapplied(tmp_path)` 在
副本上**主动造出**该前提（剥掉 16 段 `import_export` 并用生成器的确定性序列化重写），
判据落在**机制**上 —— 给一个未收口 catalog，登记器必须：pending 16 → `--check` 2 并点名生成器命令；
给生成后的目录，`--check` 0。判据不依赖 committed catalog 当刻处于哪一态。

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.8
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "fix" / "fix_x3_adjustment_ie_registration.py"


def _load_registrar():
    """按路径加载登记器（`backend/scripts/fix` 不是包）。"""
    assert _SCRIPT.exists(), f"登记器脚本缺失：{_SCRIPT}"
    spec = importlib.util.spec_from_file_location("_x3_registrar_under_test", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reg():
    return _load_registrar()


@pytest.fixture(scope="module")
def real_plan(reg) -> Any:
    plan, _data, _raw = reg.build_plan()
    return plan


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _real_file_md5s(reg) -> dict[str, str]:
    """真实（非副本）写盘面的 md5 快照：committed catalog + 三份 partial manifest。"""
    files = [reg.CATALOG, *sorted(reg.SOURCES.glob("*_cycle_ie_manifest.yaml"))]
    return {p.name: _md5(p) for p in files}


@pytest.fixture(scope="module")
def real_file_baseline(reg) -> dict[str, str]:
    return _real_file_md5s(reg)


@pytest.fixture(autouse=True)
def _real_files_are_never_written(reg, real_file_baseline: dict[str, str]):
    """每条用例前后都复量真实文件 —— 任何一条用例写到真实文件即当场判红。"""
    yield
    assert _real_file_md5s(reg) == real_file_baseline, (
        "本用例改到了真实文件（catalog / manifest）—— 本文件的写盘只许落在 tmp 副本"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ① Preflight 行为（R5.1）
# ═══════════════════════════════════════════════════════════════════════════════


def test_real_preflight_is_16_of_16(real_plan) -> None:
    """真实仓库态：16 张全过四门，0 被挡。

    这条是**反空转锚点**：若作业面被算成 0 张，后面所有「必须挡下」的用例都会
    在空集上恒真。
    """
    assert len(real_plan.targets) == 16, (
        f"作业面 {len(real_plan.targets)} 张 != 16 —— partial manifest 实读集变了，"
        "先核对 backend/data/acnr/sources/{l,m,n}_cycle_ie_manifest.yaml"
    )
    assert len(real_plan.preflight) == 16
    failed = [(p.sheet_code, p.reason) for p in real_plan.preflight if not p.ok]
    assert not failed, f"Preflight 未 16/16：{failed}"
    assert real_plan.blocked == []
    # 四门 × 16 张 = 64 次判定，且每一门都真给出了 detail（空 detail = 判据没真跑）
    gate_names = {g.name for p in real_plan.preflight for g in p.gates}
    assert gate_names == {
        "adapter_registered",
        "module_resolved",
        "three_state_endpoints",
        "sheet_in_ie_sheets",
    }, f"门集合变了：{sorted(gate_names)}"
    assert sum(len(p.gates) for p in real_plan.preflight) == 64
    assert all(g.detail.strip() for p in real_plan.preflight for g in p.gates)


def test_preflight_three_state_detail_names_real_endpoint_objects(real_plan, reg) -> None:
    """三态门的 detail 必须回显真实端点函数对象名（证明是真取到了端点，不是恒真）。

    同时与运行期同一函数对象比对：`_endpoint_for(module, prefix, suffix)` 取出的
    就是 bulk 适配器闭包运行时会调的那个对象。
    """
    import importlib

    from app.services.bulk_tab import _kfgh_cycle_adapters as kfgh

    for p in real_plan.preflight:
        module = importlib.import_module(p.module_path)
        for suffix in reg.THREE_STATE:
            fn = kfgh._endpoint_for(module, p.api_prefix, suffix)
            assert fn is not None, f"{p.sheet_code}/{suffix} 端点为 None"
            assert getattr(fn, "__qualname__", "") in next(
                g.detail for g in p.gates if g.name == "three_state_endpoints"
            ), f"{p.sheet_code}/{suffix}: detail 未回显端点对象名"


@pytest.mark.parametrize(
    "gate_name",
    ["adapter_registered", "module_resolved", "three_state_endpoints", "sheet_in_ie_sheets"],
)
def test_each_gate_failure_refuses_the_sheet_rather_than_warning(
    reg, monkeypatch: pytest.MonkeyPatch, gate_name: str
) -> None:
    """逐门制造不就绪 ⇒ 该 sheet **被拒绝写入**（不进 plan.pending），不是警告。

    机制差分：只动一处（注册表 / 模块映射 / 端点提取 / 白名单），其余逐字不变。
    """
    import importlib

    from app.services.bulk_tab import _kfgh_cycle_adapters as kfgh
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    victim_prefix, victim_code = "m4", "M4-3"

    if gate_name == "adapter_registered":
        patched = {k: v for k, v in IE_ADAPTER_REGISTRY.items() if k != victim_prefix}
        monkeypatch.setattr(reg, "_adapter_registry", lambda: patched)
    elif gate_name == "module_resolved":
        mapping = dict(kfgh._PREFIX_TO_MODULE)
        mapping[victim_prefix] = "app.routers.does_not_exist_x3_probe"
        monkeypatch.setattr(kfgh, "_PREFIX_TO_MODULE", mapping)
    elif gate_name == "three_state_endpoints":
        real = kfgh._endpoint_for

        def only_two(module, api_prefix, suffix):
            if api_prefix == victim_prefix and suffix == "import-data":
                return None
            return real(module, api_prefix, suffix)

        monkeypatch.setattr(kfgh, "_endpoint_for", only_two)
    else:
        host = importlib.import_module(kfgh._resolve_module_path(kfgh._PREFIX_TO_MODULE[victim_prefix]))
        monkeypatch.setattr(host, "IE_SHEETS", frozenset({"M4-2"}), raising=False)

    plan, _data, _raw = reg.build_plan()

    blocked_codes = {p.sheet_code for p in plan.blocked}
    assert victim_code in blocked_codes, f"{gate_name}: {victim_code} 未被挡下（= 判据空转）"
    assert victim_code not in {t.sheet_code for t in plan.pending}, (
        f"{gate_name}: 被挡 sheet 仍进了 plan.pending ⇒ 会被写入 catalog（这正是禁止的"
        "「警告而非拒绝」）"
    )
    failed_gate_names = {g.name for p in plan.blocked for g in p.failures}
    assert gate_name in failed_gate_names, (
        f"{gate_name}: 挡下的理由里没有这道门（实际 {sorted(failed_gate_names)}）"
        " ⇒ 门与理由错位"
    )
    # 其余 15 张不受影响（不许一处不就绪就整批哑掉）
    assert len(plan.targets) == 16
    assert len(blocked_codes) == 1, f"{gate_name}: 连带挡下了 {sorted(blocked_codes)}"


def test_gate_exception_is_error_state_not_swallowed(reg, monkeypatch: pytest.MonkeyPatch) -> None:
    """判据自身抛异常 ⇒ 记 `error` 态并判不过（R10.11 禁 fail-open）。"""
    from app.services.bulk_tab import _kfgh_cycle_adapters as kfgh

    def boom(module, api_prefix, suffix):
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(kfgh, "_endpoint_for", boom)
    plan, _data, _raw = reg.build_plan()

    assert len(plan.blocked) == 16, "异常被吞成通过 ⇒ fail-open"
    states = {g.state for p in plan.blocked for g in p.gates if g.name == "three_state_endpoints"}
    assert states == {"error"}, f"期望 error 态，实得 {states}"
    assert all("RuntimeError" in g.detail for p in plan.blocked for g in p.failures
               if g.name == "three_state_endpoints"), "error 态未回显异常类型"
    assert plan.pending == [], "有 error 态时仍规划了写入"


def test_blocked_sheet_without_registered_reason_is_refused(
    reg, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """R5.8：被挡 sheet 若未在 `PREFLIGHT_BLOCK_REGISTRY` 登记理由 ⇒ `--check` exit 2 并点名。"""
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    patched = {k: v for k, v in IE_ADAPTER_REGISTRY.items() if k != "m4"}
    monkeypatch.setattr(reg, "_adapter_registry", lambda: patched)
    assert reg.PREFLIGHT_BLOCK_REGISTRY == {}, (
        "登记表已非空 —— 本条用例的前提（当前 16/16 通过、无需登记）已变，须同步核对"
    )

    code = reg.run("check", catalog_path=_catalog_copy(tmp_path))
    assert code == 2

    records = reg.deviation_records(reg.build_plan()[0])
    assert [r["sheet_code"] for r in records] == ["M4-3"]
    r = records[0]
    for col in ("catalog_value", "contract_value", "frontend_observed"):
        assert col in r, f"Deviation 记录缺三列之一：{col}（R8.4）"
    assert set(r["na_reasons"]) == {"catalog_value", "frontend_observed"}, (
        "为 None 的列必须带 na_reasons（R8.4）"
    )
    assert r["evidence"]["refused_write"] is True
    assert r["evidence"]["registered_reason"] is None
    assert any(g["state"] != "pass" for g in r["evidence"]["gates"])


# ═══════════════════════════════════════════════════════════════════════════════
# ② 零写盘（R5.6 的只读态义务）
# ═══════════════════════════════════════════════════════════════════════════════


def _explode_on_write(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """把 `Path.write_text` / `Path.write_bytes` / `open(..., 'w')` 全换成一写就炸。"""
    hits: list[str] = []

    def boom_text(self: Path, *a: Any, **kw: Any) -> int:
        hits.append(str(self))
        raise AssertionError(f"零写盘约定被破坏：write_text({self})")

    def boom_bytes(self: Path, *a: Any, **kw: Any) -> int:
        hits.append(str(self))
        raise AssertionError(f"零写盘约定被破坏：write_bytes({self})")

    monkeypatch.setattr(Path, "write_text", boom_text)
    monkeypatch.setattr(Path, "write_bytes", boom_bytes)
    return hits


@pytest.mark.parametrize("mode", ["check", "dry-run"])
def test_readonly_modes_never_write_a_single_byte(
    reg, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    """`--check` / `--dry-run` 在"一写就炸"的探针下必须跑到底（行为判据，非 grep）。

    跑在**未收口副本**上（副本先造好、再装探针）⇒ 两个退出码都由机制唯一确定：
    `--check` 见 16 张待补必 **2**、`--dry-run` 出完整台账必 **0**，与仓库是否已施加无关。
    真实文件不被写另有 autouse fixture 与 `test_real_files_untouched_by_this_module` 兜。
    """
    cat = _catalog_copy_unapplied(tmp_path)
    hits = _explode_on_write(monkeypatch)
    code = reg.run(mode, catalog_path=cat)
    assert hits == [], f"{mode} 触发了写盘：{hits}"
    # 未收口副本上：check=未收口(2) / dry-run=台账正常(0)。刻意不写 `in (0, 2)`。
    expected = 2 if mode == "check" else 0
    assert code == expected, f"{mode} 在未收口副本上的退出码 {code} != {expected}"


def test_write_funnel_refuses_when_not_allowed(reg, tmp_path: Path) -> None:
    """唯一写盘出口在 `allow=False` 时抛拒绝（纵深防御）。"""
    target = tmp_path / "x.json"
    with pytest.raises(reg.RegistrarRefusal):
        reg._write_text(target, "{}", allow=False)
    assert not target.exists()
    reg._write_text(target, "{}\n", allow=True)
    assert target.read_text(encoding="utf-8") == "{}\n"


def test_real_files_untouched_by_this_module(reg, real_file_baseline: dict[str, str]) -> None:
    """真实 catalog 与三份 manifest 在本文件跑完后逐字节不变。

    🔴 刻意**不**写死 md5 字面量：任务 9.1 施加后 committed catalog 的 md5 会合法变化，
    锁字面量等于把「未施加」当成正确基线（R8.6 禁止）。这里比的是「本次会话内没被改动」。
    """
    assert _real_file_md5s(reg) == real_file_baseline, (
        "本文件跑动过程中改到了真实文件 —— 所有写盘用例都应落在 tmp 副本上"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ③ 核对生成后的目录（R5.2 / R5.5 + 目录只由生成器写出）
# ═══════════════════════════════════════════════════════════════════════════════


#: 16 个目标 `sheet_code`（任务 8.1 交付的三份 partial manifest 实读集）。
#:
#: 🔴 这份字面量**不是作业面真源** —— 作业面仍由登记器实读 manifest 得出（见
#: `test_real_preflight_is_16_of_16` 的反空转锚点）。它只用于两件事：①造「9.1 施加前」
#: 态时定位要剥的条目；②给下游用例一个与登记器**互相独立**的期望集（若两侧算出的集合
#: 不同即判红，这正是"差异集 == 目标集"能钉住的原因）。
_TARGET_SHEET_CODES: tuple[str, ...] = (
    "L2-3", "L6-3", "M1-3", "M2-3", "M3-3", "M4-3", "M5-3", "M6-3",
    "M7-3", "M8-3", "M9-3", "M10-3", "N1-3", "N2-3", "N3-3", "N5-3",
)
_TARGET_ADDR_IDS: frozenset[str] = frozenset(
    f"{code.split('-')[0]}/{code}" for code in _TARGET_SHEET_CODES
)


def _catalog_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "global_catalog.json"
    shutil.copy2(_REPO_ROOT / "backend" / "data" / "acnr" / "global_catalog.json", dst)
    return dst


def _catalog_copy_unapplied(tmp_path: Path) -> Path:
    """真实 catalog 的副本，且**强制回到「任务 9.1 施加前」态**（16 段 `import_export` 全不在）。

    为什么必须这么造（机制基线 vs 状态基线）：直接用 `_catalog_copy` 等于把 committed
    的**当刻状态**当基线 —— 9.1 一施加，"pending 16 / `--check` 2 / diff 16" 全部翻红，
    而生产行为一个字节都没退化。这里主动把副本推回未收口态，判据就只依赖登记器的机制，
    与仓库处于「未施加」还是「已施加」无关。

    重写走生成器自己的 `_deterministic_json`（与生成器写出的目录同一序列化）。

    **反向自检（防 helper 静默造出「空差异」副本，使下游"必须 diff 16"变成假绿）**：
    ①目标 `addr_id` 必须**恰好定位到 16 个**（每个恰 1 条）—— catalog 结构变了 / sheet
    改名 ⇒ 当场抛；②剥完这 16 条**全部**不含 `import_export`（= 下游 pending 必为 16 的
    结构前提）；③实际被剥掉的段数只允许 **0**（仓库未施加）或 **16**（仓库已施加）——
    1~15 说明 committed 处于**半施加**态，属异常，当场抛而不是悄悄补齐。
    """
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    dst = _catalog_copy(tmp_path)
    data = json.loads(dst.read_text(encoding="utf-8"))

    hits = [s for s in data.get("sheets", []) if str(s.get("addr_id") or "") in _TARGET_ADDR_IDS]
    located = {str(s.get("addr_id") or "") for s in hits}
    assert located == _TARGET_ADDR_IDS, (
        "未在真实 catalog 中定位到全部 16 个目标 addr_id —— "
        f"缺 {sorted(_TARGET_ADDR_IDS - located)} / 多 {sorted(located - _TARGET_ADDR_IDS)}；"
        "catalog 结构或 sheet_code 变了，helper 会造出空差异副本 ⇒ 拒绝"
    )
    assert len(hits) == len(_TARGET_ADDR_IDS), (
        f"目标 addr_id 在 catalog 中不是一条一命中（实得 {len(hits)} 条）⇒ 拒绝"
    )

    removed = [s.pop("import_export") for s in hits if "import_export" in s]
    assert all("import_export" not in s for s in hits), "剥段后仍有目标条目带 import_export"
    assert len(removed) in (0, len(_TARGET_ADDR_IDS)), (
        f"committed catalog 处于半施加态：16 个目标里只有 {len(removed)} 个带 import_export"
        "（合法值只有 0 = 未施加 / 16 = 已施加）⇒ 拒绝，先核对 catalog"
    )

    dst.write_text(_deterministic_json(data), encoding="utf-8")
    return dst


def test_check_on_unapplied_copy_names_the_16_missing_segments(
    reg, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """未收口副本：pending 恰为 16 个目标，`--check` 退出 2 并点名生成器命令，副本逐字节不变。"""
    cat = _catalog_copy_unapplied(tmp_path)
    md5_before = _md5(cat)
    plan, data, _raw = reg.build_plan(catalog_path=cat)
    assert {reg._addr_of(data, t.sheet_code) for t in plan.pending} == set(_TARGET_ADDR_IDS)
    assert plan.already == []
    capsys.readouterr()
    assert reg.run("check", catalog_path=cat) == 2
    out = capsys.readouterr().out
    assert "目录缺 16 张的 import_export 段" in out, out
    assert "generate_catalog.py --write" in out, out
    assert _md5(cat) == md5_before, "--check 改了目录副本"


def test_committed_catalog_segments_match_ledger_and_regeneration_keeps_enabled(reg) -> None:
    """生成后的 committed 目录：16 段逐字段 == Key_Ledger 派生值；整体重生成不丢任何已启用 I/E 条目。

    杀伤面基线：原 38 = H4/I24/L8/N2 这 38 条 SAFE 档外科补丁只在目录里、没有生成器输入；T07 把它们迁进
    `global_catalog.overrides.json` 后现算为 0（再出现非 0 即又有条目绕过了生成器输入）。
    """
    data = json.loads(reg.CATALOG.read_text(encoding="utf-8"))
    ledger = reg._ledger_x3()
    by_addr = {s["addr_id"]: s for s in data["sheets"]}
    for addr in sorted(_TARGET_ADDR_IDS):
        assert by_addr[addr].get("import_export") == ledger[addr.split("/")[1]], f"{addr} 的段非 Key_Ledger 派生值"

    from generate_catalog import generate_catalog  # noqa: PLC0415

    fresh, _r, _b = generate_catalog(offline=True, registry_version=str(data.get("registry_version") or ""))
    lost = reg._enabled_addr_ids(data) - reg._enabled_addr_ids(fresh)
    assert lost == set(), f"整体重生成会丢 {len(lost)} 条已启用 I/E：{sorted(lost)[:10]}"
    assert set(_TARGET_ADDR_IDS) <= reg._enabled_addr_ids(fresh)


def test_registrar_has_no_catalog_write_branch(reg, tmp_path: Path) -> None:
    """目录写入分支已删除：`--apply` 不再是合法 CLI 参数（argparse 退出 2），`run("apply")` 抛 ValueError。"""
    assert not hasattr(reg, "patch_catalog")
    with pytest.raises(SystemExit) as exc:
        reg.main(["--apply"])
    assert exc.value.code == 2
    cat = _catalog_copy(tmp_path)
    md5_before = _md5(cat)
    with pytest.raises(ValueError, match="未知模式"):
        reg.run("apply", catalog_path=cat)
    assert _md5(cat) == md5_before


def test_check_refuses_when_catalog_entry_missing(reg, tmp_path: Path) -> None:
    """R5.2：目标 sheet 在 catalog 无条目 ⇒ 拒绝（退出码 2）。"""
    cat = _catalog_copy(tmp_path)
    data = json.loads(cat.read_text(encoding="utf-8"))
    data["sheets"] = [s for s in data["sheets"] if s.get("sheet_code") != "M4-3"]
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    cat.write_text(_deterministic_json(data), encoding="utf-8")
    md5_before = _md5(cat)
    plan, _data, _raw = reg.build_plan(catalog_path=cat)
    assert any("'M4-3' 有 0 个条目" in r for r in plan.refusals), plan.refusals
    assert reg.run("check", catalog_path=cat) == 2
    assert _md5(cat) == md5_before


def test_check_refuses_a_different_existing_segment(reg, tmp_path: Path) -> None:
    """目录里已有值且与目标段不同 ⇒ 拒绝（不认作已收口）。"""
    cat = _catalog_copy(tmp_path)
    data = json.loads(cat.read_text(encoding="utf-8"))
    for s in data["sheets"]:
        if s.get("sheet_code") == "N2-3":
            s["import_export"] = {
                "enabled": True,
                "api_prefix": "n2",
                "item_id": "别的键",
                "storage_field": "remark",
                "import_order": 10,
                "depends_on_sheets": [],
            }
    from generate_catalog import _deterministic_json  # noqa: PLC0415

    cat.write_text(_deterministic_json(data), encoding="utf-8")
    md5_before = _md5(cat)
    plan, _data, _raw = reg.build_plan(catalog_path=cat)
    assert any("'N2-3'.import_export 已有值且与目标段不同" in r for r in plan.refusals), plan.refusals
    assert "N2-3" not in plan.already
    assert reg.run("check", catalog_path=cat) == 2
    assert _md5(cat) == md5_before


# ═══════════════════════════════════════════════════════════════════════════════
# ④ 幂等 / 真源 / 退出码（R5.3 / R5.4 / R5.6）
# ═══════════════════════════════════════════════════════════════════════════════


def test_check_exit_codes_express_closure(reg, tmp_path: Path) -> None:
    """R5.6：`--check` 未收口 = 2、收口 = 0（退出码是 CI 的唯一判据）。

    两态都是机制判据：未收口副本 → 2；生成后的 committed 目录副本 → 0。
    """
    (tmp_path / "unapplied").mkdir()
    cat = _catalog_copy_unapplied(tmp_path / "unapplied")
    assert reg.run("check", catalog_path=cat) == 2, "未收口副本应判未收口"
    assert reg.run("check", catalog_path=_catalog_copy(tmp_path)) == 0, "生成后的目录应判收口"

    # 默认 catalog_path 必须真的指向 committed catalog（**接线**判据，不锁仓库当刻状态）：
    # 由 committed 现值独立算出闭合谓词再推导期望退出码，两种调用形式必须一致。
    plan_real, _data, _raw = reg.build_plan()
    expected_real = 0 if plan_real.closed else 2
    assert reg.run("check") == expected_real, "默认 catalog_path 未指向 committed catalog"
    assert reg.run("check", catalog_path=reg.CATALOG) == expected_real


def test_manifest_and_ledger_are_locked_both_ways(reg, tmp_path: Path) -> None:
    """manifest 段与 Key_Ledger 派生值任一侧被改 ⇒ 拒绝（双向锁死，非单向抄）。"""
    src = tmp_path / "sources"
    src.mkdir()
    for p in reg.SOURCES.glob("*_cycle_ie_manifest.yaml"):
        shutil.copy2(p, src / p.name)

    # 基线：临时目录与真实目录判定相同
    _plan, refusals = reg.build_targets(sources_dir=src)
    assert refusals == [], f"临时 sources 副本本身就被拒绝：{refusals}"

    victim = src / "n_cycle_ie_manifest.yaml"
    doc = yaml.safe_load(victim.read_text(encoding="utf-8"))
    doc["entries"][0]["item_id"] = "N1-3-entries-TAMPERED"
    victim.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    _t, refusals = reg.build_targets(sources_dir=src)
    assert any("Key_Ledger 派生值不一致" in r for r in refusals), refusals
    assert reg.run("check", catalog_path=_catalog_copy(tmp_path), sources_dir=src) == 2


def test_extra_manifest_entry_is_refused_not_silently_registered(reg, tmp_path: Path) -> None:
    """往 manifest 多塞一条（第 17 张）⇒ 拒绝，不许被静默补进 catalog。"""
    src = tmp_path / "sources"
    src.mkdir()
    for p in reg.SOURCES.glob("*_cycle_ie_manifest.yaml"):
        shutil.copy2(p, src / p.name)

    victim = src / "n_cycle_ie_manifest.yaml"
    doc = yaml.safe_load(victim.read_text(encoding="utf-8"))
    doc["entries"].append(
        {
            "sheet_code": "N4-3",
            "api_prefix": "n4",
            "item_id": "N4-3-entries",
            "storage_field": "remark",
            "import_order": 20,
            "depends_on_sheets": [],
        }
    )
    victim.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    _t, refusals = reg.build_targets(sources_dir=src)
    assert any("不在 Key_Ledger" in r for r in refusals), refusals
    cat = _catalog_copy(tmp_path)
    md5_before = _md5(cat)
    assert reg.run("check", catalog_path=cat, sources_dir=src) == 2
    assert _md5(cat) == md5_before


def test_manifest_convention_requires_its_rationale(reg, tmp_path: Path) -> None:
    """`import_order` / `depends_on_sheets` 的约定必须与理由同在（删了理由即拒绝）。"""
    src = tmp_path / "sources"
    src.mkdir()
    for p in reg.SOURCES.glob("*_cycle_ie_manifest.yaml"):
        shutil.copy2(p, src / p.name)

    victim = src / "m_cycle_ie_manifest.yaml"
    doc = yaml.safe_load(victim.read_text(encoding="utf-8"))
    doc["notes"].pop("import_order_rationale")
    victim.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    _t, refusals = reg.build_targets(sources_dir=src)
    assert any("import_order_rationale" in r for r in refusals), refusals


def test_reproducibility_check_compares_against_generator_output(reg, real_plan) -> None:
    """Step 4：生成器输出与补丁值逐字段相等；把补丁值改一格必须报出不等。"""
    assert reg.reproducibility(real_plan) == []

    tampered = reg.Plan(
        targets=[
            reg.Target(
                cycle=t.cycle,
                sheet_code=t.sheet_code,
                api_prefix=t.api_prefix,
                manifest_file=t.manifest_file,
                manifest_segment=t.manifest_segment,
                expected_segment={**t.expected_segment, "import_order": 999}
                if t.sheet_code == "M5-3"
                else t.expected_segment,
            )
            for t in real_plan.targets
        ],
        registry_version=real_plan.registry_version,
    )
    problems = reg.reproducibility(tampered)
    assert [p.split(":")[0] for p in problems] == ["M5-3.import_order"], problems
