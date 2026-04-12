"""合并抵消路由"""



from decimal import Decimal

from uuid import UUID



from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from app.deps import get_current_user

from app.core.database import get_db

from app.models.consolidation_models import (

    EliminationEntryType,

    ForexTranslation,

    ReviewStatusEnum,

)

from app.models.consolidation_schemas import (

    EliminationCreate,

    EliminationEntryResponse,

    EliminationEntryUpdate,

    EliminationReviewAction,

    EliminationSummary,

    ForexRates,

    ForexTranslationCreate,

    ForexTranslationResponse,

    ForexTranslationResult,

    ForexTranslationUpdate,

    GoodwillCalcResponse,

    GoodwillInput,

    InternalArApCreate,

    InternalArApResponse,

    InternalArApUpdate,

    InternalTradeCreate,

    InternalTradeResponse,

    InternalTradeUpdate,

    MinorityInterestBatchResult,

    MinorityInterestCreate,

    MinorityInterestEliminationResponse,

    MinorityInterestResponse,

    MinorityInterestUpdate,

    ReconciliationStatus,

    ReviewStatusEnum,

    TransactionMatrix,

    TranslationWorksheet,

    TradeType,

)

from app.services.elimination_service import (

    change_review_status,

    create_entry,

    delete_entry,

    get_entries,

    get_entry,

    get_summary,

    update_entry,

)

from app.services.forex_translation_service import (

    apply_to_consol_trial,

    create_forex,

    delete_forex,

    get_forex_by_company,

    get_forex_list,

    get_translation_worksheet,

    translate,

    update_forex,

)

from app.services.goodwill_service import (

    carry_forward,

    create_goodwill,

    delete_goodwill,

    get_goodwill,

    get_goodwill_list,

    record_impairment,

    update_goodwill,

)

from app.services.internal_trade_service import (

    auto_generate_eliminations,

    create_arap,

    create_trade,

    delete_arap,

    delete_trade,

    get_arap,

    get_arap_list,

    get_trade,

    get_trades,

    reconcile_arap,

    update_arap,

    update_trade,

)



router = APIRouter(prefix="/api/consolidation/eliminations", tags=["合并抵消"])





@router.get("", response_model=list[EliminationEntryResponse])

def list_eliminations(

    project_id: UUID,

    year: int | None = None,

    entry_type: EliminationEntryType | None = None,

    review_status: ReviewStatusEnum | None = None,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return get_entries(db, project_id, year, entry_type, review_status)





@router.post("", response_model=EliminationEntryResponse, status_code=201)

def create_elimination(

    project_id: UUID,

    data: EliminationCreate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    try:

        return create_entry(db, project_id, data)

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





@router.get("/{entry_id}", response_model=EliminationEntryResponse)

def get_elimination(

    entry_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    entry = get_entry(db, entry_id, project_id)

    if not entry:

        raise HTTPException(status_code=404, detail="抵消分录不存在")

    return entry





@router.put("/{entry_id}", response_model=EliminationEntryResponse)

def update_elimination(

    entry_id: UUID,

    project_id: UUID,

    data: EliminationEntryUpdate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    try:

        entry = update_entry(db, entry_id, project_id, data)

        if not entry:

            raise HTTPException(status_code=404, detail="抵消分录不存在")

        return entry

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





@router.delete("/{entry_id}", status_code=204)

def delete_elimination(

    entry_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    try:

        if not delete_entry(db, entry_id, project_id):

            raise HTTPException(status_code=404, detail="抵消分录不存在")

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





@router.post("/{entry_id}/review", response_model=EliminationEntryResponse)

def review_elimination(

    entry_id: UUID,

    project_id: UUID,

    action: EliminationReviewAction,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    try:

        entry = change_review_status(db, entry_id, project_id, action, user.id)

        if not entry:

            raise HTTPException(status_code=404, detail="抵消分录不存在")

        return entry

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





@router.get("/summary/year", response_model=list[EliminationSummary])

def elimination_summary(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return get_summary(db, project_id, year)





# ---------------------------------------------------------------------------

# 内部交易

# ---------------------------------------------------------------------------



_trade_router = APIRouter(prefix="/api/consolidation/trades", tags=["内部交易"])





@_trade_router.get("", response_model=list[InternalTradeResponse])

def list_trades(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return get_trades(db, project_id, year)





@_trade_router.get("/{trade_id}", response_model=InternalTradeResponse)

def get_trade_detail(

    trade_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    trade = get_trade(db, trade_id, project_id)

    if not trade:

        raise HTTPException(status_code=404, detail="内部交易不存在")

    return trade





@_trade_router.post("", response_model=InternalTradeResponse)

def create_trade_endpoint(

    project_id: UUID,

    data: InternalTradeCreate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return create_trade(db, project_id, data)





@_trade_router.put("/{trade_id}", response_model=InternalTradeResponse)

def update_trade_endpoint(

    trade_id: UUID,

    project_id: UUID,

    data: InternalTradeUpdate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    trade = update_trade(db, trade_id, project_id, data)

    if not trade:

        raise HTTPException(status_code=404, detail="内部交易不存在")

    return trade





@_trade_router.delete("/{trade_id}")

def delete_trade_endpoint(

    trade_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    ok = delete_trade(db, trade_id, project_id)

    if not ok:

        raise HTTPException(status_code=404, detail="内部交易不存在")

    return {"ok": True}





# ---------------------------------------------------------------------------

# 内部往来

# ---------------------------------------------------------------------------



_arap_router = APIRouter(prefix="/api/consolidation/arap", tags=["内部往来"])





@_arap_router.get("", response_model=list[InternalArApResponse])

def list_arap(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return get_arap_list(db, project_id, year)





@_arap_router.get("/{arap_id}", response_model=InternalArApResponse)

def get_arap_detail(

    arap_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    arap = get_arap(db, arap_id, project_id)

    if not arap:

        raise HTTPException(status_code=404, detail="内部往来不存在")

    return arap





@_arap_router.post("", response_model=InternalArApResponse)

def create_arap_endpoint(

    project_id: UUID,

    data: InternalArApCreate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    return create_arap(db, project_id, data)





@_arap_router.put("/{arap_id}", response_model=InternalArApResponse)

def update_arap_endpoint(

    arap_id: UUID,

    project_id: UUID,

    data: InternalArApUpdate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    arap = update_arap(db, arap_id, project_id, data)

    if not arap:

        raise HTTPException(status_code=404, detail="内部往来不存在")

    return arap





@_arap_router.delete("/{arap_id}")

def delete_arap_endpoint(

    arap_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    ok = delete_arap(db, arap_id, project_id)

    if not ok:

        raise HTTPException(status_code=404, detail="内部往来不存在")

    return {"ok": True}





@_arap_router.post("/reconcile", response_model=list[InternalArApResponse])

def reconcile_arap_endpoint(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """批量核对内部往来,计算差额并更新核对状态"""

    return reconcile_arap(db, project_id, year)





# ---------------------------------------------------------------------------

# 交易矩阵 & 自动抵消

# ---------------------------------------------------------------------------





@router.get("/transaction-matrix", response_model=TransactionMatrix)

def transaction_matrix(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    from app.services.internal_trade_service import get_transaction_matrix

    return get_transaction_matrix(db, project_id, year)





@router.post("/auto-eliminations", response_model=list[EliminationEntryResponse])

def generate_auto_eliminations(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """根据内部交易和内部往来自动生成抵消分录"""

    from app.models.consolidation_schemas import EliminationEntryResponse

    entries = auto_generate_eliminations(db, project_id, year)

    return [EliminationEntryResponse.model_validate(e) for e in entries]





# ---------------------------------------------------------------------------

# 少数股东权益

# ---------------------------------------------------------------------------



_mi_router = APIRouter(prefix="/api/consolidation/minority-interest", tags=["少数股东权益"])





@_mi_router.get("", response_model=list[MinorityInterestResponse])

def list_minority_interest(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """获取指定项目和年度的全部少数股东权益记录"""

    from app.services.minority_interest_service import get_minority_interest_list

    return get_minority_interest_list(db, project_id, year)





@_mi_router.post("", response_model=MinorityInterestResponse, status_code=201)

def create_minority_interest_endpoint(

    project_id: UUID,

    data: MinorityInterestCreate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """创建少数股东权益记录"""

    from app.services.minority_interest_service import create_minority_interest

    return create_minority_interest(db, project_id, data)





@_mi_router.put("/{mi_id}", response_model=MinorityInterestResponse)

def update_minority_interest_endpoint(

    mi_id: UUID,

    project_id: UUID,

    data: MinorityInterestUpdate,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """更新少数股东权益记录"""

    from app.services.minority_interest_service import update_minority_interest

    mi = update_minority_interest(db, mi_id, project_id, data)

    if not mi:

        raise HTTPException(status_code=404, detail="少数股东权益记录不存在")

    return mi





@_mi_router.delete("/{mi_id}", status_code=204)

def delete_minority_interest_endpoint(

    mi_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """软删除少数股东权益记录"""

    from app.services.minority_interest_service import delete_minority_interest

    if not delete_minority_interest(db, mi_id, project_id):

        raise HTTPException(status_code=404, detail="少数股东权益记录不存在")





@_mi_router.post("/calculate", response_model=MinorityInterestBatchResult)

def batch_calculate_minority_interest(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """

    批量计算所有全额合并子公司的少数股东权益(Requirement 5.5)



    companies 表筛consol_method=full 的子公司,从 consol_trial 汇总净资产和净利润

    minority_share_ratio = 1 - parent_share_ratio,结果写入 minority_interest 表(upsert)

    """

    from app.services.minority_interest_service import batch_calculate

    return batch_calculate(db, project_id, year)





@_mi_router.post(

    "/generate-elimination",

    response_model=MinorityInterestEliminationResponse,

    summary="5.8 生成少数股东权益/损益抵消分录",

)

def generate_minority_elimination_endpoint(

    project_id: UUID,

    subsidiary_code: str,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

) -> MinorityInterestEliminationResponse:

    """

    为指定子公司生成少数股东权益/损益抵消分录(Requirement 5.8)



    抵消逻辑(完全合并法):

        借:少数股东损益  (净利润 * 少数股东持股比例

        贷:少数股东权益  (期末少数股东权益 - 期初少数股东权益

    """

    from app.services.minority_interest_service import generate_minority_elimination

    try:

        return generate_minority_elimination(db, project_id, year, subsidiary_code)

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





# ---------------------------------------------------------------------------

# 外币折算

# ---------------------------------------------------------------------------



_forex_router = APIRouter(prefix="/api/consolidation/forex", tags=["外币折算"])





@_forex_router.get("", response_model=list[ForexTranslationResponse])

async def list_forex_translations(

    project_id: UUID,

    year: int,

    user=Depends(get_current_user),

):

    """获取指定项目和年度的全部外币折算记录"""

    from app.core.database import async_session

    async with async_session() as session:

        records = await get_forex_list(session, project_id, year)

        return [ForexTranslationResponse.model_validate(r) for r in records]





@_forex_router.post("/translate", response_model=ForexTranslationResponse)

async def execute_forex_translation(

    project_id: UUID,

    company_code: str,

    year: int,

    rates: ForexRates,

    user=Depends(get_current_user),

):

    """

    对境外子公司执行外币报表折算(apply_to_consol_trial)



    折算规则

    1. 资产/负债:期末汇率(bs_closing_rate)

    2. 收入/成本/费用:平均汇率(pl_average_rate)

    3. 实收资本/资本公积:历史汇率(equity_historical_rate)

    4. 未分配利润:公式推算

    5. 折算差额 -> 其他综合收益(OCI)



    执行后自动将折算后金额替换到合并试算(individual_sum)

    """

    from app.core.database import async_session

    async with async_session() as session:

        forex_record, result = await translate(

            session, project_id, year, company_code, rates

        )

        # 应用到合并试算表

        await apply_to_consol_trial(session, project_id, year, company_code)

        await session.commit()

        return ForexTranslationResponse.model_validate(forex_record)





@_forex_router.get("/worksheet", response_model=TranslationWorksheet)

async def get_forex_worksheet(

    project_id: UUID,

    year: int,

    company_code: str,

    user=Depends(get_current_user),

):

    """

    获取指定子公司的外币折算工作表



    返回结构:原币金| 适用汇率 | 折算金额(CNY) | 折算差额汇总

    """

    from app.core.database import async_session

    async with async_session() as session:

        return await get_translation_worksheet(session, project_id, year, company_code)





@_forex_router.post("", response_model=ForexTranslationResponse, status_code=201)

async def create_forex_translation(

    data: ForexTranslationCreate,

    user=Depends(get_current_user),

):

    """创建外币折算记录"""

    from app.core.database import async_session

    async with async_session() as session:

        record = await create_forex(session, data)

        await session.commit()

        return ForexTranslationResponse.model_validate(record)





@_forex_router.get("/{forex_id}", response_model=ForexTranslationResponse)

async def get_forex_translation(

    forex_id: UUID,

    project_id: UUID,

    user=Depends(get_current_user),

):

    """根据 ID 获取单条外币折算记录"""

    from app.core.database import async_session

    async with async_session() as session:

        result = await session.execute(

            select(ForexTranslation).where(

                ForexTranslation.id == forex_id,

                ForexTranslation.project_id == project_id,

                ForexTranslation.is_deleted == False,  # noqa: E712

            )

        )

        record = result.scalar_one_or_none()

        if not record:

            raise HTTPException(status_code=404, detail="外币折算记录不存在")

        return ForexTranslationResponse.model_validate(record)





@_forex_router.put("/{forex_id}", response_model=ForexTranslationResponse)

async def update_forex_translation(

    forex_id: UUID,

    project_id: UUID,

    data: ForexTranslationUpdate,

    user=Depends(get_current_user),

):

    """更新外币折算记录"""

    from app.core.database import async_session

    async with async_session() as session:

        record = await update_forex(session, forex_id, project_id, data)

        if not record:

            raise HTTPException(status_code=404, detail="外币折算记录不存在")

        await session.commit()

        return ForexTranslationResponse.model_validate(record)





@_forex_router.delete("/{forex_id}", status_code=204)

async def delete_forex_translation(

    forex_id: UUID,

    project_id: UUID,

    user=Depends(get_current_user),

):

    """软删除外币折算记录"""

    from app.core.database import async_session

    async with async_session() as session:

        ok = await delete_forex(session, forex_id, project_id)

        if not ok:

            raise HTTPException(status_code=404, detail="外币折算记录不存在")

        await session.commit()





# ---------------------------------------------------------------------------

# 商誉

# ---------------------------------------------------------------------------



_goodwill_router = APIRouter(prefix="/api/consolidation/goodwill", tags=["商誉"])





@_goodwill_router.get("", response_model=list[GoodwillCalcResponse])

def list_goodwill(

    project_id: UUID,

    year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """获取指定项目和年度的全部商誉记录"""

    return get_goodwill_list(db, project_id, year)





@_goodwill_router.get("/{goodwill_id}", response_model=GoodwillCalcResponse)

def get_goodwill_detail(

    goodwill_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """根据 ID 获取单条商誉记录"""

    goodwill = get_goodwill(db, goodwill_id, project_id)

    if not goodwill:

        raise HTTPException(status_code=404, detail="商誉记录不存在")

    return goodwill





@_goodwill_router.post("", response_model=GoodwillCalcResponse, status_code=201)

def create_goodwill_endpoint(

    project_id: UUID,

    data: GoodwillInput,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """创建商誉计算记录,自动计算商誉金额(含负商誉处理)"""

    return create_goodwill(db, project_id, data)





@_goodwill_router.put("/{goodwill_id}", response_model=GoodwillCalcResponse)

def update_goodwill_endpoint(

    goodwill_id: UUID,

    project_id: UUID,

    data: GoodwillInput,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """更新商誉计算记录,若关键参数变化则自动重算商誉"""

    goodwill = update_goodwill(db, goodwill_id, project_id, data)

    if not goodwill:

        raise HTTPException(status_code=404, detail="商誉记录不存在")

    return goodwill





@_goodwill_router.delete("/{goodwill_id}", status_code=204)

def delete_goodwill_endpoint(

    goodwill_id: UUID,

    project_id: UUID,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """软删除商誉记录"""

    if not delete_goodwill(db, goodwill_id, project_id):

        raise HTTPException(status_code=404, detail="商誉记录不存在")





@_goodwill_router.post("/impairment", response_model=GoodwillCalcResponse)

def record_goodwill_impairment(

    project_id: UUID,

    company_code: str,

    year: int,

    impairment_amount: Decimal,

    notes: str | None = None,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """记录商誉减值,自动生成减值抵消分录并发布事件"""

    try:

        return record_impairment(db, project_id, company_code, year, impairment_amount, notes)

    except ValueError as e:

        raise HTTPException(status_code=400, detail=str(e))





@_goodwill_router.post("/carry-forward", response_model=dict)

def carry_forward_goodwill(

    project_id: UUID,

    from_year: int,

    to_year: int,

    db: AsyncSession = Depends(get_db),

    user=Depends(get_current_user),

):

    """结转上年商誉数据到当年,累计减值自动更新"""

    return carry_forward(db, project_id, from_year, to_year)





# 注册子路由

router.include_router(_trade_router)

router.include_router(_arap_router)

router.include_router(_goodwill_router)

router.include_router(_mi_router)

router.include_router(_forex_router)

