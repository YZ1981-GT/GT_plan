"""知识库上传健壮性 —— 真实 PostgreSQL 守卫

spec: knowledge-upload-robustness-and-consumer-wiring（Requirement 1 / 2 / 3，design §六）

═══ 回归背景（2026-09-30 Playwright + 真库实测）═══

  * UTF-16（记事本「Unicode」另存）与含 NUL 的 txt：旧实现 ``decode('utf-8', errors='ignore')``
    保留 ``\\x00`` → PG ``CharacterNotInRepertoireError`` → 整个上传请求 500。
  * 「扩展名」超 20 字的文件名 → ``file_type VARCHAR(20)`` 溢出 → 500。
  * 逐文件 ``try/except`` 挡不住 flush 失败：会话 aborted 后同批其余文件 ``PendingRollbackError``，
    末尾 commit 抛出 ⇒ 单文件问题放大为**整批丢失**，已落盘文件成孤儿（实测 3 个）。
  * GBK 编码 txt 按 UTF-8 忽略错误解码 → 上传「成功」、正文成乱码、AI 永远检索不到。

═══ 为什么必须真库 ═══

SQLite 不校验 NUL、不校验 VARCHAR 长度、也没有「语句失败 → 事务 aborted」语义：上面每一条
在内存库上修没修都绿。故本文件在真实 PostgreSQL 的 scratch schema 里跑真实端点，并带两条
**反向对照**（对照不红 ⇒ 夹具没复现缺陷 ⇒ 正向断言在空转）：
  * 把逐文件 SAVEPOINT 换回旧式直接写库 → 同一混批必须整批丢失；
  * 绕过 ORM 清洗直接 INSERT 含 NUL 的正文 → 必须被 PG 拒绝。

全部场景一次 ``asyncio.run`` 跑完落快照；``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from tests._kb_pg_scratch import scratch_schema  # noqa: E402

GBK_TEXT = "函证程序要点：发函、跟函、回函核对"
UTF16_TEXT = "坏账准备计提测试 ABC 123"
LONG_TYPE_NAME = "审计报告.final-reviewed-by-partner-v2"


class _Admin:
    id = uuid.UUID("00000000-0000-0000-0000-00000000a0a1")
    role = "admin"
    username = "kb-robust-tester"
    email = "kb-robust@example.com"
    is_active = True


#: 两种真实存在的写库失败形态（文件名含 ``BOOM`` 的那个文件触发）：
#:   * flush —— INSERT 本身被 PG 拒绝（NOT NULL 违约；与 NUL / VARCHAR 溢出同型）。SQLAlchemy
#:     把会话标成「待回滚」，旧实现后续文件 PendingRollbackError、末尾 commit 抛出 ⇒ 500。
#:   * execute —— 写入之后同一事务里另一条语句失败。PG 事务 aborted，但 SQLAlchemy 不标待回滚，
#:     旧实现末尾 COMMIT 被 PG 静默改成 ROLLBACK ⇒ **接口 200 报成功，整批悄悄丢失**。
FAULT_MODES = ("flush", "execute")


def _service_fault(mode: str):
    """在 **service 层** 注入写库失败，生产 ``_insert_document_isolated``（含 SAVEPOINT）原样参与。

    🔴 故障不能靠替换 ``_insert_document_isolated`` 注入：旧写法让「现行实现」跑的是本文件里的
    一份 SAVEPOINT 拷贝 —— 删掉生产代码的 ``begin_nested`` 后本守卫照样全绿（Task 8 变异 M1 实测
    SURVIVED）。守卫验证的必须是生产写路径，测试侧只负责制造故障。
    """
    from app.services.knowledge_folder_service import KnowledgeDocumentService

    original = KnowledgeDocumentService.create_document

    async def create_document(self, **fields):
        boom = "BOOM" in (fields.get("name") or "")
        if mode == "flush" and boom:
            fields = {**fields, "name": None}  # NOT NULL 违约：INSERT 本身被 PG 拒绝
        doc = await original(self, **fields)
        if mode == "execute" and boom:
            await self.db.execute(sa.text("SELECT 1 / 0"))  # 写入之后同事务另一条语句失败
        return doc

    return patch.object(KnowledgeDocumentService, "create_document", create_document)


async def _legacy_insert(db, svc, **fields):
    """旧实现（无 SAVEPOINT，直接写库）：反向对照。"""
    return await svc.create_document(**fields)


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    import app.routers.knowledge_folders as kb_module
    from app.core.config import settings
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.models.knowledge_models import KnowledgeAccessLevel, KnowledgeDocument, KnowledgeFolder

    errors: list[str] = []
    snap: dict[str, Any] = {"harness_errors": errors}
    tmp_root = Path(__file__).resolve().parent / f".kb_robust_{uuid.uuid4().hex[:8]}"

    try:
        async with scratch_schema("kbrobust", errors) as Session:
            folder_ids: dict[str, uuid.UUID] = {}
            fault_keys = [f"{impl}_{mode}" for impl in ("current", "legacy") for mode in FAULT_MODES]
            async with Session() as s:
                for key in ("mixed", "enc", "nul_orm", *fault_keys):
                    folder_ids[key] = uuid.uuid4()
                    s.add(KnowledgeFolder(
                        id=folder_ids[key], name=f"健壮性-{key}",
                        access_level=KnowledgeAccessLevel.public, created_by=_Admin.id,
                    ))
                await s.commit()

            app = FastAPI()
            app.include_router(kb_module.router)

            async def _override_db():
                async with Session() as session:
                    yield session

            app.dependency_overrides[get_db] = _override_db
            app.dependency_overrides[get_current_user] = lambda: _Admin()

            async def upload(client, key: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
                resp = await client.post(
                    f"/api/knowledge-library/folders/{folder_ids[key]}/upload",
                    files=[("files", (name, data, "application/octet-stream")) for name, data in files],
                )
                body: Any
                try:
                    body = resp.json()
                except Exception:  # noqa: BLE001
                    body = resp.text
                return {"status": resp.status_code, "body": body}

            async def docs_in(key: str) -> list[dict[str, Any]]:
                async with Session() as s:
                    rows = (
                        await s.execute(
                            sa.select(
                                KnowledgeDocument.name,
                                KnowledgeDocument.file_type,
                                KnowledgeDocument.content_text,
                                KnowledgeDocument.storage_path,
                            ).where(KnowledgeDocument.folder_id == folder_ids[key])
                        )
                    ).all()
                # Python 侧排序：不依赖数据库排序规则（真库 collation 与中文排序曾不一致）
                return sorted(
                    (
                        {"name": r.name, "file_type": r.file_type, "content": r.content_text,
                         "on_disk": bool(r.storage_path) and Path(r.storage_path).exists()}
                        for r in rows
                    ),
                    key=lambda d: d["name"],
                )

            def disk_files(key: str) -> list[str]:
                d = tmp_root / "knowledge" / str(folder_ids[key])
                return sorted(p.name for p in d.iterdir()) if d.exists() else []

            mixed = [
                ("正常一.txt", "第一份正文".encode("utf-8")),
                (LONG_TYPE_NAME, "扩展名超长".encode("utf-8")),
                ("含NUL.txt", "前半段\x00后半段".encode("utf-8")),
                ("UTF16.txt", UTF16_TEXT.encode("utf-16")),
                ("正常二.md", "# 第二份".encode("utf-8")),
            ]
            encodings = [
                ("gbk.txt", GBK_TEXT.encode("gbk")),
                ("gbk.csv", "科目,金额\n应收账款,1000\n".encode("gbk")),
                ("utf8bom.txt", GBK_TEXT.encode("utf-8-sig")),
                ("utf16be.txt", UTF16_TEXT.encode("utf-16-be")),
                ("空白.txt", b"   \n  "),
            ]
            fault = [
                ("甲.txt", "甲".encode("utf-8")),
                ("BOOM.txt", "炸".encode("utf-8")),
                ("乙.txt", "乙".encode("utf-8")),
            ]

            with patch.object(settings, "STORAGE_ROOT", str(tmp_root)), patch.object(
                kb_module, "_trigger_index_update", new=AsyncMock()
            ), patch("app.services.indexing_pipeline.run_indexing_pipeline", new=AsyncMock()):
                async with AsyncClient(
                    transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
                ) as client:
                    # ① 现行实现：问题文件与正常文件混批
                    snap["mixed"] = await upload(client, "mixed", mixed)
                    snap["mixed_docs"] = await docs_in("mixed")
                    snap["mixed_disk"] = disk_files("mixed")

                    # ② 编码样本
                    snap["enc"] = await upload(client, "enc", encodings)
                    snap["enc_docs"] = await docs_in("enc")
                    # 列表接口的 has_text（前端「未提取到正文」标记的唯一依据）
                    listed = await client.get(f"/api/knowledge-library/folders/{folder_ids['enc']}/documents")
                    try:
                        listed_body: Any = listed.json()
                    except Exception:  # noqa: BLE001
                        listed_body = listed.text
                    snap["enc_list"] = {"status": listed.status_code, "body": listed_body}

                    # ③ 故障注入：中间一个文件写库失败（两种形态 × 现行 / 旧实现）。
                    #    故障一律注在 service 层；「现行」= 生产 _insert_document_isolated 原样，
                    #    「旧实现」= 再把它换成无 SAVEPOINT 的直写（反向对照）
                    from app.services.knowledge_folder_service import KnowledgeDocumentService

                    original = kb_module._insert_document_isolated
                    original_create = KnowledgeDocumentService.create_document
                    snap["faults"] = {}
                    for impl in ("current", "legacy"):
                        for mode in FAULT_MODES:
                            key = f"{impl}_{mode}"
                            if impl == "legacy":
                                kb_module._insert_document_isolated = _legacy_insert
                            try:
                                production_path = kb_module._insert_document_isolated is original
                                with _service_fault(mode):
                                    result = await upload(client, key, fault)
                            finally:
                                kb_module._insert_document_isolated = original
                            snap["faults"][key] = {
                                **result,
                                "production_path": production_path,
                                "docs": [d["name"] for d in await docs_in(key)],
                                "disk": disk_files(key),
                            }
                    snap["restored_hook"] = (
                        kb_module._insert_document_isolated is original
                        and KnowledgeDocumentService.create_document is original_create
                    )

            # ⑤ ORM 层清洗覆盖「非上传」写入方：手工建文档（POST /documents 同路径）
            async with Session() as s:
                s.add(KnowledgeDocument(
                    folder_id=folder_ids["nul_orm"], name="手工\x00文档",
                    content_text="正文\x00片段", tags=["标签\x00一"], file_type=".MD",
                ))
                await s.commit()
            async with Session() as s:
                row = (
                    await s.execute(
                        sa.select(
                            KnowledgeDocument.name, KnowledgeDocument.content_text,
                            KnowledgeDocument.tags, KnowledgeDocument.file_type,
                        ).where(KnowledgeDocument.folder_id == folder_ids["nul_orm"])
                    )
                ).one()
            snap["orm_row"] = {"name": row.name, "content": row.content_text,
                               "tags": row.tags, "file_type": row.file_type}

            # ⑥ 反向对照：绕过 ORM 直接 INSERT 含 NUL 的正文，必须被 PG 拒绝
            async with Session() as s:
                try:
                    await s.execute(
                        sa.text(
                            "INSERT INTO knowledge_documents (id, folder_id, name, content_text) "
                            "VALUES (:id, :fid, 'raw', :txt)"
                        ),
                        {"id": uuid.uuid4(), "fid": folder_ids["nul_orm"], "txt": "a\x00b"},
                    )
                    await s.commit()
                    snap["raw_nul_rejected"] = False
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    snap["raw_nul_rejected"] = type(getattr(exc, "orig", exc)).__name__
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def _by_name(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {d["name"]: d for d in docs}


def test_harness_ran_without_errors(snap):
    assert snap["harness_errors"] == []


# ─── R1 / R2：问题文件不拖垮整批 ───────────────────────────────────────────────


def test_mixed_batch_returns_200_and_stores_every_file(snap):
    """UTF-16 / 含 NUL / 扩展名超长 与正常文件混批：全部入库（清洗后），不再 500。"""
    assert snap["mixed"]["status"] == 200, snap["mixed"]
    body = snap["mixed"]["body"]
    assert body["uploaded"] == 5 and body["failed"] == [], body
    docs = _by_name(snap["mixed_docs"])
    assert set(docs) == {"正常一.txt", LONG_TYPE_NAME, "含NUL.txt", "UTF16.txt", "正常二.md"}
    assert all(d["on_disk"] for d in docs.values()), "入库文档的原文件必须可下载"


def test_nul_is_stripped_and_text_survives(snap):
    docs = _by_name(snap["mixed_docs"])
    assert docs["含NUL.txt"]["content"] == "前半段后半段"
    assert docs["UTF16.txt"]["content"] == UTF16_TEXT, "UTF-16 必须按真实编码解码，而不是剔掉 NUL 后的残片"


def test_overlong_extension_stored_without_file_type(snap):
    docs = _by_name(snap["mixed_docs"])
    assert docs[LONG_TYPE_NAME]["file_type"] is None
    assert docs["正常二.md"]["file_type"] == "md"


def test_fault_hook_was_restored(snap):
    assert snap["restored_hook"] is True, "故障注入没有还原生产写库函数 / service 方法，后续场景结论不可信"


@pytest.mark.parametrize("mode", FAULT_MODES)
def test_fault_in_one_file_keeps_the_others(snap, mode):
    """R1.1 / R1.3：中间文件写库失败 → 前后文件照常入库、失败文件不留孤儿、failed 带中文原因。"""
    r = snap["faults"][f"current_{mode}"]
    # 防空转：「现行」必须跑生产写库函数，而不是测试里的拷贝（否则删掉生产 SAVEPOINT 也全绿）
    assert r["production_path"] is True, "故障场景没有走生产 _insert_document_isolated"
    assert r["status"] == 200, r
    body = r["body"]
    assert body["uploaded"] == 2
    assert [f["filename"] for f in body["failed"]] == ["BOOM.txt"]
    reason = body["failed"][0]["reason"]
    assert reason and not any(k in reason for k in ("SELECT", "INSERT", "division", "null value")), (
        "失败原因不得回显 SQL / 异常原文"
    )
    assert r["docs"] == sorted(["甲.txt", "乙.txt"])
    assert len(r["disk"]) == 2 and not any("BOOM" in n for n in r["disk"]), r["disk"]


def test_negative_control_legacy_flush_failure_is_500_and_loses_batch(snap):
    """反向对照（flush 形态，= 2026-09-30 实测的 NUL / VARCHAR 溢出）：旧实现 500、整批丢失。"""
    r = snap["faults"]["legacy_flush"]
    assert r["status"] == 500, f"夹具未复现「待回滚会话 → commit 抛出」，正向断言会空转：{r}"
    assert r["docs"] == []
    # 即便走到 commit 失败这条最坏路径，本请求已落盘的文件也必须清掉（R1.3）
    assert r["disk"] == [], r["disk"]


def test_negative_control_legacy_execute_failure_silently_loses_batch(snap):
    """反向对照（execute 形态）：旧实现接口 200 报成功，数据却被 PG 静默回滚、原文件成孤儿。"""
    r = snap["faults"]["legacy_execute"]
    assert r["status"] == 200 and r["body"]["uploaded"] >= 1, r
    assert r["docs"] == [], "夹具未复现「COMMIT 被静默改成 ROLLBACK」，正向断言会空转"
    assert len(r["disk"]) >= 1, "旧实现在这种形态下留下孤儿文件"


# ─── R3：纯文本按真实编码解码 ───────────────────────────────────────────────


def test_text_encodings_are_decoded_faithfully(snap):
    assert snap["enc"]["status"] == 200, snap["enc"]
    docs = _by_name(snap["enc_docs"])
    assert docs["gbk.txt"]["content"] == GBK_TEXT
    assert "应收账款" in docs["gbk.csv"]["content"], "GBK 的 CSV 也必须解码（anydoc 会把它读成 Latin-1 乱码）"
    assert docs["utf8bom.txt"]["content"] == GBK_TEXT, "BOM 不得残留在正文开头"
    assert docs["utf16be.txt"]["content"] == UTF16_TEXT


def test_blank_text_is_reported_as_not_extracted(snap):
    files = {f["name"]: f for f in snap["enc"]["body"]["files"]}
    assert files["空白.txt"]["text_extracted"] is False, "空白正文 AI 检索不到，必须如实告知"
    assert files["gbk.txt"]["text_extracted"] is True


def test_document_list_has_text_matches_upload_receipt(snap):
    """R4.2：列表 ``has_text`` 只看「去空白后非空」—— 纯空白正文必须是 False（只判非空会误报 True），
    且与上传回执 ``text_extracted`` 逐文件同口径（否则上传时说「未提取到正文」、列表里却不标）。"""
    assert snap["enc_list"]["status"] == 200, snap["enc_list"]
    flags = {d["name"]: d["has_text"] for d in snap["enc_list"]["body"]}
    assert flags == {
        "gbk.txt": True, "gbk.csv": True, "utf8bom.txt": True, "utf16be.txt": True, "空白.txt": False,
    }
    receipt = {f["name"]: f["text_extracted"] for f in snap["enc"]["body"]["files"]}
    assert flags == receipt


# ─── R2.1：ORM 层清洗覆盖所有写入方 ───────────────────────────────────────────


def test_orm_layer_strips_nul_for_non_upload_writers(snap):
    assert snap["orm_row"] == {"name": "手工文档", "content": "正文片段", "tags": ["标签一"], "file_type": "md"}


def test_negative_control_raw_insert_with_nul_is_rejected(snap):
    """反向对照：绕过 ORM 写 NUL 必被 PG 拒绝 —— 证明上一条断言不是因为 PG 本来就能存 NUL。"""
    assert snap["raw_nul_rejected"] not in (False, None), "PG 居然接受了 NUL，上面的清洗断言无区分力"
