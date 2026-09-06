"""变异检验：把修复逐条改坏，确认守卫测试必红。会话结束即删。

四态判定：RED（打红且是预期那条）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中或命中多处）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]  # backend/scripts/diagnose/ -> 仓库根
FE = ROOT / "audit-platform" / "frontend"
BRIDGE = FE / "src" / "components" / "workpaper" / "sync" / "useD2SyncBridge.ts"
HOST = FE / "src" / "components" / "workpaper" / "GtD2AccountsReceivable.vue"
SPECS = [
    "src/components/workpaper/__tests__/d2SyncDurableGate.spec.ts",
    "src/components/workpaper/__tests__/d2SyncHostWiring.spec.ts",
]

MUTATIONS = [
    (
        "M01 去掉耐久门（durable 判定恒真）→ pull 会读旧文件",
        BRIDGE,
        "if (!saved || !saved.durable) {",
        "if (false) {",
    ),
    (
        "M02 不 await flush（缺陷 A 复现）",
        BRIDGE,
        "if (flushBeforeOo) await flushBeforeOo()",
        "if (flushBeforeOo) void flushBeforeOo()",
    ),
    (
        "M03 拿不到确认仍切模式",
        BRIDGE,
        "        throw new NotDurableError(",
        "        void 0 || new NotDurableError(",
    ),
    (
        "M04 isOoAvailable 退回硬编码 true",
        BRIDGE,
        "    if (s.bidirectional === false) return false",
        "    if (false) return false",
    ),
    (
        "M05 不把耐久指纹传给后端（服务端二次校验失效）",
        BRIDGE,
        "      durableFingerprint ? { durable_fingerprint: durableFingerprint } : {},",
        "      {},",
    ),
    (
        "M06 宿主漏传 flushBeforeOo（原始缺陷 A）",
        HOST,
        "  flushBeforeOo: () => formData.flushPendingSave(),",
        "",
    ),
    (
        "M07 宿主漏传 requestForceSave（原始缺陷 B）",
        HOST,
        "  requestForceSave: () => ooSheetRef.value?.forceSave() ?? Promise.resolve(null),",
        "",
    ),
]


def run_spec() -> tuple[bool, str]:
    proc = subprocess.run(
        ["cmd", "/c", "npx", "vitest", "run", *SPECS, "--reporter=basic"],
        cwd=str(FE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # 判据用退出码 + 「没有 failed」双条件，不用脆弱的空格敏感字符串
    passed = proc.returncode == 0 and "failed" not in out
    return passed, out


print("=== 基线：未变异应全绿 ===")
ok, out = run_spec()
print(f"  baseline passed={ok}")
if not ok:
    print("❌ 基线就不绿，先修基线")
    sys.exit(1)

verdicts: dict[str, str] = {}
for name, path, old, new in MUTATIONS:
    original = path.read_text(encoding="utf-8")
    hits = original.count(old)
    if hits != 1:
        verdicts[name] = f"ANCHOR-MISS(命中 {hits} 处)"
        print(f"  {verdicts[name]:24s} {name}")
        continue
    try:
        path.write_text(original.replace(old, new), encoding="utf-8")
        passed, _ = run_spec()
        verdicts[name] = "GREEN(守卫缺陷!)" if passed else "RED"
    finally:
        path.write_text(original, encoding="utf-8")
        assert path.read_text(encoding="utf-8") == original, f"{path} 未干净还原"
    print(f"  {verdicts[name]:24s} {name}")

print()
reds = sum(1 for v in verdicts.values() if v == "RED")
print(f"RED={reds} / {len(MUTATIONS)}")
bad = {k: v for k, v in verdicts.items() if v != "RED"}
if bad:
    print("❌ 非 RED 项：")
    for k, v in bad.items():
        print(f"   {v}  {k}")
    sys.exit(1)
print("✅ 全部 RED —— 守卫对每条修复都有效")
