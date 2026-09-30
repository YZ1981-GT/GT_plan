# -*- coding: utf-8 -*-
"""端到端脚本的变异证明（spec chain-closure-phase1-root-cause-fixes · task 7 配套）。

🔴 为什么必须有这一层（方法论铁律 ㉒ / ⑮）：`verify_chain_closure_phase1_real_stack.py` 首跑 19/19 全绿。
**全绿本身不构成证据** —— 判据可能恒真（比如 preset_count 读错字段恒取到非 0、
stale 计数把分母也算成 0/0）。这里逐个把四个根因的修复**改回坏的样子**，确认对应判据
真的转红；红了才说明那条判据在看该根因。

每个变异：改文件 → 跑一次真库端到端 → 从 `_chain_p1_e2e_result.json` 读判据 →
**finally 里按原始字节恢复**（不用 git checkout：R1/R2/R4 三处修复本身尚未提交，
`git checkout` 会把修复一起抹掉）。

用法（仓库根，需 `audit-postgres` 可连）::

    python backend/scripts/e2e/verify_chain_closure_phase1_mutation.py
    python backend/scripts/e2e/verify_chain_closure_phase1_mutation.py --only R3

退出码：0 = 四个变异全部按预期转红；1 = 任一变异没能打红（= 该判据恒真，必须重写）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
E2E = _BACKEND / "scripts" / "e2e" / "verify_chain_closure_phase1_real_stack.py"
RESULT = Path(tempfile.gettempdir()) / "chain_p1_e2e_result.json"
PY = _REPO / ".venv" / "Scripts" / "python.exe"

F_R1 = _BACKEND / "app" / "routers" / "draft_refresh.py"
F_R2 = _BACKEND / "app" / "services" / "formula_management" / "draft_refresh_orchestrator.py"
F_R3 = _BACKEND / "app" / "services" / "report_engine.py"
F_R4 = _BACKEND / "app" / "services" / "event_handlers" / "_impl.py"


def _sub(text: str, old: str, new: str, tag: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"[{tag}] 锚点命中 {text.count(old)} 次（应为 1），变异器已过期：\n{old[:120]}")
    return text.replace(old, new)


def mut_r1(t: str) -> str:
    return _sub(t, 'PARTNER_ROLES = ["partner", "signing_partner", "admin"]',
                'PARTNER_ROLES = ["partner", "signing_partner"]', "R1")


def mut_r2(t: str) -> str:
    return _sub(
        t,
        "                page_keys.extend(\n"
        "                    sorted(k for k in build_preset_index() if k.startswith(\"report:\"))\n"
        "                )\n",
        "                page_keys.append(\"report:*\")\n",
        "R2",
    )


def mut_r3(t: str) -> str:
    return _sub(
        t,
        "        regenerated = await self.regenerate_affected(\n"
        "            payload.project_id, year, payload.account_codes,\n"
        "            applicable_standard=applicable_standard,\n"
        "        )\n",
        "        regenerated = await self.regenerate_affected(\n"
        "            payload.project_id, year, payload.account_codes,\n"
        "        )\n",
        "R3",
    )


def mut_r4(t: str) -> str:
    """按标记切掉整段 FinancialReport stale（含注释与 except），不逐字复述原文。"""
    start = "                # 标记财务报表数据 stale\n"
    end = "                # 标记附注 stale\n"
    i, j = t.find(start), t.find(end)
    if i < 0 or j < 0 or j <= i:
        raise SystemExit(f"[R4] 定位失败 start={i} end={j}，变异器已过期")
    return t[:i] + t[j:]


MUTATIONS = [
    ("R1", F_R1, mut_r1, "R1 核心"),
    ("R2", F_R2, mut_r2, "R2 核心"),
    ("R3", F_R3, mut_r3, "R3 核心 链条⑦ →报表审定数"),
    ("R4", F_R4, mut_r4, "R4 核心 stale 落到 financial_report"),
]


def run_e2e() -> dict:
    if RESULT.exists():
        RESULT.unlink()
    proc = subprocess.run(
        [str(PY), str(E2E)], cwd=str(_REPO), capture_output=True,
        # 🔴 Windows 子进程 piped stdout 默认 gbk，脚本输出含中文与 emoji 必炸解码；
        #    解码失败不会让 run() 失败，只把 stdout 变 None ⇒ 假绿（方法论铁律 ㉗）。
        encoding="utf-8", errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    if not RESULT.exists():
        return {"crashed": True, "rc": proc.returncode,
                "tail": (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:]}
    data = json.loads(RESULT.read_text("utf-8"))
    data["rc"] = proc.returncode
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只跑某个变异（R1/R2/R3/R4）")
    args = ap.parse_args()

    # 🔴 先跑一次**未变异**基线并要求全绿：否则脚手架自己坏了（路径改名 / PG 连不上）会让
    #    每个变异都"崩溃"，而崩溃在下面被当作"打红" ⇒ 得到一份全是 ✅ 的假报告。
    print(f"{'=' * 72}\n基线（未变异）：要求 19 判据全绿，证明脚手架本身可用")
    base = run_e2e()
    if base.get("crashed") or base.get("passed") != base.get("total"):
        print(f"  🔴 基线不绿：{base.get('passed')}/{base.get('total')} "
              f"crashed={base.get('crashed')}\n{base.get('tail', '')[:1200]}")
        return 1
    print(f"  ✅ 基线 {base['passed']}/{base['total']} 通过")

    verdicts: list[tuple[str, bool, str]] = []
    for tag, path, fn, expect_name in MUTATIONS:
        if args.only and args.only.upper() != tag:
            continue
        original = path.read_bytes()
        print(f"\n{'=' * 72}\n变异 {tag}：{path.relative_to(_REPO)} → 期望判据「{expect_name}」转红")
        # 🔴 本仓这四个文件全是 **CRLF**（现算：208 / 380 / 2325 / 2300 处 \r\n，零 LF-only）。
        #    多行锚点若写 '\n' 会命中 0 次 —— 首版 R2/R4 就是这样静默失配的。统一拍平成 '\n'
        #    做替换、写回时还原成原换行符；并先做**恒等往返自检**，往返不等就不敢动这个文件。
        text = original.decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        flat = text.replace("\r\n", "\n")
        if flat.replace("\n", nl).encode("utf-8") != original:
            raise SystemExit(f"[{tag}] {path.name} 换行符往返不恒等（混合换行？），拒绝变异")
        try:
            path.write_bytes(fn(flat).replace("\n", nl).encode("utf-8"))
            res = run_e2e()
            if res.get("crashed"):
                verdicts.append((tag, True, f"端到端直接崩（rc={res['rc']}）—— 也算打红"))
                print(f"  🔴 崩溃尾部:\n{res['tail'][:800]}")
                continue
            by = {c["name"]: c for c in res["checks"]}
            target = by.get(expect_name)
            if target is None:
                verdicts.append((tag, False, f"判据「{expect_name}」根本没跑到（判据名漂了？）"))
                continue
            reddened = not target["ok"]
            verdicts.append((
                tag, reddened,
                f"判据 {res['passed']}/{res['total']} 通过；目标判据 "
                f"{'转红 ✅' if reddened else '仍绿 🔴（恒真！）'} — {target['detail'][:140]}",
            ))
        finally:
            path.write_bytes(original)
            assert path.read_bytes() == original, f"{path} 恢复失败！"
            print(f"  ↩ 已按原始字节恢复 {path.name}")

    print(f"\n{'=' * 72}\n变异结论")
    for tag, ok, note in verdicts:
        print(f"  {'✅' if ok else '🔴'} {tag}: {note}")
    bad = [t for t, ok, _ in verdicts if not ok]
    if bad:
        print(f"\n🔴 未能打红：{bad} —— 这些判据恒真，端到端等于没测")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
