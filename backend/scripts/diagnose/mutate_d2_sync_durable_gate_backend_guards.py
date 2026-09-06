"""后端变异检验：把 D2 同步修复改坏，确认守卫必红。会话结束即删。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]  # backend/scripts/diagnose/ -> 仓库根
ROUTER = ROOT / "backend" / "app" / "routers" / "d2_sync_router.py"
BRIDGE = ROOT / "backend" / "app" / "services" / "workpaper_sync" / "d2_bidirectional_bridge.py"
SPEC = "backend/tests/test_d2_sync_durable_gate.py"

MUTATIONS = [
    (
        "M01 陈旧校验整体失效（永不抛）",
        ROUTER,
        "        if current_sha == before_sha:",
        "        if False:",
    ),
    (
        "M02 并发换文件不再拒绝",
        ROUTER,
        "    if after_sha and current_sha != after_sha:",
        "    if False:",
    ),
    (
        "M03 pull 不调陈旧校验（回到直接读旧文件）",
        ROUTER,
        "        _assert_not_stale(artifact, fingerprint)",
        "        pass",
    ),
    (
        "M04 指纹只留 sha256（丢时间序维度）",
        ROUTER,
        'return {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "sha256": digest}',
        'return {"sha256": digest}',
    ),
    (
        "M05 _assign_store_value 退回无条件写并恒返 True",
        BRIDGE,
        "    if leaf in cursor and _same_store_value(cursor[leaf], value):\n        return False\n",
        "",
    ),
    (
        "M06 空值家族不再互等（把 None→'' 当成变化）",
        BRIDGE,
        "    if empty_existing or empty_incoming:",
        "    if False:",
    ),
    (
        "M07 数值不再按数值比（5200 vs 5200.0 判为变化）",
        BRIDGE,
        "    if isinstance(existing, (int, float)) and isinstance(incoming, (int, float)):",
        "    if False:",
    ),
    (
        "M08 forcesave 的 URL 缺失时谎报已接受",
        ROUTER,
        'return _FORCESAVE_REJECTED, "ONLYOFFICE_URL 未配置，无法发起强制保存"',
        'return _FORCESAVE_ACCEPTED, "ONLYOFFICE_URL 未配置，无法发起强制保存"',
    ),
    (
        "M09 把「无待保存」误当不可回写（复测踩到的误拒）",
        ROUTER,
        "    if outcome == _FORCESAVE_NOTHING_TO_SAVE:\n        # 无待保存内容 ⇒ 磁盘就是权威版本，不必等（等也永远等不到变化）。\n        durable = True",
        "    if outcome == _FORCESAVE_NOTHING_TO_SAVE:\n        durable = False",
    ),
]


def run_spec() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SPEC, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return proc.returncode == 0


print("=== 基线 ===")
if not run_spec():
    print("❌ 基线不绿")
    sys.exit(1)
print("  baseline PASS")

verdicts: dict[str, str] = {}
for name, path, old, new in MUTATIONS:
    original = path.read_text(encoding="utf-8")
    hits = original.count(old)
    if hits != 1:
        verdicts[name] = f"ANCHOR-MISS({hits})"
        print(f"  {verdicts[name]:20s} {name}")
        continue
    try:
        path.write_text(original.replace(old, new), encoding="utf-8")
        verdicts[name] = "GREEN(缺陷!)" if run_spec() else "RED"
    finally:
        path.write_text(original, encoding="utf-8")
        assert path.read_text(encoding="utf-8") == original, f"{path} 未还原"
    print(f"  {verdicts[name]:20s} {name}")

print()
reds = sum(1 for v in verdicts.values() if v == "RED")
print(f"RED={reds} / {len(MUTATIONS)}")
bad = {k: v for k, v in verdicts.items() if v != "RED"}
if bad:
    for k, v in bad.items():
        print(f"  {v}  {k}")
    sys.exit(1)
print("✅ 全部 RED")
