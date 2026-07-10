# Design Document

> C2~C15 业务循环控制测试组件翻新

## Overview

翻新 `c-control-test` 组件内部结构，以匹配致同 2025 修订版真实模板：目录导航 + 控制测试汇总表（控制清单）+ 逐控制测试子页（Cx-1-X，抽样）+ Cx-2 偏差评价决策树（6 步 IF 驱动）+ 样本规模自动建议 + 缺陷联动 A14 + B23/B50 联动。14 循环共用组件，wpCode 区分。沿用 componentType `c-control-test` 与 `C{n}-` 前缀 checklist_responses（兼容历史数据）。本设计取代已归档 `c-control-test-component` 的卡片模型。

## Architecture

```mermaid
graph TD
  A[GtWpRenderer] -->|c-control-test| B[GtCControlTest 翻新]
  B --> D[useCControlTestData 持久化 兼容 C{n}-]
  B --> DIR[目录导航]
  B --> SUM[控制测试汇总表 15列 下拉]
  B --> SUB[Cx-1-X 控制测试子页 抽样]
  B --> DEV[Cx-2 偏差评价决策树 6步]
  SUM --> SS[useSampleSizeEngine 样本规模建议]
  DEV --> DT[useDeviationDecisionTree 6步 IF]
  DT -->|缺陷| A14CHIP[GtIndexChip → A14]
  B --> BUS[EventBus control:test-concluded → B50]
  B --> API[GET/PUT checklist-responses]
```

## Components and Interfaces

### GtCControlTest.vue（翻新）

```typescript
interface Props { wpId: string; projectId: string; wpCode: string; year: number; readonly?: boolean }
// sheetName v-if 分发：directory / summary / ctrl-{m} / deviation
```

### 控制点汇总行

```typescript
interface ControlSummaryRow {
  index: number; subProcess: string; controlId: string; controlName: string; description: string
  affectedItems: string; assertion: string; attribute: string; frequency: string; relatedRisk: string
  testMethod: string; sampleSize: number; hasDeviation: 'Y'|'N'|null; remediation: string
  defect: string; indexRef: string
}
```

### useSampleSizeEngine（纯函数）

```typescript
// 样本规模区间表：控制频率 × 运行总次数 → 最小样本规模
export function suggestSampleSize(frequency: string, totalCount: number): { min: number; max: number }
```

### useDeviationDecisionTree（纯函数，Cx-2 六步）

```typescript
export interface DeviationInput {
  isDeviation: 'Y'|'N'|null                    // 步骤一
  nature: '系统性偏差'|'人为偏差'|'随机性偏差'|null  // 步骤二
  randomResponse: '扩大样本量'|'直接认定为偏差'|null  // 步骤三
  expandedFoundNew: 'Y'|'N'|null                // 步骤四
  designDeficiency: 'Y'|'N'|null                // 步骤六
}
export interface DecisionResult { nextStep: string; conclusion: string; goToA14: boolean }
// 复刻源模板 IF 链：
// 步骤一=否 → 步骤六；=是 → 步骤二
// 步骤二=随机 → 步骤三；=系统性/人为 → 缺陷(步骤五)
// 步骤三=直接认定 → 步骤五；=扩大 → 步骤四
// 步骤四=否 → 控制有效；=是 → 该控制无效(步骤五)
// 步骤五 → 进入 A14
// 步骤六=否 → 不构成偏差或缺陷；=是 → 设计缺陷(回步骤五)
export function evaluateDeviation(i: DeviationInput): DecisionResult
```

### 后端

- wp_code_overrides.json：保持 C2~C15 → `c-control-test`
- htmlRendererRegistry.ts：保持 `c-control-test`（组件内部翻新，注册不变）
- 复用 GET/PUT checklist-responses；EventBus 复用 `control:test-concluded`
- 后端 conclusion 白名单：新增偏差性质值（系统性偏差/人为偏差/随机性偏差/扩大样本量/直接认定为偏差）

## Data Models

### item_id 命名（前缀 C{n}-，兼容历史）

| 区域 | item_id 模式 |
|------|-------------|
| 汇总控制行 | `C{n}-sum-{m}-{field}` |
| 控制测试子页 | `C{n}-ctrl-{m}-{field}` / `-sample-{s}-result` |
| 样本规模 | `C{n}-ctrl-{m}-sample-size` |
| 偏差决策树 | `C{n}-dev-{m}-step{k}` |
| 评价结论 | `C{n}-dev-{m}-conclusion` |
| 循环结论 | `C{n}-cycle-conclusion` |

### 14 循环映射

沿用已归档设计的 CYCLE_CONFIG（wpCode → 循环名/B23 流程/目标 D~N 循环）。

### 数据流

```
点击 C2~C15 → GtCControlTest(c-control-test)
  onMounted: 提取 n → GET checklist-responses(C{n}-) → 还原汇总/子页/决策树
  汇总表: 下拉选择即时保存；样本规模 → useSampleSizeEngine 建议
  子页: 抽样测试 → 偏差数回填汇总「是否识别偏差」
  Cx-2: 6 步选择 → useDeviationDecisionTree 推导 nextStep/conclusion/goToA14
  缺陷 → GtIndexChip → A14；整体缺陷 → EventBus control:test-concluded → B50
```

## Correctness Properties

*属性是系统在所有合法执行路径下都应保持为真的行为声明。*

### Property 1: 注册与数据兼容

*For any* C2~C15，componentType 保持 `c-control-test`；已有 `C{n}-` 前缀数据加载后字段值不变（向后兼容）。

**Validates: Requirements 1.1, 1.2, 1.5**

### Property 2: 样本规模建议单调性

*For any* 控制频率与运行总次数，suggestSampleSize 返回的区间应满足 min ≤ max，且运行总次数越大建议样本规模不减（单调不降）。

**Validates: Requirements 3.1, 3.2**

### Property 3: 偏差决策树推导确定性

*For any* DeviationInput，evaluateDeviation 应确定性复刻源模板 IF 链：步骤一=否→步骤六；系统性/人为→缺陷；随机+扩大+无新偏差→控制有效；随机+扩大+有新偏差→控制无效；步骤五→goToA14=true。

**Validates: Requirements 5.1, 5.2**

### Property 4: 缺陷联动 A14

*For any* 决策路径，goToA14=true 当且仅当推导进入步骤五（评价控制缺陷）。

**Validates: Requirements 5.3**

### Property 5: 偏差回填一致性

*For any* 控制测试子页样本集合，汇总表「是否识别出偏差」应等于该子页存在偏差样本（deviation 计数 > 0）。

**Validates: Requirements 4.3**

### Property 6: EventBus 发布正确性

*For any* 循环结论变更，仅在新旧值不同时发布 `control:test-concluded`，载荷含 wpCode/cycleName/结论/缺陷摘要。

**Validates: Requirements 7.2, 7.3**

### Property 7: 持久化往返与 readonly

*For any* C{n}- 前缀数据，PUT 后 GET 一致；readonly=true 时禁止编辑与行增删。

**Validates: Requirements 8.1, 8.3, 8.4**

## Error Handling

| 场景 | 处理 |
|------|------|
| GET/PUT 失败 | 提示，保留本地编辑 |
| 决策树步骤缺失 | 后续步骤置灰待录入，不报错 |
| 样本规模无匹配区间 | 提示手工确定样本量 |
| 新增控制点未命名 | 拒绝创建，提示命名 |
| A14/B23/B50 不存在 | GtIndexChip 灰态 |
| 历史数据字段缺失 | 按默认空值渲染，不崩溃 |

## Testing Strategy

### 属性测试（PBT）

fast-check（前端）+ hypothesis（后端往返），每 property ≥100 次。Tag：`Feature: c-control-test-refresh, Property {N}: {title}`。

| Property | 生成器 |
|----------|--------|
| P1 兼容 | 固定 C2~C15 + hypothesis 历史 C{n}- 数据 |
| P2 样本规模 | `fc.record({frequency: fc.constantFrom(...), totalCount: fc.nat()})` |
| P3 决策树 | `fc.record({isDeviation, nature, randomResponse, expandedFoundNew, designDeficiency})` 全组合 |
| P4 A14 联动 | 同 P3 断言 goToA14 |
| P5 偏差回填 | `fc.array(fc.record({result: fc.constantFrom('有效','偏差','不适用')}))` |
| P6 EventBus | 随机新旧结论 |
| P7 往返/readonly | hypothesis C{n}- item_id + `fc.boolean()` |

### 单元/集成测试

- componentType 保持注册；历史数据兼容加载
- 汇总表 15 列 + 下拉 + 动态增删
- 样本规模建议
- Cx-1-X 子页抽样 + 偏差回填
- Cx-2 六步决策树全路径 + A14 联动
- EventBus 发布 B50
- 只读禁编辑；Playwright 实测

## 交互增强设计（点选/附件OCR/一键联动回写）

### 点选控件映射

| 字段 | 控件 |
|------|------|
| 认定/控制属性/控制频率/测试方法/是否偏差 | 命名区域来源 el-select / 多选 tag |
| 样本结果（有效/偏差/不适用）| 点选按钮组（不手打）|
| Cx-2 六步每步选项 | el-radio 点选，选后自动推进 + 显示指引 |
| 长文本（控制描述/偏差描述/评价说明）| autosize textarea + AI 按钮 |

### 附件上传 + OCR（Cx-1-X 样本行）

```typescript
// 逐笔样本 📎 上传 → OCR → 确认弹窗 merge；抽样过程引用 IDEA 底稿（GtIndexChip）
async function onUploadSample(file, row) {
  const ocr = await api.post('/d4/contract-ocr', form)
  await ElMessageBox.confirm(preview(ocr)); mergeSample(row, ocr)
}
```

### 一键联动与回写

```
汇总表控制点索引号 → 一键跳 Cx-1-X 子页
Cx-1-X 样本有偏差 → 回填汇总「是否识别偏差=是」→ 联动 Cx-2 偏差评价入口
Cx-2 决策树 → 控制缺陷 → GtIndexChip 跳 A14 + 带摘要 + 回填汇总「识别出的缺陷」
B23 一键引用本循环控制点 → 生成汇总表行
循环整体结论变更 → EventBus control:test-concluded → B50
```

### 新增 Correctness Properties（补充）

- **P8 点选值合法性**：*For any* 命名下拉/点选字段，保存值属于命名区域选项枚举。**Validates: Requirements 9.1, 9.2**
- **P9 决策树点选推进确定性**：*For any* Cx-2 每步点选，nextStep 指引与 evaluateDeviation 推导一致。**Validates: Requirements 9.3, 5.2**
- **P10 偏差回填一致性**：*For any* 子页样本偏差状态，汇总表「是否识别偏差」与之一致；缺陷推导时回填「识别出的缺陷」。**Validates: Requirements 11.2, 11.3**
- **P11 B23 引用生成一致性**：*For any* B23 控制点集合，一键引用生成的汇总行数量与控制点数量一致，控制编号/目标正确映射。**Validates: Requirements 11.4**
