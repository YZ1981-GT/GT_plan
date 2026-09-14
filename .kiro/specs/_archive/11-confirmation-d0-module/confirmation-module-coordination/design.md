# Design Document

## Overview

函证模块横切协同设计——为已建的 9 张 D0 表（D0-1~D0-8 + D0-4b）抽取统一的协同层：函证主数据 SSOT、状态机、统一枚举、共享 UI Kit、跨表导航、D0-1 分发。不新增业务底稿，不重写组件，只统一其共享基础。

## Architecture

```
函证子系统数据流（confirm_index 为全局主键）

         ┌─────────────── D0-1 函证结果汇总（SSOT 主数据台账）───────────────┐
         │  confirm_index / subject / entity_name / book_amount /             │
         │  confirm_method / reply_method / reply_status / reply_amount /     │
         │  is_consistent / confirmation_status                               │
         └───────────────────────────────────────────────────────────────────┘
              ▲ 写入(发函前)            │ 只读引用 by confirm_index ▼
        D0-2 核实被函证单位      ┌──────┴───────┬──────────┬──────────┬─────────┐
              │                 ▼              ▼          ▼          ▼         ▼
        D0-3 跟函过程      D0-4 差异调节   D0-5 替代   D0-6 替代  D0-7 可靠性  D0-8 舞弊评价
        (跟函中)          (有差异)        (未回函)    (未回函)   (电子回函)   (综合→B50)
                               │
                          D0-4b 差异检查（穿透 D0-4 单公司深挖）

共享层（ConfirmationKit / confirmation_dicts / 状态机 / 导航条）被 9 组件统一引用

后端：
- system_dicts.confirmation_dicts 命名空间（统一枚举）
- 函证主数据：以 D0-1 sheet 数据为 SSOT；其他表经 cross_wp_references 按 confirm_index 解析
- confirmation_status 字段随各表事件流转（EventBus：WORKPAPER_SAVED → 更新状态）

前端：
- frontend/src/components/workpaper/confirmation/kit/  （共享 UI Kit）
  ├── ConfirmationDashboard.vue   通用看板（slot 化指标）
  ├── ConfirmationToolbar.vue     通用工具栏
  ├── ConfirmationStatusBadge.vue 状态徽章（绿/橙/红）
  ├── ConfirmationNavBar.vue      本笔函证相关底稿导航条
  ├── useConfirmationMaster.ts    按 confirm_index 取主数据（SSOT 引用）
  ├── useConfirmationStatus.ts    状态读写/流转
  └── confirmationTheme.ts        统一配色/金额格式/网格美化常量
```

## Components and Interfaces

### useConfirmationMaster.ts（新共享 composable）
```ts
interface ConfirmationMaster {
  confirm_index: string; subject: string; entity_name: string
  book_amount: number | null; confirm_method: string; reply_method: string
  reply_status: string; reply_amount: number | null; is_consistent: string
  confirmation_status: string
}
useConfirmationMaster(wpId) => {
  getByIndex(confirm_index)   // 从 D0-1 SSOT 解析（cross_wp_references）
  listAll()                   // 全项目函证主数据
  upsert(master)              // D0-1/D0-2 写入
  // 下游表只读：getByIndex 派生，不持久化副本
}
```

### useConfirmationStatus.ts（新共享 composable）
```ts
type ConfirmationStatus =
  '未核实'|'已核实'|'已发函'|'跟函中'|'已回函'|'未回函'
  |'待可靠性验证'|'相符'|'有差异'|'替代程序中'|'替代完成'|'存在舞弊迹象'
useConfirmationStatus() => {
  statusOf(confirm_index)         // 当前状态
  transition(confirm_index, evt)  // 事件驱动流转
  distribution()                  // computed: 各状态计数（D0-1 看板用）
  stalled()                       // 停滞预警（已发函久未回/有差异久未调）
}
```

### ConfirmationStatusBadge.vue（新共享组件）
- Props: `{ status }`；按 confirmationTheme 配色映射（绿/橙/红 三档）

### ConfirmationNavBar.vue（新共享组件，需求 5）
- Props: `{ confirmIndex, currentSheet }`
- 渲染导航条：D0-2|D0-1|D0-3|D0-7|D0-4|D0-4b|D0-5/6|D0-8，按状态点亮，点击跳转并定位行
- 各组件在 detail/选中行时挂载

### confirmationTheme.ts（新共享常量）
```ts
export const STATUS_COLORS = { ok: '#67C23A' /*绿*/, warn: '#E6A23C' /*橙*/, danger: '#F56C6C' /*红*/ }
export const AMOUNT_FORMAT = { align: 'right', thousands: true, decimals: 2, unit: '元' }
export const GRID_BEAUTY = { groupHeaderPalette: [...5色], freezeFirstCol: true, zebra: true, dimEmpty: true }
export const AUTO_FETCH_MARK = { class: 'gt-auto-fetched', tip: '自动取数（来自上游底稿）' }
```

### D0-1 分发（需求 6，补充到 D0-1 spec 实现）
```ts
// D0-1 工具栏"分发到下游"
distributeDownstream() => {
  差异≠0 → upsert D0-4 rows
  未回函 & 科目=合同负债 → upsert D0-5 companies
  未回函 & 科目=应收 → upsert D0-6 companies
  电子回函 → upsert D0-7 rows
  标记已分发状态（避免重复）
}
```

## Data Models

### ConfirmationMaster（见上，SSOT 字段）
### ConfirmationStatus（12 状态枚举，见上）
### confirmation_dicts（统一枚举命名空间，见 requirements 需求 3）

## Correctness Properties

### Property 1: 主数据单源不漂移
同一 confirm_index 的主数据字段 SHALL 仅由 D0-1 SSOT 持有；下游表 getByIndex 派生，不持久化副本；主数据更新后下游读到最新值。
**Validates: Requirements 1.2, 1.4, 1.5**

### Property 2: 状态机流转一致
confirmation_status SHALL 单源（D0-1）；各表事件驱动流转；distribution() 计数 == 各状态实际函证数之和。
**Validates: Requirements 2.2, 2.3, 2.4**

### Property 3: 枚举单点复用
同义枚举（如 yes_no_na）在多表 SHALL 引用同一 dictKey，无重复定义。
**Validates: Requirements 3.2, 3.3**

### Property 4: 配色与格式一致
9 组件状态徽章/金额格式/网格美化 SHALL 来自 confirmationTheme 同一常量源。
**Validates: Requirements 4.2, 4.3, 4.4**

### Property 5: 导航条状态正确
导航条入口点亮 SHALL 与该 confirm_index 实际状态一致；跳转定位到正确行。
**Validates: Requirements 5.2, 5.3**

### Property 6: 分发与拉取等价去重
D0-1 分发到下游 SHALL 与下游"从 D0-1 带入"结果一致（同去重规则），不产生重复行。
**Validates: Requirements 6.2, 6.4**

### Property 7: 单表独立可用
主数据/状态/导航缺失（仅单表存在）时 SHALL 降级独立可用，不阻塞、不报错。
**Validates: Requirements 1.6, 7.3**

### Property 8: 交互能力基线一致
所有函证表格/子表/清单 SHALL 一致具备 编辑/右键/选区/复制/粘贴/求和/增删/导入导出/键盘导航；只读时一致守卫（编辑禁用、复制求和导出可用）；无表缺失任一基线能力。
**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**

## Error Handling

- 主数据解析失败（D0-1 不存在）→ 下游降级手工录入
- 状态流转事件丢失 → 状态保持上一态，看板提示停滞
- 导航目标表不存在 → 入口置灰
- 分发重复 → 按 confirm_index 去重跳过

## Testing Strategy

- **useConfirmationMaster 单测**：SSOT 解析 + upsert + 下游只读派生 + 缺失降级（P1/P7）
- **useConfirmationStatus 单测**：流转 + distribution 计数 + 停滞预警（P2）
- **confirmation_dicts 测试**：统一枚举注册 + 同义复用无重复（P3）
- **ConfirmationKit 视觉测试**：状态徽章/金额/网格美化一致（P4）
- **导航条 spec**：状态点亮 + 跳转定位（P5）
- **分发 spec**：分发=拉取等价 + 去重（P6）
- **回归**：9 组件接入共享层后零回归（render-config 冒烟）
- **Playwright**：D0-1 分发→下游出现行→各表导航条跳转→主数据一处改多处同步→状态机流转看板更新
