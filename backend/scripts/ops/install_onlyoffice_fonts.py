"""给 OnlyOffice 文档服务器装中文 / Arial Narrow 字体（报告正文等 Word 预览与在线编辑的版式依赖它们）。

OnlyOffice 镜像只带开源字体：仿宋、黑体会被换成 Droid Sans Fallback，Arial Narrow 换成 Arial，
行距和分页因此与 Word 不同（报告正文 4 页会转成 5 页）。这些是微软字体，不能放进仓库，
只能从服务器本机的字体目录拷进容器。

做法：字体拷进容器的 ``/usr/share/fonts/truetype/custom/``，再运行容器自带的
``documentserver-generate-allfonts.sh`` 重建字体表。不重建容器，但脚本会重启文档服务与转换服务，
正在在线编辑的人会断开几秒（自动重连）⇒ 必须带 ``--yes`` 才执行。
另存一份到 ``docker/onlyoffice-fonts/``（已 gitignore），docker-compose 挂载这个目录，容器重建后仍在。

用法::

    python backend/scripts/ops/install_onlyoffice_fonts.py --check          # 只查容器里有没有这些字体
    python backend/scripts/ops/install_onlyoffice_fonts.py --yes            # 安装（Windows 默认取 C:\\Windows\\Fonts）
    python backend/scripts/ops/install_onlyoffice_fonts.py --yes --src /path/to/fonts --container audit-onlyoffice

退出码：0 = 字体齐全；1 = 仍缺字体 / 执行失败；2 = 参数不全或未确认。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KEEP_DIR = ROOT / "docker" / "onlyoffice-fonts"
CONTAINER_FONT_DIR = "/usr/share/fonts/truetype/custom/"
ALLFONTS = "/var/www/onlyoffice/documentserver/server/FileConverter/bin/AllFonts.js"
GENERATE = "documentserver-generate-allfonts.sh"

#: 显示名 → (OnlyOffice 字体表里的名字, 字体文件)
FONTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "仿宋": ("FangSong", ("simfang.ttf",)),
    "黑体": ("SimHei", ("simhei.ttf",)),
    "宋体": ("SimSun", ("simsun.ttc",)),
    "楷体": ("KaiTi", ("simkai.ttf",)),
    "Arial Narrow": ("Arial Narrow", ("ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF", "ARIALNBI.TTF")),
}


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def registered(container: str) -> dict[str, bool]:
    """容器字体表里每个字体是否已登记。"""
    out = _run(["docker", "exec", container, "cat", ALLFONTS])
    if out.returncode != 0:
        raise RuntimeError(f"读不到容器字体表：{out.stderr.strip()}")
    return {label: f'["{name}",' in out.stdout for label, (name, _) in FONTS.items()}


def _find_sources(src: Path) -> tuple[list[Path], list[str]]:
    """按文件名（不分大小写）在 ``src`` 下找字体文件；返回 (找到的, 缺的文件名)。"""
    by_name = {p.name.lower(): p for p in src.iterdir() if p.is_file()}
    found, missing = [], []
    for _, files in FONTS.values():
        for name in files:
            path = by_name.get(name.lower())
            (found.append(path) if path else missing.append(name))
    return found, missing


def _report(state: dict[str, bool]) -> bool:
    for label, ok in state.items():
        print(f"  {'✓' if ok else '✗'} {label}")
    return all(state.values())


def install(container: str, src: Path, keep_dir: Path) -> None:
    files, missing = _find_sources(src)
    if missing:
        raise RuntimeError(f"{src} 下缺字体文件：{', '.join(missing)}")
    keep_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, keep_dir / f.name)
        cp = _run(["docker", "cp", str(f), f"{container}:{CONTAINER_FONT_DIR}"])
        if cp.returncode != 0:
            raise RuntimeError(f"拷入容器失败 {f.name}：{cp.stderr.strip()}")
    print(f"已拷入 {len(files)} 个字体文件（另存一份到 {keep_dir}）；正在重建字体表，约 1~3 分钟…")
    gen = _run(["docker", "exec", container, GENERATE], timeout=900)
    if gen.returncode != 0:
        raise RuntimeError(f"重建字体表失败：{(gen.stderr or gen.stdout).strip()[-500:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="给 OnlyOffice 文档服务器装中文 / Arial Narrow 字体")
    parser.add_argument("--container", default="audit-onlyoffice")
    parser.add_argument("--src", type=Path, help="字体所在目录（Windows 默认 C:\\Windows\\Fonts）")
    parser.add_argument("--keep-dir", type=Path, default=DEFAULT_KEEP_DIR,
                        help="另存一份供 docker-compose 挂载（容器重建后仍在）")
    parser.add_argument("--check", action="store_true", help="只检查，不安装")
    parser.add_argument("--yes", action="store_true", help="确认安装（会重启文档服务，在线编辑的人断开几秒）")
    args = parser.parse_args()

    try:
        before = registered(args.container)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"✗ {exc}")
        return 1
    print(f"容器 {args.container} 当前字体：")
    if _report(before) or args.check:
        return 0 if all(before.values()) else 1

    src = args.src or (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" if os.name == "nt" else None)
    if src is None or not src.is_dir():
        print("✗ 请用 --src 指定字体所在目录（需含 simfang.ttf / simhei.ttf / simsun.ttc / simkai.ttf / ARIALN*.TTF）")
        return 2
    if not args.yes:
        print("未执行：安装会重启 OnlyOffice 文档服务（在线编辑的人断开几秒），确认后加 --yes 重新运行")
        return 2
    try:
        install(args.container, src, args.keep_dir)
        after = registered(args.container)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"✗ {exc}")
        return 1
    print("安装后：")
    return 0 if _report(after) else 1


if __name__ == "__main__":
    sys.exit(main())
