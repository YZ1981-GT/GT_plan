# S 类底稿联动、裁剪与组件接线 — 任务清单

## P0 — 裁剪执行链 + 孤儿接线

### Phase 0: 前置确认

- [ ] 0. 前置确认：① `procedure-trim-generation-delegation-chain` spec 是否已入库——如已入库检查 chain_orchestrator 的 SELECT/project_flags 变化,据实调整 Task 2 基线;② `Project.business_category` String(10) 是否够存 `"refinancing"`(11字符),真库 `SELECT MAX(LENGTH(business_category)) FROM projects` 确认;③ `formula-fetch-followup-defect-closure` 的 Task 4.2 后端门禁是否入库

### Phase 1: applicable_when 生成链（R-P0-1）

- [ ] 1. `match_workpapers` 追加 `applicable_when` 第四匹配路径：遍历 dict 全部键（`_KEY_FLAG_PREFIX` 映射 business_category→biz_ / industry→ind_），键间 OR。补测试覆盖 hit + miss + industry 键各一例
- [ ] 2. `chain_orchestrator._step_generate_workpapers` SELECT 增加 `Project.business_category`，构建 `biz_ipo/biz_listed/biz_neeq/biz_refinancing` flag。现读确认 `Project.industry` 是否存在（如存在同步构建 ind_ flag，如不存在则框架可遍历但 flag 恒空——不构成延迟风险）
- [ ] 3. 端到端验证：IPO 项目 → S34 子码在生成列表；普通年审 → S34 不出现

### Phase 2: 前端裁剪 + 统一工具（R-P0-2, R-P0-3）

- [ ] 4. 新建 `src/utils/ipoProjectUtils.ts`：`IPO_BIZ_KEYWORDS` + `isIpoProject(biz, cats?)`，vitest 覆盖关键词匹配、大小写、空串、allowedCats
- [ ] 5. `useAProgramData.ts` `isNotApplicable` 增加 dict 分支调用 `isIpoProject`
- [ ] 6. `wp_classification_service.py` 新增 `_WP_APPLICABLE_WHEN`（从 `wp_account_mapping.json` 预加载 wp_code→applicable_when 映射）。🔴 **bundle 父码聚合**：S32/S33/S34/S35 父码 applicable_when=None，须从子码向上取 business_category 并集。`wp_render_config.py` render-config 端点附加 `applicable_when` 到响应
- [ ] 7. GtWpRenderer 层新增 `isWpNotApplicable` computed：render-config 响应取 `applicable_when`，比对项目 business_category，不匹配渲染覆盖层。vitest 覆盖 bundle + 通用两种路径
- [ ] 8. `useD4FormulaEngine.ts` 删 `isIpoGroupVisible` 改调 `isIpoProject(biz, [...IPO_BIZ_KEYWORDS, 'fraud_risk'])`（保留 fraud_risk 检测）；同步修改 `useD4FormulaEngine.spec.ts`/`.pbt.spec.ts` 中 8 个 isIpoGroupVisible 测试用例 + `useD4CrossSheet.ts` 的 import；`useF2SpecialFormData.ts` 保留三级瀑布 wrapper `isF2IpoProject`，内部首级调 `isIpoProject`
- [ ] 9. grep 全仓确认无其他分散 IPO/business_category 判定遗漏，收敛到 ≤2 个来源

### Phase 3: s-checklist 孤儿组件接线（R-P0-4）

- [ ] 10. openpyxl 读 S1/S8/S9/S10/S17 五个模板确认 5 个内部 sheet 精确 tab 名；12 个组件 props/字段绑定与模板对账；确认 `composables/useSSpecialImportExport.ts` 端点存在且工作正常（S1/S17 组件 import 了它）
- [ ] 11. 修复 s-checklist 组件字段偏移（如有），附 openpyxl 列结构证据
- [ ] 12. `wp_code_overrides.json` 组 A：7 个 wp_code componentType 改专属类型
- [ ] 13. `wp_code_overrides.json` 组 B：5 个内部 sheet 添加 `"{wp_code}-{tab_name}"` override
- [ ] 14. `htmlRendererRegistry.ts` + `specialized.ts` 追加 12 个类型 + 12 个 Entry
- [ ] 15. `htmlRendererRegistry.spec.ts` / contract test 补新类型覆盖
- [ ] 16. 浏览器实测 S1/S8/S9/S10/S17 子 sheet 专属组件渲染

### Phase 4: S 段侧边栏路由（R-P0-5）

- [ ] 17. `resolveProcedureSheetKey.ts` 追加 S 段：S20/S17/S16(→e1a)/S15/S14/S13/S12/S11(→e1a)/S10/**S8**/S1。验证 S11/S16 不被 startsWith('S1') 误捕获；S8 在 S1 之前（避免 S8 被 S1 误捕获不适用但 S8 不以 S1 开头所以无此风险,仅确认 S8 路由到 s8a）
- [ ] 18. `resolveProcedureSheetKey.spec.ts` 补 S 段测试（每前缀一例 + S11→e1a/S16→e1a 优先级 + S8→s8a + S2/S9/S21→e1a）
- [ ] 19. 浏览器验证 S 底稿侧边栏状态正确

## P1 — 关联联动

### Phase 5: linked_workpapers + resolver（R-P1-1, R-P1-2）

- [ ] 20. `wp_account_mapping.json` 为 S20/S15/S17/S6/S33-5 补 `linked_workpapers`。grep `linked_workpapers` 确认 D~N 循环的前端消费组件路径（GtWpPreparationHeader / WorkpaperSidePanel 等），确保 S 类也走同一展示路径（如按 componentType 过滤需扩展白名单）。跑 `test_wp_account_mapping_single_source` 无回归
- [ ] 21. 新建 `_s_linkage.py`：`s6_related_party_summary` / `s33_5_revenue_cost_check` / `s14_estimate_related_data`，各 1 例单测。**同时确认对应 render-schema YAML 中是否有 auto_data_source 声明**——如无须同步补声明（否则 resolver 注册了无人调用）；如走通用程序表中控台取数机制则确认注入路径与 S4~S10 已有 resolver 一致
- [ ] 22. 验证既有 11 个 S 相关 resolver 签名与 `resolve_auto_data_source` 调用协议一致（签名 `async (db, project_id, year, **kwargs) -> dict[str, Any]`）。注意总 resolver 数已从 ~35 增长到 ~50+（formula-fetch-followup 新增了多个循环模块），注册机制不变；前端底稿面板展示关联链接
- [ ] 23. 端到端：S20 程序表取数区域展示 D4 营收审定数

### Phase 6: S34 公式引擎完整化（R-P1-3）

- [ ] 24. openpyxl 读 12 张 hasSubTable 子表模板，记录列结构和公式位置
- [ ] 25. `useS34FormulaEngine.ts` 补 S34-2/S34-3/S34-4/S34-8/S34-9 公式定义
- [ ] 26. 补 S34-11/S34-18/S34-20 公式定义
- [ ] 27. 补 S34-25/S34-30/S34-34 公式定义；验证 S34-16 试点无回归
- [ ] 28. vitest 每张子表 ≥1 例公式计算；浏览器实测 12 张子表自动计算

### Phase 7: 跨引用展示（R-P1-4）

- [ ] 29. `useS34CrossRef.ts` / `useS35CrossRef.ts` 外部 chip hover 调 `cycle_audited_amounts` 展示审定额
- [ ] 30. `GtS34SubCheckTable.vue` chip 增加 `el-popover` 只读展示；vitest mock 验证

## P2 — 风险导向 + 委派

### Phase 8: 风险映射（R-P2-1, R-P2-2）

- [ ]* 31. `SELECT DISTINCT account_or_cycle FROM risk_assessments LIMIT 50` 确认真库值域
- [ ]* 32. `s34_checklist_service.py` 新增 `_load_risk_indicators`；mock 单测
- [ ]* 33. `get_s34_checklist` 叠加风险指示器 + recommended 状态；Overview 组件展示
- [ ]* 34. 浏览器实测：高舞弊风险项目 S32 标「建议适用」

### Phase 9: 委派展示（R-P2-3）

- [ ]* 35. 4 个 bundle tab 标签增加 assigned_to 展示（JOIN 路径 G9 确认）；vitest 验证

### Phase 10: 回归 + 收口

- [ ] 36. 全量 pytest 相关测试无回归（wp_account_mapping / render_config / resolver）；含 `s34-ipo-bundle/__tests__`、`s32-fraud-bundle/__tests__`、`s35-refinance-bundle/__tests__` 下既有测试
- [ ] 37. 全量 vitest workpaper 目录无回归；含 `s-checklist/__tests__`（如有）、`s33-ann14-bundle/__tests__`
- [ ] 38. 浏览器走查 S3/S12/S14/S15/S20/S21 已有专属组件不受影响
