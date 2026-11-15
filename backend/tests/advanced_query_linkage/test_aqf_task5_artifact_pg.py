"""查询证据封存（AQF 任务 5 / design §6.3、§10.2 P10；真 PG）。

缺陷背景（2026-11-15 任务 10 走查抓到）：`seal_artifact` / `verify_and_stream` / 清理与 10 个端点都写好了，
但 `query_export` **从未调用**它们 —— 导出仍走临时文件、发完即删，库里 `query_artifacts` 恒 0 行、证据目录不创建。
本文件钉住「接线真的通了」，判据全部取**运行期真实值**：

1. **P10-a 封存成功**：导出响应带 `X-Query-Artifact-Status: stored` + `X-Query-Run-Id` + `X-Query-Artifact-Id`；
   证据文件真实存在；文件 SHA-256 = 库记录 = 清单里的 `file.sha256`；清单字节的 SHA-256 = 库 `manifest_sha256`；
   openpyxl 读出的数据行数 = 库 `row_count`；说明页含新增四行（查询编号 / 证据编号 / 数据版本 / 版本摘要）。
2. **P10-b 改 1 字节 → 409**：下载端点重验摘要，返回 409 `QUERY_ARTIFACT_INTEGRITY`（变异 M10：不重验就绿）。
3. **P10-c 清理后 → 410**：把记录置 `purged` 后下载 410；文件不存在同样 410。
4. **P10-d 证据目录不可写 → 导出照常、`unavailable`**：封存失败降级，导出仍 200 且是合法 xlsx，
   库里不留证据行（变异 M11：失败时抛错就红）。
5. **反向对照**：正常导出后 `query_artifacts` 行数必须比导出前多 1 —— 证明第 1 条不是「无论怎样都绿」。

写入纪律：真库用例只在 `pg_rollback_session`（外层事务最终回滚）里进行；证据记录的「独立短事务」
经 `query_export._seal_session_factory` 指到**同一回滚会话**，因此不会把行留在共享库。

🔴 用户身份：`query_runs.user_id` / `query_artifacts.user_id` 都外键到 `users(id)`，所以本文件用
``business_real_user``（库里真实 admin），不能用缺省的虚构管理员 —— 虚构 id 会让两处写入 FK 违约、
被 `except` 降级吞掉，表现为「导出成功但响应里少两个响应头」。
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.services.custom_query import query_export

pytestmark = pytest.mark.pg_only

EXPORT = "/api/custom-query/export"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LEDGER_HEADERS = {
    "voucher_date": "凭证日期", "voucher_no": "凭证号", "account_code": "科目编码", "account_name": "科目名称",
    "debit_amount": "借方发生额", "credit_amount": "贷方发生额", "summary": "摘要",
}
EXTRA_INFO_KEYS = ["查询编号", "证据编号", "数据版本", "版本摘要"]


@pytest.fixture(autouse=True)
def _seal_into_rollback_session(pg_rollback_session, tmp_path, monkeypatch):
    """证据记录的短事务指到回滚会话（不落共享库）；产物目录指到本例私有目录。

    `_artifact_root()` 读 `settings.QUERY_ARTIFACT_ROOT`，改它比 monkeypatch 私有函数更贴近生产。
    """
    from app.core.config import settings
    from app.services.custom_query import export_gate

    monkeypatch.setattr(query_export, "_seal_session_factory", _RollbackFactory(pg_rollback_session))
    root = tmp_path / "query_artifacts"
    root.mkdir()
    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(root))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "xlsx_tmp"))
    (tmp_path / "xlsx_tmp").mkdir()
    assert export_gate.in_flight_count() == 0
    yield root
    leaked = export_gate.in_flight_count()
    export_gate._IN_FLIGHT.clear()
    assert leaked == 0, f"本例结束时仍有 {leaked} 个导出名额未释放"


class _RollbackFactory:
    """把 `async_session()` 的用法映射到同一个回滚会话（不 commit 到真实库）。

    生产里是独立短事务，测试里必须复用外层事务：否则证据行会真的留在共享库。
    """

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _Ctx(self._session)


class _Ctx:
    """``async with factory() as short_db`` 的上下文：交出**代理会话**。

    生产里 ``short_db`` 是全新会话，``short_db.begin()`` 开顶层事务；测试复用外层回滚会话时
    该会话已在外层事务里，直接 ``begin()`` 会 `InvalidRequestError`。代理只改 ``begin()``
    （返回无操作上下文，写入仍受外层回滚保护），其余属性原样转发。
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return _SessionProxy(self._session)

    async def __aexit__(self, *exc):
        # 不关闭外层会话；回滚由 pg_rollback_session 夹具统一负责
        return False


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def begin(self):
        return _NoopTx()

    def __getattr__(self, name):
        return getattr(self._session, name)


class _NoopTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _month(project, **extra) -> dict:
    day0 = f"{project.audit_year}-01-01"
    day1 = f"{project.audit_year}-01-31"
    return {
        "project_id": str(project.id), "year": project.audit_year, "source": "ledger_entries",
        "conditions": [{"field": "voucher_date", "op": "between", "value": [day0, day1]}],
        "headers": LEDGER_HEADERS, **extra,
    }


def _read(content: bytes) -> tuple[int, dict]:
    wb = load_workbook(io.BytesIO(content), read_only=True)
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        next(rows)  # 表头
        count = sum(1 for _ in rows)
        notes = {}
        if len(wb.worksheets) > 1:
            notes = {
                str(r[0]): r[1]
                for r in wb.worksheets[1].iter_rows(values_only=True)
                if r and r[0] is not None
            }
        return count, notes
    finally:
        wb.close()


async def _artifact_row(db, artifact_id: str) -> dict | None:
    row = (await db.execute(text("""
        SELECT id, status, storage_key, sha256, byte_size, row_count, manifest, manifest_sha256, run_id
          FROM query_artifacts WHERE id = :id
    """), {"id": artifact_id})).first()
    if row is None:
        return None
    return {
        "id": str(row[0]), "status": row[1], "storage_key": row[2], "sha256": row[3],
        "byte_size": row[4], "row_count": row[5], "manifest": row[6],
        "manifest_sha256": row[7], "run_id": str(row[8]) if row[8] else None,
    }


async def _count(db) -> int:
    return int((await db.execute(text("SELECT count(*) FROM query_artifacts"))).scalar())


async def test_export_seals_artifact_and_manifest_matches_file(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session,
):
    """P10-a：导出 → 证据落库 → 文件 SHA-256 = 记录 = 清单；说明页四行齐全。"""
    db = pg_rollback_session
    project = await picks.resolve("ledger_month_export")
    before = await _count(db)

    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="证据封存用例"))
    assert response.status_code == 200, response.text[:800]

    # 三个响应头（design §6.3 第 5 步）
    assert response.headers.get("X-Query-Artifact-Status") == "stored", (
        f"导出没有封存证据：status={response.headers.get('X-Query-Artifact-Status')!r}。"
        "接线断了（历史上 seal_artifact 零调用）"
    )
    artifact_id = response.headers.get("X-Query-Artifact-Id")
    run_id = response.headers.get("X-Query-Run-Id")
    assert artifact_id, "缺少 X-Query-Artifact-Id"
    assert run_id, "缺少 X-Query-Run-Id（导出未登记运行记录）"

    row = await _artifact_row(db, artifact_id)
    assert row is not None, "响应声明已封存，但库里没有 query_artifacts 行"
    assert row["status"] == "ready"
    assert row["run_id"] == run_id

    # 反向对照：行数确实 +1（证明上一条不是恒绿）
    assert await _count(db) == before + 1

    # 文件真实存在，且 SHA / 大小与记录一致
    file_path = _seal_into_rollback_session / row["storage_key"]
    assert file_path.exists(), f"证据文件不存在：{file_path}"
    actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert actual_sha == row["sha256"], "文件 SHA-256 与记录不一致"
    assert file_path.stat().st_size == row["byte_size"]

    # 清单：file.sha256 与记录一致；清单字节摘要 = manifest_sha256
    manifest = row["manifest"]
    assert manifest["schema"] == "gt.query-artifact/v1"
    assert manifest["file"]["sha256"] == row["sha256"]
    assert manifest["artifact_id"] == artifact_id
    assert manifest["run_id"] == run_id
    canonical = json.dumps(
        manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(canonical).hexdigest() == row["manifest_sha256"]

    # 内容：数据行数 = 记录；说明页含新增四行
    count, notes = _read(file_path.read_bytes())
    assert count == row["row_count"], f"文件数据行 {count} ≠ 记录 row_count {row['row_count']}"
    for key in EXTRA_INFO_KEYS:
        assert key in notes, f"说明页缺新增行「{key}」；实际键：{sorted(notes)}"
    assert notes["证据编号"] == artifact_id
    assert notes["查询编号"] == run_id


async def test_download_detects_one_byte_tampering(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session,
):
    """P10-b：改文件 1 字节 → 下载 409（变异 M10：不重验摘要则绿）。"""
    db = pg_rollback_session
    project = await picks.resolve("ledger_month_export")
    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="篡改检测"))
    assert response.status_code == 200, response.text[:600]
    artifact_id = response.headers["X-Query-Artifact-Id"]
    row = await _artifact_row(db, artifact_id)
    assert row is not None

    file_path = _seal_into_rollback_session / row["storage_key"]
    raw = bytearray(file_path.read_bytes())
    raw[100] ^= 0xFF  # 翻一个字节
    file_path.write_bytes(bytes(raw))

    download = await business_real_user.http.get(f"/api/custom-query/artifacts/{artifact_id}/download")
    assert download.status_code == 409, download.text[:500]
    assert download.json()["detail"]["error_code"] == "QUERY_ARTIFACT_INTEGRITY"


async def test_download_after_purge_is_410(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session,
):
    """P10-c：记录置 purged → 410；文件被删也 410。"""
    db = pg_rollback_session
    project = await picks.resolve("ledger_month_export")
    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="清理后下载"))
    assert response.status_code == 200, response.text[:600]
    artifact_id = response.headers["X-Query-Artifact-Id"]
    row = await _artifact_row(db, artifact_id)
    assert row is not None
    file_path = _seal_into_rollback_session / row["storage_key"]

    # 文件被删（但记录仍是 ready）→ 410
    file_path.unlink()
    gone = await business_real_user.http.get(f"/api/custom-query/artifacts/{artifact_id}/download")
    assert gone.status_code == 410, gone.text[:400]
    assert gone.json()["detail"]["error_code"] == "QUERY_ARTIFACT_PURGED"

    # 记录置 purged → 410
    await db.execute(
        text("UPDATE query_artifacts SET status='purged', purged_at=now() WHERE id=:id"),
        {"id": artifact_id},
    )
    purged = await business_real_user.http.get(f"/api/custom-query/artifacts/{artifact_id}/download")
    assert purged.status_code == 410, purged.text[:400]


async def test_unwritable_artifact_root_degrades_to_temporary_file(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session, monkeypatch,
):
    """P10-d：证据目录不可写 → 导出照常 200、`unavailable`、库里不留证据行（变异 M11）。"""
    db = pg_rollback_session
    project = await picks.resolve("ledger_month_export")
    before = await _count(db)

    # 用一个「文件名当目录」的路径 ⇒ mkdir 必失败（比 chmod 在 Windows 上可靠）
    blocked = _seal_into_rollback_session.parent / "not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    from app.core.config import settings
    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(blocked / "query_artifacts"))

    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="降级用例"))
    assert response.status_code == 200, (
        f"证据目录不可写时导出被中断了（ADR-AQF-06 要求降级而不是失败）：{response.text[:500]}"
    )
    assert response.headers.get("X-Query-Artifact-Status") == "unavailable", (
        "封存失败时响应头必须是 unavailable"
    )
    assert not response.headers.get("X-Query-Artifact-Id"), "降级时不该有证据编号"
    # 导出的仍然是合法 xlsx
    count, _notes = _read(response.content)
    assert count > 0
    # 库里不留证据行
    assert await _count(db) == before, "封存失败却留下了证据记录"


async def test_manifest_endpoint_returns_canonical_bytes_and_matching_header(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session,
):
    """清单端点：返回体就是规范序列化字节，且 `X-Manifest-SHA256` = 库里的摘要。

    design §6.4 要求「`GET .../manifest` 返回同一规范序列化的字节」—— 若端点返回的是
    ORM/JSONB 里取出来的 dict 再经框架重新序列化，字节会随键序变化，摘要就对不上。
    """
    db = pg_rollback_session
    project = await picks.resolve("ledger_month_export")
    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="清单用例"))
    assert response.status_code == 200, response.text[:600]
    artifact_id = response.headers["X-Query-Artifact-Id"]
    row = await _artifact_row(db, artifact_id)
    assert row is not None

    got = await business_real_user.http.get(f"/api/custom-query/artifacts/{artifact_id}/manifest")
    assert got.status_code == 200, got.text[:500]
    assert got.headers.get("X-Manifest-SHA256") == row["manifest_sha256"]

    body = got.json()
    canonical = json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(canonical).hexdigest() == row["manifest_sha256"], (
        "清单端点的返回体不是规范序列化（键序 / 分隔符变了，摘要对不上）"
    )
    assert body["artifact_id"] == artifact_id
    assert body["file"]["sha256"] == row["sha256"]


async def test_export_audit_carries_evidence_identifiers(
    business_real_user, pg_rollback_session, picks, _seal_into_rollback_session, monkeypatch,
):
    """导出审计必须带证据编号、清单摘要、运行编号、版本摘要（design §6.3 末段）。

    变异靶子：把 `manifest_sha256` 读成响应对象上不存在的属性（`getattr(..., None)` 静默取到
    None）⇒ 审计里这一项恒空而所有导出用例照绿 —— 2026-11-15 实测该字段原本就是恒 None。
    """
    from app.services.custom_query import audit_helper

    captured: list[dict] = []

    async def _capture(**kwargs):
        captured.append(kwargs.get("details") or {})
        return True

    monkeypatch.setattr(audit_helper, "_log_unthrottled", _capture)

    project = await picks.resolve("ledger_month_export")
    response = await business_real_user.http.post(EXPORT, json=_month(project, file_name="审计字段"))
    assert response.status_code == 200, response.text[:600]

    exports = [d for d in captured if d.get("operation") == audit_helper.ACTION_EXPORT]
    assert len(exports) == 1, f"导出审计条数异常：{captured}"
    details = exports[0]
    artifact_id = response.headers["X-Query-Artifact-Id"]
    run_id = response.headers["X-Query-Run-Id"]
    row = await _artifact_row(pg_rollback_session, artifact_id)
    assert row is not None

    assert details.get("artifact_id") == artifact_id
    assert details.get("run_id") == run_id
    assert details.get("manifest_sha256") == row["manifest_sha256"], (
        "审计里的清单摘要为空或与库中不一致（恒 None 说明读的属性和写入的对不上）"
    )
    assert details.get("vector_hash"), "审计缺版本摘要"
