# 货币资金 E1 底稿优化 - 任务清单

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-17 | 初始版本,3 Sprint / 91 task / 总工时 ~24 天(数据层 8 + UI 层 12.5 + E2E 3 + Sprint 0 0.5) |
| v1.1 | 2026-05-18 | Sprint 2 全部 48 task 完成（F1 场景裁剪+审计导航图 / F1 组件分流+全屏 / F3 程序状态 / F5 前置+复核联动 / F6 附件批注签字 / F4 sheet 过滤 / F2.3 手动公式编辑 / vitest 单测 21 用例全绿）|
| v1.2 | 2026-05-18 | Sprint 3 全部 11 task 完成（11 Playwright E2E 用例全绿 9.8s / 真实数据验证陕西华氏 E1 端到端 / PG schema 已应用 wp_e1_project_scenario + wp_e1_review_record 两个迁移）|

---

## Sprint 0 现状核验(0.5 天)

- [x] 0.1 grep `Project.scenario` / `Project.has_foreign_currency` 确认字段不存在需新增
- [x] 0.2 实测陕西华氏 E1 当前 chain 生成状态(wp_index 含 E1 + 33 sheet 是否全有)
- [x] 0.3 验证 prefill_formula_mapping E1 13 cell 是否真正生效(打开 Univer 看 E1-1 有数据)
- [x] 0.4 重写核验脚本提取 E1 4 文件表样格式(每 sheet 的列头+行结构),输出 cell 级映射基线

---

## Sprint 1 数据层(~8 天)

### F4 + F6 ORM/迁移前置(必须最先做)

- [x] 1.0 Alembic 迁移:wp_template_metadata 表新增 header_cells JSONB + llm_prompts JSONB 字段(F4.2 + F6.3 锚定;1.14/1.15 写 seed 前必须先有字段)

### F2 prefill 扩展

- [x] 1.1 prefill_engine.py 新增"不覆盖公式 cell"逻辑(cell.value.startswith("=")时跳过)+ 单测 5 用例
- [x] 1.2 prefill_engine.py 新增 LEDGER 公式类型(从 tb_ledger 汇总借方/贷方发生额)
- [x] 1.3 prefill_engine.py 新增 AUX 公式类型(从 tb_aux_balance 按维度取数)
- [x] 1.4 prefill_engine.py 新增 LEDGER_DETAIL 公式类型(从 tb_ledger 筛选明细行返回列表)
- [x] 1.5 prefill_engine.py 新增 COUNT_LEDGER 公式类型(从 tb_ledger 统计笔数)
- [x] 1.6 prefill_engine.py 新增 NOTE 公式类型(从 disclosure_notes 取附注金额)
- [x] 1.6a 基于 Sprint 0.4 表样基线(列头+行结构),设计 E1-2 cell 级公式映射表(输出 mapping_e1_2_draft.md,含 R15-R21 各币种行的 B/E 列 → TB 公式;评审通过后才做 1.7)
- [x] 1.6b 基于 Sprint 0.4 表样基线,设计 E1-3/E1-4 cell 级公式映射表(输出 mapping_e1_3_e1_4_draft.md;评审通过后才做 1.8)
- [x] 1.7 基于 1.6a 映射表,编写 E1-2 现金明细表 prefill 条目(B15-B21 数据行)
- [x] 1.8 基于 1.6b 映射表,编写 E1-3 银行存款明细表 prefill 条目(汇总驱动行)
- [x] 1.9 prefill_formula_mapping.json 写入 E1-2/E1-3/E1-4 新条目 + 单测验证

### F5 cross_wp_ref 28 条

- [x] 1.10 cross_wp_references.json 新增 A 组 14 条(CW-108~121,E1A 内部索引号跳转)
- [x] 1.11 cross_wp_references.json 新增 B 组 6 条(CW-122~127,B/C 循环联动)
- [x] 1.12 cross_wp_references.json 新增 C 组 8 条(CW-128~135,E0/A5-1/A17-5-5/S 联动)

### F6 ConsistencyGate + LLM

- [x] 1.13 consistency_gate.py 注册 3 条 E1↔CFS 规则(动态容差 max(1.0, 重要性×0.001))
- [x] 1.14 wp_template_metadata_dn_seed.json E1 条目新增 header_cells 字段(表头坐标配置)
- [x] 1.15 wp_template_metadata_dn_seed.json E1 条目新增 llm_prompts 字段(4 种 prompt 模板)
- [x] 1.16 wp_ai_service.py 新增 generate_audit_conclusion / generate_variance_analysis / generate_check_conclusion / generate_cutoff_conclusion 4 个方法

### F4 表头自动填充

- [x] 1.17 prefill_engine.py 新增 fill_header_cells(wp_id, project) 函数(按 header_cells 配置填充 R3-R4)
- [x] 1.18 chain_orchestrator._step_generate_workpapers 生成时自动调用 fill_header_cells

### F2.3 手动公式编辑器后端支持

- [x] 1.19 wp.parsed_data 新增 user_formulas dict(存用户自定义公式 cell→formula 映射)
- [x] 1.20 prefill_engine 执行优先级:user_formulas(覆盖)> prefill_formula_mapping(预设)> 模板内置公式
- [x] 1.21 公式语法校验 API:POST /api/workpapers/{id}/validate-formula(校验语法+预览结果)

### 数据层测试

- [x] 1.22 test_e1_prefill_no_overwrite.py:验证 B22=SUM 合计公式不被覆盖(P0 级)
- [x] 1.23 test_e1_formula_types.py:10 种公式类型各 2 用例(含 LEDGER/AUX/LEDGER_DETAIL/COUNT_LEDGER/NOTE)
- [x] 1.24 test_e1_consistency_gate.py:3 条 CFS 勾稽规则 + 容差边界测试
- [x] 1.25 test_user_formulas_override.py:用户自定义公式覆盖预设公式不冲突

---

## Sprint 2 UI 层(~12.5 天)

### F1 场景裁剪 + 审计导航图

- [x] 2.1 Alembic 迁移:projects 表新增 scenario VARCHAR(20) + has_foreign_currency BOOLEAN
- [x] 2.2 chain_orchestrator._step_generate_workpapers 按 scenario 裁剪 template_files 列表
- [x] 2.3 useUniverSheetNav.ts 新增 scenarioFilter 参数(A 类 9 sheet 过滤)
- [x] 2.4 新建 WorkpaperAuditNav.vue 主框架(空骨架,左侧导航最顶部,默认展开可折叠)
- [x] 2.4a 5 项认定卡片(A 存在/B 完整性/C 权利义务/D 准确性/E 列报)+ 每项程序数 badge
- [x] 2.4b 风险评估摘要(从 B23-2/B51-3/C3 取固有风险/控制风险/综合应对)
- [x] 2.4c 程序执行进度流程图 SVG(5 段节点+颜色联动,与 LifecycleView 同款手绘)
- [x] 2.4d 关键风险提示(LLM 基于 E1-1 异常检测)+ 底稿间关系图(简化 SVG)
- [x] 2.5 WorkpaperEditor.vue 集成 WorkpaperAuditNav(左侧导航最顶部,默认展开可折叠)

### F1 组件选型分流 + 全屏

- [x] 2.6 新建 ProcedureControlPanel.vue(通用总控台面板,接受 wpCode+procedureSheetName 参数)
- [x] 2.7 WorkpaperEditor.vue 新增 B/C/D/E 类弹窗入口按钮(左侧导航 sheet 列表下方)
- [x] 2.8 B 类检查清单弹窗骨架(el-form + 逐项 verified + 结论 + 签字区)
- [x] 2.9 D 类盘点弹窗骨架(el-form + items 表格 + 双人签字 + 附件区)
- [x] 2.10 E1 类截止测试弹窗骨架(el-table 数据驱动 + 逐笔核对标记)
- [x] 2.11 E2 类人工检查弹窗骨架(el-table 手工录入 + 结论)
- [x] 2.12 全屏模式:A 类 Univer useFullscreen + B/C/D/E 类 el-dialog fullscreen + sticky footer + ESC 两步退出 + 返回时触发 prefill 重执行刷新 Univer 受影响 sheet

### F3 程序完成状态

- [x] 2.13 新建 useProcedureStatus.ts composable(三档计算 + eventBus 订阅)
- [x] 2.14 ProcedureControlPanel.vue 集成完成状态(每行 el-tag + progress bar 三色)
- [x] 2.15 WorkpaperAuditNav.vue 集成程序进度流程图(5 段节点颜色联动)

### F5 前置状态 + 复核联动(L1-L5 双向溯源)

- [x] 2.16 新建 usePrerequisiteStatus.ts composable(查询 B23-2/C3/B51-3 完成状态)
- [x] 2.17 WorkpaperEditor.vue 顶部前置状态横幅(前置未完成时显示警告)
- [x] 2.18 WorkpaperEditor.vue 右上角复核状态 badge(L1/L2/L3/L4/L5 五层 + 专委会/IT/税务)
- [x] 2.19 cross_wp_ref 超链接渲染(E1A 底稿索引号列 → router.push 跳转)
- [x] 2.20 复核模板反向跳转:A21-1~A25-1 复核表行 → 跳转 E1 sheet/cell + 高亮目标
- [x] 2.21 ReviewRecord schema 扩展:source_wp + target_wp + target_sheet + target_cell + review_layer
- [x] 2.22 LLM 复核问题一键生成:合伙人打开 A23-1 时 wp_ai_service 基于 E1 数据生成问题清单
- [x] 2.23 复核回复辅助:审计助理收到问题后 LLM 基于底稿+序时账草拟回复

### F6 附件 + 批注 + 签字 + LLM 按钮

- [x] 2.24 新建 ItemAnnotation.vue(逐项批注组件,存 parsed_data.items[N].annotations[])
- [x] 2.25 新建 ItemAttachment.vue(逐项附件组件,object_type='workpaper_item')
- [x] 2.26 B/D/E 类弹窗集成 ItemAnnotation + ItemAttachment
- [x] 2.27 签字功能集成:D 类盘点弹窗双人签字(审计员+出纳)接入 signature_service
- [x] 2.28 签字功能集成:B 类检查清单单人签字(审计员)接入 signature_service
- [x] 2.29 签字状态联动 procedure_status:签字完成自动触发 E1A 程序状态变 reviewed
- [x] 2.30 每个 sheet/弹窗结论区旁增加"✨ AI 审计说明"按钮 → 调 wp_ai_service → AiContentConfirmDialog
- [x] 2.31 每个弹窗顶部显示审计上下文(认定 + 风险等级 + E1A 程序编号)

### F4 sheet 过滤规则

- [x] 2.32 chain_orchestrator 生成时按规则过滤 sheet(修订前/双附注/双 E1-3/数字货币)
- [x] 2.33 数据刷新:eventBus 订阅 6 种事件 + 工具栏"🔄 刷新取数"按钮触发 prefill 重执行

### F2.3 手动公式编辑器前端

- [x] 2.34 公式管理弹窗扩展(FormulaManagerDialog 已有):新增"用户自定义公式"Tab + 蓝/绿背景区分
- [x] 2.35 cell 右键菜单新增"编辑公式"入口 + 实时预览结果 + 语法校验提示
- [x] 2.36 已修改的预设公式 cell 旁显示"↺ 恢复"按钮 → 恢复到 prefill_formula_mapping.json 原始预设
- [x] 2.37 E1-1 双区显隐:has_foreign_currency=false 时通过 Univer Facade API 隐藏上区 R7-R21
- [x] 2.38 useProcedureStatus 完成判定加附件+签字联动:F3.2 三档晋级条件全部满足才能 filled
- [x] 2.39 ProcedureControlPanel 程序分类列改 el-checkbox-group(常规★/备选/IPO 应对)+ change 事件触发 chain refresh(F1.8)
- [x] 2.40 procedure_categories 数组持久化到 wp.parsed_data + 联动 LinkageBus(勾选"IPO 应对"自动加载 F4)
- [x] 2.41 B51-3 conclusion="高"自动触发 E26A 加载(LinkageBus 监听 + toast 提示)+ overlap_reference 类型显示"相关底稿已涵盖"提示

### F1+F2+F3 前端单测(vitest)

- [x] 2.42 useProcedureStatus.spec.ts:三档晋级条件(filled/reviewed/approved)各 3 用例 + eventBus 订阅刷新
- [x] 2.43 useUniverSheetNav 双区显隐.spec.ts:has_foreign_currency 切换 → setRowVisible 调用断言
- [x] 2.44 FormulaManagerDialog 公式恢复.spec.ts:覆盖预设 → 点恢复按钮 → 回到原始预设(state 三态切换)

---

## Sprint 3 E2E(~3 天)

- [x] 3.1 Playwright E2E:普通项目打开 E1 → 验证 22 sheet + 审计导航图首屏
- [x] 3.2 Playwright E2E:一键填充 → E1-2 数据行有值 + E1-1 合计自动汇总
- [x] 3.3 Playwright E2E:E1A 程序完成状态三色 + 前置状态横幅
- [x] 3.4 Playwright E2E:"✨ AI 审计说明"按钮 → LLM 生成 → 确认填入
- [x] 3.5 Playwright E2E:全屏弹窗 + ESC 两步退出 + 返回刷新
- [x] 3.6 Playwright E2E:复核状态 badge + A21-1 → E1 跳转
- [x] 3.7 Playwright E2E:E1-1 双区显隐(has_foreign_currency 切换)
- [x] 3.8 Playwright E2E:公式恢复预设(覆盖→点"↺ 恢复"→回到原始)
- [x] 3.9 Playwright E2E:程序分类勾选驱动(勾选"IPO 应对"→ E26A 显示)
- [x] 3.10 真实数据验证:陕西华氏项目 E1 端到端(prefill + CFS 勾稽 + 复核 badge)
- [x] 3.11 复盘:跨章节一致性核验 + TD 回写 + 工时实测 vs 估算对比

---

## UAT 验收清单(对应 requirements §四)

| # | 验收项 | 对应需求 | 预期结果 |
|---|-------|---------|---------|
| 1 | 普通项目打开 E1 看到 sheet 数 | F1.2+F4.1 | 22 sheet(Univer 9 + 弹窗按钮 13) |
| 2 | 审计导航图首屏显示 | F1.4 | 5 认定卡片 + 风险摘要 + 进度流程图 |
| 3 | E1A 程序分类勾选"舞弊应对" | F1.2 | E26A + E1-26~E1-32 弹窗按钮出现 |
| 4 | 一键填充 E1-2 + E1-1 | F2.2 | 明细表数据行从 TB 取数 → Univer 公式自动汇总 |
| 5 | E1A 完成状态三色 progress | F3.1 | filled/reviewed/approved 三色区分 |
| 6 | 点击 E1A R38"A1-1"跳转 | F5.1 | 跳转 A1-1;A1 显示反向引用 badge |
| 7 | 前置状态横幅 | F5.6 | B23-2 未完成时显示"⚠ 前置未满足" |
| 8 | "✨ AI 审计说明"按钮 | F6.3 | LLM 生成审计说明草稿 → 确认后填入 R41 |
| 9 | E1-1 vs CFS 勾稽 | F6.1 | 偏差超容差时 ConsistencyGate 报错 |
| 10 | 全屏弹窗 | F1.5 | el-dialog fullscreen + sticky footer + ESC 两步退出 |
| 11 | 附件未上传阻止完成 | F6.2 | E1-7 盘点无附件时 E1A R22 不能标 completed |
| 12 | 复核状态 badge | F5.5 | E1 右上角显示 L1✅/L2⏳/L3❌ |
| 13 | A21-1 复核表跳转 E1 | F5.7 | 复核表行点击 → 跳转 E1 sheet/cell + 高亮 |
| 14 | LLM 复核问题一键生成 | F5.8 | A23-1 打开时 LLM 生成"建议关注问题清单" |
| 15 | D 类盘点双人签字 | F6.4 | 审计员+出纳两人签字后弹窗变只读 + E1A R22 进 reviewed |
| 16 | E1-1 双区显隐 | F1.7 | has_foreign_currency=false 时上区 R7-R21 隐藏 |
| 17 | 公式恢复预设 | F2.3 | 已修改的预设公式点"↺ 恢复"按钮 → 回到原始预设 |
| 18 | 程序分类勾选驱动 | F1.8 | E1A 勾选"IPO 应对"→ E26A + E1-26~E1-32 自动显示 |
| 19 | B51-3 自动触发 E26A | D14 | B51-3 标"高"→ 自动加载 F4 + toast 提示 |

---

## 已知缺口与技术债

| TD | 描述 | 对应需求 | 优先级 |
|----|------|---------|-------|
| TD-1 | D-N 全循环推广(88 个底稿)| F1 全方向 | P1 |
| TD-2 | scenario + has_foreign_currency 需 Project 创建向导收集 | F1 | P1 |
| TD-3 | 全模板库扫描 `(修订前)`/`(示例)`/`(提示)` 类 sheet | F4 | P2 |
| TD-4 | procedure_status JSONB schema 校验 | F3 | P2 |
| TD-5 | scenarioFilter 与 13 类分组优先级 | F1 | P2 |
| TD-6 | conclusion_cell metadata 错位修正 | F3 | P1 |
| TD-7 | E1-3 多银行账户自动展开 prefill | F2 | P1 |
| TD-8 | E26A 与 E1A 共享 audit objective 重复 | F1 | P3 |
| TD-9 | prefill 不覆盖公式 cell 逻辑(P0 级)| F2 | P0 |
| TD-10 | prefill 第二条 sheet 名修正 | F2 | P2 |
