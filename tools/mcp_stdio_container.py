#!/usr/bin/env python
"""Run stdio MCP servers in self-cleaning Docker containers.

The wrapper never puts credentials on the command line.  A managed container is
labelled with the workspace and owner process identity, then removed in
``finally``.  A later wrapper invocation also reaps labelled containers whose
owner no longer exists, covering abrupt IDE termination.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
MANAGED_LABEL = "com.gt-plan.mcp-managed"
WORKSPACE_LABEL = "com.gt-plan.workspace"
OWNER_PID_LABEL = "com.gt-plan.owner-pid"
OWNER_START_LABEL = "com.gt-plan.owner-start"
SESSION_LABEL = "com.gt-plan.session"
WORKSPACE_ID = hashlib.sha256(str(ROOT.resolve()).lower().encode("utf-8")).hexdigest()[:16]
POSTGRES_IMAGE = "crystaldba/postgres-mcp"

_SERVER_SPECS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "postgres": (POSTGRES_IMAGE, "DATABASE_URI", ("--access-mode=restricted",)),
}


class WrapperError(RuntimeError):
    """A lifecycle precondition failed before the MCP server started."""


def _docker_capture(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _process_start_token(pid: int) -> str | None:
    """Return a process creation token, so PID reuse cannot keep an orphan alive."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        class FILETIME(ctypes.Structure):
            _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
            ok = ctypes.windll.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel), ctypes.byref(user),
            )
            if not ok:
                return None
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            if exit_code.value != 259:  # STILL_ACTIVE
                return None
            return str((created.high << 32) | created.low)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        # Linux /proc stat field 22 is the process start time in clock ticks.
        return Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()[21]
    except (OSError, IndexError):
        return None


def _inspect(ids: Iterable[str]) -> list[dict[str, Any]]:
    values = [value for value in ids if value]
    if not values:
        return []
    proc = _docker_capture("inspect", *values)
    data = json.loads(proc.stdout.decode("utf-8", errors="strict"))
    return data if isinstance(data, list) else []


def _container_ids(*filters: str) -> list[str]:
    args = ["ps", "-a", "--format", "{{.ID}}"]
    for value in filters:
        args.extend(("--filter", value))
    proc = _docker_capture(*args)
    return [line.strip() for line in proc.stdout.decode("utf-8", "replace").splitlines() if line.strip()]


def _container_name(item: dict[str, Any]) -> str:
    return str(item.get("Name") or "").lstrip("/")


def _labels(item: dict[str, Any]) -> dict[str, str]:
    raw = (item.get("Config") or {}).get("Labels") or {}
    return {str(k): str(v) for k, v in raw.items()}


def _remove_container(name: str) -> bool:
    if not name:
        return False
    proc = _docker_capture("rm", "-f", name, check=False)
    return proc.returncode == 0


def cleanup_stale_managed(*, dry_run: bool = False, exclude_session: str = "") -> list[str]:
    """Remove only labelled containers whose exact owner process is gone."""
    removed: list[str] = []
    ids = _container_ids(f"label={MANAGED_LABEL}=true", f"label={WORKSPACE_LABEL}={WORKSPACE_ID}")
    for item in _inspect(ids):
        labels = _labels(item)
        if exclude_session and labels.get(SESSION_LABEL) == exclude_session:
            continue
        try:
            owner_pid = int(labels.get(OWNER_PID_LABEL, "0"))
        except ValueError:
            owner_pid = 0
        expected_start = labels.get(OWNER_START_LABEL)
        current_start = _process_start_token(owner_pid)
        if owner_pid > 0 and expected_start and current_start == expected_start:
            continue
        name = _container_name(item)
        if name and (dry_run or _remove_container(name)):
            removed.append(name)
    return removed


def _legacy_candidates() -> list[dict[str, Any]]:
    """Return conservative, unlabelled restricted postgres MCP candidates."""
    candidates: list[dict[str, Any]] = []
    for item in _inspect(_container_ids(f"ancestor={POSTGRES_IMAGE}")):
        if _labels(item).get(MANAGED_LABEL) == "true":
            continue
        config = item.get("Config") or {}
        image = str(config.get("Image") or "")
        cmd = [str(part) for part in (config.get("Cmd") or [])]
        mounts = item.get("Mounts") or []
        if image != POSTGRES_IMAGE or "--access-mode=restricted" not in cmd or mounts:
            continue
        candidates.append(item)
    candidates.sort(key=lambda item: str(item.get("Created") or ""), reverse=True)
    return candidates


def cleanup_legacy(*, apply: bool, keep: set[str]) -> list[str]:
    """List or remove explicitly approved pre-wrapper containers."""
    affected: list[str] = []
    for item in _legacy_candidates():
        name = _container_name(item)
        if not name or name in keep:
            continue
        if not apply or _remove_container(name):
            affected.append(name)
    return affected


def _cleanup_own(name: str) -> None:
    # ``docker run --rm`` only removes after the container exits.  If the stdio
    # client disappears without EOF, force-removing our labelled container is
    # the bounded cleanup required here.
    _remove_container(name)


def _heartbeat_writer(path: Path, stop: threading.Event) -> None:
    while not stop.wait(2.0):
        try:
            path.touch()
        except OSError:
            return


_HEARTBEAT_SHELL = """
exec 3<&0
/app/docker-entrypoint.sh postgres-mcp "$@" <&3 &
child=$!
while kill -0 "$child" 2>/dev/null; do
  now=$(date +%s)
  modified=$(stat -c %Y /gt-mcp-heartbeat/alive 2>/dev/null || echo 0)
  if [ $((now - modified)) -gt 30 ]; then
    kill "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    exit 0
  fi
  sleep 2
done
wait "$child"
""".strip()


def run_server(server: str) -> int:
    if server not in _SERVER_SPECS:
        raise WrapperError(f"unknown MCP server: {server}")
    image, credential_env, server_args = _SERVER_SPECS[server]
    if not os.environ.get(credential_env):
        raise WrapperError(f"required environment variable is missing: {credential_env}")

    session_id = uuid.uuid4().hex
    owner_pid = os.getpid()
    owner_start = _process_start_token(owner_pid)
    if not owner_start:
        raise WrapperError("cannot determine wrapper process start time")
    cleanup_stale_managed(exclude_session=session_id)

    name = f"gt-plan-{server}-mcp-{session_id[:12]}"
    with tempfile.TemporaryDirectory(prefix="gt_mcp_") as tmp:
        tmp_path = Path(tmp).resolve()
        cidfile = str(tmp_path / "container.cid")
        heartbeat = tmp_path / "alive"
        heartbeat.touch()
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat_writer, args=(heartbeat, heartbeat_stop),
            name="gt-mcp-heartbeat", daemon=True,
        )
        heartbeat_thread.start()
        command = [
            "docker", "run", "-i", "--rm", "--name", name,
            "--cidfile", cidfile,
            "--mount", f"type=bind,source={tmp_path},target=/gt-mcp-heartbeat,readonly",
            "--label", f"{MANAGED_LABEL}=true",
            "--label", f"{WORKSPACE_LABEL}={WORKSPACE_ID}",
            "--label", f"{OWNER_PID_LABEL}={owner_pid}",
            "--label", f"{OWNER_START_LABEL}={owner_start}",
            "--label", f"{SESSION_LABEL}={session_id}",
            "-e", credential_env,
            "--entrypoint", "/bin/sh",
            image, "-c", _HEARTBEAT_SHELL, "mcp-server", *server_args,
        ]
        proc = subprocess.Popen(command)
        previous: dict[int, Any] = {}
        stopping = False

        def stop_child(_signum: int, _frame: Any) -> None:
            nonlocal stopping
            if stopping:
                return
            stopping = True
            if proc.poll() is None:
                proc.terminate()
            # IDE stdio clients may kill the wrapper immediately after SIGTERM;
            # clean synchronously inside the handler instead of relying only on finally.
            _cleanup_own(name)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                previous[sig] = signal.signal(sig, stop_child)
            except (OSError, ValueError):
                pass
        try:
            return int(proc.wait())
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=3)
            for sig, handler in previous.items():
                try:
                    signal.signal(sig, handler)
                except (OSError, ValueError):
                    pass
            _cleanup_own(name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one managed stdio MCP server")
    run.add_argument("server", choices=sorted(_SERVER_SPECS))

    cleanup = sub.add_parser("cleanup", help="inspect or clean MCP containers")
    cleanup.add_argument("--legacy", action="store_true", help="include conservative pre-wrapper candidates")
    cleanup.add_argument("--apply", action="store_true", help="perform removal; default is dry-run")
    cleanup.add_argument("--keep", action="append", default=[], help="container name to retain")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_server(args.server)
        managed = cleanup_stale_managed(dry_run=not args.apply)
        legacy = cleanup_legacy(apply=args.apply, keep=set(args.keep)) if args.legacy else []
        action = "removed" if args.apply else "would_remove"
        print(json.dumps({action: {"managed": managed, "legacy": legacy}}, ensure_ascii=False, indent=2))
        return 0
    except (WrapperError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"[mcp-wrapper] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
