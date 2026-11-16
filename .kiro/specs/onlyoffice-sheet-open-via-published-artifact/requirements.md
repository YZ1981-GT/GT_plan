# Sheet 级 OnlyOffice 入口改走 Published Representation

> **状态：0/30，产品代码未实施（2026-11-16 新建）**
>
> 本 spec 承接 `workpaper-html-onlyoffice-bidirectional-writeback-closure` 任务 2.8 的实测结论。
> 它解决的是「旧式 sheet 入口打开的模板副本」与「room 协议打开的 published artifact」不是同一文件的问题。
> 本文件定义目标契约；不把当前旧式接口的行为当作目标行为。

## Requirement 1：建立显式 Sheet → Entry 映射

**User Story:** 作为在线编辑平台，我需要把 `(project_id, wp_id, sheet_name, whole_workbook)` 映射到一个已登记的 sync entry，避免运行时凭 sheet 名猜子码。

### Acceptance Criteria

1. WHEN 服务端收到 sheet 级在线编辑请求 THEN 系统 SHALL 从版本化的 `sheet_open_bindings` 真源读取映射，并返回 `entry_id`、`source_wp_code`、`target_sheet`、`document_scope` 与 `mapping_status`。
2. 映射 SHALL 只允许 `exact`、`provider`、`whole_workbook` 三种封闭形态；路由层不得新增正则、前缀或模糊匹配兜底。
3. WHEN 请求没有唯一映射、映射指向不存在的 manifest entry、或映射与当前 `wp_id` 不相容 THEN 系统 SHALL 返回结构化中文原因，不得猜测父级底稿，也不得签发旧式 URL。
4. `sheet_open_bindings` 的每条记录 SHALL 带 source digest、生成器版本、审核状态与来源引用；生成结果必须幂等，内容不变时重跑不得产生 diff。

## Requirement 2：Published Representation 是迁移后唯一 OO 文件来源

**User Story:** 作为审计师，我需要打开当前已发布的 immutable artifact，而不是请求期复制模板或修改 OO 缓存副本。

### Acceptance Criteria

1. WHEN 映射状态为 `migrated` 且 entry 为 `bidirectional` THEN 系统 SHALL 通过 `resolve_visible_current_representation_id` 定位当前 representation，并通过 `CanonicalArtifactRepository` / `ArtifactStorageLayout` 读取文件。
2. 迁移后的读取路径 SHALL 不调用 `find_template_file_any`、`_resolve_wp_file`、`shutil.copy2`、`_hide_non_target_sheets` 或 `_ensure_all_sheets_visible` 来生成本次编辑文件。
3. 当前 representation 不存在、不是 published、definition bundle 不可用、文件缺失或 digest 不一致时，系统 SHALL fail-closed 返回 typed reason；不得回退到模板副本并伪装成双向编辑。
4. 读取 artifact SHALL 不改变文件字节、sheet 可见性、revision、representation generation 或 content version。

## Requirement 3：Room Descriptor 承载 sheet 视图

**User Story:** 作为 OnlyOffice 编辑器，我需要拿到绑定 entry 的 room descriptor，并在同一个 immutable artifact 中定位目标 sheet。

### Acceptance Criteria

1. 迁移后的入口 SHALL 复用 `materialize` / `materializeFromStore`、`EditorLaunchDescriptor`、`confirm-descriptor`、room contents 与 forcesave 链路，不再为 sheet 入口创建第二套 config 解释。
2. `document.url`、`callbackUrl`、`doc_key`、`room_id`、`generation` 与 `entry_id` SHALL 来自同一个 descriptor / room；不得由调用方拼接不一致的 URL。
3. 单 sheet 模式 SHALL 通过 descriptor 的 target sheet / OnlyOffice `actionLink` 表达视图；不得通过隐藏其它 sheet 改写 artifact。
4. `whole_workbook=true` SHALL 打开同一 published artifact 的完整 workbook 视图，不得将 whole workbook 重新解析为某个子码或复制另一份文件。

## Requirement 4：前端宿主与旧式组件边界清晰

**User Story:** 作为前端维护者，我需要知道哪些入口已经进入 room 协议，哪些仍是独立在线编辑，避免页面显示“已同步”但实际走旧链路。

### Acceptance Criteria

1. `WorkpaperSyncEditorHost` 只能消费 descriptor；它不得接收旧式 `document_url` / `callback_url` 作为第二来源。
2. 仍未完成映射或 published artifact 供给的入口 SHALL 显示“独立在线编辑（不同步）”或真实不可用原因，不得显示“双向回写”“已同步”等文案。
3. `GtOnlyOfficeSheet` 的 legacy 调用方必须有逐入口登记、owner、原因和下一步；登记项不得通过 `DEPRECATED` 注释长期隐藏。
4. 迁移完成的入口不得再调用 `/onlyoffice-config`；守卫 SHALL 对宿主闭包、composable 与直接组件调用面做 AST / 运行时双向检查。

## Requirement 5：Custom、Word、Single 能力单独裁决

**User Story:** 作为平台治理者，我需要避免把 custom 文件、Word 载体和纯 OO 入口错误套用 Excel published artifact 迁移。

### Acceptance Criteria

1. `single_onlyoffice` entry 不得伪造 HTML counterpart、contract、bundle 或双向入口；它可以继续使用独立 OO 入口，但界面必须标明真实能力。
2. Word / DOCX 入口 SHALL 继续由 Word carrier / Word engine 的 lane 管理；本 spec 不把 DOCX 映射到 Excel sheet binding。
3. custom workpaper SHALL 明确采用“业务文件本体”或单独的 custom artifact owner；不得把模板库文件当作 custom 的 published artifact。
4. 每一种不纳入本 spec 的入口都必须在 mapping ledger 中登记 `out_of_scope_reason` 与后续 owner。

## Requirement 6：兼容期与 Legacy Drain

**User Story:** 作为发布负责人，我需要逐入口切换并安全清理旧式 doc key / direct-write，不影响已经打开的编辑器。

### Acceptance Criteria

1. 每条 binding SHALL 有 `pending`、`ready`、`migrated`、`draining`、`retired` 之一的状态；状态变更必须由服务端现读 readiness 与 evidence 决定。
2. `migrated` entry 不得签发新的 `/onlyoffice-config`、`wopi/contents` 或 legacy callback URL；`pending` entry 可回退旧式，但响应必须标明“独立在线编辑（不同步）”。
3. `draining` 期间，系统 SHALL 按旧 doc key / token TTL 接收已签发的合法 callback，但不得为新请求创建旧 doc key；超时后旧 direct-write 必须返回可观测的 typed reason。
4. 旧式 URL 的签发数、callback 数、拒绝数和 drain 超时数 SHALL 进入指标与审计日志；删除旧路径前这些计数必须按 entry 维度连续为零。

## Requirement 7：权限、路径与租户隔离

**User Story:** 作为平台安全负责人，我需要确保新读取路径不能通过 sheet 名、entry_id 或 artifact 路径越权。

### Acceptance Criteria

1. 服务端必须先验证 `project_id`、`wp_id`、当前用户与底稿的归属，再读取 mapping、representation 或 artifact。
2. 客户端不得提交任意 artifact path、relative path、representation path 或 callback target；这些值必须由服务端从冻结 identity 生成。
3. artifact 读取必须经过既有 canonical path boundary；跨项目、跨底稿、历史 candidate、incoming artifact 与模板库路径必须 fail-closed。
4. room token 必须绑定 project、wp、entry、generation、doc_key 与操作目的；旧 token 不能被新 binding 重放。

## Requirement 8：生成物、契约与数据版本可追溯

**User Story:** 作为审计复核人，我需要从一个映射结果追溯到它的来源、契约和 published artifact。

### Acceptance Criteria

1. `sheet_open_bindings` 生成物必须记录 `manifest_digest`、`wp_code_adjudication_digest`、source file digest、mapping rule digest 与 schema version。
2. 每次 descriptor SHALL 能回溯到 `entry_id`、representation id/generation、definition bundle id/digest、target sheet 与 mapping record id。
3. 任何 manifest、mapping、contract、bundle、representation 或 provider digest 变化都必须使 binding / readiness 标 stale，禁止沿用旧映射继续宣称 ready。
4. 生成器必须提供 `--check`，并由测试守卫确认重跑幂等、源 digest 变更会使检查失败。

## Requirement 9：真实验证覆盖四种打开场景

**User Story:** 作为验收人员，我需要证明单 sheet、整册、聚合子码和失败回退都使用正确的文件与身份。

### Acceptance Criteria

1. 至少覆盖一个普通单 sheet entry、一个 whole workbook entry、一个聚合包内 source sheet、一个 custom 或 single_onlyoffice 排除样本。
2. 每个迁移样本必须验证 HTML → room descriptor → OnlyOffice target sheet → forcesave → HTML / API 回读，且 artifact 字节和未受管 sheet 不被破坏。
3. 必须验证旧式 pending 入口仍显示独立在线编辑、迁移后入口不再签发旧 URL、draining 旧 callback 可安全结算。
4. 浏览器验收必须使用 `http://127.0.0.1:3030`，记录 console、网络、页面错误和操作前后数据快照；真实写入只使用【测试】项目并可逐项恢复。

## Requirement 10：完成与归档门

**User Story:** 作为项目负责人，我需要在没有假绿的情况下关闭本 spec。

### Acceptance Criteria

1. 所有 binding 必须是 `migrated`、明确 `out_of_scope` 或有 owner 的 `pending`；不得留下无原因的 legacy 调用。
2. mapping / readiness / room / artifact / legacy drain 的单元、PG、前端和 Playwright 守卫全部通过；预存失败必须以干净基线逐节点对账。
3. 变异必须杀死：删除映射、改 entry_id、把 current 改 candidate、恢复模板 copy、绕过 room token、放宽 legacy callback、去掉 target sheet 校验等形态；阴性对照必须保持绿。
4. 完成前必须在 clean checkout 验证三件套、生成物、路由注册、前端构建和关键测试；完成后才更新 INDEX 并归档。
