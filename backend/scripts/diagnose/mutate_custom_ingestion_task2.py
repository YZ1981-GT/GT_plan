"""Task 1–2 变异检验：破坏关键点，确认守卫真会红。

Spec: custom-workpaper-template-ingestion-and-sync-closure

用法：
    python scripts/diagnose/mutate_custom_ingestion_task2.py --check-anchors   # 只读，秒级
    python scripts/diagnose/mutate_custom_ingestion_task2.py --apply           # 逐条打补丁+复原

🔴 不看退出码下结论：区分 RED（真打红预期项）/ GREEN（守卫缺陷）/
   ANCHOR-MISS（脚本缺陷：锚点未命中或命中 >1）/ WRONG-TEST（打红了但不是
   预期项 = 污染残留或锚点错行）。锚点一律行首锚定正则，不用固定字符窗口。
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
AUTH = ROOT / "backend/app/services/custom_template_ingestion/authorization.py"
ACT = ROOT / "backend/app/services/custom_template_ingestion/actions.py"

# pytest rootdir / pytest.ini 在 backend/
PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion", "-q", "-p", "no:randomly", "--tb=line",
]
PYTEST_CWD = ROOT / "backend"

# 🔴 字节级捕获 + 显式 UTF-8：Windows 默认 GBK 会在 pytest 的中文/✓ 输出上
# UnicodeDecodeError，导致 stdout=None、变异判据静默失效。
ENVPATCH: dict[str, str] = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    """一条变异。

    file: 被改文件；anchor: 行首锚定正则（re.MULTILINE，必须恰好命中 1 次）；
    replacement: 替换文本（原样字符串，不解释转义）；wants: 预期变红的测试名。
    """

    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    requirement: str


CASES: list[Case] = [
    # ── Requirement 2.4：审计助理拿到 confirm_mapping 权 ──
    Case(
        id="M1-auditor-gains-confirm",
        file=AUTH,
        anchor=(
            r"    \"auditor\": frozenset\(\{\n"
            r"        Capability\.UPLOAD,\n"
            r"    \}\),  # 🔴 Requirement 2\.4：只能上传 \+ 编辑 draft mapping；confirm 不给"
        ),
        replacement=(
            '    "auditor": frozenset({\n'
            "        Capability.UPLOAD,\n"
            "        Capability.CONFIRM_MAPPING,\n"
            "    }),  # 🔴 Requirement 2.4：只能上传 + 编辑 draft mapping；confirm 不给"
        ),
        wants=("test_auditor_can_only_upload_and_edit_draft_mapping",),
        requirement="2.4",
    ),
    # ── Requirement 2.3：partner 拿到组织级发布发起权（可自批自过）──
    Case(
        id="M2-partner-can-publish-org",
        file=AUTH,
        anchor=(
            "        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 批准者，非发起者\n"
            "    \\}\\),\n"
            "    \"qc\":"
        ),
        replacement=(
            "        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 批准者，非发起者\n"
            "        Capability.PUBLISH_ORGANIZATION,\n"
            "    }),\n"
            "    \"qc\":"
        ),
        wants=("test_only_template_admin_can_publish_organization",),
        requirement="2.3/2.4",
    ),
    # ── Requirement 2.7：QC 拿到 raw quarantine 下载权 ──
    Case(
        id="M3-qc-gains-raw-quarantine",
        file=AUTH,
        anchor=(
            "        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 质量控制复核合伙人批准\n"
            "    \\}\\),"
        ),
        replacement=(
            "        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 质量控制复核合伙人批准\n"
            "        Capability.READ_RAW_QUARANTINE,\n"
            "    }),"
        ),
        wants=("test_read_only_high_risk_roles_cannot_download_raw_quarantine",),
        requirement="2.7",
    ),
    # ── Requirement 1.6：成功文案谎称已发布 ──
    Case(
        id="M4-ingestion-claims-published",
        file=ACT,
        anchor=(
            '    if spec\\.action_id == INGEST_EXCEL_TEMPLATE:\n'
            '        return "已接收文件并进入隔离预检（未发布、未生成项目底稿）"'
        ),
        replacement=(
            '    if spec.action_id == INGEST_EXCEL_TEMPLATE:\n'
            '        return "模板已发布成功"'
        ),
        wants=("test_no_success_message_claims_upload_or_publication",),
        requirement="1.6",
    ),
    # ── Requirement 1.3：批量空白入口谎称接收二进制 ──
    Case(
        id="M5-batch-claims-binary",
        file=ACT,
        anchor=(
            '        side_effects=\\("create_blank_workpaper_rows",\\),\n'
            '        consumes_binary=False,'
        ),
        replacement=(
            '        side_effects=("create_blank_workpaper_rows",),\n'
            '        consumes_binary=True,'
        ),
        wants=("test_only_ingestion_action_consumes_binary",),
        requirement="1.3",
    ),
    # ── Requirement 2.5：candidate digest 变化不再使 intent 失效 ──
    Case(
        id="M6-digest-change-ignored",
        file=AUTH,
        anchor=(
            "            self.candidate_digest == candidate_digest\n"
        ),
        replacement=(
            "            True\n"
        ),
        wants=("test_stale_candidate_digest_invalidates_intent",),
        requirement="2.5",
    ),
    # ── Requirement 2.5：authorization epoch 变化不再使 intent 失效 ──
    Case(
        id="M7-epoch-change-ignored",
        file=AUTH,
        anchor=(
            "            and self.authorization_epoch == authorization_epoch\n"
        ),
        replacement=(
            "            and True\n"
        ),
        wants=("test_stale_authorization_epoch_invalidates_intent",),
        requirement="2.5",
    ),
    # ── Requirement 11.7：epoch basis 塞入文件字节字段 ──
    Case(
        id="M8-epoch-carries-content",
        file=AUTH,
        # 🔴 `{` 是正则字符类起始符，必须转义，否则整段被当空字符类而不命中
        anchor=(
            r"    basis = json\.dumps\(\{\n"
            r"        \"organizationId\": organization_id,\n"
            r"        \"projectId\": project_id,\n"
            r"    \}, sort_keys=True\)\n"
        ),
        replacement=(
            '    basis = json.dumps({\n'
            '        "organizationId": organization_id,\n'
            '        "projectId": project_id,\n'
            '        "fileSha256": organization_id,\n'
            '    }, sort_keys=True)\n'
        ),
        wants=("test_authorization_epoch_carries_no_content_fields",),
        requirement="11.7",
    ),
]


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    """只读校验：每条锚点必须命中且仅命中 1 次。"""
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        n = _count_matches(text, case.anchor)
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
        if not hit:
            failed = [l for l in out_str.splitlines() if "FAILED" in l][:5]
            return (f"{case.id}: WRONG-TEST ✗ —— 打红了但不是预期项 "
                    f"{case.wants}；实际: {failed}")
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
