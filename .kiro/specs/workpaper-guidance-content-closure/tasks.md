# Implementation Plan: 逐 sheet 编制说明内容闭环

## Overview

执行顺序为“WIP 红基线 → C0 wire bundle → identity/registry → inventory/publication/resolution → host/store/UI/rail → tests/browser → C1 → custom conformance → C2/持续健康”。所有任务均为 required。

完成里程碑：

- `G-C0`：共享 wire contract bundle；
- `G-ID`：template/sheet stable identity 与 SourceRef authority；
- `G-RAIL`：可被公共壳层消费的 GuidanceRailAdapter；
- `G-HANDOFF-CONSUMER`：candidate/finalized handoff 与 durable ACK consumer；
- C1：固定 catalog snapshot 的标准内容完成；
- C2：固定 runtime cutoff 的不可变 milestone；
- `platform_guidance_health`：C2 后持续状态。

旧 `exact_status`、static-only exact、请求时全量扫描和 addendum 覆盖模型不再实施。任务编号用于稳定引用，实际执行顺序以依赖图为准。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "name": "已完成只读基线", "tasks": [1]},
    {"wave": 1, "name": "WIP 对账与红守卫", "tasks": [2]},
    {"wave": 2, "name": "C0 wire contract bundle", "tasks": [3]},
    {"wave": 3, "name": "稳定身份与 SourceRef authority", "tasks": [4]},
    {"wave": 4, "name": "inventory、publication 与 render identity", "tasks": [5, 6, 10]},
    {"wave": 5, "name": "内容、解析、宿主与 handoff consumer", "tasks": [7, 8, 11, 12, 16]},
    {"wave": 6, "name": "response 与 cache", "tasks": [9]},
    {"wave": 7, "name": "frontend store", "tasks": [13]},
    {"wave": 8, "name": "安全 UI", "tasks": [14]},
    {"wave": 9, "name": "GuidanceRailAdapter", "tasks": [15]},
    {"wave": 10, "name": "定向行为与变异", "tasks": [17, 18]},
    {"wave": 11, "name": "回归、CI 与 tracked 产物", "tasks": [19]},
    {"wave": 12, "name": "浏览器与 custom conformance", "tasks": [20, 22]},
    {"wave": 13, "name": "C1 catalog milestone", "tasks": [21]},
    {"wave": 14, "name": "C2 milestone 与持续健康", "tasks": [23]}
  ],
  "critical_path": [1, 2, 3, 4, 6, 8, 9, 13, 14, 15, 18, 19, 20, 21, 23],
  "hard_dependencies": {
    "2": [1],
    "3": [2],
    "4": [3],
    "5": [3, 4],
    "6": [3, 4],
    "7": [4, 6],
    "8": [4, 6],
    "9": [5, 6, 8],
    "10": [3, 4],
    "11": [10],
    "12": [10],
    "13": [3, 9, 10],
    "14": [6, 13],
    "15": [3, 14],
    "16": [3, 4, 5],
    "17": [4, 5, 6, 7, 8, 9, 10, 16],
    "18": [11, 12, 13, 14, 15],
    "19": [17, 18],
    "20": [15, 19],
    "21": [7, 17, 19, 20],
    "22": [16, 17],
    "23": [5, 21, 22]
  },
  "parallelizable": [
    [5, 6, 10],
    [7, 8, 11, 12, 16],
    [17, 18],
    [20, 22]
  ],
  "external_dependencies": {
    "consumes": [
      {"milestone": "F-SHELL", "producer_spec": "workpaper-page-formula-toolbar-closure", "required_by_tasks": [20], "on_missing": "BLOCKED"},
      {"milestone": "X-HANDOFF-CONFORMANCE", "producer_spec": "custom-workpaper-template-ingestion-and-sync-closure", "required_by_tasks": [22], "on_missing": "BLOCKED"},
      {"milestone": "X-RUNTIME-EVIDENCE", "producer_spec": "custom-workpaper-template-ingestion-and-sync-closure", "required_by_tasks": [23], "on_missing": "BLOCKED"}
    ],
    "produces": [
      {"milestone": "G-C0", "task": 3, "consumers": ["workpaper-page-formula-toolbar-closure:F1", "custom-workpaper-template-ingestion-and-sync-closure:X2", "custom-workpaper-template-ingestion-and-sync-closure:X9"]},
      {"milestone": "G-ID", "task": 4, "consumers": ["workpaper-page-formula-toolbar-closure:F4", "custom-workpaper-template-ingestion-and-sync-closure:X8", "custom-workpaper-template-ingestion-and-sync-closure:X10"]},
      {"milestone": "G-RAIL", "task": 15, "consumers": ["workpaper-page-formula-toolbar-closure:F11"]},
      {"milestone": "G-HANDOFF-CONSUMER", "task": 16, "consumers": ["custom-workpaper-template-ingestion-and-sync-closure:X11"]}
    ]
  }
}
```

## Tasks

### Foundation and Contracts

- [x] 1. 冻结生产链与数据红基线
  - 核实 route/service/extractor/store/panel/HTML/Univer/OnlyOffice 真实链路与现有 WIP
  - 记录 `extract_exact_static()`、单 `source/exact_status`、请求级 inventory 扫描、custom 501、双 fetch、初始 context、Univer no-op、OO 整册和 sanitize 缺口
  - 只冻结事实；不把已有文件或历史测试数字反推为实现完成
  - _Requirements: 1.1, 2.5, 4.1, 7.3, 9.5, 10.1, 10.3, 11.3, 15.1_

- [x] 2. 建立 WIP reconciliation 与真实红守卫
  - 将 guidance services/routes/data/tests/scripts 逐文件映射到 Task、AC、Property、owner、正向证据、mutation 状态
  - 外来/并发 WIP 标 frozen/foreign/blocked；mutation anchor miss 记 ANCHOR-MISS，不算 RED
  - 建立 contract/inventory/resolution/context/UI 红守卫，真实执行消费链，不用字符串存在代替
  - 2026-09-09：`wip_reconciliation.md` §7–§8 已复核；contract/inventory/resolution/handoff
    变异脚本齐全；行为级守卫真跑消费链。残留 tracked 产物入库属归档门（T19），不阻塞 T2
  - _Requirements: 14.1, 14.2, 14.3, 15.1, 15.6_

- [x] 3. 发布 `G-C0` 共享 wire contract bundle
  - 单源定义 location、section、SourceRef、TemplateAuthorityIdentity、candidate/finalized handoff、ConsumerAck、rail adapter、EvidenceEnvelope subject union
  - 发布 schema、语言绑定、canonical fixtures、major/minor 兼容矩阵与 unknown-major fail-closed 守卫
  - 反查 formula/custom，任何同名本地 interface/schema 副本均使 conformance 失败
  - 形成 `G-C0` evidence，供 F1/X2 消费
  - 2026-09-08 收口：evidence digests 全匹配；`discover_local_dupes` 清掉前端两处
    本地 `GuidanceSection` 副本（store/C-control → 改名）；conformance + 内嵌变异 M1–M5 绿；
    formula `workpaper-route-baseline` 与 custom `authorization` 已 import 消费
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 15.2_

- [x] 4. 发布 `G-ID`：稳定 template/sheet identity 与 SourceRef registry
  - 复用 template finder/index/override，冻结 lineage/version/sheet uid/code/null reason，不以名称/下标为身份
  - 实现 xlsx/docx/bcd_markdown/methodology_publication/project_evidence/custom_artifact locator handlers
  - 校验 path/anchor/range/authority/digest/stale/cross-authority；unknown kind fail-closed
  - 用真实源和 custom authority fixtures 做行为/变异证据，发布 `G-ID`
  - 产物：`guidance_gid.py`（SourceRefHandler Protocol + Registry + StableSheetIdentity）；
    `data/guidance/contracts/gid/evidence/gid_evidence.json`；
    `test_guidance_gid.py`；变异 4/4 RED（`mutate_guidance_gid_guards.py`：
    M1 unknown-kind / M2 lifecycle-kind / M3 physical-path / M4 publication-lookup）
  - 结构性：生命周期名不得作 locator kind；methodology 无 lookup 不放行；
    project_evidence 必经 visibility；custom_artifact 禁物理 path；
    `validate_source_ref` 一律经 registry
  - _Requirements: 2.1, 2.3, 5.3, 5.4, 5.5, 8.1, 8.2, 8.3, 8.5, 15.2_

### Inventory, Publication and Resolution

- [x] 5. 实现 materialized catalog/runtime inventory 与阶段 accounting
  - catalog key 使用 lineage/version/wp/sheet；runtime key 使用 organization/project/wp/entry/sheet
  - snapshot 保存 run/scope/cutoff/input digests/entries/digest，不在请求时全目录扫描
  - 实现 `gross_required` 四集合、`effective_required`、有效 exemption 与非法三轴 blocked
  - 输出 C1/C2 投影及 `platform_guidance_health`，不写死历史数量
  - 2026-09-09：`guidance_inventory_snapshots.py`（Catalog/Runtime key、immutable SnapshotStore、
    stage accounting、platform_guidance_health）；`test_guidance_inventory_snapshots.py` 9 passed；
    变异 3/3 RED（`mutate_guidance_task5_snapshots.py`）；evidence `basis/T05-mutation-report.json`
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.5, 4.6_

- [x] 6. 实现 immutable Guidance Publication 与 Project Supplement
  - legacy/template/BCD 抽取只导入 candidate/draft；draft→reviewed→published，published immutable
  - 发布/撤回/恢复/supersede 保存 actor/reviewer/diff/digests/reason，写 audit/outbox
  - supplement 独立版本并绑定 runtime subject/base publication/project evidence；不改 canonical、不补齐缺失 canonical 后推 complete
  - 权限/capability 前置并由服务端复验；变化触发 inventory/response stale
  - _Requirements: 4.2, 4.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 12.2, 12.3_

- [~] 7. 按 catalog 工作卡完成标准九段内容迁移
  - 每批从 catalog snapshot 领取，不写死 sheet 数；逐 sheet 读取运行时权威模板并交叉 BCD/render schema/真实 UI/公式与联动
  - 九段 key 唯一，每段 refs 通过 registry；不得用泛化自动文案补缺
  - candidate 经独立 review/publication 后才进入 primary authority；未齐保持 pending/blocked
  - 保存 reviewer/version/source digests/正向与变异 evidence
  - 2026-09-09：`migrate_guidance_canonical_schema.py --check` → files=373 changed=0
    unmapped=308 errors=0（结构 v2 已落地，但 308 份仍有 unmapped，不得假绿 complete）。
  - 2026-09-09：`emit_t7_migration_workcards.py` 已产出 **373** 张 gap 工作卡
    （`basis/T07-workcards/`，policy=`no_generic_autofill`）；catalog pending=373 complete=0。
    卡片只列 missing_sections / unmapped titles / SourceRef 缺口，**不**自动填九段正文；
    内容/publication 仍依赖人工复核批次后才可推进 C1。
  - 2026-09-09 批次：扩展高置信标题别名 + `promote_unmapped_guidance_sections.py`
    → **85 files / 149 sections** 把已有 unmapped 正文升入九段（不造文、不造 refs）；
    migrate `--check` unmapped **308→159** errors=0；pilot A1-13/A14-4 unmapped 清空。
    evidence `basis/T07-promote-unmapped-summary.json`。**仍非 exact**：缺 SourceRef + 其余缺段 + 无 publication。
  - 2026-09-09 SourceRef 可行性核算：`diagnose_guidance_source_ref_feasibility.py`
    → 373 份中 **264 单模板 + 30 父工作簿 sheet = 294 可挂**，14 ambiguous、65 无模板；
    仍有 **1158** 个 canonical section 的 `source_refs=[]`。
    报告只登记真实 path/digest/sheetNames，**不生成任何 ref**；
    evidence `basis/T07-source-ref-feasibility.json`。
  - **T7 缺口结论（不可脚本化）**：materials 373 / data_sources 374 / formulas 357 /
    completion 356 / judgments 348 份仍完全缺段，正文在任何来源里都不存在，
    只能人工按 sheet 撰写 + 挂 registry ref + 独立 publication。
  - _Requirements: 4.3, 5.1, 5.2, 5.6, 6.1, 7.5_

- [x] 8. 以 `resolve_authoritative_exact()` 重构解析链
  - child 只查询 active publication 或 durable custom-confirmed authority
  - child miss/invalid/stale 后进入 parent authoritative exact→typed→generic；legacy/static/template candidate 不抢 exact
  - 返回 requested/resolved identity、三轴状态、primary/overlays/extraction、缺段与 structured reasons
  - 跨 wp/sheet membership fail-closed，不泄漏其他内容
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 12.1_

- [x] 9. 收敛 response version、stable cache 与错误模型
  - response/ETag fingerprint 覆盖 subject/inventory/publication/custom authority/supplement/refs/schema
  - 服务端 cache stable key 不含 contextRevision；只缓存 immutable result/snapshot并有界
  - 前端 key 含 project/wp/entry/stable sheet-or-whole/schema；短 TTL + revalidate
  - invalid/timeout/stale/permission 结构化返回；旧响应按 identity/ownerEpoch/revision 丢弃
  - 日志/telemetry 记录 correlation、subject、operation、version 与 verdict，但不记录 token、附件正文或敏感项目内容
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 12.4_

### Identity, Host, UI and Consumer

- [x] 10. render-config 下发 canonical identity/location input
  - 下发 template authority、sheet uid/code 或 null reason、whole-workbook capability
  - override/index 变化使 identity/source/evidence stale；复合码与重名 sheet 不靠 regex
  - host raw event 只产生稳定 input，交 formula runtime owner 归一，不建立第二 location owner
  - 2026-09-09：`guidance_render_identity.py` + `annotate_sheet_identities(..., parent_wp_code=)`；
    wire 增 `sheet_uid`/`sheet_uid_null_reason`/`stable_identity`；显示名永不发明 uid；
    `test_guidance_render_identity.py` + sheet_context 共 13 passed
  - _Requirements: 8.2, 8.3, 8.4, 8.5, 10.1_

- [x] 11. HTML 全激活路径发布稳定 context
  - initial/deep-link/tab/navigate/locate/section/wp reset 汇入同一 emitter
  - 删除 sheet 名正则、数组下标与跨 wp stale ref
  - 快速切换按 ownerEpoch/contextRevision 只保留最后位置
  - 2026-09-09：`htmlStableContextEmitter.ts` + `sheetUidProjection.ts`；
    `GtWpRenderer` 唯一 publish；`WorkpaperSheetContext` 带 sheetUid/nullReason/epoch/revision；
    shellLocation 禁 display-name 作 uid；runtime-boundary + emitter 16 tests passed
  - _Requirements: 10.1, 10.2, 10.6_

- [x] 12. Univer 与 OnlyOffice 诚实 context
  - Univer engine id→stable uid/code，native/custom/locate 汇流并删除 no-op
  - OnlyOffice 外层单 sheet 使用 stable identity；整册固定 whole-workbook
  - 不做 iframe DOM 穿透、轮询或伪事件；未来解除边界需受支持事件与黑盒证据
  - 2026-09-09：`resolveUniverSheetContext(..., parentWpCode)` + `univerContextEmitter`；
    `onSwitchSheet` 必 publish；OO 外层/整册由同一 resolve 投影；无 DOM 穿透
  - _Requirements: 10.3, 10.4, 10.5, 10.6_

- [x] 13. guidance store 单 fetch 与竞态隔离
  - `setContext` 为唯一 fetch owner；abort/request identity/ownerEpoch/revision 多门拒绝旧结果
  - 完整消费 provenance/resolution/completion/version/error 类型，不再依赖单 `source/exact_status`
  - 切 context、失败、AI capability 变化清 data/AI/tab；cache preview 后 ETag revalidate
  - 2026-09-09：`setWpContext` + `isResponseCurrent` 四门（requestId/identity/epoch/revision）；
    cache key 用 sheetUid、不含 revision；`If-None-Match` + 304 保预览；store 8 tests passed
  - _Requirements: 4.1, 4.4, 9.3, 9.4, 9.5, 11.4_

- [x] 14. 展示九段、三轴 provenance、缺口与安全内容
  - 分层 badge 展示 primary/overlays/extraction/resolution/completion/publication/ACK/refs
  - 非 exact/complete 显示中文依据、owner、阻断和下一步
  - 全部不可信内容统一 sanitize，异常退纯文本；删除 guidance 内旧 AI 承载链
  - supplement/canonical 分开展示，权限错误可解释
  - 2026-09-09：`GuidanceTabContent` 增 completion + provenance 三轴 + reasons/blockers；
    sanitize fail-closed 既有守卫保留；UI 5 tests passed
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 12.5_

- [x] 15. 发布 `G-RAIL` GuidanceRailAdapter
  - adapter 只提供 visibility/reason/location/version/draft/open/close
  - 删除 guidance fixed trigger、top/right/z-index 和相互 offset；最终 DOM/CSS 交给 `F-SHELL`
  - unknown major/incomplete location 不挂载；保存 adapter 行为 evidence
  - 2026-09-08：`shell/guidance/guidanceRailAdapter.ts` + evidence
    `evidence/G-RAIL/adapter-behavior.json`；formula T11 已消费
  - _Requirements: 11.5, 11.6, 15.2_

- [x] 16. 发布 `G-HANDOFF-CONSUMER` 与 durable ACK ledger
  - candidate/finalized discriminator、authority、artifact/mapping/formula/guidance digests、九段/refs/inventory 依次校验
  - candidate 只 review_pending；finalized 写幂等 ACCEPTED/REJECTED ConsumerAck
  - 定义 PENDING visibility saga contract、timeout/retry/compensation；ACK fail 时 visibility=0
  - 变化/withdraw 使 confirmed stale 并触发 runtime reevaluation evidence
  - 2026-09-08 交付：`guidance_handoff_consumer_service.py`（verify_candidate/verify_finalized
    有序 pipeline + record_ack 幂等 + resolve_visibility saga + mark_stale_on_change）；
    `models/guidance_handoff_ack_models.py` + `migrations/V157__guidance_handoff_consumer_ack.sql`
    （guidance_consumer_ack 幂等键 `(handoff_id,handoff_digest,consumer,consumer_version)` +
    guidance_handoff_visibility）；`test_guidance_handoff_consumer.py` 19 例全绿；
    变异 `mutate_guidance_handoff_consumer_guards.py` 5/5 RED（CAND-EXACT/SECTIONS/DIGEST-CONST/
    VIS-REJECT/ACK-IDEM）；evidence `contracts/ghandoff/evidence/ghandoff_consumer_evidence.json`
    （subject=contract，含 sagaContract + idempotencyKey，module digest 与实现锁死）。custom `X11` 可消费。
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 15.2_

### Evidence and Closure

- [x] 17. 后端/data/contract 定向测试与逐项变异 RED
  - 覆盖 C0、identity/registry、inventory/accounting、publication、resolver、cache、handoff/ACK
  - 变异契约副本、candidate discriminator、exemption subtraction、publication gate、ref digest、ACK visibility
  - 每项记录 RED/GREEN/ANCHOR-MISS/WRONG-TEST，finally 字节复原
  - 2026-09-09：`run_guidance_task17_mutations.py` 批量 **11/11 RED**（anchors 11/11 OK）；
    directed pytest 子集 89 passed；evidence `basis/T17-backend-mutation-report.json`
  - _Requirements: 14.1, 14.2, 14.4_

- [x] 18. 前端/host/rail 定向测试与逐项变异 RED
  - 覆盖 HTML/Univer/OO context、single fetch、race gate、三轴 UI、sanitize、adapter
  - 变异 initial emit、Univer switch、cache identity、sanitize、visible=false 和 fixed offset
  - 只接受行为/挂载证据，不以 symbol/string 存在判定
  - 2026-09-09：`mutate_guidance_frontend_host_ui_guards.py` **5/5 RED**
    （emit immediate / Univer null / cache revision / sanitize / rail null-location）；
    evidence `basis/T18-frontend-mutation-report.json`
  - _Requirements: 14.3, 14.4_

- [~] 19. 广域引用回归、CI job 与 tracked 产物
  - 按引用反查受影响测试；共享 workflow 只追加归因区间
  - clean checkout 核对 schema/fixtures/migrations/tests/mutation/evidence 文件均 tracked
  - WIP reconciliation 更新到磁盘最新正向与变异证据
  - 2026-09-09：已追加 CI `wgcc-guidance-backend-guards` / `wgcc-guidance-frontend-guards`；
    T17 批量 RED + directed 89 passed 登记于 `basis/T19-ci-and-tracking-status.json`。
    推荐 add 清单已冻结 `basis/T19-tracked-paths.json`（含 F-SHELL `rightRailArbiter` CI 依赖）。
    **仍 BLOCKED**：正式产物大量 `??` 未 tracked，clean-checkout 门未过（需显式 git add/commit）。
  - _Requirements: 14.1, 14.2, 14.3, 14.6, 15.1, 15.6_

- [x] 20. Playwright 三宿主、权限与 `F-SHELL` 消费实测
  - HTML 默认/deep-link/快速切换；Univer native/custom/locate；OnlyOffice 外层/整册
  - 核 network、三轴 DOM、publication/supplement、旧内容清除、sanitize、console
  - 通过 `F-SHELL` 验证 GuidanceRailAdapter，无重复 AI/fixed rail；保存 envelope/trace/截图
  - 2026-09-09：`e2e/workpaper-guidance-fshell.spec.ts` **PASS**；三宿主 shellSeen；
    HTML/OO guidanceOpened；`/guidance` 200；HTML provenance+completion 可见；
    fixedTriggerCount=0；evidence `basis/T20-playwright/`
  - _Requirements: 10.6, 11.1, 11.3, 11.6, 14.5, 14.6_

- [~] 21. 生成 C1 catalog milestone
  - 冻结 catalog run/digest；standard/custom_blank gross/effective 集合核算无遗漏
  - effective required 全 complete，pending/blocked=0；exemption 全有效
  - clean checkout 重跑并保存真实数字和 evidence；C1 不等于 C2/最终归档
  - 2026-09-09：`emit_c1_catalog_milestone.py` 已诚实冻结 **verdict=FAIL**
    （effective=373 complete=0 pending=373 blocked=0；reason=`pending_entries_present`）；
    evidence `basis/T21-c1-catalog-milestone.json` + `evidence/C1/`。
    **不得勾 [x]**：PASS 仅当 T7 关闭 pending 后重跑。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 15.4_

- [~] 22. 验收 `X-HANDOFF-CONFORMANCE`
  - 只等待 custom 发布 candidate/finalized/ACK/rollback conformance evidence，不等待本 spec C1/C2
  - 用三 projection mode 验证 candidate→finalized→confirmed→stale→rollback 和 ACK fail visibility=0
  - 不修改 custom runtime；仅记录 consumer conformance verdict
  - 2026-09-08 状态：**BLOCKED** —— 外部里程碑 `X-HANDOFF-CONFORMANCE`（custom spec Task 19）
    未发布，且其自身依赖 `G-HANDOFF-CONSUMER`(本 spec T16) + `F-SHELL`。on_missing=BLOCKED。
  - 2026-09-09：consumer verdict 已落盘 `basis/T22-x-handoff-consumer-verdict.json`
    （verdict=BLOCKED；xVerdict=PARTIAL；reason=`x_handoff_conformance_partial` + `sync_gates_incomplete`）。
    不修改 custom runtime；等 custom X PASS 后再重验三 projection mode。
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.6, 15.3_

- [~] 23. 消费 `X-RUNTIME-EVIDENCE`，生成 C2 milestone 与持续健康
  - 以最新 runtime snapshot/cutoff 核算 standard/custom_blank/user_uploaded gross/effective 集合
  - C1 与 handoff conformance 均有效、effective required 全 complete 后生成不可变 C2Milestone
  - 初始化 `platform_guidance_health`；cutoff 后变化只发 reevaluation evidence，不反写 C2
  - 完成 WIP 对账、tracked/clean-checkout 复现和 INDEX 归因更新后才归档
  - 2026-09-08 状态：**BLOCKED** —— 依赖 `X-RUNTIME-EVIDENCE`（custom spec Task 19）未发布。on_missing=BLOCKED。
  - _Requirements: 3.5, 3.6, 15.3, 15.5, 15.6_

## Property Coverage

| Property | Implemented/verified by Task |
|---|---|
| 1 | 3, 17 |
| 2 | 3, 17 |
| 3 | 4, 5, 17 |
| 4 | 5, 17, 21, 23 |
| 5 | 5, 21, 23 |
| 6 | 5, 8, 13, 17 |
| 7 | 6, 7, 8, 17 |
| 8 | 7, 17, 21 |
| 9 | 4, 17 |
| 10 | 6, 14, 17 |
| 11 | 6, 17, 20 |
| 12 | 8, 17 |
| 13 | 4, 10, 17 |
| 14 | 9, 13, 17, 18 |
| 15 | 9, 12, 14, 16, 17 |
| 16 | 10, 11, 12, 18, 20 |
| 17 | 13, 14, 18, 20 |
| 18 | 15, 18, 20 |
| 19 | 16, 17, 22 |
| 20 | 16, 17, 22 |
| 21 | 17, 18, 19 |
| 22 | 17, 18 |
| 23 | 19, 20, 21, 23 |
| 24 | 2, 3, 15, 16, 19 |
| 25 | 5, 21 |
| 26 | 5, 23 |
| 27 | 19, 21, 22, 23 |

## Completion Notes

- Task 22 与 C1 独立；它消费 `X-HANDOFF-CONFORMANCE`，不制造 `X → G23 → X` 环。
- Task 23 只对固定 cutoff 生成 C2；后续新增 custom entry 由持续健康处理。
- 任何 existing code、历史 passed 数、HTTP 200、字符串存在或未跟踪文件都不能自动勾任务。
- OnlyOffice 整册边界是诚实产品能力，不豁免整册 guidance、SourceRef、权限和 evidence。
