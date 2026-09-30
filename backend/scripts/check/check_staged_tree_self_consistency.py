# -*- coding: utf-8 -*-
"""在**暂存树**上跑零回归门 —— 提交前就发现「基线入库了、实现没入库」。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-i（2026-09-28）

═══ 这个门解决什么 ═══

本轮实测的三处漏提交，共同形态是「**工作树绿 ≠ 提交后绿**」：

  digest 基线随某轮提交入库了，而对应的 6 个 provider 改动留在工作树 ⇒
  工作树上 golden digest 门 exit 0（两边都是新的），HEAD 上 exit 1（基线新、代码旧）。

现有机制一个都拦不住这类：

  * pre-commit 的各门都读**工作树** ⇒ 永远绿；
  * CI 虽然跑 Gate 1，但要等 push 之后 —— 本轮那 6 个 provider 从没进过任何 commit，
    所以 CI 从来没有机会看到它们；
  * 只有「起 worktree / 临时换文件」这种手工动作才能发现，本轮正是这么发现的。

⇒ 把那个手工动作自动化：`git checkout-index` 把**暂存内容**物化到临时目录，
  在那里跑门。检查的对象恰好是「这次 commit 之后仓库会是什么样」。

═══ 为什么不用 worktree ═══

`git worktree add` 要检出整个工作树（本仓库含大量 xlsx 模板，慢），而且 worktree 是
分支级的，表达不了「暂存区」这个中间状态。`checkout-index` 直接导出 index，
按后缀过滤后实测 ~2.6 秒 / 5962 个文件。

═══ 🔴 导出范围：全部已跟踪的 backend 文件，不做后缀过滤 ═══

首版只导出 `.py` / `.json` / `.yaml`，理由写的是「golden digest 是合成 payload 驱动、
不读 xlsx 模板，所以够用」—— **那是推演，实测打脸**：

    [SKIP] g10: 探针覆盖的权威模板缺失: K11 → <tree>/backend/wp_templates/K/K11 ....xlsx
    [SKIP] g8 / g14 / g11 / g13 / g12 / g1 / g3 / g4 / g6 / g5 ...（十余家）

golden digest 门对缺模板的 provider 走 `[SKIP]` 而**照常 exit 0** ⇒ 我的门拿到的绿
是假的。这正是平台铁律「禁推演、必现算」的又一次应验，也是「结构性零/通过必须配
变异证明」的同一件事：不先证明门在这棵树上**真的跑满**，它的 exit 0 毫无意义。

改为全量导出（实测 9633 文件 / 286 MB / **4.2 秒**，可接受），并加下面这条硬检查。

═══ SKIP 检测：跑不满就不算过 ═══

`_SKIP_MARKERS` 命中即判失败，无论门自己返回什么。理由：本门的语义是「提交后仓库
是否自洽」，而 `[SKIP]` 意味着这道门对一部分 provider 什么都没验 —— 那是覆盖面缺口，
不是通过。

导出树里没有 `.venv`，所以用**当前解释器**跑子进程，只把 `cwd` 指向导出树 ——
依赖来自当前环境，被检查的只有代码本身。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

#: 🔴 不做后缀过滤、也不限 `backend/`（见模块 docstring）。两次收窄都被实测打脸：
#:   ① 只导 `.py/.json/.yaml` ⇒ golden digest 对十余家 provider 报
#:      `[SKIP] 探针覆盖的权威模板缺失`（它真的读 `backend/wp_templates/*.xlsx`）；
#:   ② 只导 `backend/` ⇒ 又报
#:      `[SKIP] d4: ... .kiro/specs/d-cycle-sheet-bidirectional-expansion/evidence/
#:      T09-d45-block-field-mapping.json` 不存在（门还读 spec 目录下的 evidence）。
#: 两次都是「我以为它只读代码」这个推演。⇒ 物化**全部已跟踪文件**
#: （实测 21499 个 / 456 MB / 9.8 秒）。
_INCLUDE_SUFFIXES: tuple[str, ...] | None = None
_PATHSPEC: tuple[str, ...] = ()  # 空 = 全仓

#: 门输出里出现这些标记 ⇒ 该门「跑不满」。
_SKIP_MARKERS: tuple[str, ...] = ("[SKIP]", "[skip]")

#: 每道门**允许**的 SKIP 标签（其余 SKIP 一律判失败）。
#:
#: 🔴 这不是放宽，而是把「门自己已登记的预期跳过」与「我的物化树缺东西」分开 ——
#: 后者是本门的缺陷，前者是被测门的既有登记。
#: `f1` 是 golden digest 门自己 `SKIPPED_PROVIDER_LABELS` 里登记的那条
#: （`build_store_projection(store_item_id, payload, *, contract)` 两个位置参数、
#: 与该门单参调用口径不兼容），在真实工作树上同样 SKIP。
#: 自测 `test_expected_skips_are_still_actually_skipped` 断言它真的仍在 SKIP。
_EXPECTED_SKIPS: dict[str, tuple[str, ...]] = {
    "backend/scripts/check/check_sync_provider_golden_digest.py": ("f1",),
}

_SKIP_LINE_RE = re.compile(r"\[SKIP\]\s*([A-Za-z0-9_.\-]+)\s*:")

#: 在暂存树上跑哪些门（相对仓库根的脚本路径）。
#:
#: 只放**纯代码驱动、不依赖真库/真模板**的门 —— 其余的在暂存树上跑没有意义
#: （缺 storage / 缺 DB），会变成噪音。
_GATES: tuple[tuple[str, str], ...] = (
    (
        "backend/scripts/check/check_sync_provider_golden_digest.py",
        "golden digest 零回归（本轮 6 个 provider 漏提交就是它在 HEAD 上报出来的）",
    ),
    (
        "backend/scripts/check/check_store_item_two_way_parity.py",
        "两方向 store item parity（本轮 registry 接线漏提交就是它报出来的）",
    ),
)


def _staged_paths() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", *_PATHSPEC],
        cwd=str(_REPO), capture_output=True, check=True,
    )
    out = []
    for raw in proc.stdout.split(b"\x00"):
        if not raw:
            continue
        p = raw.decode("utf-8")
        if _INCLUDE_SUFFIXES is not None and not p.endswith(_INCLUDE_SUFFIXES):
            continue
        out.append(p)
    return out


def unexpected_skips(gate_rel: str, output: str) -> list[str]:
    """门输出里**非预期**的 SKIP 标签。

    只按 `[SKIP] <label>:` 解析标签；解析不出标签的 SKIP 行一律算非预期
    （宁可误报也不放过 —— 放过等于回到「跑不满也算过」）。
    """
    allowed = set(_EXPECTED_SKIPS.get(gate_rel, ()))
    found: list[str] = []
    for line in output.splitlines():
        if not any(m in line for m in _SKIP_MARKERS):
            continue
        m = _SKIP_LINE_RE.search(line)
        label = m.group(1) if m else line.strip()[:60]
        if label not in allowed:
            found.append(label)
    return sorted(set(found))


def _materialise(dest: Path) -> int:
    """把暂存内容里的 backend 代码物化到 dest。返回文件数。"""
    paths = _staged_paths()
    if not paths:
        raise RuntimeError("git ls-files 没有返回任何 backend 下的代码文件 —— 口径有问题")
    payload = b"\x00".join(p.encode("utf-8") for p in paths) + b"\x00"
    proc = subprocess.run(
        ["git", "checkout-index", "--stdin", "-z", "--force", f"--prefix={dest.as_posix()}/"],
        cwd=str(_REPO), input=payload, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "checkout-index 失败：" + proc.stderr.decode("utf-8", "replace")[:500]
        )
    return len(paths)


def _run_gate(tree: Path, gate_rel: str) -> tuple[int, str]:
    script = tree / gate_rel
    if not script.exists():
        return 127, f"暂存树里没有 {gate_rel} —— 该门本身未入库？"
    proc = subprocess.run(
        [sys.executable, str(script.relative_to(tree / "backend"))],
        cwd=str(tree / "backend"), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=900,
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or ""))[-2500:]


def _force_utf8_stdout() -> None:
    """让本门的输出在 GBK 控制台上也不会崩。

    🔴 2026-09-30 修一个**只在失败路径上触发**的缺陷：成功分支打的 `✅`(U+2705) 恰好能被
    GBK 编码，失败分支打的 `❌`(U+274C) 不能 ⇒ 门一旦判失败就
    `UnicodeEncodeError: 'gbk' codec can't encode character '\\u274c'`，
    在**打印失败原因的那一行**崩掉。后果不是「少看到一个图标」，而是
    **整份诊断信息全没了**：pre-push 只剩一句「暂存树自洽检查失败」，
    到底哪道门、哪个 provider、基线与现算差多少，一个字都看不到
    （我本轮就是靠 `PYTHONIOENCODING=utf-8` 重跑才拿到诊断）。

    失败路径比成功路径更需要能说话 —— 这类「门能判红但说不出红在哪」等于半个门。

    用**就地** `reconfigure`（不新建 TextIOWrapper、不夺走 buffer 所有权，
    因此不会像 `scripts/ops/setup_wp_templates_dir.py` 那样把 pytest capture 的底层
    buffer 关掉）；再配 `errors="replace"`，即便目标编码仍装不下也只是替换字符、不抛。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - 已被替换的流可能不支持
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    parser.add_argument("--keep", action="store_true", help="保留导出树（排查用）")
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="gt_staged_tree_"))
    results: list[dict[str, object]] = []
    try:
        count = _materialise(tmp)
        for gate_rel, why in _GATES:
            rc, out = _run_gate(tmp, gate_rel)
            skipped = unexpected_skips(gate_rel, out)
            results.append(
                {
                    "gate": gate_rel,
                    "why": why,
                    "rc": rc,
                    "unexpected_skips": skipped,
                    # 🔴 跑不满 ⇒ 不算过（哪怕门自己返回 0）
                    "verdict_ok": rc == 0 and not skipped,
                    "tail": out,
                }
            )
    finally:
        if args.keep:
            print(f"[keep] 导出树保留在 {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if not r["verdict_ok"]]
    report = {
        "ok": not failed,
        "materialised_files": count,
        "gates": [{k: v for k, v in r.items() if k != "tail"} for r in results],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not failed:
        print(
            f"✅ 暂存树自洽：物化 {count} 个代码文件，{len(results)} 道门全 exit 0"
        )
        for r in results:
            print(f"   [ok] {Path(str(r['gate'])).name} —— {r['why']}")
        return 0

    print(
        f"❌ 暂存树上有 {len(failed)} 道门不过 —— 提交后仓库会是这个样子。"
        "常见成因：基线/生成物已暂存而对应实现没暂存（或反之）："
    )
    for r in failed:
        if r["unexpected_skips"]:
            print(
                f"\n   [rc={r['rc']} 但有非预期 SKIP {r['unexpected_skips']}] {r['gate']}"
                f"\n   🔴 该门在暂存树上**跑不满** —— 这些 provider 被跳过，"
                "它的 exit 0 不可信（覆盖面缺口不是通过）。"
                "\n   若确属被测门自己登记的预期跳过，登记进 _EXPECTED_SKIPS 并说明理由。"
            )
        else:
            print(f"\n   [rc={r['rc']}] {r['gate']}\n   {r['why']}")
        print("   " + str(r["tail"]).replace("\n", "\n   "))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
