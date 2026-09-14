"""OCR 规则引擎 — 本地脚本层（零 LLM 成本，毫秒级）

移植自 Fa_piao_Gt 的 OCRPostProcessor + InvoiceClassifier + 各 Parser 精华。
作为 LLM 调用前的前置规则层：
- 字符纠错（O→0, l→1 等常见 OCR 混淆）
- 关键词规则分类（12 类单据，含前置检查防误判）
- 正则提取确定性字段（发票号、金额、日期、税号）
- 高置信度直出，低置信度交给 LLM 增强

三层管线：本地脚本（毫秒） → LLM 增强（仅低置信度） → 人工确认（兜底）
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1a: OCR 后处理（字符纠错）
# ═══════════════════════════════════════════════════════════════════════════════

class OCRPostProcessor:
    """OCR 文本后处理器 — 纠正常见字符混淆"""

    # 预编译正则
    _TAX_ID_RE = re.compile(r'[A-Za-z0-9]{15,20}')
    _AMOUNT_RE = re.compile(r'[¥￥]?\s*([0-9OolISBZ,]+\.[0-9OolISBZ]{2})')
    _INVOICE_NO_RE = re.compile(r'发票号码[:：\s]*([0-9OolI]{8,30})')
    _DATE_RE = re.compile(r'(\d{4})\s*[年/.—-]\s*(\d{1,2})\s*[月/.—-]\s*(\d{1,2})')

    # 数字上下文中的字符替换规则
    _NUM_CHAR_MAP = str.maketrans('OoIlZSB', '0011258')

    @classmethod
    def process(cls, text: str) -> str:
        """对 OCR 原始文本做后处理纠错"""
        if not text:
            return text
        result = text
        result = cls._fix_digital_invoice_splits(result)
        result = cls._fix_tax_ids(result)
        result = cls._fix_amounts(result)
        result = cls._fix_invoice_numbers(result)
        return result

    @classmethod
    def _fix_digital_invoice_splits(cls, text: str) -> str:
        """修复数电票 OCR 拆行问题

        数电票常见 OCR 问题：
        1. "合计" 被拆成 "合\n计" 或 "合 计"
        2. "价税合计" 拆成 "价税合\n计" 或 "价税\n合计"
        3. 金额前的 ¥ 和数字被拆行："¥\n28500.00"
        4. "购买方信息" 拆成 "购买方\n信息"
        5. "销售方信息" 拆成 "销售方\n信息"
        """
        # 合并 "合\n计" → "合计"
        result = re.sub(r'合\s*\n\s*计', '合计', text)
        # 合并 "价税\n合计" → "价税合计"
        result = re.sub(r'价\s*税\s*\n?\s*合\s*\n?\s*计', '价税合计', result)
        # 合并 ¥ 与后续金额之间的换行
        result = re.sub(r'([¥￥])\s*\n\s*(\d)', r'\1\2', result)
        # 合并 "购买方\n信息" → "购买方信息"
        result = re.sub(r'(购买方|销售方)\s*\n\s*(信息)', r'\1\2', result)
        # 合并 "纳税人\n识别号" → "纳税人识别号"
        result = re.sub(r'纳税人\s*\n?\s*识别号', '纳税人识别号', result)
        # 合并 "统一社会\n信用代码" → "统一社会信用代码"
        result = re.sub(r'统一社会\s*\n?\s*信用代码', '统一社会信用代码', result)
        return result

    @classmethod
    def _fix_tax_ids(cls, text: str) -> str:
        """纠正税号中的字符混淆"""
        def _replace(m: re.Match) -> str:
            raw = m.group(0)
            fixed = raw.translate(cls._NUM_CHAR_MAP)
            # 税号格式：大写字母+数字，修正后保留大写
            return fixed.upper()
        return cls._TAX_ID_RE.sub(_replace, text)

    @classmethod
    def _fix_amounts(cls, text: str) -> str:
        """纠正金额中的字符混淆"""
        def _replace(m: re.Match) -> str:
            raw = m.group(1)
            fixed = raw.translate(cls._NUM_CHAR_MAP)
            prefix = m.group(0)[:m.group(0).index(raw)] if raw in m.group(0) else ''
            return prefix + fixed
        return cls._AMOUNT_RE.sub(_replace, text)

    @classmethod
    def _fix_invoice_numbers(cls, text: str) -> str:
        """纠正发票号码中的字符混淆"""
        def _replace(m: re.Match) -> str:
            raw = m.group(1)
            fixed = raw.translate(cls._NUM_CHAR_MAP)
            return f"发票号码：{fixed}"
        return cls._INVOICE_NO_RE.sub(_replace, text)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1b: 规则分类器（关键词匹配，毫秒级）
# ═══════════════════════════════════════════════════════════════════════════════

# 分类规则：关键词列表 + 优先级（数字越小越优先）
_CLASSIFY_RULES: dict[str, dict[str, Any]] = {
    "sales_invoice": {
        "keywords": ["增值税专用发票", "增值税普通发票", "增值税电子普通发票",
                     "增值税电子专用发票", "全电发票", "数电票", "电子发票"],
        "priority": 3,
        "require_any": ["购买方", "销售方", "价税合计", "税率"],
    },
    "purchase_invoice": {
        "keywords": ["进项税", "采购发票"],
        "priority": 3,
        "require_any": ["供应商", "进项税额"],
    },
    "bank_receipt": {
        "keywords": ["银行回单", "电子回单", "收款回单", "付款回单", "转账回单",
                     "银行收付款回单"],
        "priority": 1,
        "require_any": ["收款人", "付款人", "交易金额", "交易日期"],
    },
    "bank_statement": {
        "keywords": ["银行对账单", "银行流水", "交易明细"],
        "priority": 1,
        "require_any": ["期初余额", "期末余额", "对手户名"],
    },
    "train_ticket": {
        "keywords": ["火车票", "中国铁路", "车票", "铁路客票"],
        "priority": 0,
        "require_any": ["车次", "出发", "到达", "席别"],
    },
    "flight_itinerary": {
        "keywords": ["航空运输电子客票行程单", "行程单", "电子客票"],
        "priority": 0,
        "require_any": ["航班号", "舱位", "客票号码", "民航发展基金"],
    },
    "taxi_receipt": {
        "keywords": ["出租车发票", "出租汽车发票", "的士发票", "网约车"],
        "priority": 0,
        "require_any": ["上车", "下车", "里程", "等候"],
    },
    "voucher": {
        "keywords": ["记账凭证", "凭证号", "付款凭证", "收款凭证"],
        "priority": 2,
        "require_any": ["借方", "贷方", "摘要", "科目"],
    },
    "contract": {
        "keywords": ["合同", "协议书", "合作协议"],
        "priority": 2,
        "require_any": ["甲方", "乙方", "合同金额", "有效期"],
    },
    "tax_return": {
        "keywords": ["纳税申报表", "税务局", "应纳税额"],
        "priority": 2,
        "require_any": ["税款", "申报期", "税种"],
    },
    "bank_reconciliation": {
        "keywords": ["银行余额调节表", "余额调节"],
        "priority": 1,
        "require_any": ["银行余额", "账面余额", "未达账项"],
    },
    "accommodation_receipt": {
        "keywords": ["住宿费", "住宿服务", "酒店", "宾馆", "旅馆", "客房"],
        "priority": 0,
        "require_any": [],
    },
    "toll_invoice": {
        "keywords": ["过路费", "通行费", "入口站", "出口站"],
        "priority": 0,
        "require_any": [],
    },
    "catering_receipt": {
        "keywords": ["餐饮发票", "餐费", "餐饮服务"],
        "priority": 0,
        "require_any": [],
    },
    "fixed_amount_invoice": {
        "keywords": ["定额发票", "通用定额发票"],
        "priority": 1,
        "require_any": [],
    },
}

# VAT 结构关键词（用于防误判）
_VAT_STRUCTURE_KEYWORDS = ["项目名称", "规格型号", "税率/征收率", "税率", "税额"]


def classify_by_rules(text: str) -> dict[str, Any] | None:
    """规则分类器：关键词匹配 + 前置检查

    Returns:
        {"type": str, "confidence": float, "method": "rule"} 或 None（需 LLM 裁决）
    """
    if not text or len(text.strip()) < 20:
        return None

    # ─── 前置检查：航空行程单（含"电子发票"会误匹配 VAT） ───
    flight_kw = ["航班号", "行程单", "客票号码", "电子客票号码"]
    flight_specific = ["舱位等级", "民航发展基金", "燃油附加", "承运人", "旅客姓名"]
    flight_hit = sum(1 for kw in flight_kw if kw in text)
    flight_specific_hit = sum(1 for kw in flight_specific if kw in text)
    has_vat_structure = sum(1 for kw in _VAT_STRUCTURE_KEYWORDS if kw in text) >= 3
    if flight_hit >= 1 and flight_specific_hit >= 1 and not has_vat_structure:
        return {"type": "flight_itinerary", "confidence": 0.92, "method": "rule"}

    # ─── 前置检查：过路费（含"专用发票"会误匹配 VAT） ───
    if any(kw in text for kw in ["过路费", "通行费"]) and any(kw in text for kw in ["入口站", "出口站", "车型"]):
        return {"type": "toll_invoice", "confidence": 0.90, "method": "rule"}

    # ─── 通用关键词匹配 ───
    matches: list[tuple[str, float, int]] = []  # (type, confidence, priority)

    for doc_type, rule in _CLASSIFY_RULES.items():
        keywords = rule["keywords"]
        require_any = rule.get("require_any", [])
        priority = rule["priority"]

        # 主关键词命中数
        kw_hits = sum(1 for kw in keywords if kw in text)
        if kw_hits == 0:
            continue

        # require_any 辅助验证
        req_hits = sum(1 for kw in require_any if kw in text) if require_any else 1

        if require_any and req_hits == 0:
            # 主关键词命中但辅助验证全部失败，降低置信度
            confidence = 0.4
        else:
            # 关键词是 OR 关系（命中任一即可），辅助验证加分
            kw_score = min(1.0, kw_hits * 0.5)  # 命中 1 个=0.5，2 个=1.0
            req_score = (req_hits / max(len(require_any), 1)) if require_any else 0.5
            confidence = min(0.95, kw_score * 0.6 + req_score * 0.4)

        matches.append((doc_type, confidence, priority))

    if not matches:
        return None

    # 按置信度降序 + 优先级升序排序
    matches.sort(key=lambda x: (-x[1], x[2]))
    best_type, best_conf, _ = matches[0]

    # ─── 结构性校验：非 VAT 类型但有 VAT 表格结构 → 切到 VAT ───
    vat_types = {"sales_invoice", "purchase_invoice"}
    if best_type not in vat_types:
        vat_structure_count = sum(1 for sk in _VAT_STRUCTURE_KEYWORDS if sk in text)
        if vat_structure_count >= 3:
            # 有 VAT 表格结构，看是否有 VAT 候选
            for t, c, _ in matches:
                if t in vat_types:
                    best_type, best_conf = t, max(c, 0.80)
                    break

    # 置信度太低（< 0.6）交给 LLM
    if best_conf < 0.6:
        return None

    return {"type": best_type, "confidence": round(best_conf, 3), "method": "rule"}


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1c: 正则字段提取（确定性字段，零 LLM 成本）
# ═══════════════════════════════════════════════════════════════════════════════

# 通用字段正则（适用于大部分票据）
_COMMON_FIELD_PATTERNS: dict[str, list[re.Pattern]] = {
    "invoice_no": [
        re.compile(r'发票号码[:：\s]*(\d{8,30})'),
        re.compile(r'No[.:：]\s*(\d{8,20})'),
        re.compile(r'号码[:：\s]*(\d{8,20})'),
    ],
    "invoice_date": [
        re.compile(r'开票日期[:：\s]*(\d{4})\s*[年/.—-]\s*(\d{1,2})\s*[月/.—-]\s*(\d{1,2})'),
        re.compile(r'日期[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "amount": [
        # 不含税金额（排除"价税合计"）
        re.compile(r'(?<!价税)(?:合计金额|金额|不含税金额)[:：\s]*[¥￥]?\s*([\d,]+\.\d{2})'),
        re.compile(r'(?:小写)[:：\s]*[¥￥]?\s*([\d,]+\.\d{2})'),
    ],
    "tax_amount": [
        re.compile(r'(?:税额|合计税额)[:：\s]*[¥￥]?\s*([\d,]+\.\d{2})'),
    ],
    "total": [
        # 价税合计（含税总额）
        re.compile(r'(?:价税合计|合计|总金额|总计)[:：\s]*[¥￥]?\s*([\d,]+\.\d{2})'),
        re.compile(r'(?:价税合计).*?[¥￥]\s*([\d,]+\.\d{2})'),
        # 数电票"合计"行后紧跟 ¥ 金额
        re.compile(r'合\s*计\s*[¥￥]\s*([\d,]+\.\d{2})'),
    ],
    "buyer_name": [
        re.compile(r'(?:购买方|购方|买方|名\s*称)[:：\s]*([^\n]{2,40})'),
    ],
    "seller_name": [
        re.compile(r'(?:销售方|销方|卖方)[:：\s]*([^\n]{2,40})'),
    ],
    "tax_id": [
        re.compile(r'(?:纳税人识别号|税号|统一社会信用代码)[:：\s]*([A-Z0-9]{15,20})'),
    ],
}

# 火车票专用字段
_TRAIN_TICKET_PATTERNS: dict[str, list[re.Pattern]] = {
    "departure": [re.compile(r'(\S{2,8})站?\s*[→\-—到]\s*')],
    "arrival": [re.compile(r'[→\-—到]\s*(\S{2,8})站?')],
    "train_no": [re.compile(r'([GDZTKC]\d{1,5})')],
    "seat_class": [re.compile(r'(一等座|二等座|商务座|硬座|硬卧|软卧|无座)')],
    "amount": [re.compile(r'[¥￥]\s*([\d.]+)')],
}

# 银行回单专用字段
_BANK_RECEIPT_PATTERNS: dict[str, list[re.Pattern]] = {
    "transaction_date": [
        re.compile(r'(?:交易日期|日期)[:：\s]*(\d{4}[年/.—-]\d{1,2}[月/.—-]\d{1,2})'),
    ],
    "counterparty_name": [
        re.compile(r'(?:收款人|对方户名|收款方)[:：\s]*([^\n]{2,40})'),
        re.compile(r'(?:付款人|付款方)[:：\s]*([^\n]{2,40})'),
    ],
    "amount": [
        re.compile(r'(?:交易金额|金额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "summary": [
        re.compile(r'(?:摘要|用途|备注|附言)[:：\s]*([^\n]{1,50})'),
    ],
}

# 合同专用字段
_CONTRACT_PATTERNS: dict[str, list[re.Pattern]] = {
    "party_a": [re.compile(r'(?:甲方|买方|委托方)[:：（(]\s*([^\n)）]{2,40})')],
    "party_b": [re.compile(r'(?:乙方|卖方|受托方)[:：（(]\s*([^\n)）]{2,40})')],
    "contract_amount": [
        re.compile(r'(?:合同金额|合同总额|总金额)[:：\s]*[¥￥人民币]?\s*([\d,]+\.?\d*)'),
    ],
    "sign_date": [
        re.compile(r'(?:签订日期|签署日期|签约日)[:：\s]*(\d{4}[年/.—-]\d{1,2}[月/.—-]\d{1,2})'),
    ],
}

# 类型 → 专用正则映射
_TYPE_SPECIFIC_PATTERNS: dict[str, dict[str, list[re.Pattern]]] = {
    "train_ticket": _TRAIN_TICKET_PATTERNS,
    "bank_receipt": _BANK_RECEIPT_PATTERNS,
    "contract": _CONTRACT_PATTERNS,
}


# ─── 扩展：出入库单 ───
_OUTBOUND_ORDER_PATTERNS: dict[str, list[re.Pattern]] = {
    "outbound_date": [
        re.compile(r'(?:出库日期|日期|发货日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "product_name": [
        re.compile(r'(?:商品名称|品名|物料|货物名称)[:：\s]*([^\n]{2,40})'),
    ],
    "quantity": [
        re.compile(r'(?:数量|出库数量|发货数量)[:：\s]*([\d,.]+)'),
    ],
    "unit_price": [
        re.compile(r'(?:单价|含税单价)[:：\s]*[¥￥]?\s*([\d,.]+)'),
    ],
    "amount": [
        re.compile(r'(?:金额|合计金额|总金额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "customer": [
        re.compile(r'(?:客户|收货单位|收货方)[:：\s]*([^\n]{2,40})'),
    ],
    "warehouse": [
        re.compile(r'(?:仓库|发货仓库|出库仓)[:：\s]*([^\n]{2,20})'),
    ],
}

_INBOUND_ORDER_PATTERNS: dict[str, list[re.Pattern]] = {
    "inbound_date": [
        re.compile(r'(?:入库日期|到货日期|验收日期|日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "product_name": [
        re.compile(r'(?:商品名称|品名|物料|货物名称)[:：\s]*([^\n]{2,40})'),
    ],
    "quantity": [
        re.compile(r'(?:数量|入库数量|到货数量|验收数量)[:：\s]*([\d,.]+)'),
    ],
    "unit_price": [
        re.compile(r'(?:单价|含税单价)[:：\s]*[¥￥]?\s*([\d,.]+)'),
    ],
    "amount": [
        re.compile(r'(?:金额|合计金额|总金额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "supplier": [
        re.compile(r'(?:供应商|发货单位|供货方|送货方)[:：\s]*([^\n]{2,40})'),
    ],
    "warehouse": [
        re.compile(r'(?:仓库|入库仓|收货仓库)[:：\s]*([^\n]{2,20})'),
    ],
}

# ─── 扩展：物流签收单 ───
_LOGISTICS_ORDER_PATTERNS: dict[str, list[re.Pattern]] = {
    "tracking_no": [
        re.compile(r'(?:运单号|快递单号|物流单号|单号)[:：\s]*([A-Z0-9]{8,30})'),
    ],
    "ship_date": [
        re.compile(r'(?:寄件日期|发货日期|揽收日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "sign_date": [
        re.compile(r'(?:签收日期|签收时间|送达日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "sender": [
        re.compile(r'(?:寄件人|发货人|发件方)[:：\s]*([^\n]{2,30})'),
    ],
    "receiver": [
        re.compile(r'(?:收件人|收货人|签收人)[:：\s]*([^\n]{2,30})'),
    ],
    "weight": [
        re.compile(r'(?:重量|实际重量)[:：\s]*([\d.]+)\s*(?:kg|KG|公斤)?'),
    ],
}

# ─── 扩展：银行对账单/流水 ───
_BANK_STATEMENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "account_no": [
        re.compile(r'(?:账号|账户号|卡号)[:：\s]*(\d{10,25})'),
    ],
    "bank_name": [
        re.compile(r'(?:开户行|开户银行|银行名称)[:：\s]*([^\n]{2,30})'),
    ],
    "statement_date": [
        re.compile(r'(?:对账日期|打印日期|截止日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "opening_balance": [
        re.compile(r'(?:期初余额|上期余额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "closing_balance": [
        re.compile(r'(?:期末余额|本期余额|余额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
}

# ─── 扩展：纳税申报表 ───
_TAX_RETURN_PATTERNS: dict[str, list[re.Pattern]] = {
    "tax_type": [
        re.compile(r'(?:税种|税目)[:：\s]*([^\n]{2,20})'),
        re.compile(r'(增值税|企业所得税|个人所得税|城建税|印花税|房产税|土地使用税)'),
    ],
    "period": [
        re.compile(r'(?:所属期|申报期|纳税期限)[:：\s]*([^\n]{4,20})'),
        re.compile(r'(\d{4}年\d{1,2}月)'),
    ],
    "amount": [
        re.compile(r'(?:应纳税额|本期应补退税额|应缴税额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "filing_date": [
        re.compile(r'(?:申报日期|填报日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
}

# ─── 扩展：住宿发票 ───
_ACCOMMODATION_PATTERNS: dict[str, list[re.Pattern]] = {
    "hotel_name": [
        re.compile(r'(?:酒店|宾馆|旅馆|饭店)[:：\s]*([^\n]{2,30})'),
        # 也匹配发票头中出现的酒店名
        re.compile(r'([^\n]{2,20}(?:酒店|宾馆|旅馆|大酒店|商务酒店))'),
    ],
    "check_in": [
        re.compile(r'(?:入住日期|入住|check.?in)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "check_out": [
        re.compile(r'(?:离店日期|退房|check.?out)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "nights": [
        re.compile(r'(?:天数|住宿天数|晚数)[:：\s]*(\d{1,3})'),
    ],
    "amount": [
        re.compile(r'(?:金额|房费|合计|总额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
}

# ─── 扩展：餐饮票据 ───
_CATERING_PATTERNS: dict[str, list[re.Pattern]] = {
    "restaurant_name": [
        re.compile(r'([^\n]{2,20}(?:餐厅|饭店|食堂|餐饮|美食))'),
    ],
    "amount": [
        re.compile(r'(?:金额|合计|实收|消费金额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "invoice_date": [
        re.compile(r'(?:日期|开票日期|消费日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
}

# ─── 扩展：银行余额调节表 ───
_BANK_RECONCILIATION_PATTERNS: dict[str, list[re.Pattern]] = {
    "bank_name": [
        re.compile(r'(?:开户行|银行名称|开户银行)[:：\s]*([^\n]{2,30})'),
    ],
    "account_no": [
        re.compile(r'(?:账号|账户号码)[:：\s]*(\d{10,25})'),
    ],
    "statement_date": [
        re.compile(r'(?:调节日期|编制日期|截至日期)[:：\s]*(\d{4})[年/.—-](\d{1,2})[月/.—-](\d{1,2})'),
    ],
    "bank_balance": [
        re.compile(r'(?:银行对账单余额|银行余额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
    "book_balance": [
        re.compile(r'(?:企业账面余额|账面余额)[:：\s]*[¥￥]?\s*([\d,]+\.?\d*)'),
    ],
}

# 完整类型→专用正则映射（14 类全覆盖）
_TYPE_SPECIFIC_PATTERNS: dict[str, dict[str, list[re.Pattern]]] = {
    "sales_invoice": {},  # 通用字段已覆盖
    "purchase_invoice": {},
    "train_ticket": _TRAIN_TICKET_PATTERNS,
    "flight_itinerary": {},  # 机票格式特殊，主要靠 LLM
    "taxi_receipt": {},
    "bank_receipt": _BANK_RECEIPT_PATTERNS,
    "bank_statement": _BANK_STATEMENT_PATTERNS,
    "outbound_order": _OUTBOUND_ORDER_PATTERNS,
    "inbound_order": _INBOUND_ORDER_PATTERNS,
    "logistics_order": _LOGISTICS_ORDER_PATTERNS,
    "voucher": {},  # 凭证字段在通用正则中
    "tax_return": _TAX_RETURN_PATTERNS,
    "contract": _CONTRACT_PATTERNS,
    "bank_reconciliation": _BANK_RECONCILIATION_PATTERNS,
    "accommodation_receipt": _ACCOMMODATION_PATTERNS,
    "catering_receipt": _CATERING_PATTERNS,
    "toll_invoice": {},
    "fixed_amount_invoice": {},
}


def extract_fields_by_rules(text: str, doc_type: str) -> list[dict[str, Any]]:
    """正则提取确定性字段

    Returns:
        [{"field_name": str, "field_value": str|None, "confidence_score": float, "method": "rule"}]
        空列表表示规则层无法提取（需 LLM 补全）
    """
    if not text:
        return []

    results: list[dict[str, Any]] = []

    # 通用字段提取
    for field_name, patterns in _COMMON_FIELD_PATTERNS.items():
        value = _try_patterns(text, patterns, field_name)
        if value:
            results.append({
                "field_name": field_name,
                "field_value": value,
                "confidence_score": 0.95,
                "method": "rule",
            })

    # 类型专用字段
    specific = _TYPE_SPECIFIC_PATTERNS.get(doc_type, {})
    for field_name, patterns in specific.items():
        # 避免重复提取通用字段
        if any(r["field_name"] == field_name for r in results):
            continue
        value = _try_patterns(text, patterns, field_name)
        if value:
            results.append({
                "field_name": field_name,
                "field_value": value,
                "confidence_score": 0.90,
                "method": "rule",
            })

    # ─── 金额校验容差（amount + tax_amount ≈ total） ───
    results = _validate_amount_consistency(results)

    return results


# 金额校验容差（从 Fa_piao_Gt 移植）
_AMOUNT_TOLERANCE = 0.02  # 允许 2 分钱误差


def _validate_amount_consistency(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验金额+税额≈价税合计，不一致时降低置信度并添加警告"""
    amount_val = _get_field_as_float(fields, "amount")
    tax_val = _get_field_as_float(fields, "tax_amount")
    total_val = _get_field_as_float(fields, "total")

    # 如果没有提取到 total，尝试通过 amount 正则中的"价税合计"提取
    # （通用正则 amount 可能匹配到价税合计而非不含税金额）

    if amount_val is not None and tax_val is not None and total_val is not None:
        expected_total = amount_val + tax_val
        diff = abs(expected_total - total_val)
        if diff <= _AMOUNT_TOLERANCE:
            # 校验通过，标记置信度提升
            for f in fields:
                if f["field_name"] in ("amount", "tax_amount"):
                    f["confidence_score"] = min(0.99, f["confidence_score"] + 0.03)
        else:
            # 校验不通过，降低所有金额字段置信度 + 添加警告
            logger.warning(
                f"金额校验不通过: amount({amount_val}) + tax({tax_val}) = {expected_total} ≠ total({total_val}), diff={diff:.2f}"
            )
            for f in fields:
                if f["field_name"] in ("amount", "tax_amount", "total"):
                    f["confidence_score"] = max(0.5, f["confidence_score"] - 0.2)
                    f["_warning"] = f"金额校验差异 {diff:.2f} 元"

    elif amount_val is not None and tax_val is not None and total_val is None:
        # 有 amount + tax 但无 total → 自动推算 total
        computed_total = amount_val + tax_val
        fields.append({
            "field_name": "total",
            "field_value": f"{computed_total:.2f}",
            "confidence_score": 0.85,
            "method": "rule_computed",
        })

    return fields


def _get_field_as_float(fields: list[dict[str, Any]], name: str) -> float | None:
    """从字段列表中按名称取浮点数值"""
    for f in fields:
        if f["field_name"] == name and f["field_value"]:
            try:
                return float(f["field_value"].replace(",", ""))
            except (ValueError, TypeError):
                return None
    return None


def _try_patterns(text: str, patterns: list[re.Pattern], field_name: str) -> str | None:
    """尝试多个正则模式，返回第一个匹配结果"""
    for pat in patterns:
        m = pat.search(text)
        if m:
            groups = m.groups()
            if not groups:
                continue
            # 日期字段特殊处理：多组拼接为 YYYY-MM-DD
            if "date" in field_name and len(groups) == 3:
                y, mo, d = groups
                return f"{y}-{int(mo):02d}-{int(d):02d}"
            # 金额字段：去掉千分位逗号
            value = groups[0].strip()
            if "amount" in field_name:
                value = value.replace(",", "")
            return value if value else None
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 统一入口：规则层处理管线
# ═══════════════════════════════════════════════════════════════════════════════

def run_rule_pipeline(raw_text: str) -> dict[str, Any]:
    """运行完整规则管线：后处理 → 分类 → 字段提取

    Returns:
        {
            "corrected_text": str,       # 纠错后文本
            "classification": {...}|None, # 分类结果（None 表示需 LLM）
            "fields": [...],             # 已提取字段（可能为空，需 LLM 补全）
            "needs_llm": bool,           # 是否需要 LLM 增强
        }
    """
    # Step 1: 后处理纠错
    corrected = OCRPostProcessor.process(raw_text)

    # Step 2: 规则分类
    classification = classify_by_rules(corrected)

    # Step 3: 正则字段提取（仅分类成功时）
    fields: list[dict[str, Any]] = []
    if classification:
        fields = extract_fields_by_rules(corrected, classification["type"])

    # 判断是否需要 LLM 增强
    needs_llm = (
        classification is None  # 分类失败
        or classification["confidence"] < 0.8  # 分类置信度不够
        or len(fields) < 2  # 提取字段太少
    )

    return {
        "corrected_text": corrected,
        "classification": classification,
        "fields": fields,
        "needs_llm": needs_llm,
    }
