"""变异反证：post-durable 失败真因的读侧投影判据可被打红。

用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_post_durable_failure_reason_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ROUTER = BACKEND / "app" / "routers" / "wp_sync_router.py"
WORDING = BACKEND / "app" / "services" / "workpaper_sync" / "failure_wording.py"
TEST = "tests/workpaper_sync/test_post_durable_failure_reason_is_visible.py"
PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "端点不再投影 application 侧失败真因",
        ROUTER,
        "                **await _application_failure_facts(svc, application_id=row.id),",
        "                # MUTATED: 不投影",
    ),
    (
        "取首条事件而不是最后一条（会拿到早期无关失败）",
        ROUTER,
        "            .order_by(WorkpaperContentApplicationEvent.sequence_no.desc())",
        "            .order_by(WorkpaperContentApplicationEvent.sequence_no.asc())",
    ),
    (
        "不过滤 error_code 非空（会取到一条正常 state_changed）",
        ROUTER,
        "                WorkpaperContentApplicationEvent.error_code.isnot(None),",
        "                # MUTATED: 不过滤",
    ),
    (
        "未登记的码也编一句措辞",
        WORDING,
        "    for registry in _registries():\n"
        "        text = registry.get(key)\n"
        "        if text:\n"
        "            return str(text)\n"
        "    return None",
        "    for registry in _registries():\n"
        "        text = registry.get(key)\n"
        "        if text:\n"
        "            return str(text)\n"
        '    return "回写失败，请稍后重试"',
    ),
    (
        "措辞改成自己抄的第二份副本（必然与引擎词表漂移）",
        WORDING,
        "    from app.services.workpaper_sync.excel_materialize import FAILURE_KINDS\n\n"
        "    return (FAILURE_KINDS,)",
        "    return ({\n"
        '        "excel_materialize_editable_write_failed": "写入失败",\n'
        "    },)",
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


def summary(out: str) -> str:
    for line in out.splitlines():
        if "passed" in line or "failed" in line:
            return line.strip()
    return out[-140:].replace("\n", " ")


def main() -> int:
    originals = {path: path.read_bytes() for path in {ROUTER, WORDING}}
    rc, out = run_tests()
    print(f"[baseline] rc={rc}  {summary(out)}")
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
                print(f"[MISS] 锚点命中 {hits} 次（需 1）：{label}")
                failures += 1
                continue
            target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary(out)}")
            for line in out.splitlines():
                if "FAILED" in line:
                    print(f"    {line.strip()}")
            if rc == 0:
                failures += 1
            target.write_bytes(original)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
            assert path.read_bytes() == raw, f"还原失败：{path}"
        print("[restore] 已逐字节还原")

    rc, out = run_tests()
    print(f"[post-restore] rc={rc}  {summary(out)}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
