"""离线守卫：已知 checksum 漂移登记表（spec migration-integrity-and-enum-drift-closure Requirement 3.4）。

登记表只对「审阅时看到的那一次编辑」成立：
* 登记项的 ``current`` 必须等于磁盘文件**用 runner 自己的算法**实算的 checksum —— 文件再被改、
  或被还原成应用时版本，这里都会红（提示重新审阅 / 删除登记项）；
* 判据按 ``(version, stored, current)`` 三元组逐字比较，任一不同即「未解释」。
"""
from __future__ import annotations

import hashlib

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.migration_drift_ledger import KNOWN_CHECKSUM_DRIFTS, unexplained_checksum_drift
from app.core.migration_runner import ChecksumDrift, MigrationRunner


@pytest.fixture(scope="module")
def disk_checksums() -> dict[str, str]:
    # scan_migrations 不碰引擎；用 runner 本身的算法（read_text 通用换行 + utf-8 sha256）
    runner = MigrationRunner(engine=create_async_engine("sqlite+aiosqlite:///:memory:"))
    return {m.version: m.checksum for m in runner.scan_migrations()}


def _drift(version: str, stored: str, current: str | None) -> ChecksumDrift:
    return ChecksumDrift(version=version, filename=f"V{version}__x.sql",
                         stored_checksum=stored, current_checksum=current)


def test_ledger_has_no_duplicate_versions() -> None:
    versions = [k.version for k in KNOWN_CHECKSUM_DRIFTS]
    assert len(versions) == len(set(versions)), versions


@pytest.mark.parametrize("entry", KNOWN_CHECKSUM_DRIFTS, ids=lambda k: f"V{k.version}")
def test_entry_current_matches_disk(entry, disk_checksums) -> None:
    assert entry.version in disk_checksums, f"V{entry.version} 的迁移文件不在磁盘上"
    assert disk_checksums[entry.version] == entry.current, (
        f"V{entry.version} 的文件自登记后又变了（或被还原）：先现查真库确认效果、缺则写补齐迁移，"
        f"再更新登记项的 current / resolution；实算 {disk_checksums[entry.version]}"
    )


@pytest.mark.parametrize("entry", KNOWN_CHECKSUM_DRIFTS, ids=lambda k: f"V{k.version}")
def test_entry_is_a_real_drift_with_a_resolution(entry) -> None:
    assert entry.stored != entry.current, "stored == current 的登记项不是漂移，不应登记"
    assert len(entry.current) == 64 and int(entry.current, 16) >= 0
    assert len(entry.resolution) >= 20, "每条登记必须写明结论（效果由谁补齐 / 为何不补）"


def test_v042_was_registered_as_an_empty_file() -> None:
    """F4 的事实锚点：V042 登记值就是 sha256 空串（零语句迁移被静默记为成功的那一次）。"""
    (v042,) = [k for k in KNOWN_CHECKSUM_DRIFTS if k.version == "042"]
    assert v042.stored == hashlib.sha256(b"").hexdigest()


def test_exact_triples_are_explained() -> None:
    live = [_drift(k.version, k.stored, k.current) for k in KNOWN_CHECKSUM_DRIFTS]
    assert unexplained_checksum_drift(live) == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda k: _drift(k.version, "0" * 64, k.current), id="stored-changed"),
        pytest.param(lambda k: _drift(k.version, k.stored, "f" * 64), id="current-changed"),
        pytest.param(lambda k: _drift(k.version, k.stored, None), id="file-missing"),
        pytest.param(lambda k: _drift("999", k.stored, k.current), id="other-version"),
    ],
)
def test_any_difference_in_the_triple_is_unexplained(mutate) -> None:
    for entry in KNOWN_CHECKSUM_DRIFTS:
        d = mutate(entry)
        assert unexplained_checksum_drift([d]) == [d], (entry.version, d)
