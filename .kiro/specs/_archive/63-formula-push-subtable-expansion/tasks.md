# 公式推送子表级规则扩展 — 任务清单

## Phase 1：基础设施

- [x] 1. 扩展 `NOTE_FIELDS` 字典：注册变动表/分类表/明细表的新字段（~15 个）
  - 实际新增 32 个字段（三批）：
    - 第一批 16 个：营业收入/成本 4 + 分解信息 8 + 履约义务 3 + 分类表扩展 5
    - 第二批 16 个（D2 补 columns 后）：balance/provision/book_value/reversal/write_off/amount/cumulative_provision/end_ratio + ar_amount/contract_asset_amount/total_amount/gain_loss/asset_amount/liability_amount
  - 总计 NOTE_FIELDS 从 30 扩展到 62 个条目
- [x] 2. 新建规则生成脚本 `scripts/gen/gen_subtable_push_rules.py`：从模板 JSON 提取子表 → 生成规则
  - 改进：复用主表 rows+source.name / 按 (table,section) 去重防跨科目冲突 / 超长表名过滤 / 跨准则模板去重
- [x] 3. 验证生成的规则能被 `load_rules()` 加载且校验通过
  - 420 条规则（267 基线 + 153 子表）全部通过 load_rules() 校验

## Phase 2：D 循环（第一批）

- [x] 4. D1 应收票据全部子表规则（分类/坏账计提/变动/背书/贴现/组合，15 条）
- [x] 5. D2 应收账款子表规则（17 条）
  - 补 D2 两侧模板 columns 定义（soe 13 张 + listed 17 张 = 30 张表）
  - 参照 D1 column key 命名模式：分类表 balance/ratio/provision/loss_rate/book_value；变动表 prior_balance/provision/reversal/write_off/end_balance；跨期表 end_*/prior_*
  - 账龄表 2 字段 + 分类表 5 字段 + 单项明细 3 字段 + 组合跨期 6 字段 + 变动表 5 字段 + 前五名/终止/涉入等
- [x] 6. D3~D7 各科目子表规则（D3=1 D4=6 D5=0 D6=8 D7=1，共 16 条）
  - D4 营业收入/成本 6 条子表规则（含分解信息/履约义务），需注册 end_revenue 等新字段
  - D5 应收款项融资主表已有规则覆盖，子表 1 条被主表同名过滤
  - D3/D7 各有账龄子表
- [x] 7. D 循环真库 dry-run（和平药房_2025）
  - 420 条规则全部加载无异常
  - D 循环 88 个 items 全部正确触发（D1=20 D2=17 D3=1 D4=6+8 D5=1 D6=9 D7=1）
  - skip 原因均为业务数据层面（附注 `sub_table_data` 为空 = 用户未同步过披露表）
  - 引擎已改进：当 `sub_table_data` 中有目标子表时跳过标题校验（`engine.py`）
  - 底稿写入规则（adj_tb）正常 write/unchanged

## Phase 3：E+F 循环（第二批）

- [x] 8. E1 货币资金子表规则（1 条：受限货币资金明细）
  - 已在全量生成时写入，模板 columns 完整
- [x] 9. F1~F5 各科目子表规则（14 条：F1=3 F2=10 F4=1，F3/F5 无额外子表）
  - F2 存货最丰富：分类/跌价变动/数据资源/组合计提×4/开发成本/产品/周转房
  - 已在全量生成时写入，无需补模板 columns
- [x] 10. E+F 循环真库 dry-run（和平药房_2025）
  - 111 items，15 条子表规则全部触发无异常
  - skip 原因同 D 循环（sub_table_data 为空 + 标题校验）
  - 主表规则正常（E1 unchanged / F1~F4 fallback_to_total）

## Phase 4：G/H/I 循环（第三批）

- [x] 11. G1~G14 子表规则（42 条：G4=12 G5=8 G6=12 G7=3 G8=1 G10=2 G11=1 G13=2 G14=1）
  - 已在全量生成时写入，模板 columns 完整
- [x] 12. H1~H10 子表规则（11 条：H1=4 H2=5 H3=1 H7=2 H10=2）
- [x] 13. I1~I6 子表规则（1 条：I1=1）（I2~I6 无额外子表）
  - I1 无形资产有 1 条子表
- [x] 14. G/H/I 循环真库 dry-run（和平药房_2025）
  - 244 items，57 条子表规则全部触发无异常
  - skip 原因同前（sub_table_data 为空 + 标题校验）

## Phase 5：J/K/L/M/N 循环（第四批）

- [x] 15. J/K 循环子表规则（J2=2 K2=2 K3=3 K4=1 K6=3 K7=1 K8=1 K9=1，共 14 条）
  - K3 其他应付款的「应付利息」「应付股利」子表被跨科目同名排除（L2/M1 主表覆盖）
- [x] 16. L/M/N 循环子表规则（L1=2 L4=2 L5=2 L8=1 M2=1 M9=2 M10=1 N1=1，共 12 条）
- [x] 17. 全量真库 dry-run（和平药房_2025）
  - 211 items，33 条子表全部触发无异常（含 7 条 listed 侧独有子表）
  - skip 原因同前（sub_table_data 为空 + 标题/行不匹配）
  - **全量子表规则总计 153 条**（D=55 E=1 F=14 G=42 H=14 I=1 J=2 K=12 L=7 M=4 N=1）
  - **总规则数 420 条**（267 基线 + 153 子表），load_rules() 校验全绿

## Phase 6：公式管理面板

- [x] 18. 前端按子表分组展示（FormulaPushPanel）
  - `PushRuleView.target` 加 `table` 字段
  - `targetText()` 附注域追加子表名显示
  - 规则表格加「子表」列（有 table 显示名，无则显示「主表」）
  - `groupedRules` computed 按 stage→table 排序
- [x] 19. 全量回归测试
  - 268 passed / 0 failed（rules + engine + note_writer + binding_protocol + policy + note_skip）
  - 修复 4 个因子表规则数量增加导致的断言问题（筛选条件加 `"subtable" not in rule_id`）
  - 引擎标题校验改进：仅对 subtable 规则在 sub_table_data 有目标表时跳过校验
