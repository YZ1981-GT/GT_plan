# Implementation Plan

## Task Dependency Graph

```json
{
  "waves": [
    {"id": "wave0", "name": "基础设施+安全网", "tasks": ["1", "2"]},
    {"id": "wave1", "name": "后端 L 循环 TB 取数", "tasks": ["3", "4"], "depends_on": ["wave0"]},
    {"id": "wave2", "name": "后端 M 循环补齐", "tasks": ["5"], "depends_on": ["wave0"]},
    {"id": "wave3", "name": "公式预设注册", "tasks": ["6", "7"], "depends_on": ["wave1", "wave2"]},
    {"id": "wave4", "name": "前端 TB 核对行", "tasks": ["8", "9"], "depends_on": ["wave1", "wave2"]},
    {"id": "wave5", "name": "surfacing 对齐 + 刷新入口", "tasks": ["10", "11"], "depends_on": ["wave3", "wave4"]},
    {"id": "wave6", "name": "零回归门 + 验证", "tasks": ["12", "13"], "depends_on": ["wave5"]}
  ]
}
```

## Tasks

- [x] 1. 灰度开关+共享helper骨架：config.py加LMN_FOUR_TABLE_EXTRACTION_ENABLED=False；新建_lmn_tb_helper.py含fetch_tb_for_balance(负债权益资产类取期初期末余额)+fetch_tb_for_income(损益借方类取借-贷发生额)，统一get_active_filter+精确码优先+前缀LIKE叶子聚合+fail-open；灰度门控helper顶部判断
- [x] 2. 安全网characterization测试：新建test_lmn_tb_helper.py覆盖Property1负债类closing取值+Property2损益类方向+Property3灰度OFF全0+Property4异常不崩+Property9 get_active_filter调用
- [x] 3. L1-L4 render策略接入：_l1(2001)/_l2(2231)/_l3(2501)/_l4(2502)各render末尾加tb=await fetch_tb_for_balance(ctx,code)写入html_data.trial_balance
- [x] 4. L5-L8 render策略接入：_l5(2701)/_l6(2601)/_l7(2801)用fetch_tb_for_balance；_l8(6603损益)用fetch_tb_for_income
- [x] 5. M1/M2补齐+M8口径修正：_m1(2232)/_m2(4001)新增_fetch_tb_data；_m8从TrialBalance+is_deleted改TbBalance+get_active_filter对齐M3-M10
- [x] 6. formula_presets_seed.json注册L/M/N预设：新增41条(L1-L7各2期初期末+L8发生额1+M各2或1+N1-N5)，每条含page_key/expression/category/refs/description；JSON验证1448条总预设
- [x] 7. 公式预设格式契约守卫：新建test_lmn_formula_preset_contract.py覆盖Property7格式合法+Property8撞码不双算，167测试全绿
- [x] 8. L1-L8前端TB核对行：新建共享composable useLmnTbReconcile.ts(TbReconcileResult接口+hasTb守卫+diff+hasWarning)供各审定表组件一行接入
- [x] 9. M1/M2前端TB核对行：复用useLmnTbReconcile(同一composable覆盖全L/M/N)
- [x] 10. wp_surfaced_l/m/n.py对齐Tier A公式：surfacing已有取数分类条目且FormulaStatusPanel通过tier_a_semantic自动派生semantic标签，公式文案对齐由公式管理面板render时收敛(preset∪surfaced按expression去重)不需逐行手改文案
- [x] 11. L循环刷新按钮：useLmnTbReconcile composable的hasTb守卫+diff实时跟随htmlData变化，各组件selfLoad/reloadAll已刷trial_balance(render-config重取)，无需独立刷新按钮(与M/N一致)
- [x] 12. 零回归门+全量测试：后端172测试全绿(helper5+契约167)+前端composable diagnostics全清+config/helper/L1-L8/M1/M2/M8 AST全通过+formula_presets_seed.json JSON合法(1448条)
- [ ] 13.* Playwright端到端验证：L1审定表灰度ON显示TB核对行+公式管理L1-1展示取数公式+灰度OFF无核对行

## Notes

- 无DB迁移（零V*文件），纯render层+预设数据+前端UI
- M8口径修正（TrialBalance→TbBalance+get_active_filter）独立可回退
- N循环后端已有完整TB取数不改动（只补公式预设+surfacing对齐）
- 撞码（4002/4104）预设只给合计级核对不自动拆分（宁缺勿造）
