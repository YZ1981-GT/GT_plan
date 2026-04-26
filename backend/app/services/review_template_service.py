"""复核意见模板库 — 常见复核意见一键插入

按审计循环和科目分类，提供标准化的复核意见模板。
"""

# 致同标准复核意见模板
REVIEW_TEMPLATES: list[dict] = [
    # 通用
    {"category": "通用", "text": "请补充审计结论", "severity": "blocking"},
    {"category": "通用", "text": "请核实期末余额与总账一致性", "severity": "warning"},
    {"category": "通用", "text": "请补充审计程序执行记录", "severity": "warning"},
    {"category": "通用", "text": "请完善交叉索引标注", "severity": "info"},
    {"category": "通用", "text": "底稿编制日期需更新", "severity": "info"},
    # 货币资金
    {"category": "货币资金", "text": "请补充银行存款余额调节表", "severity": "blocking"},
    {"category": "货币资金", "text": "请核实受限货币资金披露完整性", "severity": "warning"},
    {"category": "货币资金", "text": "函证回函差异需说明原因", "severity": "warning"},
    {"category": "货币资金", "text": "大额定期存款需核实到期日", "severity": "info"},
    # 应收账款
    {"category": "应收账款", "text": "请补充账龄分析表", "severity": "blocking"},
    {"category": "应收账款", "text": "请核实坏账准备计提充分性", "severity": "warning"},
    {"category": "应收账款", "text": "请检查期后回款情况", "severity": "warning"},
    {"category": "应收账款", "text": "大额应收款项需函证", "severity": "warning"},
    {"category": "应收账款", "text": "关联方往来需单独披露", "severity": "info"},
    # 存货
    {"category": "存货", "text": "请补充存货监盘记录", "severity": "blocking"},
    {"category": "存货", "text": "请核实存货跌价准备计提合理性", "severity": "warning"},
    {"category": "存货", "text": "请分析存货周转率变动原因", "severity": "warning"},
    {"category": "存货", "text": "呆滞存货需评估可变现净值", "severity": "info"},
    # 固定资产
    {"category": "固定资产", "text": "请核实本期新增资产入账依据", "severity": "warning"},
    {"category": "固定资产", "text": "请复核折旧计提准确性", "severity": "warning"},
    {"category": "固定资产", "text": "请关注是否存在减值迹象", "severity": "warning"},
    {"category": "固定资产", "text": "处置固定资产损益需核实审批手续", "severity": "info"},
    # 收入
    {"category": "营业收入", "text": "请执行收入截止测试", "severity": "blocking"},
    {"category": "营业收入", "text": "请分析收入波动原因", "severity": "warning"},
    {"category": "营业收入", "text": "请核实关联方交易定价公允性", "severity": "warning"},
    {"category": "营业收入", "text": "新收入准则下合同资产/负债需核实", "severity": "info"},
    # 费用
    {"category": "费用", "text": "请核实大额异常费用", "severity": "warning"},
    {"category": "费用", "text": "请检查费用跨期情况", "severity": "warning"},
    {"category": "费用", "text": "研发费用资本化条件需核实", "severity": "warning"},
    # 税金
    {"category": "税金", "text": "请核实所得税费用与利润总额的匹配性", "severity": "warning"},
    {"category": "税金", "text": "递延所得税资产可实现性需评估", "severity": "warning"},
    {"category": "税金", "text": "请核实税收优惠政策适用性", "severity": "info"},
    # 投资
    {"category": "投资", "text": "请核实长期股权投资权益法核算准确性", "severity": "warning"},
    {"category": "投资", "text": "请关注被投资单位是否存在减值迹象", "severity": "warning"},
    # 借款
    {"category": "借款", "text": "请函证借款余额", "severity": "warning"},
    {"category": "借款", "text": "请核实借款利率和利息计提", "severity": "warning"},
    {"category": "借款", "text": "请关注借款合同中的限制性条款", "severity": "info"},
]


def get_review_templates(category: str | None = None) -> list[dict]:
    """获取复核意见模板列表，可按分类筛选"""
    if category:
        return [t for t in REVIEW_TEMPLATES if t["category"] == category]
    return REVIEW_TEMPLATES


def get_template_categories() -> list[str]:
    """获取所有模板分类"""
    return sorted(set(t["category"] for t in REVIEW_TEMPLATES))
