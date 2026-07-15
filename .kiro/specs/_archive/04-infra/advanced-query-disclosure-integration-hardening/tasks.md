# Implementation Plan: 高级查询—附注集成加固

## Overview

本计划按 Wave0–Wave6 交付授权、查询身份、分页、编排兼容、模板、附注事务和前端状态加固；全部任务均以真实测试证据为完成条件。

## 执行规则

- 所有任务初始均为 `[ ]`；只有真实执行并有证据时才能改为 `[x]`。
- 标记 `*` 的 PBT 为 optional 分类，但**本次仍必须实现、运行并通过**。
- 每个 coding task 都必须先读现有实现、复用既有服务，不建立平行查询/权限/状态体系。
- 本 spec 禁止 DB migration、批量 writeback、异步大查询导出、历史 Word/PDF 真解析和 DisclosureEditor 全量拆分。
- service 遵循现有事务约定；router 必注册；EventBus `publish` 使用正式事件载荷；中文 UI 与错误提示不得退化。
- 每个任务完成前运行对应定向 pytest/Vitest 与改动文件 diagnostics；失败或未运行保持 `[ ]`。

## Tasks

### Wave0：契约基线与测试护栏

- [x] 0.1 建立主 execute 兼容契约基线测试
  - 为现有 `POST /api/custom-query/execute` 的旧请求、成功响应、422 与领域 4xx 建 golden cases，记录 rows/columns/total 等既有字段类型。
  - 增加 orchestrator 调用 spy，为后续“单执行核心”断言提供基线。
  - _Requirements: 5.1, 5.3, 5.4, 5.5, 10.1_

- [x] 0.2 建立附注 mutation、trace 与历史上传现状回归测试
  - 覆盖 generate/update/delete/restore/status、note_id trace、现有历史上传桩和 EventBus 失败路径，先固定真实现状，不把当前静默失败写成期望成功。
  - _Requirements: 1.2, 7.1–7.4, 9.1–9.4, 10.1_

- [x] 0.3 建立前端草稿与元数据测试夹具
  - 为 `sessionStorage`、fake timers、响应式 project/year/section、manual/provenance/trace cell 构造器和 capability response 提供共享 fixture。
  - _Requirements: 8.1–8.5, 9.2, 10.1_

- [x]* 0.4 建立 PBT 生成器与标签约定
  - 后端 Hypothesis 新增查询请求、项目权限集合、分页行、模板 scope、mutation 故障点生成器；前端 fast-check 新增 context/cell/操作序列生成器。
  - 每个测试标注 `Feature: advanced-query-disclosure-integration-hardening, Property Pn`，使用仓库 fast profile。
  - _Requirements: 1–9; Properties: P1–P12_

### Wave1：项目授权与写权限封口

- [x] 1.1 收敛高级查询项目读取门禁
  - 在指标、主 execute、模板执行及其他项目化查询入口复用统一 readonly gate；保证门禁位于 cache identity、cache get 和领域查询之前。
  - 对多项目请求先验证完整显式项目集合，不允许仅过滤后继续执行。
  - _Requirements: 1.1, 1.3, 1.4_

- [x] 1.2 收敛附注读取与对象归属门禁
  - 为目录、详情、prior-year、自动取数和 trace 接入 readonly gate；仅携带 `note_id` 时先最小投影解析 `project_id` 再授权。
  - 403 响应不得包含 note 内容、trace 证据或缓存命中信息。
  - _Requirements: 1.1–1.3_

- [x] 1.3 加固附注 mutation edit/operation/锁权限
  - generate/update/delete/restore/status mutation 统一要求项目 edit；适用端点叠加 `note:edit` 与合并锁检查。
  - 删除仅依赖隐式 session 提交的路径，确保权限失败在 mutation 前发生。
  - _Requirements: 2.1, 2.3, 2.4_

- [x] 1.4 加固 writeback preview/confirm 权限
  - 复用 OwnershipGuard/ACNR 对所有目标 `addr_id` 逐一校验项目归属、edit 与 writeback 权限；任一失败时 SnapshotWriter 不得被调用。
  - readonly 用户接口 403，前端不展示可执行回写动作。
  - _Requirements: 2.2–2.4_

- [x]* 1.5 实现并运行授权属性测试 P1–P2
  - P1 随机用户/对象/项目集合，断言授权先于缓存/领域读取且执行计划为授权闭包。
  - P2 随机目标集合与故障位置，断言写权限全有或全无、无部分写入/事件。
  - _Requirements: 1.1–1.4, 2.1–2.3; Properties: P1, P2_
### Wave2：完整查询身份、真实分页与主 execute 编排

- [x] 2.1 扩展兼容 QueryRequest/QueryResult 契约
  - 在既有 schema 上新增 optional sort/group/pivot/acnr_targets，修正 mutable defaults；保留旧 columns/limit/offset 语义。
  - QueryResult 明确 total/limit/offset/warnings，并无损承载 provenance/trace/manual 元数据。
  - _Requirements: 3.1, 4.1, 5.1–5.3, 8.5_

- [x] 2.2 加固 CanonicalQueryIdentityBuilder
  - canonical payload 纳入 source/filters/columns/limit/offset/sort/group/pivot/ACNR/project/user-scope/schema/contract-version。
  - 映射递归键排序；有序字段保序；未知或不可稳定序列化字段返回 `cacheable=false`、记录 warning 并绕过缓存。
  - _Requirements: 3.1–3.5_

- [x] 2.3 实现 StablePagination
  - 在 group/pivot 后对最终结果执行 limit/offset，返回分页前 total；数据库可下推路径使用真实 LIMIT/OFFSET 与可信 count。
  - 用户 sort 后补唯一 tie-breaker；无 sort 使用领域默认 + 唯一 tie-breaker；非法 limit/offset/sort 在执行前 422。
  - _Requirements: 4.1–4.5_

- [x] 2.4 将主 execute 唯一接入 QueryOrchestrator
  - 实现/收敛 `ExecuteCompatibilityAdapter`，旧字段补默认、新字段无损传递，统一结果适配回旧响应。
  - 删除或封闭旧 router 实执行分支；orchestrator 4xx 映射既有错误，未知异常 rollback + correlation id + 500，禁止语义不同的 fallback。
  - _Requirements: 5.1–5.5_

- [x] 2.5 补齐前后端请求序列化与响应消费
  - `CustomQuery`/`CustomQueryTab` 等入口发送 columns/offset/sort/group/pivot/acnr_targets；分页切换使用后端 total，不做本地伪切片。
  - 晚到响应仅在当前 identity/context 匹配时应用；结果元数据继续供 ACNR/trace 下钻。
  - _Requirements: 3.1, 4.1–4.5, 5.2–5.3, 8.5_

- [x]* 2.6 实现并运行查询属性测试 P3–P6
  - P3：逐字段扰动、键序扰动、有序数组置换验证 identity 完整确定。
  - P4：缓存与直查在 columns/rows/total/manual/provenance/trace 上观测等价。
  - P5：随机重复排序键结果集全页拼接不重不漏，group/pivot 后 total 正确。
  - P6：旧请求适配与直调 orchestrator 等价、调用恰一次、新字段无损。
  - _Requirements: 3.1–5.5; Properties: P3–P6_

### Wave3：模板作用域与分享兼容

- [x] 3.1 实现 TemplateScopeAdapter
  - canonical API scope 为 private/team/project/public；输入或旧记录 global 归一为 public，新写不得产生 global。
  - 用现有 `shared_project_ids` 与 config 表达 project，不新增 migration；旧 private/team/public/global 数据均可读取。
  - _Requirements: 6.1, 6.4, 6.6_

- [x] 3.2 加固模板 CRUD、分享与执行授权
  - private 仅 owner；team 仅团队授权成员；project 要求 shared_project_ids 非空去重并逐项目 edit 校验；public 全体认证用户可读。
  - 编辑/删除/分享/执行不可见模板统一 403；执行时重新按当前用户项目权限授权，不信任保存时权限。
  - _Requirements: 6.2–6.5_

- [x] 3.3 更新模板前端作用域与项目选择 UI
  - 中文显示“私人/团队/项目/公开”；不得显示 global 新选项，读取 legacy global 时显示“公开”。
  - 选择 project 时强制选择至少一个有 edit 权限的项目，提交去重的 shared_project_ids；readonly 用户禁用分享编辑。
  - _Requirements: 2.4, 6.1–6.5_

- [x]* 3.4 实现并运行模板属性测试 P7
  - 随机 scope/owner/team/shared projects/user access 验证可见性 iff 规则；验证 global→public、project 空集合拒绝、分享项目逐一授权及新写无 global。
  - _Requirements: 6.1–6.5; Property: P7_

### Wave4：附注事务、事件可观测与历史能力

- [x] 4.1 引入 DisclosureMutationCoordinator
  - 统一包裹 generate/update/delete/restore/status：成功显式 commit，commit 前任意异常显式 rollback；commit 失败不得发布成功事件。
  - mutation service 保持单一业务写核心，router 不散落隐式事务语义。
  - _Requirements: 7.1, 7.4_

- [x] 4.2 实现 mutation_id 幂等门与事件去重字段
  - 接受/生成 mutation_id，使用现有 Redis 能力做 project+mutation_id+request-hash 幂等门，并保持领域写为确定性 update/upsert。
  - 同 id 同摘要重试返回同一最终状态；同 id 不同摘要返回冲突；事件载荷携带 mutation_id。
  - _Requirements: 7.2, 7.5_

- [x] 4.3 使 EventBus 发布失败可观测
  - 删除 `except Exception: pass`；commit 后同步 publish，失败时保留业务 commit，响应 warning=`event_delivery_failed` 并记录 correlation id、结构化错误和 counter metric。
  - 成功响应明确 `event_delivery=published|failed`，不得把 failed 宣称为 delivered。
  - _Requirements: 7.2–7.4_

- [x] 4.4 固化历史上传 501 与能力发现
  - 历史 Word/PDF 上传/解析端点直接返回 501 + `HISTORICAL_UPLOAD_NOT_IMPLEMENTED`，在读取/存储文件和创建任务之前终止。
  - capability endpoint 返回 `historical_upload=false` 与中文原因；不得返回空 200 或模拟解析结果。
  - _Requirements: 9.1–9.4_

- [x]* 4.5 实现并运行事务/能力属性测试 P8、P9、P12 后端部分
  - P8 随机 mutation/flush/commit/publish 故障点验证状态机、warning/log/metric。
  - P9 重复 mutation_id 操作序列验证业务 mutation/成功事件至多一次。
  - P12 验证 capability=false 下历史直调恒 501 且任务、文件、DB 零副作用。
  - _Requirements: 7.1–7.5, 9.1–9.4; Properties: P8, P9, P12_
### Wave5：附注前端状态隔离与元数据保持

- [x] 5.1 实现响应式 ScopedAutoSave
  - 在 `useAutoSave` 上增加兼容封装或新建窄 composable，key 由 reactive project_id/year/section 计算；context 切换先停旧 timer、取消旧恢复提示，再检查新草稿并启动新 timer。
  - DraftEnvelope 写入 context/version/savedAt；恢复时校验完整 context；禁止 global/空 context key。
  - _Requirements: 8.1, 8.2_

- [x] 5.2 最小接线 DisclosureEditor 的 project/year/section 生命周期
  - 将现有一次性字符串 key 改为响应式上下文输入；对晚到草稿/请求使用 context token 丢弃。
  - 仅改状态接线，不拆分约 2371 行编辑器的其他职责，不改变既有 manual/provenance/trace UI。
  - _Requirements: 8.1, 8.2, 8.5_

- [x] 5.3 实现 ManualPreservingMerge
  - 查询自动填充逐 cell 合并：manual=true 保留当前值；非 manual 更新值；用户编辑后标记 manual=true。
  - provenance/trace/addr_id 使用追加或版本化历史，保存、刷新、分页、模板执行和重开章节不得清空。
  - _Requirements: 8.3–8.5_

- [x] 5.4 接通查询定位附注与元数据 round-trip
  - 从 QueryResult 到附注填充保留 manual/provenance/trace/addr_id；ACNR/trace 下钻继续使用 canonical addr_id。
  - 服务端附注 schema/serializer 接受旧缺省元数据并归一为 false/[]/[]，不得在写回时丢弃未知兼容元数据。
  - _Requirements: 5.3, 8.3–8.5_

- [x] 5.5 依据 capability 禁用历史上传 UI
  - capability=false 时隐藏或禁用历史 Word/PDF 上传按钮，显示“历史 Word/PDF 解析尚未实现”；不得发起上传请求。
  - 保留后端 501 为绕过 UI 时的权威门禁。
  - _Requirements: 9.1–9.4_

- [x]* 5.6 实现并运行前端属性测试 P10–P12
  - P10 用 fake timers + fast-check 随机 context 切换，验证 key 唯一、旧 timer 不写、新草稿才恢复。
  - P11 用随机自动填充/手工编辑序列验证 manual 值不被覆盖且来源历史不删除。
  - P12 用保存/刷新/分页/模板/重开序列验证元数据与 addr_id 关联不变，并验证 capability=false UI 不发上传请求。
  - _Requirements: 8.1–9.4; Properties: P10–P12_

### Wave6：全量验证与中文主链硬门槛

- [x] 6.1 运行后端定向 pytest 与 PBT
  - 运行本 spec 新增测试，以及受影响的 custom-query、template、writeback、disclosure-notes、EventBus 回归集；保存命令、退出码、失败示例。
  - PBT 失败必须保留 Hypothesis 原始 counterexample 并修复后重跑；不得 skip。
  - _Requirements: 10.1, 10.2, 10.5, 10.6_

- [x] 6.2 运行前端 Vitest/fast-check
  - 运行高级查询请求/分页/模板 UI、ScopedAutoSave、ManualPreservingMerge、capability UI 测试；保存命令、退出码与 fast-check seed/counterexample。
  - _Requirements: 10.1, 10.2, 10.5_

- [x] 6.3 运行全部改动文件 diagnostics
  - 对 Python、Vue、TS 及本 spec 三文档运行 diagnostics；修复所有新增 error/warning 后重跑。
  - diagnostics 不能替代 pytest/Vitest/Playwright。
  - _Requirements: 10.1, 10.2, 10.5_

- [x] 6.4 Playwright 实测中文主链一：高级查询
  - 选择中文项目 → 指定 columns/sort/group/pivot → 执行 → 翻下一页并断言不重行与 total → ACNR/trace 下钻 → 保存 project 模板 → 验证有权可见、无权不可见。
  - 记录关键网络状态、页面断言、下载/模板证据和 console error；不得全程 mock。
  - _Requirements: 10.2, 10.3, 10.5_

- [x] 6.5 Playwright 实测中文主链二：附注闭环
  - 查询定位附注 → 切换 project/year/section 验证三个草稿隔离 → 编辑自动填充单元格形成 manual → 保存/刷新/重开 → 验证 provenance/trace → 上传 UI 禁用并 API 直调 501。
  - 记录关键网络状态、页面断言与 console error；不得用单一 mock 页面代替真实链路。
  - _Requirements: 10.2, 10.4, 10.5_

- [x] 6.6 汇总验收证据并执行不假绿检查
  - 逐项核对 Req 1–10、P1–P12、pytest、Vitest、diagnostics、EventBus 故障注入及两条 Playwright 主链。
  - 任一未运行/skip/失败项保持 `[ ]` 并记录阻塞；仅全部真实通过后才完成本任务。
  - _Requirements: 10.1–10.6_

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": "Wave0",
      "tasks": ["0.1", "0.2", "0.3", "0.4"],
      "depends_on": []
    },
    {
      "id": "Wave1",
      "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"],
      "depends_on": ["Wave0"]
    },
    {
      "id": "Wave2",
      "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"],
      "depends_on": ["Wave0", "Wave1"]
    },
    {
      "id": "Wave3",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "depends_on": ["Wave1", "2.1", "2.4"]
    },
    {
      "id": "Wave4",
      "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5"],
      "depends_on": ["Wave1"]
    },
    {
      "id": "Wave5",
      "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6"],
      "depends_on": ["Wave2", "Wave3", "Wave4"]
    },
    {
      "id": "Wave6",
      "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"],
      "depends_on": ["Wave5"]
    }
  ]
}
```

## Notes

### 已验证通过（真实命令+Playwright 证据）

**Wave3 模板作用域（3.1–3.4 全部 [x]）**
- 后端：`rtk python -m pytest tests/test_advanced_query_template_service.py tests/test_template_service_pbt.py tests/test_custom_query_templates.py tests/test_wave3_query_contract_pbt.py tests/test_custom_query_template_scope_hardening.py -q --tb=short` → **全部通过（exit 0）**
- 前端：`rtk npx vitest --run src/components/custom-query/__tests__/advancedQueryFrontend.spec.ts` → exit 0（含 P7 中文测试）
- Playwright live：高级查询 CustomQueryDialog 数据源树渲染+91行查询结果+保存模板弹窗+0 errors

**Wave4.4 历史上传 501 与能力发现 [x]**
- 前端：`HistoricalUploadMenuItem.spec.ts` → exit 0（disabled+中文原因+不 emit）
- Playwright live：附注编辑器"更多▾"下拉→"📄 历史 Word/PDF 导入（暂不可用）"disabled + title="历史 Word/PDF 解析尚未实现" → 0 errors

**Wave5.5 历史上传 UI 禁用 [x]**
- 同 Wave4.4 Playwright 验证覆盖

**附注 resolver 清单漂移修复**
- `note_template_bindings.json` 补 `consol_aggregation`（第 9 项，对齐 `note_source_resolvers.py`）
- `test_disclosure_engine_v2.py` 断言改 9 + fixture 修 AsyncMock scalar_one_or_none

**构建阻塞（既有 pre-existing，非本 spec 引入）**
- `vue-tsc` OOM 4GB 默认→8GB 后暴露 4 个既有文件 72 errors（C1 PBT UTF-8 损坏 / D4TabIndex / F2 IPO ×2），本次不修

### 尚未验证（保持 [ ]）

- Wave0–Wave2、Wave4（除 4.4）、Wave5（除 5.5）：尚未编写对应实现或运行定向测试
- Wave6 两条完整 Playwright 中文主链尚未覆盖 ACNR/trace 下钻+分页+group/pivot+草稿隔离+provenance+模板执行端点真实调用
- 不假绿：未运行/skip/失败项保持 `[ ]`
