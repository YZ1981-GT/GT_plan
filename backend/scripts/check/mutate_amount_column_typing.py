"""mutate_amount_column_typing — 列类型判据与探针的变异检验

Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 4（Property 10）

证明「列类型真源 + 探针 + 正反断言」具备**区分能力**：故意破坏判据的某一环，
对应守卫必须打红（RED）。若变异后守卫仍绿（GREEN）＝守卫是死代码 / 只查字符串存在
的假绿。

四态判定：
  RED         变异后预期守卫由绿转红（唯一通过态）
  GREEN       变异后守卫仍绿 → 守卫缺陷（假绿）
  ANCHOR-MISS 变异锚点在目标文件命中数 != 1 → 脚本缺陷（锚点漂移）
  BASELINE-BAD 变异前守卫就不是绿 → 环境/污染问题，判定不可信

四个锚点：
  M1 删真源非金额词 /股数/         → amountColumnSemantics.spec.ts 红（19 类覆盖）
  M2 I1-10 使用期限列改 WpAmountInput → amountInputColumnTyping.spec.ts 红（反向边界）
  M3 删真源金额词 /原值/           → amountInputColumnTyping.spec.ts 红（I1-10 含原值）
  M4 探针插入固定字符窗口切片       → amountInputColumnTyping.spec.ts 红（Property 9）

用法（Windows）::

    python backend/scripts/check/mutate_amount_column_typing.py --list
    python backend/scripts/check/mutate_amount_column_typing.py --check-anchors
    python backend/scripts/check/mutate_amount_column_typing.py --only M2
    python backend/scripts/check/mutate_amount_column_typing.py --all
    python backend/scripts/check/mutate_amount_column_typing.py --restore

控制台禁 emoji。变异是「备份→改→跑→恢复」单进程闭环；中断残留用 --restore 兜底。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND = REPO_ROOT / "audit-platform" / "frontend"
WP_DIR = FRONTEND / "src" / "components" / "workpaper"
SEMANTICS_TS = WP_DIR / "shared" / "amountColumnSemantics.ts"
PROBE = BACKEND_ROOT / "scripts" / "check" / "audit_amount_input_columns.py"
I1_NO_IMPAIR = WP_DIR / "i1" / "amortization" / "I1TabAmortizationNoImpair.vue"

SEMANTICS_SPEC = "src/components/workpaper/shared/__tests__/amountColumnSemantics.spec.ts"
TYPING_SPEC = "src/components/workpaper/shared/__tests__/amountInputColumnTyping.spec.ts"


@dataclass
class Anchor:
    key: str
    desc: str
    file: Path
    find: str
    replace: str
    test_kind: str  # 'vitest'
    test_target: str  # spec 相对路径


ANCHORS: dict[str, Anchor] = {
    "M1": Anchor(
        key="M1",
        desc="删真源非金额词 /股数/ → amountColumnSemantics 守卫红（19 类覆盖）",
        file=SEMANTICS_TS,
        find="  { category: '股数', pattern: /股数/, sample: '股数' },\n",
        replace="",
        test_kind="vitest",
        test_target=SEMANTICS_SPEC,
    ),
    "M2": Anchor(
        key="M2",
        desc="I1-10 使用期限(年)列 el-input-number→WpAmountInput → 反向断言红",
        file=I1_NO_IMPAIR,
        find=(
            "            <el-input-number\n"
            "              v-if=\"!isReadonly\"\n"
            "              v-model=\"row.usefulLifeYears\"\n"
        ),
        replace=(
            "            <WpAmountInput\n"
            "              v-if=\"!isReadonly\"\n"
            "              v-model=\"row.usefulLifeYears\"\n"
        ),
        test_kind="vitest",
        test_target=TYPING_SPEC,
    ),
    "M3": Anchor(
        key="M3",
        desc="删真源金额词 /原值/ → amountColumnSemantics 守卫红（原值→amount + I1-10 定向）",
        file=SEMANTICS_TS,
        find="  /原值/,\n",
        replace="",
        test_kind="vitest",
        # Task7 翻转后 amountInputColumnTyping 不再断言「I1 含原值」，
        # 删 /原值/ 由 amountColumnSemantics 的「原值→amount」+「I1-10 定向」断言捕获
        test_target=SEMANTICS_SPEC,
    ),
    "M4": Anchor(
        key="M4",
        desc="探针插入固定字符窗口切片 → amountInputColumnTyping 守卫红（Property 9）",
        file=PROBE,
        find="    for m in TAG_OPEN.finditer(src):\n        open_at = m.start()\n",
        replace=(
            "    for m in TAG_OPEN.finditer(src):\n"
            "        open_at = m.start()\n"
            "        _window = src[open_at:open_at + 400]  # MUTATION\n"
        ),
        test_kind="vitest",
        test_target=TYPING_SPEC,
    ),
}


def run_vitest(spec: str) -> bool:
    """跑单个 spec，返回是否**通过**（绿=True）。"""
    cmd = f"npx vitest run {spec} --no-file-parallelism --reporter=dot"
    r = subprocess.run(
        cmd, cwd=str(FRONTEND), shell=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return r.returncode == 0


def run_test(a: Anchor) -> bool:
    if a.test_kind == "vitest":
        return run_vitest(a.test_target)
    raise SystemExit(f"[ERR] 未知 test_kind: {a.test_kind}")


def check_anchor(a: Anchor) -> str | None:
    """返回错误信息；命中唯一返回 None。"""
    if not a.file.exists():
        return f"目标文件不存在: {a.file}"
    n = a.file.read_text(encoding="utf-8").count(a.find)
    if n != 1:
        return f"锚点命中 {n} 次（应为 1）"
    return None


def mutate_one(a: Anchor) -> str:
    """对单锚点做「baseline→变异→恢复」闭环，返回四态。"""
    miss = check_anchor(a)
    if miss:
        print(f"  [MISS] {a.key}: {miss}")
        return "ANCHOR-MISS"

    print(f"  [....] {a.key} baseline（变异前应绿）...")
    if not run_test(a):
        print(f"  [BASELINE-BAD] {a.key}: 变异前守卫就不是绿，判定不可信")
        return "BASELINE-BAD"

    # 🔴 字节级读写：恢复用原始 bytes 完美还原（换行 + 编码全保持）。
    # Python write_text 在 Windows 会把 \n 转 \r\n，会改变文件换行状态；用字节级规避。
    raw = a.file.read_bytes()
    crlf = b"\r\n" in raw
    norm = raw.decode("utf-8").replace("\r\n", "\n")  # 归一 LF 后与 LF 锚点匹配
    bak = a.file.with_suffix(a.file.suffix + ".mutbak")
    bak.write_bytes(raw)
    try:
        mutated = norm.replace(a.find, a.replace, 1)
        out = mutated.replace("\n", "\r\n") if crlf else mutated  # 按原换行风格写回
        a.file.write_bytes(out.encode("utf-8"))
        print(f"  [....] {a.key} 变异后（预期红）...")
        passed = run_test(a)
    finally:
        a.file.write_bytes(raw)  # 原始字节完美还原，不改任何换行/编码
        bak.unlink(missing_ok=True)

    if passed:
        print(f"  [GREEN] {a.key}: 变异后守卫仍绿 → 守卫缺陷（假绿）")
        return "GREEN"
    print(f"  [RED] {a.key}: {a.desc}")
    # 恢复后复验（Windows 上连续 spawn python 写同一 JSON 偶发文件锁，失败重试一次）
    if not run_test(a) and not run_test(a):
        print(f"  [WARN] {a.key}: 恢复后守卫未回绿，请检查 {a.file}")
    return "RED"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--check-anchors", action="store_true", help="只读验证锚点命中（不跑测试）")
    g.add_argument("--only", metavar="KEY", help="只跑一个锚点，如 M2")
    g.add_argument("--all", action="store_true")
    g.add_argument("--restore", action="store_true", help="从 .mutbak 恢复中断残留")
    args = ap.parse_args()

    if args.list:
        for a in ANCHORS.values():
            print(f"  {a.key}: {a.desc}")
            print(f"        file={a.file.relative_to(REPO_ROOT)} test={a.test_target}")
        return 0

    if args.restore:
        n = 0
        for p in REPO_ROOT.rglob("*.mutbak"):
            orig = p.with_suffix("")  # 去掉 .mutbak
            orig.write_bytes(p.read_bytes())  # 字节级还原，不改换行
            p.unlink()
            n += 1
            print(f"  restored {orig.relative_to(REPO_ROOT)}")
        print(f"[OK] 恢复 {n} 个残留")
        return 0

    if args.check_anchors:
        bad = 0
        for a in ANCHORS.values():
            miss = check_anchor(a)
            mark = "MISS" if miss else "OK  "
            print(f"  [{mark}] {a.key}: {miss or a.desc}")
            if miss:
                bad += 1
        if bad:
            print(f"[ERR] {bad} 个锚点未命中（锚点漂移）")
            return 1
        print(f"[OK] {len(ANCHORS)} 个锚点全部命中唯一")
        return 0

    keys = [args.only] if args.only else list(ANCHORS.keys())
    if args.only and args.only not in ANCHORS:
        print(f"[ERR] 未知锚点 {args.only}，可选: {list(ANCHORS.keys())}")
        return 2

    verdicts: dict[str, str] = {}
    for k in keys:
        print(f"[MUT] {k}")
        verdicts[k] = mutate_one(ANCHORS[k])

    print("\n[SUMMARY]")
    all_red = True
    for k, v in verdicts.items():
        print(f"  {k}: {v}")
        if v != "RED":
            all_red = False
    if all_red:
        print(f"[OK] {len(verdicts)} 个锚点全部 RED（判据具区分能力）")
        return 0
    print("[ERR] 存在非 RED 锚点（守卫缺陷或锚点漂移）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
