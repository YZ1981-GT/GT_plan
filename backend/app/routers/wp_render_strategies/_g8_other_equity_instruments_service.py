"""G8 其他权益工具投资 — 业务逻辑（公式验证 / 借贷平衡）."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FormulaError:
    row_key: str
    field: str
    message: str
    variance: float


class G8OtherEquityInstrumentsService:
    """G8 服务端校验与取数辅助。"""

    TOLERANCE = 0.01

    @staticmethod
    def parse_num(v: object) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return n if n == n else 0.0
        try:
            n = float(str(v).strip())
            return n if n == n else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def calc_adjusted(unadjusted: float, adjustment: float) -> float:
        return float(unadjusted or 0) + float(adjustment or 0)

    @staticmethod
    def calc_debit_balance(opening: float, debit: float, credit: float) -> float:
        return float(opening or 0) + float(debit or 0) - float(credit or 0)

    @staticmethod
    def calc_ending_balance(
        opening_adjusted: float,
        increase: float,
        decrease: float,
        fv_change: float,
    ) -> float:
        return (
            float(opening_adjusted or 0)
            + float(increase or 0)
            - float(decrease or 0)
            + float(fv_change or 0)
        )

    @staticmethod
    def calc_fair_value_amount(qty: float, unit_price: float) -> float:
        return round(float(qty or 0) * float(unit_price or 0), 2)

    @staticmethod
    def calc_fair_value_diff(audited: float, unadjusted: float) -> float:
        return round(float(audited or 0) - float(unadjusted or 0), 2)

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < 0.01

    def validate_adjudication_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("row_key") or row.get("id") or "")
            opening_unadj = self.parse_num(row.get("openingUnadjusted"))
            opening_adj = self.parse_num(row.get("openingAdjustment"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_unadj, opening_adj)
            opening_var = opening_computed - opening_audited
            if opening_audited and abs(opening_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "openingAdjusted", "期初审定数公式不平衡", opening_var)
                )

            closing_unadj = self.parse_num(row.get("closingUnadjusted"))
            closing_adj = self.parse_num(row.get("closingAdjustment"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_computed = self.calc_adjusted(closing_unadj, closing_adj)
            closing_var = closing_computed - closing_audited
            if closing_audited and abs(closing_var) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingAdjusted", "期末审定数公式不平衡", closing_var)
                )
        return errors

    def validate_detail_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("investeeName") or row.get("id") or "")
            opening_bal = self.parse_num(row.get("openingBalance"))
            opening_adj = self.parse_num(row.get("openingAdjustment"))
            opening_audited = self.parse_num(row.get("openingAdjusted"))
            opening_computed = self.calc_adjusted(opening_bal, opening_adj)
            if opening_audited and abs(opening_computed - opening_audited) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "openingAdjusted",
                        "明细表期初审定数公式不平衡",
                        opening_computed - opening_audited,
                    )
                )

            closing_bal = self.parse_num(row.get("closingBalance"))
            closing_computed = self.calc_ending_balance(
                opening_computed,
                self.parse_num(row.get("increaseAmount")),
                self.parse_num(row.get("decreaseAmount")),
                self.parse_num(row.get("fvChangeAmount")),
            )
            if closing_bal and abs(closing_computed - closing_bal) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "closingBalance",
                        "明细表期末余额公式不平衡",
                        closing_computed - closing_bal,
                    )
                )

            closing_adj = self.parse_num(row.get("closingAdjustment"))
            closing_audited = self.parse_num(row.get("closingAdjusted"))
            closing_adj_computed = self.calc_adjusted(closing_bal, closing_adj)
            if closing_audited and abs(closing_adj_computed - closing_audited) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "closingAdjusted",
                        "明细表期末审定数公式不平衡",
                        closing_adj_computed - closing_audited,
                    )
                )

            # 持股数×每股公允 ↔ 公允价值合计
            share_count = self.parse_num(row.get("shareCount") or row.get("sharesHeld"))
            price = self.parse_num(row.get("pricePerShare"))
            fv_total = self.parse_num(row.get("fairValueTotal"))
            if share_count and price:
                product = self.calc_fair_value_amount(share_count, price)
                if fv_total and abs(product - fv_total) > self.TOLERANCE:
                    errors.append(
                        FormulaError(
                            key,
                            "fairValueTotal",
                            "公允价值合计应等于持股数×每股公允价值",
                            product - fv_total,
                        )
                    )

            # FVOCI：本期 FV 变动与本期 OCI 通常对等（两者均有值时）
            fv_change = self.parse_num(row.get("fvChangeAmount"))
            oci_current = self.parse_num(row.get("ociCurrentChange"))
            if (
                abs(fv_change) > self.TOLERANCE
                and abs(oci_current) > self.TOLERANCE
                and abs(fv_change - oci_current) > self.TOLERANCE
            ):
                errors.append(
                    FormulaError(
                        key,
                        "ociCurrentChange",
                        "本期OCI变动与FV变动不一致（FVOCI通常应对等）",
                        oci_current - fv_change,
                    )
                )

            # OCI 滚动：期末累计 = 期初累计 + 本期 − 转入
            oci_opening = self.parse_num(row.get("ociOpeningCumulative"))
            oci_to_re = self.parse_num(row.get("ociToRetainedEarnings"))
            oci_ending = self.parse_num(row.get("ociCumulativeChange"))
            oci_expected = oci_opening + oci_current - oci_to_re
            has_oci = (
                abs(oci_opening) > self.TOLERANCE
                or abs(oci_current) > self.TOLERANCE
                or abs(oci_to_re) > self.TOLERANCE
                or abs(oci_ending) > self.TOLERANCE
            )
            if has_oci and abs(oci_ending - oci_expected) > self.TOLERANCE:
                errors.append(
                    FormulaError(
                        key,
                        "ociCumulativeChange",
                        "OCI期末累计≠期初累计+本期OCI−转入留存",
                        oci_ending - oci_expected,
                    )
                )

            # 有期末审定须填指定原因
            if abs(closing_audited or closing_adj_computed) > self.TOLERANCE and not str(
                row.get("designationReason") or ""
            ).strip():
                errors.append(
                    FormulaError(key, "designationReason", "有期末审定余额但未填指定OCI原因", 0.0)
                )

            # Level3 须填估值方法
            level = str(row.get("fairValueLevel") or "").strip()
            if level == "Level3" and not str(row.get("valuationMethod") or "").strip():
                errors.append(
                    FormulaError(key, "valuationMethod", "Level3须填估值方法", 0.0)
                )

        return errors

    def validate_fair_value_rows(self, rows: list[dict]) -> list[FormulaError]:
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("rowKey") or row.get("investeeName") or row.get("id") or "")
            unadj_qty = self.parse_num(row.get("closingUnadjustedQty"))
            unadj_price = self.parse_num(row.get("closingUnadjustedPrice"))
            unadj_fv = self.parse_num(row.get("closingUnadjustedFV"))
            audited_qty = self.parse_num(row.get("closingAuditedQty"))
            audited_price = self.parse_num(row.get("closingAuditedPrice"))
            audited_fv = self.parse_num(row.get("closingAuditedFV"))
            diff = self.parse_num(row.get("fairValueDiff"))

            unadj_computed = self.calc_fair_value_amount(unadj_qty, unadj_price)
            if unadj_fv and abs(unadj_computed - unadj_fv) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingUnadjustedFV", "未审公允价值应等于数量×单价", unadj_computed - unadj_fv)
                )

            audited_computed = self.calc_fair_value_amount(audited_qty, audited_price)
            if audited_fv and abs(audited_computed - audited_fv) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "closingAuditedFV", "审定公允价值应等于数量×单价", audited_computed - audited_fv)
                )

            computed_diff = self.calc_fair_value_diff(audited_fv or audited_computed, unadj_fv or unadj_computed)
            if diff and abs(computed_diff - diff) > self.TOLERANCE:
                errors.append(
                    FormulaError(key, "fairValueDiff", "公允价值差异公式不平衡", computed_diff - diff)
                )

            if abs(computed_diff) > self.TOLERANCE and not str(row.get("diffReason") or "").strip():
                errors.append(
                    FormulaError(key, "diffReason", "存在公允价值差异时须填写差异原因", computed_diff)
                )

            level = str(row.get("fairValueLevel") or "")
            if level == "Level3":
                for field, label in (
                    ("valuationTechnique", "估值技术"),
                    ("unobservableInputDesc", "不可观察输入值描述"),
                    ("unobservableInputValue", "不可观察输入值"),
                    ("valuationDocIndex", "估值文件索引号"),
                ):
                    if not str(row.get(field) or "").strip():
                        errors.append(FormulaError(key, field, f"Level3 必填：{label}", 0.0))
            elif level == "Level2" and not str(row.get("valuationSource") or "").strip():
                errors.append(FormulaError(key, "valuationSource", "Level2 必填：公允价值来源机构", 0.0))
        return errors

    def validate_adjustment_balance(
        self,
        debits: list[float],
        credits: list[float],
    ) -> list[FormulaError]:
        if self.is_debit_credit_balanced(debits, credits):
            return []
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return [
            FormulaError("adjustment", "balance", "调整分录借贷不平衡", d - c),
        ]

    def validate_designation_rows(
        self,
        rows: list[dict],
        detail_rows: list[dict] | None = None,
        fair_value_rows: list[dict] | None = None,
    ) -> list[FormulaError]:
        """G8-5 指定适当性：矩阵完整性 + 与 G8-2/G8-4 勾稽。"""
        errors: list[FormulaError] = []
        yn_fields = (
            ("tradingNearTermSale", "近期出售或回购"),
            ("tradingPortfolioShortTerm", "组合短期获利"),
            ("tradingDerivative", "衍生/交易性"),
            ("equityInstrument", "权益工具定义"),
            ("designatedFvtoci", "不可撤销指定"),
            ("fvReliable", "FV可靠计量"),
        )
        listed: list[dict] = []
        for row in rows:
            name = str(row.get("investeeName") or "").strip()
            book = self.parse_num(row.get("closingBookValue"))
            if not name and not book:
                continue
            listed.append(row)
            key = name or str(row.get("rowId") or row.get("id") or "")
            for field, label in yn_fields:
                if not str(row.get(field) or "").strip():
                    errors.append(FormulaError(key, field, f"未勾选：{label}", 0.0))
            trading = any(
                str(row.get(f) or "").strip().lower() in ("yes", "是", "true", "1")
                for f in ("tradingNearTermSale", "tradingPortfolioShortTerm", "tradingDerivative")
            )
            equity_ok = all(
                str(row.get(f) or "").strip().lower() in ("yes", "是", "true", "1")
                for f in ("equityInstrument", "designatedFvtoci", "fvReliable")
            )
            if trading and equity_ok:
                errors.append(
                    FormulaError(key, "designation", "存在交易性特征但权益/指定均勾「是」，指定结论矛盾", 0.0)
                )

        if detail_rows:
            detail_names = {
                str(d.get("investeeName") or "").strip()
                for d in detail_rows
                if str(d.get("investeeName") or "").strip()
            }
            desig_names = {
                str(r.get("investeeName") or "").strip()
                for r in listed
                if str(r.get("investeeName") or "").strip()
            }
            for n in sorted(detail_names - desig_names):
                errors.append(FormulaError(n, "investeeName", "G8-2 有该被投资单位，G8-5 未列示", 0.0))
            for n in sorted(desig_names - detail_names):
                errors.append(FormulaError(n, "investeeName", "G8-5 有该被投资单位，G8-2 明细无对应行", 0.0))
            detail_total = sum(
                self.parse_num(d.get("closingAdjusted") or d.get("closingBalance") or d.get("closingBookValue"))
                for d in detail_rows
            )
            desig_total = sum(self.parse_num(r.get("closingBookValue")) for r in listed)
            diff = round(desig_total - detail_total, 2)
            if abs(diff) > self.TOLERANCE:
                errors.append(
                    FormulaError("total", "closingBookValue", "G8-5 账面合计与 G8-2 不一致", diff)
                )

        if fair_value_rows:
            def _norm(n: str) -> str:
                return n.strip().lower()

            def _extract_level(row: dict) -> str:
                direct = str(row.get("fairValueLevel") or "").strip()
                if direct:
                    return direct
                other = str(row.get("other") or "")
                for token in ("Level1", "Level2", "Level3", "L1", "L2", "L3"):
                    if token.lower() in other.lower():
                        return token if token.startswith("Level") else f"Level{token[1:]}"
                return ""

            fv_map = {
                _norm(str(r.get("investeeName") or "")): str(r.get("fairValueLevel") or "").strip()
                for r in fair_value_rows
                if str(r.get("investeeName") or "").strip()
            }
            for row in listed:
                name = str(row.get("investeeName") or "").strip()
                if not name:
                    continue
                key = _norm(name)
                fv_level = fv_map.get(key, "")
                desig_level = _extract_level(row)
                fv_reliable = str(row.get("fvReliable") or "").strip().lower() in ("yes", "是", "true", "1")
                if not fv_level:
                    errors.append(FormulaError(name, "fairValueLevel", "G8-5 有该被投资单位，G8-4 无对应行", 0.0))
                    continue
                if desig_level and fv_level and desig_level != fv_level:
                    errors.append(
                        FormulaError(
                            name,
                            "fairValueLevel",
                            f"G8-4 为 {fv_level}，G8-5 标注 {desig_level}",
                            0.0,
                        )
                    )
                elif fv_level == "Level3" and fv_reliable and desig_level != "Level3":
                    errors.append(
                        FormulaError(
                            name,
                            "fairValueLevel",
                            "G8-4 为 Level3 且 G8-5 已勾 FV 可靠，但未标注 Level3",
                            0.0,
                        )
                    )
            desig_keys = {_norm(str(r.get("investeeName") or "")) for r in listed if str(r.get("investeeName") or "").strip()}
            for r in fair_value_rows:
                name = str(r.get("investeeName") or "").strip()
                if name and _norm(name) not in desig_keys:
                    errors.append(FormulaError(name, "investeeName", "G8-4 有该被投资单位，G8-5 未列示", 0.0))
        return errors
