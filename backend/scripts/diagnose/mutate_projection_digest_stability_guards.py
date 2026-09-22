"""变异反证：projection digest 的表示稳定性判据可被打红。

用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_projection_digest_stability_guards.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "services" / "workpaper_sync" / "content_mutation.py"
TEST = "tests/workpaper_sync/test_projection_digest_is_representation_stable.py"
PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"

MUTATIONS: list[tuple[str, str, str]] = [
    (
        "退回改动前的口径（直接 json_safe 原值）",
        '                "value": _canonical_value_for_digest(value),',
        '                "value": _json_safe(value.value),',
    ),
    (
        "不做 Decimal normalize（0.0 与 0 仍分叉）",
        "    if isinstance(normalized, Decimal):\n"
        "        if normalized == 0:\n"
        "            # `Decimal('-0')` / `Decimal('0E+1')` 也要归一到同一个零。\n"
        "            normalized = Decimal(0)\n"
        "        else:\n"
        "            normalized = normalized.normalize()",
        "    if isinstance(normalized, Decimal):\n"
        "        pass  # MUTATED: 不归一",
    ),
    (
        "把 None 也折叠成零（语义折叠，必须被反向锁抓到）",
        "    if normalized is MISSING:\n"
        "        return json_safe(field.value)",
        "    if normalized is MISSING or normalized is None:\n"
        "        return json_safe(0)",
    ),
    (
        "规范化失败改成抛出（会把坏值升级成 flush 失败）",
        "    except Exception:  # noqa: BLE001 - 规范化失败不得让 flush 失败，见 docstring\n"
        "        return json_safe(field.value)",
        "    except Exception:  # MUTATED\n        raise",
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
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def summary(out: str) -> str:
    for line in out.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    return out[-140:].replace("\n", " ")


def main() -> int:
    original = TARGET.read_bytes()
    eol = "\r\n" if b"\r\n" in original else "\n"
    rc, out = run_tests()
    print(f"[baseline] rc={rc}  {summary(out)}")
    if rc != 0:
        print("基线不绿，终止")
        return 1

    failures = 0
    try:
        for label, old_lf, new_lf in MUTATIONS:
            old = old_lf.replace("\n", eol)
            new = new_lf.replace("\n", eol)
            text = original.decode("utf-8")
            hits = text.count(old)
            if hits != 1:
                print(f"[MISS] 锚点命中 {hits} 次（需 1）：{label}")
                failures += 1
                continue
            TARGET.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary(out)}")
            if rc == 0:
                failures += 1
            TARGET.write_bytes(original)
    finally:
        TARGET.write_bytes(original)
        assert TARGET.read_bytes() == original, "还原失败！"
        print("[restore] 已逐字节还原")

    rc, out = run_tests()
    print(f"[post-restore] rc={rc}  {summary(out)}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
