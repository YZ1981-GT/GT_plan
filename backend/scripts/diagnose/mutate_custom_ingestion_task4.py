"""Task 4 变异检验：破坏 multipart 摄取 / private quarantine 关键点，确认守卫真会红。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7, 6.1, 6.7

用法：
    python scripts/diagnose/mutate_custom_ingestion_task4.py --check-anchors   # 只读，秒级
    python scripts/diagnose/mutate_custom_ingestion_task4.py --apply           # 逐条打补丁+复原

🔴 不看退出码下结论：区分 RED（真打红预期项）/ GREEN（守卫缺陷）/
   ANCHOR-MISS（脚本缺陷：锚点未命中或命中 >1）/ WRONG-TEST（打红了但不是
   预期项 = 污染残留或锚点错行）。

锚点约定（与 Task 2/3 一致）：一律**单行**行首锚定正则 —— 多行锚点在 CRLF/
换行归一化下极易 MISS，而单行锚点唯一且短。
🔴 正则特殊字符必须转义：``(`` ``)`` ``{`` ``}`` ``[`` ``]`` ``|`` ``.``。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: .../backend/scripts/diagnose/x.py → repo root
ROOT = Path(__file__).resolve().parents[3]
QUA = ROOT / "backend/app/services/custom_template_ingestion/quarantine.py"
ROUTER = ROOT / "backend/app/routers/custom_template_ingestion.py"

PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_quarantine.py",
    "tests/custom_template_ingestion/test_ingestion_routes.py",
    "-q", "-p", "no:randomly",
    "--tb=line",
]
PYTEST_CWD = ROOT / "backend"

# 🔴 字节级捕获 + 显式 UTF-8：Windows 默认 GBK 会在 pytest 的中文输出上
# UnicodeDecodeError，导致 stdout=None、变异判据静默失效。
ENVPATCH: dict[str, str] = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    """一条变异。

    file: 被改文件；anchor: 行首锚定单行正则（re.MULTILINE，必须恰好命中 1 次）；
    replacement: 替换文本；wants: 预期变红的测试名。
    """

    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    requirement: str


CASES: list[Case] = [
    # ── Requirement 3.1：绕过扩展名白名单（不写任何字节直接落盘）──
    # 🔴 变异点是「白名单判定的返回」而非删掉整段 —— 后者会让测试以不同
    # 错误失败，掩盖守卫缺陷。把判定恒为 True，等于允许 malware.exe 进隔离区。
    Case(
        id="M1-bypass-extension-whitelist",
        file=QUA,
        anchor=r"^    return extension_of\(raw\) in ALLOWED_EXTENSIONS$",
        replacement="    return True",
        wants=("test_ingest_rejects_non_allowed_extension_without_writing_bytes",),
        requirement="3.1",
    ),
    # ── Requirement 3.2：放行非 ZIP magic（非 Excel 字节进隔离区）──
    # 破坏的是「magic 校验的比较方向」，让任意字节都通过。
    Case(
        id="M2-accept-non-zip-magic",
        file=QUA,
        anchor=r"^        if bytes_path\.read_bytes\(\)\[:4\] != ZIP_MAGIC:$",
        replacement="        if False:",
        wants=("test_ingest_rejects_non_zip_magic",),
        requirement="3.2",
    ),
    # ── Requirement 3.1：storage key 与输入文件名关联（路径穿越/同名覆盖）──
    # 把 artifact_id 换成由文件名派生的值，让 relative_path 含用户输入。
    Case(
        id="M3-storage-key-derived-from-filename",
        file=QUA,
        anchor=r"^        artifact_id = uuid\.uuid4\(\)\.hex$",
        replacement='        artifact_id = display_filename(source.filename).casefold().replace(".", "-")',
        wants=("test_storage_key_never_contains_user_input",),
        requirement="3.1",
    ),
    # ── Requirement 3.6：manifest 携带 valid 布尔（空报告 valid 的变体）──
    # 拒绝产物不得有 valid 字段；把它加回去会同时击穿
    # test_rejected_artifact_carries_rejection_not_valid_flag 与
    # test_ingest_stream_handles_multichunk_without_buffering_all。
    Case(
        id="M4-rejected-artifact-carries-valid-flag",
        file=QUA,
        anchor=r'^            "previousState": self\.previous_state\.value if self\.previous_state else None,$',
        replacement=('            "previousState": self.previous_state.value if self.previous_state else None,\n'
                     '            "valid": self.state.value in {"QUARANTINED", "PREFLIGHT_READY"},'),
        wants=(
            "test_rejected_artifact_carries_rejection_not_valid_flag",
            "test_ingest_stream_handles_multichunk_without_buffering_all",
        ),
        requirement="3.6",
    ),
    # ── Requirement 6.1：终态枚举混入 publication 状态（跨域混合表达）──
    # 加 ACTIVE 会让 test_state_machine_is_closed_to_quarantine_domain 红。
    Case(
        id="M5-state-enum-mixes-in-publication-state",
        file=QUA,
        anchor=r'^    EXPIRED = "EXPIRED"$',
        replacement='    EXPIRED = "EXPIRED"\n    ACTIVE = "ACTIVE"',
        wants=("test_state_machine_is_closed_to_quarantine_domain",),
        requirement="6.1",
    ),
    # ── Requirement 6.7：TTL 判定改走真实墙钟（注入时钟失效）──
    # 把 _utc_now(clock) 换成 datetime.now()，不动时钟也能清理 → 测不出过期。
    Case(
        id="M6-ttl-uses-wall-clock-not-injected-clock",
        file=QUA,
        anchor=r"^        now = _utc_now\(self\._clock\)$",
        replacement="        now = datetime.now(timezone.utc)",
        wants=("test_cleanup_expired_uses_injected_clock_not_wall_clock",),
        requirement="6.7",
    ),
    # ── Requirement 1.4：/actions 遍历三条 action 时崩溃（fail-hard）──
    # 把「无 capability 门槛 = 可见」改成恒 False，则三条 action 全被过滤 →
    # GET /actions 返回空列表，UI 列不出任何入口（Requirement 1.4 入口发现失效）。
    # 🔴 变异目标文件是 **router**，不是 quarantine service —— 分层不同，
    # 故此 Case 的 file 单独指向 ROUTER。
    Case(
        id="M7-actions-endpoint-hides-all-actions",
        file=ROUTER,
        anchor=r"^        if required is None or is_permitted\(role, required\):$",
        replacement="        if False:",
        wants=("test_three_actions_have_distinct_ids_and_binary_semantics",),
        requirement="1.4",
    ),
]


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    """只读校验：每条锚点必须命中且仅命中 1 次。"""
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        try:
            n = _count_matches(text, case.anchor)
        except re.error as exc:
            print(f"  [ANCHOR-MISS] {case.id} 正则非法: {exc}")
            bad += 1
            continue
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})")
    print(f"\nANCHOR-MISS 条数: {bad}/{len(CASES)}")
    return 1 if bad else 0


def run_pytest() -> tuple[int, bytes]:
    """返回 (exit code, stdout 字节)。cwd=backend（pytest rootdir）。"""
    proc = subprocess.run(
        PYTEST_ARGS, cwd=str(PYTEST_CWD), capture_output=True, env=ENVPATCH,
    )
    return proc.returncode, proc.stdout


def apply_one(case: Case) -> str:
    """对单条变异打补丁并复原，返回四态结论。"""
    text = case.file.read_text(encoding="utf-8")
    n = _count_matches(text, case.anchor)
    if n != 1:
        return f"{case.id}: ANCHOR-MISS (n={n})"
    new_text, cnt = re.subn(case.anchor, case.replacement, text, count=1,
                            flags=re.MULTILINE)
    if cnt != 1:
        return f"{case.id}: ANCHOR-MISS (subn={cnt})"

    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_pytest()
        if rc == 0:
            return (f"{case.id}: GREEN ✗ —— 守卫缺陷！破坏 Requirement "
                    f"{case.requirement} 后测试仍全绿")
        out_str = out.decode("utf-8", errors="replace")
        hit = [w for w in case.wants if w in out_str]
        if len(hit) != len(case.wants):
            failed = [l for l in out_str.splitlines() if "FAILED" in l][:5]
            return (f"{case.id}: WRONG-TEST ✗ —— 预期项 {case.wants} 未全部打红；"
                    f"实际: {failed}")
        return f"{case.id}: RED ✓ —— 预期项 {hit} 全部变红"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.check_anchors:
        return check_anchors()

    if not args.apply:
        print(__doc__)
        return 0

    rc, out = run_pytest()
    if rc != 0:
        print(f"✗ 基线不绿 (rc={rc})，先修守卫再跑变异")
        print(out.decode("utf-8", errors="replace")[-2000:])
        return 1
    print("✓ 基线全绿\n")

    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "✗" in result:
            bad += 1
    print(f"\n守卫缺陷/脚本缺陷条数: {bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
