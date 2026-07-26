# Requirements Document

## Introduction

H3 投资性房地产底稿与其他循环底稿之间存在三组跨底稿勾稽关系，目前各 composable 已计算好对方数据的聚合值但无 UI 展示、无跨底稿 pull、无双向事件联动。本 spec 补齐这三组跨底稿勾稽面板。

## Requirements

### Requirement 1: H3-6 互转勾稽面板

**User Story:** 作为审计师，我需要在 H3-6 互转审核表看到与 H1/H2 的三方向金额对比，以便确认互转一致。

#### Acceptance Criteria

- H3-6 底部显示勾稽面板，展示 fromH1/toH1/fromH2 三方向对比（H3 vs H1/H2）
- 差异>1元显示 warning tag，差异≤1元显示 success
- GtIndexChip 跳转 H1/H2

### Requirement 2: H3-6 跨底稿数据 pull

**User Story:** 作为系统，我需要从 H1/H2 底稿拉取互转相关数据供 H3-6 勾稽。

#### Acceptance Criteria

- 经 wp-id-by-code 解析 H1/H2 的 wp_id，读取 checklist-responses
- H1 增加/减少检查行中含"投资性房地产"的金额合计
- H2 转固行中含"投资性房地产"的金额合计
- pull 失败降级为手工输入+info 提示

### Requirement 3: H3-14 租金勾稽面板

**User Story:** 作为审计师，我需要在 H3-14 看到测算租金 vs TB 6051 的对比，确认租金收入完整性。

#### Acceptance Criteria

- H3-14 底部显示勾稽卡片：H3 测算年租金 vs TB 6051 审定值
- diff>0 为 info（差额来自其他来源），diff<0 为 warning（H3>TB 需关注）
- TB6051 为 null 时显示 info 不告警
- D4 GtIndexChip 跳转

### Requirement 4: 后端 TB 6051 数据注入

**User Story:** 作为系统，我需要在 H3 render 时提供 TB 6051 审定发生额供前端租金勾稽。

#### Acceptance Criteria

- `project_context` 新增 `tb_6051_audited`（trial_balance 6051% 聚合 audited_amount）
- 查询使用 get_active_filter
- 查询失败返回 null 不阻塞 render

### Requirement 5: H3-12 产权抵押勾稽面板

**User Story:** 作为审计师，我需要在 H3-12 看到已抵押投资性房地产金额 vs L1/L3 借款质押物的对比。

#### Acceptance Criteria

- H3-12 底部显示抵押勾稽卡片
- H3 已抵押合计 vs L1+L3 质押中投资性房地产合计
- 差异>1元显示 warning
- GtIndexChip 跳转 L1/L3

### Requirement 6: H3-12 L1/L3 数据 pull

**User Story:** 作为系统，我需要从 L1/L3 底稿拉取质押相关数据供 H3-12 勾稽。

#### Acceptance Criteria

- 经 wp-id-by-code 解析 L1/L3 的 wp_id
- 读取质押/抵押行筛含"投资性房地产"/"房地产"的行合计
- pull 失败降级手工输入

### Requirement 7: EventBus 联动

**User Story:** 作为系统，当对方底稿变更时 H3 勾稽面板应自动刷新。

#### Acceptance Criteria

- H3 主入口已订阅 substantive:adjudicated → selfLoad 刷新 allResponses
- 无需新增事件注册（既有机制天然覆盖）

### Requirement 8: 零回归与向后兼容

**User Story:** 作为系统，当对方底稿未实例化时不影响 H3 正常使用。

#### Acceptance Criteria

- pull 函数 try/catch + fail-open
- 勾稽面板 v-if 守卫（数据为 null 时不告警）
- TB6051 null 时面板显示 info 提示

### Requirement 9: 正确性属性可测

**User Story:** 作为开发者，我需要纯函数覆盖全部勾稽逻辑以保证正确性。

#### Acceptance Criteria

- P1-P8 全纯函数可 vitest
- 容差统一1元
- pull 失败 status='unavailable' 不抛

## Glossary

| 术语 | 含义 |
|------|------|
| 互转 | CAS3 投资性房地产与自用资产/在建工程之间的三方向转换 |
| pull | 从对方底稿读取数据（wp-id-by-code + checklist-responses） |
| TB 6051 | 试算表科目6051其他业务收入 |
| 容差 | 勾稽差异允许范围（默认1元） |
