# -*- coding: utf-8 -*-
"""一次性部署辅助：SSH 执行远程命令（用完即删）。

用法:
    python _ssh_run.py "command"            # 执行并回显
    python _ssh_run.py --put 本地路径 远端路径
"""
import sys
from pathlib import Path

import paramiko

HOST = "182.92.234.38"
USER = "root"
PASSWORD = "Zaqc2026"


def client() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    return c


def run(cmd: str, timeout: int = 300) -> int:
    c = client()
    try:
        stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print("[stderr]", err, end="" if err.endswith("\n") else "\n", file=sys.stderr)
        return code
    finally:
        c.close()


def put(local: str, remote: str) -> None:
    c = client()
    try:
        sftp = c.open_sftp()
        sftp.put(local, remote)
        sftp.close()
        print(f"uploaded {local} -> {remote}")
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--put":
        put(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2:
        sys.exit(run(sys.argv[1]))
    else:
        print("usage: _ssh_run.py [command | --put local remote]")
        sys.exit(2)
