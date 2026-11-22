# -*- coding: utf-8 -*-
"""旧式 drain ledger 守卫（spec onlyoffice-sheet-open 任务 4.2）。

四组判据，每组都断言观测到的副作用而非「不抛异常」：

1. 写入侧：签发真的落库，字段形态符合 V274 的 CHECK。
2. append-only：结算写新行、原行不变；重复结算被拒。
3. 计数：drain_metrics 三个数各自能独立非零。
4. 交付物与接线：迁移成对、DDL 与 ORM 双向一致、端点真的调了记账。
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.workpaper_legacy_drain_ledger import WorkpaperLegacyDrainLedger
from app.services.workpaper_sync import legacy_drain_ledger as ledger

REPO = Path(__file__).resolve().parents[3]
ROUTER = REPO / "backend" / "app" / "routers" / "wp_onlyoffice_router.py"
MIG = REPO / "backend" / "migrations" / "V274__workpaper_legacy_drain_ledger.sql"
ROLLBACK = REPO / "backend" / "migrations" / "R274__rollback_workpaper_legacy_drain_ledger.sql"

#: 记账入口的两种形态：record_issuance 会抛（供测试），record_issuance_quietly
#: 永不抛（端点用）。判据必须认两者：只认前者会在端点改用 quietly 后恒红，
#: 只认后者会在有人绕过包装直接调原始入口时漏判。
_RECORD_ATTRS = frozenset({"record_issuance", "record_issuance_quietly"})


@pytest.fixture
async def session():
    """独立的 in-memory SQLite 会话，只建本表（不碰共享 PG）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sc: WorkpaperLegacyDrainLedger.__table__.create(sc, checkfirst=True)
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _issue(session, **kw):
    d = dict(
        entry_id="xlsx/b60/gt-b60-bundle",
        wp_id=uuid4(), project_id=uuid4(),
        binding_id="b60", binding_status="migrated",
        source_wp_code="B60-1", sheet_name="B60",
        doc_key="doc-key-abc",
    )
    d.update(kw)
    return await ledger.record_issuance(session, **d)


# --- 1. 写入侧 ---


@pytest.mark.asyncio
async def test_issuance_row_carries_all_required_fields(session):
    """签发行必须带全 4.2 列举的每一项：签发时间/TTL/binding/entry/generation/终态。"""
    row = await _issue(session, generation=7, ttl=timedelta(hours=2))
    assert row.event_kind == ledger.EVENT_ISSUED
    assert row.entry_id == "xlsx/b60/gt-b60-bundle"
    assert row.binding_id == "b60"
    assert row.generation == 7
    assert row.issued_at is not None
    assert row.expires_at - row.issued_at == timedelta(hours=2)
    # 签发行不得带终结字段（V274 的 ck_wpldl_issued_shape）
    assert row.issuance_id is None
    assert row.terminal_state is None
    assert row.settled_at is None


@pytest.mark.asyncio
async def test_issuance_stores_doc_key_hash_not_plaintext(session):
    """doc_key 只以 sha256 落库 —— 明文落库等于写入可伪造的会话标识。"""
    row = await _issue(session, doc_key="super-secret-doc-key")
    assert row.doc_key_sha256 == ledger.doc_key_digest("super-secret-doc-key")
    assert len(row.doc_key_sha256) == 64
    for col in WorkpaperLegacyDrainLedger.__table__.columns:
        v = getattr(row, col.name, None)
        if isinstance(v, str):
            assert "super-secret-doc-key" not in v, col.name


@pytest.mark.asyncio
async def test_issuance_without_doc_key_leaves_digest_null(session):
    """没签 doc key 时哈希列必须为空，而不是空串的哈希。"""
    row = await _issue(session, doc_key=None)
    assert row.doc_key_sha256 is None
    assert row.doc_key_sha256 != ledger.doc_key_digest("")


@pytest.mark.asyncio
async def test_non_positive_ttl_is_rejected(session):
    """TTL 必须为正 —— 签发即过期会让 drain timeout 计数恒为非零。"""
    for bad in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError) as exc:
            await _issue(session, ttl=bad)
        # 必须断言到「是我们的 TTL 校验拒的」，不能只看抛了 ValueError：
        # 删掉 TTL 校验后，expires_at == issued_at 会撞 V274 的 ck_wpldl_ttl_order，
        # 同样抛 ValueError —— 只断言类型会让变异存活（首轮实测 M1 SURVIVED）。
        assert "TTL" in str(exc.value), (
            "拒绝理由必须点名 TTL —— 否则无法区分是我们的校验还是数据库 CHECK 兜住的"
        )


# --- 2. append-only 与结算 ---


@pytest.mark.asyncio
async def test_settlement_writes_new_row_and_leaves_origin_untouched(session):
    """结算是新行，原签发行逐字段不变（append-only 的核心判据）。"""
    origin = await _issue(session)
    before = {c.name: getattr(origin, c.name) for c in WorkpaperLegacyDrainLedger.__table__.columns}

    settled = await ledger.settle_issuance(
        session, issuance_id=origin.id,
        terminal_state=ledger.TERMINAL_SAVED,
        reason="用户在收尾期内保存并关闭", callback_in_flight=False,
    )
    assert settled.event_kind == ledger.EVENT_SETTLED
    assert settled.issuance_id == origin.id
    assert settled.terminal_state == "saved"
    assert settled.settled_at is not None

    await session.refresh(origin)
    after = {c.name: getattr(origin, c.name) for c in WorkpaperLegacyDrainLedger.__table__.columns}

    def norm(v):
        # SQLite 的 TIMESTAMP 不保留 tzinfo，时间列比 UTC 值而不比 tzinfo 身份
        if isinstance(v, datetime):
            return v if v.tzinfo is None else v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

    assert {k: norm(v) for k, v in after.items()} == {k: norm(v) for k, v in before.items()}, (
        "签发行被就地修改 —— append-only 语义被破坏"
    )


@pytest.mark.asyncio
async def test_double_settlement_is_rejected(session):
    """同一签发不得结算两次（否则计数会重复扣减）。"""
    origin = await _issue(session)
    await ledger.settle_issuance(
        session, issuance_id=origin.id,
        terminal_state=ledger.TERMINAL_SAVED, reason="第一次",
    )
    with pytest.raises(ValueError) as exc:
        await ledger.settle_issuance(
            session, issuance_id=origin.id,
            terminal_state=ledger.TERMINAL_EXPIRED, reason="第二次",
        )
    assert "已被结算" in str(exc.value)


@pytest.mark.asyncio
async def test_settlement_requires_reason_and_known_state(session):
    """空白原因与未知状态都必须被拒（空白串与 NULL 在 IS NOT NULL 下同义）。"""
    origin = await _issue(session)
    with pytest.raises(ValueError) as exc:
        await ledger.settle_issuance(
            session, issuance_id=origin.id,
            terminal_state=ledger.TERMINAL_SAVED, reason="   ",
        )
    assert "原因" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        await ledger.settle_issuance(
            session, issuance_id=origin.id, terminal_state="not_a_state", reason="x",
        )
    assert "未知的终结状态" in str(exc.value)


@pytest.mark.asyncio
async def test_settlement_rejects_non_issuance_target(session):
    """拿结算行去结算必须被拒 —— 否则可以无限套娃。"""
    origin = await _issue(session)
    settled = await ledger.settle_issuance(
        session, issuance_id=origin.id,
        terminal_state=ledger.TERMINAL_SAVED, reason="x",
    )
    with pytest.raises(ValueError) as exc:
        await ledger.settle_issuance(
            session, issuance_id=settled.id,
            terminal_state=ledger.TERMINAL_SAVED, reason="y",
        )
    assert "不是一条有效的签发行" in str(exc.value)


# --- 3. 计数（4.4 的三个删除判据） ---


@pytest.mark.asyncio
async def test_metrics_all_zero_on_empty_ledger(session):
    """空表三个数都是 0 —— 但这是基线，不是删除依据。"""
    assert await ledger.drain_metrics(session) == {
        "open_issuances": 0, "expired_unsettled": 0, "callback_in_flight": 0,
    }


@pytest.mark.asyncio
async def test_open_issuances_counts_unsettled_only(session):
    """已结算的签发不再计入 open —— 否则「旧签发数」永远减不下去。"""
    keep = await _issue(session)
    gone = await _issue(session)
    await ledger.settle_issuance(
        session, issuance_id=gone.id,
        terminal_state=ledger.TERMINAL_SAVED, reason="收尾",
    )
    m = await ledger.drain_metrics(session)
    assert m["open_issuances"] == 1
    opens = await ledger.open_issuances(session)
    assert [r.id for r in opens] == [keep.id]


@pytest.mark.asyncio
async def test_expired_unsettled_is_independent_from_open(session):
    """两个数必须能各自独立非零，否则「同时为 0」是同一个数说了两遍。

    构造两条过期 + 一条未过期。数量刻意不对称：若把 <= 写成 >，计数会从 2 变 1，
    判据才分得开。1:1 的构造两个方向都数出 1 —— 那是变异存活的原因（首轮实测）。
    """
    now = datetime.now(timezone.utc)
    await _issue(session, issued_at=now - timedelta(hours=10), ttl=timedelta(hours=1))
    await _issue(session, issued_at=now - timedelta(hours=8), ttl=timedelta(hours=1))
    await _issue(session, issued_at=now, ttl=timedelta(hours=10))
    m = await ledger.drain_metrics(session)
    assert m["open_issuances"] == 3
    assert m["expired_unsettled"] == 2


@pytest.mark.asyncio
async def test_callback_in_flight_counted_from_settlement_rows(session):
    """in-flight 计数来自结算行，且只有显式 True 才计（None/False 不算）。"""
    a = await _issue(session)
    b = await _issue(session)
    await ledger.settle_issuance(
        session, issuance_id=a.id,
        terminal_state=ledger.TERMINAL_EXPIRED, reason="超时", callback_in_flight=True,
    )
    await ledger.settle_issuance(
        session, issuance_id=b.id,
        terminal_state=ledger.TERMINAL_SAVED, reason="正常", callback_in_flight=False,
    )
    assert (await ledger.drain_metrics(session))["callback_in_flight"] == 1


@pytest.mark.asyncio
async def test_find_open_by_doc_key_matches_hash(session):
    """4.3 的 callback 归属校验：按 doc_key 找未结算签发。"""
    row = await _issue(session, doc_key="dk-1")
    found = await ledger.find_open_by_doc_key(session, doc_key="dk-1")
    assert found is not None and found.id == row.id
    await ledger.settle_issuance(
        session, issuance_id=row.id,
        terminal_state=ledger.TERMINAL_SAVED, reason="x",
    )
    assert await ledger.find_open_by_doc_key(session, doc_key="dk-1") is None


@pytest.mark.asyncio
async def test_find_open_by_doc_key_rejects_unknown_key(session):
    """没签发过的 doc_key 不得命中（反向判据 —— 不能见谁都放行）。"""
    await _issue(session, doc_key="dk-known")
    assert await ledger.find_open_by_doc_key(session, doc_key="dk-other") is None


# --- 4. 交付物与接线 ---


def test_migration_pair_exists_and_idempotent():
    """迁移成对存在；CREATE 用 IF NOT EXISTS、DROP 用 IF EXISTS。"""
    assert MIG.is_file(), MIG
    assert ROLLBACK.is_file(), ROLLBACK
    v = MIG.read_text(encoding="utf-8")
    r = ROLLBACK.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS working_paper_legacy_drain_ledger" in v
    assert "DROP TABLE IF EXISTS working_paper_legacy_drain_ledger" in r


def test_migration_files_have_no_bom_and_use_lf():
    """本仓 pre-commit 门禁：迁移文件必须无 BOM、LF 行尾。"""
    for p in (MIG, ROLLBACK):
        raw = p.read_bytes()
        assert raw[:3] != bytes([0xEF, 0xBB, 0xBF]), p.name + " has BOM"
        assert bytes([0x0D, 0x0A]) not in raw, p.name + " has CRLF"


def test_model_is_not_in_v151_registry():
    """新表不得进 WORKPAPER_SYNC_TABLES —— 那张字典以完全相等锁死 V151 的 28 张表。"""
    from app.models.workpaper_sync_models import WORKPAPER_SYNC_TABLES
    assert "working_paper_legacy_drain_ledger" not in WORKPAPER_SYNC_TABLES
    assert len(WORKPAPER_SYNC_TABLES) == 28


def test_ddl_columns_match_orm_columns():
    """V274 DDL 与 ORM 双向比对（多一列或少一列即红）。"""
    import re
    ddl = MIG.read_text(encoding="utf-8")
    head = "CREATE TABLE IF NOT EXISTS working_paper_legacy_drain_ledger ("
    body = ddl.split(head, 1)[1].split(chr(10) + ");", 1)[0]
    pat = r"^([a-z][a-z0-9_]*)\s+(UUID|VARCHAR|CHAR|BOOLEAN|BIGINT|TIMESTAMPTZ|TEXT)"
    ddl_cols = set()
    for line in body.split(chr(10)):
        m = re.match(pat, line.strip())
        if m:
            ddl_cols.add(m.group(1))
    orm_cols = {c.name for c in WorkpaperLegacyDrainLedger.__table__.columns}
    assert ddl_cols == orm_cols, (
        "DDL only=" + str(ddl_cols - orm_cols) + " ORM only=" + str(orm_cols - ddl_cols)
    )


def test_terminal_states_match_migration_check():
    """封闭集必须与 V274 的 ck_wpldl_terminal_state 逐值一致。"""
    import re
    ddl = MIG.read_text(encoding="utf-8")
    m = re.search(r"terminal_state IN \(([^)]+)\)", ddl)
    assert m, "迁移里找不到 terminal_state 的封闭集"
    Q = chr(39)
    pat = Q + "([a-z]+)" + Q
    ddl_states = set(re.findall(pat, m.group(1)))
    assert ddl_states == set(ledger.TERMINAL_STATES)


def test_router_calls_record_issuance_via_ast():
    """端点必须真的调记账入口。用 AST 不用文本匹配（注释会骗过文本判据）。"""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in _RECORD_ATTRS
    ]
    assert calls, "router 里没有对记账入口的真实调用"
    kw = {k.arg for c in calls for k in c.keywords if k.arg}
    for req in ("entry_id", "wp_id", "project_id", "doc_key"):
        assert req in kw, "记账调用缺实参 " + req


def test_router_uses_quiet_wrapper_not_raising_one():
    """端点必须调 quietly 版 —— 记账失败不得让在线编辑整体不可用。

    与上一条分工：上一条判有没有接线，这一条判接的是哪一种。
    """
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    attrs = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "record_issuance_quietly" in attrs, (
        "端点没有调用 record_issuance_quietly —— 直接调会抛的版本会让记账失败"
        "连带整个在线编辑不可用"
    )
    assert "record_issuance" not in attrs, (
        "端点直接调了会抛的 record_issuance —— 必须走 quietly 包装"
    )


# --- 5. 变异残留 ---


_RESIDUAL_MARKERS = ("if False:", "(lambda **k: None)(")

_PRODUCTION_FILES = (
    "backend/app/services/workpaper_sync/legacy_drain_ledger.py",
    "backend/app/models/workpaper_legacy_drain_ledger.py",
    "backend/app/routers/wp_onlyoffice_router.py",
)


def test_no_mutation_residue_in_production_files():
    """生产代码里不得残留变异注入形态。"""
    bad = []
    for rel in _PRODUCTION_FILES:
        p = REPO / rel
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8")
        for m in _RESIDUAL_MARKERS:
            if m in t:
                bad.append(rel + ": " + m)
    assert not bad, "生产代码残留变异形态：" + "; ".join(bad)


# --- 6. 守卫自身的元判据（防「守卫空转」） ---


def test_residual_guard_is_not_vacuous():
    """残留守卫必须真的在看文件 —— 全部路径都不存在时它会恒绿。

    这是「空分母恒真」的直接防护：_PRODUCTION_FILES 若因重命名/迁移全部失效，
    test_no_mutation_residue_in_production_files 会一条都没检查却照样通过。
    """
    missing = [rel for rel in _PRODUCTION_FILES if not (REPO / rel).is_file()]
    assert not missing, "残留守卫的目标文件不存在，守卫在空转：" + "; ".join(missing)
    # 且至少一个文件里确实存在可被扫描的内容
    total = sum(len((REPO / rel).read_text(encoding="utf-8")) for rel in _PRODUCTION_FILES)
    assert total > 1000, "残留守卫扫到的总字符数异常小，可能路径错了"


# --- 7. 编码完整性（中文写入曾被 PowerShell 破坏 1097 处） ---


#: 本 spec 全部交付物。新增交付物必须同步登记到这里。
DELIVERABLES = (
    "backend/migrations/V274__workpaper_legacy_drain_ledger.sql",
    "backend/migrations/R274__rollback_workpaper_legacy_drain_ledger.sql",
    "backend/app/models/workpaper_legacy_drain_ledger.py",
    "backend/app/services/workpaper_sync/legacy_drain_ledger.py",
    "backend/tests/workpaper_sync/test_legacy_drain_ledger.py",
)

#: 编码损坏的特征：? 紧邻 CJK 字符（汉字被替换成 ? 后，前后仍是中文）。
#:
#: 🔴 不能用「含 ? 即违规」：代码里正当的 ? 很多（三元 a ? b : c、正则 (?:、
#: 查询串 ?token=、以及讨论这个问题的注释本身）⇒ 那种判据会把自己判红。
#: 实测首版就是这样：抓到 8 处全是正当用法。
_CJK_RANGE = "\u4e00-\u9fff"
_CJK_ADJACENT_QMARK = re.compile("[" + _CJK_RANGE + "]\\?|\\?[" + _CJK_RANGE + "]")


def _encoding_damage_lines(text: str) -> list[tuple[int, str]]:
    """找出 ? 紧邻 CJK 的行 —— 那是汉字被 ASCII 编码替换后的残留形态。"""
    out = []
    for i, line in enumerate(text.split(chr(10)), 1):
        if _CJK_ADJACENT_QMARK.search(line):
            out.append((i, line.strip()[:90]))
    return out


def test_deliverables_have_no_encoding_damage():
    """交付物不得含「? 紧邻 CJK」的编码损坏残留。

    实测教训：首轮用 Set-Content -Encoding ascii 写中文，把 1097 处汉字变成 ?，
    而文件仍能通过 AST 解析与大部分测试（注释里的 ? 不影响执行）⇒ 只有专门的
    编码判据才抓得到。

    判据取「? 紧邻 CJK」而不是「含 ?」：后者会误报代码里正当的 ?（三元 / 正则 /
    查询串），实测抓到 8 处全是正当用法。
    """
    bad = []
    for rel in DELIVERABLES:
        p = REPO / rel
        if not p.is_file():
            continue
        for ln, snippet in _encoding_damage_lines(p.read_text(encoding="utf-8")):
            bad.append(rel + ":" + str(ln) + " " + snippet)
    assert not bad, ("交付物含编码损坏（? 紧邻 CJK）：" + chr(10) + chr(10).join(bad))


# --- 8. 拒绝类判据的元守卫（M1 教训） ---


def test_every_pytest_raises_asserts_the_rejection_reason():
    """每个 pytest.raises 块必须断言拒绝理由，不能只看异常类型。

    M1 首轮存活的原因：删掉 TTL 校验后 expires_at == issued_at 会撞 V274 的
    ck_wpldl_ttl_order，同样抛 ValueError，只断言类型的判据被第二道防线兜住。
    这类判据被兜底机制遮蔽的问题只有元判据能系统性地挡住。

    判据形态：with pytest.raises(...) as X 之后（块内或紧随其后的同级语句）
    必须出现对 X.value 的断言。

    首版只扫块内，把 5 处「assert 写在 with 之后」的正确写法全判成违规。
    with 块结束后再断言是更常见的写法（块内只能写触发语句），判据必须认它。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    offenders = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        body = fn.body
        for idx, stmt in enumerate(body):
            if not isinstance(stmt, ast.With):
                continue
            alias = None
            for item in stmt.items:
                c = item.context_expr
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "raises"
                        and isinstance(item.optional_vars, ast.Name)):
                    alias = item.optional_vars.id
                    break
            if alias is None:
                continue
            scope = list(stmt.body)
            for nxt in body[idx + 1:]:
                if isinstance(nxt, ast.With):
                    break
                scope.append(nxt)
            # 认两种写法：① assert ... in str(exc.value)；② msg = str(exc.value)
            # 后再 assert ... in msg（中间变量是常见写法，不能判成违规）。
            msg_asserted = any(
                isinstance(n, ast.Assert)
                and any(isinstance(s, ast.Attribute) and s.attr == "value"
                        for s in ast.walk(n.test))
                for n in scope
            )
            if not msg_asserted:
                msg_asserted = any(
                    isinstance(n, ast.Assign)
                    and any(isinstance(s, ast.Attribute) and s.attr == "value"
                            for s in ast.walk(n.value))
                    for n in scope
                    if isinstance(n, ast.Assign)
                )
            if not msg_asserted:
                offenders.append(fn.name + " (line " + str(stmt.lineno) + ")")
    assert not offenders, (
        "这些 pytest.raises 块只断言了异常类型，没断言拒绝理由：" + "; ".join(offenders)
    )


# --- 9. 4.3 draining 判据 ---


@pytest.mark.asyncio
async def test_draining_accepts_only_issued_and_unsettled_callback(session, monkeypatch):
    """draining 下：已签发未结算 ⇒ 接受；没签发过 ⇒ 拒绝。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    async def _draining(_db, *, wp_id, sheet_name):
        return "draining"

    monkeypatch.setattr(L, "_binding_status_for", _draining)
    wp, sheet = uuid4(), "B60"

    row = await _issue(session, doc_key="dk-live", wp_id=wp, sheet_name=sheet)
    ok, why = await L.verify_draining_callback(
        session, wp_id=wp, sheet_name=sheet, doc_key="dk-live",
    )
    assert ok is True, why

    # 结算后不再算「已签发待结算」
    await L.settle_issuance(
        session, issuance_id=row.id,
        terminal_state=L.TERMINAL_SAVED, reason="收尾",
    )
    ok2, why2 = await L.verify_draining_callback(
        session, wp_id=wp, sheet_name=sheet, doc_key="dk-live",
    )
    assert ok2 is False
    assert "没有未结算的签发记录" in why2


@pytest.mark.asyncio
async def test_draining_rejects_missing_doc_key(session, monkeypatch):
    """draining 下缺 doc key 必须拒 —— 否则空 key 会绕过归属校验。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    async def _draining(_db, *, wp_id, sheet_name):
        return "draining"

    monkeypatch.setattr(L, "_binding_status_for", _draining)
    ok, why = await L.verify_draining_callback(
        session, wp_id=uuid4(), sheet_name="B60", doc_key="",
    )
    assert ok is False
    # 必须点名「请求体缺 key」这个**特定**理由，不能只匹配 "doc key"：
    # 删掉这道校验后，doc_key_digest("") 查不到记录会落到「没有未结算的签发记录」
    # 分支，那条消息里**也**含 "doc key" ⇒ 宽断言会让变异存活（实测 N2 SURVIVED）。
    assert "必须带 doc key" in why, why


@pytest.mark.asyncio
async def test_non_draining_states_pass_through(session, monkeypatch):
    """非 draining（pending / out_of_scope / None）必须放行。

    这是「不做假切换」的直接判据：旧式链路在那些状态下仍是正常通道，额外要求
    ledger 记录会让升级前已打开的会话在升级后存不了。
    """
    from app.services.workpaper_sync import legacy_drain_ledger as L

    for state in ("pending", "out_of_scope", "migrated", None):
        async def _st(_db, *, wp_id, sheet_name, _s=state):
            return _s

        monkeypatch.setattr(L, "_binding_status_for", _st)
        ok, why = await L.verify_draining_callback(
            session, wp_id=uuid4(), sheet_name="B60", doc_key="never-issued",
        )
        assert ok is True, (state, why)


# --- 10. 4.4 删除前门禁 ---


@pytest.mark.asyncio
async def test_delete_gate_rejects_any_nonzero_counter(session):
    """三个计数任一非 0 都必须拒删 —— 不能只看其中一个。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    # 空表：三个都是 0 ⇒ 通过
    m = await L.assert_drain_complete_for_delete(session, entry_id="e1")
    assert m == {"open_issuances": 0, "expired_unsettled": 0, "callback_in_flight": 0}

    # 造一条未结算 ⇒ open 非 0 ⇒ 必须拒
    await _issue(session, entry_id="e1")
    with pytest.raises(L.DrainNotCompleteError) as exc:
        await L.assert_drain_complete_for_delete(session, entry_id="e1")
    assert "open_issuances" in str(exc.value), str(exc.value)


@pytest.mark.asyncio
async def test_delete_gate_rejects_expired_even_when_others_zero(session):
    """只有 expired_unsettled 非 0 时也必须拒 —— 证明它独立承重。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    now = datetime.now(timezone.utc)
    await _issue(session, entry_id="e2", issued_at=now - timedelta(hours=10), ttl=timedelta(hours=1))
    with pytest.raises(L.DrainNotCompleteError) as exc:
        await L.assert_drain_complete_for_delete(session, entry_id="e2")
    msg = str(exc.value)
    assert "expired_unsettled" in msg, msg


@pytest.mark.asyncio
async def test_delete_gate_rejects_when_never_observed(session):
    """从未有过已结算记录时必须拒 —— 三个 0 只是「没流量」，不是「drain 完成」。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    with pytest.raises(L.DrainNotCompleteError) as exc:
        await L.assert_drain_complete_for_delete(
            session, entry_id="e3", require_observed_seconds=60,
        )
    assert "从未有过已结算" in str(exc.value), str(exc.value)


@pytest.mark.asyncio
async def test_delete_gate_passes_after_full_drain(session):
    """真 drain 完之后必须通过 —— 否则门禁永远打不开，等于没实现。"""
    from app.services.workpaper_sync import legacy_drain_ledger as L

    wp, sheet = uuid4(), "B60"
    row = await _issue(session, entry_id="e4", wp_id=wp, sheet_name=sheet, doc_key="k4")
    await L.settle_issuance(
        session, issuance_id=row.id,
        terminal_state=L.TERMINAL_SAVED, reason="正常收尾", callback_in_flight=False,
        settled_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    m = await L.assert_drain_complete_for_delete(
        session, entry_id="e4", require_observed_seconds=3600,
    )
    assert m["open_issuances"] == 0
    assert m["expired_unsettled"] == 0
    assert m["callback_in_flight"] == 0


@pytest.mark.asyncio
async def test_delete_gate_rejects_when_window_too_short(session):
    """有结算记录但距今不足窗口时必须拒 —— 证明「窗口时长」这条分支独立承重。

    🔴 与上一条分工：上一条测「从未结算」（settled is None），这一条测「结算了但太新」
    （age < require）。只测前者时把 `age < require` 改成恒假不会打红（实测 G3 SURVIVED）。
    """
    from app.services.workpaper_sync import legacy_drain_ledger as L

    row = await _issue(session, entry_id="e5", doc_key="k5")
    await L.settle_issuance(
        session, issuance_id=row.id,
        terminal_state=L.TERMINAL_SAVED, reason="刚结算", callback_in_flight=False,
        settled_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    with pytest.raises(L.DrainNotCompleteError) as exc:
        await L.assert_drain_complete_for_delete(
            session, entry_id="e5", require_observed_seconds=3600,
        )
    assert "不足观测窗口" in str(exc.value), str(exc.value)
