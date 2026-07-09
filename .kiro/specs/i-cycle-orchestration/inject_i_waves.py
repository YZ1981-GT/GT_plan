"""为 I1–I6 tasks.md 注入 JSON waves 块（替换 mermaid 依赖图）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SPECS_DIR = Path(__file__).resolve().parent.parent

# spec_folder, wave-2..wave-9
WAVE_CONFIGS: list[tuple[str, ...]] = [
    (
        "i1-intangible-assets",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 15)],
        ["3.1", "3.2", "3.3"],
        ["3.4", "3.5", "3.6", "3.7"],
        [f"4.{i}" for i in range(1, 16)],
        ["5.1", "5.2", "5.3", "5.4", "5.5"],
        [f"6.{i}" for i in range(1, 8)],
        [f"7.{i}" for i in range(1, 7)],
    ),
    (
        "i2-development-expenditure",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 11)],
        ["3.1", "3.2", "3.3"],
        ["3.4", "3.5", "3.6", "3.7"],
        [f"4.{i}" for i in range(1, 13)],
        ["5.1", "5.2", "5.3", "5.4", "5.5"],
        [f"6.{i}" for i in range(1, 8)],
        [f"7.{i}" for i in range(1, 6)],
    ),
    (
        "i3-goodwill",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 11)],
        ["3.1", "3.2", "3.3"],
        ["3.4", "3.5", "3.6"],
        [f"4.{i}" for i in range(1, 11)],
        ["5.1", "5.2", "5.3", "5.4", "5.5"],
        [f"6.{i}" for i in range(1, 6)],
        [f"7.{i}" for i in range(1, 5)],
    ),
    (
        "i4-long-term-prepaid",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 9)],
        ["3.1", "3.2", "3.3"],
        ["3.4", "3.5"],
        [f"4.{i}" for i in range(1, 10)],
        ["5.1", "5.2", "5.3", "5.4"],
        [f"6.{i}" for i in range(1, 5)],
        [f"7.{i}" for i in range(1, 5)],
    ),
    (
        "i5-other-noncurrent-assets",
        ["2.1"],
        [f"2.{i}" for i in range(2, 7)],
        ["3.1", "3.2"],
        ["3.3", "3.4"],
        [f"4.{i}" for i in range(1, 7)],
        ["5.1", "5.2", "5.3", "5.4"],
        [f"6.{i}" for i in range(1, 5)],
        [f"7.{i}" for i in range(1, 5)],
    ),
    (
        "i6-research-development-expense",
        ["2.1"],
        [f"2.{i}" for i in range(2, 9)],
        ["3.1", "3.2", "3.3"],
        ["3.4", "3.5", "3.6"],
        [f"4.{i}" for i in range(1, 8)],
        ["5.1", "5.2", "5.3", "5.4"],
        [f"6.{i}" for i in range(1, 7)],
        [f"7.{i}" for i in range(1, 6)],
    ),
]


def _wave(
    wid: str,
    name: str,
    tasks: list[str],
    *,
    parallel: bool | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": wid, "name": name, "tasks": tasks}
    if parallel is None:
        parallel = len(tasks) > 1
    if parallel:
        entry["parallel"] = True
    return entry


def build_waves_json(
    w2: list[str],
    w3: list[str],
    w4: list[str],
    w5: list[str],
    w6: list[str],
    w7: list[str],
    w8: list[str],
    w9: list[str],
) -> str:
    waves = [
        _wave("wave-0", "Phase0 双源输入", ["0.1", "0.2"]),
        {"id": "wave-1", "name": "Phase1 注册+契约", "tasks": ["1.1", "1.2"]},
        _wave("wave-2", "Phase2 公式/领域引擎", w2),
        _wave("wave-3", "Phase2 PBT", w3),
        _wave("wave-4", "Phase3 基础 composable", w4),
        _wave("wave-5", "Phase3 sheet/domain composables", w5),
        _wave("wave-6", "Phase4 Vue 子组件", w6),
        _wave("wave-7", "Phase5 后端", w7),
        _wave("wave-8", "Phase6 集成联动", w8),
        _wave("wave-9", "Phase7 测试验收", w9),
    ]
    return json.dumps({"waves": waves}, indent=2, ensure_ascii=False)


MERMAID_BLOCK = re.compile(
    r"## Task Dependency Graph\s*\n\s*```mermaid\s*\n.*?```",
    re.DOTALL,
)
JSON_BLOCK = re.compile(
    r"## Task Dependency Graph\s*\n\s*```json\s*\n.*?```",
    re.DOTALL,
)


def inject(args: tuple[str, ...]) -> None:
    spec_folder, w2, w3, w4, w5, w6, w7, w8, w9 = args
    path = SPECS_DIR / spec_folder / "tasks.md"
    text = path.read_text(encoding="utf-8")
    replacement = (
        "## Task Dependency Graph\n\n```json\n"
        + build_waves_json(w2, w3, w4, w5, w6, w7, w8, w9)
        + "\n```"
    )
    if "## Task Dependency Graph" not in text:
        raise ValueError(f"No Task Dependency Graph section: {path}")
    if '"waves":' in text and "```mermaid" not in text:
        new_text, n = JSON_BLOCK.subn(replacement, text, count=1)
        if n == 1:
            path.write_text(new_text, encoding="utf-8")
            print(f"refresh: {spec_folder}")
            return
        print(f"skip (already JSON): {spec_folder}")
        return
    new_text, n = MERMAID_BLOCK.subn(replacement, text, count=1)
    if n != 1:
        raise ValueError(f"Could not patch: {path}")
    path.write_text(new_text, encoding="utf-8")
    print(f"ok: {spec_folder}")


def main() -> None:
    for cfg in WAVE_CONFIGS:
        inject(cfg)


if __name__ == "__main__":
    main()
