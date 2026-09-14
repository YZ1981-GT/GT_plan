# Requirements Document

## Introduction

D1-D7 底稿披露表↔附注模块联动已全链打通（结构化推送/正反向跳转/定向刷新/保存自动同步），本 spec 补齐最后两个系统性增强：审定数↔披露数一致性校对 + 项目级一键批量推送入口。

## Requirements

### Requirement 1: 审定合计与披露合计差异实时告警

**User Story:** 作为审计师，我希望在编辑 D3/D5/D6/D7 披露表时能实时看到审定表合计与当前披露表合计的差异，以便及时发现两者不一致。

#### Acceptance Criteria

- When 审计师打开 D3/D5/D6/D7 任一科目的附注披露 tab，then 系统在表格上方渲染校对横幅，显示「审定表合计 X / 披露表合计 Y / 差异 Z」。
- When 差异绝对值 > 1 元，then 横幅为黄色警告。
- When 差异绝对值 ≤ 1 元，then 横幅为绿色「核对一致」。
- 审定合计从跨 sheet 键（allResponses 已有键）读取，无需额外 API。
- 披露合计 = 当前披露表主表合计行的期末数。
- 只读态同样显示（供复核人查看一致性）。

### Requirement 2: 从审定表一键刷新披露表主表金额

**User Story:** 作为审计师，我希望在差异不一致时能一键用审定表数据刷新披露表金额，减少手工逐行核对。

#### Acceptance Criteria

- When 差异告警显示 且 非只读态，then 横幅提供「从审定表刷新」按钮。
- When 点击该按钮，then ElMessageBox.confirm 确认后以审定表各分类行期末审定数覆盖披露表对应行期末金额（按名称匹配）。
- 仅覆盖期末金额列；期初金额/说明文本/动态行不动。
- 刷新后差异自动重算，横幅变绿。
- 手工覆盖优先：未匹配行不动。

### Requirement 3: D1/D2 已有机制零回归

**User Story:** 作为开发者，我希望 D1/D2 已有的差异告警与带入逻辑不被影响。

#### Acceptance Criteria

- D1TabDisclosure / D2DisclosureNoteBody 的差异告警与「从审定表带入」代码不改动。
- 新增 D3-D7 校对逻辑对齐 D1/D2 范式但独立实现。

### Requirement 4: 项目级从全部底稿同步到附注

**User Story:** 作为现场经理/合伙人，我希望在审计收尾阶段能一键把全项目所有底稿披露表数据同步到附注，无需逐科目手动操作。

#### Acceptance Criteria

- When 点击附注工具栏「从全部底稿同步」按钮，then 系统按 note_workpaper_sync_registry.json 遍历全部已映射科目逐一推送。
- 后端新增 `POST /api/projects/{pid}/disclosure-notes/{year}/batch-sync-from-workpapers` 端点。
- 逐科目 fail-open（单科目失败不阻断其余），返回成功/失败/跳过计数 + 失败科目清单。
- 前端弹窗展示进度条 + 结果摘要（成功 N / 失败 M / 跳过 K）。
- 同步完成后自动刷新当前章节详情 + 树节点 stale 标记。

### Requirement 5: 权限与门控

**User Story:** 作为系统管理员，我希望批量同步和刷新操作受角色权限控制。

#### Acceptance Criteria

- When 用户角色为审计助理（无编辑权）或项目处于归档状态，then 「从全部底稿同步」按钮禁用 + tooltip 提示权限不足。
- 「从审定表刷新」按钮在只读态灰化。

### Requirement 6: 零回归与增量可回退

**User Story:** 作为开发者，我希望改动不破坏已有链路。

#### Acceptance Criteria

- 各科目手动「同步到附注」按钮行为不变。
- `refill_sections`（「全部刷新」走 TB/binding 取数路径）逻辑不变。
- 各科目 `useDisclosureAutoSync`（保存后自动同步）不变。
- 无 DB 迁移、无新表。
- 后端新端点 additive，不改已有 `sync_from_workpaper` 签名。

## Glossary

| 术语 | 含义 |
|------|------|
| 审定合计 | 审定表 X-1 各分类行期末审定数之和 |
| 披露合计 | 披露表主表合计行期末金额 |
| buildXSyncPayload | 各科目结构化推送 payload 构建函数 |
| note_workpaper_sync_registry.json | 科目→附注章节权威映射文件 |
| batch-sync | 项目级一次性遍历全部映射科目推送 |
