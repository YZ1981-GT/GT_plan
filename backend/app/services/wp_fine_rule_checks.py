"""底稿精细化规则引擎 — 审计检查执行引擎

从 wp_fine_rule_engine 抽出的审计检查逻辑（_run_audit_checks + 各 _check_*）。
依赖单向：wp_fine_rule_engine → wp_fine_rule_checks → wp_fine_rule_util。
"""

from app.services.wp_fine_rule_util import _safe_num


# ═══════════════════════════════════════════
# 审计检查执行引擎
# ═══════════════════════════════════════════

def _run_audit_checks(rule: dict, sheets: dict, summary: dict) -> list[dict]:
    """执行精细化规则中定义的审计检查

    根据 check.type 分派到不同的校验逻辑：
    - balance: 余额核对（审定表合计 vs 试算表/报表）
    - cross_ref: 交叉引用（审定表行 vs 明细表合计）
    - movement: 变动校验（期初+变动=期末）
    - completeness: 完整性（账户数核对）
    - reconciliation: 余额调节（账面±未达=对账单±未达）
    - confirmation: 函证核对
    - analysis: 分析程序
    - cutoff: 截止测试
    """
    results = []
    wp_code = rule.get("wp_code", "")
    summary_code = f"{wp_code}-1"
    summary_sheet = sheets.get(summary_code, {})
    summary_rows = summary_sheet.get("rows", {})

    for check in rule.get("audit_checks", []):
        check_code = check.get("id", check.get("code", ""))
        check_type = check.get("type", "")
        severity = check.get("severity", "info")
        description = check.get("description", "")

        passed = None
        actual = None
        expected = None
        diff = None
        message = ""

        try:
            if check_type == "balance":
                passed, actual, expected, diff, message = _check_balance(
                    check_code, summary_rows, sheets, rule
                )
            elif check_type == "cross_ref":
                passed, actual, expected, diff, message = _check_cross_ref(
                    check_code, summary_rows, sheets, rule
                )
            elif check_type == "movement":
                passed, message = _check_movement(summary_rows)
                actual = expected = diff = None
            elif check_type == "formula":
                passed, actual, expected, diff, message = _check_formula(
                    check_code, summary_rows, sheets, rule
                )
            elif check_type == "completeness":
                passed, message = _check_completeness(check_code, sheets, rule)
            elif check_type == "aging":
                passed, actual, expected, diff, message = _check_aging(
                    check_code, summary_rows, sheets, rule
                )
            elif check_type == "confirmation":
                passed, message = _check_confirmation(check_code, sheets, rule)
            elif check_type in ("check", "analysis", "cutoff"):
                # 这些是定性检查，需要人工判断或LLM辅助
                # 从对应Sheet检查是否有数据填写
                passed, message = _check_sheet_filled(check_code, sheets, rule)
            elif check_type == "reconciliation":
                passed, message = _check_reconciliation(check_code, sheets, rule)
            else:
                message = f"未知检查类型: {check_type}"
        except Exception as e:
            message = f"检查执行异常: {e}"

        results.append({
            "code": check_code,
            "type": check_type,
            "severity": severity,
            "description": description,
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "diff": diff,
            "message": message,
        })

    return results


def _check_balance(check_code: str, summary_rows: dict, sheets: dict, rule: dict):
    """余额核对检查"""
    total = summary_rows.get("total", {})
    total_closing = total.get("closing_audited") or total.get("closing_balance")
    tb_row = summary_rows.get("tb_balance", {})
    tb_closing = tb_row.get("closing_audited") or tb_row.get("closing_balance")

    if "CHK-01" in check_code:
        # 审定表合计 vs 试算平衡表数
        if total_closing is not None and tb_closing is not None:
            diff = abs(total_closing - tb_closing)
            passed = diff < 0.01
            return passed, total_closing, tb_closing, round(diff, 2), \
                "通过" if passed else f"差异 {diff:.2f}"
        return None, total_closing, tb_closing, None, "数据不完整，无法校验"

    if "CHK-02" in check_code:
        # 审定表合计 vs 报表（需要外部数据，标记待验证）
        if total_closing is not None:
            return None, total_closing, None, None, "需要报表数据验证（REPORT('BS-002','期末')）"
        return None, None, None, None, "审定表合计为空"

    return None, None, None, None, "未匹配的余额检查"


def _check_cross_ref(check_code: str, summary_rows: dict, sheets: dict, rule: dict):
    """交叉引用检查"""
    wp_code = rule.get("wp_code", "")

    if "CHK-03" in check_code:
        # 库存现金审定数 vs 现金明细表合计
        cash_row = summary_rows.get("cash", {})
        cash_audited = cash_row.get("closing_audited") or cash_row.get("closing_balance")
        detail_sheet = sheets.get(f"{wp_code}-2", {})
        detail_rows = detail_sheet.get("detail_rows", [])
        if detail_rows:
            # 合计明细表的审定数列
            detail_total = sum(
                _safe_num(r.get("closing_audited") or r.get("closing_rmb")) or 0
                for r in detail_rows
            )
            if cash_audited is not None:
                diff = abs(cash_audited - detail_total)
                passed = diff < 0.01
                return passed, cash_audited, detail_total, round(diff, 2), \
                    "通过" if passed else f"差异 {diff:.2f}"
        return None, cash_audited, None, None, "现金明细表无数据"

    if "CHK-04" in check_code:
        # 银行存款审定数 vs 银行明细表合计
        bank_row = summary_rows.get("bank_deposit", {})
        bank_audited = bank_row.get("closing_audited") or bank_row.get("closing_balance")
        # 银行明细可能在 E1-3-rmb 或 E1-3
        for detail_code in [f"{wp_code}-3-rmb", f"{wp_code}-3"]:
            detail_sheet = sheets.get(detail_code, {})
            detail_rows = detail_sheet.get("detail_rows", [])
            if detail_rows:
                detail_total = sum(
                    _safe_num(r.get("closing_audited") or r.get("closing_balance")) or 0
                    for r in detail_rows
                )
                if bank_audited is not None:
                    diff = abs(bank_audited - detail_total)
                    passed = diff < 0.01
                    return passed, bank_audited, detail_total, round(diff, 2), \
                        "通过" if passed else f"差异 {diff:.2f}"
        return None, bank_audited, None, None, "银行明细表无数据"

    return None, None, None, None, "未匹配的交叉引用检查"


def _check_movement(summary_rows: dict):
    """变动校验：各行期初+变动=期末"""
    issues = []
    for key, row in summary_rows.items():
        if row.get("is_total") or key in ("tb_balance", "diff", "overseas"):
            continue
        opening = row.get("opening_audited")
        closing = row.get("closing_audited") or row.get("closing_balance")
        change = row.get("change_amount")
        if opening is not None and closing is not None and change is not None:
            expected = opening + change
            if abs(expected - closing) > 0.01:
                issues.append(f"{row.get('label', key)}: 期初{opening}+变动{change}={expected} ≠ 期末{closing}")

    if not issues:
        return True, "各行变动校验通过"
    return False, f"{len(issues)}行变动不一致: " + "; ".join(issues[:3])


def _check_formula(check_code: str, summary_rows: dict, sheets: dict, rule: dict):
    """公式校验：净值 = 原值 - 坏账准备（逐行）"""
    wp_code = rule.get("wp_code", "")
    summary_code = f"{wp_code}-1"
    sheet = sheets.get(summary_code, {})
    rows = sheet.get("rows", {})

    # 查找三段小计行
    gross_key = None
    bad_debt_key = None
    net_key = None
    for key, row in rows.items():
        label = (row.get("label") or "").lower()
        if row.get("is_total"):
            if "原值" in label or "gross" in key:
                gross_key = key
            elif "坏账" in label or "bad_debt" in key:
                bad_debt_key = key
            elif "净值" in label or "net" in key or "合计" in label:
                net_key = key

    if not (gross_key and bad_debt_key and net_key):
        return None, None, None, None, "未找到原值/坏账/净值小计行"

    gross = rows[gross_key].get("closing_audited") or rows[gross_key].get("closing_balance") or 0
    bad_debt = rows[bad_debt_key].get("closing_audited") or rows[bad_debt_key].get("closing_balance") or 0
    net = rows[net_key].get("closing_audited") or rows[net_key].get("closing_balance") or 0

    expected_net = gross - bad_debt
    diff = abs(net - expected_net)
    passed = diff < 0.01
    return passed, net, expected_net, round(diff, 2), \
        "通过" if passed else f"净值{net} ≠ 原值{gross}-坏账{bad_debt}={expected_net}"


def _check_completeness(check_code: str, sheets: dict, rule: dict):
    """完整性检查：检查关键Sheet是否有数据"""
    wp_code = rule.get("wp_code", "")

    # 检查明细表是否有数据行
    for code_suffix in ["-2", "-3"]:
        detail_code = f"{wp_code}{code_suffix}"
        detail_sheet = sheets.get(detail_code, {})
        detail_rows = detail_sheet.get("detail_rows", [])
        if detail_rows and len(detail_rows) > 0:
            return True, f"明细表有 {len(detail_rows)} 条数据"

    # 检查是否找到了Sheet但无数据
    found_sheets = sum(1 for s in sheets.values() if s.get("found"))
    total_sheets = len(sheets)
    if found_sheets == 0:
        return None, "未找到任何Sheet数据"
    return None, f"已找到 {found_sheets}/{total_sheets} 个Sheet，明细表暂无数据"


def _check_aging(check_code: str, summary_rows: dict, sheets: dict, rule: dict):
    """账龄相关检查"""
    # CHK-12: 账龄分段合计 = 原值合计
    if "CHK-12" in check_code:
        # 需要从明细表的账龄列汇总，当前精细化提取未细化到账龄列
        return None, None, None, None, "需要明细表账龄列数据验证"

    # CHK-13: 计提比例与政策一致
    if "CHK-13" in check_code:
        return None, None, None, None, "需要与会计政策比对验证"

    # CHK-14: 迁徙率合理性
    if "CHK-14" in check_code:
        return None, None, None, None, "需要上年账龄数据计算迁徙率"

    return None, None, None, None, "未匹配的账龄检查"


def _check_confirmation(check_code: str, sheets: dict, rule: dict):
    """函证检查：函证结果汇总表是否有数据"""
    wp_code = rule.get("wp_code", "")

    # 查找函证结果汇总Sheet
    for code, sheet in sheets.items():
        if "D0-1" in code or "E0-1" in code or "函证结果" in code:
            if sheet.get("found") and sheet.get("detail_rows"):
                count = len(sheet["detail_rows"])
                return True, f"函证结果汇总有 {count} 条记录"
            elif sheet.get("found"):
                return None, "函证结果汇总Sheet已找到但暂无数据"

    return None, "未找到函证结果汇总Sheet"


def _check_sheet_filled(check_code: str, sheets: dict, rule: dict):
    """定性检查：检查对应Sheet是否已填写（有数据行）"""
    # 从check_code推断对应的Sheet
    # 如 D1-CHK-08 → 检查D1-8（贴现/背书）
    # 如 D2-CHK-11 → 检查D2-10（ECL测试）
    wp_code = rule.get("wp_code", "")

    # 遍历所有已找到的Sheet，检查是否有数据
    filled_count = 0
    total_found = 0
    for code, sheet in sheets.items():
        if not sheet.get("found"):
            continue
        total_found += 1
        has_data = bool(
            sheet.get("detail_rows") or
            sheet.get("adjustments") or
            (sheet.get("rows") and any(
                v for k, v in sheet["rows"].items()
                if not k.endswith("_title") and v.get("closing_audited") or v.get("closing_balance")
            ))
        )
        if has_data:
            filled_count += 1

    if total_found == 0:
        return None, "未找到相关Sheet"
    rate = round(filled_count / total_found * 100)
    return True if rate > 50 else None, f"{filled_count}/{total_found} 个Sheet已填写（{rate}%）"


def _check_reconciliation(check_code: str, sheets: dict, rule: dict):
    """余额调节检查"""
    wp_code = rule.get("wp_code", "")

    # 查找余额调节表Sheet
    for code, sheet in sheets.items():
        if "调节" in code or "reconciliation" in sheet.get("type", ""):
            if sheet.get("found"):
                return None, "余额调节表已找到，需人工确认调节项"

    return None, "未找到余额调节表"
