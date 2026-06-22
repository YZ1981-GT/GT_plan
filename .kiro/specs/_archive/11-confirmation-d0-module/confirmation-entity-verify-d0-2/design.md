# Design Document

## Overview

为 D0-2 核实被函证单位信息创建专用组件 `GtConfirmationEntityVerify`（componentType=`confirmation-entity-verify`），按 5 个生命周期阶段重构约 38 列宽表为 master-detail + 条件字段 + 企查查自动核对 + 质量红线 + 双视图。与 D0-1（confirmation-summary）高度同构，最大化复用其已建基础能力，仅实现 D0-2 特有的"单位信息核对 + 两轮发函"逻辑。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-entity-verify → GtConfirmationEntityVerify
后端 _WP_CODE_OVERRIDE / render-config 对 D0-2 sheet 标 componentType=confirmation-entity-verify

GtConfirmationEntityVerify.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── 视图切换：列表视图(默认) / 完整表格视图（localStorage 记忆）
├── EntityVerifyDashboard.vue   核实进度看板（核实完成率/退回率/警示）
├── 【列表视图】EntityVerifyMaster.vue + EntityVerifyDetail.vue（5 阶段分区 + 条件 + tooltip + 行状态徽章/红旗清单）
├── EntityVerifyFraudPanel.vue  反舞弊红旗清单（detail 顶部逐条 + master 行状态徽章，需求 12）
├── 【完整表格视图】复用 D0-1 的 ConfirmationFullGrid（泛化为通用宽表网格）或同构 EntityVerifyFullGrid
│
├── useEntityVerifyData.ts      数据核心（rows/dirty/CRUD/buildPayload/进度指标）
├── useFraudFlagDetect.ts       反舞弊检测：行内一致性自动比对 + 跨行红旗（地址聚类/号段相邻/撞员工名单/同寄件人）
├── useConfirmationAutoFetch.ts 复用 + 扩展：企查查地址拉取 + 一致性自动判定
├── useCellSelection.ts         复用：选区/复制/粘贴/求和
├── CellContextMenu.vue         复用：右键菜单
├── useDictStore                复用：枚举
├── useExcelIO                  复用：导入/导出
├── entityVerifyEnums.ts        枚举 dictKey 映射
└── entityVerifyTypes.ts        类型定义

保存链路（复用既有）：emit('save', payload) → GtWpRenderer.onSave → WorkpaperEditor → POST /save
  payload = { rows, progress_config, _format: 'entity-verify-v1' }

后端：system_dicts._DICTS 增 confirmation_send_result（送抵/退回）；其余枚举复用 D0-1
编制指引：backend/data/wp_guidance/D0-2.json 补准则程序文本（核实程序/检查支持性文件/确认联系人身份/电子平台）
```

## Components and Interfaces

### GtConfirmationEntityVerify.vue（新，主组件）
- Props: `{ wpId, sheetName, schema, htmlData, readonly }`；Emit: `save / open-formula / restore`
- 旧格式（无 `_format`）降级 GtGridSheet 只读

### EntityVerifyMaster.vue（新）
- Props: `{ rows, readonly, expandedRowId }`；Emit: `expand / add / delete / context-menu`
- el-table 关键 7 列 + 多选 + 工具栏（新增/删除/保存/导入/导出）

### EntityVerifyDetail.vue（新）
- Props: `{ row, readonly, enumOptions }`；Emit: `field-change`
- 5 阶段 el-collapse；条件 v-show（is_second_send / first_result / address_match）
- 字段旁 el-tooltip 注入说明 1-5（按字段映射 FIELD_HINTS）

### EntityVerifyDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 核实完成率（已核实一致/总数）、退回率、橙/红警示计数、舞弊红旗计数（需求 12/14）

### EntityVerifyFraudPanel.vue（新，需求 12）
- Props: `{ row, fraudFlags }`；detail 顶部展示该笔函证命中的红旗清单（逐条），master 行展示状态徽章（一致/存疑/舞弊红旗 → 绿/橙/红）
- 红旗来源：行内一致性比对（需求 13）+ 跨行检测（需求 14）合并去重

### useEntityVerifyData.ts（新 composable）
```ts
interface EntityVerifyRow {
  id: string; confirm_index: string          // 函证索引（关联 D0-1）
  // ① 单位信息核对
  entity_name: string; method: string; address: string; postcode: string
  contact: string; phone: string; email_fax: string
  qcc_address: string; address_match: string   // 发函地址与企查查是否一致
  mismatch_desc: string; verify_method: string; verify_doc_index: string
  mismatch_reasonable: string; remark: string
  // ② 回函核对
  reply_method: string; is_original: string; direct_received: string
  reply_address: string; reply_sender: string; reply_phone: string
  addr_consistent: string; sender_consistent: string; phone_consistent: string
  reply_mismatch_desc: string; reply_evidence_index: string
  // ③ 跟函 + 第一次发函结果
  followup_index: string; first_result: string    // 送抵/退回
  return_reason: string; reason_reasonable: string; is_second_send: string
  // ④ 第二次发函单位信息
  s2_address: string; s2_postcode: string; s2_contact: string
  s2_phone: string; s2_fax: string; s2_info_consistent: string
  // ⑤ 第二次发函结果
  second_result: string
}

useEntityVerifyData(htmlData, readonly) => {
  rows, addRow, deleteRow, updateField, importRows
  progressMetrics (computed: 核实完成率/退回率/警示)
  dirty, buildPayload
}
```

### useConfirmationAutoFetch.ts（复用 + 扩展）
- 新增 `fetchQccAddress(entityName)`：调函证中心企查查接口取注册地址
- `autoJudgeAddressMatch(address, qccAddress)`：地址比对自动判一致/不一致

### useFraudFlagDetect.ts（新 composable，需求 13/14）
```ts
// 行内一致性自动比对（6+ "是否一致"字段）
interface ConsistencyRule { result: keyof EntityVerifyRow; a: keyof EntityVerifyRow; b: keyof EntityVerifyRow; mode: 'addr' | 'exact' }
const CONSISTENCY_RULES: ConsistencyRule[] = [
  { result: 'address_match',     a: 'address',       b: 'qcc_address',  mode: 'addr'  },
  { result: 'addr_consistent',   a: 'reply_address', b: 'address',      mode: 'addr'  },
  { result: 'sender_consistent', a: 'reply_sender',  b: 'contact',      mode: 'exact' },
  { result: 'phone_consistent',  a: 'reply_phone',   b: 'phone',        mode: 'exact' },
  { result: 's2_info_consistent',a: 's2_address',    b: 'address',      mode: 'addr'  },
]
useFraudFlagDetect(rows, options) => {
  autoJudgeRow(row)        // 行内：规范化(去空格/全半角/标点)+相似度→各 *_consistent 初判；未覆盖才写；依赖空则留空
  detectCrossRow()         // 跨行：地址聚类/电话号段相邻/联系人撞员工名单/同一回函寄件人
  fraudFlagsByRow          // computed: Map<rowId, FraudFlag[]>
  rowStatus(rowId)         // computed: 'consistent' | 'suspect' | 'fraud'
  thresholds               // { addrSimilarity, phoneAdjacentRange } 可配置，内置默认
  runScreening()           // 一键运行舞弊筛查（手动触发）
}
// 规范化与相似度复用既有工具（如有）；无则本地 levenshtein/包含判定，不引新依赖
```

## Data Models

### EntityVerifyRow（约 38 字段，见上）

### ProgressMetrics
```ts
{
  total: number                 // 函证总数
  verified_consistent: number   // 已核实且一致
  verify_rate: number           // 核实完成率
  returned: number              // 第一次退回数
  return_rate: number           // 退回率
  warn_count: number            // 橙色警示数（地址存疑）
  danger_count: number          // 红色警示数（原因不合理/二次退回）
}
```

### 字段提示映射（FIELD_HINTS，说明 1-5 落位）
```ts
{
  qcc_address / verify_method: 说明1（核实信息要求 + 多途径核实）
  return_reason:              说明2（退回核实程序：询问/检查）
  reason_reasonable:          说明3（不合理→舞弊应对，警示级）
  second_result:              说明4（二次跟进，仍退回→调查+舞弊）
  reply_method:               说明5（传真/电邮验可靠性+寄回原件）
  method(电子函证):            顶部审计说明（电子函证无需核对发函地址）
}
```

### 保存载荷（`_format: 'entity-verify-v1'`）
`{ "_format": "entity-verify-v1", "rows": [EntityVerifyRow...], "progress_config": {...} }`

### RowStatus / FraudFlag（需求 12/13/14）
```ts
type RowStatus = 'consistent' | 'suspect' | 'fraud'   // 绿/橙/红
interface FraudFlag {
  type: 'addr_mismatch' | 'addr_cluster' | 'phone_adjacent' | 'contact_hits_employee' | 'same_reply_sender'
  level: 'warn' | 'danger'      // 橙/红
  message: string               // 红旗说明（逐条展示）
  relatedRowIds?: string[]      // 跨行红旗关联的其他行
}
// 字段比对覆盖标记：row 上各 *_consistent 字段被用户改动后置 `${field}_overridden: true`，不再自动改
```

### 单位主数据共享（需求 15）
同一 `confirm_index` 的单位字段（entity_name/address/contact/phone/method）在 D0-1 与 D0-2 间共享：
- 通过既有跨底稿引用机制（cross_wp_references / address_registry wp 域）按索引解析，**不存两份副本**
- D0-2 核实更新后，D0-1 按 confirm_index 解析获取最新值
- 仅存在一侧时各自独立可用（共享为增强非强依赖）

## Correctness Properties

### Property 1: 条件字段不丢数据
当 `is_second_send` 从"是"改为"否"时，第二次发函字段（④⑤）SHALL 保留值但不显示；改回"是"时恢复。不清除已填数据。
**Validates: Requirements 2.1, 2.2**

### Property 2: 地址一致性自动判定可覆盖
当 address 与 qcc_address 都有值时 address_match 自动判定；用户手工覆盖后 SHALL 标 `_overridden`，不再自动改。
**Validates: Requirements 3.2**

### Property 3: 进度指标实时性
rows 增删/修改后 progressMetrics 同一 tick 重算（核实完成率/退回率/警示数）。
**Validates: Requirements 5.4**

### Property 4: 旧格式兼容
htmlData 无 `_format` 时降级 GtGridSheet 只读，不崩。
**Validates: Requirements 11.2**

### Property 5: 只读不可编辑
readonly=true 时所有控件不可编辑，工具栏增删/保存/导入禁用。
**Validates: Requirements 1.3, 7.5**

### Property 6: 函证索引关联一致
D0-2 行的 confirm_index 与 D0-1 函证行索引同源；同一索引在两底稿表示同一笔函证。
**Validates: Requirements 9.1, 9.2**

### Property 7: 一致性自动比对可覆盖且不强判
各 `*_consistent` 字段在两依赖字段都有值时自动初判（一致/不一致）；任一依赖为空时留空不强判；用户覆盖后标 `_overridden`，重算不再改写。
**Validates: Requirements 13.1, 13.3, 13.4**

### Property 8: 跨行红旗对称且实时
地址聚类/号段相邻/同一回函寄件人等跨行红旗 SHALL 标注到所有相关行（对称），行增删改后重算；员工名单不可取时撞名检测跳过不报错。
**Validates: Requirements 14.1, 14.2, 14.3, 14.5**

### Property 9: 行状态由比对+红旗派生
master 行状态徽章（一致/存疑/舞弊红旗）SHALL 由行内不一致项 + 命中红旗派生：有 danger 红旗→fraud(红)，有 warn/不一致→suspect(橙)，否则 consistent(绿)。
**Validates: Requirements 12.1, 12.2**

### Property 10: 单位主数据单源
同一 confirm_index 的单位字段在 D0-1/D0-2 间通过引用共享，不持久化两份副本；一侧缺失时另一侧仍独立可用。
**Validates: Requirements 15.1, 15.3, 15.4**

## Error Handling

- 企查查接口失败 → qcc_address 降级手填，address_match 手判
- 枚举字典缺失 → 降级 el-input
- 导入缺列行 → 预览标错跳过，不中断
- 保存失败 → console.warn + dirty 保留
- 旧格式 → 降级只读网格

## Testing Strategy

- **useEntityVerifyData 单测**：CRUD + progressMetrics 实时 + buildPayload 格式 + 条件字段保留(P1)
- **自动核对 spec**：企查查地址拉取 + 一致性自动判定 + 用户覆盖(P2)
- **条件字段 spec**：is_second_send / first_result / address_match 切换显隐
- **字段提示 spec**：说明 1-5 tooltip 正确落到对应字段
- **质量警示 spec**：地址存疑/原因不合理/二次退回 三级警示触发
- **一致性自动比对单测**：5 条规则规范化+相似度初判 / 依赖空留空 / 用户覆盖标 _overridden 不被重算改写（P7）
- **跨行舞弊检测单测**：地址聚类/号段相邻/同一回函寄件人对称标注 + 增删改重算 + 撞员工名单可取时命中、不可取时跳过（P8）
- **行状态派生单测**：danger→fraud / warn→suspect / 无→consistent（P9）
- **单位主数据共享 spec**：同 confirm_index 单源解析、D0-2 更新后 D0-1 取最新、单侧独立可用（P10）
- **后端枚举测试**：confirmation_send_result 返回完整
- **回归**：render-config 冒烟零回归
- **Playwright**：D0-2 新增核实行 → 填企查查比对 → 一致性自动比对+跨行红旗触发标红 → 退回→二次发函条件展开 → 警示 → 保存 → 重开持久化 + 跳 D0-1
