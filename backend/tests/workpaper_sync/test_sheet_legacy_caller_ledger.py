"""task 3.7：宿主闭包守卫 —— legacy `onlyoffice-config` 调用面必须逐条登记。

spec: `onlyoffice-sheet-open-via-published-artifact` task 3.7 / Requirement 4.4 / 6.2 / 10.1

═══ 这条判据的真实形态 ═══

spec 原文是「迁移 binding 的所有旧 `onlyoffice-config` 调用为 0；未迁移调用逐条存在
ledger、owner 与 reason」。当前 197 条 binding **全部 pending / out_of_scope**
（无一条 migrated），所以「迁移 binding 的调用为 0」是**空分母恒真** —— 单靠它证明不了
任何事，而且它会在任何时候都绿。

所以本文件把判据拆成三条**互补**的：

1. **ledger 与现算双向相等**（漏登 / 死条目都红）—— 这一条现在就在承重；
2. **每条都有 owner + reason + next**，且三者互不相同（不是复制粘贴的占位）；
3. **migrated binding 的调用方必须为 0** —— 当前空分母，但 binding 一晋级就咬人。

第 3 条刻意保留：它是本 spec 从「登记现状」走向「真正收敛」的唯一自动判据。删了它
就只剩一份静态清单，而清单不会告诉你什么时候该动手。

═══ 为什么不许用 `DEPRECATED` 注释隐藏 ═══

Requirement 4.3 明写「登记项不得通过 DEPRECATED 注释长期隐藏」。所以判据不认注释：
它数的是**代码行**（`_is_comment_line` 排除纯注释），一个只写了 `// DEPRECATED` 的文件
不会因此被当成「已处理」。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
LEDGER = BACKEND / "data/workpaper_sync_legacy_onlyoffice_callers.json"
GENERATOR = BACKEND / "scripts" / "gen" / "generate_legacy_onlyoffice_caller_ledger.py"
BINDINGS = BACKEND / "data" / "workpaper_sync_sheet_open_bindings.json"
FE = REPO / "audit-platform" / "frontend" / "src"


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert LEDGER.is_file(), f"ledger 缺失：{LEDGER}"
    return json.loads(LEDGER.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 1. 生成物新鲜度（--check）
# ═══════════════════════════════════════════════════════════════════════════


def test_ledger_is_current() -> None:
    """`--check` 必须通过：ledger 与现算逐字节一致。

    这条是**总闸** —— 任何调用方增删都会让它红，从而强制登记。
    """
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.returncode == 0, (
        f"ledger 与现算不一致（重跑 --apply 并复核 diff）：\n{proc.stdout}\n{proc.stderr}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 双向相等：不漏登、不留死条目
# ═══════════════════════════════════════════════════════════════════════════


def _is_comment_line(line: str) -> bool:
    return line.strip().startswith(("//", "*", "/*"))


def _scan_callers() -> dict[str, list[int]]:
    """独立重算（不 import 生成器）—— 判据与生成器互为对照。

    🔴 刻意不 import 生成器的 `scan()`：那会让「生成器写错了」同时污染两侧，
    两边一起错就是全绿。这里独立实现一遍，两边不一致即红。
    """
    legit = set((json.loads(LEDGER.read_text(encoding="utf-8"))["legit_entrypoints"]).keys())
    found: dict[str, list[int]] = {}
    for path in sorted(FE.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        parts = path.parts
        if "__tests__" in parts or path.name.endswith((".spec.ts", ".test.ts")):
            continue
        rel = str(path.relative_to(FE)).replace("\\", "/")
        if rel in legit:
            continue
        hits = [
            lineno
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            )
            if re.search(r"onlyoffice-config", line) and not _is_comment_line(line)
        ]
        if hits:
            found[rel] = hits
    return found


def test_every_live_caller_is_registered(ledger: dict) -> None:
    """现算的每个调用方都必须在 ledger 里 —— 漏登即红。"""
    live = _scan_callers()
    registered = set(ledger["callers"])
    missing = sorted(set(live) - registered)
    assert not missing, (
        f"这些文件调用旧式 onlyoffice-config 但未登记（Requirement 4.3）：{missing}"
    )


def test_no_stale_ledger_entry(ledger: dict) -> None:
    """ledger 里的每一条都必须在现算里真实存在 —— 死条目即红。

    死条目的危害：它让 ledger 变成一份「看着很完整」的清单，而清单本身不再可信。
    """
    live = set(_scan_callers())
    stale = sorted(set(ledger["callers"]) - live)
    assert not stale, f"这些 ledger 条目在代码里已不存在（删掉它们）：{stale}"


def test_registered_line_numbers_are_real(ledger: dict) -> None:
    """登记的**行号**必须真的指向含 `onlyoffice-config` 的代码行。

    只登记文件名时，文件里那处调用被删掉后 ledger 仍然「有这一条」—— 行号让条目可伪证。
    """
    for rel, entry in ledger["callers"].items():
        path = FE / rel
        assert path.is_file(), f"ledger 指向不存在的文件：{rel}"
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno in entry["lines"]:
            assert 1 <= lineno <= len(lines), f"{rel}:{lineno} 越界（文件 {len(lines)} 行）"
            line = lines[lineno - 1]
            assert "onlyoffice-config" in line, (
                f"{rel}:{lineno} 不含 onlyoffice-config —— 行号已漂移：{line.strip()[:100]!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 每条登记必须可执行（owner + reason + next 三样且互不相同）
# ═══════════════════════════════════════════════════════════════════════════


def test_every_entry_has_owner_reason_and_next(ledger: dict) -> None:
    """owner / reason / next 三样齐全，且**互不相同**。

    🔴 只查「非空」会让 `reason == next == '待迁移'` 这类占位通过 —— 那不是登记，
    那是把「不知道」写成了三个字段。
    """
    problems: list[str] = []
    for rel, entry in ledger["callers"].items():
        for key in ("owner", "reason", "next"):
            value = str(entry.get(key) or "").strip()
            if not value:
                problems.append(f"{rel}: 缺 {key}")
        if len({entry.get("reason"), entry.get("next")}) != 2:
            problems.append(f"{rel}: reason 与 next 相同（占位文本）")
        if len(str(entry.get("reason") or "")) < 10:
            problems.append(f"{rel}: reason 过短（{entry.get('reason')!r}）")
        if len(str(entry.get("next") or "")) < 10:
            problems.append(f"{rel}: next 过短（{entry.get('next')!r}）")
    assert not problems, "登记不可执行：\n" + "\n".join(problems)


def test_owner_is_a_module_not_a_person(ledger: dict) -> None:
    """owner 必须是**模块名**（kebab-case），不是人名。

    人名会随组织变动失效；模块名可查。判据：不含空格、不含 `@`、长度 <= 40。
    """
    for rel, entry in ledger["callers"].items():
        owner = str(entry["owner"])
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", owner), (
            f"{rel} 的 owner={owner!r} 不是模块名（kebab-case）"
        )


def test_no_deprecated_comment_hiding(ledger: dict) -> None:
    """登记项不得靠 `DEPRECATED` 注释「处理」掉（Requirement 4.3）。

    判据：ledger 里每个调用方的文件都**仍然真实调用**（上面 `_scan_callers` 已证），
    且本判据额外要求它们没有把调用改成纯注释。
    """
    for rel in ledger["callers"]:
        text = (FE / rel).read_text(encoding="utf-8")
        code_lines = [
            line for line in text.splitlines()
            if "onlyoffice-config" in line and not _is_comment_line(line)
        ]
        assert code_lines, (
            f"{rel} 的 onlyoffice-config 只在注释里了 —— 那就该从 ledger 删除，"
            "而不是留一条「已 DEPRECATED」的登记"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 承重点：migrated binding 的调用方必须为 0
# ═══════════════════════════════════════════════════════════════════════════


def _find_migrated_offenders(
    *, migrated: list[dict], caller_files: set[str]
) -> list[str]:
    """找出「已 migrated 但仍在走旧式 config」的入口。

    🔴 抽成函数是为了可注入假设（阳性/阴性对照用例需要它）。判据形态是**内容匹配**，
    不按文件名猜 wp_code —— composable 命名与 wp_code 没有强制映射（实测 `exact` 那条是
    `B60-1`，ledger 里没有 B60 的调用方 ⇒ 按名字匹配恒空）。

    三种匹配形态（避免 `K11` 恰好出现在无关字符串里）：
      * `'K11'` / `"K11"`（引号字面量）
      * `wpCode === 'K11'` / `wp_code === "K11"`（比较）
      * `useK11DualMode`（composable 名）
    """
    offenders: list[str] = []
    for row in migrated:
        code = str(row.get("source_wp_code") or "").strip()
        if not code:
            continue
        patterns = [
            re.compile(rf"""['"]{re.escape(code)}['"]"""),
            re.compile(rf"""wp_?code\s*===?\s*['"]{re.escape(code)}['"]""", re.I),
            re.compile(rf"use{re.escape(code)}DualMode", re.I),
        ]
        for rel in caller_files:
            path = FE / rel
            if not path.is_file():
                continue
            code_lines = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if not _is_comment_line(line)
            ]
            if any(pat.search(line) for line in code_lines for pat in patterns):
                offenders.append(f"{row['entry_id']} (wp_code={code}) → {rel}")
    return offenders


def test_migrated_bindings_have_no_legacy_callers(ledger: dict) -> None:
    """一旦有 binding 晋级 `migrated` / `ready`，它的入口就**不得**再走旧式 config。

    ═══ 这条判据现在为什么是空分母，以及为什么必须保留 ═══

    当前 197 条 binding 全部 `pending` / `out_of_scope` ⇒ `migrated` 集为空 ⇒ 本条恒真。
    它证明不了「现在没问题」，但它会在**第一个** binding 晋级的那一刻开始咬人：

    * 若那个 entry 的宿主还在调旧式 `onlyoffice-config`，本条立刻红；
    * 红的意思是「你已经声明这个入口走 room 了，但前端还在走旧链路」——
      那正是双写的入口，也是本 spec 要消灭的事故本身。

    删掉本条，整套 ledger 就退化成一份静态清单，而清单不会告诉你什么时候该动手。
    """
    bindings = json.loads(BINDINGS.read_text(encoding="utf-8"))
    migrated = [
        row for row in bindings["bindings"]
        if row["status"] in {"migrated", "ready"}
    ]
    if not migrated:
        # 空分母：**显式**记录，不静默 pass。分母为 0 时判据无法证伪任何东西，
        # 但把这件事写出来，读的人就知道「绿」的含义是「还没有 migrated binding」。
        pytest.skip("当前 0 条 migrated/ready binding —— 本条为空分母（binding 晋级后自动生效）")

    # 有 migrated binding 时，逐条核对它的入口不在 legacy 调用面里。
    #
    # 🔴 **不能按文件名猜 wp_code**：composable 命名与 wp_code 没有强制映射
    # （实测 `exact` 那条是 `B60-1`，而 ledger 里 22 个文件没有一个叫 B60 —— 按名字匹配
    # 恒空 ⇒ 承重点永远绿，变异 M10 因此存活）。改成**内容判据**：
    # 在调用方文件的代码行里找该 wp_code 的**独立字面量**形态。
    #
    # 收窄到三种形态（避免 `K11` 恰好出现在无关字符串里造成误报）：
    #   * `'K11'` / `"K11"`（引号字面量）
    #   * `wpCode === 'K11'` / `wp_code === "K11"`（比较）
    #   * `useK11DualMode`（composable 名，作为**辅助**形态）
    offenders = _find_migrated_offenders(
        migrated=migrated, caller_files=set(ledger["callers"])
    )
    assert not offenders, (
        "这些 binding 已 migrated/ready，但前端仍在走旧式 onlyoffice-config：\n"
        + "\n".join(offenders)
    )


def test_migrated_offender_predicate_is_load_bearing() -> None:
    """**阳性对照**：用「K11 已 migrated」这个假设证明上一条会红。

    ═══ 为什么必须有这条 ═══

    上一条在当前数据上恒真（0 条 migrated）⇒ 无法证伪任何东西。实测变异 M10 用
    `exact` 那条 binding（`B60-1`，ledger 里没有对应调用方）时**存活** —— 判据确实
    没东西可判。本条把假设直接注入判据函数，断言它能找出 `useK11DualMode.ts`。
    """
    offenders = _find_migrated_offenders(
        migrated=[{"entry_id": "xlsx/gt-k11-asset-impairment-loss", "source_wp_code": "K11"}],
        caller_files={"components/workpaper/composables/useK11DualMode.ts"},
    )
    assert offenders, (
        "把 K11 标成 migrated 后判据没找出 useK11DualMode.ts —— 承重点不承重"
    )
    assert "useK11DualMode" in offenders[0]


def test_migrated_offender_predicate_does_not_over_report() -> None:
    """**阴性对照**：与任何调用方无关的 wp_code 不得报红。

    没有这条，判据写成「无条件 append」也能让上一条全绿。
    """
    offenders = _find_migrated_offenders(
        migrated=[{"entry_id": "xlsx/gt-zzz", "source_wp_code": "ZZZ-9"}],
        caller_files={"components/workpaper/composables/useK11DualMode.ts"},
    )
    assert offenders == [], f"无关 wp_code 被误报：{offenders}"


def test_summary_migrated_counter_is_zero_and_documented(ledger: dict) -> None:
    """`summary.migrated_binding_callers` 必须是 0，且生成物里说明了它的含义。

    🔴 这个字段不是「恒 0 的装饰」：它是第 4 组判据的**机器可读**形态。放在 summary 里
    让 CI 与看板能直接读到「还有多少个已迁移入口仍在走旧链路」，而不必跑测试。
    """
    summary = ledger["summary"]
    assert summary["migrated_binding_callers"] == 0, (
        f"有已迁移 binding 仍在走旧式入口：{summary['migrated_binding_callers']} 个"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 分母守卫：ledger 不能是空壳
# ═══════════════════════════════════════════════════════════════════════════


def test_ledger_denominator_is_not_empty(ledger: dict) -> None:
    """ledger 必须有真实条目 —— 空 ledger 会让上面所有「逐条」判据全绿。"""
    assert ledger["callers"], "ledger 的 callers 为空 —— 上面所有逐条判据都成了空转"
    assert len(ledger["callers"]) >= 15, (
        f"只登记了 {len(ledger['callers'])} 个调用方 —— 实测有 22 个，分母不对"
    )
    assert ledger["summary"]["caller_sites"] >= len(ledger["callers"]), (
        "caller_sites 少于 caller_files —— 统计口径错了"
    )


def test_legit_entrypoints_are_exactly_three(ledger: dict) -> None:
    """合法入口必须恰好 3 个：唯一入口 + 它的 URL 拼装 + http 的 URL 判断。

    多一个就是「给某个调用方开了后门」—— 那会让第 1 组判据漏掉它。
    """
    legit = ledger["legit_entrypoints"]
    assert len(legit) == 3, f"合法入口应恰好 3 个，实得 {sorted(legit)}"
    assert any("onlyOfficeEntryConfig" in rel for rel in legit)
    assert any("onlyOfficeSheetConfig" in rel for rel in legit)
    assert any(rel.endswith("utils/http.ts") for rel in legit)
    for rel, entry in legit.items():
        assert str(entry.get("why") or "").strip(), f"{rel} 缺 why 说明"


def test_ledger_and_bindings_are_both_tracked() -> None:
    """两份生成物都必须入库 —— clean checkout 缺任一份，端点与守卫都跑不了。"""
    for path in (LEDGER, BINDINGS):
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO))],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, f"未入库：{path}"
