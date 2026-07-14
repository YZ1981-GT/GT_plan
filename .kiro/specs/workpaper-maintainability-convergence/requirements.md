# Requirements Document

## Introduction

本 spec 是底稿模块的可维护性收敛专项，承接但不修改已归档/已完成标记的 `platform-global-hardening`。当前代码已经具备 `GtWorkpaperShell`、`useWorkpaperScaffold`、Coverage Ledger、Vite transform 冒烟、版本链、复核、AI、导入导出和 ACNR 等能力，但 codegraph 实证显示“能力存在”与“真实接入”不一致：`GtWorkpaperShell` 零调用，`useWorkpaperScaffold` 仅由 Shell 调用，复核 provide 仅覆盖少量主入口，保存逻辑存在大量同构实现，Coverage Ledger 的整底稿豁免会掩盖单项能力缺失。

本 spec 不新增审计业务功能，不改变底稿业务口径，不重建已成熟的 D~N/S 组件。目标是建立可持续维护的运行时边界、统一持久化契约、逐能力覆盖真源和强制防回归门禁，使“保存可回读、全局能力默认可用、缺失接线可被自动发现”成为平台不变量。

### 事实基线（2026-07-14）

1. `GtWorkpaperShell` 当前无调用者；`useWorkpaperScaffold` 仅被该 Shell 调用。
2. `useWorkpaperReviewProvide` 的 codegraph caller 数显著低于专属底稿主入口数量。
3. `useWorkpaperVersionToolbar` 被大量组件分别调用，横切能力仍以手工接线为主。
4. `saveImmediate` 存在多种签名与重复实现，保存、debounce、快照、错误处理和 hydrate 行为不一致。
5. `coverage-ledger.json` 允许整条 entry 通过单个 exemption 跳过全部能力检查；`check_coverage_ledger.py` 只推断 displayPrefs/agingConfig，其余能力默认 fail-open。
6. Vite transform 冒烟已存在，但 API 前缀、default-only import、运行时 named-export 与保存往返仍缺统一门禁。

## Glossary

- **Runtime_Boundary**：由 `GtWpRenderer` 承担的统一底稿运行时边界，负责一次性 provide 全局能力并挂载必要 Host。
- **Scaffold**：`useWorkpaperScaffold`，提供 displayPrefs、agingConfig、版本链、复核、AI、跳转与 reload。
- **Persistence_Adapter**：统一 checklist response 加载、乐观更新、防抖保存、失败回滚、自动快照和 hydrate 的 composable。
- **Capability_Ledger**：按 wp_code × capability 记录实际接入、豁免和证据的机器可验证清单。
- **Round_Trip**：编辑 → PUT 成功 → 页面重新导航/刷新 → 相同值恢复的完整持久化闭环。
- **Legacy_Provider**：专属主入口内手工 provide 版本链、复核、AI、displayPrefs 或保存函数的旧接线。
- **Evidence_Gate**：完成任务前必须提供调用图、静态守卫、测试或 Playwright 结果，不以复选框作为完成证据。

## Requirements

### Requirement 1: 真实覆盖基线与防假完成（P0）

**User Story:** 作为平台维护者，我希望底稿能力覆盖由当前代码和运行时证据生成，而不是由历史任务勾选或人工豁免推断，以便维护决策建立在真实状态上。

#### Acceptance Criteria

1. WHEN 基线扫描运行时，THE Scanner SHALL 枚举 `htmlRendererRegistry` 中全部专属 componentType、对应主入口、wp_code 和上下文策略。
2. THE Scanner SHALL 为每个 wp_code 分别检测 displayPrefs、agingConfig、version、review、ai、importExport、acnr、persistence 八项能力，并记录证据文件与符号。
3. THE Capability_Ledger SHALL 支持“单能力豁免”，且 SHALL NOT 允许一个 entry 级 exemption 自动豁免其他能力。
4. WHEN Ledger 记录与静态调用图不一致时，THE Evidence_Gate SHALL 失败并输出 wp_code、capability、期望证据和实际证据。
5. WHEN 历史 tasks 标记为完成但现状不满足验收时，THE 本 spec SHALL 以现状为准创建修复任务，不修改归档 spec 的历史记录。

### Requirement 2: 统一底稿运行时边界（P0）

**User Story:** 作为底稿开发者，我希望所有经 `GtWpRenderer` 渲染的底稿自动获得平台横切能力，以便不再由每个主入口重复 provide 和挂载 Host。

#### Acceptance Criteria

1. WHEN `GtWpRenderer` 渲染任一 `standard` 或专属 HTML componentType 时，THE Runtime_Boundary SHALL 恰好初始化一次 Scaffold。
2. THE Runtime_Boundary SHALL 提供 displayPrefs、agingConfig、version、review、ai、jumpToSection 和 reload，并挂载版本历史与复核对话所需 Host。
3. WHEN 子组件存在 Legacy_Provider 时，THE 迁移期 SHALL 保持行为兼容并记录重复 provider；完成迁移后 CI SHALL 阻断新增 Legacy_Provider。
4. THE `GtWorkpaperShell` SHALL 保留为脱离 `GtWpRenderer` 的独立渲染场景使用，且 SHALL 与 Runtime_Boundary 共享同一 Scaffold 实现。
5. WHEN wpId、projectId、wpCode 或 year 缺失时，THE Runtime_Boundary SHALL 在开发环境输出明确错误，在生产环境降级但不得使页面白屏。
6. THE Runtime_Boundary SHALL NOT 重复渲染现有底稿 toolbar、导入导出按钮或业务区域。

### Requirement 3: checklist 持久化统一契约（P0）

**User Story:** 作为审计助理，我希望任何底稿编辑都可靠落库并在刷新后恢复，以便不会出现界面已填写但数据未保存或 reload 丢失。

#### Acceptance Criteria

1. THE Persistence_Adapter SHALL 提供 `load`、`save`、`saveDebounced`、`flush`、`cancel` 和 `hydrate` 稳定接口。
2. WHEN 保存 checklist item 时，THE Adapter SHALL 使用 `/api/workpapers/{wpId}/checklist-responses`，并以 `{item_id, remark, conclusion, wp_ref}` 标准结构发送。
3. WHEN projectId 未显式提供时，THE 后端 SHALL 从 working_paper 解析 project_id；前端 SHALL NOT 伪造 wpId 作为 project_id。
4. WHEN remark 为结构化数据时，THE Adapter SHALL 恰好 JSON 序列化一次；hydrate SHALL 兼容历史双层包裹数据但新写入 SHALL 为单层 JSON。
5. WHEN 防抖窗口内同一 item 多次更新时，THE Adapter SHALL 最终写入最后值，且不同 item 的定时器 SHALL 相互独立。
6. WHEN 保存失败时，THE Adapter SHALL 保留可重试状态、向用户显示明确错误并避免把失败值标记为已持久化。
7. WHEN 保存成功时，THE Adapter SHALL 触发自动版本快照调度；同一防抖窗口 SHALL NOT 产生重复快照。
8. WHEN组件卸载或切换 sheet 时，THE Adapter SHALL flush 待保存变更或显式 cancel，禁止静默丢弃。
9. WHEN执行 Round_Trip 验收时，THE 页面刷新或重新导航后 SHALL 恢复最后一次成功保存值。

### Requirement 4: 保存与读取的后端边界（P0）

**User Story:** 作为平台维护者，我希望 checklist API 在权限、事务、字段校验和事件通知上具备单一行为，以便所有底稿使用同一可靠边界。

#### Acceptance Criteria

1. THE checklist API SHALL 保持 `(wp_id, item_id)` UPSERT 唯一语义和单请求事务原子性。
2. THE API SHALL 校验当前用户对目标项目/底稿的编辑权限，而不只对复核表执行专项 RBAC。
3. WHEN批量 items 中任一条不合法时，THE API SHALL 返回可定位 item_id 的错误并按定义选择整批回滚；不得部分成功而无报告。
4. WHEN保存成功时，THE API SHALL 发布统一底稿保存事件或调用现有事件入口，使版本链、联动和一致性检查获得通知。
5. THE读取端点 SHALL 返回稳定字段并支持 ETag 或版本号，为失败回滚和并发覆盖检测提供依据。
6. WHEN两个客户端基于同一旧版本并发保存同一 item 时，THE API SHALL 检测冲突或明确采用 last-write-wins 并返回覆盖信息；行为必须可测试、可观察。

### Requirement 5: 强制防回归门禁（P0）

**User Story:** 作为开发负责人，我希望最高频的 API 前缀、导入方式、运行时 ESM 和持久化断路由自动检查阻断，以便不再依赖 Playwright 偶然发现。

#### Acceptance Criteria

1. THE API Prefix Guard SHALL 检测底稿源码中经平台 http 客户端发出的相对 URL；明确缺少 `/api` 的调用 SHALL 阻断 CI，已登记的非 API 地址 SHALL 可逐项豁免。
2. THE Import Contract Guard SHALL 阻断从 default-only 模块进行 named import 的已知模式，包括 `@/utils/http`。
3. THE Vite transform 冒烟 SHALL 保持覆盖全部工作底稿 `.vue/.ts` 生产代码并作为 blocking job 执行。
4. THE Runtime Import Smoke SHALL 至少加载每个专属 componentType 一次，以发现 transform 无法识别的 named-export 运行时错误。
5. THE Persistence Contract Guard SHALL 检测重复自建 `saveImmediate` 网络实现、双层 `JSON.stringify({remark})`、错误 project_id 和无 `/api` checklist URL。
6. WHEN守卫无法确定时，THE Guard SHALL fail-open 并报告；WHEN明确命中禁用模式时，THE Guard SHALL fail-closed。
7. THE CI SHALL 输出可操作的文件、行号、规则编号和迁移建议。

### Requirement 6: 同构 composable 与注册表收敛（P1）

**User Story:** 作为维护开发者，我希望重复的表单持久化和目录定义通过工厂与数据配置表达，以便修复一次即可覆盖所有同类底稿。

#### Acceptance Criteria

1. WHEN 两个 FormData composable 仅在 prefix、label、endpoint 或 sheet cache 键上不同，THE 系统 SHALL 使用参数化工厂生成，不保留复制实现。
2. THE 工厂 SHALL 复用 Persistence_Adapter，并允许业务 composable 注入 normalize/validate/afterSave 钩子。
3. THE 目录页 SHALL 优先从 render-config/ACNR/注册真源生成 sheet 名称、编码、componentType 和状态；业务特有勾稽可通过扩展函数注入。
4. THE `htmlRendererRegistry` SHALL 按领域拆分为多个 registry module，并由单一 barrel 合并；componentType 类型、lazy component、contextProps 和 emits SHALL 保持单一真源。
5. WHEN 拆分或工厂化完成时，THE 现有 componentType 集合、sheet 顺序和用户可见行为 SHALL 保持不变。
6. THE CI SHALL 检测新建的同构 FormData 网络实现和重复 componentType 注册。

### Requirement 7: 横切能力用户可见验收（P1）

**User Story:** 作为审计助理、经理和合伙人，我希望版本、复核、AI、导入导出和跨表跳转在每个适用底稿中真实可操作，以便平台能力不是“代码存在但按钮失效”。

#### Acceptance Criteria

1. WHEN 用户点击适用底稿的复核按钮时，THE 系统 SHALL 打开绑定当前 wpId 与 sectionId 的真实复核对话，而非 console 桩。
2. WHEN 用户完成一次成功保存时，THE 版本服务 SHALL 在防抖窗口后生成至多一个自动快照。
3. WHEN 用户打开版本历史时，THE 系统 SHALL 展示当前 wpId 的历史且可关闭返回原 sheet。
4. WHEN 用户调用 AI 辅助时，THE 请求 context 值 SHALL 全部为字符串，错误 SHALL 可见且不得覆盖已有文本。
5. WHEN 底稿适用导入导出时，THE toolbar SHALL 使用统一“导入导出▾”交互并调用已有端点；不适用时 SHALL 不显示假按钮。
6. WHEN 用户从目录或索引跳转时，THE 系统 SHALL 优先精确 sheet 名匹配并避免 `J1-1` 误匹配 `J1-10`。

### Requirement 8: 性能、可观测性与渐进迁移（P1）

**User Story:** 作为运维与现场团队，我希望底稿收敛后不降低首屏和保存性能，并能从指标定位异常，以便支持高并发项目现场使用。

#### Acceptance Criteria

1. THE 系统 SHALL 记录 render-config 冷/热耗时、renderer 调用次数、checklist load/save 耗时、409 冲突数和保存失败数。
2. WHEN whole-workpaper dedicated component 的多个 sheet 使用同一渲染结果时，THE render-config SHALL 在单请求内 memo，避免重复 renderer/DB 调用。
3. BEFORE 引入跨请求缓存，THE 实现 SHALL 提供基准数据、cache key、失效事件和权限隔离设计；不得只以 TTL 掩盖一致性问题。
4. THE 迁移 SHALL 按代表性试点和循环批次推进，每批可独立回滚，不要求一次性切换全部组件。
5. WHEN 任一批次迁移完成时，THE 批次 SHALL 通过 targeted tests、Vite transform、Runtime Import Smoke 与 Playwright Round_Trip。
6. THE 最终验收 SHALL 达到：Runtime Boundary 覆盖全部经 GtWpRenderer 渲染的专属底稿；适用能力缺失为 0；Legacy_Provider 和重复 checklist 网络实现均为 0 或有逐能力、限期豁免。

## Traceability Summary

| 需求 | 优先级 | 主要验收证据 |
|---|---|---|
| Req 1 | P0 | codegraph/registry 清单 + Ledger v2 + drift guard |
| Req 2 | P0 | Runtime Boundary 单实例测试 + Host 实测 |
| Req 3 | P0 | Persistence Adapter PBT + Round_Trip |
| Req 4 | P0 | API 契约/权限/并发测试 |
| Req 5 | P0 | blocking CI guards + runtime import smoke |
| Req 6 | P1 | 工厂化等价测试 + registry contract |
| Req 7 | P1 | Playwright 用户可见行为 |
| Req 8 | P1 | 性能基准、指标和全量覆盖报告 |
