# 设计：税审底稿取数、公式计算与保存

## 1 数据流

```
样表 xlsx ──gen_tax_workpaper_sheets.py──┬─> 前端 sheets/<编号>.json（显示结构 + 值格 ref）
                                          └─> backend/data/tax_workpaper_model.json（全部公式 / 常量 / 取数规则）

GET /api/projects/{pid}/tax-workpapers/sheets/{code}?year=
  tax_workpaper_service.compute_sheet
    ├─ 读本项目全部手工值（tax_workpaper_inputs）+ 参数
    ├─ tax_workpaper_fetch：账套（tb_balance / tb_ledger / account_mapping）→ 科目树 → 规则取数
    └─ tax_formula_engine：只算本表依赖到的公式（拓扑序），返回本表打印区内的值格
PUT  …/sheets/{code}?year=   {version, inputs}   → 保存手工值，返回重算结果
GET/PUT …/params?year=                         → 表头参数
```

## 2 计算模型 `backend/data/tax_workpaper_model.json`
- 纳入：编号对应的 sheet + 它们传递引用到的 sheet（索引、填写参数、A 类申报表）。说明类 sheet 不纳入。
- 每个 sheet：`cells` = 全部非空格（公式存公式文本，常量存值），`print` = 打印区。公式里的 `[1]` 外部簿前缀按本簿处理。
- `codes`：编号 → [sheet 名]；`params`：参数页 sheet 名与 B1~B15 的标签、下拉选项。
- `rules`：展开到单元格的取数项（§3）。规则目标格上的样表常量 / 公式由取数结果替代；`G列=E列+F列`、`3-2-1-01!D52` 两条规则转成公式写进模型。

## 3 取数规则（生成时解析，运行时只按结构执行）
每个目标格一项：`{sheet, ref, rule, status, op, ...}`
- `op=amount`：`path`（["其他业务收入","出租固定资产收入"]）或 `label`（取本行某格文字作为最后一级）、`measure`。
- `op=month`：`path` / `label`（同列第 6 行）、`measure`、`month`（1~12）。
- `op=list_name` / `list_amount`：同一张列表（`lists[id]`：`path`、`mode`=children|leaves|others、`exclude`）的第 n 行名称 / 金额；行数不够时超出部分并入最后一行。
- `op=others_sum`：`path` 下排除 `exclude` 名称后的合计。
- `measure`：`credit` / `debit` / `opening` / `closing`（自然方向为正）、`closing_debit` / `closing_credit`（借方 / 贷方余额，取正数）。
- `status`：`auto`（@直取）/ `confirm`（@说明但口径确定）/ `manual`（需人工判断，不取数）。
- 解析不了的规则 → 生成失败并点名；原文笔误 → `CORRECTIONS` 表按目标格纠正并登记。

## 4 科目树与取数 `tax_workpaper_fetch`
- 只读当前有效账套：`get_active_filter(TbBalance)`；科目码剥 `.0`；同码多行取名字不以「\」开头的那一行（真库同码有一行是错位名）。
- 父子：按码前缀（最长前缀为父）。标准科目：本码或最近上级在 `account_mapping` 里的映射。
- 一级名称 → 标准码：标准科目表按名查；查不到按客户科目名查；`存货` 等用别名组。
- 某标准码的「顶层节点」= 映射到它、但上级不映射到它的客户科目；路径下一级在顶层节点的下级里按名称匹配（去空白、全半角括号、取「\」后最后一段；先全等后包含；同义词表如 应付福利费 ≈ 职工福利费）。
- 金额：节点有余额行用本行，否则下级合计。期初 / 期末按 `*_direction` 转借正贷负，再按标准科目方向转自然正数。按月发生额来自 `tb_ledger` 按 `accounting_period` 汇总（节点 + 全部下级）。
- 取不到：值为空 + `issue` 文字。

## 5 公式引擎 `tax_formula_engine`
- openpyxl Tokenizer 分词 → 递归下降解析（`: ` 区域、`-` 取负、`%`、`^`、`* /`、`+ -`、`&`、比较）。
- 值：`Decimal` / `str` / `bool` / 空 / `XlError`。空值参与算术为 0、参与比较为 0 或空串；错误按 Excel 传播，`IFERROR` 捕获。
- 依赖图在模型加载时建好（区域展开到公式格），每次请求只算本表依赖闭包，按拓扑序逐格求值，无递归深度问题；有环的格返回 `#CIRC!`。
- 不支持的函数 → `#NAME?`；测试断言模型里用到的函数全部受支持。

## 6 存储 `tax_workpaper_inputs`（V211 / R211）
`id, project_id, year, sheet_code, inputs JSONB({sheet名: {ref: 值}}), version, updated_by, updated_at, created_at`，唯一 `(project_id, year, sheet_code)`。参数存 `sheet_code='__params__'`。PUT 带 `version`，不符 409。

## 7 前端
- `sheets/<编号>.json` 值格带 `ref`（单元格地址）、`role`（`f` 公式 / `e` 可填）、`fmt`（`money` / `pct` / `int`）。
- `TaxWorkpaperSheetPanel` 进页拉 `GET`，按 `ref` 填值；可填格可直接编辑，取数格着色（待确认橙、需人工填写灰），悬停显示规则原文与问题；「保存」「恢复取数」；顶部列取数问题。
- 索引页上方「表头信息」面板编辑参数。

## 8 范围外
- 导入 / 导出按钮仍不开放；「有 / 无」标记仍存浏览器本地。
- 审计调整、审核调整额列不自动取数（人工填写）。
- A 类申报表本身不做页面（只参与计算）。
