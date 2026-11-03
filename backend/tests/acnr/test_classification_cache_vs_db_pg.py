"""T04：classification 缓存 vs 库表对照守卫（需求 A2 裁定 / design §1.3；段四审计 F4-05 返工）。

裁定：生成器 classification 权威输入 = 已提交离线缓存（库表缺 771 拆分编码、模板版本不同，不作权威）。
差异逐类登记在 `sources/classification_reconcile.json`。

守卫：
  0. 离线：缓存 sha256 / 记录数与 reconcile 一致；各清单 count == len(items)；无依据清单恰为设计的 13 条记录。
  1. pg_only：库表 current 版本按 `workpaper_template_version.is_current` 取（不是「行数最多」），与登记一致；
  2. pg_only：库表 current 每个 (wp_code, sheet_name) 都在缓存里，例外恰为 `db_newer_than_cache`；
  3. pg_only（设计的**记录级**判据）：缓存独有记录（wp_code 不在库表 current）的 sheet_name 是库表父码
     记录之一 → 可复算，否则必须登记在 `cache_only_without_db_basis`（按 wp_code + sheet_name）；
     清单有失效条目（已能复算 / 已不是缓存独有）也红。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "data" / "acnr" / "sources"
_CACHE = _SRC / "classification_cache.json"
_RECONCILE = _SRC / "classification_reconcile.json"

#: design §1.3：13 条无库表依据的拆分记录（wp_code, sheet_name）。
_DESIGN_NO_BASIS = {
    ("A18", "A18"), ("A18-1", "A18-1"), ("A18-2", "A18-2"),
    ("A26", "A26"), ("A26-1", "A26-1"), ("A26-2", "A26-2"), ("A26-3", "A26-3"), ("A26-4", "A26-4"),
    ("A27", "A27"), ("A27-1", "A27-1"), ("B5", "B5"),
    ("F1-12", "邮件传真回函核对记录F1-12"), ("L2A", "长期应付职工薪酬实质性程序表 L2A"),
}


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
    return json.loads(_RECONCILE.read_bytes().decode("utf-8"))


def _load_cache() -> list[dict]:
    return json.loads(_CACHE.read_bytes().decode("utf-8"))


def _db_current():
    """返回 (template_version_id, set((wp,sheet)))；版本按 workpaper_template_version.is_current 取。"""
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()
        cur.execute("SELECT id::text FROM workpaper_template_version WHERE is_current")
        rows = cur.fetchall()
        assert len(rows) == 1, f"workpaper_template_version 应恰有 1 个 is_current，实得 {len(rows)}"
        tv = rows[0][0]
        cur.execute(
            "SELECT wp_code, sheet_name FROM workpaper_sheet_classification WHERE template_version_id::text=%s",
            (tv,),
        )
        keys = {(w, s) for (w, s) in cur.fetchall()}
        conn.rollback()
        return tv, keys
    finally:
        conn.close()


def _no_basis_records(cache: list[dict], db_keys: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """设计 §1.3 记录级判据：缓存独有记录的 sheet_name 不在库表父码记录里 ⇒ 无库表依据。"""
    db_codes = {w for w, _ in db_keys}
    db_names: dict[str, set[str]] = defaultdict(set)
    for w, s in db_keys:
        db_names[w].add(s)
    return {
        (r["wp_code"], r["sheet_name"]) for r in cache
        if r["wp_code"] not in db_codes and r["sheet_name"] not in db_names.get(_parent_of(r["wp_code"]), set())
    }


# ── 离线：缓存与 reconcile 自洽 ─────────────────────────────────────────────


def test_reconcile_matches_cache_sha256_and_counts():
    rec = _load_reconcile()
    cache = _load_cache()
    assert rec["cache"]["sha256"] == hashlib.sha256(_CACHE.read_bytes()).hexdigest(), (
        "reconcile 记录的缓存 sha256 过期——缓存变了必须重算 classification_reconcile.json"
    )
    assert rec["cache"]["records"] == len(cache)
    assert rec["cache"]["distinct_wp_code"] == len({r["wp_code"] for r in cache})
    for sect in ("db_newer_than_cache", "cache_only_without_db_basis"):
        assert rec[sect]["count"] == len(rec[sect]["items"]), f"{sect} count != len(items)"


def test_report_release_classification_matches_reconcile_and_cache():
    """T04 原文验收（段四返工核实 RV-01）：生成器写进报告 release.classification 的模板版本 / 记录数 / sha256
    与 reconcile 的 cache 段及缓存文件现算值逐值相等。"""
    from app.services.acnr.catalog_integrity import content_sha256

    report = json.loads((_SRC.parent / "catalog_report.json").read_text(encoding="utf-8"))
    cls = report["release"]["classification"]
    rec = _load_reconcile()["cache"]
    cache = _load_cache()
    live_tv = sorted({str(r.get("template_version_id") or "") for r in cache})
    live_sha = content_sha256(_CACHE.read_bytes())
    assert live_sha == hashlib.sha256(_CACHE.read_bytes()).hexdigest(), "缓存含 CR：LF 内容哈希与字节哈希口径不同，须统一"
    assert cls["template_version_id"] == rec["template_version_id"] == live_tv
    assert cls["record_count"] == rec["records"] == len(cache)
    assert cls["sha256"] == rec["sha256"] == live_sha
    assert cls["path"] == rec["path"]


def test_no_basis_list_is_design_thirteen_records():
    items = _load_reconcile()["cache_only_without_db_basis"]["items"]
    got = {(i["wp_code"], i["sheet_name"]) for i in items}
    assert got == _DESIGN_NO_BASIS, (
        f"无依据清单与设计 §1.3 的 13 条记录不一致：多 {sorted(got - _DESIGN_NO_BASIS)} 缺 {sorted(_DESIGN_NO_BASIS - got)}"
    )
    cache_keys = {(r["wp_code"], r["sheet_name"]) for r in _load_cache()}
    assert got <= cache_keys, "清单里有缓存中不存在的记录"


# ── PG 只读：库表 current vs 缓存 ───────────────────────────────────────────


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_db_current_version_selected_by_is_current():
    tv, keys = _db_current()
    db = _load_reconcile()["db_current"]
    assert db["template_version_id"] == tv
    assert db["rows"] == len(keys) and db["distinct_wp_code"] == len({w for w, _ in keys})


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_db_current_keys_all_in_cache_except_registered():
    rec = _load_reconcile()
    cache_keys = {(r["wp_code"], r["sheet_name"]) for r in _load_cache()}
    _tv, db_keys = _db_current()
    registered = {(i["wp_code"], i["sheet_name"]) for i in rec["db_newer_than_cache"]["items"]}
    db_only = db_keys - cache_keys
    assert db_only == registered, (
        f"库表 current 独有键与 db_newer_than_cache 清单不一致："
        f"缺登记={sorted(db_only - registered)[:10]} 多登记={sorted(registered - db_only)[:10]}"
    )
    stale = registered & cache_keys
    assert not stale, f"db_newer_than_cache 清单含已在缓存的失效条目：{sorted(stale)[:10]}"


@pytest.mark.skipif(not _pg_available(), reason="本地 PostgreSQL 不可用")
def test_cache_only_records_derivable_or_registered():
    rec = _load_reconcile()
    cache = _load_cache()
    _tv, db_keys = _db_current()
    registered = {(i["wp_code"], i["sheet_name"]) for i in rec["cache_only_without_db_basis"]["items"]}
    no_basis = _no_basis_records(cache, db_keys)
    assert no_basis == registered, (
        f"无库表依据的缓存记录与清单不一致（记录级判据）："
        f"缺登记={sorted(no_basis - registered)[:10]} 多登记（失效条目）={sorted(registered - no_basis)[:10]}"
    )
    db_codes = {w for w, _ in db_keys}
    split = rec["cache_only_split_codes"]
    cache_only = [r for r in cache if r["wp_code"] not in db_codes]
    assert split["count"] == len({r["wp_code"] for r in cache_only})
    assert split["records"] == len(cache_only)
    assert split["derivable_records"] == len(cache_only) - len(no_basis)
