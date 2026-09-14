"""平台级 per-entry 契约磁盘字节稳定性守卫。

契约的 canonical digest 基于解析后的 JSON，无法发现 Windows ``write_text``
把 LF 转成 CRLF 的回流。因此这里直接检查磁盘原始字节，并把登记清单与
生产契约目录做双向覆盖，避免空集或孤儿文件让守卫假绿。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS


_REPO = Path(__file__).resolve().parents[3]
_CONTRACT_DIR = _REPO / "backend" / "data" / "workpaper_sync_contracts"


def _contract_path(contract_id: str) -> Path:
    return _CONTRACT_DIR / f"{contract_id}.json"


def test_delivered_contract_registry_and_disk_files_are_bidirectionally_equal() -> None:
    """每个已登记契约必须有对应文件，目录中不得出现未登记生产契约。"""
    registered = {
        str(row.get("contract_id") or "").strip()
        for row in DELIVERED_PER_ENTRY_CONTRACTS
    }
    assert registered and "" not in registered

    disk = {
        p.stem
        for p in _CONTRACT_DIR.glob("*.json")
        if not p.name.startswith("_example.")
    }
    assert disk == registered


def test_delivered_contract_files_are_lf_and_canonical_bytes() -> None:
    """原始字节必须是 LF 结尾且等于 canonical JSON 序列化结果。"""
    for contract_id in sorted(
        str(row["contract_id"]) for row in DELIVERED_PER_ENTRY_CONTRACTS
    ):
        path = _contract_path(contract_id)
        raw = path.read_bytes()
        assert b"\r\n" not in raw, path
        assert raw.endswith(b"\n"), path

        payload = json.loads(raw.decode("utf-8"))
        canonical = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        assert raw == canonical, path
