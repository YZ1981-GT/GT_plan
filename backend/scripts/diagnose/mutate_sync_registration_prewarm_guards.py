"""一次性变异反证：冷注册串行锁 + 启动预热的判据各自可被打红。

用完即删（`_` 前缀）。用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_sync_registration_prewarm_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ROUTER = BACKEND / "app" / "routers" / "wp_sync_router.py"
MAIN = BACKEND / "app" / "main.py"
PREWARM = BACKEND / "app" / "services" / "workpaper_sync" / "startup_prewarm.py"
TEST = "tests/workpaper_sync/test_sync_registration_prewarm.py"
PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"

# (标签, 目标文件, 锚点(LF), 替换(LF))
MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "去掉冷注册串行锁",
        ROUTER,
        "    async with _registration_build_lock():\n"
        "        # 拿到锁后**重查**：等锁期间别的请求很可能已经把缓存建好了。\n"
        "        cached = _REGISTRATION_CACHE.get(fingerprint)\n"
        "        if cached is not None:\n"
        "            return _replay_cached_registrations(svc, cached)\n",
        "    if True:  # MUTATED: 无锁\n"
        "        cached = _REGISTRATION_CACHE.get(fingerprint)\n"
        "        if False:\n"
        "            return _replay_cached_registrations(svc, cached)\n",
    ),
    (
        "拿锁后不重查缓存（串行但不省成本）",
        ROUTER,
        "        cached = _REGISTRATION_CACHE.get(fingerprint)\n"
        "        if cached is not None:\n"
        "            return _replay_cached_registrations(svc, cached)\n\n"
        "        explicit = (",
        "        cached = None  # MUTATED: 不重查\n"
        "        if cached is not None:\n"
        "            return _replay_cached_registrations(svc, cached)\n\n"
        "        explicit = (",
    ),
    (
        "预热不走请求路径（自己拼一遍）",
        PREWARM,
        "        return await _attach_pilot_adapters(context)",
        "        return await _mutated_not_the_request_path(context)",
    ),
    (
        "预热改成阻塞启动（await 而非 create_task）",
        MAIN,
        "    tasks.append(asyncio.create_task(_warm_workpaper_sync_registry()))",
        "    await _warm_workpaper_sync_registry()",
    ),
    (
        "预热失败不再被吞（会打挂启动）",
        MAIN,
        "    except Exception as exc:  # noqa: BLE001 — 预热失败不阻塞，首请求会自行惰性注册",
        "    except ValueError as exc:  # MUTATED: 只吞 ValueError",
    ),
    (
        "projection 预热不再按 bidirectional 过滤",
        PREWARM,
        "                registration = registry.assert_bidirectional_ready(str(entry_id))",
        "                registration = registry.registration_for(str(entry_id))",
    ),
    (
        "projection 预热去掉 LIMIT（无界后台负载）",
        PREWARM,
        "                .limit(PREWARM_PROJECTION_MAX_ENTRIES)",
        "                .limit(None)",
    ),
    (
        "启动只跑注册预热，不跑 projection 预热",
        MAIN,
        "        warmed, skipped = await prewarm_sync_baseline_projections()",
        "        warmed, skipped = (0, 0)  # MUTATED: 不跑第二段",
    ),
]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", TEST, "-q", "--tb=line", "-p", "no:randomly"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    originals = {path: path.read_bytes() for path in {ROUTER, MAIN, PREWARM}}
    rc, out = run_tests()
    tail = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    print(f"[baseline] rc={rc}  {tail[-1] if tail else out[-200:]}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    failures = 0
    try:
        for label, target, old_lf, new_lf in MUTATIONS:
            original = originals[target]
            eol = "\r\n" if b"\r\n" in original else "\n"
            old = old_lf.replace("\n", eol)
            new = new_lf.replace("\n", eol)
            text = original.decode("utf-8")
            hits = text.count(old)
            if hits != 1:
                print(f"[MISS] 锚点命中 {hits} 次（需恰好 1）：{label}")
                failures += 1
                continue
            target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            red = [line for line in out.splitlines() if "FAILED" in line]
            summary = [line for line in out.splitlines() if "passed" in line or "failed" in line]
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary[-1] if summary else ''}")
            for line in red[:4]:
                print(f"    {line}")
            if rc == 0:
                failures += 1
            target.write_bytes(original)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
            assert path.read_bytes() == raw, f"还原失败：{path}"
        print("[restore] 全部目标文件已逐字节还原")

    rc, out = run_tests()
    tail = [line for line in out.splitlines() if "passed" in line or "failed" in line]
    print(f"[post-restore] rc={rc}  {tail[-1] if tail else ''}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
