# 实施计划：出品物溯源与回填（deliverable-lineage-and-writeback）

## 概述

本计划将 design.md 拆解为可由编码代理增量执行的任务序列。每个任务都建立在前序任务之上，最终接线成完整双向数据流（正向溯源 P0/P1 + 反向回填 P2），不留孤立未接线代码。任务聚焦"接入/适配/扩展已有服务"——严禁重建溯源总线、Stale 传播引擎、事件总线、留痕服务（唯一允许新建的是状态承载表 `deliverable_section_state` 与两个薄适配服务）。

实施语言：后端 **Python 3.12**（仓库根 `.venv`）；前端 **Vue3 + TypeScript**；数据层 **PostgreSQL 16** 手写迁移（MigrationRunner，非 alembic）。属性测试用 **hypothesis**（`max_examples=5`，用户铁律）。

---

## 🚨 实施门控（START GATE — 全部任务阻塞于此）

> **本 spec 全部编码任务（除 Phase 0 POC 外）阻塞于下列上游前置条件。门控未解除前，被标 ⚠️ 的任务一律不得开始编码实施。**

| 门控项 | 来源 | 当前状态 | 解除判据 |
|--------|------|----------|----------|
| **G1：附注模板整理 + 全量打标** | `audit-report-template-integration` task 0.6（含 0.6.2 附注四份 `##SECTION:` 打标） | 0.6.2 chapter-scoped 打标已完成；模板 SECTION 块内仍是参考内容（非 `{{section}}/{{table}}/{{seq}}` 填充占位符）+ 残留【】指引 | 模板插入 fill 占位符 + `strip_bracket_guidance` 清【】完成 |
| **G2：附注 template 模式灰度可用** | `audit-report-template-integration` task 10.2（`_export_template_mode`）+ 10.4（`render_disclosure_notes` 灰度切 `mode=template`） | 机制已由合成 docx 测试证实；`USE_TEMPLATE_FILL_SERVICE` 仍默认 `false` | 完成 G1 + 人工 spot check（上游 task 18）后 flip `USE_TEMPLATE_FILL_SERVICE=true` |

**门控解读**：

- ⚠️ 标记的任务 = 直接依赖段落锚点写入或附注 template 章节块定位能力，**硬阻塞于 G1+G2**（`USE_TEMPLATE_FILL_SERVICE=true`）。
- 未标 ⚠️ 的任务（迁移/ORM/快照服务/纯只读映射骨架）可在门控解除前先行实施，但**端到端联调仍须等 G2 开启**。
- Phase 0 的 D1 锚点 POC **不受门控约束**（它本就是为验证锚点形式、解除 G2 风险服务的前置工作），且是后续 P0 锚点写入的前置。

---

## 验收里程碑

| 里程碑 | 完成判据 | 覆盖任务 |
|--------|----------|----------|
| **M0 锚点 POC 通过** | 隐藏书签经 OnlyOffice 往返 + python-docx 回读三项判据全过（不可见 / 往返不丢 / 可按 name 定位），结论回写 design | Phase 0（任务 0） |
| **M1 P0 溯源可用** | deliverable 接入 LinkageFacade + confirm 写锚点 + 前端 Lineage_Panel 可溯源跳转；V067 三层一致 + 契约测试绿 | Phase 1（任务 1-6） |
| **M2 P1 Stale 闭环** | 上游变更级联标章节 stale + SSE 推前端 + 单/批量增量刷新；自触发防护生效 | Phase 2（任务 7-11） |
| **M3 P2 回填闭环** | 合规护栏 + OnlyOffice 显式回填 + 冲突三方裁决 + 留痕 + 终态禁止回填/刷新 + 权限/审计日志/异步 job | Phase 3（任务 12-18） |
| **M4 收尾** | 28 条属性测试全绿（max_examples=5）+ 文档/memory 更新 | 收尾（任务 19） |

---

## 任务依赖说明

```
Phase 0 (POC) ──► Phase 1 ①V067迁移 ──► ②LinkageFacade ──► ⑤前端面板
                            │                  ▲
                            └──► ③段落锚点⚠️ ──┤(④快照依赖confirm锚点写入点)
                                 ④快照服务 ────┘
Phase 1 ──► Phase 2 ⑥StaleEngine ──► ⑦event_handlers ──► ⑨stale前端
                    ⑧增量刷新⚠️(依赖③锚点+④快照)
Phase 2 ──► Phase 3 ⑩护栏 ──► ⑪回填管道⚠️ ──► ⑫冲突 ──► ⑬留痕 ──► ⑭回填前端 ──► ⑮非功能闸门
收尾 ⑯ 贯穿全程（属性测试随实现落地，文档最后统一更新）
```

- ③（段落锚点）是 ④（快照 on confirm）、⑧（增量刷新）、⑪（回填分块）的物理前置——锚点不写则无处定位。
- ②（LinkageFacade deliverable 分支）依赖 ①（V067 表 + ORM）提供章节级 stale 查询。
- ⑦（event_handlers）依赖 ⑥（StalePropagationEngine DELIVERABLE 前缀）。
- ⑫（冲突检测）依赖 ④（快照基线 hash）+ ⑪（回填管道三方比对）。

---

## Phase 0：D1 段落锚点 POC（前置，阻塞 P0 锚点写入；不受 START GATE 约束）

- [ ] 0. D1 段落锚点 POC（隐藏书签双方可读可定位验证）
  - 在编码 P0 锚点写入（任务 3）前独立验证锚点形式，POC 不改生产模板，以最小脚本完成
  - 产物：`backend/scripts/e2e/_poc_section_anchor.py`（`_` 前缀，验证后即删或归档）+ 结论回写 design.md「D1 段落锚点 POC 验证计划」节
  - _Requirements: 2.2_ / _Design: 决策 D1 + D1 POC 验证计划_

  - [ ] 0.1 合成附注 docx 写入隐藏书签
    - 用 python-docx 在合成附注 docx 章节块 `open_el` 前插入 `<w:bookmarkStart w:id w:name="sec_八_1"/>`、`close_el` 后插入 `<w:bookmarkEnd w:id/>`，保存
    - 验证书签不可见、排版无变化
    - _Requirements: 2.2, 2.3_ / _Design: D1 POC 步骤 1_

  - [ ] 0.2 OnlyOffice 往返保真验证
    - 上传到 OnlyOffice Docker（9.4.0）→ 打开确认书签不可见、排版无变 → 编辑无关章节保存 → 经 signed-download 重新下载
    - 注意 SSRF 私有 IP 放行（`local.json` allowPrivateIPAddress）+ callback 不被 ResponseWrapperMiddleware 包装（已知坑）
    - _Requirements: 2.2_ / _Design: D1 POC 步骤 2_

  - [ ] 0.3 python-docx 回读定位验证 + 结论判定
    - 对下载回来的 docx 重新扫描章节块 + 按 name 定位书签区间，断言能正确切出对应章节块文字
    - 三项判据（①不可见 ②往返不丢 ③可按 name 定位）全过 → 采用书签；任一不过 → 回退评估 SDT 内容控件（同口径补测）
    - 结论回写 design.md，确定最终锚点形式后才进入任务 3
    - _Requirements: 2.2_ / _Design: D1 POC 步骤 3-4_

---

## Phase 1（P0）：deliverable 接入溯源体系 + 段落锚点 + 溯源面板

- [ ] 1. V067 迁移 + ORM + 契约测试（deliverable_section_state 三层一致）
  - 当前最高迁移 V066，本 spec 用 V067；遵循三层一致铁律（DDL = ORM = service）+ TimestampMixin 列必须同步到手写 DDL
  - 本表承载的是"出品物层全新章节状态维度"——出品物从未有任何章节状态承载，故须新建；**非**上游缺章节粒度（上游 `disclosure_notes.is_stale` 本就是章节级行存储，每 `note_section` 一行）
  - 出品物身份键统一为 `word_export_task_id`（关联 `word_export_task.id`，即 task_id；程序中无 `deliverable_id` 概念），章节状态绑 task 级（跨版本稳定）
  - _Requirements: 4.4, 4.5_ / _Design: 数据模型「新表 deliverable_section_state」「迁移 V067 + 回滚 R067」「ORM 模型」_

  - [ ] 1.1 编写 V067 迁移 + R067 回滚配对
    - `backend/migrations/V067__deliverable_section_state.sql`：CREATE TABLE IF NOT EXISTS，含 id/word_export_task_id/version_no/project_id/year/section_code/source_snapshot_hash/is_stale/last_writeback_baseline_hash/anchor_name + 显式 `created_at`/`updated_at`（TimestampMixin 铁律）
    - `version_no INT NULL`：记录该快照对应版本号（**不入主键/唯一约束**，绑 task 级跨版本稳定）
    - 唯一约束 `uq_deliverable_section (word_export_task_id, section_code)` + 索引 idx_dss_project_year / idx_dss_stale(word_export_task_id, is_stale) / idx_dss_section（均 IF NOT EXISTS）
    - `backend/migrations/R067__rollback.sql`：`DROP TABLE IF EXISTS deliverable_section_state;`
    - 校验同号去重（scan_migrations 同号检测），确认无 V067 撞号
    - _Requirements: 4.4_ / _Design: 迁移 V067 + 回滚 R067_

  - [ ] 1.2 新增 ORM 模型 DeliverableSectionState（继承 TimestampMixin）
    - 加入 `backend/app/models/audit_platform_models.py`：`class DeliverableSectionState(Base, TimestampMixin)`，`Mapped[]` 列与 DDL 逐列一致 + UniqueConstraint
    - 含 `word_export_task_id: Mapped[UUID]`（NOT NULL）+ `version_no: Mapped[int | None]`（记录列，不入主键/唯一约束）
    - _Requirements: 4.4_ / _Design: ORM 模型（三层一致）_

  - [ ]* 1.3 编写 V067 三层一致契约测试
    - 复用现有 `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` 体系 + drift detector，断言 deliverable_section_state 表/列在 DDL=ORM 零 drift
    - 验证 R067 回滚可执行
    - _Requirements: 4.4_ / _Design: 测试策略「验证铁律」_

- [ ] 2. LinkageFacadeService 扩展 deliverable source_type（只读穿透）
  - 在现有 `trace` 的 if/elif 链新增 `source_type == "deliverable"` 分支，不新建并行溯源服务
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_ / _Design: 组件「1. LinkageFacadeService 扩展」_

  - [ ] 2.1 实现 _trace_from_deliverable 映射 + 上游链延续
    - `source_id` 约定 `'{word_export_task_id}:{section_code}'`，按 section_code（含 legacy_alias 归一）映射 disclosure_notes
    - 无匹配 → 返回明确"无匹配来源"结果并记录 section_code（需求 1.4）
    - 复用 `wp_trace_service.trace_upstream` 向上游展开（附注→报表→审定表→调整分录，需求 1.5）
    - 沿用现有 LinkageContract（含 route），仅读取不修改 disclosure_notes（需求 1.3/1.6）
    - 补一步章节级 stale 查询（读 deliverable_section_state.is_stale，依赖任务 1）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_ / _Design: _trace_from_deliverable docstring_

  - [ ]* 2.2 属性测试：deliverable→附注映射正确性
    - **Property 1: deliverable→附注映射正确性**
    - **Validates: Requirements 1.2**
    - `# Feature: deliverable-lineage-and-writeback, Property 1`
    - hypothesis max_examples=5；生成器覆盖 legacy_alias 章节
    - _Requirements: 1.2_

  - [ ]* 2.3 属性测试：契约结构复用（含 route）
    - **Property 2: 契约结构复用（含 route）**
    - **Validates: Requirements 1.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 2`
    - _Requirements: 1.3_

  - [ ]* 2.4 属性测试：溯源只读不变量
    - **Property 3: 溯源只读不变量**（溯源前后 disclosure_notes 不变；标 deliverable stale 不翻转 notes.is_stale）
    - **Validates: Requirements 1.6, 4.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 3`
    - _Requirements: 1.6, 4.4_

  - [ ]* 2.5 属性测试：上游链路延续
    - **Property 4: 上游链路延续**
    - **Validates: Requirements 1.5**
    - `# Feature: deliverable-lineage-and-writeback, Property 4`
    - _Requirements: 1.5_

  - [ ]* 2.6 单元测试：deliverable 分支存在 + 缺失 section_code
    - 1.1（deliverable 分支可达）、1.4（缺失 section_code 返回无匹配并记录）
    - _Requirements: 1.1, 1.4_

- [ ] 3. ⚠️ 段落锚点写入（confirm 时写隐藏书签）【阻塞于 G1+G2】
  - 在 `NoteWordExporter._export_template_mode`（及 TemplateFillService confirm 路径）清理标记之前插入锚点写入步骤；依赖任务 0 POC 确定的锚点形式
  - WHERE `USE_TEMPLATE_FILL_SERVICE=false` 期间该步骤标"阻塞中"，灰度开启后实施（需求 2.7）
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7_ / _Design: 组件「2. 段落锚点写入」_

  - [ ] 3.1 实现 anchor_name / section_code_from_anchor 双向映射
    - `anchor_name(section_code)`：`'八、1' → 'sec_八_1'`（确定性替换，OOXML 书签名禁空格）
    - `section_code_from_anchor(name)`：逆映射，结合 section_code_index 校验存在性
    - _Requirements: 2.6_ / _Design: 锚点命名_

  - [ ] 3.2 实现 write_section_anchors 并接入 confirm 清理标记之前
    - 在 `_export_template_mode` 步骤 7（remove_section_markers）之前新增 6.5 步：对每个保留章节块在 open_el 前插 bookmarkStart、close_el 后插 bookmarkEnd，锚点名 = anchor_name(section_code)
    - 仅对 kept_codes 写锚点，被裁剪删除章节不写（需求 2.5）；保留 remove_section_markers 清可见标记（需求 2.4）
    - 锚点保持隐藏不影响可见正文（需求 2.3）；同步写 anchor_name 到 deliverable_section_state
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.7_ / _Design: 组件 2 算法步骤_

  - [ ]* 3.3 属性测试：保留章节有锚点、裁剪章节无锚点
    - **Property 5: 保留章节有锚点、裁剪章节无锚点**
    - **Validates: Requirements 2.1, 2.5**
    - `# Feature: deliverable-lineage-and-writeback, Property 5`
    - 生成器覆盖保留/裁剪集合随机组合
    - _Requirements: 2.1, 2.5_

  - [ ]* 3.4 属性测试：锚点写入保留可见正文、清除可见标记
    - **Property 6: 锚点写入保留可见正文、清除可见标记**
    - **Validates: Requirements 2.3, 2.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 6`
    - _Requirements: 2.3, 2.4_

  - [ ]* 3.5 属性测试：锚点命名往返
    - **Property 7: 锚点命名往返**（`section_code_from_anchor(anchor_name(code)) == code`）
    - **Validates: Requirements 2.6**
    - `# Feature: deliverable-lineage-and-writeback, Property 7`
    - 生成器覆盖国企（八、1）/上市（五、1）/含·分隔符
    - _Requirements: 2.6_

- [ ] 4. DeliverableSectionStateService（新建：快照计算 / stale 标记 / 查询）
  - 仅承载状态，不含传播逻辑（传播复用 StalePropagationEngine）；依赖任务 1（表）+ 任务 3（confirm 锚点写入点）
  - 服务签名统一以 `word_export_task_id` 为出品物标识键
  - _Requirements: 4.1, 4.2, 4.6, 10.5_ / _Design: 组件「3. DeliverableSectionStateService」+ 数据模型「Source_Snapshot_Hash 计算口径」+ 决策 D9_

  - [ ] 4.1 实现 compute_source_snapshot_hash（确定性 sha256，与 doc 级 tb_hash 分层）
    - 覆盖 disclosure_notes.text_content + table_data + 相关 audited_amount
    - 规范化 JSON（`sort_keys=True, ensure_ascii=False, separators=(",",":")`）→ sha256；金额统一转字符串；audited_amount 按 account_code 排序（需求 10.5）
    - **分层口径（D9）**：与现有 `DeliverableSnapshotService.tb_hash`（整张试算表 MD5，doc 级整份闸门）配合——本章节级 hash 在 `tb_hash` 口径上细化到 `section_code` + `text_content`（`tb_hash` 不含 `text_content`）
    - _Requirements: 4.1, 10.5_ / _Design: Source_Snapshot_Hash 计算口径 + 决策 D8 + D9_

  - [ ] 4.2 实现 snapshot_on_confirm / mark_section_stale / clear_section_stale / get_section_states / detect_upstream_drift
    - snapshot_on_confirm：confirm 时为每个保留章节 upsert 快照 + 清 stale（需求 4.1/4.6），接入任务 3.2 confirm 流程；签名以 word_export_task_id 为键
    - mark_section_stale：供 StalePropagationEngine 调用置 is_stale=true
    - clear_section_stale：增量/全量刷新后清 stale + 更新快照
    - get_section_states：供 Lineage_Panel + 冲突检测查询
    - detect_upstream_drift：当前 DB 内容哈希 ≠ 基线 hash → 上游已独立修改（供需求 8）
    - _Requirements: 4.1, 4.6_ / _Design: 组件 3 方法签名_

  - [ ] 4.3 复用 DeliverableSnapshotService 实现分层 stale 检测（先 tb_hash 整份闸门，变了才逐章算）
    - 复用现有 `DeliverableSnapshotService.tb_hash` 作整份闸门：先比对 doc 级 `tb_hash` 判断整份是否变化（廉价闸门）
    - 仅当 `tb_hash` 变化时，再逐章节调 `compute_source_snapshot_hash` 算 section hash 定位具体哪些章节变更；`tb_hash` 未变时不逐章计算（需求 4.2）
    - 不新建平行章节快照体系，复用 DeliverableSnapshotService 绑 `WordExportTask.source_snapshot_refs` 的现有口径
    - _Requirements: 4.1, 4.2_ / _Design: 决策 D9 + 概述「快照分层复用」_

  - [ ]* 4.4 属性测试：confirm 计算并存储章节快照哈希
    - **Property 8: confirm 计算并存储章节快照哈希**
    - **Validates: Requirements 4.1**
    - `# Feature: deliverable-lineage-and-writeback, Property 8`
    - _Requirements: 4.1_

  - [ ]* 4.5 属性测试：快照哈希确定性
    - **Property 26: 快照哈希确定性**（多次/跨进程同输入同 hash；内容等但对象不同→同 hash）
    - **Validates: Requirements 10.5**
    - `# Feature: deliverable-lineage-and-writeback, Property 26`
    - 生成器覆盖空 text_content、中文/非 ASCII、dict 键序乱序、浮点金额
    - _Requirements: 10.5_

- [ ] 5. 前端 Lineage_Panel + 溯源查询端点 + 跨层跳转（P0）
  - router 必在 router_registry 注册（铁律）；前端复用现有溯源 UI 不新建并行体系
  - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.1_ / _Design: API 契约「溯源查询」+ 前端设计「Lineage_Panel 组件」_

  - [ ] 5.1 新增溯源查询端点 + 章节状态查询端点 + router_registry 注册
    - `GET /api/projects/{project_id}/deliverables/{word_export_task_id}/trace?section_code=&year=`（project:read），调 LinkageFacadeService.trace(deliverable)，2s 超时返回明确错误（需求 10.1）
    - `GET .../section-states`（project:read）返回 sections 列表
    - 在 `backend/app/router_registry/{group}.py` 注册（铁律）；响应经 ResponseWrapperMiddleware 包 `{code,message,data}`
    - _Requirements: 1.1, 3.1, 10.1_ / _Design: API 契约「溯源查询」「章节状态查询」_

  - [ ] 5.2 实现 Lineage_Panel.vue（参照 CellTraceDialog/ReportTracePanel/useLinkageTraceDrawer）
    - OnlyOffice JS API 取书签/光标 → 解析 anchor_name → section_code_from_anchor → 调 trace 端点（需求 3.1）
    - 展示来源类型/标识/编辑状态（含 stale 徽标）（需求 3.2）；复用 useLinkageTraceDrawer 抽屉状态，不新建并行面板（需求 3.4）
    - 全中文化（技术术语保留英文，需求 3.6）；GT 紫令牌
    - 原生 fetch 调后端须手动解 `{code,message,data}` 信封（铁律）
    - _Requirements: 3.1, 3.2, 3.4, 3.6_ / _Design: 前端设计「Lineage_Panel 组件」「书签定位说明」_

  - [ ] 5.3 实现跨层跳转 + 无锚点降级提示
    - 点击上游来源跳转入口 → 用 LinkageContract.route 经 vue-router 导航，不新建跳转逻辑（需求 3.3）
    - 无可解析锚点（旧版本出品物）→ 提示"该出品物版本不支持溯源，请重新生成"，不报错（需求 3.5）
    - _Requirements: 3.3, 3.5_ / _Design: 前端设计 + 错误处理表_

  - [ ] 5.4 前端 router 联通验证 + Playwright 实测
    - 验证 /projects/:id/deliverables/:did 路由联通、Lineage_Panel 渲染、跳转生效（getDiagnostics 过 ≠ 运行时无错，铁律）
    - _Requirements: 3.1, 3.3_

  - [ ]* 5.5 单元测试：面板渲染 + 降级提示 + 超时错误
    - 3.2（面板渲染来源/状态）、3.5（降级提示）、10.1（trace 超时返回明确错误）
    - _Requirements: 3.2, 3.5, 10.1_

- [ ] 6. 检查点 — 确保 P0 全部测试通过
  - 确保所有测试通过，如有疑问请询问用户。

---

## Phase 2（P1）：出品物 Stale 感知 + 单/批量章节增量刷新

- [ ] 7. StalePropagationEngine 扩展 DELIVERABLE: URI 前缀
  - 在 `_mark_stale_by_uri` 前缀分组逻辑新增 DELIVERABLE 分支，复用现有 `on_change → BFS → _mark_stale_by_uri → _notify_frontend` 流程，零并行引擎
  - _Requirements: 4.2, 4.4, 4.7_ / _Design: 组件「4. StalePropagationEngine 扩展」+ 决策 D5_

  - [ ] 7.1 实现 DELIVERABLE: 前缀分发 + SSE 推送
    - URI 约定 `DELIVERABLE:{word_export_task_id}:{section_code}`，UPDATE deliverable_section_state.is_stale（需求 4.2/4.4）
    - SSE 复用 `_notify_frontend`，前端经现有 LINKAGE_STALE_CHANGED 事件感知，不新建推送通道（需求 4.7）
    - 复用现有 `_fallback_mark_stale` 降级路径（图未加载场景）
    - _Requirements: 4.2, 4.4, 4.7_ / _Design: 组件 4 + 错误处理表_

  - [ ]* 7.2 属性测试：DELIVERABLE: URI 标记正确行
    - **Property 9: DELIVERABLE: URI 标记正确行**（恰好对应行置 stale，WP/REPORT/NOTE 不受影响）
    - **Validates: Requirements 4.2, 4.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 9`
    - _Requirements: 4.2, 4.4_

- [ ] 8. event_handlers 新增 deliverable stale handler + 自触发防护
  - 订阅现有事件（调整分录变更、REPORTS_UPDATED、NOTE_SECTION_SAVED），不新建事件类型
  - _Requirements: 4.3, 4.9_ / _Design: 组件「5. event_handlers 新增 handler」+ 决策 D6_

  - [ ] 8.1 实现 on_upstream_changed_mark_deliverable_stale handler
    - 由变更 section_code/row_code 反查依赖它的出品物章节（deliverable_section_state，用 idx_dss_section）
    - 对受影响 (word_export_task_id, section_code) 调 StalePropagationEngine on_change(`DELIVERABLE:...`)（需求 4.3）
    - _Requirements: 4.3_ / _Design: 组件 5 流程_

  - [ ] 8.2 实现自触发 stale 循环防护
    - 若 payload.extra.get('writeback_source_deliverable_id') == 本出品物 word_export_task_id → 跳过该出品物（但仍标其他依赖同一附注的出品物）；事件 extra 的语义键名沿用 `writeback_source_deliverable_id`，其值=来源出品物 word_export_task_id（需求 4.9）
    - _Requirements: 4.9_ / _Design: 决策 D6_

  - [ ]* 8.3 属性测试：上游变更标记依赖出品物章节 stale
    - **Property 10: 上游变更标记依赖出品物章节 stale**
    - **Validates: Requirements 4.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 10`
    - _Requirements: 4.3_

  - [ ]* 8.4 属性测试：自回填不标记来源出品物自身 stale
    - **Property 11: 自回填不标记来源出品物自身 stale**
    - **Validates: Requirements 4.9**
    - `# Feature: deliverable-lineage-and-writeback, Property 11`
    - _Requirements: 4.9_

  - [ ]* 8.5 单元测试：EventBus 发布 stale 状态变更
    - 4.7（stale 状态变更经 EventBus + SSE 推送）
    - _Requirements: 4.7_

- [ ] 9. ⚠️ 单/批量章节增量刷新【阻塞于 G1+G2】
  - 复用 `_export_template_mode` 章节块定位（scan_section_blocks / delete_section_block），不全量重生成；WHERE `USE_TEMPLATE_FILL_SERVICE=false` 标"阻塞中"（需求 5.6）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 4.6, 11.1, 11.3_ / _Design: 组件「7. 单章节增量刷新」_

  - [ ] 9.1 实现 refresh_section（单章节增量刷新）+ 端点
    - 主流程开头终态检查（需求 11.1/11.3）：查 WordExportTask.status，若 ∈ {signed, confirmed, archived} 终态 → 拦截并提示终态约束（中文："该出品物已签字/确认/归档，不可回填或刷新；如需修改请走撤回/解锁流程"），不创建新版本；复用现有 create_version 归档锁同一判定（TERMINAL_REEXPORT_STATUSES）
    - 下载当前 docx → scan_section_blocks 经 Section_Anchor 定位目标块（需求 5.2）
    - 覆盖用户已编辑内容 → 需用户确认（需求 5.5）；delete_section_block + 最新 disclosure_notes 内容重填
    - 仅更新该章节 source_snapshot_hash + 清 stale，不影响其他章节（需求 5.3）；经 DeliverableService 创建新版本 version_no+1（需求 5.4）
    - `POST .../refresh-section`（project:write）+ router_registry 注册
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 4.6, 11.1, 11.3_ / _Design: 组件 7 + API 契约「单/批量刷新」_

  - [ ] 9.2 实现 refresh_all_stale_sections（批量刷新）+ 端点
    - 主流程开头同样做终态检查（需求 11.1/11.3）：终态出品物（signed/confirmed/archived）拦截，不创建新版本，复用 create_version 归档锁同一判定
    - 逐章节复用 refresh_section，保留未过期且已人工编辑章节，覆盖人工编辑按 5.5 统一提示确认（需求 5.7）
    - `POST .../refresh-stale`（project:write），>100 章节走异步（任务 15 接线）
    - _Requirements: 5.7, 11.1, 11.3_ / _Design: 组件 7 + API 契约_

  - [ ]* 9.3 属性测试：增量刷新只影响目标 stale 章节集合
    - **Property 12: 增量刷新只影响目标 stale 章节集合**
    - **Validates: Requirements 5.1, 5.3, 5.7**
    - `# Feature: deliverable-lineage-and-writeback, Property 12`
    - 生成器覆盖 stale/非 stale 混合章节
    - _Requirements: 5.1, 5.3, 5.7_

  - [ ]* 9.4 属性测试：刷新后目标章节内容等于最新附注
    - **Property 13: 刷新后目标章节内容等于最新附注**
    - **Validates: Requirements 5.2**
    - `# Feature: deliverable-lineage-and-writeback, Property 13`
    - _Requirements: 5.2_

  - [ ]* 9.5 属性测试：刷新/回填创建新版本且保留旧版本
    - **Property 14: 刷新/回填创建新版本且保留旧版本**
    - **Validates: Requirements 5.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 14`
    - _Requirements: 5.4_

  - [ ]* 9.6 属性测试：基线对账（刷新/裁决写回后）
    - **Property 15: 基线对账**（刷新/裁决后清 stale + 基线 hash = 当前源内容 hash）
    - **Validates: Requirements 4.6, 8.6**
    - `# Feature: deliverable-lineage-and-writeback, Property 15`
    - _Requirements: 4.6, 8.6_

  - [ ]* 9.7 单元测试：覆盖人工编辑确认
    - 5.5（增量刷新覆盖人工编辑前提示确认）
    - _Requirements: 5.5_

- [ ] 10. 前端 stale 展示 + 刷新按钮（P1）
  - _Requirements: 4.5, 5.5, 11.4_ / _Design: 前端设计「OnlyOffice 集成点」_

  - [ ] 10.1 Lineage_Panel 章节 stale 提示 + "刷新本章节"/"刷新所有过期"按钮
    - stale 章节显示"源数据已变更"提示（需求 4.5）；工具栏新增两个刷新按钮调任务 9 端点
    - "刷新本章节"覆盖人工编辑前弹确认（需求 5.5）；经 SSE LINKAGE_STALE_CHANGED 实时更新徽标
    - **终态出品物只读（需求 11.4）**：当出品物处于 signed/confirmed/archived 终态时，Lineage_Panel 溯源仍可查看（只读），但禁用"刷新本章节"/"刷新所有过期"入口（按钮 disabled + 悬浮提示"该出品物已签字/确认/归档，不可回填或刷新"）
    - 全中文化 + GT 紫令牌
    - _Requirements: 4.5, 5.5, 11.4_ / _Design: 前端设计 OnlyOffice 集成点 + 需求 11.4_

  - [ ] 10.2 前端刷新流程 Playwright 实测
    - 验证 stale 徽标实时更新 + 刷新按钮联通 + 覆盖确认弹窗 + 终态出品物刷新入口禁用
    - _Requirements: 4.5, 5.5, 11.4_

- [ ] 11. 检查点 — 确保 P1 全部测试通过
  - 确保所有测试通过，如有疑问请询问用户。

---

## Phase 3（P2）：回填合规护栏 + OnlyOffice 回填管道 + 冲突检测 + 留痕 + 非功能闸门

- [ ] 12. 回填合规护栏分类算法（审计底线，强制 PBT）
  - 审计合规底线：仅文字说明可回填，金额/表格严禁倒灌，标题忽略；护栏是写回前置闸门
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.5_ / _Design: 「回填合规护栏设计」_

  - [ ] 12.1 实现 _classify_change 字段分类（TEXT/TABLE/TITLE）
    - 按块内结构定位（非正则猜测）：`<w:tbl>` 数字单元格→TABLE 拒绝；块首标题行（{{seq:}} 编号+名称）→TITLE 忽略；其余正文段落→TEXT 放行
    - 表格/标题拒绝项携带"金额变更须通过调整分录（AJE/RJE）修正"中文指引（需求 6.3/6.6）
    - 仅 TEXT 写回 text_content，table_data 永不修改（需求 6.1/6.2/6.5/7.5）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5_ / _Design: 变更项字段分类算法 + 分类处置矩阵_

  - [ ]* 12.2 属性测试：回填合规护栏分类（审计底线，需求 6.7 强制覆盖）
    - **Property 16: 回填合规护栏分类**（仅文字写回；table_data 绝不改；标题忽略；表格/标题拒绝含 AJE 指引）
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5**
    - `# Feature: deliverable-lineage-and-writeback, Property 16`
    - 必须覆盖金额/表格/标题被拒 + 仅文字放行四类用例（需求 6.7 审计底线）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.5_

- [ ] 13. ⚠️ DeliverableWritebackService（下载→分块→diff→护栏→写回）【阻塞于 G1+G2】
  - 显式按钮触发，复用 scan_section_blocks 按锚点分块；依赖任务 3（锚点）+ 12（护栏）
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.8, 7.9, 11.1, 11.3_ / _Design: 组件「6. DeliverableWritebackService」+「章节级 diff」_

  - [ ] 13.1 实现章节级 diff（下载 docx → 按锚点分块 → 文本比对）
    - 下载最新已保存 docx → scan_section_blocks 按书签区间切块 → 提取 TEXT 段落文字（剔标题/表格）→ 与 DB text_content 比对
    - `normalize()` 去首尾空白/统一换行/合并连续空白，消除格式噪声；自行计算章节级 diff（OnlyOffice 不提供段落级 diff，需求 7.3/7.4）
    - _Requirements: 7.3, 7.4_ / _Design: 章节级 diff 算法 + 决策 D4_

  - [ ] 13.2 实现 writeback 主流程 + 终态检查 + 锚点丢失隔离 + 失败保留原值
    - 主流程开头终态检查（需求 11.1/11.3）：查 WordExportTask.status，若 ∈ {signed, confirmed, archived} 终态 → 拒绝回填，返回中文说明（"该出品物已签字/确认/归档，不可回填或刷新；如需修改请走撤回/解锁流程"），不创建新版本；复用现有终态判定常量（TERMINAL_REEXPORT_STATUSES / create_version 对 archived 抛 ValueError 的同一判定）
    - 锚点缺失/损坏章节 → 跳过列入 skipped[]，不影响其他章节（需求 7.9）
    - 经护栏分类后仅文字变更写回 text_content（需求 7.5）；写回成功触发 NOTE_SECTION_SAVED，extra 携带 writeback_source_deliverable_id（值为来源出品物 word_export_task_id，需求 7.6 + 4.9）
    - 下载/解析失败 → 中止本次、保留 DB 原值、记录原因（需求 7.8）
    - WritebackResult 含 written[]/rejected[]/conflicts[]/skipped[]/trace_id
    - _Requirements: 7.3, 7.5, 7.6, 7.8, 7.9, 11.1, 11.3_ / _Design: 组件 6 writeback docstring + 错误处理表_

  - [ ]* 13.3 属性测试：章节级 diff 精确识别变更章节
    - **Property 17: 章节级 diff 精确识别变更章节**
    - **Validates: Requirements 7.3, 7.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 17`
    - _Requirements: 7.3, 7.4_

  - [ ]* 13.4 属性测试：部分锚点丢失的隔离处理
    - **Property 18: 部分锚点丢失的隔离处理**
    - **Validates: Requirements 7.9**
    - `# Feature: deliverable-lineage-and-writeback, Property 18`
    - 生成器覆盖部分章节锚点被删/破坏
    - _Requirements: 7.9_

  - [ ]* 13.5 属性测试：终态出品物禁止回填与刷新
    - **Property 28: 终态出品物禁止回填与刷新**（终态 signed/confirmed/archived 出品物触发 writeback 或 refresh_section/refresh_all_stale_sections 必被拒绝，且不创建新版本 version_no 不递增）
    - **Validates: Requirements 11.1, 11.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 28`
    - hypothesis max_examples=5；生成器覆盖三类终态 + 非终态对照
    - _Requirements: 11.1, 11.3_

  - [ ]* 13.6 单元测试：自动保存不回填 + 携带来源标记 + 下载失败保留原值
    - 7.1/7.2（自动保存仅存文件不回填）、7.6（NOTE_SECTION_SAVED 携带来源标记）、7.8（下载失败保留原值）
    - _Requirements: 7.1, 7.2, 7.6, 7.8_

- [ ] 14. 回填冲突检测（三方比对）
  - 复用 LinkageFacadeService 已有 conflict/stale 能力 + detect_upstream_drift（任务 4），不新建判定逻辑
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_ / _Design: 「三方比对冲突检测」+ 组件「冲突三方模型」_

  - [ ] 14.1 实现三方比对冲突检测 + 裁决写回 + 基线更新
    - 冲突判定：current_db_hash ≠ baseline_hash（上游已独立改，需求 8.1）；双方改成一样→幂等跳过
    - 真冲突 → 暂停该章节，呈现 WritebackConflict 三方内容（deliverable_value/upstream_value/baseline_value），不静默覆盖（需求 8.2/8.3）
    - 裁决经 resolutions 参数回传（复用回填端点）；写回后更新 source_snapshot_hash 基线（需求 8.6）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_ / _Design: 三方比对冲突检测算法_

  - [ ]* 14.2 属性测试：冲突检测谓词
    - **Property 19: 冲突检测谓词**（冲突 ⟺ 当前 DB hash ≠ 基线 hash）
    - **Validates: Requirements 8.1**
    - `# Feature: deliverable-lineage-and-writeback, Property 19`
    - _Requirements: 8.1_

  - [ ]* 14.3 属性测试：冲突呈现三方且非裁决不写回
    - **Property 20: 冲突呈现三方且非裁决不写回**
    - **Validates: Requirements 8.2, 8.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 20`
    - _Requirements: 8.2, 8.3_

- [ ] 15. 回填留痕（复用 TraceEventService）
  - 复用现有 L1/L2/L3 回放，不新建留痕表/服务
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 7.7, 8.5_ / _Design: 组件 6 第 9 步 + API 契约「留痕回放」_

  - [ ] 15.1 接入 TraceEventService.write 留痕（含被拒变更）
    - 每次回填/冲突裁决写回经 TraceEventService.write 记录（before/after snapshot + content_hash，需求 9.1/9.2/7.7/8.5）
    - 包含操作人/时间/出品物标识与版本/section_code/before-after text_content（需求 9.2）
    - 被护栏拒绝的变更同样留痕 + 拒绝原因（需求 9.3）
    - 复用既有"写入失败不阻断主业务"语义
    - _Requirements: 9.1, 9.2, 9.3, 7.7, 8.5_ / _Design: 组件 6 + 错误处理表_

  - [ ]* 15.2 属性测试：回填留痕写入→回放往返
    - **Property 21: 回填留痕写入→回放往返**
    - **Validates: Requirements 7.7, 8.5, 9.1, 9.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 21`
    - _Requirements: 7.7, 8.5, 9.1, 9.4_

  - [ ]* 15.3 属性测试：留痕字段完整性
    - **Property 22: 留痕字段完整性**
    - **Validates: Requirements 9.2**
    - `# Feature: deliverable-lineage-and-writeback, Property 22`
    - _Requirements: 9.2_

  - [ ]* 15.4 属性测试：被拒变更留痕
    - **Property 23: 被拒变更留痕**
    - **Validates: Requirements 9.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 23`
    - _Requirements: 9.3_

- [ ] 16. 前端回填按钮 + 冲突裁决弹窗（P2）
  - _Requirements: 7.1, 8.2, 8.3, 11.4_ / _Design: 前端设计「OnlyOffice 集成点」_

  - [ ] 16.1 实现"回填到附注模块"按钮 + WritebackResult 分组展示
    - 显式按钮触发回填（需求 7.1）；展示成功/拒绝/冲突/跳过分组；拒绝项显示中文 AJE 指引
    - **终态出品物只读（需求 11.4）**：当出品物处于 signed/confirmed/archived 终态时，禁用"回填到附注模块"入口（按钮 disabled + 悬浮提示"该出品物已签字/确认/归档，不可回填或刷新"），溯源面板仍可只读查看
    - 全中文化 + GT 紫令牌
    - _Requirements: 7.1, 11.4_ / _Design: 前端设计 OnlyOffice 集成点 + 需求 11.4_

  - [ ] 16.2 实现冲突三方裁决弹窗
    - 三栏对照（出品物值/上游值/基线值）+ 单选保留方 → 收集后再次提交 resolutions（需求 8.2/8.3）
    - _Requirements: 8.2, 8.3_ / _Design: 前端设计 + 冲突裁决_

  - [ ] 16.3 前端回填流程 Playwright 实测
    - 验证回填按钮 → WritebackResult 展示 → 冲突弹窗 → 裁决提交闭环
    - _Requirements: 7.1, 8.2, 8.3_

- [ ] 17. 非功能闸门：权限 + app_audit_log + 异步 job
  - _Requirements: 10.2, 10.3, 10.4, 10.6_ / _Design: API 契约权限 + 错误处理表 + 决策 D7_

  - [ ] 17.1 回填/刷新权限闸门
    - 回填写回受 project:write（或等同附注编辑权限）控制；无权限 403；project:read 仅可查看溯源面板不能触发回填（需求 10.3）
    - _Requirements: 10.3_ / _Design: API 契约权限_

  - [ ] 17.2 回填/刷新写 app_audit_log
    - 所有回填与刷新操作经 audit_logger 写 app_audit_log（注意 audit_log 是 Metabase no-op，必须写独立表 app_audit_log，铁律）（需求 10.4）
    - _Requirements: 10.4_ / _Design: 错误处理表事务边界_

  - [ ] 17.3 大文档异步 job 接线（>100 章节）
    - 回填/全量刷新章节数 >100 走现有 export_jobs_v2 返回 job_id + 进度，不阻塞主 API；单章节失败隔离（需求 10.2）
    - _Requirements: 10.2_ / _Design: 决策 D7 + 错误处理表_

  - [ ]* 17.4 属性测试：回填权限闸门
    - **Property 24: 回填权限闸门**
    - **Validates: Requirements 10.3**
    - `# Feature: deliverable-lineage-and-writeback, Property 24`
    - _Requirements: 10.3_

  - [ ]* 17.5 属性测试：应用审计日志写入
    - **Property 25: 应用审计日志写入**
    - **Validates: Requirements 10.4**
    - `# Feature: deliverable-lineage-and-writeback, Property 25`
    - _Requirements: 10.4_

  - [ ]* 17.6 属性测试：现有四类源向后兼容
    - **Property 27: 现有四类源向后兼容**（tb/workpaper/note/report trace 上线前后一致）
    - **Validates: Requirements 10.6**
    - `# Feature: deliverable-lineage-and-writeback, Property 27`
    - 黄金值对照
    - _Requirements: 10.6_

- [ ] 18. 检查点 — 确保 P2 全部测试通过
  - 确保所有测试通过，如有疑问请询问用户。

---

## 收尾

- [ ] 19. 文档与 memory 更新
  - [ ] 19.1 更新 spec 状态与 memory
    - `.kiro/specs/INDEX.md` 标注本 spec 状态；附录 A 服务职责对照核对实施后目标态
    - 更新 `.kiro/steering/memory.md` 任务状态节（标注本 spec 完成情况、V067 迁移、门控解除情况）
    - 一次性 POC 脚本（`_poc_section_anchor.py`）用完即删（铁律）
    - _Requirements: 全部（收尾）_

---

## 备注

- 标 `*` 的子任务为可选（属性测试 / 单元测试 / 前端实测）；按用户铁律，`*` 任务也要做完（除非明确跳过）；顶层任务不标 `*`。
- 编码代理 SHALL 实现未标 `*` 的子任务；标 `*` 的属性/单元测试任务亦须实现并跑通（max_examples=5）。
- ⚠️ 任务硬阻塞于 START GATE（G1 模板整理 + G2 `USE_TEMPLATE_FILL_SERVICE=true`）；门控未解除前不得开始编码。
- 28 条属性测试逐条对应 design.md 正确性属性，每条注释标 `# Feature: deliverable-lineage-and-writeback, Property N`；Property 16（合规护栏）与 Property 26（哈希确定性）为审计底线，强制覆盖。
- 三层一致铁律：V067 迁移 DDL + ORM（DeliverableSectionState 继承 TimestampMixin）+ service，配 R067 回滚 + 契约测试（任务 1）。
- router 必在 router_registry 注册（任务 5/9/13/14 涉及端点）。
- 验证：后端 `rtk python -m pytest`；前端 vitest + Playwright（getDiagnostics 过 ≠ 运行时无错）。

---

## 工作流完成说明

本工作流仅用于生成设计与规划产物（requirements / design / tasks 三件套）。tasks.md 已创建完成，**本工作流到此结束，不在本阶段实施功能**。

你可以开始执行任务：

- 打开 `tasks.md` 文件；
- 点击任务项旁的"Start task"开始逐项实施。
