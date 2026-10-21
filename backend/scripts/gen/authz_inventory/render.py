"""确定性 JSON 输出与检查模式比对（design §4.12 render；需求 1.1 / 9.1「同一仓库状态下重复生成逐字节相同」）。

- ``dumps(payload, *, roots=())``：键排序、``ensure_ascii=False``、``indent=2``、LF 换行、末尾恰一个换行。
  输出前先 ``find_forbidden``：时间、机器名、绝对路径（``roots`` 与本机主目录 / 临时目录 / 当前目录，以及任何
  盘符路径与常见 POSIX 根目录）、行号、浮点数、非字符串键与表示行号 / 时间 / 机器的键名一律拒绝
  （``RenderError``，中文逐项列出 JSON 位置），不静默剔除。
- ``sort_entries(entries, fields)``：条目按字段排序（默认 文件 → 完整路径 → 方法），字段相同时再按条目自身的
  规范化 JSON 排序 —— 结果只由内容决定，与输入顺序无关。条目内的列表（如辅助函数链）保持调用方给的顺序。
- ``write_text(path, text)``：原子写（同目录临时文件 + 替换），按字节写出，不做换行转换。
- ``utf8_console()``：控制台改按 UTF-8 输出（两个生成脚本与 ``selfcheck`` 命令行入口共用）。
- ``diff_entries(old, new, fields)`` / ``describe_diff``：检查模式逐条比对，给出新增 / 消失 / 变化（列出不同的字段）。
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENTRY_FIELDS = ("file", "path", "method")
FORBIDDEN_KEYS = frozenset({
    "line", "lineno", "line_no", "line_number", "end_lineno", "col_offset", "end_col_offset",
    "generated_at", "generated_on", "timestamp", "time", "date", "datetime", "created_at", "updated_at", "mtime",
    "elapsed", "elapsed_seconds", "duration", "hostname", "host", "machine", "computer_name", "node_name",
    "cwd", "abs_path", "absolute_path",
})
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}|(?<![\d:])\d{1,2}:\d{2}:\d{2}(?![\d:])")
_LINE = re.compile(r"\.(?:py|pyi|ts|tsx|js|mjs|vue|sql|json|md)[:(]\d+|#L\d+|\blines? \d+|第 ?\d+ ?行")
_DRIVE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|^\\\\[^\\]")
_POSIX_ROOTS = ("/home/", "/Users/", "/tmp/", "/var/", "/usr/", "/opt/", "/mnt/", "/root/", "/private/", "/etc/",
                "/srv/", "/Volumes/")
_MISSING = object()


class RenderError(ValueError):
    """产物不能确定性输出（信息为中文原因）。"""


def _norm_path(text: str) -> str:
    return text.replace("\\", "/").rstrip("/").lower()


def _local_markers(roots: Iterable[str | os.PathLike[str]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """本机特有的取值：(绝对路径前缀，机器名)。"""
    paths = {str(Path(r).resolve()) for r in roots} | {str(Path.home()), tempfile.gettempdir(), os.getcwd()}
    names = {socket.gethostname(), platform.node(), os.environ.get("COMPUTERNAME", "")}
    return (tuple(sorted({_norm_path(p) for p in paths if len(_norm_path(p)) > 3})),
            tuple(sorted({n.lower() for n in names if len(n) >= 3})))


def _string_problems(text: str, prefixes: tuple[str, ...], machines: tuple[str, ...]) -> list[str]:
    problems = []
    lowered = _norm_path(text) + "/"
    if _DRIVE.search(text) or text.startswith(_POSIX_ROOTS) \
            or any(re.search(rf"(?:^|[\s'\"=(]){re.escape(p)}/", lowered) for p in prefixes):
        problems.append("绝对路径")
    if _TIME.search(text):
        problems.append("时间")
    if _LINE.search(text):
        problems.append("行号")
    word = text.lower()
    if any(re.search(rf"(?<![0-9a-z]){re.escape(m)}(?![0-9a-z])", word) for m in machines):
        problems.append("机器名")
    return problems


def find_forbidden(payload: Any, *, roots: Iterable[str | os.PathLike[str]] = ()) -> list[str]:
    """列出产物中随运行变化或本机特有的内容（每项：「JSON 位置：原因」）；为空即可确定性输出。"""
    prefixes, machines = _local_markers(roots)
    found: list[str] = []

    def walk(value: Any, where: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    found.append(f"{where}：键 {key!r} 不是字符串")
                    continue
                if key.lower() in FORBIDDEN_KEYS:
                    found.append(f"{where}.{key}：键名表示行号 / 时间 / 机器等随运行变化的信息")
                walk(item, f"{where}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{where}[{index}]")
        elif isinstance(value, float):
            found.append(f"{where}：浮点数 {value!r}（耗时等随运行变化的量不得进入产物）")
        elif isinstance(value, str):
            found.extend(f"{where}：{reason}（{value[:80]!r}）" for reason in _string_problems(value, prefixes, machines))
        elif value is not None and not isinstance(value, (bool, int)):
            found.append(f"{where}：{type(value).__name__} 不是 JSON 取值（集合须先排序成列表）")

    walk(payload, "$")
    return found


def dumps(payload: Any, *, roots: Iterable[str | os.PathLike[str]] = ()) -> str:
    """确定性 JSON 文本；含随运行变化或本机特有的内容时抛 ``RenderError``。"""
    problems = find_forbidden(payload, roots=roots)
    if problems:
        raise RenderError("产物含随运行变化或本机特有的内容，拒绝输出：\n" + "\n".join(f"- {p}" for p in problems))
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sortable(value: Any) -> tuple[int, Any]:
    if value is None:
        return (0, "")
    if isinstance(value, str):
        return (1, value)
    if isinstance(value, (bool, int)):
        return (2, int(value))
    return (3, _canon(value))


def _entry_key(entry: Mapping[str, Any], fields: Sequence[str]) -> tuple[tuple[int, Any], ...]:
    missing = [f for f in fields if f not in entry]
    if missing:
        raise RenderError(f"条目缺少排序字段 {missing}：{_canon(entry)[:120]}")
    return tuple(_sortable(entry[f]) for f in fields)


def sort_entries(entries: Iterable[Mapping[str, Any]], fields: Sequence[str] = ENTRY_FIELDS) -> list[Any]:
    """按 ``fields`` 排序；字段相同的再按规范化 JSON 排序（与输入顺序无关）。"""
    return sorted(entries, key=lambda e: (_entry_key(e, fields), _canon(e)))


def utf8_console() -> None:
    """控制台改按 UTF-8 输出（Windows 下被管道捕获时默认是本地代码页），不随 ``PYTHONIOENCODING`` 变化。"""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "").replace("_", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def write_text(path: str | os.PathLike[str], text: str) -> None:
    """原子写出（同目录临时文件 + 替换）；按 UTF-8 字节写，不做换行转换。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class EntryDiff:
    """检查模式的比对结果。键 = 各排序字段的取值。"""

    added: tuple[Any, ...]
    removed: tuple[Any, ...]
    changed: tuple[tuple[tuple[Any, ...], tuple[str, ...]], ...]  # (键, 取值不同的字段)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_entries(old: Iterable[Mapping[str, Any]], new: Iterable[Mapping[str, Any]],
                 fields: Sequence[str] = ENTRY_FIELDS) -> EntryDiff:
    """逐条比对（取值按规范化 JSON 比较，tuple 与 list 视为相同）；同一侧键重复即 ``RenderError``。"""

    def index(entries: Iterable[Mapping[str, Any]], side: str) -> dict[tuple[Any, ...], dict[str, Any]]:
        out: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in entries:
            plain = json.loads(_canon(entry))
            key = tuple(plain.get(f) for f in fields)
            if key in out:
                raise RenderError(f"{side}里有重复的条目键 {key}")
            out[key] = plain
        return out

    before, after = index(old, "已提交的产物"), index(new, "现算结果")
    order = lambda keys: sorted(keys, key=lambda k: tuple(_sortable(x) for x in k))  # noqa: E731
    changed = []
    for key in order(before.keys() & after.keys()):
        fields_changed = tuple(sorted(f for f in before[key].keys() | after[key].keys()
                                      if before[key].get(f, _MISSING) != after[key].get(f, _MISSING)))
        if fields_changed:
            changed.append((key, fields_changed))
    return EntryDiff(tuple(after[k] for k in order(after.keys() - before.keys())),
                     tuple(before[k] for k in order(before.keys() - after.keys())), tuple(changed))


def describe_diff(diff: EntryDiff, fields: Sequence[str] = ENTRY_FIELDS) -> list[str]:
    """比对结果的中文逐条说明：新增 / 消失 / 变化（变化列出字段名）。"""
    label = lambda key: " ".join("—" if v is None else str(v) for v in key)  # noqa: E731
    lines = [f"新增：{label(tuple(e.get(f) for f in fields))}" for e in diff.added]
    lines += [f"消失：{label(tuple(e.get(f) for f in fields))}" for e in diff.removed]
    lines += [f"变化：{label(key)}（字段：{'、'.join(names)}）" for key, names in diff.changed]
    return lines
