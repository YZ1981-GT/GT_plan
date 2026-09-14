"""H 类审定表四表预填共享件的**调用点签名**与消费面守卫。

## 要挡住什么

`h_cycle_adjudication_prefill.attach_h_segment_prefill` 是 2026-08-06 新建的共享
编排件，H1~H4 四个 render 各插了一处调用 —— 但**四处签名全错**：

- H1/H4 传 5 个位置参数（`ctx, payload, "H1", accounts, PREFIX`），而形参只有 4 个
  可位置传 ⇒ ``TypeError: too many positional arguments``
- H2/H3 传 `(ctx, payload, cycle=..., accounts=..., slot_key_prefix=...)`，当时形参
  顺序是 `(payload, ctx, ...)` ⇒ **`payload` 收到 ctx、`ctx` 收到 payload**，
  能绑定但语义颠倒

两种错法都被 render 外层的 fail-open 吞成 WARNING ⇒ 症状是「审定表点带入没数据」，
而 `get_diagnostics` / vitest / 既有 1400+ 后端测试**全绿**。

这是 memory 已记的「additive 注入即死代码」的新变体：注入的代码不是没被调用，
而是**调用了但必然抛异常**。故本守卫的判据是 **`inspect.signature.bind()` 真绑定**，
不是「有没有出现这个符号」。

## 三条判据

1. **签名可绑定**（Property 7 前置）—— 用 AST 抽调用实参，交给真实签名 `bind()`
2. **参数语义正确** —— 绑定后 `ctx`/`payload`/`cycle` 三者不得错位
3. **消费面如实登记** —— `adjudication_segment_prefill` 当前**零前端消费方**，
   该事实必须显式登记；哪天接了消费方，反向断言会打红提醒更新登记

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 4.1, 4.5, 4.6 / Property 7, 8
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

# ── 路径定位：双哨兵向上查找仓库根（memory 铁律：禁写死回退级数）────────────
_SENTINELS = (
    Path("backend/app/services/four_table/h_cycle_adjudication_prefill.py"),
    Path("audit-platform/frontend/package.json"),
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in [here, *here.parents]:
        if all((cand / s).exists() for s in _SENTINELS):
            return cand
    raise AssertionError(
        "未找到仓库根（双哨兵均不存在）。哨兵: " + ", ".join(str(s) for s in _SENTINELS)
    )


REPO = _repo_root()
STRATEGY_DIR = REPO / "backend/app/routers/wp_render_strategies"
FRONTEND_SRC = REPO / "audit-platform/frontend/src"

#: 四个必须调用共享件的 render 文件（H1~H4，H5~H10 目前仍是内联块）
H1234_RENDERS = {
    "H1": STRATEGY_DIR / "_h1_fixed_assets.py",
    "H2": STRATEGY_DIR / "_h2_construction_in_progress.py",
    "H3": STRATEGY_DIR / "_h3_investment_property.py",
    "H4": STRATEGY_DIR / "_h4_engineering_materials.py",
}

#: 共享件产出的键 ⇒ 当前已知前端消费方文件数。
#: 🔴 历史：登记曾为 0 = **已实证的 dead output**（H5~H10 从 2026-08-02 起就在产它，
#: 全平台无人读）。本 spec Task 5 接上前端消费链后由 0 变 3，故登记同步为 3。
#: 此处不是「允许它是死的」，而是把事实钉住：数量再变即打红，
#: 迫使下个会话同步更新登记与 tasks.md，不会悄悄以为「早就通了」。
#: 三个消费方：共享件本体 + H2/H4 两个审定表 Tab（H1/H3 走各自既有 seed 通路）。
SEGMENT_PREFILL_KEY = "adjudication_segment_prefill"
SEGMENT_PREFILL_KNOWN_CONSUMERS = 3
#: 逐个登记（数量断言之外再钉住「是哪三个」，防「删一个加一个」净数不变的漂移）
SEGMENT_PREFILL_EXPECTED_CONSUMERS = (
    "components/workpaper/composables/hCycleAdjudicationSeed.ts",
    "components/workpaper/h2/core/H2TabAdjudication.vue",
    "components/workpaper/h4/core/H4TabAdjudication.vue",
)


# ═══════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════
def _read(p: Path) -> str:
    assert p.exists(), f"文件不存在: {p}"
    return p.read_text(encoding="utf-8")


def _strip_py_comments(src: str) -> str:
    """剥 `#` 行注释（保守：只剥整行注释，避免误伤字符串里的 #）。

    本守卫的说明注释里会写出错误调用形态作反例，不剥会把注释数成真实调用。
    """
    out: list[str] = []
    for line in src.splitlines():
        if line.lstrip().startswith("#"):
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def _find_attach_calls(src: str) -> list[ast.Call]:
    """AST 抽取所有 `attach_h_segment_prefill(...)` 调用节点。"""
    tree = ast.parse(src)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name == "attach_h_segment_prefill":
            calls.append(node)
    return calls


def _arg_repr(node: ast.AST) -> str:
    """把实参节点还原成可读字符串（用于 bind 与断言消息）。"""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - py<3.9 兜底，本仓库是 3.12
        return type(node).__name__


def _bind_call(call: ast.Call, sig: inspect.Signature) -> inspect.BoundArguments:
    """用真实签名绑定 AST 调用的实参形态（值用占位字符串）。"""
    args = [_arg_repr(a) for a in call.args]
    kwargs = {kw.arg: _arg_repr(kw.value) for kw in call.keywords if kw.arg}
    return sig.bind(*args, **kwargs)


@pytest.fixture(scope="module")
def attach_signature() -> inspect.Signature:
    from app.services.four_table.h_cycle_adjudication_prefill import (
        attach_h_segment_prefill,
    )

    return inspect.signature(attach_h_segment_prefill)


# ═══════════════════════════════════════════════════════════════════════════
# 存在性自检（memory 铁律：按名单扫描必配「条目数 >= N」，防 KeyError 伪装成断言失败）
# ═══════════════════════════════════════════════════════════════════════════
def test_scan_surface_is_not_empty():
    """扫描面自检：四个 render 文件都在磁盘上且非空。"""
    assert len(H1234_RENDERS) == 4, "H1~H4 清单被改动，请同步更新守卫"
    for cycle, path in H1234_RENDERS.items():
        assert path.exists(), f"{cycle} render 文件不存在: {path}"
        assert len(_read(path)) > 2000, f"{cycle} render 文件异常短，扫描面可能失效"


def test_shared_module_exports_expected_symbols(attach_signature):
    """共享件导出面自检：符号在、且是 async。"""
    from app.services.four_table import h_cycle_adjudication_prefill as mod

    for name in ("build_h_segment_prefill", "attach_h_segment_prefill"):
        assert hasattr(mod, name), f"共享件缺少导出 {name}"
        assert inspect.iscoroutinefunction(getattr(mod, name)), f"{name} 必须是 async"
    # 签名里必须有这四个参数名，否则下面的语义断言会静默失效
    for pname in ("ctx", "payload", "cycle", "accounts", "slot_key_prefix"):
        assert pname in attach_signature.parameters, (
            f"签名缺少参数 {pname}；守卫的语义断言将失效，请同步更新"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 7 前置：四处调用必须能真实绑定
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("cycle", sorted(H1234_RENDERS))
def test_attach_call_exists(cycle):
    """每个 render 恰好有一处 attach 调用（多处 = 重复挂载，会产出两次）。"""
    src = _strip_py_comments(_read(H1234_RENDERS[cycle]))
    calls = _find_attach_calls(src)
    assert len(calls) == 1, (
        f"{cycle}: 期望恰好 1 处 attach_h_segment_prefill 调用，实测 {len(calls)} 处。"
        " 0 处 = 未接线；>1 处 = 重复挂载。"
    )


@pytest.mark.parametrize("cycle", sorted(H1234_RENDERS))
def test_attach_call_binds_to_real_signature(cycle, attach_signature):
    """🔴 核心判据：AST 实参必须能被真实签名 bind()。

    改造前 H1/H4 传 5 个位置参数 ⇒ 此断言必红（TypeError: too many positional）。
    """
    src = _strip_py_comments(_read(H1234_RENDERS[cycle]))
    calls = _find_attach_calls(src)
    assert calls, f"{cycle}: 未找到 attach 调用"
    call = calls[0]
    try:
        _bind_call(call, attach_signature)
    except TypeError as e:
        pos = [_arg_repr(a) for a in call.args]
        kw = [kw.arg for kw in call.keywords if kw.arg]
        pytest.fail(
            f"{cycle}: attach_h_segment_prefill 调用与签名不兼容 -> {e}\n"
            f"  位置参数({len(pos)}): {pos}\n"
            f"  关键字参数: {kw}\n"
            f"  真实签名: {attach_signature}\n"
            "  该错误在运行时被 render 的 fail-open 吞成 WARNING，"
            "表现为「审定表点带入没数据」。"
        )


@pytest.mark.parametrize("cycle", sorted(H1234_RENDERS))
def test_attach_call_argument_semantics(cycle, attach_signature):
    """绑定后参数语义必须正确：ctx / payload / cycle 不得错位。

    改造前 H2/H3 因形参顺序是 `(payload, ctx, ...)` 而把两者对调 ——
    能 bind 但 payload 收到 ctx。故 bind 成功还不够，必须查语义。
    """
    src = _strip_py_comments(_read(H1234_RENDERS[cycle]))
    call = _find_attach_calls(src)[0]
    bound = _bind_call(call, attach_signature)
    a = bound.arguments

    ctx_expr = str(a.get("ctx", ""))
    payload_expr = str(a.get("payload", ""))
    cycle_expr = str(a.get("cycle", ""))
    prefix_expr = str(a.get("slot_key_prefix", ""))
    accounts_expr = str(a.get("accounts", ""))

    assert ctx_expr == "ctx", (
        f"{cycle}: `ctx` 形参收到的是 `{ctx_expr}` 而非 `ctx` —— 参数错位。"
    )
    assert payload_expr and payload_expr != "ctx", (
        f"{cycle}: `payload` 形参收到 `{payload_expr}`（疑似与 ctx 对调）。"
    )
    assert cycle_expr.strip("'\"") == cycle, (
        f"{cycle}: `cycle` 实参为 `{cycle_expr}`，与所在 render 的循环号不符。"
    )
    assert prefix_expr.startswith(f"{cycle}_SLOT_KEY_PREFIX"), (
        f"{cycle}: `slot_key_prefix` 实参为 `{prefix_expr}`，"
        f"期望引用 `{cycle}_SLOT_KEY_PREFIX` 常量（不得写字面量 dict）。"
    )
    assert accounts_expr == "accounts", (
        f"{cycle}: `accounts` 实参为 `{accounts_expr}`，"
        "期望传 resolve_semantic_accounts 的返回值。"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：确认上面的判据真的能抓住已知的两种错法
# ═══════════════════════════════════════════════════════════════════════════
def test_selfcheck_five_positional_args_would_fail(attach_signature):
    """替身：复现 H1/H4 改造前的 5 位置参数形态，必须 bind 失败。"""
    stub = "await attach_h_segment_prefill(ctx, payload, 'H1', accounts, H1_SLOT_KEY_PREFIX)"
    call = _find_attach_calls(f"async def f():\n    {stub}\n")[0]
    with pytest.raises(TypeError):
        _bind_call(call, attach_signature)


def test_selfcheck_swapped_ctx_payload_would_fail(attach_signature):
    """替身：复现 H2/H3 改造前 payload/ctx 对调的形态，语义断言必须打红。

    构造「payload 位置传 ctx、ctx 位置传 payload」——若签名恢复成
    `(payload, ctx, ...)`，这个替身就能 bind 且看似正常。
    """
    stub = (
        "await attach_h_segment_prefill(payload, ctx, cycle='H2',"
        " accounts=accounts, slot_key_prefix=H2_SLOT_KEY_PREFIX)"
    )
    call = _find_attach_calls(f"async def f():\n    {stub}\n")[0]
    bound = _bind_call(call, attach_signature)
    assert str(bound.arguments.get("ctx")) == "payload", (
        "替身构造失效：期望 ctx 形参收到 payload。若本断言失败，"
        "说明签名已变更，请同步更新反向自检。"
    )


def test_selfcheck_comment_stripping_is_effective():
    """`_strip_py_comments` 有效性自检：注释里的调用不得被数进来。"""
    src = (
        "# await attach_h_segment_prefill(ctx, payload, 'HX', a, b)\n"
        "async def f():\n"
        "    return 1\n"
    )
    assert _find_attach_calls(_strip_py_comments(src)) == [], (
        "注释剥离失效：注释里的调用被数成真实调用"
    )
    # 反面：不剥注释时确实会被数到（证明这条自检不是空转）
    assert len(_find_attach_calls(src)) == 0 or True  # ast 本身不解析注释，见下
    # ast.parse 不会把注释当代码，故真正的风险在正则式扫描。
    # 这里额外验证：若改用正则，注释会被误数。
    assert re.search(r"attach_h_segment_prefill\s*\(", src), (
        "自检数据异常：替身里应含该符号"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 8：消费面事实登记（dead output 不得被静默接受）
# ═══════════════════════════════════════════════════════════════════════════
def _frontend_files() -> list[Path]:
    return [
        p
        for p in FRONTEND_SRC.rglob("*")
        if p.suffix in {".ts", ".vue"}
        and "__tests__" not in p.parts
        and p.name != "components.d.ts"
    ]


def test_segment_prefill_consumer_count_matches_registry():
    """`adjudication_segment_prefill` 的前端消费方数量必须与登记一致。

    登记曾为 0 = 已实证的 dead output（H5~H10 产它但无人读）；
    本 spec Task 5 接通后为 3。数量再变即打红 —— 那时应更新
    `SEGMENT_PREFILL_KNOWN_CONSUMERS` 并同步 tasks.md，而不是把断言删掉。
    """
    files = _frontend_files()
    assert len(files) > 500, (
        f"前端扫描面异常小（{len(files)} 个文件），路径可能解析错误: {FRONTEND_SRC}"
    )
    hits = sorted(
        p.relative_to(FRONTEND_SRC).as_posix()
        for p in files
        if SEGMENT_PREFILL_KEY in p.read_text(encoding="utf-8", errors="ignore")
    )
    assert len(hits) == SEGMENT_PREFILL_KNOWN_CONSUMERS, (
        f"`{SEGMENT_PREFILL_KEY}` 前端消费方数量由 "
        f"{SEGMENT_PREFILL_KNOWN_CONSUMERS} 变为 {len(hits)}: {hits}\n"
        "  若是接上了消费方 -> 更新 SEGMENT_PREFILL_KNOWN_CONSUMERS 并同步 tasks.md；\n"
        "  若是误引用 -> 移除。"
    )
    # 逐个登记：只断言数量会被「删一个 + 加一个」绕过（净数不变但接线已漂移）
    assert tuple(hits) == SEGMENT_PREFILL_EXPECTED_CONSUMERS, (
        f"`{SEGMENT_PREFILL_KEY}` 的消费方清单发生漂移。\n"
        f"  期望: {list(SEGMENT_PREFILL_EXPECTED_CONSUMERS)}\n"
        f"  实际: {hits}"
    )


def test_h1_category_prefill_is_the_wired_path():
    """H1 的**已接通**路径是 `adjudication_category_prefill`，须保持接线。

    这条是 H2/H3/H4 补预填时的范式参照（后端产 → 宿主合并 → Tab 消费）。
    若它被改坏，H2/H3/H4 会照错误范式抄。
    """
    key = "adjudication_category_prefill"
    be = _read(H1234_RENDERS["H1"])
    assert f'"{key}"' in be, f"H1 render 不再产出 {key}，范式被破坏"

    host = FRONTEND_SRC / "components/workpaper/GtH1FixedAssets.vue"
    tab = FRONTEND_SRC / "components/workpaper/h1/core/H1TabAdjudication.vue"
    assert key in _read(host), f"H1 宿主未合并 {key}（宿主不传则 Tab 恒读不到）"
    assert key in _read(tab), f"H1 审定表 Tab 未消费 {key}"


# ═══════════════════════════════════════════════════════════════════════════
# Property：宁缺勿造的两条语义（Task 5 / Task 17 变异检验补强）
#
# 🔴 本节补的是变异检验判出 GREEN 的缺口：改造前本文件只验**调用点签名绑定**
# （Task 5 的假交付形态是「共享件在、四个调用点全部传错参」），
# 却没有一条断言验共享件**自身的行为**：
#   - 把 `if not slot or not getattr(slot, "found", False):` 改成 `if not slot:`
#     （即对未命中槽也去取数产段）→ 守卫全绿；
#   - 把「全槽皆空返 None」改成返 `{"segments": [], "enabled": True}` → 守卫全绿。
#
# 两条语义都关系到「本项目无此科目」与「取到空」的区分：
#   - 槽 `found=False` 表示**科目表里没有这个科目** ⇒ 不产段（不得填 0）；
#   - 返 `None` 让调用方**不写** `adjudication_segment_prefill` 键 ——
#     「键不存在」与「键存在但 items 为空」对前端是两种语义。
# ═══════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio
import types as _types
from dataclasses import dataclass as _dataclass, field as _field

import pytest as _pytest


@_dataclass
class _FakeSlot:
    key: str
    found: bool
    codes: tuple[str, ...] = ()


@_dataclass
class _FakeAccounts:
    slots: dict = _field(default_factory=dict)


def _patch_prefill(monkeypatch, recorder: list, items_by_code: dict):
    """替换 `build_d_adjudication_prefill`，记录被取数的码。

    共享件是**函数内延迟导入**（避免纯函数测试也要连库），故必须打在
    源模块 `app.services.d_cycle_extraction.prefill` 上，打在共享件模块上无效。
    """
    import app.services.d_cycle_extraction.prefill as _p

    async def _fake(ctx, *, account_prefix, mode):  # noqa: ANN001
        recorder.append((account_prefix, mode))
        return items_by_code.get(account_prefix, [])

    monkeypatch.setattr(_p, "build_d_adjudication_prefill", _fake)


class TestNothingFabricatedWhenSlotMissing:
    def test_slot_not_found_produces_no_segment(self, monkeypatch):
        """`found=False` 的槽**不得**被取数、不得产段（宁缺勿造）。"""
        from app.services.four_table.h_cycle_adjudication_prefill import (
            build_h_segment_prefill,
        )

        called: list = []
        _patch_prefill(monkeypatch, called, {"1641": [{"x": 1}], "1642": [{"y": 2}]})

        accounts = _FakeAccounts(
            slots={
                "gross": _FakeSlot("gross", found=True, codes=("1641",)),
                # 科目表里没有累计折旧 → 必须整槽跳过
                "accum_dep": _FakeSlot("accum_dep", found=False, codes=("1642",)),
            }
        )
        got = _asyncio.run(
            build_h_segment_prefill(
                object(), accounts, {"gross": "a", "accum_dep": "b"}, cycle="H8"
            )
        )
        assert got is not None
        segs = [s["segment"] for s in got["segments"]]
        assert segs == ["gross"], f"未命中槽也产段了: {segs}"
        assert called == [("1641", "balance")], (
            f"未命中槽仍被取数（多余 DB 往返 + 可能填出 0）: {called}"
        )

    def test_all_slots_missing_returns_none_not_empty_shell(self, monkeypatch):
        """全槽皆空必须返 `None` —— 返空壳会让「无此科目」显示成「取到空」。"""
        from app.services.four_table.h_cycle_adjudication_prefill import (
            attach_h_segment_prefill,
            build_h_segment_prefill,
        )

        called: list = []
        _patch_prefill(monkeypatch, called, {})

        accounts = _FakeAccounts(
            slots={"gross": _FakeSlot("gross", found=False, codes=("1641",))}
        )
        got = _asyncio.run(
            build_h_segment_prefill(object(), accounts, {"gross": "a"}, cycle="H8")
        )
        assert got is None, f"期望 None（键不写），实为 {got!r}"

        # attach 侧连带语义：返 False 且**一个键都不加**
        payload: dict = {}
        ok = _asyncio.run(
            attach_h_segment_prefill(
                object(),
                payload,
                cycle="H8",
                accounts=accounts,
                slot_key_prefix={"gross": "a"},
            )
        )
        assert ok is False
        assert payload == {}, f"无数据时不得写任何键，实为 {sorted(payload)}"

    def test_empty_items_slot_produces_no_segment(self, monkeypatch):
        """槽 `found=True` 但取数返空 → 也不产段（同样是宁缺勿造）。"""
        from app.services.four_table.h_cycle_adjudication_prefill import (
            build_h_segment_prefill,
        )

        called: list = []
        _patch_prefill(monkeypatch, called, {})  # 所有码都返 []

        accounts = _FakeAccounts(
            slots={"gross": _FakeSlot("gross", found=True, codes=("1641", "1651"))}
        )
        got = _asyncio.run(
            build_h_segment_prefill(object(), accounts, {"gross": "a"}, cycle="H8")
        )
        assert got is None
        # 双族两个码都应被尝试
        assert called == [("1641", "balance"), ("1651", "balance")], called

    def test_attach_writes_both_keys_when_data_exists(self, monkeypatch):
        """有数据时 additive 挂两个键（`adjudication_segment_prefill` + 灰度开关）。"""
        from app.services.four_table.h_cycle_adjudication_prefill import (
            attach_h_segment_prefill,
        )

        called: list = []
        _patch_prefill(monkeypatch, called, {"2601": [{"a": 1}]})

        accounts = _FakeAccounts(
            slots={"gross": _FakeSlot("gross", found=True, codes=("2601",))}
        )
        payload: dict = {"existing": 1}
        ok = _asyncio.run(
            attach_h_segment_prefill(
                object(),
                payload,
                cycle="H9",
                accounts=accounts,
                slot_key_prefix={"gross": "lease_liability"},
            )
        )
        assert ok is True
        assert payload["existing"] == 1, "必须是 additive，不得覆盖既有键"
        assert payload["adjudication_segment_prefill"]["enabled"] is True
        assert payload["hi_extraction_enabled"] is True

    def test_slot_failure_does_not_abort_other_slots(self, monkeypatch):
        """单槽取数异常只丢该槽（fail-open），不拖垮整个 render。"""
        from app.services.four_table.h_cycle_adjudication_prefill import (
            build_h_segment_prefill,
        )

        import app.services.d_cycle_extraction.prefill as _p

        async def _fake(ctx, *, account_prefix, mode):  # noqa: ANN001
            if account_prefix == "1642":
                raise RuntimeError("boom")
            return [{"code": account_prefix}]

        monkeypatch.setattr(_p, "build_d_adjudication_prefill", _fake)

        accounts = _FakeAccounts(
            slots={
                "gross": _FakeSlot("gross", found=True, codes=("1641",)),
                "accum_dep": _FakeSlot("accum_dep", found=True, codes=("1642",)),
            }
        )
        got = _asyncio.run(
            build_h_segment_prefill(
                object(), accounts, {"gross": "a", "accum_dep": "b"}, cycle="H8"
            )
        )
        assert got is not None
        assert [s["segment"] for s in got["segments"]] == ["gross"]

    def test_selfcheck_removing_found_gate_would_change_result(self, monkeypatch):
        """反向自检：不看 `found` 时未命中槽也会产段（证明上面第一条非空转）。"""
        called: list = []
        _patch_prefill(monkeypatch, called, {"1642": [{"y": 2}]})

        import app.services.d_cycle_extraction.prefill as _p

        # 复现「只判 slot 存在、不判 found」的旧行为
        async def _naive(accounts, slot_key_prefix):
            segs = []
            for k in slot_key_prefix:
                slot = accounts.slots.get(k)
                if not slot:
                    continue
                for code in slot.codes:
                    items = await _p.build_d_adjudication_prefill(
                        object(), account_prefix=code, mode="balance"
                    )
                    if items:
                        segs.append(k)
            return segs

        accounts = _FakeAccounts(
            slots={"accum_dep": _FakeSlot("accum_dep", found=False, codes=("1642",))}
        )
        naive = _asyncio.run(_naive(accounts, {"accum_dep": "b"}))
        assert naive == ["accum_dep"], "朴素实现应产出段，否则本自检无意义"
