"""Task 66 可收缩执行账的守卫（spec task 5.5 / AC 1.7, 12.9）。

守的四件事，与 task 5.5 的三条要求一一对应：

1. **已满足 entry 必须进物理删除** —— `eligible_now` 非空时账必须红，逼迫真删；
   反过来，只要还有 live BP，`eligible_now` 必须为空（fail closed，不是豁免）。
2. **失效项自动移除** —— `landed`（已不在盘上）不得出现在 outstanding / eligible 里。
3. **计划外 legacy 新增立即打红** —— `unplanned_legacy_paths` 必须为空。
4. **棘轮只减** —— `outstanding_paths` 不得超过基线。基线写在**本文件**里而不是产物里：
   写在产物里的话，重跑 `--write` 就能把基线抬上去，棘轮就成了装饰。

另外守两条「判据本身别坏掉」：产物必须幂等（无时间戳 ⇒ `--write` + `git diff` 式门禁
不会永红），legacy 判据必须与冻结生成器**同一个对象**（防止判据分叉成两份）。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
_GEN_DIR = _BACKEND / "scripts" / "gen"

LEDGER_PATH = _BACKEND / "data" / "workpaper_sync_task66_execution_ledger.json"
LEDGER_GENERATOR = _GEN_DIR / "generate_task66_execution_ledger.py"
FROZEN_PLAN_PATH = _BACKEND / "data" / "workpaper_sync_task66_legacy_deletion_plan.json"

#: 🔴 outstanding 棘轮基线。2026-11-01 现算 97（= 125 个 pending_delete path 里 28 个已
#: landed 出账）。**只许下调**：每删一批就把这个数改小，永远不要为了让守卫变绿而上调。
#: 上调等于把「可收缩执行账」变成「可膨胀执行账」。
_OUTSTANDING_RATCHET = 97

#: 棘轮基线不得虚高：它必须贴着现算值，不能预留一大截空间（预留空间 = 静默容许回弹）。
_RATCHET_SLACK_CAP = 5


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert LEDGER_PATH.is_file(), (
        f"{LEDGER_PATH.name} 不在 —— 先跑 "
        "`python backend/scripts/gen/generate_task66_execution_ledger.py --write`"
    )
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger_module():
    spec = importlib.util.spec_from_file_location("t66ledger", LEDGER_GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 带 dataclass / 注解解析的模块必须先登记再 exec，否则解析注解时拿不到模块字典
    sys.modules["t66ledger"] = module
    for extra in (str(_BACKEND), str(_GEN_DIR)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    spec.loader.exec_module(module)
    return module


# ═══════════════════════════════════════════════════════════════════════
# task 5.5 的三条要求
# ═══════════════════════════════════════════════════════════════════════


def test_eligible_entries_must_not_sit_undeleted(ledger: dict) -> None:
    """已满足释放条件的 entry 不得继续留在盘上。

    这条是 5.5「已满足 entry 必须从 pending 进入物理删除并重验」的门。它红的时候**不是**
    让你改断言，是让你真去删那些文件。
    """
    eligible = ledger["eligibility"]["eligible_now_paths"]
    assert eligible == [], (
        f"{len(eligible)} 条 outstanding 已满足释放条件却还在盘上，必须物理删除并重验："
        f"{eligible[:10]}"
    )


def test_live_blockers_force_zero_eligibility(ledger: dict) -> None:
    """还有 live BP 时 eligible 必须为空 —— fail closed，不是豁免。"""
    live = ledger["live_blocking_point_ids"]
    eligible_count = ledger["eligibility"]["eligible_now_count"]
    if live:
        assert eligible_count == 0, (
            f"live BP {live} 仍成立，却报出 {eligible_count} 条 eligible —— "
            "前置未满足时不得放行删除"
        )
    else:
        # 全部 BP 都释放了 ⇒ eligible 必须等于 outstanding，不许悄悄缩小分母
        assert eligible_count == ledger["counters"]["outstanding_paths"], (
            "全部 BP 已释放，eligible 必须等于 outstanding —— 分母被缩小了"
        )


def test_landed_paths_are_auto_removed_from_outstanding(ledger: dict) -> None:
    """`landed` = 已不在盘上 ⇒ 自动出账，不得计入 outstanding 或 eligible。"""
    landed = {row["path"] for row in ledger["paths"] if row["state"] == "landed"}
    assert landed, "landed 为空 —— 若计划里真有已删项，说明三态现算没生效（结构性零）"

    eligible = set(ledger["eligibility"]["eligible_now_paths"])
    assert not (landed & eligible), f"已删的 path 又被算成 eligible：{sorted(landed & eligible)}"

    # landed 的行不得声称自己还有当前内容
    for row in ledger["paths"]:
        if row["state"] == "landed":
            assert row["current_sha256"] is None, f"{row['path']} 已 landed 却带 current_sha256"

    counters = ledger["counters"]
    assert (
        counters["outstanding_paths"]
        == counters["pending_delete_paths"] - counters["pending_delete_landed"]
    ), "outstanding 不等于 pending_delete 减去已 landed 的 —— 自动出账口径不自洽"


def test_no_unplanned_legacy_object_on_disk(ledger: dict) -> None:
    """计划外的 legacy 对象立即打红 —— 新增 legacy 不许绕过计划。"""
    unplanned = ledger["unplanned_legacy_paths"]
    assert unplanned == [], (
        f"现盘有 {len(unplanned)} 个计划外 legacy 对象，必须登记进计划或当场删掉："
        f"{unplanned[:10]}"
    )


def test_outstanding_ratchet_only_shrinks(ledger: dict) -> None:
    outstanding = ledger["counters"]["outstanding_paths"]
    assert outstanding <= _OUTSTANDING_RATCHET, (
        f"outstanding 从 {_OUTSTANDING_RATCHET} 涨到 {outstanding} —— 执行账只许收缩。"
        "新增 legacy 必须在引入时就删掉，不许进账"
    )


def test_ratchet_baseline_is_not_inflated(ledger: dict) -> None:
    """基线必须贴着现算值 —— 预留空间等于静默容许回弹。"""
    outstanding = ledger["counters"]["outstanding_paths"]
    slack = _OUTSTANDING_RATCHET - outstanding
    assert slack <= _RATCHET_SLACK_CAP, (
        f"棘轮基线 {_OUTSTANDING_RATCHET} 比现算 {outstanding} 高出 {slack} —— "
        f"超过允许的 {_RATCHET_SLACK_CAP}，请把基线下调到现算值"
    )


# ═══════════════════════════════════════════════════════════════════════
# 判据本身别坏掉
# ═══════════════════════════════════════════════════════════════════════


def test_ledger_reuses_frozen_generator_predicate(ledger_module) -> None:
    """legacy 判据必须与冻结生成器**同一个对象**，不得各写一份。

    判据分叉过一次就会永久分叉：两边各自演化，谁也说不清哪个是对的。
    """
    frozen = ledger_module.frozen_plan
    assert (
        ledger_module.frozen_plan._LEGACY_COMPOSABLE_NAME
        is frozen._LEGACY_COMPOSABLE_NAME
    )
    # 执行账不得自己定义一份同名正则
    source = LEDGER_GENERATOR.read_text(encoding="utf-8")
    assert "_LEGACY_COMPOSABLE_NAME = re.compile" not in source, (
        "执行账自己定义了 legacy 正则 —— 必须复用冻结生成器的那一个"
    )


def test_ledger_output_is_idempotent(ledger: dict) -> None:
    """产物不得含时间戳等每次都变的字段。

    `--write` + `git diff --exit-code` 式门禁遇到时间戳必然永红，而永红门禁等于没门禁
    （本仓库已因此吃过一次漂移：note-section-map 的注册表门长期全红）。
    """
    blob = json.dumps(ledger, ensure_ascii=False)
    forbidden = ("generated_at", "snapshot_date", "elapsed_seconds", "checked_at")
    for key in forbidden:
        assert f'"{key}"' not in blob, f"产物含易变字段 {key} —— 会让幂等门禁永红"
    # ISO 时间戳字面量同样不许出现
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", blob), (
        "产物含 ISO 时间戳 —— 同上"
    )


def test_ledger_check_mode_passes_and_reports_counters() -> None:
    """`--check` 必须真的通过，并且**真的读到了输出**。

    🔴 只断言 returncode 会假绿：Windows 子进程 piped stdout 默认 gbk，中文按 utf-8 解码
    失败时 `subprocess.run` 不会失败，只把 stdout 变成 None 并留一条线程异常警告。
    所以这里同时断言 stdout 里有预期内容。
    """
    import os

    proc = subprocess.run(
        [sys.executable, str(LEDGER_GENERATOR), "--check"],
        cwd=str(_REPO),
        capture_output=True,
        # 🔴 `text=True` 会按**本机 locale**（Windows 上是 gbk）解码，子进程写的 utf-8 中文
        # 会变成乱码，于是「输出里有没有这句话」的断言永假。必须显式 encoding="utf-8"；
        # 光设 PYTHONIOENCODING 只管子进程**写**的那一端，管不了父进程**读**的那一端。
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=900,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"`--check` 未通过：{out[-600:]}"
    assert "逐字节一致" in out, f"`--check` 没输出比对结论 —— 可能根本没读到 stdout：{out[-400:]}"
    assert "outstanding_paths" in out, "`--check` 没打印 counters"


def test_frozen_plan_digest_matches_recorded(ledger: dict) -> None:
    """账里记的冻结计划 digest 必须等于磁盘上那份 —— 这是「冻结产物真的没再变」的断言。"""
    import hashlib

    actual = hashlib.sha256(FROZEN_PLAN_PATH.read_bytes()).hexdigest()
    assert ledger["frozen_inputs"]["plan_digest"] == actual, (
        "冻结计划变了但执行账没重生成 —— 重跑 `--write` 并复核 diff"
    )


def test_retired_generator_is_not_wired_into_any_gate() -> None:
    """退役的冻结生成器不得留在门禁里当永红项。

    它现在跑不通（owner 校验把 Wave-6 任务号对当前 tasks.md 比对），留在门禁里就是永红。
    要断言的是「冻结产物没再变」，由 `test_frozen_plan_digest_matches_recorded` 承担。
    """
    needle = "generate_task66_legacy_deletion_plan.py"
    offenders: list[str] = []
    for rel in (
        ".github/workflows/ci.yml",
        ".github/workflows/governance-checks.yml",
        ".pre-commit-config.yaml",
        ".git-hooks/pre-commit",
        ".git-hooks/pre-push",
    ):
        path = _REPO / rel
        if not path.is_file():
            continue
        if needle in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(rel)
    assert offenders == [], (
        f"退役生成器仍被这些门禁引用，会长期全红：{offenders} —— "
        "改引用执行账的 `--check`"
    )


def test_states_are_closed_and_every_path_has_one(ledger: dict) -> None:
    """三态封闭，且每条 path 恰好一个态 —— 防止出现第四种「说不清」的状态。"""
    allowed = set(ledger["state_vocabulary"])
    assert allowed == {"landed", "drifted", "intact"}
    seen: dict[str, int] = {}
    for row in ledger["paths"]:
        assert row["state"] in allowed, f"{row['path']} 的态 {row['state']} 不在封闭集合里"
        seen[row["path"]] = seen.get(row["path"], 0) + 1
    duplicated = sorted(p for p, n in seen.items() if n > 1)
    assert not duplicated, f"同一 path 出现多次：{duplicated[:5]}"
    counters = ledger["counters"]
    assert counters["plan_paths_total"] == len(ledger["paths"])
    assert (
        counters["state_landed"] + counters["state_drifted"] + counters["state_intact"]
        == counters["plan_paths_total"]
    ), "三态计数之和不等于总数"


def test_drifted_paths_are_flagged_for_reverdict(ledger: dict) -> None:
    """内容变了的条目必须被标成「需重判」，不得静默沿用计划里的裁决。"""
    drifted = [row for row in ledger["paths"] if row["state"] == "drifted"]
    assert drifted, "drifted 为空 —— 若真有文件内容变了，说明 sha 比对没生效"
    for row in drifted:
        assert row["current_sha256"] and row["planned_sha256"]
        assert row["current_sha256"] != row["planned_sha256"], (
            f"{row['path']} 标成 drifted 但两个 sha 相同"
        )
    counters = ledger["counters"]
    assert counters["outstanding_drifted_need_reverdict"] == sum(
        1
        for row in drifted
        if "pending_delete" in row["dispositions"] and row["state"] != "landed"
    ), "需重判计数与 drifted 行不一致"
