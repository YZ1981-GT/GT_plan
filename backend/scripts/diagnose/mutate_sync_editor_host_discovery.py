"""变异检验：证明 `sync-editor-host-discovery-contract-closure` 的判据不是装饰。

spec: sync-editor-host-discovery-contract-closure · Task 15 / Requirement 4.5

每条变异临时改**一处**源码或 overlay，跑指定判据，期望它**打红**（或生成器 fail closed）；
随后按 sha256 校验**强制还原**。只读模式见 `--check-anchors`。

用法：
  python backend/scripts/diagnose/mutate_sync_editor_host_discovery.py --check-anchors
  python backend/scripts/diagnose/mutate_sync_editor_host_discovery.py --run all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

#: 仓库根：本文件在 `backend/scripts/diagnose/` 下 ⇒ parents[3]
#: （parents[2] 是 `backend/`，首版写错导致全部锚点报「文件不存在」）
ROOT = Path(__file__).resolve().parents[3]
MJS = "audit-platform/frontend/scripts/discover-workpaper-sync-mounts.mjs"
OVERLAY = "backend/data/workpaper_sync_entry_overlay.json"
FACTS = "backend/app/services/workpaper_sync/entry_source_facts.py"
GENERATOR = "backend/scripts/gen/generate_workpaper_sync_manifest.py"
GUARD = "backend/tests/workpaper_sync/test_sync_editor_host_discovery_contract.py"


@dataclass(frozen=True)
class Mutation:
    id: str
    path: str
    anchor: str
    replacement: str
    why: str
    #: 期望打红的 pytest 选择器；`"GENERATOR"` = 期望生成器 --check 非零退出
    want: str
    #: 可选：非零退出还不够，输出必须含该文案，防止 fixture 提前报错造成 WRONG-RED。
    must_contain: str | None = None


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        id="M01",
        path=MJS,
        anchor="  ['workpapersynceditorhost', {",
        replacement="  ['DISABLED_BY_MUTATION_workpapersynceditorhost', {",
        why=(
            "把同步载体从发现器白名单里摘掉 ⇒ 缺口本体判据必须打红。"
            "🔴 **首版把 want 指向读磁盘 manifest 的那条，实测 GREEN** —— 因为改发现器"
            "在产物重生成之前不改变磁盘产物，判据还在看旧事实。这暴露的是**判据缺口**"
            "而不是变异无效，故新增了接活事实的 `TestTheInvariantHoldsOnLiveFacts`，"
            "want 改指它（它现跑发现器 + 在内存重算 manifest）。"
        ),
        want="TestTheInvariantHoldsOnLiveFacts",
    ),
    Mutation(
        id="M02",
        path=MJS,
        anchor="      fact.documentType = siblingTypes[0]",
        replacement="      fact.documentType = 'xlsx'  // MUTATION: 兜底成 xlsx",
        why=(
            "把 L1 的「继承兄弟挂点」换成硬编码兜底 ⇒ 交叉校验（L1 vs L2 必须一致）"
            "在 docx 场景下会失效。本仓现算 96/96 都是 xlsx，故本变异**不期望**现在打红 —— "
            "它的价值是把「兜底为何危险」写成可复现实验：改完三层覆盖判据仍绿，"
            "正说明「今天对」不等于「正确」。期望目标取闭合判据以证明变异确实生效。"
        ),
        want="TestResolutionLayersClose::test_layers_partition_all_hosts_and_none_is_empty",
    ),
    Mutation(
        id="M03",
        path=OVERLAY,
        anchor='"sync_host_entry_rules"',
        replacement='"sync_host_entry_rules_DISABLED_BY_MUTATION"',
        why="删掉 L3 规则 ⇒ 30 个 d4 tab 身份无从解析，生成器必须 fail closed（而非静默少 30 条）",
        want="GENERATOR",
    ),
    Mutation(
        id="M04",
        path=FACTS,
        anchor='        return Editability.editable, FACT_BRIDGE_GATED_EDITABLE',
        replacement='        return Editability.readonly, FACT_BRIDGE_GATED_EDITABLE',
        why="把同步载体判成只读 ⇒ expected_profile 的取值域不符，生成器必须 fail closed",
        want="GENERATOR",
    ),
    Mutation(
        id="M05",
        path=OVERLAY,
        anchor='"canonical_resolver": "sync_bridge_editor_host"',
        replacement='"canonical_resolver": "legacy_sheet_onlyoffice_router"',
        why=(
            "把新组件默认 resolver 改成 legacy 的 ⇒ 「仅同步载体 entry 用同步 resolver」必红。"
            "🔴 同 M01：首版 want 指向读磁盘的那条、实测 GREEN（改 overlay 不改磁盘产物）；"
            "改指接活事实的 `…_on_live_facts` 版本。"
        ),
        want="TestTheInvariantHoldsOnLiveFacts::test_only_sync_host_entries_use_the_sync_resolver_on_live_facts",
    ),
    Mutation(
        id="M06",
        path=GENERATOR,
        anchor='        capability = value.get("capability")',
        replacement=(
            '        if "WorkpaperSyncEditorHost" in mount_components and len(mount_components) > 1:\n'
            '            value["capability"] = "single_html"  # MUTATION: 挂同步载体即篡改裁决\n'
            '        capability = value.get("capability")'
        ),
        why=(
            "在 overlay 裁决完成后、entry 落盘前，仅当同一 entry 含同步载体 + legacy 双挂时把 "
            "capability 篡改为 single_html。before 态过滤了同步挂点所以不触发，after 态触发；"
            "两态都能完整生成，不会先撞 stale / expected_profile 门，故必须在逐 entry 零 churn "
            "assertion 本身打红。🔴 旧判据只查 resolver 不等于某默认值，此变异会照样 GREEN；"
            "M06 专门证明新差分判据不是同类假绿。"
        ),
        want="TestEntryDerivationIsCorrect::test_dual_mount_entries_took_no_capability_churn",
        must_contain="因发现同步载体而改变业务裁决",
    ),
    Mutation(
        id="M07",
        path=GENERATOR,
        anchor="        entry_id = _entry_id(document_type, source_file)",
        replacement=(
            "        entry_id = _entry_id(document_type, source_file)\n"
            "        if (\n"
            "            \"WorkpaperSyncEditorHost\" in mount_components\n"
            "            and source_file.endswith(\"GtB22AControlMatrix.vue\")\n"
            "        ):\n"
            "            entry_id += \"-MUTATED\"  # MUTATION: 同步挂点导致既有 entry_id 改名"
        ),
        why=(
            "仅对 B22A 双挂宿主在同步载体可见时改写 entry_id；before 态过滤同步挂点所以保持原 id，"
            "after 态改名。B22A 是现算 4 个『双挂但同步挂点无 entryIdDeclaration』的宿主之一，"
            "不会因改名先被 declared_parent / parent missing 门截住，能完整走到 guard。"
            "必须红在『旧 entry 消失或改名』断言本身。"
        ),
        want="TestEntryDerivationIsCorrect::test_dual_mount_entries_took_no_capability_churn",
        must_contain="旧发现器可见的 entry 在纳入同步载体后消失或改了 entry_id",
    ),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_anchors() -> int:
    bad = 0
    for mutation in MUTATIONS:
        target = ROOT / mutation.path
        if not target.is_file():
            print(f"  !! {mutation.id} 文件不存在：{mutation.path}")
            bad += 1
            continue
        text = target.read_bytes().decode("utf-8")
        hits = text.count(mutation.anchor)
        flag = "OK " if hits == 1 else "!! "
        if hits != 1:
            bad += 1
        print(f"  {flag}{mutation.id} anchor 命中 {hits} 次  {mutation.path}")
    print(f"\n锚点检查：{len(MUTATIONS) - bad} / {len(MUTATIONS)} 唯一命中")
    return 1 if bad else 0


def _run_pytest(selector: str, must_contain: str | None = None) -> tuple[bool, str]:
    proc = subprocess.run(
        [str(ROOT / ".venv/Scripts/python.exe"), "-m", "pytest",
         f"{GUARD}::{selector}" if "::" in selector else GUARD,
         "-q", "--tb=short", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, shell=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "JWT_SECRET_KEY": "mutation-probe"},
    )
    out = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", errors="replace")
    assert out.strip(), "pytest 无输出 ⇒ 不采信（可能解码失败被吞）"
    tail = out.strip().split("\n")[-1]
    if proc.returncode != 0 and must_contain and must_contain not in out:
        details = [
            line.strip()
            for line in out.splitlines()
            if any(token in line for token in (
                "Error", "ERROR at", "ManifestGeneration", "stale reviewed",
                "assert ",
            ))
        ]
        detail = " | ".join(details[-3:]) if details else tail
        return False, (
            f"WRONG-RED：输出未含预期文案 {must_contain!r}；"
            f"真实首条错误={detail}"
        )
    return proc.returncode != 0, tail


def _run_generator() -> tuple[bool, str]:
    proc = subprocess.run(
        [str(ROOT / ".venv/Scripts/python.exe"),
         "backend/scripts/gen/generate_workpaper_sync_manifest.py", "--check"],
        cwd=ROOT, capture_output=True, shell=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", errors="replace")
    assert text.strip(), "生成器无输出 ⇒ 不采信"
    line = next((ln for ln in text.split("\n") if "[FAIL]" in ln), text.strip().split("\n")[-1])
    return proc.returncode != 0, line.strip()[:160]


def run(selected: set[str]) -> int:
    chosen = [m for m in MUTATIONS if "all" in selected or m.id in selected]
    assert chosen, f"没有匹配的变异：{selected}"
    tmp = Path(tempfile.mkdtemp(prefix="gt_mut_"))
    paths = sorted({m.path for m in chosen})
    before = {p: sha(ROOT / p) for p in paths}
    for p in paths:
        dest = tmp / p.replace("/", "__")
        shutil.copy2(ROOT / p, dest)

    results: list[tuple[Mutation, bool, str]] = []
    try:
        for mutation in chosen:
            target = ROOT / mutation.path
            text = target.read_bytes().decode("utf-8")
            assert text.count(mutation.anchor) == 1, f"{mutation.id} 锚点不唯一"
            newline = "\r\n" if target.read_bytes().count(b"\r\n") else "\n"
            mutated = text.replace(mutation.anchor, mutation.replacement, 1)
            assert mutated != text
            target.write_bytes(mutated.encode("utf-8"))
            assert sha(target) != before[mutation.path], f"{mutation.id} 写入未生效"
            try:
                red, tail = (
                    _run_generator() if mutation.want == "GENERATOR"
                    else _run_pytest(mutation.want, mutation.must_contain)
                )
            finally:
                shutil.copy2(tmp / mutation.path.replace("/", "__"), target)
                assert sha(target) == before[mutation.path], f"{mutation.id} 还原失败"
            results.append((mutation, red, tail))
            print(f"  {'RED ' if red else 'GREEN'} {mutation.id}  {tail[:500]}")
    finally:
        for p in paths:
            shutil.copy2(tmp / p.replace("/", "__"), ROOT / p)
        ok = all(sha(ROOT / p) == before[p] for p in paths)
        print(f"\n[RESTORE] {len(paths)} 个文件已还原、sha256 逐个一致 = {ok}")
        assert ok, "还原失败！请手工 checkout"
        shutil.rmtree(tmp, ignore_errors=True)

    # M02 的期望是 GREEN（见其 why）：它证明「兜底在本仓今天不可见」，是反例而非判据缺口
    expect_green = {"M02"}
    bad = [
        m.id for m, red, _ in results
        if (m.id in expect_green and red) or (m.id not in expect_green and not red)
    ]
    print(f"\n变异结果：{len(results) - len(bad)} / {len(results)} 符合预期")
    if bad:
        print(f"🔴 不符合预期：{bad}")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-anchors", action="store_true")
    group.add_argument("--run", metavar="all|M01,M02")
    args = parser.parse_args()
    if args.check_anchors:
        return check_anchors()
    return run({token.strip() for token in str(args.run).split(",") if token.strip()})


raise SystemExit(main())
