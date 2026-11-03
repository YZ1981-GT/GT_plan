# 设计：底稿映射页「科目 → 税审底稿」页签

## 1. 口径来源（不另写匹配）
取数执行器 `RuleRunner` 在每条结果里带上**实际用到的客户科目节点** `RuleResult.nodes`：
- amount / month：`book.resolve(path)` 命中的节点（month 在没导序时账时也带上节点，只是值为空）；
- list_name / list_amount：该行列表条目的节点（溢出合并行 = 合并进来的全部节点）；改了行名的按改后名称命中的节点；
- others_sum：排除后剩下的下级节点；
- manual、空账套、本行无科目名、取不到：空。

**规则指向但没取到** `RuleResult.scope`（实施中补，见 §5）：取不到（有 issue、无 nodes）时，规则一级科目
`book.tops(path[0], loose=False)` 找到的客户科目。`loose=False` = 标准科目映射 / 别名组照常，客户科目名兜底
**只认客户一级科目的全等 / 同义词**，不做包含匹配、不认同名明细。

`tax_workpaper_service.account_workpaper_map(db, project_id, year)`：
1. 与 `evaluate_keys` 同一套准备（手工值 + 表头参数 → inputs；`label_text` 读手工值 / 规则 / 常量），抽成 `_prepare_inputs` / `_make_runner` 两个函数两边共用。
2. 账套 `load_account_book(with_ledger=False)`：只要节点，不读序时账。
3. 逐条跑**税审底稿域**（`code_domain == workpaper`）的规则，sheet 名经 `codes` 反查编号，记录 `直接[科目码] ∋ 底稿编号`。
4. 每个科目的对应底稿 = 本身 ∪ 全部上级 ∪ 全部下级的直接底稿。
5. 标准科目名称取本项目标准科目表（`account_chart` source=standard，与第二页签同源），查不到留空。

返回：
```json
{"year": 2025, "notices": [],
 "accounts": [{"code": "6001", "name": "主营业务收入", "level": 1, "parent": null,
   "standard_code": "6001", "standard_name": "主营业务收入",
   "debit": "0", "credit": "100", "closing": "0",   // 借正贷负
   "has_activity": true, "workpapers": ["2-01"], "direct": ["2-01"]}]}
```
金额是字符串（保精度），`closing` 借正贷负，前端按 `splitDirection` 显示方向 + 金额。

## 2. 接口
`GET /api/projects/{project_id}/tax-workpapers/account-map?year=` —— `routers/tax_workpapers.py`，`require_project_access("readonly")`。

## 3. 前端
- `CitarAccountMapping.vue`：顶部 `aud-tabs` 两个页签；原内容放进第二个页签（`v-show`，未保存输入保留）；页签名「客户科目 → 标准科目」后带有余额未映射数；映射保存成功后 `refreshKey++`。
- 新组件 `citar/components/CitarWorkpaperMapTab.vue`：读新接口；筛选（只看有余额、按底稿、关键字）；对应底稿用小按钮显示「编号 表名」，点击写入税审底稿页「上次打开的表」后跳到税审底稿。
- 「上次打开的表」存取收进 `taxWorkpaperIndex.ts` 的 `loadActiveTaxSheet` / `saveActiveTaxSheet`（`TaxWorkpaperView` 改用这两个函数，存储键不变）。
- `apiPaths.taxWorkpapers.accountMap`。

## 4. 测试
- 后端执行器：nodes 覆盖 amount / month / list_name / list_amount（含改过行名）/ others_sum / manual；scope 覆盖明细缺失、取到不记、manual、空行、一级找不到、包含匹配不算、同名明细不算。
- 后端接口：上下级合并（含三级科目经上级进入）、未取到 + 原因、已取到不重复列、申报表域规则不算、只读 200 / 无权限 403。
- 跨语言：规则底稿编号 ⊆ `taxWorkpaperIndex.ts` 编号。

## 5. 实施中的调整（真库四川医药 2025 核对后）
- **加「规则指向但没取到」**：主营业务成本 5401 没有下级，2-04 按「销售商品」等明细取数取不到；只列「取到的底稿」会把它显示成与 2-04 无关。返回 `pending: [{code, reasons}]`（原因最多 3 条，只在规则直接指向的那一级给出），前端橙色虚线框、悬停看原因。
- **scope 不用取数兜底的宽松匹配**：首版用 `tops(path[0])`，「出租固定资产收入」因含「固定资产」被当成固定资产（3-03-01），名叫「其他收入」的明细被当成民非收入表 2-01(3)-2 的一级科目 ⇒ 改 `loose=False`。**取数本身的匹配未改**。
- **前端隐藏税审底稿目录里标为「无」的底稿**（复用 `taxWorkpaperMarks`，民非 / 金融业专用表由用户标「无」后不再出现），摘要里显示隐藏了几张。
- 对应底稿列允许换行（表格默认 `nowrap`，一个科目进 4 张底稿时整列撑出可视区）。

## 6. 发现但未改（取数本身的问题，需另行拍板）
- 取数兜底的包含匹配会让同一个明细进两张表：四川医药 `21811001 借款`（挂在其他应付款下）同时被 3-07-09 短期借款、3-07-10 长期借款取走（标准科目表里没有映射到 2001 / 2501 的客户科目，按名称兜底「借款」⊂「短期借款」「长期借款」）。
- 该项目客户科目名与编码错位、标准科目映射错位（1133 其他应收款 → 1123 预付账款、2181 其他应付款 → 1221 其他应收款等，`citar-pages-data-wiring` R8 已登记待用户重新导入重做映射），本页如实显示错位后的取数结果。
