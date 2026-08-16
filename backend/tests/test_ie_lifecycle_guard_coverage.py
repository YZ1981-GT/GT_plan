"""导入导出全生命周期 —— 守卫五类覆盖元守卫（Wave 6 Task 22）

spec: workpaper-import-export-lifecycle-closure（R7.1、R7.4）

## 这是「守卫的守卫」

本 spec 立了 16 个守卫文件、288 条判据。风险不在单条判据写得对不对（那由
变异检验 `mutate_ie_lifecycle_guards.py` 负责），而在**某一类不变量整体没人守**：

删掉一个守卫文件、把某类断言全 skip、或改造时漏掉一整类，
其余守卫照样全绿 —— 因为没有任何判据在看「五类是否都有人管」。

⇒ 本文件断言五类不变量**逐类至少一个守卫文件存在且真在跑**：

| 类别 | 守的是什么 | 失守后的现象 |
|------|-----------|-------------|
| 产物自证 | 导出物必须自己说明「为什么是空白/为什么缺内容」 | 用户拿到空表却以为是数据真的没有 |
| 数据源接通 | 库里的录入必须能进 xlsx（不是只在 DB 里） | 导出文件缺录入内容，看不出来 |
| registry 三向锁死 | 前端 registry ↔ catalog ↔ 后端白名单一致 | 挂上去的按钮点了 400/404 |
| 孤儿基线 | 后端有能力但用户不可达的 composable 不许增长 | 能力做了没人能用 |
| 模板库只读 | `wp_templates/` 不被任何写路径碰 | 改一次污染此后所有新建项目 |

## 类别 → 守卫的映射真源

复用 `mutate_ie_lifecycle_guards.GUARD_FILES` 作为守卫清单真源 ——
不在本文件另抄一份路径表。两处各写一份的话，一处改名另一处 stale 且不打红。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))

from scripts.diagnose.mutate_ie_lifecycle_guards import (  # noqa: E402
    GUARD_FILES,
    UNCOVERED_RATIONALE,
)

#: 五类不变量 → 负责它的守卫键（`GUARD_FILES` 的键）。
#:
#: 🔴 每类至少一个。某类映射为空即打红 —— 那意味着这类不变量整体无人守。
INVARIANT_CLASSES: dict[str, tuple[str, ...]] = {
    "产物自证": ("self_evidence", "download_manifest"),
    "数据源接通": ("entry_payload", "export_entry_sheet"),
    "registry三向锁死": ("registry_lock", "prefix_reachability", "route_inventory"),
    "孤儿基线": ("orphan_baseline", "wiring_integrity"),
    "模板库只读": ("templates_readonly", "deref_script"),
}


def _guard_path(key: str) -> Path:
    return _REPO / GUARD_FILES[key]


def _count_assertions(key: str) -> int:
    src = _guard_path(key).read_text(encoding="utf-8")
    if key in {"orphan_baseline", "wiring_integrity", "registry_lock", "bulk_dialog"}:
        return len(re.findall(r"\b(?:it|test)\(\s*['\"`]", src))
    return len(re.findall(r"^\s*(?:async )?def test_\w+", src, re.M))


# ═══════════════════════════════════════════════════════════════════════════
# 五类覆盖
# ═══════════════════════════════════════════════════════════════════════════


def test_all_five_invariant_classes_declared() -> None:
    """必须正好五类 —— 少一类说明有不变量没被纳入治理。"""
    assert len(INVARIANT_CLASSES) == 5, (
        f"不变量类别数 {len(INVARIANT_CLASSES)} != 5：{sorted(INVARIANT_CLASSES)}"
    )


@pytest.mark.parametrize("cls_name", sorted(INVARIANT_CLASSES))
def test_each_class_has_at_least_one_guard(cls_name: str) -> None:
    """🔴 每类至少一个守卫文件，且文件真实存在。"""
    keys = INVARIANT_CLASSES[cls_name]
    assert keys, f"「{cls_name}」类无任何守卫 ⇒ 该不变量整体失守"
    missing = [k for k in keys if k not in GUARD_FILES]
    assert not missing, f"「{cls_name}」引用了未登记的守卫键: {missing}"
    absent = [k for k in keys if not _guard_path(k).is_file()]
    assert not absent, (
        f"「{cls_name}」的守卫文件不存在: {[GUARD_FILES[k] for k in absent]}\n"
        "→ 守卫文件被删除/改名后，这类不变量就没人守了，而其余守卫照样全绿"
    )


@pytest.mark.parametrize("cls_name", sorted(INVARIANT_CLASSES))
def test_each_class_guards_have_real_assertions(cls_name: str) -> None:
    """守卫文件不能是空壳 —— 文件在但断言被清空等于没守。"""
    empty = [k for k in INVARIANT_CLASSES[cls_name] if _count_assertions(k) == 0]
    assert not empty, (
        f"「{cls_name}」的守卫文件里抽不到任何断言: {empty}\n"
        "→ 文件存在但判据被清空（或抽取正则失效），属假绿"
    )


def test_every_guard_file_belongs_to_some_class() -> None:
    """反向：`GUARD_FILES` 里的每个守卫都应归入某一类。

    不归类的守卫说明「五类」划分不完整 —— 要么补类，要么说明它是辅助守卫。
    """
    classified = {k for keys in INVARIANT_CLASSES.values() for k in keys}
    #: 有意不归入五类的辅助守卫（各有归属说明）
    auxiliary = {
        # 元守卫：守的是「五类是否都有人守」与「CI 是否真挂了」，
        # 属治理层而非五类不变量本身 —— 把它算进某一类会造成自指。
        "guard_coverage",
        "ci_wiring",
        # 四场景 UI 是「入口语义」而非五类不变量之一；它守的是文案单一真源，
        # 与产物自证相邻但不同 —— 前者管「用户看到的说明」，后者管「产物里的自证」。
        "scenario_ui",
        # 场景 registry / mode 错用 / 归档门控：都是 bulk 场景的**内部一致性**，
        # 由「registry 三向锁死」类的同族判据间接覆盖，不单列为一类。
        "scenario_registry",
        "bulk_mode_mismatch",
        "archive_gating",
        # 可见集过滤粒度：属**权限×导出**交叉面，不是五类不变量本身。
        # 它守的是「别把 sheet 级判据用在整稿导出上」——
        # 失守表现为产物空壳（Task 24 实测 1025→0 份），已单列守卫 + 2 个变异。
        "bulk_visible_granularity",
        # 组件挂载渲染管线，属 UI 层，不是数据/契约不变量。
        "bulk_dialog",
        # x3 调整分录 spec 的专属守卫（x3-adjustment-entry-import-export 已归档）：
        # 属 x3 导入导出的子域契约，不是 IE lifecycle 五类不变量本身。
        # 它们守的是「16 个 X-3 sheet 接入专属 router 后端到端可用」。
        "x3_adapter_host",
        "x3_catalog_registration",
        "x3_column_alignment",
        "x3_ie_wiring",
        "x3_key_ledger",
        "x3_roundtrip_live",
    }
    unclassified = sorted(set(GUARD_FILES) - classified - auxiliary)
    assert not unclassified, (
        f"以下守卫既不属五类也未登记为辅助: {unclassified}\n"
        "→ 要么归类，要么加进 auxiliary 并写明为什么不算一类不变量"
    )


def test_auxiliary_guards_are_not_double_counted() -> None:
    """辅助守卫不得同时出现在五类里（语义矛盾）。"""
    classified = {k for keys in INVARIANT_CLASSES.values() for k in keys}
    auxiliary = {
        "guard_coverage", "ci_wiring",
        "scenario_ui", "scenario_registry", "bulk_mode_mismatch",
        "archive_gating", "bulk_dialog", "bulk_visible_granularity",
        "x3_adapter_host", "x3_catalog_registration", "x3_column_alignment",
        "x3_ie_wiring", "x3_key_ledger", "x3_roundtrip_live",
    }
    both = sorted(classified & auxiliary)
    assert not both, f"以下守卫既归五类又列为辅助: {both}"


def test_class_guard_keys_are_unique_across_classes() -> None:
    """同一守卫不应挂在多个类下 —— 那会让「每类都有守卫」变得虚高。"""
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for cls_name, keys in INVARIANT_CLASSES.items():
        for k in keys:
            if k in seen:
                dupes.append(f"{k}（{seen[k]} 与 {cls_name}）")
            else:
                seen[k] = cls_name
    assert not dupes, f"守卫被重复归类: {dupes}"


# ═══════════════════════════════════════════════════════════════════════════
# 守卫真在跑（不是文件存在就算）
# ═══════════════════════════════════════════════════════════════════════════


def test_no_guard_is_wholesale_skipped() -> None:
    """🔴 没有守卫文件被整体 skip / xfail 掉。

    `pytestmark = pytest.mark.skip` 或文件级 `pytest.skip(allow_module_level=True)`
    会让整个文件静默不跑，而 CI 显示的是「passed」——
    这是最省事的假绿手法，必须单独拦。
    """
    offenders: list[str] = []
    for key, rel in GUARD_FILES.items():
        path = _REPO / rel
        if not path.is_file() or path.suffix != ".py":
            continue
        src = path.read_text(encoding="utf-8")
        if re.search(r"^pytestmark\s*=\s*pytest\.mark\.(?:skip|xfail)\b(?!if)", src, re.M):
            offenders.append(f"{rel}（文件级 pytestmark skip/xfail）")
        # 🔴 判据要认「真实调用」而非「字符串出现」：本文件的 docstring 里就写着
        # `allow_module_level=True` 用于解释这种手法，纯查子串会把说明文字当违规
        # （初版即因此误报自己）。故要求它出现在真正的 pytest.skip( 调用里，
        # 且该行不是注释/文档行。
        for m in re.finditer(r"^(?!\s*#)[^\n]*pytest\.skip\([^\n]*allow_module_level\s*=\s*True",
                             src, re.M):
            line = m.group(0)
            # 排除 docstring 内的说明（约定：说明行会用反引号包裹代码）
            if "`" in line:
                continue
            offenders.append(f"{rel}（模块级 pytest.skip: {line.strip()[:60]}）")
    assert not offenders, (
        "以下守卫文件被整体跳过（CI 会显示 passed 但一条都没跑）：\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_five_class_guards_actually_pass() -> None:
    """真跑一遍五类的后端守卫 —— 文件存在 ≠ 断言通得过。

    只跑后端（前端 vitest 需 node 环境，由前端 CI job 负责）。
    """
    backend_keys = [
        k
        for keys in INVARIANT_CLASSES.values()
        for k in keys
        if (_REPO / GUARD_FILES[k]).suffix == ".py"
    ]
    targets = sorted({GUARD_FILES[k] for k in backend_keys})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--tb=line",
         "-p", "no:cacheprovider"],
        cwd=str(_REPO), check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=1800,
        # 🔴 与 `tests/scripts/test_wp_template_deref.py::_run` 同一处编码坑，
        # 删掉即在 Windows 上变红。`capture_output=True` ⇒ 子进程 stdout 是管道，
        # Windows 上 CPython 按 locale 编码（cp936/GBK）写；父进程的
        # `encoding="utf-8"` 只覆盖解码侧。此处子进程是 pytest，它转发被跑守卫的
        # 中文断言消息，乱码会让下面按 `\d+ passed` 取数与失败摘要都不可读。
        # Linux CI locale 为 UTF-8 故不暴露 —— Windows 本地专属假红。
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"五类后端守卫未全绿：\n{out[-2500:]}"
    )
    # 反向自检：确认真跑了足量断言（防 targets 为空导致空转）
    m = re.search(r"(\d+) passed", out)
    assert m and int(m.group(1)) >= 80, (
        f"只跑了 {m.group(1) if m else '?'} 条断言，疑似 targets 收集失败\n{out[-800:]}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 与变异检验的一致性
# ═══════════════════════════════════════════════════════════════════════════


def test_mutation_script_covers_every_class() -> None:
    """🔴 五类里每类至少有一个守卫做过变异检验。

    某类全部守卫都零变异 ⇒ 这类判据从未被证明有效，可能整类都是假绿。
    """
    from scripts.diagnose.mutate_ie_lifecycle_guards import MUTATIONS

    mutated = {m.guard for m in MUTATIONS}
    naked = [
        cls_name
        for cls_name, keys in INVARIANT_CLASSES.items()
        if not (set(keys) & mutated)
    ]
    assert not naked, (
        f"以下类别的守卫全体零变异检验: {naked}\n"
        "→ 该类判据从未被证明「改坏代码会打红」，可能整类假绿"
    )


def test_uncovered_rationale_does_not_hide_whole_class() -> None:
    """缺口登记不得掩盖「一整类无变异」。

    单个守卫登记理由可以；但若某类的**全部**守卫都靠登记豁免，
    等于用登记规避了整类验证。
    """
    fully_exempt = [
        cls_name
        for cls_name, keys in INVARIANT_CLASSES.items()
        if keys and all(k in UNCOVERED_RATIONALE for k in keys)
    ]
    assert not fully_exempt, (
        f"以下类别的全部守卫都在 UNCOVERED_RATIONALE 里: {fully_exempt}\n"
        "→ 登记理由是为个别守卫开的口子，不能整类豁免"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 真实库验收脚本的行为约束（Task 23）
#
# 验收脚本本身就是可执行判据，没有独立的 pytest 守卫文件。这里守它的两条
# 关键行为，防日后有人为了「让验收过」而放水。
# ═══════════════════════════════════════════════════════════════════════════

_LIVE_VERIFY = _REPO / "backend" / "scripts" / "diagnose" / "verify_ie_lifecycle_live.py"


def test_live_verify_script_exists() -> None:
    """真实库验收脚本必须在 —— 它是 R7.4/R7.5 的唯一可执行判据。"""
    assert _LIVE_VERIFY.is_file(), f"缺少真实库验收脚本: {_LIVE_VERIFY}"


def test_live_verify_refuses_fixture_fallback() -> None:
    """🔴 找不到合法对象时必须报「无法验收」+ 非零退出，不许 fixture 冒充。

    用 fixture 造一份底稿再导出，验的是 fixture 而不是这个平台的真实状态 ——
    那种「验收通过」比不验收更糟，因为它给了错误的信心。

    判据落在源码结构上（真跑一次要连库且耗时长，不适合放进这条元守卫）：
      · 有「无法验收」分支且该分支 return 非 0
      · 明确写了拒绝 fixture 的意图
      · 挑选函数对三个合法性条件都有排除逻辑
    """
    src = _LIVE_VERIFY.read_text(encoding="utf-8")
    assert "无法验收" in src, "缺少「无法验收」分支"
    assert "return 2" in src, "「无法验收」应以非零码退出"
    assert "fixture" in src, "未写明拒绝 fixture 冒充的意图"
    for cond in ("cr_nonblank", "_BLOCKED_FOR_ROUNDTRIP", "is_file()"):
        assert cond in src, f"挑选逻辑缺少合法性条件: {cond}"


def test_live_verify_probe_drills_to_leaf() -> None:
    """产物找回探针必须下钻到叶子标量，不能拿容器 `str()`。

    2026-08-12 实测：D1 有一条 `{"bankRows":[{...}]}`，取 `next(iter(obj.values()))`
    得到嵌套 list，`str()` 出来是 Python repr（单引号）⇒ 与产物里的渲染文本对不上
    ⇒ 判「找不回」。那是**探针缺陷不是产物缺陷**（载荷本身合法且已正确解析）。

    这类假红最费时间：会让人以为导出丢了内容而去改导出逻辑。
    """
    src = _LIVE_VERIFY.read_text(encoding="utf-8")
    assert "_leaf_probe" in src, "缺少叶子探针函数"
    assert "_leaf_probe(p.obj)" in src, "json_object 载荷未走叶子探针"
    assert "_leaf_probe(p.rows)" in src, "json_array 载荷未走叶子探针"
    # 反向：不得再出现直接取容器首值的旧写法
    assert "str(next(iter(p.obj.values())" not in src, (
        "仍在用容器 str() 作探针 ⇒ 会重现「找不回」假红"
    )


def test_live_verify_forbids_head_swap() -> None:
    """零回归对照禁用 HEAD-swap（并发度下会破坏他人未提交成果）。

    🔴 判据必须排除说明文字。本文件与验收脚本的 docstring 里都写着
    「禁 `git stash` / `git checkout`」来解释这条约束 —— 纯查子串会把
    **解释禁令的文字**当成违反禁令（Task 22 的 skip 检测已踩过同一个坑）。
    故只在「非注释、非反引号包裹」的代码行里查。
    """
    src = _LIVE_VERIFY.read_text(encoding="utf-8")
    offenders: list[str] = []
    for raw_line in src.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # 约定：说明性提及一律用反引号包裹（`git stash`）
        stripped = re.sub(r"`[^`]*`", "", line)
        for banned in ("git stash", "git checkout", "git reset"):
            if banned in stripped:
                offenders.append(f"{banned}: {line[:70]}")
    assert not offenders, (
        "验收脚本在代码里用了 HEAD-swap（会破坏并发会话未提交的工作树）：\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_live_verify_registers_known_data_state() -> None:
    """必须登记 checklist 空骨架现状（R7.7）—— 边界不写清，下次有人当缺陷查。"""
    src = _LIVE_VERIFY.read_text(encoding="utf-8")
    assert "known_data_state" in src, "报告未登记已知数据现状"
    assert "C24" in src, "未点明最大单份空骨架来源（C24 占 99.9%）"
    assert "数据治理" in src, "未说明清理属另一半径、本 spec 不做"
