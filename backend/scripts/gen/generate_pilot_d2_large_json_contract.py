# -*- coding: utf-8 -*-
"""生成 / 校验 Task 41 D2 大 JSON pilot 的 per-entry contract 磁盘文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41

payload 的**唯一真源**是
:func:`app.services.workpaper_sync.pilot_d2_large_json.build_contract_payload`。本脚本
只负责序列化落盘与 `--check`，不在这里第二次拼字段 —— 复制一份的后果是任一侧被短路都不
改变行为（变异检验判 GREEN）。

用法（仓库根）::

    py -3 backend/scripts/gen/generate_pilot_d2_large_json_contract.py --check
    py -3 backend/scripts/gen/generate_pilot_d2_large_json_contract.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))


def observe_template_resolution() -> Any:
    """用**真实** `wp_template_finder` 观测本 pilot 的模板解析事实。

    🔴 观测器住在脚本里而不是 `backend/app/`：`find_template_file` /
    `find_template_file_any` 是 Task 19 清册登记的 **non-canonical resolver 符号**，
    生产模块里出现它们会给 Task 20 的收口门增一条 `unadjudicated_resolver` + 一条
    `non_canonical_resolver_only` 欠账（清册生成器只扫 `backend/app`，脚本不在其内）。
    判定逻辑在 `pilot_d2_large_json.assert_no_implicit_template_fallback`，这里只取事实
    —— 一份观测器同时喂给本脚本与 `test_task41_d2_large_json_pilot.py`，不抄第二份。
    """
    from app.services.wp_template_finder import (
        find_all_template_files,
        find_template_file,
        find_template_file_any,
    )
    from app.services.workpaper_sync import pilot_d2_large_json as P

    return P.TemplateResolutionFacts(
        by_wp_code={
            code: (
                find_template_file(code),
                find_template_file_any(code),
                tuple(find_all_template_files(code)),
            )
            for code in sorted(P.PILOT_WP_CODES)
        },
        parent_code="D2",
        parent_resolved_path=find_template_file("D2"),
    )


def _render(payload: dict) -> bytes:
    """稳定序列化：键排序 + 2 空格缩进 + LF + 末尾换行。

    🔴 用 `write_bytes` 而不是 `write_text`：后者按 `os.linesep` 写回，会把 LF 腌成 CRLF
    （本 spec 实测过一次 116317→116960 字节的形态），而基于 `read_text()` 的字节断言
    因 universal newlines 两头都转、查不出来。
    """
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 41 D2 pilot 契约生成/校验")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只校验磁盘与真源一致")
    group.add_argument("--apply", action="store_true", help="重写磁盘契约")
    args = parser.parse_args()

    from app.services.workpaper_sync import pilot_d2_large_json as P
    from app.services.workpaper_sync.contracts import parse_contract

    # 🔴 选型条件不成立时**不得**落盘：契约的每个 source_ref 都指向权威模板的具体单元格，
    #    entry 一漂移（宿主消失 / 变成 parent duplicate / wp_code 变了 / 配置指到别的
    #    工作簿 / finder 开始回退）就意味着这些单元格属于另一份底稿。
    entry = P.assert_pilot_entry_selectable(resolution=observe_template_resolution())
    assert entry["entry_id"] == P.PILOT_ENTRY_ID

    payload = P.build_contract_payload()
    # 落盘前先过一遍强校验：非法契约绝不落盘。
    contract = parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)
    blob = _render(payload)
    path = P.contract_file_path()

    if args.check:
        if not path.is_file():
            print(f"MISSING {path}")
            return 1
        on_disk = path.read_bytes()
        if on_disk != blob:
            print(f"STALE {path}: 磁盘 {len(on_disk)} 字节 != 真源 {len(blob)} 字节")
            return 1
        print(
            f"OK {path.name} bytes={len(blob)} "
            f"fields={len(contract.all_fields())} "
            f"protected={len(contract.protected_field_keys())} "
            f"canonical_sha256={contract.canonical_sha256}"
        )
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    print(
        f"WROTE {path} bytes={len(blob)} "
        f"fields={len(contract.all_fields())} "
        f"protected={len(contract.protected_field_keys())} "
        f"canonical_sha256={contract.canonical_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
