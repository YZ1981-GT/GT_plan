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
    "transfer": (
        "撰写期末因出票人未履约而转为应收账款票据的说明。依据《企业会计准则第 23 号——"
        "金融资产转移》说明终止确认的金额及与终止确认相关的利得或损失（源模板该表括注要求）；"
        "并说明票据逾期后转入应收账款、账龄连续计算的处理，以及对应收账款坏账准备的影响。"
        "注意该表只列示商业承兑票据。"
    ),
    "badDebtClass": (
        "撰写坏账准备计提方法分类的说明。区分按单项计提与按组合计提，说明组合的划分依据"
        "（出票人类型或账龄）、预期信用损失率的确定方法与关键假设。注意源模板口径：此处只披露"
        "未逾期的应收票据；票据逾期应转入应收账款并计提坏账准备、账龄连续计算。"
    ),
    "badDebtMovement": (
        "撰写本期坏账准备变动的说明。按「期初 + 本期计提 − 收回或转回 − 核销 − 其他变动 = 期末」"
        "的口径说明各项变动的成因；说明按组合计提坏账准备的原因（源模板要求）；"
        "对本期转回或收回金额重要者，说明债务人、转回或收回的原因与方式、"
        "以及原确定坏账准备的依据。"
    ),
    "writeOff": (
        "撰写本期实际核销应收票据的说明。对其中重要的核销逐项说明款项性质、核销原因、"
        "履行的核销程序及核销金额；由关联交易产生的款项须单独说明"
        "（源模板核销表附注要求）。"
    ),
}

# D3 预收款项（源模板 `D3 预收账款.xlsx`；国企侧源模板无说明段，故只有上市 3 段）
_D3_DISCLOSURE_PROMPTS: dict[str, str] = {
    "nature": (
        "撰写预收款项按性质分类的附注说明。依据审定表 D3-1 的期末余额与上年年末余额，"
        "说明预收款项的主要构成（如预收工程款、预收货款、预收租金）、形成原因，"
        "以及与合同负债的划分口径（属于合同负债的部分不在本项目列示）。"
    ),
    "longTerm": (
        "撰写账龄超过 1 年的重要预收款项说明。逐项说明债权单位、期末余额与未偿还或未结转的原因"
        "（如工程未完工验收、商品尚未交付、退款条件未满足），并说明是否存在需转入其他应付款"
        "或确认收入的情形。"
    ),
    "change": (
        "撰写本期预收款项账面价值重大变动的说明。按项目说明变动金额与变动原因"
        "（新签合同预收、履约义务完成转收入、退款、合同变更等），"
        "并说明变动对收入确认时点与流动性的影响。"
    ),
}

# D5 应收款项融资（源模板 `D5 应收款项融资.xlsx`）
_D5_DISCLOSURE_PROMPTS: dict[str, str] = {
    "listed-1": (
        "撰写应收款项融资分类的附注说明。依据源模板提示：本项目反映资产负债表日以公允价值计量"
        "且其变动计入其他综合收益的应收票据和应收账款。说明业务模式判断依据"
        "（是否经常贴现或背书信用等级较高的银行承兑汇票 → 既收取合同现金流量又出售），"
        "并按「票面金额或余额 − 公允价值变动 = 期末公允价值」的口径说明构成与变动。"
    ),
    "listed-2": (
        "撰写应收款项融资减值准备变动的说明。按「上年年末余额 + 本期计提 − 本期收回或转回 "
        "− 本期核销 − 本期转销 − 其他 = 期末余额」的口径说明各项变动成因；"
        "若涉及应收账款，说明其减值准备计提与核销参考应收账款相应附注的口径。"
    ),
    "listed-3": (
        "撰写已质押、已背书或贴现但尚未到期的应收票据说明。按票据种类说明质押金额与质押事由；"
        "依据《企业会计准则第 23 号——金融资产转移》说明终止确认与未终止确认的判断依据"
        "（承兑行信用等级、追索权、主要风险和报酬是否转移），并说明被追索时可能存在的支付风险。"
    ),
    "soe-1": (
        "撰写国企版应收款项融资分类说明。按应收票据、应收账款两类说明期末余额与期初余额的构成"
        "与变动；并说明应收账款的减值准备与核销参考附注八、5（3）（4），应收票据的质押、背书或"
        "贴现、出票人未履约、坏账准备计提参考附注八、4（2）至（6）。"
    ),
}

# D6 合同资产（源模板 `D6 合同资产.xlsx`；键 = 文本域键去掉 `D6-note-` 前缀）
_D6_DISCLOSURE_PROMPTS: dict[str, str] = {
    "listed-text-1": (
        "撰写合同资产分类的附注说明。依据源模板提示：同一合同下的合同资产与合同负债应以净额列示，"
        "净额为借方余额时按流动性在「合同资产」或「其他非流动资产」列示。结合按单项计提与按组合计提"
        "的账面余额、减值准备、账面价值（期末与上年年末）说明构成与变动原因。"
    ),
    "listed-text-major-change": (
        "撰写本期合同资产账面价值重大变动的说明。变动情形包括企业合并导致的变动、"
        "对收入进行累积追加调整导致的变动（源于估计履约进度、估计交易价格变化或合同变更）、"
        "以及对合同对价的权利成为无条件权利（合同资产重分类为应收款项）的时间安排变化。"
    ),
    "listed-text-2": (
        "撰写合同资产减值准备计提情况的说明。区分按单项计提与按组合计提，说明组合划分依据、"
        "预期信用损失率的确定方法与关键假设。依据源模板注意事项：计量合同资产预期信用损失时"
        "考虑的期限应截止于预期收取现金流量之日，需考虑合同资产转为应收款项后可能发生的违约损失；"
        "合同资产与应收账款账龄不连续计算。"
    ),
    "listed-text-3": (
        "撰写按单项计提减值准备的合同资产明细说明。逐项说明名称、账面余额、坏账准备、"
        "预期信用损失率及计提理由（如客户财务困难、结算争议、工程质量纠纷），"
        "并说明期末与上年年末的变化原因。"
    ),
    "listed-text-4": (
        "撰写按组合计提减值准备的合同资产明细说明。说明组合的划分标准（如工程施工、质量保证金）、"
        "各账龄段的合同资产与坏账准备、预期信用损失率的确定依据，"
        "以及本期损失率变化的原因与合理性。"
    ),
    "listed-text-5": (
        "撰写本期计提、收回或转回合同资产减值准备的说明。逐项说明本期计提、本期转回、"
        "本期转销/核销的金额与原因；对重要的转回或核销，说明依据、审批程序与是否涉及关联方。"
    ),
    "soe-text-1": (
        "撰写国企版合同资产情况说明。按单项计提与按组合计提说明期末数与期初数的账面余额、"
        "减值准备、账面价值构成；说明合同资产与合同负债以净额列示的口径，"
        "以及组合明细（业务类型组合、客户类型组合）的划分依据。"
    ),
    "soe-text-2": (
        "撰写国企版合同资产减值准备变动说明。按「期初数 + 计提 − 转回 − 转销/核销 = 期末数」"
        "的口径说明各项变动的成因，并对重要的计提、转回与转销/核销逐项说明原因与审批依据。"
    ),
    "soe-text-3": (
        "撰写国企版合同资产账面价值重大变动说明（源模板标注国资委格式未要求披露，按需填列）。"
        "说明变动金额与变动原因，包括企业合并、收入累积追加调整、"
        "合同资产重分类为应收款项的时间安排变化。"
    ),
}

# D7 合同负债（源模板 `D7 合同负债.xlsx`；键 = 文本域键去掉 `D7-note-` 前缀）
_D7_QUALITATIVE_PROMPTS: dict[str, str] = {
    "qual-1": (
        "撰写「在本期确认的、包括在合同负债期初账面价值中的收入」的披露说明。说明本期确认的"
        "该部分收入金额及其构成，并说明前期已履行（或部分履行）履约义务在本期确认的收入"
        "（如交易价格变动导致），依据 CAS14 收入准则的披露要求组织语言。"
    ),
    "qual-2": (
        "撰写履行履约义务的时间与通常付款时间之间关系的披露说明。说明预收款与履约进度的时间差、"
        "典型合同的收款节奏与结转收入节奏，以及此类因素对合同负债账面价值影响的定量或定性信息。"
    ),
    "qual-3": (
        "撰写合同负债账面价值在本期内发生重大变动情形的披露说明。情形包括企业合并导致的变动、"
        "对收入进行累积追加调整导致的变动（源于估计履约进度、估计交易价格变化或合同变更）、"
        "以及履行履约义务（从合同负债转为收入）的时间安排发生变化。"
    ),
}

_D7_DISCLOSURE_PROMPTS: dict[str, str] = {
    "listed-text-1": (
        "撰写合同负债按性质分类的附注说明。依据审定表 D7-1 的期末余额与上年年末余额说明主要构成"
        "（如预收货款、预收工程款、预收会员费）。依据源模板提示：同一合同下的合同资产与合同负债"
        "应以净额列示，净额为贷方余额时按流动性在「合同负债」或「其他非流动负债」列示，"
        "预计一年内到期的在「合同负债」列示。"
    ),
    "listed-text-2": (
        "撰写账龄超过 1 年的重要合同负债说明。逐项说明项目、期末余额与未偿还或未结转的原因"
        "（履约义务尚未完成、验收未通过、退款条件未满足等），"
        "并说明是否存在需退款或转入其他应付款的情形。"
    ),
    "listed-text-3": (
        "撰写本期合同负债账面价值重大变动的说明。按项目说明变动金额与变动原因"
        "（新签合同预收、履约义务完成转收入、合同变更、退款等），"
        "并说明变动对收入确认节奏的影响。"
    ),
    **{f"listed-{k}": v for k, v in _D7_QUALITATIVE_PROMPTS.items()},
    "soe-text-1": (
        "撰写国企版合同负债按性质分类说明。依据审定表 D7-1 说明期末余额与期初余额的构成与变动，"
        "并说明与预收款项、其他非流动负债的划分口径。"
    ),
    "soe-text-2": (
        "撰写国企版本期合同负债账面价值重大变动说明。按项目说明变动金额与变动原因，"
        "并说明对收入确认时点与资产负债表列报流动性划分的影响。"
    ),
    **{f"soe-{k}": v for k, v in _D7_QUALITATIVE_PROMPTS.items()},
}

_SECTION_PROMPTS: dict[str, str] = {
    # D1 应收票据附注披露（上市 / 国企两版共用同一子节口径）
    **{
        f"d1-disclosure-{variant}-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for variant in ("listed", "soe")
        for key, text in _D1_DISCLOSURE_PROMPTS.items()
    },
    # D3 预收款项（仅上市侧有说明文本域；国企源模板无说明段）
    **{
        f"d3-disclosure-listed-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for key, text in _D3_DISCLOSURE_PROMPTS.items()
    },
    # D5 应收款项融资（键已含变体）
    **{
        f"d5-disclosure-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for key, text in _D5_DISCLOSURE_PROMPTS.items()
    },
    # D6 合同资产（键已含变体）
    **{
        f"d6-disclosure-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for key, text in _D6_DISCLOSURE_PROMPTS.items()
    },
    # D7 合同负债（键已含变体；含源模板要求的 3 段定性披露 × 两版）
    **{
        f"d7-disclosure-{key}-note": f"{text}\n{_NO_FABRICATION}"
        for key, text in _D7_DISCLOSURE_PROMPTS.items()
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
