# Design Document — B23 业务层面控制底稿重做

## Overview

本设计将 B23 从"composable 已实现但 template 空壳 + 通用 8 流程模型"重做为**对齐致同 14 循环源模板的聚合专属组件**，让已有 composable 逻辑真正被渲染，控制矩阵承载完整审计字段，并打通 B22A→B23→B50→C 类→D~N 联动。

设计遵循需求锁定的关键决策：
- **唯一渲染模型 = 聚合组件模式**（子底稿一律 `skip`，无分别渲染、无混合）。
- **14 循环 + 2（B23-15 信息处理控制 / B23-XX-5 职责分离）由单一配置源驱动**。
- **穿行测试（验设计）与控制测试（验运行）分层持久化**。
- **缺陷按 A14-4 分级**，联动只"建议"不自动执行。

### 1.1 设计原则

- **配置驱动**：循环编码/名称/科目循环/子底稿编码/附件标签/联动映射全部来自 `b23CycleConfig` 单一常量，消除标签错位类 bug（Req12）。
- **最小重建，最大复用**：`useB23FormData`（加载/保存/防抖/flush）、`useB23Review`（复核/只读/修订）原样复用；`useB23ProcessControl` 从 8 流程模型重构为 14 循环模型 + 21 列控制矩阵 + 穿行/控制测试分层；`GtB23ProcessControl.vue` 的 `<template>` 从空壳重建为完整 UI。
- **持久化零迁移风险**：沿用 `checklist_responses` + `B23-` 前缀 + 后端既有白名单；因旧 template 为空、用户从未通过 UI 产生过 `B23-P{n}-ctrl-*` 数据，采用 cycle-keyed 新 item_id 方案，旧键作为孤儿保留不自动迁移（§7）。

## Architecture

```
GtB23ProcessControl.vue（聚合专属组件，唯一渲染入口）
├── 顶部：审计目标 alert + 编制进度 + 工具栏（展开/收起·导入导出·复核）
├── Status_Dashboard（仪表盘）
│    ├── 各循环适用性/控制点数/关键控制数/穿行完成度/控制测试完成度/缺陷数汇总
│    └── Entity_Level_Context（B22A 只读上下文，EventBus control:conclusion-changed）
├── 审计链路流程图（B22A→B23→B50→D~N，CSS 轻量）
├── 循环目录（GtBArchitectureTree，展示全部循环，>14 也全显）
├── 循环列表/卡片（14+2，编码 chip / 适用性标签 / 完成进度）
│    └── [选中后展开] Cycle_Detail
│         ├── 整体控制汇总（受影响交易账户/子流程/部门人员/职责分离/特别风险/应用系统/服务机构）
│         ├── 控制矩阵（21 列，点选优先，WCGW 可追溯）
│         ├── 穿行测试记录（验设计，独立）
│         ├── 控制测试记录（验运行，独立，走 C 类）
│         ├── 缺陷汇总（A14-4 分级）
│         ├── Linkage_Panel（B50 影响 / C 类映射 / D~N 范围建议）
│         └── Cross_Ref_Chips（B22A-4/B18/B14/B50-4/A14-4/C26/a27-1）
├── 现场经理复核区（签字/待完成清单/只读横幅/Amendment）
└── 附件底稿 Tab（14+2 入口，标签同源 §3，部分加载失败可继续）

Composable 分层：
- useB23FormData（复用）：allResponses / loadAll / saveImmediate / saveDebouncedText / flushPendingSave / getField / setFieldImmediate
- useB23ProcessControl（重构）：14 循环卡片 / 21 列控制矩阵 CRUD / 穿行·控制测试分层 / 缺陷 / 适用性 / 循环结论建议 / dashboardStats / linkageInfo / EventBus
- useB23Review（复用）：isReviewed / isReadonly / canReview / pendingItems / doReview / startAmendment
- useB23ImportExport（新增）：ExcelJS 按循环分 sheet 导入导出
- b23CycleConfig（新增常量）：单一配置源

后端：
- wp_render_strategies：新增 _b23_process_control.py（RENDERER_DISPATCH 注册 b23-process-control），注入 project_context + responses_snapshot
- 复用 resolver：b23_walkthrough_for_cycle / b23_walkthrough_progress
- 复用 WORKPAPER_SAVED 事件写 field_overrides scope=b23_walkthrough:{cycle}
- checklist_responses.py 白名单已含 B23-（补充新枚举值，§6）
```

## 3. 单一循环配置源 `b23CycleConfig`

位置：`audit-platform/frontend/src/components/workpaper/composables/b23CycleConfig.ts`

```ts
export interface B23CycleDef {
  code: string          // 循环 item_id 键，如 'c1'..'c15'、'cxx5'
  wpCode: string        // 子底稿编码，如 'B23-1'..'B23-15'、'B23-XX-5'
  name: string          // 循环名称：销售循环 / 货币资金 ...
  subjectCycle: string  // 对应科目循环字母：D/E/F...Q（B23-15/XX-5 为空）
  cTests: string[]      // 关联 C 类控制测试 wp_code（对齐 CYCLE_DEPENDENCIES）
  substantiveCycles: string[] // 关联 D~N 实质性程序循环
  defaultSubProcesses: string[] // 预置子流程骨架（源模板，供点选套用，可增删）
  isSpecial?: boolean   // B23-15/XX-5 标记（非标准 14 循环）
}

export const B23_CYCLES: readonly B23CycleDef[] = [
  { code: 'c1',  wpCode: 'B23-1',  name: '销售循环',   subjectCycle: 'D', cTests: ['C2'],  substantiveCycles: ['D'], defaultSubProcesses: ['客户信用管理','销售订单','组织发货','开具发票','收款与对账','坏账准备计提'] },
  { code: 'c2',  wpCode: 'B23-2',  name: '货币资金',   subjectCycle: 'E', cTests: ['C3'],  substantiveCycles: ['E'], defaultSubProcesses: [...] },
  { code: 'c3',  wpCode: 'B23-3',  name: '存货循环',   subjectCycle: 'F', cTests: ['C4'],  substantiveCycles: ['F'], defaultSubProcesses: [...] },
  { code: 'c4',  wpCode: 'B23-4',  name: '投资循环',   subjectCycle: 'G', cTests: [...],   substantiveCycles: ['G'], defaultSubProcesses: [...] },
  { code: 'c5',  wpCode: 'B23-5',  name: '固定资产',   subjectCycle: 'H', ... },
  { code: 'c6',  wpCode: 'B23-6',  name: '在建工程',   subjectCycle: 'H', ... },
  { code: 'c7',  wpCode: 'B23-7',  name: '无形资产',   subjectCycle: 'I', ... },
  { code: 'c8',  wpCode: 'B23-8',  name: '研发循环',   subjectCycle: 'I', ... },
  { code: 'c9',  wpCode: 'B23-9',  name: '职工薪酬',   subjectCycle: 'J', ... },
  { code: 'c10', wpCode: 'B23-10', name: '管理循环',   subjectCycle: 'K', ... },
  { code: 'c11', wpCode: 'B23-11', name: '税金循环',   subjectCycle: 'N', cTests: ['C12'], substantiveCycles: ['N'], ... },
  { code: 'c12', wpCode: 'B23-12', name: '债务循环',   subjectCycle: 'L', ... },
  { code: 'c13', wpCode: 'B23-13', name: '租赁循环',   subjectCycle: 'H', ... },
  { code: 'c14', wpCode: 'B23-14', name: '关联方及交易', subjectCycle: 'Q', ... },
  { code: 'c15', wpCode: 'B23-15', name: '信息处理控制', subjectCycle: '',  cTests: ['C26'], substantiveCycles: [], isSpecial: true },
  { code: 'cxx5',wpCode: 'B23-XX-5', name: '职责分离（通用）', subjectCycle: '', cTests: [], substantiveCycles: [], isSpecial: true },
]
```

**同源保证（Req12.4 / Property P3）**：附件入口 `B23_ATTACHMENT_CODES`、仪表盘循环集合、Linkage_Panel 循环键、目录节点，全部从 `B23_CYCLES` 派生（`.map`）。删除 `GtB23ProcessControl.vue` 中现有硬编码且标签错位的 `B23_ATTACHMENT_CODES` 常量。cTests / substantiveCycles 与后端 `wp_dependency_service.CYCLE_DEPENDENCIES` 对齐（设计阶段以后端为准，配置源作前端展示层）。

## Data Models

### 4.1 控制点（21 列，Req4）

```ts
export interface B23ControlPoint {
  index: number
  subProcess: string          // 子流程
  ctrlNo: string              // 控制编号（如"收入1"）
  ctrlName: string            // 控制名称
  ctrlDesc: string            // 详细控制描述
  affectedItems: string       // 受影响的交易/账户/余额/披露
  assertion: Assertion[]      // 认定（多选枚举：存在/发生/完整性/准确性/计价分摊/权利义务/列报）
  wcgwRef: string             // WCGW 引用（可追溯到流程图，Req4.5）
  wcgwDetail: string          // WCGW 详细记录
  ctrlAttr: string            // 控制属性
  frequency: ControlFrequency | null  // 控制频率（枚举）
  itApp: string               // IT 应用名称
  preventDetect: '预防性' | '检查性' | null  // 枚举
  designEffective: '是' | '否' | null        // 控制设计是否有效
  ctrlTypeL1: string | null   // 控制类型一级（枚举：授权和审批/监督控制/信息处理/实物控制/职责分离/绩效评价）
  ctrlTypeL2: string | null   // 控制类型二级
  executor: string            // 执行人
  executorOrg: string         // 执行人名称或服务机构
  hasDoc: '是' | '否' | null   // 是否有文件记录（枚举）
  isKeyControl: '是' | '否' | null   // 是否为关键控制点（枚举）
  doControlTest: '是' | '否' | null  // 是否执行控制测试（枚举）
}
```

枚举字段（点选录入，Req4.2）：assertion / preventDetect / frequency / ctrlTypeL1 / ctrlTypeL2 / hasDoc / isKeyControl / doControlTest / designEffective。长文本字段用 autosize textarea + AI 辅助（Req3.5）。

### 4.2 穿行测试记录（验设计，独立，Req5）

```ts
export interface B23WalkthroughTest {
  ctrlIndex: number           // 关联控制点
  method: string              // 测试方法（询问/观察/检查文件/重新执行 多选）
  interviewee: string         // 访谈对象
  procedure: string           // 实施的程序
  evidence: string            // 检查的证据
  result: string              // 实施结果
  asDesigned: '是' | '否' | null  // 是否按设计执行（枚举，验设计核心）
  deficiencyFound: string     // 识别出的缺陷
}
```

### 4.3 控制测试记录（验运行，独立，走 C 类，Req5）

```ts
export interface B23ControlTest {
  ctrlIndex: number
  riskJudgment: string        // 控制相关风险判断
  testNature: string          // 测试性质
  testTiming: string          // 测试时间安排
  testScope: string           // 测试范围（样本量）
  operatingEffective: '有效' | '无效' | null  // 运行有效性结论（枚举）
  deviation: string           // 偏差
  substantiveImpact: string   // 对实质性程序的影响
}
```

### 4.4 缺陷记录（A14-4 分级，Req6）

```ts
export interface B23Deficiency {
  index: number
  subProcess: string
  description: string         // 缺陷描述
  deficiencyType: '缺乏控制' | '设计不合理' | '未执行' | null  // 枚举
  severity: '重大缺陷' | '重要缺陷' | '一般缺陷' | null         // A14-4 分级（枚举）
  impact: string              // 对审计计划/实质性程序影响
}
```

### 4.5 item_id 方案（cycle-keyed）

以循环 `code`（§3）为键，前缀 `B23-{code}-`：

| 数据 | item_id | 存储列 |
|------|---------|--------|
| 循环适用性 | `B23-{code}-applicability` | conclusion（Y/N） |
| 循环整体结论 | `B23-{code}-cycle-conclusion` | conclusion |
| 结论覆盖标记/理由 | `B23-{code}-conclusion-override` | conclusion=Y, remark=理由 |
| 控制点数量 | `B23-{code}-ctrl-count` | remark（数字） |
| 控制点字段 | `B23-{code}-ctrl-{m}-{field}` | 枚举→conclusion / 文本→remark / 多选→remark(逗号) |
| 穿行样本数量 | `B23-{code}-wt-{m}-count` | remark |
| 穿行测试字段 | `B23-{code}-wt-{m}-{s}-{field}` | asDesigned→conclusion / 其余→remark |
| 控制测试字段 | `B23-{code}-ct-{m}-{field}` | operatingEffective→conclusion / 其余→remark |
| 缺陷数量 | `B23-{code}-def-count` | remark |
| 缺陷字段 | `B23-{code}-def-{d}-{field}` | deficiencyType/severity→conclusion / 其余→remark |
| 子流程骨架 | `B23-{code}-subproc-{s}-name` | remark |

**穿行/控制测试分离（Property P8）**：`wt-*` 与 `ct-*` 为不同 item_id 命名空间，写入互不覆盖。复核/修订键 `B23-review-sign`、`B23-amend-{k}-reason` 为模型无关，原样保留（`useB23Review` 不改）。

`generateItemId` 从 `(processNum, type)` 重签为 `(cycleCode, type, ctrlIndex?, sampleIndex?, field?)`。

## Components and Interfaces

### 5.1 GtB23ProcessControl.vue（重建 template）

保留现有 script setup 的 props（wpId/projectId/wpCode/year/readonly）/emits（save/completed）/三 composable 初始化 + onMounted loadAll + EventBus 监听 + onBeforeUnmount flush。重建 `<template>`：

1. **顶部**：审计目标 el-alert（了解、评价并测试各业务循环内控设计与执行，CAS1231）+ 编制进度（已完成子视图/总子视图，不适用循环不计入分母 Req9.2）+ 工具栏（全部展开/收起、导入导出 dropdown、复核）。
2. **Status_Dashboard**：循环维度汇总卡（适用性/控制点/关键控制/穿行完成/控制测试完成/缺陷），颜色编码（复用 PROCESS_CONCLUSION_COLOR_MAP）。Entity_Level_Context 只读面板（B22A 五要素 + 整体结论，EventBus 更新，B22A 未完成灰色提示，控制环境无效红色警告）。
3. **审计链路流程图**：CSS 节点+连线（B22A→B23→B50→D~N），点击 GtIndexChip 跳转，可折叠。
4. **循环目录**：`GtBArchitectureTree`，展示全部循环（>14 也全显 Req16.1），点击切换。
5. **循环列表/卡片**：`B23_CYCLES.map`，标题栏=名称+编码 chip+适用性开关+完成进度+循环结论标签（左侧 4px 色带）。
6. **Cycle_Detail（选中后展开，默认隐藏 Req3.3）**：整体控制汇总 → 控制矩阵（21 列，13px，横向滚动，`fixed` 前几列，超 15 列加 ⚙ 列设置）→ 穿行测试 → 控制测试 → 缺陷汇总 → Linkage_Panel → Cross_Ref_Chips。判断/枚举点选，长文本 autosize+AI；section 标题栏右侧放 AI + 复核按钮。
7. **复核区**：签字（canReview 前置，pendingItems 清单）+ 已复核绿色横幅 + Amendment 弹窗（原因非空校验）。
8. **附件 Tab**：`B23_CYCLES.map` 生成 14+2 入口，标签同源（修复错位 + 补 B23-1~8）；部分加载失败仅提示不阻塞（Req12.5）。

### 5.2 只读态（Req11）

`isReadonly` 为真时，全部录入控件 `disabled`，无例外（展开/显示切换类也禁用）；修订（amendment）状态非只读，控件可用。复用 `GtWpReviewDialogHost` + `useWorkpaperReviewProvide` 挂真实复核对话；版本链 `useWorkpaperVersionToolbar` + `scheduleAutoSnapshot`。

## 6. 后端设计

### 6.1 Render 策略

新增 `backend/app/routers/wp_render_strategies/_b23_process_control.py`，component_type=`b23-process-control`，在 `__init__.py` 的 `RENDERER_DISPATCH` 注册（避免被 onlyoffice-sheet 兜底 Req13.3）。输出：
- `project_context`：client_name / audit_year / bs_date。
- `responses_snapshot`：全部 `B23-` 的 checklist_responses（前端 selfLoad 合并）。
- `cycle_dependencies`：从 `wp_dependency_service.CYCLE_DEPENDENCIES` 派生的循环→c_tests/substantive 映射（供 Linkage_Panel 与前端配置源对齐校验）。

### 6.2 白名单补充

`checklist_responses.py` 的 `B23-` 分支已存在；补充新枚举值到白名单：认定值（存在/发生/完整性/准确性/计价分摊/权利义务/列报）、预防性/检查性、控制类型一级二级值、是/否、有效/无效、重大缺陷/重要缺陷/一般缺陷、缺乏控制/设计不合理/未执行、穿行 asDesigned 是/否。文本值走 remark 不校验。

### 6.3 复用

`b23_walkthrough_for_cycle` / `b23_walkthrough_progress` resolver 与 WORKPAPER_SAVED→`field_overrides scope=b23_walkthrough:{cycle}` 事件处理器保留；事件处理器的 cycle 提取需适配新 cycle-keyed 数据（按 B23_CYCLES 映射 wpCode→name）。

## 7. 迁移与兼容

- **wp_code_overrides.json**：已符合目标（B23→b23-process-control，B23-1~15/XX-5→skip），无需改。
- **旧 item_id `B23-P{n}-*`**：旧 8 流程模型键。因旧 template 为空、用户从未通过 UI 产生过控制点数据，视为孤儿，不自动迁移、不删除（保留可读）。新数据一律走 cycle-keyed 键。设计阶段确认：如某项目确有 `B23-P{n}-ctrl-*` 残留，提供一次性 best-effort 映射脚本（P{n}→对应循环 code），但默认不执行，避免误映射。
- **review/amend 键**：`B23-review-sign` / `B23-amend-{k}-reason` 模型无关，`useB23Review` 原样复用，跨重做保持。

## Correctness Properties

### Property 1: 持久化往返不变式
落点：`useB23FormData.saveImmediate/loadAll` + cycle-keyed item_id。随机 ControlPoint/WT/CT/Deficiency → save → load 等价 `load(save(x))==x`。

**Validates: Requirements 10.1, 10.5**

### Property 2: 导入导出往返不变式
落点：`useB23ImportExport.exportToExcel/importFromExcel`（纯函数 rows↔model）。export→import 等价。

**Validates: Requirements 14.1, 14.2, 14.4**

### Property 3: 循环集合与配置一致
落点：单一 `B23_CYCLES`；仪表盘/附件/联动/目录全 `.map` 派生。契约测试：附件标签≡配置 name，无硬编码。

**Validates: Requirements 2.3, 12.4**

### Property 4: 关键控制驱动测试对象
落点：`eligibleForTest(cp)=cp.isKeyControl==='是'`；测试对象集 ⊆ 关键控制集 ⊆ 全集。纯函数 + PBT。

**Validates: Requirements 4.3, 5.3**

### Property 5: 穿行有效是控制测试前置
落点：`suggestControlTest(cp,wt)`：isKeyControl 且 `wt.asDesigned==='是'` → 建议控制测试；`asDesigned==='否'` → 缺陷提示。纯函数 + PBT。

**Validates: Requirements 5.3, 5.4, 7.1**

### Property 6: 缺陷触发一致
落点：`deficiencyHints(cp,wt)`：`designEffective==='否'` 或 `wt.asDesigned==='否'` → 必有缺陷提示（即使缺陷记录数为 0，Req6.4）。PBT。

**Validates: Requirements 4.4, 6.4**

### Property 7: 适用性过滤幂等
落点：`applicableCycles(cycles)`：`filter(filter(x))==filter(x)`；不适用不计入编制进度分母。PBT。

**Validates: Requirements 9.2, 9.3**

### Property 8: 穿行与控制测试结论分离
落点：`wt-*` 与 `ct-*` 独立 item_id 命名空间；写 wt 不改 ct 反之。PBT。

**Validates: Requirements 5.5**

### Property 9: 只读态禁写
落点：`isReadonly` 为真时所有 setter 短路 return，不调 saveImmediate。单测 spy PUT 次数=0。

**Validates: Requirements 11.1**

### Property 10: item_id 前缀完整
落点：`generateItemId` 恒返回非空 `B23-` 前缀键。PBT 全组合枚举唯一且非空。

**Validates: Requirements 10.1, 13.4**

## Error Handling

- **保存失败（Req10.4）**：`useB23FormData.doSave` catch 后 `ElMessage.error('保存失败')` 并保留本地编辑内容不回滚；`canceled`/`ERR_CANCELED` 静默忽略（复用现有实现）。
- **加载失败**：`loadAll` catch → `ElMessage.warning('数据加载失败，可手动填写')`，界面进入可手动填写态而非空白（复用现有实现）。
- **加载超时（Req3.6/3.7）**：数据就绪 10 秒内呈现主体；仅当发生真实超时事件（如请求超时/拒绝）才呈现降级提示（"加载超时，请重试"+ 重试按钮），单纯经过 10 秒但请求仍在途不触发降级。
- **附件入口部分失败（Req12.5）**：`getWpIndex` 或个别附件 wp 解析失败时，仅记录并提示该入口不可用，其余已成功入口正常渲染，不阻塞整体（`try/catch` 包裹单入口解析）。
- **Cross_Ref_Chip 跳转失败（Req8.3）**：点击恒可触发；若目标底稿不存在/未实例化，跳转回调 catch → `ElMessage.error('目标底稿暂不可用')`，不阻止点击。
- **枚举白名单校验（Req11.4/后端）**：非法 B23- 结论值后端返回 422；前端因枚举点选录入不产生非法值，422 时提示并保留本地数据。
- **配置漂移守卫**：`b23CycleConfig` 与后端 `CYCLE_DEPENDENCIES` 不一致时，契约测试失败（CI 拦截），运行时以前端配置源渲染并 console.warn。

## Testing Strategy

- **前端 PBT（fast-check）**：P1–P8/P10 对应纯函数（suggestCycleConclusion / eligibleForTest / suggestControlTest / deficiencyHints / applicableCycles / generateItemId / import-export 往返）。
- **前端单测（vitest）**：14+2 循环渲染、默认隐藏详情面板、点选录入、只读禁写（P9）、复核前置、Amendment、附件标签同源、Cross_Ref_Chip canonical 值。
- **后端 PBT（hypothesis）**：B23- item_id round-trip + 白名单校验（合法 200 / 非法 422）。
- **契约测试**：registry 含 b23-process-control；wp_code_overrides 映射正确；附件配置≡ B23_CYCLES。
- **Playwright 实测**：打开 B23 → 渲染主体（非仅附件）→ 选循环展开 → 控制矩阵录入 → 穿行/控制测试 → 缺陷 → 保存 round-trip 落库 → 刷新回显 → 0 console error。
