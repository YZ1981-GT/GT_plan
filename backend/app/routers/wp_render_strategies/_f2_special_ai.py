"""F2 特殊组 — AI 辅助生成（合同履约 + IPO）."""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["f2-spe-ai"])


class F2SpeAiRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2SpeAiResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED = {
    "contract-cost-note",
    "contract-cost-conclusion",
    "contract-check-note",
    "contract-check-conclusion",
    "contract-check-issue",
    "contract-impairment-note",
    "contract-impairment-conclusion",
    "loss-contract-note",
    "loss-contract-conclusion",
    "purchase-price-variance-note",
    "purchase-price-market-note",
    "purchase-price-conclusion",
    "unit-price-note",
    "unit-price-conclusion",
    "capacity-utilization-note",
    "storage-capacity-note",
    "energy-consumption-note",
    "capacity-energy-conclusion",
    "production-cost-structure-note",
    "production-cost-flow-note",
    "product-unit-cost-note",
    "material-consumption-note",
    "unit-consumption-conclusion",
    "related-inquiry-note",
    "related-inquiry-conclusion",
    "related-market-note",
    "related-market-conclusion",
    "undisclosed-party-note",
    "undisclosed-party-conclusion",
    "supplier-structure-note",
    "supplier-structure-conclusion",
    "supplier-checklist-note",
    "supplier-checklist-conclusion",
    "supplier-info-note",
    "supplier-info-conclusion",
    "interview-summary-note",
    "interview-summary-conclusion",
    "interview-detail-note",
    "interview-detail-conclusion",
    "impairment-analysis",
    "loss-analysis",
    "price-analysis",
    "capacity-analysis",
    "consumption-analysis",
    "related-party-conclusion",
    "supplier-analysis",
}

_PROMPTS: dict[str, str] = {
    "contract-cost-note": (
        "请根据底稿数据起草F2-55合同履约成本构成明细表的审计说明，"
        "说明项目构成、期初至期末变动、合同台账及履约进度核对、"
        "资本化条件（直接相关且预期可收回）、审计调整和与1410科目勾稽情况。"
        "对异常项目说明核查过程，语气客观，适合直接填入底稿。"
    ),
    "contract-cost-conclusion": (
        "请生成F2-55合同履约成本构成明细表的正式审计结论，采用A/B/C结论口径："
        "A为合同履约成本构成、计量和资本化条件未见异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合期末账面、审计调整、期末审定金额及异常项目判断，只输出结论正文。"
    ),
    "contract-check-note": (
        "请根据底稿数据起草F2-56合同履约成本检查表的审计说明，"
        "概述样本选取方法和覆盖率，说明记账凭证与合同协议、到货验收、"
        "物流运输及费用分配资料的逐笔勾稽情况，并说明异常样本的处理。"
        "语气客观、适合直接填入底稿。"
    ),
    "contract-check-conclusion": (
        "请生成F2-56合同履约成本检查表的正式审计结论，采用A/B/C结论口径："
        "A为抽样检查及支持性单据勾稽未见异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或证据不足，无法确认。"
        "结合测试金额、不正确金额、差错率、覆盖率及异常样本数判断，只输出结论正文。"
    ),
    "contract-check-issue": (
        "请根据F2-56检查表中该笔样本的记账凭证、合同/协议、到货验收、"
        "物流运输、费用分配等单据核对结果，起草该样本的异常说明："
        "指出缺失或不一致的单据及金额差异，说明对履约成本确认的影响和建议处理方式。"
        "若各项勾稽一致则说明未见异常。只输出说明正文，简洁适合填入底稿单元格。"
    ),
    "contract-impairment-note": (
        "请根据底稿数据起草F2-57合同履约成本减值准备测算表的审计说明，"
        "说明减值测试方法（账面价值与预期剩余对价扣除估计将发生成本后净额比较）、"
        "各项目是否发生减值、测算计提/转回金额与企业账面减值准备的差异及原因，"
        "并评价管理层计提的充分性。语气客观、适合直接填入底稿。"
    ),
    "contract-impairment-conclusion": (
        "请生成F2-57合同履约成本减值准备测算表的正式审计结论，采用A/B/C结论口径："
        "A为减值准备计提充分、测算与账面无重大差异，未见异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合账面价值、测算计提/转回、差异合计及差异项目数判断，只输出结论正文。"
    ),
    "loss-contract-note": (
        "请根据底稿数据起草F2-58亏损合同预计损失测算表的审计说明，"
        "说明亏损合同识别标准、完工进度及预计总收入和预计总成本的数据来源与复核过程，"
        "分析合同预计损失、已在损益反映亏损、本期应确认金额与企业账面已确认金额的差异，"
        "并说明异常项目及建议处理。语气客观、适合直接填入底稿。"
    ),
    "loss-contract-conclusion": (
        "请生成F2-58亏损合同预计损失测算表的正式审计结论，采用A/B/C结论口径："
        "A为亏损合同识别完整、预计损失测算及账面确认未见重大异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合预计损失合计、本期应确认、账面已确认、差异合计及差异项目数判断，只输出结论正文。"
    ),
    "purchase-price-variance-note": (
        "请根据F2-61原材料采购价格分析表的底稿数据，起草「原材料××月采购单价变动较大的原因」审计说明："
        "指出月度采购单价偏离本期平均单价超过阈值的材料及月份，"
        "结合采购量、供应商变化、大宗商品行情等说明波动原因及核查过程"
        "（如查阅采购合同、询价记录、供应商访谈）。语气客观、适合直接填入底稿。"
    ),
    "purchase-price-market-note": (
        "请根据F2-61原材料采购价格分析表的底稿数据，起草「原材料采购单价与市场价格差异较大原因」审计说明："
        "对采购均价与市场均价差异率超过阈值的材料，说明差异方向与幅度、"
        "管理层解释及审计核查情况，并关注《问题解答第18号》所述第三方配合舞弊风险"
        "（虚增/虚减采购单价、套取资金、第三方代为承担成本费用）。语气客观、适合直接填入底稿。"
    ),
    "purchase-price-conclusion": (
        "请生成F2-61原材料采购价格分析表的正式审计结论，采用A/B/C结论口径："
        "A为采购价格逐月波动及与市场价格对比未见异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合本期合计采购金额、单价异常材料数、市场价差异材料数判断，只输出结论正文。"
    ),
    "unit-price-note": (
        "请根据F2-62原材料单价分析表的三层交叉分析数据起草审计说明："
        "分别说明同一供应商采购不同物料、同一原材料向不同供应商采购、"
        "同类原材料不同规格跨年度采购单价的比较结果；"
        "列明单价偏离超过阈值的组别、材料/供应商/规格及核查过程，"
        "并结合《问题解答第18号》评价第三方配合舞弊风险。语气客观，适合直接填入底稿。"
    ),
    "unit-price-conclusion": (
        "请生成F2-62原材料单价分析表的正式审计结论，采用A/B/C结论口径："
        "A为供应商、材料和规格三个维度的采购单价比较未见重大异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合比较组数、异常项数及采购金额判断，只输出结论正文。"
    ),
    "capacity-utilization-note": (
        "请根据F2-63存货产量与产能、能耗分析表的底稿数据，起草「实际产量与产能异常的原因，"
        "与同行业产能利用率差异的原因」审计说明：指出产能利用率超过100%或明显偏低的存货，"
        "结合排产安排、技改扩产、订单情况及同行业可比公司产能利用率水平说明差异原因及核查过程"
        "（如查阅生产报表、现场察看产线、访谈生产负责人）。语气客观、适合直接填入底稿。"
    ),
    "storage-capacity-note": (
        "请根据F2-63存货产量与产能、能耗分析表的底稿数据，起草「期末实际库存与库存容量比较异常的原因」"
        "审计说明：对容量利用率超过100%或明显异常的仓库，说明实际库存量、库存容量的核实过程"
        "（监盘、丈量库容、外部仓储合同核对），并结合已有订单及期后销售情况分析期末库存的合理性，"
        "关注虚构存货或体外存货风险。语气客观、适合直接填入底稿。"
    ),
    "energy-consumption-note": (
        "请根据F2-63存货产量与产能、能耗分析表的底稿数据，起草「能耗异常原因」审计说明："
        "对本期与上期能源采购单价变动超过阈值的能源项目、单位能耗变动率超过阈值的产品，"
        "结合水电费单、能源合同、工艺变化及产量波动说明原因，"
        "并说明以标准单耗倒推产量与账面产量的比较结果，评价产量数据的真实性。"
        "语气客观、适合直接填入底稿。"
    ),
    "capacity-energy-conclusion": (
        "请生成F2-63存货产量与产能、能耗分析表的正式审计结论，采用A/B/C结论口径："
        "A为产能利用、库存容量与能耗匹配性分析未见重大异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。"
        "结合产能利用率异常项数、库存容量异常仓库数及能耗异常项数判断，只输出结论正文。"
    ),
    "production-cost-structure-note": (
        "请根据F2-64主要产品生产成本及单耗分析表，起草生产成本构成审计说明。"
        "比较本年与上年各月主要原材料、其他材料、直接人工及制造费用金额和占比，"
        "指出波动较大的月份及项目，结合产量、采购价格、薪酬和产能利用率说明原因及核查程序。"
        "语气客观，适合直接填入底稿。"
    ),
    "production-cost-flow-note": (
        "请根据F2-64成本衔接数据起草审计说明，说明期初在产品、本期材料/人工/制造费用投入、"
        "期末在产品、完工产量和单位成本之间的勾稽关系，识别异常结转、跨期或成本归集不完整风险，"
        "并概述执行的凭证抽查、成本分配复核及截止测试。"
    ),
    "product-unit-cost-note": (
        "请根据F2-64产品单位成本月度数据及同行业比较起草审计说明。"
        "分析单位材料、单位人工、单位制造费用及单位总成本的月度和年度变化，"
        "说明与同行业公司的差异方向、幅度、管理层解释及审计核查结果。"
    ),
    "material-consumption-note": (
        "请根据F2-64主要原材料耗用数据起草审计说明。"
        "比较本年与上年各月产量、主要原材料投入量、单位产量耗用及单位成本，"
        "指出超过阈值的单耗或成本波动，并结合BOM、领料单、产量记录和盘点资料评价投入产出合理性。"
    ),
    "unit-consumption-conclusion": (
        "请生成F2-64主要产品生产成本及单耗分析表正式审计结论，采用A/B/C结论口径："
        "A为成本构成、成本衔接、单位成本及原材料单耗未见重大异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大未调整差异或审计范围受限，无法确认。只输出结论正文。"
    ),
    "related-inquiry-note": (
        "请根据F2-65关联方采购定价公允性询价数据起草审计说明。"
        "说明独立询价单位的选择依据、询价函发出及回收情况，按关联方和产品列明价差率超过10%的月份，"
        "结合规格质量、采购量、运输及付款条款、市场行情说明差异原因和核查程序，"
        "评价是否存在利益输送、虚增成本或采购价格操纵。语气客观，适合直接填入底稿。"
    ),
    "related-inquiry-conclusion": (
        "请生成F2-65关联方采购定价公允性核查（询价函）的正式审计结论，采用A/B/C结论口径："
        "A为询价程序充分、关联方采购价格与独立可比报价无重大异常，定价公允；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在重大不公允定价、未调整差异或询价范围受限，无法确认。"
        "结合有效询价组数、异常月份数及逐月合理性判断，只输出结论正文。"
    ),
    "related-market-note": (
        "请根据F2-66关联方采购定价公允性核查（市场价）数据起草审计说明。"
        "说明市场（挂牌）价格的取数来源与可靠性，按关联方和产品列明采购均价落在市场价区间外的月份，"
        "结合价格波动趋势、采购时点、规格质量及合同条款说明差异原因和核查过程，"
        "评价关联方采购定价是否公允。语气客观，适合直接填入底稿。"
    ),
    "related-market-conclusion": (
        "请生成F2-66关联方采购定价公允性核查（市场价）的正式审计结论，采用A/B/C结论口径："
        "A为关联方采购均价均处于同期市场价区间内，定价公允未见异常；"
        "B为除已识别调整或说明事项外，其余未见异常；"
        "C为存在采购价格显著偏离市场区间且无法合理解释，或市场价取数受限，无法确认。"
        "结合比较组数、区间外月份数及偏离幅度判断，只输出结论正文。"
    ),
    "undisclosed-party-note": (
        "请根据F2-67识别未披露关联方人员身份交叉核对结果起草审计说明。"
        "概述被审计单位主要股东、董监高、亲属及员工名单，重要供应商法人、合同签订人和关键人员名单，"
        "说明姓名交叉比对、身份证号码、家庭地址及任职关系等进一步核验程序；"
        "列示出现重名或匹配人员、身份关系、涉及采购额、管理层解释及获取的支持性证据。"
        "不得将仅姓名相同直接表述为已确认关联方，语气客观、可直接填入审计底稿。"
    ),
    "undisclosed-party-conclusion": (
        "请生成F2-67识别未披露关联方的正式审计结论。"
        "根据核对人数、匹配人数、身份核验结果及涉及采购额，判断是否发现重要供应商与公司存在未披露关联关系；"
        "如仅为同名且身份证、地址或任职信息不一致，应明确说明已排除；"
        "如存在尚未充分核实的匹配或审计范围受限，应说明保留事项及后续程序。只输出结论正文。"
    ),
    "supplier-structure-note": (
        "请根据F2-68重要供应商结构分析数据起草审计说明。"
        "比较本年与上年主要供应商采购金额、排名、集中度和主要采购产品，"
        "分析新增、退出及采购额大幅波动供应商，信用期、支付方式、运输方式等交易条件变化；"
        "重点说明关联方、采购额与供应商规模不匹配、采购产品与经营范围不匹配、数量乘单价与采购额不一致等事项，"
        "结合管理层解释和获取的证据评价交易合理性及持续性。语气客观，可直接填入底稿。"
    ),
    "supplier-structure-conclusion": (
        "请生成F2-68重要供应商结构分析的正式审计结论。"
        "结合本年与上年前五大、前十大集中度，供应商新增退出和交易条件变化，"
        "以及关联方、规模匹配、经营范围匹配和金额复核异常，综合判断供应商结构及采购交易是否合理、稳定，"
        "是否存在未披露关联方或利益输送风险。只输出结论正文。"
    ),
    "supplier-checklist-note": (
        "请根据F2-69供应商核查清单起草审计说明。"
        "说明供应商选取标准和覆盖范围，按供应商概述工商资料、互联网信息、访谈、函证和实地走访等程序执行情况；"
        "比较反向核查与函证资料的期末余额和本期采购额，列示差异超过1%、程序未执行或证据索引不完整的事项，"
        "并说明管理层解释、替代程序及处理结果。语气客观、可直接填入审计底稿。"
    ),
    "supplier-checklist-conclusion": (
        "请生成F2-69供应商核查清单的正式审计结论。"
        "结合核查供应商数量、多渠道程序完成情况、反向核查与函证金额差异、走访结果及证据完整性，"
        "评价主要供应商采购交易真实性、商业实质和是否存在未披露关联方风险；"
        "如程序未完成、差异未解释或审计范围受限，应明确保留事项及后续程序。只输出结论正文。"
    ),
    "supplier-info-note": (
        "请根据F2-70供应商信息核查表起草审计说明。"
        "说明供应商信息取数渠道（企查查、国家企业信用信息公示系统、征信报告等），"
        "按供应商概述统一社会信用代码、注册及办公地址、网站与IP、企业邮箱、成立时间、注册资本、"
        "人员规模、股东及持股比例、关键管理人员和经办人员、实际控制人等核查结果；"
        "重点列示与被审计单位及其关联方、董监高、员工存在地址、网站IP、邮箱、人员重合的情形，"
        "以及注册资本与交易规模不匹配、经营范围与采购产品不匹配、成立时间临近合作起始、"
        "经营状态异常或列入失信名单的供应商，并说明管理层解释和进一步程序。"
        "语气客观、可直接填入审计底稿。"
    ),
    "supplier-info-conclusion": (
        "请生成F2-70供应商信息核查表的正式审计结论。"
        "结合供应商工商及网络信息核查、股权与关键人员穿透比对结果、"
        "关联方及同为客户情形、经营状态和失信记录，"
        "参考《审计准则问题解答第18号》第三方配合舞弊特征，"
        "综合评价主要供应商是否真实存在、具备商业实质，"
        "是否存在未披露关联方或配合舞弊风险；如信息核查不完整或存在未消除疑虑，应明确保留事项。"
        "只输出结论正文。"
    ),
    "interview-summary-note": (
        "请根据F2-71供应商访谈记录汇总表起草审计说明。"
        "说明走访范围与选取标准（前十名供应商、新增供应商、存在疑虑的供应商、主要基建工程建造商等），"
        "按供应商概述访谈时间、原因、方式、受访人及身份、参与审计人员和行程安排；"
        "重点说明现场核对结果：走访地址与注册地址是否一致、是否现场获取盖章函证、"
        "合同执行核对情况、交易金额和往来余额与账面（含F2-68采购额）核对是否一致；"
        "列示地址不一致、金额不符、未现场函证或结论存疑的供应商，说明原因、管理层解释及进一步程序，"
        "并注明访谈明细索引（F2-72）与行程票据、现场照片等证据附件的留存情况。"
        "语气客观、可直接填入审计底稿。"
    ),
    "interview-summary-conclusion": (
        "请生成F2-71供应商访谈记录汇总表的正式审计结论。"
        "结合访谈覆盖的供应商数量及占采购额比例、地址核对、交易金额与往来余额核对、"
        "现场函证获取情况及访谈中发现的异常事项，"
        "综合评价主要供应商采购交易的真实性与商业合理性，是否存在关联关系及配合舞弊迹象；"
        "如访谈范围受限、核对不一致未消除或证据不完整，应明确保留事项及后续程序。只输出结论正文。"
    ),
    "interview-detail-note": (
        "请根据F2-72供应商访谈记录起草审计说明。"
        "按访谈份数概述访谈对象、时间地点、参与人员及十一项提纲的回答要点；"
        "重点说明自产与外协、其他资金往来、关联关系核查、专项关注事项（如大额预付款）的发现；"
        "列示证据附件留存情况（工商资料、函证回函、银行流水等）及真实性声明签署情况，"
        "并说明异常事项的进一步程序。语气客观、可直接填入审计底稿。"
    ),
    "interview-detail-conclusion": (
        "请生成F2-72供应商访谈记录的正式审计结论。"
        "结合各份访谈问卷完成度、关键回答与账面及F2-68/70信息的一致性、"
        "外协生产、其他资金往来、关联关系迹象及真实性声明签署情况，"
        "综合评价主要供应商访谈所支持的采购交易真实性结论；"
        "如问卷未完成、声明未签署或存在未消除疑虑，应明确保留事项。只输出结论正文。"
    ),
    "impairment-analysis": "请生成F2-57合同履约成本减值准备测算的审计评价。",
    "loss-analysis": "请生成F2-58亏损合同预计损失测算的审计评价。",
    "price-analysis": "请生成F2-61/62原材料采购价格与单价分析的审计结论。",
    "capacity-analysis": "请生成F2-63产量与产能/能耗分析的审计结论。",
    "consumption-analysis": "请生成F2-64单耗分析的审计结论，关注异常差异率。",
    "related-party-conclusion": "请生成F2-65~67关联方定价与未披露关联方核查结论。",
    "supplier-analysis": "请生成F2-68~72供应商结构、核查与访谈的审计结论。",
}

_SYSTEM = """你是一位资深注册会计师，协助编制F2存货特殊组（合同履约+IPO舞弊应对）底稿。
输出中文审计专业用语，直接输出正文，简洁适合底稿。"""


@router.post("/api/workpapers/{wp_id}/f2-spe/ai-generate")
async def f2_spe_ai_generate(
    wp_id: str,
    body: F2SpeAiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2SpeAiResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    ctx = await _load_ctx(wp_id, db)
    parts = [f"## 任务\n{_PROMPTS.get(body.section, '请生成审计文本。')}\n"]
    if ctx.get("client_name"):
        parts.append(f"客户：{ctx['client_name']}  年度：{ctx.get('audit_year', '')}\n")
    if body.relatedContext:
        lines = "\n".join(f"- {k}: {v}" for k, v in body.relatedContext.items() if v is not None)
        if lines:
            parts.append(f"## 底稿数据\n{lines}\n")
    if body.existingContent:
        parts.append(f"## 已有内容\n{body.existingContent[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    result = await chat_completion(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n".join(parts)}],
        temperature=0.3,
        max_tokens=2000,
    )
    if isinstance(result, str) and result.startswith("["):
        return F2SpeAiResponse(content="", sources=[])
    return F2SpeAiResponse(content=result, sources=[])


async def _load_ctx(wp_id: str, db: AsyncSession) -> dict:
    try:
        r = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = r.fetchone()
        if row:
            return {"client_name": row.client_name or "", "audit_year": str(row.audit_year or "")}
    except Exception as e:
        logger.warning("F2 spe AI context: %s", e)
    return {}
