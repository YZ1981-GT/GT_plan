# -*- coding: utf-8 -*-
"""`check_sync_provider_golden_digest.py` 基线门自测。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 1 · Requirements 4.1 / 4.2 / 4.5

覆盖：
  1. `PROVIDERS` 登记的每一家都可 import 并产出应有的段（projection 为 null 的那几家
     须在 `_NO_PROJECTION_LABELS` 里登记理由，并与开关双向对账）。
  2. digest 总数由 `PROVIDERS` + 现算 report **两侧现算**（禁手抄数字：23 → 26 → 含
     sheet 粒度后再变，手抄必过期）。
  3. 现状 digest ≡ 已入库基线（零回归门本身此时必绿）。
  4. 变异反证：篡改一家的 contract digest ⇒ _compare 必须报漂移（门不是永绿装饰）。
  5. 合成 payload 确实驱动了 build_store_projection（D3 真库 0 行仍被覆盖，Req 4.5）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_sync_provider_golden_digest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_sync_provider_golden_digest", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: 🔴 因 provider 签名与本门禁不兼容而被 `[SKIP]` 的 provider（**必须显式登记**）。
#:
#: ✅ **2026-09-30 已清空**。此前唯一在册的是 `f1`：
#:    `build_store_projection(store_item_id, payload, *, contract)` 把 `store_item_id`
#:    做成**首位位置参数**，而本门禁按 `mod.build_store_projection(rows, contract=contract)`
#:    调用 ⇒ TypeError ⇒ 整家被 SKIP ⇒ F1 的三段 digest 全部不在零回归门内。
#:    原注释把处置留给 f1 lane「决定是脚本适配还是 provider 统一签名」——
#:    本轮选**脚本适配**（照本门既有的「provider 命名差异照实处理、不强行统一」原则，
#:    与 D2 用 `PILOT_ADAPTER_ID`、D4 取复数 instrumentation 同型），f1 的公开签名一字未改。
#:
#: 🔴 适配的分派条件必须看参数 **kind**：现算 24 家里 **15 家**把 `store_item_id` 声明为
#:    `KEYWORD_ONLY`，只有 f1 把它放在首位位置。首版按 `"store_item_id" in parameters`
#:    判（只看名字在不在）⇒ 给那 15 家多传一个位置参数，当场把 8 家打成 TypeError。
#:
#: 🔴 为什么要有这张表：2026-09-28 实测发现 `test_digest_count_matches_provider_capabilities`
#:    的公式按 `PROVIDERS` 全表求和，而 report 里少了被 SKIP 的那家 ⇒ 数字恒对不上
#:    （实测 139 vs 142，差 3 正是 f1 的 contract+instr+projection）。若只把期望数字改大改小，
#:    「有一家根本没进门」这个事实就被永久掩盖了。
#:
#: 🔴 保留这张**空**表而不删掉它：下面两条判据（正向「门内 == 登记 − 本表」＋ 反向
#:    「本表每一条都真的不在门内」）构成一对，空表时它们退化为「门必须覆盖全部登记 provider」，
#:    仍在起作用；将来又出现签名不兼容时，登记处现成。
#:    ⚠ 往里加条目前先想清楚：门禁本身现在已经把 skip 判为**失败**
#:    （`check_sync_provider_golden_digest.main()` 的覆盖面判据），
#:    所以再往这里加一条并不能让门变绿 —— 正确处置是修调用或关掉那一段的开关。
SKIPPED_PROVIDER_LABELS: frozenset[str] = frozenset()

#: 9 家「已交付核心 contract」—— 无论 PROVIDERS 怎么增长，这 9 家必须一直在门内。
_CORE_LABELS: frozenset[str] = frozenset(
    {"b60", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "e1"}
)

#: 🔴 **如实记 projection=None** 的 provider 登记表（label → 理由）。
#:
#: 2026-10-01 从写死的 `if p["label"] == "b60"` 改成这张表。原断言的形态是
#: 「除 b60 外每家 projection 必须非空」—— g7 作为 `has_projection=False` 纳入门内后
#: 当场打红，而它的 null **是设计如实**（见下），不是缺陷。
#:
#: 为什么不是「加一行就变绿的后门」（本仓反复登记的 allowlist 失效形态）：
#: 下面 `test_no_projection_registry_matches_providers_table` 把本表与 `PROVIDERS`
#: 的 `has_projection` 开关做**双向**对账 —— 往这里加一家而不同时在 `PROVIDERS` 里
#: 把开关关掉，本表就会被判为失效条目；反过来在 `PROVIDERS` 里悄悄关掉某家的开关
#: 而不登记理由，也会打红。即「豁免必须可被实际情况伪证」。
_NO_PROJECTION_LABELS: dict[str, str] = {
    "b60": "simple_checklist 形态，模块无 build_store_projection，如实记 null（需求 4.5）",
    "g7": (
        "两级动态 pilot：既无 MANAGED_FIELD_SPECS 也无 managed_row_table_specs() 受管清单，"
        "门里的 _synthetic_rows() 无法合成受管行 ⇒ 按本门既定原则「某一段真不适用就关那一段"
        "开关，不要让它整家抛异常被跳过」，置 has_projection=False。"
        "代价须如实记账：g7 只覆盖 contract + instrumentation 两段（2/3）。"
    ),
}


def test_all_delivered_providers_produce_three_sections() -> None:
    mod = _load_module()
    report = mod.run()
    labels = {p["label"] for p in report["providers"]}
    declared = {row[0] for row in mod.PROVIDERS}
    # 🔴 labels 从 PROVIDERS 现算，**不手抄**（本文件另一条判据早就立了这条纪律，
    #    而这里首版写死 9 家，并发 lane 把 PROVIDERS 加到 23 家后必然过期 —— 2026-09-28 实测）。
    assert labels == declared - SKIPPED_PROVIDER_LABELS, (
        f"门内 provider 与 PROVIDERS 表不符：只在表里={sorted(declared - labels)}、"
        f"只在报告里={sorted(labels - declared)}。前者若是新的签名不兼容，"
        f"请登记进 SKIPPED_PROVIDER_LABELS 并写明归属 lane，不要改这条断言。"
    )
    # 已交付核心 9 家是底线，任何时候都不得掉出门内。
    assert _CORE_LABELS <= labels, f"核心 contract 掉出零回归门：{sorted(_CORE_LABELS - labels)}"
    for p in report["providers"]:
        assert p["contract_payload_sha256"], f"{p['label']} contract digest 空"
        assert p["instrumentation_sha256"], f"{p['label']} instrumentation digest 空"
        if p["label"] in _NO_PROJECTION_LABELS:
            assert p["store_projection_sha256"] is None, (
                f"{p['label']} 已登记为「如实记 null」，却算出了 projection digest "
                f"⇒ 它的 has_projection 开关应改回 True 并从 _NO_PROJECTION_LABELS 删除"
            )
        else:
            assert p["store_projection_sha256"], (
                f"{p['label']} projection digest 空 —— 若该 provider 真的没有这一段，"
                f"请在 PROVIDERS 里置 has_projection=False **并**登记进 "
                f"_NO_PROJECTION_LABELS 写明理由，不要改这条断言"
            )


def test_no_projection_registry_matches_providers_table() -> None:
    """🔴 反向断言：`_NO_PROJECTION_LABELS` 与 `PROVIDERS.has_projection` 双向对账。

    只存理由文本的豁免名单 = 加一行就变绿的后门（本仓已多轮登记这个失效形态）。
    这里把名单钉在一个**可被实际情况伪证**的事实上：

      * 名单里的每一家，`PROVIDERS` 里的 `has_projection` 必须真的是 False
        （否则是躺着失效的条目 —— 它已经有 projection 了）；
      * `PROVIDERS` 里每个 `has_projection=False` 的 label 必须在名单里有理由
        （否则有人悄悄关掉一段开关、少掉的覆盖面无人知晓）；
      * 名单非空且理由非空白 —— 空转的名单退化成装饰。
    """
    mod = _load_module()
    switched_off = {label for (label, _m, _c, hp, _p) in mod.PROVIDERS if not hp}
    assert set(_NO_PROJECTION_LABELS) == switched_off, (
        f"登记表与 PROVIDERS 开关不符：只在登记表={sorted(set(_NO_PROJECTION_LABELS) - switched_off)}"
        f"（已有 projection 的失效条目，应删）、"
        f"只在 PROVIDERS={sorted(switched_off - set(_NO_PROJECTION_LABELS))}"
        f"（开关被关掉但没写理由，应登记）"
    )
    assert _NO_PROJECTION_LABELS, "登记表为空时本条退化为空转，应与 PROVIDERS 一起重判"
    for label, reason in _NO_PROJECTION_LABELS.items():
        assert reason and reason.strip(), f"{label} 的豁免理由为空"


def test_digest_count_matches_provider_capabilities() -> None:
    """digest 总数 = 每家 contract + instrumentation（必有）+ projection（B60 无该路径）
    + 🔴 sheet 粒度 digest（第二轮复盘问题 5 修复：此前 run() 的公式漏计 sheet_digests，
    与 P1-4 加的 sheet 粒度判据面脱节，数字失真）。

    断言从 PROVIDERS 表 + 现算 report **两侧现算**而非手抄数字（首版写死 23，E1 纳入后
    变 26，本次补 sheet 粒度后又变 ⇒ 手抄必过期）。B60 是 simple_checklist 形态、无
    `build_store_projection` ⇒ 它的 projection 如实记 null，不假造 digest（需求 4.5）。
    """
    mod = _load_module()
    report = mod.run()
    # 🔴 只对**实际进了门**的 provider 求和 —— 被 SKIP 的那家（签名不兼容，见
    #    SKIPPED_PROVIDER_LABELS）不产出 digest，把它算进分母会让公式恒对不上，
    #    而人多半会去改数字而不是追问「为什么有一家没进门」。
    in_门 = {p["label"] for p in report["providers"]}
    base_expected = sum(
        2 + (1 if has_proj else 0)
        for (label, _m, _c, has_proj, _p) in mod.PROVIDERS
        if label in in_门
    )
    sheet_expected = sum(len(p.get("sheet_digests") or {}) for p in report["providers"])
    assert report["digest_count"] == base_expected + sheet_expected


def test_skipped_providers_are_really_skipped_and_registered() -> None:
    """反向断言：`SKIPPED_PROVIDER_LABELS` 里的每一家**真的**不在门内，且真的在 PROVIDERS 表里。

    两侧都要查：
      * 若某家已被修好（进门了）⇒ 必须从 SKIPPED 里删，否则名单会躺着失效项；
      * 若某家压根不在 PROVIDERS 表里 ⇒ 说明名单抄错了 label。
    """
    mod = _load_module()
    report = mod.run()
    in_门 = {p["label"] for p in report["providers"]}
    declared = {row[0] for row in mod.PROVIDERS}
    for label in SKIPPED_PROVIDER_LABELS:
        assert label in declared, f"{label} 不在 PROVIDERS 表里 —— SKIPPED 名单抄错了"
        assert label not in in_门, (
            f"{label} 现已进入零回归门 ⇒ 请从 SKIPPED_PROVIDER_LABELS 删除该条"
        )


def test_current_matches_committed_baseline() -> None:
    """现状 digest ≡ 已入库基线（零回归门此时必绿）。"""
    mod = _load_module()
    baseline = mod._load_baseline()
    assert baseline is not None, "基线文件缺失 —— 应先 --update 入库"
    drift = mod._compare(mod.run(), baseline)
    assert drift == [], f"现状与基线漂移：{drift}"


def test_mutation_sheet_digest_drift_is_detected() -> None:
    """变异反证（P1-4 sheet 粒度）：篡改一家某 sheet 的 digest ⇒ _compare 必须报出该 sheet 漂移。

    P1-4 复盘修复后，contract 整体 digest 不再进严格比较（扩容新 sheet 是 additive）；
    改动**已有 sheet** 才算回归，由 sheet 粒度 digest 精确定位。
    """
    mod = _load_module()
    current = mod.run()
    tampered = {
        "digest_count": current["digest_count"],
        "providers": [dict(p) for p in current["providers"]],
    }
    # 篡改 d1 的某个 sheet digest（模拟已有 sheet 被改动）
    d1 = next(dict(p) for p in tampered["providers"] if p["label"] == "d1")
    d1_sheets = dict(d1.get("sheet_digests") or {})
    assert d1_sheets, "d1 应有 sheet_digests"
    first_sk = sorted(d1_sheets)[0]
    d1_sheets[first_sk] = "0" * 64
    d1["sheet_digests"] = d1_sheets
    tampered["providers"] = [d1 if p["label"] == "d1" else dict(p) for p in tampered["providers"]]
    drift = mod._compare(current, tampered)
    assert drift, "变异后未检出漂移 —— 门是永绿装饰"
    assert any(d["field"] == f"sheet[{first_sk}]" and d["label"] == "d1" for d in drift), drift


def test_synthetic_payload_drives_projection_for_zero_row_provider() -> None:
    """D3 真库 0 行，但合成 payload 必须驱动出非空 projection（Requirement 4.5）。"""
    mod = _load_module()
    d3 = mod._import_provider("phase5_d3_prepaid_receipts")
    rows = mod._synthetic_rows(d3)
    assert len(rows) == 2
    # 合成两行须各带稳定 rowId 且账龄 nested 路径已建 dict
    assert all(r.get("rowId") for r in rows)
    assert isinstance(rows[0].get("agingPrior"), dict), "nested 账龄路径应被逐级建 dict"


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 覆盖面判据的自测（2026-09-30 新增）
#
# `main()` 新加了两道覆盖面判据（skip 判失败 / 已登记 provider 必须在基线里有条目）。
# 那两道判据本身也需要被验 —— 否则它们就是「又一个没人验的门」，
# 而这一整轮排查的起点恰恰是「门在但对某一家不生效」。
# ═══════════════════════════════════════════════════════════════════════════


def test_run_reports_skipped_as_data_not_only_stderr() -> None:
    """🔴 `run()` 必须把 skip 带进返回值。

    原实现只 `print("[SKIP] …", file=sys.stderr)` 然后 `continue` ⇒ 调用方（含 `main()`
    与 pre-push）拿不到这个事实，只能靠人读 stderr。实测后果：f1 整家从未进基线而门照样
    exit 0，持续多轮无人发现。
    """
    mod = _load_module()
    report = mod.run()
    assert "skipped" in report, (
        "run() 的返回值里没有 `skipped` 键 —— skip 又回到了「只打 stderr」的状态，"
        "main() 的覆盖面判据会拿不到数据而恒绿"
    )
    assert report["skipped"] == [], f"当前有 provider 被跳过：{report['skipped']}"


def test_main_fails_when_a_provider_is_skipped(monkeypatch) -> None:
    """🔴 变异反证①：注入一个 skip ⇒ `main()` 必须返回非 0。

    这条把「skip 会被判为失败」变成会打红的事实。少了它，有人把 `return 1` 改回
    `continue` 时没有任何判据会响。
    """
    mod = _load_module()
    real_run = mod.run

    def _with_fake_skip() -> dict:
        report = real_run()
        report = dict(report)
        report["skipped"] = [{"label": "zz", "error": "TypeError: 合成的 skip"}]
        return report

    monkeypatch.setattr(mod, "run", _with_fake_skip)
    monkeypatch.setattr(sys, "argv", ["check_sync_provider_golden_digest.py"])
    assert mod.main() != 0, (
        "注入 skip 后 main() 仍返回 0 —— 「skip 判失败」这条判据没生效"
    )


def test_main_fails_when_a_registered_provider_has_no_baseline_entry(monkeypatch) -> None:
    """🔴 变异反证②：基线里抽掉一家的条目 ⇒ `main()` 必须返回非 0。

    这条覆盖的正是 f1 那个真实形态：provider 已登记、能算出 digest，但**基线里没有它**
    ⇒ `_compare` 遍历不到它的基线条目 ⇒ 它的任何漂移永远不会被发现。
    """
    mod = _load_module()
    baseline = mod._load_baseline()
    assert baseline is not None

    victim = "d1"
    stripped = {
        "digest_count": baseline["digest_count"],
        "providers": [p for p in baseline["providers"] if p["label"] != victim],
    }
    assert len(stripped["providers"]) == len(baseline["providers"]) - 1, "没抽掉任何条目"

    monkeypatch.setattr(mod, "_load_baseline", lambda: stripped)
    monkeypatch.setattr(sys, "argv", ["check_sync_provider_golden_digest.py"])
    assert mod.main() != 0, (
        f"基线里抽掉 {victim} 后 main() 仍返回 0 —— "
        "「已登记 provider 必须在基线里有条目」这条判据没生效"
    )


def test_store_item_id_dispatch_keys_on_parameter_kind_not_name() -> None:
    """🔴 变异反证③：`store_item_id` 的分派必须按参数 **kind**，不能只看名字在不在。

    现算 24 家里 **15 家**把 `store_item_id` 声明为 `KEYWORD_ONLY`，只有 f1 把它放在
    首位位置。按「名字在不在」分派会给那 15 家多传一个位置参数 —— 实测当场把 8 家
    打成 TypeError（而在旧实现下它们会被静默 SKIP，等于把一个洞换成八个洞）。

    本判据不复刻分派逻辑，而是锁住**分组事实**：两类都非空，且首位位置参数是
    `store_item_id` 的恰好只有 f1。分组一变（比如有人把 f1 的签名统一了）本条会红，
    届时应连带简化门里的分派分支。
    """
    import importlib
    import inspect

    mod = _load_module()
    positional_first: list[str] = []
    keyword_only: list[str] = []
    for label, module_name, _const, has_projection, _plural in mod.PROVIDERS:
        if not has_projection:
            continue
        provider = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
        params = inspect.signature(provider.build_store_projection).parameters
        positional = [
            n
            for n, p in params.items()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if positional[:1] == ["store_item_id"]:
            positional_first.append(label)
        elif "store_item_id" in params:
            keyword_only.append(label)

    assert positional_first == ["f1"], (
        f"首位位置参数是 store_item_id 的不再只有 f1，而是 {positional_first} —— "
        "门里的分派分支需要跟着重判"
    )
    assert len(keyword_only) >= 10, (
        f"把 store_item_id 声明为 KEYWORD_ONLY 的只有 {len(keyword_only)} 家 "
        f"（{keyword_only}）—— 这一类若为空，「按名字分派」与「按 kind 分派」"
        "就没有区分力，本条反证会退化成空转"
    )
