"""函证管理服务

能力域 D — global-refinement-v5-closure：
CRUD + 状态机 transition_status。
service 只 flush 不 commit（项目铁律，router 统一 commit）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import re

from sqlalchemy import select, delete as sa_delete, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.confirmation_models import Confirmation


# ─── 状态机合法转换表 ───────────────────────────────────────────────────────
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"sent"},
    "sent": {"returned"},
    "returned": {"matched", "discrepancy"},
    "matched": set(),
    "discrepancy": set(),
}

# 中文状态名映射（用于错误提示）
_STATUS_CN: dict[str, str] = {
    "pending": "待发函",
    "sent": "已发函",
    "returned": "已回函",
    "matched": "相符",
    "discrepancy": "差异",
}

# ─── 撤回能力（confirmation-attachment-ocr-linkage M1）────────────────────────
# 前进表 _ALLOWED_TRANSITIONS 不变；撤回基于 rank 的反向表独立维护。
_STATUS_RANK: dict[str, int] = {
    "pending": 0, "sent": 1, "returned": 2, "matched": 3, "discrepancy": 3,
}

# 撤回允许目标：任一严格更早状态（支持一步退到底至 pending）
_REVERSAL_TARGETS: dict[str, set[str]] = {
    "pending":     set(),                             # 初始态不可再撤回
    "sent":        {"pending"},
    "returned":    {"sent", "pending"},
    "matched":     {"returned", "sent", "pending"},
    "discrepancy": {"returned", "sent", "pending"},
}


def _to_dict(record: Confirmation) -> dict:
    """将 ORM 实例转为 dict 输出"""
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "confirm_type": record.confirm_type,
        "counterparty": record.counterparty,
        "status": record.status,
        "wp_id": str(record.wp_id) if record.wp_id else None,
        "account_code": record.account_code,
        "book_amount": float(record.book_amount) if record.book_amount is not None else None,
        "confirmed_amount": float(record.confirmed_amount) if record.confirmed_amount is not None else None,
        "diff_amount": float(record.diff_amount) if record.diff_amount is not None else None,
        "diff_note": record.diff_note,
        "created_by": str(record.created_by) if record.created_by else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


async def create_confirmation(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: dict,
) -> dict:
    """创建函证记录

    必填: confirm_type, counterparty
    可选: wp_id, account_code, book_amount, confirmed_amount, diff_amount, diff_note, created_by
    """
    now = datetime.now(timezone.utc)
    record = Confirmation(
        id=uuid.uuid4(),
        project_id=project_id,
        confirm_type=data.get("confirm_type") or "",
        counterparty=data.get("counterparty") or "",
        status="pending",
        wp_id=(data.get("wp_id") or None),
        account_code=(data.get("account_code") or None),
        book_amount=(data.get("book_amount") if data.get("book_amount") is not None else None),
        confirmed_amount=(data.get("confirmed_amount") if data.get("confirmed_amount") is not None else None),
        diff_amount=(data.get("diff_amount") if data.get("diff_amount") is not None else None),
        diff_note=(data.get("diff_note") or None),
        created_by=(data.get("created_by") or None),
    )
    db.add(record)
    await db.flush()
    # refresh to get server defaults (created_at, updated_at)
    await db.refresh(record)
    return _to_dict(record)


# ─── 从底稿（辅助余额表）提取函证候选对象 ─────────────────────────────────────
#
# 目的：函证很多时手动逐条录入太慢。函证对象（银行/往来单位）其实已在辅助余额表
# （tb_aux_balance）中按核算维度存好，可按函证类型映射到相应科目，分组提取为候选，
# 一键批量导入到函证中心（复用 batch-sync）。审计师只需勾选，无需逐条手打。
#
# 数据源单一口径：tb_aux_balance（经 get_active_filter 取当前 active 数据集）。
# 分组键：aux_dimensions_raw（多维组合，如「金融机构:..,中国银行;银行账户:..」），
# 每个唯一组合 = 一个函证对象（银行的「开户行+账号」/往来的「客户/供应商」）。

# 函证类型 → 相关科目编码前缀（取余额侧科目，非损益）
_CONFIRM_TYPE_ACCOUNT_PREFIXES: dict[str, list[str]] = {
    "bank": ["1001", "1002", "1012"],       # 货币资金：库存现金/银行存款/其他货币资金
    "receivable": ["1122", "1121"],          # 应收账款/应收票据
    "payable": ["2202", "2201"],             # 应付账款/应付票据
    "loan": ["2001", "2501", "2502"],        # 短期借款/长期借款/应付债券
}

# 优先作为「函证对象名称」的核算维度关键词（bank=开户行，往来=客户/供应商/单位）
_NAME_DIM_KEYWORDS = (
    "金融机构", "开户行", "银行", "客户", "供应商", "往来", "单位",
    "债务人", "债权人", "客商", "职员",
)


def _is_numeric_token(value: object) -> bool:
    """判断是否为纯数字/账号类字符串（用于区分名称 vs 账号维度）。"""
    s = str(value or "").strip()
    if not s:
        return True
    return bool(re.fullmatch(r"[\d\.\-\s]+", s))


def _build_candidate_name(raw: str | None, group_names: list[tuple[str, str]]) -> str:
    """从 aux_dimensions_raw 构造函证对象显示名。

    - 主名：首个「非数字」维度值（优先命中名称关键词维度），如「中国银行」「某某公司」。
    - 次名：首个「数字」维度值（账号），银行场景附在括号内区分同名不同账号。
    - raw 为空时回退分组内非数字 aux_name。
    """
    primary: str | None = None
    secondary: str | None = None
    if raw:
        segments = [s for s in raw.split(";") if ":" in s]
        # 先按名称关键词维度找主名
        for seg in segments:
            dim, rest = seg.split(":", 1)
            nm = rest.split(",")[-1].strip() if "," in rest else rest.strip()
            if nm and any(k in dim for k in _NAME_DIM_KEYWORDS) and not _is_numeric_token(nm):
                primary = nm
                break
        # 再遍历取次名（账号）+ 兜底主名
        for seg in segments:
            _dim, rest = seg.split(":", 1)
            nm = rest.split(",")[-1].strip() if "," in rest else rest.strip()
            if not nm:
                continue
            if _is_numeric_token(nm):
                if secondary is None:
                    secondary = nm
            elif primary is None:
                primary = nm
    if primary is None:
        for _t, nm in group_names:
            if nm and not _is_numeric_token(nm):
                primary = nm
                break
        if primary is None and group_names:
            primary = group_names[0][1]
    if primary and secondary:
        return f"{primary}（{secondary}）"
    return primary or (secondary or "")


async def list_confirmation_candidates(
    db: AsyncSession,
    project_id: uuid.UUID,
    confirm_type: str,
    year: int,
) -> list[dict]:
    """从辅助余额表提取指定函证类型的候选函证对象。

    返回 [{confirm_type, counterparty, account_code, book_amount}]，
    按账面金额降序。跳过空名称/零余额。供函证中心「从底稿导入」批量创建。
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    prefixes = _CONFIRM_TYPE_ACCOUNT_PREFIXES.get(confirm_type)
    if not prefixes:
        return []

    tbl = TbAuxBalance.__table__
    active = await get_active_filter(db, tbl, project_id, year)
    like_conds = sa.or_(*[tbl.c.account_code.like(p + "%") for p in prefixes])
    stmt = sa.select(
        tbl.c.account_code,
        tbl.c.aux_type,
        tbl.c.aux_name,
        tbl.c.aux_dimensions_raw,
        tbl.c.closing_balance,
        tbl.c.closing_credit,
        tbl.c.closing_debit,
    ).where(sa.and_(active, like_conds))
    rows = (await db.execute(stmt)).all()

    # 按 aux_dimensions_raw（多维组合）分组；无 raw 时以 aux_name 为键
    groups: dict[str, dict] = {}
    for r in rows:
        key = (r.aux_dimensions_raw or "").strip() or (r.aux_name or "").strip()
        if not key:
            continue
        g = groups.get(key)
        if g is None:
            g = {"raw": r.aux_dimensions_raw, "names": [], "account_code": r.account_code, "balance": None}
            groups[key] = g
        if r.aux_name:
            g["names"].append((r.aux_type or "", r.aux_name))
        if g["balance"] is None:
            bal = r.closing_balance
            if bal is None:
                bal = r.closing_credit if r.closing_credit is not None else r.closing_debit
            if bal is not None:
                g["balance"] = bal
        # 保留更短（更父级）的科目编码作展示
        if r.account_code and len(r.account_code) < len(g["account_code"] or ""):
            g["account_code"] = r.account_code

    candidates: list[dict] = []
    seen: set[str] = set()
    for _key, g in groups.items():
        name = _build_candidate_name(g["raw"], g["names"])
        if not name:
            continue
        bal = g["balance"]
        book = abs(float(bal)) if bal is not None else None
        if not book:  # 跳过零/None 余额
            continue
        if name in seen:
            continue
        seen.add(name)
        candidates.append({
            "confirm_type": confirm_type,
            "counterparty": name,
            "account_code": g["account_code"],
            "book_amount": round(book, 2),
        })

    candidates.sort(key=lambda c: c["book_amount"] or 0, reverse=True)
    return candidates


async def list_confirmations(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> list[dict]:
    """列出项目下所有函证"""
    stmt = (
        select(Confirmation)
        .where(Confirmation.project_id == project_id)
        .order_by(Confirmation.created_at.desc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [_to_dict(r) for r in records]


async def get_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> dict:
    """获取单条函证详情（含关联+差异）

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")
    return _to_dict(record)


async def update_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
    data: dict,
) -> dict:
    """更新函证记录

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    # 可更新字段
    updatable_fields = [
        "confirm_type", "counterparty", "wp_id", "account_code",
        "book_amount", "confirmed_amount", "diff_amount", "diff_note",
    ]
    for field in updatable_fields:
        if field in data:
            value = data[field]
            # 对可选字段用 (value or None) 兜底
            if field in ("wp_id", "account_code", "diff_note"):
                value = (value or None)
            setattr(record, field, value)

    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(record)
    return _to_dict(record)


async def delete_confirmation(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> dict:
    """删除函证记录

    Raises:
        ValueError: 函证记录不存在
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    await db.delete(record)
    await db.flush()
    return {"deleted": True, "id": str(confirmation_id)}


async def transition_status(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
    target_status: str,
) -> dict:
    """函证状态机推进

    仅允许合法转换（_ALLOWED_TRANSITIONS），非法转换抛中文 ValueError。

    Raises:
        ValueError: 函证记录不存在 / 非法状态转换
    """
    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    current = record.status
    allowed = _ALLOWED_TRANSITIONS.get(current, set())

    if target_status not in allowed:
        current_cn = _STATUS_CN.get(current, current)
        target_cn = _STATUS_CN.get(target_status, target_status)
        raise ValueError(f"不能从『{current_cn}』直接转为『{target_cn}』")

    record.status = target_status
    record.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(record)

    # #9: 记录操作历史（结构化日志，供复核追溯）
    try:
        from app.services.event_bus import event_bus
        from app.models.audit_platform_schemas import EventPayload, EventType

        await event_bus.publish_immediate(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,  # 复用已有事件类型作通用审计日志
            project_id=record.project_id,
            extra={
                "audit_action": "confirmation_transition",
                "confirmation_id": str(confirmation_id),
                "counterparty": record.counterparty,
                "from_status": current,
                "to_status": target_status,
                "timestamp": record.updated_at.isoformat(),
            },
        ))
    except Exception:
        pass  # 日志失败不阻断

    return _to_dict(record)


# ─── 状态撤回（confirmation-attachment-ocr-linkage M1）────────────────────────
#
# 允许一步退到底（matched/discrepancy → pending），回退目标须严格更早。
# 跨过 returned 回退时清已回填字段。写 append-only confirmation_action_log 留痕。


async def reverse_status(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
    target_status: str,
    reason: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> dict:
    """函证状态撤回（反向回退，支持一步退到底）。

    Raises:
        ValueError: 函证记录不存在 / 非法撤回方向
    """
    from app.models.confirmation_models import ConfirmationActionLog

    stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("函证记录不存在")

    current = record.status
    allowed = _REVERSAL_TARGETS.get(current, set())

    if not allowed:
        raise ValueError("已是初始状态，无法再撤回")

    if target_status not in allowed:
        current_cn = _STATUS_CN.get(current, current)
        target_cn = _STATUS_CN.get(target_status, target_status)
        raise ValueError(f"不能从『{current_cn}』撤回到『{target_cn}』")

    if _STATUS_RANK.get(target_status, 0) >= _STATUS_RANK.get(current, 0):
        raise ValueError("撤回目标必须严格早于当前状态")

    # 跨过 returned 回退（如 matched→sent/pending）时清已回填字段
    cleared_fields: dict = {}
    if _STATUS_RANK.get(current, 0) >= _STATUS_RANK["returned"] and _STATUS_RANK.get(target_status, 0) < _STATUS_RANK["returned"]:
        if record.confirmed_amount is not None:
            cleared_fields["confirmed_amount"] = float(record.confirmed_amount)
            record.confirmed_amount = None
        if record.diff_amount is not None:
            cleared_fields["diff_amount"] = float(record.diff_amount)
            record.diff_amount = None
        if hasattr(record, "reply_date") and record.reply_date is not None:
            cleared_fields["reply_date"] = str(record.reply_date)
            record.reply_date = None

    record.status = target_status
    record.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # 写 append-only 审计留痕
    try:
        log_entry = ConfirmationActionLog(
            id=uuid.uuid4(),
            confirmation_id=confirmation_id,
            project_id=record.project_id,
            action="reverse",
            from_status=current,
            to_status=target_status,
            final_value=cleared_fields if cleared_fields else None,
            reason=reason,
            actor_user_id=actor_user_id or record.created_by or uuid.UUID(int=0),
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        await db.flush()
    except Exception:
        pass  # 留痕失败不阻断（best-effort）

    # 发布状态变化事件（与前进推进同一下游刷新链）
    try:
        from app.services.event_bus import event_bus
        from app.models.audit_platform_schemas import EventPayload, EventType

        await event_bus.publish_immediate(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=record.project_id,
            extra={
                "audit_action": "confirmation_reverse",
                "confirmation_id": str(confirmation_id),
                "counterparty": record.counterparty,
                "from_status": current,
                "to_status": target_status,
                "cleared_fields": cleared_fields,
                "reason": reason,
                "timestamp": record.updated_at.isoformat(),
            },
        ))
    except Exception:
        pass  # 事件失败不阻断

    await db.refresh(record)
    return _to_dict(record)


# ─── 回函结果应用 + 下游 stale 传播事件（P0 恢复）────────────────────────────
#
# 历史上 workpaper-d-sales-cycle 任务 2.11 / workpaper-f-purchase-inventory 任务 2.20
# 要求"函证回函 → emit EventType.CONFIRMATION_RECEIVED → 沿 cross_wp_references
# 中 source_wp={D0,F0,G0} 的条目向下游（D2/F2/G7…）传播 stale"。该函数一度缺失
# （3 个回调测试 ImportError 红）。此处按测试契约重建并通用化。


async def apply_confirmation_result(
    *,
    project_id: uuid.UUID,
    year: int,
    confirmation_id: uuid.UUID,
    reply_status: str = "",
    reply_amount: float | None = None,
    wp_code: str = "D0",
    db: AsyncSession | None = None,
) -> dict:
    """应用函证回函结果并发布 CONFIRMATION_RECEIVED 事件（下游 stale 传播入口）。

    通用化支持各循环函证底稿：默认 ``wp_code="D0"`` 向下兼容销售循环，亦支持
    ``F0``（采购/存货）、``G0``（投资）等——``extra.wp_code`` 供 stale_engine
    按 ``cross_wp_references`` 的 ``source_wp`` 路由把下游底稿（D2/F2/G7…）标 stale。

    - ``db`` 为 None 时只发事件（供纯事件场景/测试）；提供时尽力回写函证记录
      （confirmed_amount / diff / 终态 status），失败不阻断事件发布。
    - 事件经 ``event_bus.publish_immediate`` 立即派发（不 debounce）。

    Returns: ``{applied, wp_code, confirmation_id, reply_status, reply_amount}``。
    """
    from app.services.event_bus import event_bus
    from app.models.audit_platform_schemas import EventPayload, EventType

    # 1) 尽力回写函证记录（仅当传入 db 且记录存在）
    if db is not None:
        try:
            stmt = select(Confirmation).where(Confirmation.id == confirmation_id)
            record = (await db.execute(stmt)).scalar_one_or_none()
            if record is not None:
                if reply_amount is not None:
                    record.confirmed_amount = reply_amount
                    if record.book_amount is not None:
                        record.diff_amount = float(record.book_amount) - float(reply_amount)
                status = (reply_status or "").lower()
                if "disc" in status or "diff" in status or "不符" in reply_status:
                    record.status = "discrepancy"
                elif "match" in status or "相符" in reply_status:
                    record.status = "matched"
                elif status in ("returned", "已回函"):
                    record.status = "returned"
                record.updated_at = datetime.now(timezone.utc)
                await db.flush()
        except Exception:  # noqa: BLE001 — 回写失败不阻断事件发布
            pass

    # 2) 发布 CONFIRMATION_RECEIVED（下游 stale 传播真源）
    payload = EventPayload(
        event_type=EventType.CONFIRMATION_RECEIVED,
        project_id=project_id,
        year=year,
        extra={
            "wp_code": wp_code,
            "confirmation_id": str(confirmation_id),
            "reply_status": reply_status,
            "reply_amount": reply_amount,
        },
    )
    await event_bus.publish_immediate(payload)

    return {
        "applied": True,
        "wp_code": wp_code,
        "confirmation_id": str(confirmation_id),
        "reply_status": reply_status,
        "reply_amount": reply_amount,
    }


# ─── 源底稿循环码 / 年度反查（G1：Hub 手动回函 stale 兜底）────────────────────
#
# 函证中心台账（ConfirmationHub）手动推进 transition 时通常不带 wp_code——
# 若函证记录关联了 wp_id（源函证底稿，如 D0/F0/G0…），可经 working_paper→wp_index
# 反查出 wp_code，并从 projects.audit_year 取年度，作为 CONFIRMATION_RECEIVED
# 下游 stale 传播的兜底路由源。无 wp_id 时返回 (None, None)，调用方据此不臆测源底稿。


def _normalize_source_wp_code(wp_code: str | None) -> str | None:
    """把 sheet 级函证底稿编码归一为循环级源码（D0-1 → D0）。

    stale 传播图以循环级 wp_code（D0/F0/G0…）为键，故剥离尾部 ``-N`` sheet 后缀，
    与前端 ``syncHubFromSummary`` 的 ``wpCode.split('-')[0]`` 口径一致。
    """
    if not wp_code:
        return None
    return re.sub(r"-\d+$", "", wp_code.strip()) or None


async def derive_source_wp_code_and_year(
    db: AsyncSession,
    confirmation_id: uuid.UUID,
) -> tuple[str | None, int | None]:
    """从函证记录的 wp_id 反查 (源循环 wp_code, 审计年度)。

    - 记录不存在 / 无 wp_id → ``(None, None)``（调用方不触发 stale）。
    - 反查失败不抛异常（尽力而为），返回已取到的部分。
    """
    stmt = select(Confirmation.wp_id, Confirmation.project_id).where(
        Confirmation.id == confirmation_id
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None, None
    wp_id, project_id = row[0], row[1]

    # 无关联底稿 → 不臆测源循环码；year 仅在有 wp_code（会传播 stale）时才需要，
    # 故此处直接短路，避免多余的 projects 查询。
    if wp_id is None:
        return None, None

    wc_row = (
        await db.execute(
            sa_text(
                "SELECT wi.wp_code "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "WHERE wp.id = :wp_id AND wp.is_deleted = false "
                "LIMIT 1"
            ),
            {"wp_id": str(wp_id)},
        )
    ).first()
    wp_code = _normalize_source_wp_code(wc_row[0]) if wc_row is not None else None
    if not wp_code:
        return None, None

    year: int | None = None
    if project_id is not None:
        yr_row = (
            await db.execute(
                sa_text("SELECT audit_year FROM projects WHERE id = :pid LIMIT 1"),
                {"pid": str(project_id)},
            )
        ).first()
        if yr_row is not None and yr_row[0] is not None:
            year = int(yr_row[0])

    return wp_code, year
