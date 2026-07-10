"""一次性脚本：为 K1–K13 tasks.md 注入标准 JSON waves 块（替换 mermaid 依赖图）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent.parent

# (spec_folder, wave-2 tasks, wave-3 PBT tasks, wave-6 vue tasks)
WAVE_CONFIGS: list[tuple[str, list[str], list[str], list[str]]] = [
    (
        "k1-other-receivables",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 12)],
        [f"4.{i}" for i in range(1, 8)],
    ),
    (
        "k2-other-current-assets",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 9)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k3-other-payables",
        ["2.1"],
        [f"2.{i}" for i in range(2, 8)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k4-other-current-liabilities",
        ["2.1"],
        [f"2.{i}" for i in range(2, 7)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k5-provisions",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 10)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k6-held-for-sale",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 10)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k7-deferred-income",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 9)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k8-selling-expenses",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 10)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k9-admin-expenses",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 10)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k10-other-income",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 9)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k11-asset-impairment-loss",
        ["2.1", "2.2"],
        [f"2.{i}" for i in range(3, 8)],
        [f"4.{i}" for i in range(1, 6)],
    ),
    (
        "k12-non-operating-income",
        ["2.1"],
        [f"2.{i}" for i in range(2, 7)],
        [f"4.{i}" for i in range(1, 7)],
    ),
    (
        "k13-non-operating-expense",
        ["2.1"],
        [f"2.{i}" for i in range(2, 7)],
        [f"4.{i}" for i in range(1, 7)],
    ),
]


def build_waves_json(w2: list[str], w3: list[str], w6: list[str]) -> str:
    waves = [
        {
            "id": "wave-0",
            "name": "Phase0 双源输入",
            "parallel": True,
            "tasks": ["0.1", "0.2"],
        },
        {
            "id": "wave-1",
            "name": "Phase1 注册+契约",
            "tasks": ["1.1", "1.2"],
        },
        {
            "id": "wave-2",
            "name": "Phase2 公式/领域引擎",
            "parallel": len(w2) > 1,
            "tasks": w2,
        },
        {
            "id": "wave-3",
            "name": "Phase2 PBT",
            "parallel": True,
            "tasks": w3,
        },
        {
            "id": "wave-4",
            "name": "Phase3 基础 composable",
            "parallel": True,
            "tasks": ["3.1", "3.2", "3.3"],
        },
        {
            "id": "wave-5",
            "name": "Phase3 sheet composables",
            "tasks": ["3.4"],
        },
        {
            "id": "wave-6",
            "name": "Phase4 Vue 子组件",
            "parallel": True,
            "tasks": w6,
        },
        {
            "id": "wave-7",
            "name": "Phase5 后端三件套",
            "parallel": True,
            "tasks": ["5.1", "5.2", "5.3"],
        },
        {
            "id": "wave-8",
            "name": "Phase6 集成联动",
            "parallel": True,
            "tasks": ["6.1", "6.2", "6.3"],
        },
        {
            "id": "wave-9",
            "name": "Phase7 测试验收",
            "parallel": True,
            "tasks": ["7.1", "7.2", "7.3"],
        },
    ]
    payload = {"waves": waves}
    return json.dumps(payload, indent=2, ensure_ascii=False)


MERMAID_BLOCK = re.compile(
    r"## Task Dependency Graph\s*\n\s*```mermaid\s*\n.*?```",
    re.DOTALL,
)


def inject(spec_folder: str, w2: list[str], w3: list[str], w6: list[str]) -> None:
    path = SPECS_DIR / spec_folder / "tasks.md"
    text = path.read_text(encoding="utf-8")
    replacement = (
        "## Task Dependency Graph\n\n```json\n"
        + build_waves_json(w2, w3, w6)
        + "\n```"
    )
    if "## Task Dependency Graph" not in text:
        raise ValueError(f"No Task Dependency Graph section: {path}")
    if '"waves":' in text and "```mermaid" not in text:
        print(f"skip (already JSON): {spec_folder}")
        return
    new_text, n = MERMAID_BLOCK.subn(replacement, text, count=1)
    if n != 1:
        # try replace existing json block
        json_block = re.compile(
            r"## Task Dependency Graph\s*\n\s*```json\s*\n.*?```",
            re.DOTALL,
        )
        new_text, n = json_block.subn(replacement, text, count=1)
    if n != 1:
        raise ValueError(f"Could not patch: {path}")
    path.write_text(new_text, encoding="utf-8")
    print(f"ok: {spec_folder}")


def main() -> None:
    for folder, w2, w3, w6 in WAVE_CONFIGS:
        inject(folder, w2, w3, w6)


if __name__ == "__main__":
    main()
