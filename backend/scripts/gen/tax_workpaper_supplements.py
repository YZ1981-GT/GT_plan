"""样表没有「取数规则」区的表的补充取数（生成脚本内部模块；spec citar-audited-balance-and-workpaper-coverage R3~R5）。

- ``ROW_GROUPS``：按行标签分类（2-07 / 2-08 / 2-09 / 2-10）——一级科目的末级明细按名称归到各行（运行时
  ``tax_workpaper_classify``），归不进的列在「其他」明细行；
- ``LIST_GROUPS``：按类别列明细（3-03-04 长期待摊费用：每类两行名称 + 本年摊销额，其余进「其他长期待摊费用」）；
- ``TAX_DEFAULTS``：资产类审核表的税收金额默认等于账载金额（标待确认，可改）；
- ``SHEET_NOTES``：整表说明（需人工填写的内容、按名称归类的口径）。

行名逐条核对样表原文，对不上即失败（样表改版时不悄悄错行）；目标格不能是样表公式格、不能已有取数规则。
别名口径见 ``app.services.tax_workpaper_classify``：``exact`` 全等、``contains`` 末级名称包含、``not_contains`` 末级
全路径含这些字时该行不参与。
"""

from __future__ import annotations

from typing import Callable

from app.services.tax_workpaper_fetch import name_key
from tax_workpaper_rules import ParsedRules, RuleParseError

STATUS = "confirm"


def _a(exact=(), contains=(), not_contains=()) -> dict:
    return {"exact": list(exact), "contains": list(contains), "not_contains": list(not_contains)}


_SOCIAL = ("社会保险", "社保", "养老", "医疗", "失业", "工伤", "生育", "劳动保险", "年金")

#: 2-08 销售费用 / 2-09 管理费用：行号 → (样表行名, 别名)。公式行（8 职工薪酬 / 14 社保 / 20 补充保险 / 44 其他 / 66 合计）不列
EXPENSE_ROWS: list[tuple[int, str, dict]] = [
    (9, "工资薪金支出", _a(["工资", "工资薪金", "薪金", "奖金", "津贴", "补贴", "基本工资", "绩效工资", "加班费"],
                         ["工资", "奖金", "津贴", "薪金", "股份支付", "股权激励"])),
    (10, "职工福利费支出", _a(["福利费", "职工福利费", "职工福利"],
                          ["福利费", "宿舍", "住宿", "员工餐", "职工餐", "食堂", "取暖", "防暑降温", "体检", "医疗费"],
                          ["差旅", "辞退"])),
    (11, "职工教育经费支出", _a(["职工教育经费", "教育经费", "培训费", "职工培训费"], ["教育经费", "培训"])),
    (12, "工会经费支出", _a(["工会经费", "工会会费"], ["工会"])),
    (13, "住房公积金", _a(["住房公积金", "公积金"], ["公积金"])),
    (15, "基本养老保险", _a(["养老保险", "养老保险费", "养老保险金"], ["养老"], ["补充养老", "年金"])),
    (16, "失业保险", _a(["失业保险费", "失业保险金"], ["失业"])),
    (17, "基本医疗保险", _a(["医疗保险", "医疗保险费", "大额医疗保险", "医疗生育保险"], ["医疗", "医保"], ["补充医疗", "医疗费"])),
    (18, "基本生育保险", _a(["生育保险", "生育保险费", "生育保险金"], ["生育"])),
    (19, "工伤保险", _a(["工伤保险费", "工伤保险金"], ["工伤"])),
    (21, "补充养老保险", _a(["企业年金", "年金"], ["补充养老", "年金"])),
    (22, "补充医疗保险", _a(["补充医疗"], ["补充医疗"])),
    (23, "其他职工薪酬", _a(["辞退福利", "其他薪酬", "职工薪酬", "非货币性福利", "带薪缺勤"],
                         ["辞退", "解除劳动关系", "离职补偿", "经济补偿金"])),
    (24, "劳务费", _a(["劳务费", "劳务外包费", "劳务派遣费", "外包服务费"], ["劳务", "外包", "派遣"])),
    (25, "咨询顾问费", _a(["咨询费", "顾问费", "中介机构服务费", "咨询服务费", "审计费", "法律服务费", "律师费"],
                       ["咨询", "顾问", "中介", "审计费", "律师", "法律服务"])),
    (26, "业务招待费", _a(["招待费", "交际应酬费"], ["招待"])),
    (27, "广告费和业务宣传费", _a(["广告费", "宣传费", "业务宣传费", "广告宣传费", "宣传推广费", "推广费"], ["广告", "宣传", "推广"])),
    (28, "佣金和手续费", _a(["佣金", "手续费", "佣金手续费"], ["佣金", "手续费"])),
    (29, "资产折旧摊销费", _a(["折旧费", "摊销费", "折旧摊销", "折旧", "摊销", "摊销费用", "固定资产折旧", "无形资产摊销"],
                          ["折旧", "摊销"], ["低值易耗品", "周转材料", "包装物"])),
    (30, "财产损耗、盘亏及毁损损失", _a(["财产损耗", "盘亏", "毁损", "财产损失"], ["盘亏", "毁损", "财产损"])),
    (31, "办公费", _a(["办公费", "办公用品", "办公经费", "通讯费", "通信费", "邮电费", "电话费", "印刷费"],
                   ["办公", "通讯", "通信", "邮电", "电话", "印刷"])),
    (32, "董事会费", _a(["董事会经费"], ["董事会"])),
    (33, "租赁费", _a(["租金", "房租", "房屋租赁费", "租赁费用"], ["租赁", "租金", "房租"])),
    (34, "诉讼费", _a([], ["诉讼"])),
    (35, "差旅费", _a(["差旅"], ["差旅"])),
    (36, "保险费", _a(["财产保险费", "车辆保险费"], ["保险"], _SOCIAL)),
    (37, "运输、仓储费", _a(["运输费", "仓储费", "运杂费", "运费", "物流费", "快递费", "仓储保管费", "装卸费"],
                         ["运输", "仓储", "运杂", "运费", "物流", "快递", "装卸"])),
    (38, "修理费", _a(["维修费", "修理维护费"], ["修理", "维修"])),
    (39, "包装费", _a(["包装物"], ["包装"])),
    (40, "技术转让费", _a([], ["技术转让"])),
    (41, "研究费用", _a(["研发费", "研发费用", "研究开发费"], ["研发", "研究开发"])),
    (42, "各项税费", _a(["税金", "税费", "印花税", "房产税", "土地使用税", "车船使用税", "车船税"],
                     ["印花税", "房产税", "土地使用税", "车船"])),
    (43, "党组织工作经费", _a(["党建经费", "党组织经费", "党建工作经费"], ["党建", "党组织"])),
]

#: 2-07 税金及附加：B 列行名
TAX_ROWS: list[tuple[int, str, dict]] = [
    (9, "消费税", _a([], ["消费税"])),
    (10, "城市维护建设税", _a(["城建税", "城市建设维护税"], ["城建", "城市维护"])),
    (11, "教育费附加", _a(["国家教育费附加"], ["教育费附加"], ["地方"])),
    (12, "地方教育附加", _a(["地方教育费附加"], ["地方教育"])),
    (13, "土地增值税", _a([], ["土地增值"])),
    (14, "资源税", _a([], ["资源税"])),
    (15, "印花税", _a([], ["印花"])),
    (16, "车船使用税", _a(["车船税"], ["车船"])),
    (17, "房产税", _a([], ["房产税"])),
    (18, "土地使用税", _a(["城镇土地使用税"], ["土地使用"])),
]

#: 2-10 财务费用：B 列行名（B:C 合并）
FINANCE_ROWS: list[tuple[int, str, dict]] = [
    (8, "佣金和手续费", _a(["手续费", "佣金", "手续费支出", "银行手续费", "金融机构手续费"], ["手续费", "佣金"])),
    (9, "利息收支", _a(["利息", "利息收入", "利息支出", "利息费用", "借款利息", "贴现费用", "贴现利息", "租赁负债利息"],
                    ["利息", "贴现"])),
    (10, "汇兑差额", _a(["汇兑损益", "汇兑损失", "汇兑收益", "汇兑净损失"], ["汇兑"])),
    (11, "现金折扣", _a(["现金折扣支出"], ["现金折扣"])),
]

#: (sheet, 一级科目, 一级科目的其他写法, 口径, 金额列, 行名列, 行, 其他明细的名称列, 其他明细行)
ROW_GROUPS = [
    ("2-07", "营业税金及附加", ["税金及附加", "主营业务税金及附加"], "debit", "D", "B", TAX_ROWS, "B", [19, 20]),
    ("2-08", "销售费用", ["营业费用"], "debit", "C", "A", EXPENSE_ROWS, "B", list(range(45, 66))),
    ("2-09", "管理费用", [], "debit", "C", "A", EXPENSE_ROWS, "B", list(range(45, 66))),
    ("2-10", "财务费用", [], "debit", "D", "B", FINANCE_ROWS, "C", [13, 14, 15, 16]),
]

#: 3-03-04 长期待摊费用：(类别行名格, 样表行名, 别名, 明细行)；第五类「其他长期待摊费用」= 归不进前四类的
DEFERRED_CATEGORIES: list[tuple[str, str, dict, list[int]]] = [
    ("B8", "已足额提取折旧的固定资产的改建支出", _a([], ["已提足折旧", "足额提取折旧", "提足折旧"]), [9, 10]),
    ("B11", "租入固定资产的的改建支出", _a(["装修费", "装修工程", "租入固定资产改良", "经营租入固定资产改良"],
                                     ["租入", "装修", "改建", "改良"], ["提足折旧", "足额提取折旧"]), [12, 13]),
    ("B14", "固定资产大修理支出", _a([], ["大修理", "大修"]), [15, 16]),
    ("B17", "开办费", _a(["筹建费"], ["开办", "筹建"]), [18, 19]),
]
DEFERRED_REST = ("B20", "其他长期待摊费用", [21, 22])
DEFERRED_AMOUNT = {"E": "credit"}
DEFERRED_TAX_COPY = {"I": "E"}

_RULE_ROW = "{path}末级明细按科目名称归入本行（{label}）；归不进各行的列在「其他」明细，待确认"
_RULE_REST = "{path}末级明细中归不进上面各行的科目（按科目名称归类），待确认"
_TAX_RULE = "税收金额默认等于账载金额（同口径取数）；税会有差异时改为税收金额。账载取数："

#: 职工薪酬类审核表「实际发放 / 支出」部分（样表没有取数规则：账载金额补上以后，这部分为空会把整笔薪酬当成未支付全额调增，
#: 案例 1 应纳税所得额因此多出 1,223 万）。
#: - 应付科目的年初余额 / 借方 / 贷方从账套取；「本年支付以前年度」= min(年初余额, 借方)；
#: - 「汇算清缴期支付」默认 = 年末余额（不超过本年计提），即假定年末未付部分在汇算清缴期付清 —— 需核对次年 1~5 月发放记录；
#: - 「未通过应付科目核算」默认 = 审核确认额 − 应付科目本年计提（直接列支的部分，视同已支付）；
#: - 社保「实际支付额」默认 = 审核确认额。
#: 都是待确认 / 可手工修改；有证据表明未支付的，由审核人员改。
#: (sheet, 格, 行名前缀（核对样表）, 取数路径, 口径)
PAYROLL_RULES: list[tuple[str, str, str, list[str], str]] = [
    ("3-02-01-01", "D20", "年初余额", ["应付职工薪酬", "工资"], "opening"),
    ("3-02-01-01", "D21", "借方发生额", ["应付职工薪酬", "工资"], "debit"),
    ("3-02-01-01", "D22", "其中：本年发放以前年度工资额", ["应付职工薪酬", "工资"], "paid_opening"),
    ("3-02-01-01", "D25", "贷方发生额", ["应付职工薪酬", "工资"], "credit"),
    ("3-02-01-02", "D21", "其中：本年支付以前年度", ["应付职工薪酬", "应付福利费"], "paid_opening"),
    ("3-02-01-03", "D22", "其中：本年支付以前年度", ["应付职工薪酬", "职工教育经费"], "paid_opening"),
    ("3-02-01-04", "D21", "其中：支付上年金额", ["应付职工薪酬", "工会经费"], "paid_opening"),
]
#: (sheet, 格, 行名所在格, 行名前缀, 默认公式)
PAYROLL_DEFAULTS: list[tuple[str, str, str, str, str]] = [
    ("3-02-01-01", "D27", "C27", "汇算清缴期间发放额", "=MIN(MAX(0,D26),MAX(0,D25))"),
    ("3-02-01-02", "D25", "C25", "汇算清缴期支付", "=MIN(MAX(0,D24),MAX(0,D23))"),
    ("3-02-01-02", "D27", "B27", "未通过应付福利费", "=MAX(0,D16-MAX(0,D23))"),
    ("3-02-01-03", "D26", "C26", "汇算清缴期支付", "=MIN(MAX(0,D25),MAX(0,D24))"),
    ("3-02-01-03", "D28", "B28", "未通过其他应付款-职工教育经费", "=MAX(0,D16-MAX(0,D24))"),
    ("3-02-01-04", "D26", "C26", "汇算清缴期支付", "=MIN(MAX(0,D25),MAX(0,D24))"),
    ("3-02-01-04", "D28", "B28", "未通过其他应付款-工会经费", "=MAX(0,D16-MAX(0,D24))"),
    ("3-02-01-05", "E7", "A7", "基本养老保险", "=D7"),
    ("3-02-01-05", "E8", "A8", "失业保险", "=D8"),
    ("3-02-01-05", "E9", "A9", "基本医疗保险", "=D9"),
    ("3-02-01-05", "E10", "A10", "基本生育保险", "=D10"),
    ("3-02-01-05", "E11", "A11", "工伤保险", "=D11"),
    ("3-02-01-07", "I20", "B20", "未通过应付职工薪酬-住房公积金", "=MAX(0,K8-MAX(0,I16))"),
    # 广告费和业务宣传费扣除率：一般企业 15%（实施条例第四十四条）；化妆品制造 / 医药制造 / 饮料制造 30%、烟草 0，请改
    ("3-02-03", "G14", "B14", "税收规定的扣除率", "=0.15"),
]
_PAYROLL_RULE = "{path}{measure}（应付科目取数），待确认；与实际发放记录不符时改"
_MEASURE_TEXT = {"opening": "年初余额", "debit": "借方发生额", "credit": "贷方发生额", "paid_opening": "本年支付的年初余额"}

#: 税收金额默认 = 账载金额：sheet → (行, {目标列: 来源列})
TAX_DEFAULTS: dict[str, tuple[list[int], dict[str, str]]] = {
    "3-03-01": ([r for start in (11, 16, 21, 26, 31, 36) for r in range(start, start + 4)],
                {"J": "E", "M": "H", "N": "H", "P": "I"}),
    "3-03-02": ([10, 11, 12, 14, 15, 16], {"H": "C", "K": "F", "M": "G"}),
    "3-03-03": (list(range(9, 17)), {"H": "D", "J": "F", "L": "G"}),
}

SHEET_NOTES: dict[str, list[str]] = {
    "2-07": ["账载金额按「税金及附加」末级科目名称归入各行（城建税 → 城市维护建设税等），表上没有的税种列在 11、12 行；请核对归类"],
    "2-08": ["账载金额按「销售费用」末级科目名称归入各行，归不进的列在「其他」明细；归类是按名称判断的，请核对（尤其职工薪酬各项与其他）"],
    "2-09": ["账载金额按「管理费用」末级科目名称归入各行，归不进的列在「其他」明细；归类是按名称判断的，请核对（尤其职工薪酬各项与其他）"],
    "2-10": ["账载金额按「财务费用」末级科目名称归入各行，归不进的列在「其他」明细；利息收入以负数计入利息收支"],
    "3-03-01": ["税收金额（计税基础、税收折旧额、累计折旧）默认等于账载金额，按税法计算有差异的请改；加速折旧、一次性扣除需人工填写"],
    "3-03-04": ["本年摊销额取「长期待摊费用」各明细的本年贷方发生额，按名称归类；原值、摊销年限、累计摊销额、计税基础需人工填写，"
                "税收本年摊销额默认等于账载"],
    "3-03-08": ["资产损失需按损失类别（坏账、存货盘亏毁损、固定资产处置等）逐项填写，并留存相关证据；账套里没有可直接取的数"],
    "5-01-06": ["本年境内所得额取自申报表；前十年度的所得额、亏损额、已弥补额请按以前年度纳税申报表 / 审核报告填写"],
    "3-02-01-01": ["实际发放取「应付职工薪酬-工资」（含奖金、股份支付）；汇算清缴期间发放额默认 = 年末余额（假定汇算清缴期付清），"
                   "请按次年 1~5 月实际发放记录核对修改"],
    "3-02-01-02": ["实际支出默认：应付福利费科目借方 + 汇算清缴期支付（默认 = 年末余额）+ 未通过应付科目直接列支部分（默认 = 审核确认额 − 本年计提），请核对"],
    "3-02-01-03": ["实际支出默认：应付科目借方 + 汇算清缴期支付（默认 = 年末余额）+ 未通过应付科目直接列支部分（默认 = 审核确认额 − 本年计提），请核对"],
    "3-02-01-04": ["实际支付默认：应付科目借方 + 汇算清缴期支付（默认 = 年末余额）+ 未通过应付科目直接列支部分（默认 = 审核确认额 − 本年计提），请核对拨缴凭证"],
    "3-02-01-05": ["实际支付额默认 = 审核确认额，有欠缴的请改"],
    "3-02-01-07": ["实际支出：应付职工薪酬-住房公积金科目取数 + 未通过该科目直接列支部分（默认 = 审核确认额 − 本年计提），请核对"],
    "3-02-13": ["与取得收入无关的支出需审核人员逐项判断后填写（账套里没有可直接取的数）"],
    "3-02-03": ["扣除率默认 15%（一般企业）；化妆品制造或销售、医药制造、饮料制造（不含酒类）为 30%，烟草企业不得扣除，请按行业改"],
    "3-02-15": ["扣除类其他调整事项需审核人员逐项判断后填写"],
}


def _check_label(cell_text: Callable[[str, str], str | None], sheet: str, ref: str, expect: str) -> str:
    text = cell_text(sheet, ref)
    if name_key(text or "") != name_key(expect):
        raise RuleParseError(f"{sheet}!{ref} 样表行名是 {text!r}，补充取数要求 {expect!r}（样表改版？）")
    return text


def _check_prefix(cell_text: Callable[[str, str], str | None], sheet: str, ref: str, expect: str) -> None:
    text = cell_text(sheet, ref) or ""
    if not name_key(text).startswith(name_key(expect)):
        raise RuleParseError(f"{sheet}!{ref} 样表行名是 {text!r}，补充取数要求以 {expect!r} 开头（样表改版？）")


def apply_supplements(rules: ParsedRules, cell_text: Callable[[str, str], str | None],
                      is_formula: Callable[[str, str], bool]) -> dict:
    """把补充取数项并入 ``rules``（items / lists / formulas），返回 {"classify_groups": …, "sheet_notes": …}。"""
    taken = {(i["sheet"], i["ref"]) for i in rules.items}
    defaults: list[tuple[str, str, str]] = []

    def add(sheet: str, ref: str, rule: str, op: str, **extra) -> None:
        if (sheet, ref) in taken:
            raise RuleParseError(f"{sheet}!{ref} 已有取数规则，补充取数不能覆盖")
        if is_formula(sheet, ref):
            raise RuleParseError(f"{sheet}!{ref} 是样表公式格，补充取数不能写入")
        taken.add((sheet, ref))
        rules.items.append({"sheet": sheet, "ref": ref, "rule": rule, "status": STATUS, "op": op, **extra})

    def add_list(sheet: str, list_id: str, group: str, path: list[str], category, name_col: str,
                 rows: list[int], amounts: dict[str, str], rule: str, tax_copy: dict[str, str] | None = None) -> None:
        refs = [f"{name_col}{r}" for r in rows]
        rules.lists[list_id] = {"sheet": sheet, "path": path, "mode": "classified", "group": group,
                                "category": category, "exclude": [], "refs": refs}
        for i, r in enumerate(rows):
            add(sheet, f"{name_col}{r}", rule, "list_name", list=list_id, index=i)
            for col, measure in amounts.items():
                add(sheet, f"{col}{r}", rule, "list_amount", list=list_id, index=i, path=path, measure=measure)
            for target, source in (tax_copy or {}).items():
                add(sheet, f"{target}{r}", _TAX_RULE + rule, "list_amount", list=list_id, index=i,
                    path=path, measure=amounts[source])

    groups: dict[str, dict] = {}
    for sheet, top, aliases, measure, amount_col, label_col, rows, rest_col, rest_rows in ROW_GROUPS:
        group_id = f"{sheet}!classify"
        categories = []
        for row, expect, alias in rows:
            label = _check_label(cell_text, sheet, f"{label_col}{row}", expect)
            categories.append({"index": row, "label": label, **alias})
            add(sheet, f"{amount_col}{row}", _RULE_ROW.format(path=top, label=expect), "classify",
                group=group_id, category=row)
        groups[group_id] = {"sheet": sheet, "path": [top], "base_names": aliases, "measure": measure,
                            "categories": categories}
        add_list(sheet, f"{sheet}!rest", group_id, [top], None, rest_col, rest_rows, {amount_col: measure},
                 _RULE_REST.format(path=top))

    # 3-03-04：每类两行名称 + 本年摊销额，第五类 = 其余
    sheet, top, group_id = "3-03-04", "长期待摊费用", "3-03-04!classify"
    categories = []
    for i, (ref, expect, alias, cat_rows) in enumerate(DEFERRED_CATEGORIES, start=1):
        label = _check_label(cell_text, sheet, ref, expect)
        categories.append({"index": i, "label": label, **alias})
        add_list(sheet, f"{sheet}!cat{i}", group_id, [top], i, "B", cat_rows, DEFERRED_AMOUNT,
                 _RULE_ROW.format(path=top, label=expect), DEFERRED_TAX_COPY)
    rest_ref, rest_label, rest_rows = DEFERRED_REST
    _check_label(cell_text, sheet, rest_ref, rest_label)
    add_list(sheet, f"{sheet}!rest", group_id, [top], None, "B", rest_rows, DEFERRED_AMOUNT,
             _RULE_REST.format(path=top), DEFERRED_TAX_COPY)
    groups[group_id] = {"sheet": sheet, "path": [top], "base_names": [], "measure": "credit", "categories": categories}

    # 职工薪酬类审核表：应付科目取数 + 实际发放 / 支出默认公式（可手工修改）
    for sheet, ref, expect, path, measure in PAYROLL_RULES:
        row = int(ref[1:])
        _check_prefix(cell_text, sheet, f"C{row}", expect)
        add(sheet, ref, _PAYROLL_RULE.format(path="-".join(path), measure=_MEASURE_TEXT[measure]), "amount",
            path=path, measure=measure)
    for sheet, ref, label_ref, expect, formula in PAYROLL_DEFAULTS:
        _check_prefix(cell_text, sheet, label_ref, expect)
        if (sheet, ref) in taken or is_formula(sheet, ref):
            raise RuleParseError(f"{sheet}!{ref} 已有取数规则或样表公式，不能写默认公式")
        defaults.append((sheet, ref, formula))

    # 税收金额默认 = 账载金额（复制账载格的取数项）
    by_ref = {(i["sheet"], i["ref"]): i for i in rules.items}
    for sheet, (rows, copy) in TAX_DEFAULTS.items():
        for row in rows:
            for target, source in copy.items():
                src = by_ref.get((sheet, f"{source}{row}"))
                if src is None:
                    raise RuleParseError(f"{sheet}!{source}{row} 没有账载取数项，不能给 {target}{row} 设税收默认值")
                extra = {k: v for k, v in src.items() if k not in ("sheet", "ref", "rule", "status", "op")}
                add(sheet, f"{target}{row}", _TAX_RULE + str(src["rule"]), src["op"], **extra)

    rules.formulas.extend(defaults)
    rules.corrections.append(
        "补充取数（样表无取数规则区）：2-07 / 2-08 / 2-09 / 2-10 账载金额按末级科目名称分行，3-03-04 按类别列明细；"
        "3-03-01 / 3-03-02 / 3-03-03 / 3-03-04 税收金额默认等于账载金额；3-02-01-01~07 实际发放 / 支出按应付科目取数、"
        "其余部分给默认公式（spec citar-audited-balance-and-workpaper-coverage）"
    )
    return {"classify_groups": groups, "sheet_notes": SHEET_NOTES}
