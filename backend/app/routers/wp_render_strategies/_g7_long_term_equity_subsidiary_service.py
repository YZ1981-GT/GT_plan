"""G7 长期股权投资(子公司组) — 业务逻辑服务.

核心职责：
1. 控制判断数据保存 (G7-7)
2. 初始/后续/处置计量数据保存 (G7-8~G7-12)
3. 公式验证 helpers（同控成本/非同控成本/商誉/成本法收益/期末账面/处置损益/借贷平衡）

科目属性：
- 科目代码：1511 长期股权投资（子公司）
- 方向：借方（资产类）
- 计量方法：成本法（子公司不调整账面，仅股利+减值）

公式引擎对齐前端 useG7SubFormulaEngine.ts 的 8 个纯函数：
1. calcSameControlCost(netAssets, ratio) = netAssets × ratio
2. calcNotSameControlCost(price, fees) = price（fees仅兼容旧调用并费用化）
3. calcGoodwill(cost, share) = cost - share
4. calcCostMethodIncome(dividend, ratio) = dividend × ratio
5. calcSubsequentBalance(opening, addition, impairment) = opening + addition - impairment
6. calcDisposalGain(price, bookValue, dividend, oci) = price - bookValue - dividend + oci
7. isDebitCreditBalanced(debits, credits): |sum-sum| < 0.01
8. parseNum(v) → 安全数值转换

Pattern follows _g7_long_term_equity_main_service.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 公式验证容差
_TOLERANCE = 0.01

# 有效的 sheet 编码
_VALID_SHEET_CODES = {"G7-8", "G7-9", "G7-10", "G7-11", "G7-12"}


@dataclass
class FormulaError:
    """公式验证错误."""

    row_key: str
    field: str
    message: str
    variance: float


class G7SubsidiaryService:
    """G7 长期股权投资(子公司组) 业务逻辑服务.

    Methods:
        save_control_judgment: 保存G7-7控制判断数据
        save_measurement: 保存G7-8/G7-9/G7-10/G7-11/G7-12数据
        validate_formulas: 后端公式校验（对齐前端 useG7SubFormulaEngine）
    """

    TOLERANCE = _TOLERANCE

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ─── 纯函数：parseNum ─────────────────────────────────────────────────────

    @staticmethod
    def parse_num(v: object) -> float:
        """安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0."""
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return n if n == n else 0.0  # noqa: PLR0124 — NaN check
        try:
            n = float(str(v).strip())
            return n if n == n else 0.0  # noqa: PLR0124
        except (TypeError, ValueError):
            return 0.0

    # ─── 纯函数：7大公式 ──────────────────────────────────────────────────────

    @staticmethod
    def calc_same_control_cost(net_assets: float, ratio: float) -> float:
        """同一控制下企业合并初始投资成本 = 被合并方账面净资产 × 持股比例.

        CAS20: 同控合并以账面价值计量。
        """
        return float(net_assets or 0) * float(ratio or 0)

    @staticmethod
    def calc_not_same_control_cost(price: float, fees: float = 0) -> float:
        """非同一控制下企业合并初始投资成本 = 合并对价公允价值.

        CAS20: 审计、法律、评估等中介费用计入当期损益，不构成合并成本。
        fees仅为兼容旧调用保留。
        """
        _ = fees
        return float(price or 0)

    @staticmethod
    def calc_goodwill(cost: float, share: float) -> float:
        """商誉 = 初始投资成本 - 享有被购买方可辨认净资产公允价值份额.

        正值 = 商誉（资产）；负值 = 廉价购买利得（营业外收入）。
        CAS20: 合并成本 > 被购买方净资产FV份额 → 商誉。
        """
        return float(cost or 0) - float(share or 0)

    @staticmethod
    def calc_cost_method_income(dividend: float, ratio: float) -> float:
        """成本法投资收益 = 被投资方宣告股利 × 持股比例.

        CAS2: 子公司成本法核算，投资收益仅限于宣告的现金股利。
        """
        return float(dividend or 0) * float(ratio or 0)

    @staticmethod
    def calc_subsequent_balance(
        opening: float, addition: float, impairment: float
    ) -> float:
        """成本法期末账面 = 期初 + 追加投资 - 减值.

        CAS2: 成本法下不调整权益法因素，账面变动仅来自追加和减值。
        """
        return float(opening or 0) + float(addition or 0) - float(impairment or 0)

    @staticmethod
    def calc_disposal_gain(
        price: float, book_value: float, dividend: float, oci: float
    ) -> float:
        """个别报表处置损益 = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI.

        CAS33/CAS2: 处置时释放原计入OCI中可转损益部分。
        """
        return (
            float(price or 0)
            - float(book_value or 0)
            - float(dividend or 0)
            + float(oci or 0)
        )

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        """借贷平衡: |SUM(debits) - SUM(credits)| < 0.01."""
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < _TOLERANCE

    def prepare_g7_9_rows(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[FormulaError]]:
        """重算G7-9公式列并执行不可绕过的业务校验。

        上传值中的公式结果不可信，统一由服务端覆盖。返回新列表，不修改调用方对象。
        """
        prepared: list[dict[str, Any]] = []
        errors: list[FormulaError] = []
        transaction_numbers: dict[str, set[int]] = {}

        for index, source in enumerate(rows, start=1):
            row = dict(source)
            section = str(row.get("section") or "merger")
            row_key = str(row.get("id") or index)

            if section == "merger":
                consideration = round(sum(
                    self.parse_num(row.get(key))
                    for key in (
                        "cashConsideration", "nonCashAssetFV", "debtFV",
                        "equitySecuritiesFV", "contingentConsiderationFV",
                    )
                ), 2)
                prior_fv = self.parse_num(row.get("priorHoldingFV"))
                book_value = self.parse_num(row.get("considerationBookValue"))
                net_assets = self.parse_num(row.get("acquireeIdentifiableNetAssetsFV"))
                ratio = self.parse_num(row.get("ownershipRatio"))
                share = round(net_assets * ratio, 2)
                initial_cost = round(consideration + prior_fv, 2)
                goodwill = round(initial_cost - share, 2)
                row.update({
                    "totalConsiderationFV": consideration,
                    "initialInvestmentCost": initial_cost,
                    "considerationGainLoss": round(consideration - book_value, 2),
                    "shareOfFV": share,
                    "nonControllingInterestShare": round(
                        net_assets * max(0.0, 1.0 - ratio), 2
                    ),
                    "goodwill": goodwill,
                })
                if not 0 <= ratio <= 1:
                    errors.append(FormulaError(
                        row_key, "ownershipRatio", "持股比例应在0至1之间", ratio
                    ))
                if goodwill < -_TOLERANCE:
                    if row.get("bargainPurchaseReviewed") != "是":
                        errors.append(FormulaError(
                            row_key, "bargainPurchaseReviewed",
                            "廉价购买利得须完成计量复核后方可确认", goodwill,
                        ))
                    if not str(row.get("bargainPurchaseReviewNote") or "").strip():
                        errors.append(FormulaError(
                            row_key, "bargainPurchaseReviewNote",
                            "廉价购买利得须填写复核过程", goodwill,
                        ))

            elif section == "step":
                company_name = str(row.get("companyName") or "").strip()
                company_id = str(row.get("companyId") or "").strip()
                if not company_id:
                    identity = company_name or f"row-{index}"
                    company_id = (
                        f"step-company-{uuid5(NAMESPACE_URL, f'g7-9:{identity}')}"
                    )
                row["companyId"] = company_id
                row["companyName"] = company_name
                row["adjustmentScope"] = "transaction"

                ratio = self.parse_num(row.get("purchaseRatio"))
                net_assets = self.parse_num(
                    row.get("netAssetsFVAtTxn")
                    if row.get("netAssetsFVAtTxn") not in (None, "")
                    else row.get("netAssetsBookValueAtTxn")
                )
                consideration = self.parse_num(row.get("considerationFV"))
                share = round(ratio * net_assets, 2)
                row["netAssetsFVAtTxn"] = net_assets
                row["shareOfFVAtTxn"] = share
                row["goodwillAtTxn"] = round(consideration - share, 2)
                if row.get("priorEquityMethodAdjustments") in (None, ""):
                    row["priorEquityMethodAdjustments"] = row.get("priorOCIReclassify")

                if not company_name:
                    errors.append(FormulaError(
                        row_key, "companyName", "分步合并公司名称不能为空", 0
                    ))
                if not 0 < ratio <= 1:
                    errors.append(FormulaError(
                        row_key, "purchaseRatio", "每笔购买比例应大于0且不超过1", ratio
                    ))
                transaction_no = int(self.parse_num(row.get("transactionNo")) or index)
                row["transactionNo"] = transaction_no
                seen = transaction_numbers.setdefault(company_id, set())
                if transaction_no in seen:
                    errors.append(FormulaError(
                        row_key, "transactionNo", "同一公司交易次别不得重复", 0
                    ))
                seen.add(transaction_no)
                if row.get("isPackageDeal") == "是":
                    errors.append(FormulaError(
                        row_key, "isPackageDeal",
                        "一揽子交易不得使用分步合并区段", 0,
                    ))

            elif section == "reverse":
                constitutes_business = str(row.get("constitutesBusiness") or "")
                if constitutes_business not in {"是", "否"}:
                    errors.append(FormulaError(
                        row_key, "constitutesBusiness",
                        "反向购买须判断会计被购买方是否构成业务", 0,
                    ))
                elif constitutes_business == "否":
                    errors.append(FormulaError(
                        row_key, "constitutesBusiness",
                        "不构成业务应按资产购置处理，不得在本区段确认商誉", 0,
                    ))
                if not str(row.get("businessDeterminationBasis") or "").strip():
                    errors.append(FormulaError(
                        row_key, "businessDeterminationBasis",
                        "反向购买须填写构成业务判断依据", 0,
                    ))
            else:
                errors.append(FormulaError(
                    row_key, "section", f"未知G7-9区段: {section}", 0
                ))

            prepared.append(row)
        return prepared, errors

    # ─── 控制判断保存 (G7-7) ──────────────────────────────────────────────────

    async def save_control_judgment(
        self, wp_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        """保存G7-7控制判断数据到 checklist_responses.

        与前端 DATA_KEY 对齐：item_id = G7-7-control-judgment-data
        data 结构（与 G7TabControlJudgment.getData 一致）:
        {
            "sections": [...],
            "overallConclusion": str,
            "decision": {...},
            "additionalDecisions": [...]  # 可选，多被投资单位结论
        }

        Returns: {"success": bool, "errors": list, "item_id": str}
        """
        assert self.db is not None, "db session required for async operations"

        item_id = "G7-7-control-judgment-data"
        # 兼容旧调用方把综合结论放在 conclusion / control_result
        if isinstance(data, dict):
            normalized = dict(data)
            if "overallConclusion" not in normalized and normalized.get("conclusion"):
                normalized["overallConclusion"] = normalized.pop("conclusion")
            if "decision" not in normalized and normalized.get("control_result"):
                normalized.setdefault(
                    "decision",
                    {
                        "investeeName": "",
                        "relationshipType": normalized.pop("control_result"),
                        "combinationType": "",
                        "combinationBasis": "",
                        "acquisitionDate": "",
                        "acquisitionDateBasis": "",
                        "priorConclusion": "",
                        "conclusionChangeReason": "",
                    },
                )
            data = normalized
        conclusion_val = json.dumps(data, ensure_ascii=False) if data else ""

        try:
            await self.db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (wp_id, item_id, conclusion, remark)
                    VALUES (:wp_id, :item_id, :conclusion, '')
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET conclusion = :conclusion
                """),
                {
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "conclusion": conclusion_val,
                },
            )
            await self.db.flush()
        except Exception as e:  # noqa: BLE001
            logger.error("G7 subsidiary service: 控制判断保存失败: %s", e)
            return {"success": False, "errors": [{"field": "save", "message": str(e)}]}

        return {"success": True, "errors": [], "item_id": item_id}

    # ─── 计量数据保存 (G7-8~G7-12) ───────────────────────────────────────────

    async def save_measurement(
        self, wp_id: UUID, sheet_code: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """保存G7-8/G7-9/G7-10/G7-11/G7-12数据到 checklist_responses.

        data 结构:
        {
            "rows": [...],           # 各行数据
            "conclusion": str,       # 审计结论
        }

        Returns: {"success": bool, "errors": list, "item_id": str}
        """
        assert self.db is not None, "db session required for async operations"

        if sheet_code not in _VALID_SHEET_CODES:
            return {
                "success": False,
                "errors": [{"field": "sheet_code", "message": f"无效sheet编码: {sheet_code}"}],
            }

        # G7-9公式字段由服务端覆盖；硬错误不得持久化。
        if sheet_code == "G7-9":
            prepared_rows, errors = self.prepare_g7_9_rows(
                list(data.get("rows") or [])
            )
            data = {**data, "rows": prepared_rows}
            if errors:
                return {
                    "success": False,
                    "errors": [
                        {
                            "row_key": error.row_key,
                            "field": error.field,
                            "message": error.message,
                            "variance": error.variance,
                        }
                        for error in errors
                    ],
                }
        else:
            errors = self.validate_formulas(data)

        item_id = f"G7-{sheet_code.split('-')[1]}-rows"
        conclusion_val = json.dumps(data, ensure_ascii=False) if data else ""

        try:
            await self.db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (wp_id, item_id, conclusion, remark)
                    VALUES (:wp_id, :item_id, :conclusion, '')
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET conclusion = :conclusion
                """),
                {
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "conclusion": conclusion_val,
                },
            )
            await self.db.flush()
        except Exception as e:  # noqa: BLE001
            logger.error("G7 subsidiary service: %s数据保存失败: %s", sheet_code, e)
            return {"success": False, "errors": [{"field": "save", "message": str(e)}]}

        error_dicts = [
            {"row_key": e.row_key, "field": e.field, "message": e.message, "variance": e.variance}
            for e in errors
        ]
        return {"success": True, "errors": error_dicts, "item_id": item_id}

    # ─── 公式验证 ─────────────────────────────────────────────────────────────

    def validate_formulas(self, data: dict[str, Any]) -> list[FormulaError]:
        """后端公式校验（对齐前端 useG7SubFormulaEngine 7纯函数）.

        验证项：
        1. calcSameControlCost(netAssets, ratio) = netAssets × ratio
        2. calcNotSameControlCost(price, fees) = price（fees费用化）
        3. calcGoodwill(cost, share) = cost - share
        4. calcCostMethodIncome(dividend, ratio) = dividend × ratio
        5. calcSubsequentBalance(opening, addition, impairment) = opening + addition - impairment
        6. calcDisposalGain(price, bookValue, dividend, oci) = price - bookValue - dividend + oci
        7. isDebitCreditBalanced(debits, credits): |sum-sum| < 0.01

        返回 FormulaError 列表
        """
        errors: list[FormulaError] = []

        # 1. 同控初始成本验证 (G7-8)
        if "same_control_checks" in data:
            for check in data["same_control_checks"]:
                net_assets = self.parse_num(check.get("net_assets"))
                ratio = self.parse_num(check.get("ratio"))
                cost = self.parse_num(check.get("cost"))
                expected = self.calc_same_control_cost(net_assets, ratio)
                if abs(expected - cost) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="same_control_cost",
                        message=f"同控成本公式不平: 净资产({net_assets})×比例({ratio})={expected}, 实际={cost}",
                        variance=expected - cost,
                    ))

        # 2. 非同控初始成本验证 (G7-9)
        if "not_same_control_checks" in data:
            for check in data["not_same_control_checks"]:
                price = self.parse_num(check.get("price"))
                fees = self.parse_num(check.get("fees"))
                cost = self.parse_num(check.get("cost"))
                expected = self.calc_not_same_control_cost(price, fees)
                if abs(expected - cost) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="not_same_control_cost",
                        message=f"非同控成本公式不平: 对价FV({price})={expected}, 实际={cost}；费用({fees})应费用化",
                        variance=expected - cost,
                    ))

        # 3. 商誉验证 (G7-9)
        if "goodwill_checks" in data:
            for check in data["goodwill_checks"]:
                cost = self.parse_num(check.get("cost"))
                share = self.parse_num(check.get("share"))
                goodwill = self.parse_num(check.get("goodwill"))
                expected = self.calc_goodwill(cost, share)
                if abs(expected - goodwill) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="goodwill",
                        message=f"商誉公式不平: 成本({cost})-份额({share})={expected}, 实际={goodwill}",
                        variance=expected - goodwill,
                    ))

        # 4. 成本法投资收益验证 (G7-10)
        if "cost_method_income_checks" in data:
            for check in data["cost_method_income_checks"]:
                dividend = self.parse_num(check.get("dividend"))
                ratio = self.parse_num(check.get("ratio"))
                income = self.parse_num(check.get("income"))
                expected = self.calc_cost_method_income(dividend, ratio)
                if abs(expected - income) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="cost_method_income",
                        message=f"投资收益公式不平: 股利({dividend})×比例({ratio})={expected}, 实际={income}",
                        variance=expected - income,
                    ))

        # 5. 期末账面余额验证 (G7-10)
        if "subsequent_balance_checks" in data:
            for check in data["subsequent_balance_checks"]:
                opening = self.parse_num(check.get("opening"))
                addition = self.parse_num(check.get("addition"))
                impairment = self.parse_num(check.get("impairment"))
                balance = self.parse_num(check.get("balance"))
                expected = self.calc_subsequent_balance(opening, addition, impairment)
                if abs(expected - balance) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="subsequent_balance",
                        message=f"期末账面公式不平: 期初({opening})+追加({addition})-减值({impairment})={expected}, 实际={balance}",
                        variance=expected - balance,
                    ))

        # 6. 处置损益验证 (G7-11/G7-12)
        if "disposal_gain_checks" in data:
            for check in data["disposal_gain_checks"]:
                price = self.parse_num(check.get("price"))
                book_value = self.parse_num(check.get("book_value"))
                dividend = self.parse_num(check.get("dividend"))
                oci = self.parse_num(check.get("oci"))
                gain = self.parse_num(check.get("gain"))
                expected = self.calc_disposal_gain(price, book_value, dividend, oci)
                if abs(expected - gain) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="disposal_gain",
                        message=f"处置损益公式不平: 对价({price})-账面({book_value})-股利({dividend})+OCI({oci})={expected}, 实际={gain}",
                        variance=expected - gain,
                    ))

        # 7. 借贷平衡验证 (G7-18凭证检查)
        if "debit_credit_balance" in data:
            check = data["debit_credit_balance"]
            debits = [self.parse_num(x) for x in (check.get("debits") or [])]
            credits = [self.parse_num(x) for x in (check.get("credits") or [])]
            if not self.is_debit_credit_balanced(debits, credits):
                total_d = sum(debits)
                total_c = sum(credits)
                errors.append(FormulaError(
                    row_key="voucher",
                    field="debit_credit_balance",
                    message=f"借贷不平衡: 借方合计({total_d}) ≠ 贷方合计({total_c}), 差额={total_d - total_c}",
                    variance=total_d - total_c,
                ))

        return errors
