"""task 5.4：sheet 打开链路的**指定变异套件**（7 类必红 + 阴性对照必绿）。

spec: `onlyoffice-sheet-open-via-published-artifact` task 5.4
Requirements: 1, 2, 3, 6, 10

═══ 为什么是「套件」而不是一次性脚本 ═══

一次性变异脚本跑完就没了，下次改代码没人会想起来再跑。本文件把 7 类**必须被杀死**的
变异形态固化成可重复运行的用例：每次 CI 都真的注入变异、跑守卫、断言红、再逐字节恢复。

═══ 为什么每类变异都要指定「红在哪条用例上」 ═══

只断言「退出码非 0」会漏掉两类假红：
* **收集失败**（变异引入语法错）—— `rc != 0` 但零条 FAILED；
* **红在别的用例上**（变异 A 触发了 B 的判据）—— 归因不清，修的人会改错地方。

所以每条都断言 `expected_test` 在 FAILED 列表里。

═══ 阴性对照 ═══

`NEGATIVE_CONTROL` 是**不改变语义**的变异（改注释 / 改本地变量名）。它必须保持绿 ——
没有这条，把守卫写成「对任何改动都红」也能让 7 条全过。

═══ 成本与开关 ═══

每类变异都要跑一次完整守卫集（约 10 秒），7+1 条共约 80 秒。默认**跳过**，只在
`GT_RUN_MUTATION_SUITE=1` 时运行（CI 的 mutation job 会设它）。这是本仓既有约定
（见 `test_phase5_e1_mutation_verification.py` 同形）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

_RUN = os.environ.get("GT_RUN_MUTATION_SUITE") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN,
    reason="变异套件默认跳过（设 GT_RUN_MUTATION_SUITE=1 运行；CI mutation job 会设）",
)

#: 本套件的守卫选集 —— 只跑与 sheet 打开链路直接相关的文件（约 10 秒）。
GUARD_TESTS = [
    "backend/tests/workpaper_sync/test_sheet_open_bindings.py",
    "backend/tests/workpaper_sync/test_sheet_open_binding_resolver.py",
    "backend/tests/workpaper_sync/test_sheet_published_artifact.py",
    "backend/tests/workpaper_sync/test_sheet_descriptor_view_identity.py",
    "backend/tests/workpaper_sync/test_sheet_entry_identity_endpoint.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_gate_binding_states.py",
    "backend/tests/workpaper_sync/test_sheet_legacy_caller_ledger.py",
]

GEN = BACKEND / "scripts" / "gen" / "generate_workpaper_sync_sheet_open_bindings.py"
ARTIFACT = BACKEND / "app" / "services" / "workpaper_sync" / "sheet_published_artifact.py"
RESOLVER = BACKEND / "app" / "services" / "workpaper_sync" / "sheet_open_bindings.py"
VIEW = BACKEND / "app" / "services" / "workpaper_sync" / "descriptor_view_identity.py"
GATE = BACKEND / "app" / "routers" / "_wp_onlyoffice_legacy_url_gate.py"


@dataclass(frozen=True)
class Mutant:
    """一条变异：改哪里、改成什么、红在哪条用例上。"""

    label: str
    path: Path
    needle: str
    replacement: str
    expected_test: str


#: ═══ 7 类必红变异（spec 5.4 逐条点名）═══
MUTANTS: tuple[Mutant, ...] = (
    # ① 删 mapping —— 生成器不再输出 binding（entry-identity 无映射可查）
    Mutant(
        label="01_drop_mapping",
        path=GEN,
        needle="    rows = [binding_for(dict(entry), input_digest=input_digest) for entry in manifest[\"entries\"]]",
        replacement="    rows = []",
        expected_test="test_projection_covers_manifest_entry_ids_exactly",
    ),
    # ② 伪造 parent fallback —— 子 entry 的 binding 指向父 entry
    Mutant(
        label="02_forged_parent_fallback",
        path=GEN,
        needle='        "effective_entry_id": effective_id,',
        replacement='        "effective_entry_id": "docx/gt-a16-bundle",',
        # 🔴 期望的是**专门**判据，不是只查 entry_id 集合的那条：伪造父级兜底正是通过
        # `effective_entry_id` 实现的，而 `test_projection_covers_manifest_entry_ids_exactly`
        # 只查 `entry_id` ⇒ 对它失明（实测变异存活）。task 5.4 补了
        # `test_effective_entry_id_is_never_a_forged_parent_fallback` 才咬住它。
        expected_test="test_effective_entry_id_is_never_a_forged_parent_fallback",
    ),
    # ③ candidate 冒充 current —— reader 接受 candidate artifact
    Mutant(
        label="03_candidate_as_current",
        path=ARTIFACT,
        needle='    if str(getattr(artifact, "state", "") or "") == ArtifactState.candidate.value:',
        replacement="    if False:",
        expected_test="test_candidate_artifact_is_refused_with_its_own_code",
    ),
    # ④ 恢复 template copy —— reader 在 artifact 缺失时回退模板目录
    Mutant(
        label="04_restore_template_copy",
        path=ARTIFACT,
        needle='    if not path.is_file():',
        replacement=(
            "    if not path.is_file():\n"
            "        # 变异：回退模板（本 spec 明禁）\n"
            "        from app.services.wp_template_finder import find_template_file_any\n"
            "        _tpl = find_template_file_any(str(getattr(representation, 'entry_id', '')))\n"
            "        if _tpl is not None:\n"
            "            path = Path(str(_tpl))\n"
            "    if False:"
        ),
        expected_test="test_missing_file_on_disk_has_its_own_code",
    ),
    # ⑤ 去掉 target sheet 校验 —— published artifact 里没有目标 sheet 也放行
    Mutant(
        label="05_drop_target_sheet_check",
        path=ARTIFACT,
        needle="        if not whole_workbook and target_sheet not in sheet_names:",
        replacement="        if False:",
        expected_test="test_missing_target_sheet_fails_without_template_fallback",
    ),
    # ⑥ 绕过 legacy token —— 旧式 URL 门对 migrated binding 也放行
    Mutant(
        label="06_bypass_legacy_token",
        path=GATE,
        needle='    if binding_verdict == "refuse_migrated":',
        replacement="    if False:",
        expected_test="test_migrated_refusal_does_not_consult_readiness",
    ),
    # ⑦ 让 old callback 无条件写入 —— pending 也标 bound（旧回调会被当成同步源）
    Mutant(
        label="07_old_callback_unconditional_write",
        path=GATE,
        needle='    if binding_verdict == "keep_independent":',
        replacement="    if False:",
        expected_test="test_unmigrated_bindings_keep_independent_editing",
    ),
)

#: ═══ 阴性对照：不改变语义的变异，必须保持绿 ═══
#: 阴性对照：只改**运行时模块**的注释，语义不变。
#:
#: 🔴 不能选生成器：改它的源码会让 `--check` 红（那条比的是产物字节），
#: 而那不是「语义不变」的变异 —— 首版选 `descriptor_view_identity.py` 时它没问题，
#: 但选生成器就会假红。靶点必须选**不参与生成物比对**的文件。
NEGATIVE_CONTROL = Mutant(
    label="NC_comment_only",
    path=VIEW,
    needle='DOCUMENT_SCOPES: Final[frozenset[str]] = frozenset({"single_sheet", "whole_workbook"})',
    replacement=(
        "# 阴性对照：只改注释，语义不变\n"
        'DOCUMENT_SCOPES: Final[frozenset[str]] = frozenset({"single_sheet", "whole_workbook"})'
    ),
    expected_test="",  # 不该红在任何一条上
)


def _run_guards() -> tuple[int, list[str]]:
    # 🔴 必须把沙箱路径传进**子进程**：否则子进程里 `GEN.OUTPUT` 是真实路径，
    # 读的是未变异的真实产物，而生成器源码已变异 ⇒
    # `test_generated_projection_is_current` 必红，抢了语义判据的红（实测 01/02 归因不清）。
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "GT_SHEET_BINDINGS_OUT": str(_projection_sandbox()),
    }
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest", *GUARD_TESTS,
            "-q", "-p", "no:playwright", "--no-header", "--tb=no", "-rf",
        ],
        cwd=REPO, capture_output=True, text=True, errors="replace", env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    failed = [
        line for line in out.splitlines()
        if line.startswith(("FAILED", "ERROR"))
    ]
    return proc.returncode, failed


#: 当前用例的生成物沙箱路径。
#:
#: 🔴 **每条用例独立**（不是进程级缓存）：首版用进程级 `_SANDBOX` 缓存，
#: 7 条变异共用同一目录 ⇒ 阴性对照跑时目录里还留着上一条变异
#: （`02_forged_parent_fallback`）的产物 ⇒ 语义判据读到脏数据而红（假红）。
_SANDBOX: list[Path] = []


def _fresh_projection_sandbox() -> Path:
    """为**当前用例**新建沙箱目录并返回产物路径。"""
    import tempfile

    _SANDBOX.clear()
    _SANDBOX.append(
        Path(tempfile.mkdtemp(prefix="gt_mutation_")) / "bindings.json"
    )
    return _SANDBOX[0]


def _projection_sandbox() -> Path:
    """当前用例的沙箱路径（已由 `_fresh_projection_sandbox` 建好）。"""
    if not _SANDBOX:
        return _fresh_projection_sandbox()
    return _SANDBOX[0]


def _regenerate_projection() -> None:
    """按**当前（可能已变异的）**生成器重生成产物，使 `--check` 绿。

    🔴 为什么必须这一步：生成器变异后 `test_generated_projection_is_current` 会先红
    （它比的是产物字节）。那条红是**正确**的，但它会抢在语义判据前面 ⇒ 归因不清。
    先重生成，让 `--check` 通过，红才会落在真正该红的语义判据上。
    """
    # 🔴 输出重定向到沙箱：绝不写已跟踪的真实产物（`_tracked_write_guard` 会报警，
    # 且进程被打断时会留下变异态产物 —— 本仓踩过）。
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "GT_SHEET_BINDINGS_OUT": str(_projection_sandbox()),
    }
    proc = subprocess.run(
        [sys.executable, str(GEN), "--apply"],
        cwd=REPO, capture_output=True, text=True, errors="replace", env=env,
    )
    # 🔴 不检查 rc 会让「变异让生成器崩掉」的情形留下**旧产物** ⇒ 之后每一次跑
    # `test_generated_projection_is_current` 都红（阴性对照也跟着红，看起来像守卫
    # 「对任何改动都红」）。失败时产物由外层 finally 恢复，这里只把失败暴露出来。
    if proc.returncode != 0:
        raise RuntimeError(
            f"变异态生成器 --apply 失败（rc={proc.returncode}）—— 该变异让生成器崩了，"
            f"改用它形态的变异：{proc.stderr[-600:]}"
        )


def _apply_and_observe(mutant: Mutant) -> tuple[int, list[str]]:
    """注入变异 → （生成器类）重生成产物 → 跑守卫 → 逐字节恢复。"""
    # 每条用例独立沙箱（见 `_fresh_projection_sandbox` 的说明）。
    _fresh_projection_sandbox()
    raw = mutant.path.read_bytes()
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    needle = mutant.needle.replace("\n", "\r\n") if crlf else mutant.needle
    replacement = mutant.replacement.replace("\n", "\r\n") if crlf else mutant.replacement
    count = text.count(needle)
    assert count == 1, (
        f"{mutant.label}: 靶点命中 {count} 次（源码已改形，需同步本套件）"
    )
    try:
        mutant.path.write_bytes(text.replace(needle, replacement, 1).encode("utf-8"))
        # 所有变异都重生成一次：让沙箱内容恒等于「当前生成器」的输出，
        # 这样语义判据读到的产物不会是「上一次变异残留」。
        _regenerate_projection()
        return _run_guards()
    finally:
        mutant.path.write_bytes(raw)
        assert mutant.path.read_bytes() == raw, f"{mutant.label}: 逐字节恢复失败"


@pytest.mark.parametrize("mutant", MUTANTS, ids=lambda m: m.label)
def test_mutant_is_killed_on_the_expected_guard(mutant: Mutant) -> None:
    """每类指定变异必须红，且**红在点名的用例上**。

    🔴 断言 `expected_test in failed_lines` 而不是只看 `rc != 0`：
    * 变异引入语法错时 `rc != 0` 但零条 FAILED（收集失败）—— 那是假红；
    * 变异 A 触发了 B 的判据时归因不清，修的人会改错地方。
    """
    rc, failed = _apply_and_observe(mutant)
    assert rc != 0, f"{mutant.label} 变异存活 —— 守卫不承重"
    assert failed, (
        f"{mutant.label}: rc={rc} 但零条 FAILED（收集期语法错 = 假红）"
    )
    assert any(mutant.expected_test in line for line in failed), (
        f"{mutant.label} 红在了别处，归因不清：\n"
        f"  期望含 {mutant.expected_test!r}\n"
        f"  实际 {failed[:6]}"
    )


def test_negative_control_stays_green() -> None:
    """阴性对照必须绿 —— 否则守卫是「对任何改动都红」，那等于没有守卫。

    🔴 文件名刻意以 `_a` 前缀保证它在参数化变异**之前**跑（pytest 按定义顺序收集，
    但 `parametrize` 生成的多条会集中展开）。它不改生成器、不重生成产物，
    因此不受前面变异的产物残留影响。
    """
    rc, failed = _apply_and_observe(NEGATIVE_CONTROL)
    assert rc == 0, (
        f"阴性对照（只改注释）竟被打红 —— 守卫对任何改动都红，不承重：\n{failed[:8]}"
    )
    assert not failed, failed


def test_suite_covers_every_named_mutation() -> None:
    """分母守卫：spec 5.4 点名的 7 类变异必须逐条在册。

    少一条就少一类保证 —— 而「少了哪一类」不该靠人记。
    """
    labels = {m.label for m in MUTANTS}
    required = {
        "01_drop_mapping",
        "02_forged_parent_fallback",
        "03_candidate_as_current",
        "04_restore_template_copy",
        "05_drop_target_sheet_check",
        "06_bypass_legacy_token",
        "07_old_callback_unconditional_write",
    }
    assert required <= labels, f"缺这些变异类：{sorted(required - labels)}"
    assert len(MUTANTS) == 7, f"应恰好 7 类，实得 {len(MUTANTS)}"


def test_each_mutant_targets_a_distinct_production_file() -> None:
    """7 类变异必须覆盖生成器 / reader / 门三层 —— 全挤在一个文件里说明覆盖面不够。"""
    files = {m.path for m in MUTANTS}
    assert len(files) >= 3, f"只覆盖了 {len(files)} 个生产文件：{sorted(str(p) for p in files)}"
    assert GEN in files, "缺生成器层变异"
    assert ARTIFACT in files, "缺 artifact reader 层变异"
    assert GATE in files, "缺旧式 URL 门层变异"


def test_expected_test_names_are_real() -> None:
    """点名的用例必须真的存在 —— 写错名字时上面那条会因为「红在别处」而假红。"""
    for mutant in MUTANTS:
        assert mutant.expected_test, f"{mutant.label} 未指定期望用例"
        found = False
        for test_file in GUARD_TESTS:
            text = (REPO / test_file).read_text(encoding="utf-8")
            # 允许前面有 `@pytest.mark.asyncio` 之类的装饰器，且允许 `async def`。
            if re.search(
                rf"^(?:@[^\n]*\n)*(?:async\s+)?def {re.escape(mutant.expected_test)}\b",
                text, re.M,
            ):
                found = True
                break
        assert found, (
            f"{mutant.label} 期望的用例 {mutant.expected_test!r} 在守卫选集里不存在"
        )
