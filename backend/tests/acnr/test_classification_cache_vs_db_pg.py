"""T04：classification 缓存 vs 库表对照守卫（需求 A2 裁定 / design §1.3，pg_only 只读）。

裁定：生成器 classification 权威输入 = 已提交离线缓存（库表缺 771 拆分编码、模板
版本不同，不作权威）。差异逐类登记在 `sources/classification_reconcile.json`。

守卫（对真实 PG 只读）：
  1. 库表 current 版本每个 (wp_code, sheet_name) 都在缓存里，例外恰为 reconcile
     的 `db_newer_than_cache` 清单（S17 新增）；
  2. 缓存独有编码能由库表 current 父码记录复算，否则须在
     `cache_only_without_db_basis` 清单里；
  3. 清单有失效条目（已能由库表复算 / 已在缓存）也红；
  4. 缓存 sha256 与 reconcile 记录一致（缓存变了必须重算 reconcile）。

计数按当时 DB current 现算，不绑定设计 §1.3 固定数字（见 reconcile._doc）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

_DATA = Path(__file__).resolve().parents[2] / "app"  # backend/app
_SRC = Path(__file__).resolve().parents[2] / "data" / "acnr" / "sources"
_CACHE = _SRC / "classification_cache.json"
_RECONCILE = _SRC / "classification_reconcile.json"


def _pg_available() -> bool:
    try:
        import psycopg2

        psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                         host="localhost", port=5432, connect_timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _parent_of(code: str) -> str:
    m = re.match(r"^([A-S]\d+)", code)
    return m.group(1) if m else code


def _load_reconcile() -> dict:
    return json.loads(_RECONCILE.read_text(encoding="utf-8"))


def _load_cache() -> list[dict]:
    return json.loads(_CACHE.read_text(encoding="utf-8"))


def _db_current():
    """返回 (template_version_id, set((wp,sheet)), set(wp_code))。"""
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT template_version_id, count(*) FROM workpaper_sheet_classification "
            "GROUP BY template_version_id ORDER BY count(*) DESC LIMIT 1"
        )
        row = cur.fetchone()
        assert row, "库表 workpaper_sheet_classification 为空"
        tv = str(row[0])
        cur.execute(
            "SELECT wp_code, sheet_name FROM workpaper_sheet_classification WHERE template_version_id=%s",
            (tv,),
        )
        rows = cur.fetchall()
        keys = {(w, s) for (w, s) in rows}
        codes = {w for (w, s) in rows}
        return tv, keys, codes
    finally:
        conn.close()


# ── 非 PG 可跑：缓存与 reconcile 的离线自洽 ──────────────────────────────────


def test_reconcile_matches_cache_sha256_and_counts():
    rec = _load_reconcile()
    cache = _load_cache()
    cache_bytes = _CACHE.read_bytes()
    assert rec["cache"]["sha256"] == hashlib.sha256(cache_bytes).hexdigest(), (
        "reconcile 记录的缓存 sha256 过期——缓存变了必须重算 classification_reconcile.json"
    )
    assert rec["cache"]["records"] == len(cache)
    cache_codes = {r["wp_code"] for r in cache}
    assert rec["cache"]["distinct_wp_code"] == len(cache_codes)
    # 每类 count == len(items)（有 items 的类）
    for sect in ("db_newer_than_cache", "cache_only_without_db_basis"):
        s = rec[sect]
        assert s["count"] == len(s["items"]), f"{sect} count != len(items)"


# ── PG 只读：库表 current vs 缓存 ───────────────────────────────────────────


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_db_current_keys_all_in_cache_except_registered():
    rec = _load_reconcile()
    cache = _load_cache()
    cache_keys = {(r["wp_code"], r["sheet_name"]) for r in cache}
    _tv, db_keys, _codes = _db_current()

    registered = {(i["wp_code"], i["sheet_name"]) for i in rec["db_newer_than_cache"]["items"]}
    db_only = db_keys - cache_keys
    # 库表 current 独有的 (wp,sheet) 恰为登记的 db_newer_than_cache
    assert db_only == registered, (
        f"库表 current 独有键与 db_newer_than_cache 清单不一致："
        f"缺登记={sorted(db_only - registered)[:10]} 多登记={sorted(registered - db_only)[:10]}"
    )
    # 清单失效条目：登记为 db_newer 的若其实已在缓存 → 红
    stale = registered & cache_keys
    assert not stale, f"db_newer_than_cache 清单含已在缓存的失效条目：{sorted(stale)[:10]}"


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_cache_only_codes_derivable_or_registered():
    rec = _load_reconcile()
    cache = _load_cache()
    cache_codes = {r["wp_code"] for r in cache}
    _tv, _keys, db_codes = _db_current()

    registered = {i["wp_code"] for i in rec["cache_only_without_db_basis"]["items"]}
    cache_only = cache_codes - db_codes
    # 每个缓存独有编码：父码在库表 current 可复算，或在无依据清单里
    no_basis = {c for c in cache_only if _parent_of(c) not in db_codes}
    assert no_basis == registered, (
        f"无库表依据的缓存编码与清单不一致："
        f"缺登记={sorted(no_basis - registered)[:10]} 多登记={sorted(registered - no_basis)[:10]}"
    )
    # 清单失效条目：登记的编码若其父码其实在库表里（已可复算）→ 红
    stale = {c for c in registered if _parent_of(c) in db_codes}
    assert not stale, f"cache_only_without_db_basis 清单含已可由库表复算的失效条目：{sorted(stale)[:10]}"
