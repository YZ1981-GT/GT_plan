# -*- coding: utf-8 -*-
"""生成 Task 44 probe 注册表数据文件（`backend/data/workpaper_task44_pilot_gate_probes.json`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 44
Requirements: 12.2, 14.7, 14.9

数据文件是 gate 里 probe 声明的 **canonical 投影**：

* `--apply` 重生成；
* `--check` 只读复算并逐字节比对 —— 不一致即非零退出。

🔴 为什么要落一份数据文件：让「分母被人悄悄改小」在 `git diff` 里可见。gate 自己已经与
`tasks.md` 正文双向锁死，但那条锁只在**运行 gate**时生效；数据文件让分母变化在评审阶段
就能看见（`registry_digest` 一变，diff 里就是一行）。

🔴 比**序列化字节**而不是 `json.loads` 后的对象：后者会把 tuple↔list 往返差异报成
「不一致」（Task 43 的 `--check` 实测踩过）。

用法（仓库根）::

    py -3 backend/scripts/gen/generate_workpaper_task44_pilot_probe_registry.py --apply
    py -3 backend/scripts/gen/generate_workpaper_task44_pilot_probe_registry.py --check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_GATE_PY = _BACKEND / "scripts/check/check_task44_oo94_excel_pilot_gate.py"


def load_gate() -> ModuleType:
    """按路径加载 gate 模块（`backend/scripts/check/` 不是 package）。"""
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    spec = importlib.util.spec_from_file_location("_task44_gate", _GATE_PY)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径级失效
        raise RuntimeError(f"无法加载 gate 模块：{_GATE_PY}")
    module = importlib.util.module_from_spec(spec)
    # 🔴 必须先进 `sys.modules` 再 exec：gate 用了 `from __future__ import annotations`，
    # `@dataclass` 解析字符串注解时会去 `sys.modules[cls.__module__]` 取命名空间 ——
    # 不注册就是 `AttributeError: 'NoneType' object has no attribute '__dict__'`（实测）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_payload() -> tuple[Path, bytes]:
    gate = load_gate()
    payload = gate.probe_registry_payload()
    gate.assert_registry_coverage(payload)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return Path(gate.REGISTRY_JSON), data.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入数据文件")
    parser.add_argument("--check", action="store_true", help="只读：复算并比对字节")
    args = parser.parse_args(argv)
    if not (args.apply or args.check):
        parser.print_help()
        return 2
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    try:
        path, data = build_payload()
    except Exception as exc:  # noqa: BLE001 - 生成失败必须 fail closed
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 2

    payload = json.loads(data.decode("utf-8"))
    summary = (
        f"probes={len(payload['probes'])} per_pilot={payload['per_pilot_probe_count']} "
        f"gate={payload['gate_probe_count']} rows={payload['total_probe_rows']} "
        f"registry_digest={payload['registry_digest']}"
    )
    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"[WRITE] {path.relative_to(_REPO)}  {len(data)} bytes")
        print(f"[OK] {summary}")
        return 0

    if not path.exists():
        print(f"[FAIL] 数据文件不存在：{path.relative_to(_REPO)}")
        return 1
    if path.read_bytes() != data:
        print(f"[FAIL] {path.relative_to(_REPO)} 与重算不一致（probe 分母已漂移）")
        return 1
    print(f"[OK] {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
