"""变异反证：clean close 的冻结身份必须服务端派生（四条判据各自可被打红）。

用法（仓库根）：
    .venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_close_capture_identity_guards.py

反证的缺陷：`POST …/rooms/{id}/close-intents` 曾把 `adapter_build_digest` /
`contributor_snapshot_digest` 从请求体读取（`str(payload.get(...) or "")`），而客户端
无从得知这两个值 ⇒ 每一次真实 clean close 都 422 `invalid_identity`。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
REPOSITORY = BACKEND / "app" / "services" / "workpaper_sync" / "repository.py"
ROUTER = BACKEND / "app" / "routers" / "wp_sync_router.py"
TEST = "tests/workpaper_sync/test_close_capture_frozen_identity.py"
SELECT = "close_path or request_body or froze_as_base or fails_visible"

MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "repository 重新接收 adapter_build_digest 形参（调用方又能编一个 digest）",
        REPOSITORY,
        "        entry_id: str,\n"
        "        room_id: uuid.UUID,\n"
        "    ) -> CloseReconcileOutcome:",
        "        entry_id: str,\n"
        "        room_id: uuid.UUID,\n"
        '        adapter_build_digest: str = "",\n'
        "    ) -> CloseReconcileOutcome:",
    ),
    (
        "路由重新从请求体读 adapter_build_digest",
        ROUTER,
        '    participant_id = _uuid_field(payload, "participant_id")\n'
        "    try:\n"
        "        opened = await svc.close_intents().open_close_intent(",
        '    participant_id = _uuid_field(payload, "participant_id")\n'
        '    _client_digest = str(payload.get("adapter_build_digest") or "")\n'
        "    try:\n"
        "        opened = await svc.close_intents().open_close_intent(",
    ),
    (
        "代码身份改查「任意一行 representation」而不按 base 的 id 绑定",
        REPOSITORY,
        "                sa.select(WorkpaperContentRepresentation.adapter_build_digest).where(\n"
        "                    WorkpaperContentRepresentation.id == confirmation.representation_id\n"
        "                )",
        "                sa.select(\n"
        "                    WorkpaperContentRepresentation.adapter_build_digest\n"
        "                ).limit(1)",
    ),
    (
        "取不到/非法的代码身份退回空串而不抛（把「身份未知」冻结成合法身份）",
        REPOSITORY,
        "        if digest is None:\n"
        "            raise IdentityError(\n"
        '                "close-capture 无法冻结代码身份：client confirmation 的 representation "\n'
        '                f"{confirmation.representation_id} 不存在"\n'
        "            )\n"
        "        if not is_digest(str(digest)):",
        "        if digest is None:\n"
        '            return ""\n'
        "        if False:",
    ),
]


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        [
            str(REPO / ".venv" / "Scripts" / "python.exe"),
            "-m",
            "pytest",
            TEST,
            "-q",
            "--tb=line",
            "-p",
            "no:randomly",
            "-k",
            SELECT,
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def summary(out: str) -> str:
    for line in reversed(out.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    return out[-140:].replace("\n", " ")


def main() -> int:
    originals = {path: path.read_bytes() for path in {REPOSITORY, ROUTER}}
    rc, out = run_tests()
    print(f"[baseline] rc={rc}  {summary(out)}")
    if rc != 0:
        print("baseline not green, abort")
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
                print(f"[MISS] anchor hit {hits} times (need 1): {label}")
                failures += 1
                continue
            target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            rc, out = run_tests()
            print(f"[{'KILLED' if rc != 0 else 'SURVIVED<<<'}] {label}")
            print(f"    {summary(out)}")
            if rc == 0:
                failures += 1
            target.write_bytes(original)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
            assert path.read_bytes() == raw, f"restore failed: {path}"
        print("[restore] byte-for-byte restored")

    rc, out = run_tests()
    print(f"[post-restore] rc={rc}  {summary(out)}")
    return 1 if failures or rc != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
