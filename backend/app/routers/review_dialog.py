"""复核对话路由 — 线程管理 + 消息发送 + AI 生成

注册: router_registry/collaboration.py §125
Tables: review_threads, review_messages (V095)
"""
from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["review-dialog"])

# ── Pydantic Models ──────────────────────────────────────────────────────────

class CreateMessageRequest(BaseModel):
    content: str
    message_type: str = "text"
    target_user_id: str | None = None
    target_user_name: str | None = None
    target_role: str | None = None

class AiGenerateRequest(BaseModel):
    section_id: str
    related_data: dict = {}
    existing_content: str = ""

class ReviewMessageResponse(BaseModel):
    id: str
    thread_id: str
    sender_id: str
    sender_name: str
    sender_role: str
    content: str
    message_type: str
    target_user_id: str | None = None
    target_user_name: str | None = None
    target_role: str | None = None
    created_at: str

class ReviewThreadResponse(BaseModel):
    id: str
    thread_key: str
    status: str
    messages: list[ReviewMessageResponse]

class AiGenerateResponse(BaseModel):
    generated_text: str
    is_stub: bool = False


class ReviewRecipient(BaseModel):
    user_id: str
    user_name: str
    role: str | None = None

# ── Helpers ──────────────────────────────────────────────────────────────────

_ROLE_MAP = {
    "admin": "业务合伙人", "partner": "业务合伙人", "manager": "现场经理",
    "auditor": "审计助理", "qc": "质量控制复核合伙人", "eqcr": "EQCR技术复核人",
}

def _map_user_role(user: User) -> str:
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    return _ROLE_MAP.get(role_val, "审计助理")

async def _check_project_access(db: AsyncSession, user: User, project_id: UUID) -> None:
    """验证用户对项目有权限。

    与 deps.require_project_access 对齐：
    - admin / partner 跳过委派检查（可访问全部项目）
    - 其余用户：project_users 或 staff_members→project_assignments 任一命中即可
    """
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val in ("admin", "partner"):
        return

    uid, pid = str(user.id), str(project_id)

    pu = (await db.execute(text(
        "SELECT 1 FROM project_users pu "
        "WHERE pu.user_id = :uid AND pu.project_id = :pid "
        "AND pu.is_deleted = false LIMIT 1"
    ), {"uid": uid, "pid": pid})).fetchone()
    if pu is not None:
        return

    pa = (await db.execute(text(
        "SELECT 1 FROM project_assignments pa JOIN staff_members sm ON sm.id = pa.staff_id "
        "WHERE sm.user_id = :uid AND pa.project_id = :pid "
        "AND pa.is_deleted = false AND sm.is_deleted = false LIMIT 1"
    ), {"uid": uid, "pid": pid})).fetchone()
    if pa is not None:
        return

    raise HTTPException(status_code=403, detail="无权访问该项目的复核对话")

async def _get_project_id_for_wp(db: AsyncSession, wp_id: str) -> UUID:
    row = (await db.execute(
        text("SELECT project_id FROM working_paper WHERE id = :wid"), {"wid": wp_id},
    )).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return UUID(str(row[0]))

# ── GET /api/review-threads/active ───────────────────────────────────────────

class ActiveThreadItem(BaseModel):
    section_id: str
    has_unread: bool = False
    has_targeted_unread: bool = False

@router.get("/review-threads/active", response_model=list[ActiveThreadItem])
async def list_active_threads(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActiveThreadItem]:
    """返回某底稿的所有活跃线程列表（section_id + has_unread）。"""
    project_id = await _get_project_id_for_wp(db, wp_id)
    await _check_project_access(db, current_user, project_id)

    rows = (await db.execute(text(
        "SELECT rt.section_id, "
        "  CASE WHEN EXISTS ("
        "    SELECT 1 FROM review_messages rm "
        "    WHERE rm.thread_id = rt.id AND rm.sender_id != CAST(:uid AS uuid) "
        "    AND (rm.message_type <> 'private' OR rm.sender_id = CAST(:uid AS uuid) OR rm.target_user_id = CAST(:uid AS uuid) "
        "      OR (rm.target_user_name IS NOT NULL AND rm.target_user_name LIKE :uname_like)) "
        "    AND rm.created_at > COALESCE("
        "      (SELECT MAX(rm2.created_at) FROM review_messages rm2 "
        "       WHERE rm2.thread_id = rt.id AND rm2.sender_id = CAST(:uid AS uuid)), "
        "      rt.created_at"
        "    )"
        "  ) THEN true ELSE false END AS has_unread, "
        "  CASE WHEN EXISTS ("
        "    SELECT 1 FROM review_messages rm "
        "    WHERE rm.thread_id = rt.id AND rm.sender_id != CAST(:uid AS uuid) "
        "    AND (rm.target_user_id = CAST(:uid AS uuid) "
        "      OR (rm.target_user_name IS NOT NULL AND rm.target_user_name LIKE :uname_like)) "
        "    AND rm.created_at > COALESCE("
        "      (SELECT MAX(rm2.created_at) FROM review_messages rm2 "
        "       WHERE rm2.thread_id = rt.id AND rm2.sender_id = CAST(:uid AS uuid)), "
        "      rt.created_at"
        "    )"
        "  ) THEN true ELSE false END AS has_targeted_unread "
        "FROM review_threads rt "
        "WHERE rt.wp_id = :wid AND rt.status = 'open'"
    ), {
        "wid": wp_id,
        "uid": str(current_user.id),
        "uname_like": f"%{current_user.username}%",
    })).fetchall()

    return [
        ActiveThreadItem(
            section_id=r[0],
            has_unread=bool(r[1]),
            has_targeted_unread=bool(r[2]),
        )
        for r in rows
    ]

# ── GET /api/review-threads ──────────────────────────────────────────────────

@router.get("/review-threads", response_model=ReviewThreadResponse)
async def get_or_create_thread(
    wp_id: str, section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewThreadResponse:
    """获取线程（含消息列表）。若不存在则自动创建。"""
    project_id = await _get_project_id_for_wp(db, wp_id)
    await _check_project_access(db, current_user, project_id)
    thread_key = f"{wp_id}:{section_id}"

    row = (await db.execute(
        text("SELECT id, thread_key, status FROM review_threads WHERE thread_key = :tk"),
        {"tk": thread_key},
    )).fetchone()

    if row is None:
        await db.execute(text(
            "INSERT INTO review_threads (id, project_id, wp_id, section_id, thread_key, status, created_by) "
            "VALUES (:id, :pid, :wid, :sid, :tk, 'open', :uid) ON CONFLICT (thread_key) DO NOTHING"
        ), {"id": str(uuid4()), "pid": str(project_id), "wid": wp_id,
            "sid": section_id, "tk": thread_key, "uid": str(current_user.id)})
        await db.commit()
        row = (await db.execute(
            text("SELECT id, thread_key, status FROM review_threads WHERE thread_key = :tk"),
            {"tk": thread_key},
        )).fetchone()

    thread_id = str(row[0])
    msgs = (await db.execute(text(
        "SELECT rm.id, rm.thread_id, rm.sender_id, u.username, rm.sender_role, "
        "rm.content, rm.message_type, rm.target_user_id, rm.target_user_name, rm.target_role, rm.created_at "
        "FROM review_messages rm JOIN users u ON u.id = rm.sender_id "
        "WHERE rm.thread_id = :tid "
        "AND (rm.message_type <> 'private' OR rm.sender_id = CAST(:uid AS uuid) OR rm.target_user_id = CAST(:uid AS uuid) "
        "  OR (rm.target_user_name IS NOT NULL AND rm.target_user_name LIKE :uname_like)) "
        "ORDER BY rm.created_at ASC"
    ), {
        "tid": thread_id,
        "uid": str(current_user.id),
        "uname_like": f"%{current_user.username}%",
    })).fetchall()

    messages = [
        ReviewMessageResponse(
            id=str(m[0]), thread_id=str(m[1]), sender_id=str(m[2]),
            sender_name=m[3], sender_role=m[4], content=m[5],
            message_type=m[6], target_user_id=str(m[7]) if m[7] else None,
            target_user_name=m[8], target_role=m[9],
            created_at=m[10].isoformat() if m[10] else "",
        ) for m in msgs
    ]
    return ReviewThreadResponse(id=thread_id, thread_key=row[1], status=row[2], messages=messages)


@router.get("/review-dialog/recipients", response_model=list[ReviewRecipient])
async def list_review_recipients(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReviewRecipient]:
    """返回当前底稿所属项目可选接收人列表。"""
    project_id = await _get_project_id_for_wp(db, wp_id)
    await _check_project_access(db, current_user, project_id)
    rows = (await db.execute(text(
        "SELECT DISTINCT u.id::text AS user_id, "
        "COALESCE(sm.name, u.username) AS user_name, "
        "u.role::text AS role "
        "FROM users u "
        "LEFT JOIN staff_members sm ON sm.user_id = u.id AND sm.is_deleted = false "
        "WHERE u.is_deleted = false AND ("
        " EXISTS ("
        "   SELECT 1 FROM project_users pu "
        "   WHERE pu.user_id = u.id AND pu.project_id = :pid AND pu.is_deleted = false"
        " ) OR EXISTS ("
        "   SELECT 1 FROM project_assignments pa "
        "   WHERE pa.staff_id = sm.id AND pa.project_id = :pid AND pa.is_deleted = false"
        " )"
        ") "
        "ORDER BY user_name ASC"
    ), {"pid": str(project_id)})).fetchall()
    return [ReviewRecipient(user_id=str(r[0]), user_name=r[1], role=r[2]) for r in rows]

# ── POST /api/review-threads/{thread_id}/messages ────────────────────────────

@router.post("/review-threads/{thread_id}/messages", response_model=ReviewMessageResponse)
async def create_message(
    thread_id: str, body: CreateMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReviewMessageResponse:
    """发送消息 + broadcast_raw SSE 推送。"""
    trow = (await db.execute(
        text("SELECT id, status, project_id FROM review_threads WHERE id = :tid"),
        {"tid": thread_id},
    )).fetchone()
    if trow is None:
        raise HTTPException(status_code=404, detail="对话线程不存在")
    if trow[1] == "closed":
        raise HTTPException(status_code=400, detail="该对话已关闭，无法发送新消息")

    project_id = UUID(str(trow[2]))
    await _check_project_access(db, current_user, project_id)
    if body.message_type == "private" and not body.target_user_id:
        raise HTTPException(status_code=400, detail="私密消息必须指定接收人")
    sender_role = _map_user_role(current_user)
    msg_id = uuid4()

    await db.execute(text(
        "INSERT INTO review_messages ("
        "id, thread_id, sender_id, sender_role, content, message_type, "
        "target_user_id, target_user_name, target_role"
        ") VALUES ("
        ":id, :tid, :sid, :role, :content, :mtype, "
        ":target_user_id, :target_user_name, :target_role"
        ")"
    ), {"id": str(msg_id), "tid": thread_id, "sid": str(current_user.id),
        "role": sender_role, "content": body.content, "mtype": body.message_type,
        "target_user_id": body.target_user_id, "target_user_name": body.target_user_name,
        "target_role": body.target_role})
    await db.execute(text("UPDATE review_threads SET updated_at = now() WHERE id = :tid"), {"tid": thread_id})
    await db.commit()

    crow = (await db.execute(text("SELECT created_at FROM review_messages WHERE id = :id"), {"id": str(msg_id)})).fetchone()
    created_at = crow[0].isoformat() if crow else ""

    # SSE broadcast
    try:
        from app.services.event_bus import event_bus
        event_bus.broadcast_raw("review_message.created", {
            "project_id": str(project_id), "thread_id": thread_id,
            "message": {
                "id": str(msg_id), "sender_id": str(current_user.id),
                "sender_name": current_user.username, "sender_role": sender_role,
                "content": body.content, "message_type": body.message_type,
                "target_user_id": body.target_user_id, "target_user_name": body.target_user_name,
                "target_role": body.target_role,
                "created_at": created_at,
            },
        })
    except Exception as exc:
        logger.warning("broadcast_raw failed: %s", exc)

    return ReviewMessageResponse(
        id=str(msg_id), thread_id=thread_id, sender_id=str(current_user.id),
        sender_name=current_user.username, sender_role=sender_role,
        content=body.content, message_type=body.message_type,
        target_user_id=body.target_user_id, target_user_name=body.target_user_name,
        target_role=body.target_role, created_at=created_at,
    )

# ── POST /api/workpapers/{wp_id}/review-dialog/ai-generate ──────────────────

_REVIEW_AI_SYSTEM_PROMPT = (
    "你是一位资深注册会计师（CPA），正在协助编制审计底稿。\n"
    "根据提供的审定表数据变动信息，生成专业的{section_type}文本。\n\n"
    "要求：\n- 语言：中文，审计专业用语\n- 风格：客观陈述事实，引用具体数据\n"
    "- 如为\u201c审计说明\u201d：描述审计程序执行情况和发现\n"
    "- 如为\u201c审计结论\u201d：给出审计结论和建议\n"
    "- 引用审定表数据时使用具体数字\n- 不超过300字"
)

# ── 按 section_id 精确命中的专属 prompt（纯增量，未命中回退通用 prompt）─────────
#
# 🔴 铁律：prompt 过短会诱导模型自造披露内容。每条必须 ≥20 字并写明源模板 / 15 号文 /
#    校验预设口径 + 「不得虚构」约束。新增前端 section_id 必须同时在此登记，
#    守卫见 `backend/tests/test_review_dialog_section_prompts.py`。

_NO_FABRICATION = (
    "严禁虚构未提供的数据、单位名称、金额或事实；上下文缺失的部分直接留空或写\u201c待补充\u201d，"
    "不得推测。只依据给定数据组织语言。"
)

_D1_DISCLOSURE_PROMPTS: dict[str, str] = {
    "top": (
        "撰写应收票据附注总体说明。依据源模板提示：不属于《票据法》规范的\u201c云信\u201d\u201c融信\u201d等"
        "数字化应收账款债权凭证不在\u201c应收票据\u201d列示；供应链票据自 2023 年 1 月 1 日起按业务模式"
        "列示为应收票据或应收款项融资。结合银行承兑汇票与商业承兑汇票的期末 / 上年年末账面余额、"
        "坏账准备、账面价值说明构成与变动原因。"
    ),
    "pledged": (
        "撰写期末已质押应收票据的说明。按票据种类说明质押金额、质押事由与对应的借款或担保安排，"
        "并说明质押对票据可回收性与流动性的影响（15 号文关于所有权受限资产的披露要求）。"
    ),
    "endorsed": (
        "撰写期末已背书或贴现但尚未到期应收票据的说明。依据《企业会计准则第 23 号——金融资产转移》"
        "与证监会《2014 年上市公司年报会计监管报告》，分别说明终止确认与未终止确认的判断依据"
        "（承兑行信用等级、追索权是否影响、主要风险和报酬是否转移），并说明票据被追索时可能存在的"
        "支付风险。"
    ),
    "badDebtClass": (
        "撰写坏账准备计提方法分类的说明。区分按单项计提与按组合计提，说明组合的划分依据"
        "（出票人类型或账龄）、预期信用损失率的确定方法与关键假设。注意源模板口径：此处只披露"
        "未逾期的应收票据；票据逾期应转入应收账款并计提坏账准备、账龄连续计算。"
    ),
    "writeOff": (
        "撰写本期实际核销应收票据的说明。对其中重要的核销逐项说明款项性质、核销原因、"
        "履行的核销程序及核销金额；由关联交易产生的款项须单独说明"
        "（源模板核销表附注要求）。"
    ),
}

_SECTION_PROMPTS: dict[str, str] = {
    # D1 应收票据附注披露（上市 / 国企两版共用同一子节口径）
    **{
        f"d1-disclosure-{variant}-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for variant in ("listed", "soe")
        for key, text in _D1_DISCLOSURE_PROMPTS.items()
    },
    # D1-1 审定表
    "d1-adjudication-audit-note": (
        "撰写 D1-1 应收票据审定表的审计说明。依据各区块（账面余额 / 坏账准备 / 净值）的"
        "期初审定数、期末审定数与变动额，说明已执行的审计程序（监盘、函证、贴现背书检查、"
        "坏账准备复核）及发现，并说明与试算平衡表的差异原因。\n"
        + _NO_FABRICATION
    ),
    "d1-adjudication-audit-conclusion": (
        "撰写 D1-1 应收票据审定表的审计结论。依据期末审定数与试算平衡表差异，就应收票据的"
        "存在、完整性、计价与分摊、列报是否恰当给出结论，并指出需提请管理层调整或关注的事项。\n"
        + _NO_FABRICATION
    ),
}


def resolve_review_ai_prompt(section_id: str, section_type: str) -> str:
    """按 ``section_id`` 取专属 prompt；未登记则回退通用 prompt（保持存量行为）。"""
    specific = _SECTION_PROMPTS.get(section_id)
    if specific:
        return (
            f"你是一位资深注册会计师（CPA），正在协助编制审计底稿的{section_type}。\n"
            f"{specific}\n"
            "语言：中文，审计专业用语；客观陈述事实并引用具体数字；不超过 400 字。"
        )
    return _REVIEW_AI_SYSTEM_PROMPT.format(section_type=section_type)


@router.post("/workpapers/{wp_id}/review-dialog/ai-generate", response_model=AiGenerateResponse)
async def ai_generate_review_text(
    wp_id: str, body: AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiGenerateResponse:
    """AI 生成审计说明/结论文本。"""
    project_id = await _get_project_id_for_wp(db, wp_id)
    await _check_project_access(db, current_user, project_id)

    section_type = "审计说明" if "note" in body.section_id else "审计结论"
    system_prompt = resolve_review_ai_prompt(body.section_id, section_type)
    parts = [f"请为以下底稿区域生成{section_type}："]
    if body.related_data:
        parts.append(f"审定表数据：{json.dumps(body.related_data, ensure_ascii=False)}")
    if body.existing_content:
        parts.append(f"当前已有内容（供参考）：{body.existing_content}")

    try:
        from app.services.llm_client import chat_completion
        result = await chat_completion(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "\n".join(parts)}],
            temperature=0.3, max_tokens=800,
        )
        return AiGenerateResponse(generated_text=result if isinstance(result, str) else "", is_stub=False)
    except Exception as exc:
        logger.warning("AI generate failed: %s", exc)
        raise HTTPException(status_code=503, detail="AI服务暂时不可用，请手动填写")
