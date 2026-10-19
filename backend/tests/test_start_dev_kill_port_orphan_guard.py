"""start-dev.bat `:kill_port` 必须清掉 uvicorn --reload 的孤儿 worker（2026-10-19 实测）。

## 现象

重启 start-dev.bat 后，9980 上同时有新旧两个后端：`netstat` 列出两条
`0.0.0.0:9980 LISTENING`，其中一条的 PID 早已不存在；请求随机落到旧进程上，
旧进程读的是改 `.env` 之前的配置（ENCRYPTION_KEY 为空 ⇒ 保存 API Key 503）。

## 根因

uvicorn --reload 的 supervisor 创建监听 socket，经 multiprocessing spawn 把句柄
复制给 worker。旧 `:kill_port` 只对 OwningProcess 执行 `taskkill /F`（没有 /T）：
杀掉 supervisor ⇒ worker 成孤儿，仍持有监听句柄；netstat 继续把这个 socket 记在
**已死的 supervisor PID** 名下，下一次 `:kill_port` 杀已死 PID 是空操作。uvicorn 以
SO_REUSEADDR 绑定，新后端与孤儿共享端口。另外 `Get-NetTCPConnection` 会把同地址的
重复绑定折叠成一条，只用它取 owner 会漏掉其中一个进程。

## 判据

真实复现「supervisor 先死、spawn worker 持句柄存活」，先证明旧逻辑够不着孤儿，
再执行 start-dev.bat 里**原样提取**的 `:kill_port` 命令，断言孤儿被杀、端口释放。
只作用于随机空闲端口及其 owner / spawn 子进程，不碰任何真实服务。
"""
from __future__ import annotations

import ctypes
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BAT = REPO_ROOT / "start-dev.bat"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="监听句柄跨进程共享是 Windows 语义"
)

_SUPERVISOR = '''
import multiprocessing as mp
import os
import socket
import sys
import time


def worker(sock):
    # 只持有继承来的监听句柄，模拟 uvicorn --reload 的 spawn worker。
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    port, ready = int(sys.argv[1]), sys.argv[2]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(16)
    child = mp.get_context("spawn").Process(target=worker, args=(sock,))
    child.start()
    time.sleep(4.0)  # worker 经 resource_sharer 取句柄需要 supervisor 仍存活
    with open(ready, "w", encoding="ascii") as fh:
        fh.write(str(child.pid))
    os._exit(0)  # supervisor 先死，worker 成孤儿
'''


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def _listener_owners(port: int) -> set[int]:
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True, errors="replace"
    ).stdout
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.M)
    return {int(m.group(1)) for m in pattern.finditer(out)}


def _kill_port_command(port: int) -> str:
    text = BAT.read_bytes().decode("ascii")
    section = re.search(r"^:kill_port\r?\n(.*?)^exit /b 0", text, re.M | re.S)
    assert section, "start-dev.bat 缺少 :kill_port 子过程"
    call = re.search(
        r'^powershell\b[^"\r\n]*?\s-Command\s+"(.*?)"', section.group(1), re.M | re.S
    )
    assert call, ":kill_port 必须是单次 powershell 调用（便于原样提取验证）"
    return call.group(1).replace("%~1", str(port))


def test_kill_port_reaps_orphaned_spawn_worker(tmp_path: Path) -> None:
    port = _free_port()
    script = tmp_path / "orphan_supervisor.py"
    script.write_text(_SUPERVISOR, encoding="utf-8")
    ready = tmp_path / "worker.pid"
    supervisor = subprocess.Popen([sys.executable, str(script), str(port), str(ready)])
    worker_pid = 0
    try:
        supervisor.wait(timeout=90)
        worker_pid = int(ready.read_text(encoding="ascii"))

        # 复现前提：supervisor 已死，孤儿仍在监听，netstat 只认已死的 owner。
        owners = _listener_owners(port)
        assert _alive(worker_pid), "复现失败：spawn worker 没有存活"
        assert _accepts(port), "复现失败：孤儿 worker 没有持有监听句柄"
        assert owners and worker_pid not in owners, owners
        assert not any(_alive(pid) for pid in owners), (
            "复现失败：owner 仍存活，旧逻辑本来就能杀到，本测试证明不了任何事"
        )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _kill_port_command(port)],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        deadline = time.time() + 15
        while time.time() < deadline and (_alive(worker_pid) or _accepts(port)):
            time.sleep(0.2)
        assert not _alive(worker_pid), f"孤儿 worker 未被清理：{result.stderr[-400:]}"
        assert not _accepts(port), "端口仍可连接，说明还有进程持有监听句柄"
    finally:
        if worker_pid and _alive(worker_pid):
            subprocess.run(["taskkill", "/PID", str(worker_pid), "/F", "/T"],
                           capture_output=True)
        if supervisor.poll() is None:
            supervisor.kill()
