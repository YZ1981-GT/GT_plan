# Implementation Plan: B23 业务层面控制底稿重做

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "基础", "dependsOn": [], "tasks": ["1.1", "1.2"] },
    { "wave": 1, "name": "前端数据层", "dependsOn": [0], "tasks": ["2.1", "2.2"] },
    { "wave": 2, "name": "后端渲染", "dependsOn": [0], "tasks": ["3.1"] },
    { "wave": 3, "name": "组件重建", "dependsOn": [1, 2], "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "4.12"] },
    { "wave": 4, "name": "测试", "dependsOn": [3], "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "6.1", "6.2"] },
    { "wave": 5, "name": "收尾", "dependsOn": [4], "tasks": ["7.1", "7.2"] }
  ]
}
```

## Overview

将 B23 从"空壳 template + 通用 8 流程模型"重做为对齐致同 14 循环源模板的聚合专属组件。实现顺序：单一配置源与后端白名单（W0）→ 前端数据层重构（W1）→ 后端渲染策略（W2）→ 组件 template 重建（W3）→ 测试（W4）→ 收尾与实测（W5）。带 `*` 的为可选任务（按项目偏好同样做完）。

## Tasks

## 1. 基础配置与后端白名单（Wave 0）

- [x] 1.1 创建单一循环配置源 `composables/b23CycleConfig.ts`
  - 定义 `B23CycleDef` 接口与 `B23_CYCLES`（14 循环 + B23-15 + B23-XX-5），字段：code/wpCode/name/subjectCycle/cTests/substantiveCycles/defaultSubProcesses/isSpecial
  - cTests/substantiveCycles 对齐后端 `wp_dependency_service.CYCLE_DEPENDENCIES`
  - 导出派生 helper：`attachmentEntries()`（供附件 Tab）、`cycleByCode(code)`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 12.4_

- [x] 1.2 后端 `checklist_responses.py` B23- 白名单补充新枚举值
  - 追加：认定值（存在/发生/完整性/准确性/计价分摊/权利义务/列报）、预防性/检查性、控制类型一级二级值、有效/无效、重大缺陷/重要缺陷/一般缺陷、缺乏控制/设计不合理/未执行
  - 保留既有 B23- 结论值；文本值走 remark 不校验
  - _Requirements: 11.4, 13.4_

## 2. 前端数据层（Wave 1）

- [x] 2.1 重构 `composables/useB23ProcessControl.ts` 为 14 循环模型
  - `generateItemId` 重签为 `(cycleCode, type, ctrlIndex?, sampleIndex?, field?)`，前缀 `B23-{code}-`（§4.5 方案）
  - 扩展 `B23ControlPoint` 为 21 字段（§4.1）；新增 `B23WalkthroughTest`（§4.2）/`B23ControlTest`（§4.3）/`B23Deficiency`（§4.4）读写方法
  - 控制点 CRUD / 穿行测试 CRUD / 控制测试 CRUD / 缺陷 CRUD（各自独立 item_id 命名空间，wt-* 与 ct-* 不互相覆盖）
  - 适用性：`applicableCycles(cycles)`（幂等）+ 不适用不计入进度分母
  - 纯函数（导出供 PBT）：`suggestCycleConclusion`、`eligibleForTest(cp)`、`suggestControlTest(cp,wt)`、`deficiencyHints(cp,wt)`、`applicableCycles`
  - `dashboardStats`（各循环适用性/控制点/关键控制/穿行完成/控制测试完成/缺陷汇总）、`linkageInfo`（B50 影响/C 类/D~N 建议）
  - 保留 EventBus 发布 `process:control-concluded`、`process:walkthrough-completed`；控制测试结论或缺陷变化发布控制风险事件供 B50
  - WCGW 引用可从控制点追溯到子流程描述
  - _Requirements: 2.5, 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.4, 6.5, 7.1, 7.2, 7.4, 7.5, 7.6, 9.1, 9.2, 9.3, 9.4, 10.1, 13.4_

- [x] 2.2 创建 `composables/useB23ImportExport.ts`
  - `exportToExcel`：按 Business_Cycle 分 sheet 导出控制矩阵/穿行测试/控制测试/缺陷汇总（ExcelJS，不引入新依赖）
  - `importFromExcel`：校验列结构，匹配数据回写对应循环，不匹配列跳过并提示
  - rows↔model 纯函数拆出供往返 PBT
  - _Requirements: 14.1, 14.2, 14.3, 14.4_

## 3. 后端渲染策略（Wave 2）

- [x] 3.1 后端渲染：注册 b23-process-control 为整册专属自加载组件（对齐 b22a，非新增冗余 render 策略）
  - 实际实现：加入 `DEDICATED_COMPONENT_TYPES` + `_ONLYOFFICE_HTML_WHITELIST`（防被改写为 onlyoffice-sheet），前端自加载 checklist-responses；更新契约计数 88；扩展白名单后同步修正既有 PBT 的 VALID/INVALID 结论集
  - component_type=`b23-process-control`，在 `__init__.py` 的 DISPATCH dict 注册（防 onlyoffice 兜底）
  - 输出 `project_context`（client_name/audit_year/bs_date）+ `responses_snapshot`（全部 B23- 数据）+ `cycle_dependencies`（派生自 CYCLE_DEPENDENCIES）
  - 确认 WORKPAPER_SAVED 事件处理器按新 cycle-keyed 数据正确提取 cycle（B23_CYCLES wpCode→name 映射），复用 `b23_walkthrough_for_cycle`/`b23_walkthrough_progress` resolver
  - _Requirements: 7.3, 10.3, 13.1, 13.3, 13.5_

## 4. 组件 template 重建（Wave 3）

- [x] 4.1 重建 `GtB23ProcessControl.vue` 顶部区 + Status_Dashboard + Entity_Level_Context
  - 移除硬编码错位的 `B23_ATTACHMENT_CODES`，改从 `b23CycleConfig` 派生
  - 顶部：审计目标 el-alert + 编制进度（不适用不计入分母）+ 工具栏（全部展开/收起、导入导出 dropdown、复核）
  - 仪表盘：循环维度汇总卡（颜色编码复用 PROCESS_CONCLUSION_COLOR_MAP）
  - Entity_Level_Context 只读面板（B22A 五要素+整体结论，EventBus `control:conclusion-changed` 更新，未完成灰提示，控制环境无效红警告）+ ref_chip → B22A
  - selfLoad 合并 render-config responses_snapshot 到 allResponses
  - _Requirements: 1.2, 1.5, 3.1, 3.8, 6.1, 6.2, 6.3, 6.4, 6.6, 10.3, 12.4_

- [x] 4.2 审计链路流程图 + 循环目录（GtBArchitectureTree）
  - CSS 轻量节点+连线（B22A→B23→B50→D~N），点击 GtIndexChip 跳转，可折叠
  - `GtBArchitectureTree` 循环目录，展示全部循环（>14 也全显），点击切换，显示完成/适用性状态
  - _Requirements: 16.1, 16.2, 16.3_

- [x] 4.3 循环列表/卡片 + 适用性开关
  - `B23_CYCLES.map` 渲染卡片：名称+编码 chip+适用性开关+完成进度+结论标签（左 4px 色带）
  - 适用性切换即时保存 + 更新仪表盘计数/进度；手动覆盖持久化
  - 不适用循环灰色标签 + 排除出进度分母
  - _Requirements: 1.2, 3.2, 9.1, 9.2, 9.3, 9.4, 12.4_

- [x] 4.4 循环详情：整体控制汇总区（选中后展开，默认隐藏）
  - 受影响交易账户/子流程（从 defaultSubProcesses 预置可增删）/部门人员/职责分离/特别风险控制/应用系统/服务机构
  - WHILE 未选中循环 → 详情面板隐藏
  - _Requirements: 3.3, 3.4, 2.5_

- [x] 4.5 控制矩阵 21 列表格
  - 21 列（§4.1），枚举字段点选录入，长文本 autosize+AI 辅助按钮；13px、横向滚动、前几列 fixed、超 15 列加 ⚙ 列设置
  - 新增/删除控制点（预置需确认）；WCGW 可追溯到子流程描述
  - `控制设计是否有效=否` → 提示识别缺陷
  - _Requirements: 3.5, 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 4.6 穿行测试记录区（验设计，独立）
  - 字段：测试方法(多选)/访谈对象/实施程序/检查证据/结果/是否按设计执行(枚举)/识别缺陷
  - `未按设计执行` → 提示识别缺陷 + 对实质性程序影响
  - _Requirements: 5.1, 5.3, 5.4, 5.5_

- [x] 4.7 控制测试记录区（验运行，独立，走 C 类）
  - 字段：拟测试控制/风险判断/测试性质/测试时间/测试范围/运行有效性结论(枚举)/偏差/对实质性程序影响
  - 仅关键控制且穿行按设计执行才可进入
  - _Requirements: 5.2, 5.3, 5.5, 7.1_

- [x] 4.8 缺陷汇总区（A14-4 分级）
  - 缺陷描述/缺陷类型(枚举:缺乏控制/设计不合理/未执行)/严重程度(枚举:重大/重要/一般)/影响
  - 设计无效或穿行未按设计执行 → 缺陷汇总显示提示（即使缺陷数为 0）；A14-4 ref_chip
  - 汇总各循环缺陷数到仪表盘
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 4.9 Linkage_Panel + Cross_Ref_Chips
  - 关键控制∧穿行按设计执行 → "建议执行控制测试"提示关联 C 类
  - 控制不可依赖 → "建议扩大实质性程序范围"提示（仅建议不自动执行）
  - 依 cycle_dependencies 呈现 C 类/D~N 映射 + ref_chip
  - Cross_Ref_Chips（B22A-4/B18/B14/B50-4/A14-4）GtIndexChip canonical `wp:X`；C26/a27-1 恒显；跳转失败允许点击并报错
  - _Requirements: 7.1, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 4.10 现场经理复核区 + 只读 + Amendment + 复核对话 + 版本链
  - 签字（canReview 前置，pendingItems 清单）+ 已复核绿色横幅 + emit completed
  - 只读态禁用全部录入控件无例外；修订态可编辑
  - `GtWpReviewDialogHost` + `useWorkpaperReviewProvide` 真实复核对话；`useWorkpaperVersionToolbar` + `scheduleAutoSnapshot`
  - Amendment 弹窗（原因非空校验）
  - _Requirements: 3.6, 3.7, 9.x, 11.1, 11.2, 11.3, 11.4_

- [x] 4.11 附件 Tab 修复（P0 止血）
  - `B23_CYCLES.map` 生成 14+2 入口，标签同源（修复 B23-9/10/11 等错位 + 补 B23-1~8）
  - 单入口解析 try/catch，部分失败仅提示不阻塞
  - _Requirements: 12.1, 12.2, 12.3, 12.5_

- [x] 4.12 导入导出接线 + AI 辅助 + 编制提示
  - 工具栏导入导出 dropdown 接 `useB23ImportExport`；导入冲突/格式错误提示
  - section 标题栏 AI 辅助按钮（走 `/api/workpapers/{wp_id}/ai/generate-text`，context 值全转 str）
  - 编制提示 details（CAS1231/内控评价方法论）
  - _Requirements: 3.5, 14.1, 14.3_

## 5. 前端测试（Wave 4）

- [x] 5.1 PBT Property 1（持久化往返）+ Property 10（item_id 前缀完整）
  - fast-check：随机数据 save→load 等价；generateItemId 全组合唯一非空 B23- 前缀
  - _Requirements: 10.1, 10.5, 13.4_

- [x]* 5.2 PBT Property 2（导入导出往返）
  - export→import 等价（rows↔model 纯函数）
  - _Requirements: 14.1, 14.2, 14.4_

- [x]* 5.3 PBT Property 4/5/6（关键控制驱动测试 / 穿行前置 / 缺陷触发）
  - eligibleForTest / suggestControlTest / deficiencyHints 纯函数
  - _Requirements: 4.3, 4.4, 5.3, 5.4, 6.4, 7.1_

- [x]* 5.4 PBT Property 7（适用性幂等）+ Property 8（穿行/控制测试结论分离）
  - applicableCycles 幂等；wt-*/ct-* 写入互不覆盖
  - _Requirements: 5.5, 9.2_

- [x]* 5.5 单测：14+2 循环渲染 + 默认隐藏详情面板 + 点选录入 + 只读禁写(Property 9) + 复核前置 + Amendment
  - 只读 spy PUT 次数=0
  - _Requirements: 3.3, 3.4, 11.1, 9.2_

- [x]* 5.6 契约测试：registry 含 b23-process-control；wp_code_overrides 映射正确；附件配置≡ B23_CYCLES（Property 3）
  - _Requirements: 2.3, 12.4, 13.1, 13.2_

## 6. 后端测试（Wave 4）

- [x]* 6.1 后端 PBT：B23- item_id round-trip（Property 1 后端侧）
  - _Requirements: 10.1, 10.5_

- [x]* 6.2 后端 PBT：B23- 白名单校验（合法 200 / 非法 422）
  - _Requirements: 11.4_

## 7. 收尾（Wave 5）

- [x] 7.1 Checkpoint：get_diagnostics 全清 + Vite transform 200 + 后端 AST OK + 全部测试通过
  - _Requirements: 全部_

- [ ]* 7.2 Playwright 实测：打开 B23 → 渲染主体（非仅附件）→ 选循环展开 → 控制矩阵录入 → 穿行/控制测试 → 缺陷 → 保存 round-trip 落库 → 刷新回显 → 0 console error
  - 已实例化项目上验证附件标签正确 + B23-1~8 入口齐全
  - _Requirements: 1.2, 3.1, 10.5, 12.1, 12.2_

## Notes

- **铁律**：仅用 fs_write/str_replace 改 Vue（禁 PowerShell 破坏 UTF-8）；改后端后需重启后端（run_uvicorn 带 --reload，改 .py 自动重载，改 wp_code_overrides.json/config 需手动触发）。
- **禁止臆造披露/审计内容**：控制点骨架/子流程仅取源模板 `BCD类底稿md/{cycle}/B23-N...业务层面控制底稿模板库.md`。
- **迁移零风险**：wp_code_overrides 已符合目标（B23→b23-process-control，子底稿全 skip）；旧 `B23-P{n}-*` 键作孤儿保留不自动迁移；`B23-review-sign`/`B23-amend-{k}-reason` 模型无关跨重做保持。
- **假绿教训**：本 spec 起因即旧 spec 任务标 [x] 但 template 空壳 → 任务标记不能假绿，UI 类改动必须 Playwright 实测（7.2），composable 纯逻辑测试不等于渲染验证。
- **验证门槛**：get_diagnostics 全清 + 全树 Vite transform 200（模板结构/中文引号 bug 只 Vite overlay 暴露）+ 后端 AST OK。
