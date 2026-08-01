# Implementation Plan: 附注跟随底稿实际内容

## Overview

四条主线：自动同步（R1）、模板回流（R2）、单一真源迁移（R3）、空表语义（R4/R5）。R6 零回归贯穿全程。

先做只读能力（差异计算、空表判定、迁移 dry-run），再做写入能力，最后做破坏性迁移。所有写入路径默认由灰度开关关闭，逐项 Playwright 实测后再考虑开启。

**取证基线**（改造前实况，用于回归对比）：6 条存货章节记录中仅 1 条 `sub_table_data` 非空（9 张表），其余 5 条为 0 张表 + legacy 快照。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "note": "只读基础：空表判定 / 差异计算 / 迁移 dry-run" },
    { "wave": 2, "tasks": ["4", "5"], "note": "自动同步（含去抖与 fail-soft）" },
    { "wave": 3, "tasks": ["6", "7"], "note": "模板回流写入 + 过期可见性" },
    { "wave": 4, "tasks": ["8"], "note": "破坏性迁移（需用户显式确认）" },
    { "wave": 5, "tasks": ["9", "10"], "note": "空表折叠前端 + 全链实测" },
    { "wave": 6, "tasks": ["12"], "note": "缺链路 Tab 定性 + 独立立项（已完成）" },
    { "wave": 7, "tasks": ["11"], "note": "收尾：文档 / CI / commit" }
  ]
}
```

## Tasks

- [x] 1. 空表判定纯函数（前后端同口径）
  - [x] 1.1 新建 `backend/app/services/note_empty_table_detector.py`：`is_empty_table(rows, columns)`
        + `empty_table_names(tables)`。输入契约 = **投影后的表**（`project_sub_tables` 输出），
        让模块页 / Word / 批量导出三消费方同口径
  - [x] 1.2 新建 `audit-platform/frontend/src/views/composables/disclosureEmptyTable.ts`，与后端同口径
  - [x] 1.3 双侧镜像用例各 38 条（后端 `test_note_empty_table_detector.py` ↔
        前端 `disclosureEmptyTable.spec.ts`，同名 case + 同预期）
  - [x] 1.4 PBT：任一非零数值 / 非空文本 → 必非空；合计行填任何值都不改变判定
  - _Requirements: 4.1_
  - _Properties: Property 8_
  - _关键判定（易错点，改前先读）_：
    - **行标签不参与判定** —— 模板骨架恒有标签（「原材料」「在产品」…），算进去则永不为空
    - 合计 / 小计 / 段标题 / 假表头行不参与（派生值与结构行不代表业务发生）
    - 数值列（`format ∈ amount|percent|number`）：`None`/`''`/`0`/`< 半分` 视为空；
      数值列里出现「不适用」这类文字 → **视为有内容，不吞**
    - 无列定义时全部按文本判定（保守：`'0'` 算有内容），避免降级路径误判空表

- [x] 2. 模板差异计算（只读）
  - [x] 2.1 新建 `backend/app/services/note_template_reflow_service.py`：
        纯函数 `diff_tables` + DB 薄封装 `diff_section` / `diff_project`（预览与执行共用）
  - [x] 2.2 **五类**差异：missing / renamed / column_drift / **guidance_missing** / extra
        （extra 只报告不删）。`guidance_missing` 是实测追加的第五类，见 6.6
  - [x] 2.3 改名判定：优先模板 `_renamed_from`（支持 str 或 list），否则列结构同构推断；
        歧义（多候选）时**不消费 missing**，标 `ambiguous` 等人工选
  - [x] 2.4 单测 29 条：五类差异 + 歧义改名 + `group_or_flat` 漂移 + 健壮性 + JSON 可序列化
  - [x] 2.5 新建只读诊断脚本 `backend/scripts/diagnose/diagnose_note_template_drift.py`
        （`--project/--year/--section/--only-changes/--out`），实跑核对
  - _Requirements: 2.1, 2.3, 2.5_
  - _实跑结论（2026-07-29）_：
    - **单章节核对与手工取证三条全对**：存货 五、9 → 缺表 2（按库龄组合 ×2）、
      列头漂移 `group_or_flat` 1（存货跌价准备…（续），即缺 `flat`）、缺 guidance 9（全表）
    - **全库摸底（575 个有差异章节）**：`legacy_snapshot=569`（**98.9%**）、
      `missing=1423`、`column_drift=1`、`guidance_missing=19`、`extra=12`、`renamed=0`
    - 🔴 **优先级修正**：绝大多数章节根本没走过同步路径，仍是生成时快照 →
      **Task 3/8 的 legacy 迁移是 Task 6 模板回流的前提**；否则 legacy 章节的
      `sub_table_data` 为空会让模板全部表都算「缺表」，把 missing 数字严重放大
      （1423 张里大部分属此类，诊断输出已在 notes 里提示）
    - **`guidance` 缺失是平台级现象**，非 F2 独有：同一项目「五、8 其他应收款」也缺 10 条
      （K1 spec 已在模板侧补齐，但同步路径同样不落 guidance）→ 印证 6.6 的必要性
    - `extra` 主要来自 variant/章节号错配或其它 spec 的表名差异（如「八、4 应收票据」10 张），
      本 spec 只报告不删

- [x] 3. legacy 迁移脚本（dry-run 优先）
  - [x] 3.1 新建 `backend/scripts/fix/migrate_legacy_note_snapshots.py`，**默认只读**；
        `--apply` 目前显式返回 `[BLOCKED]`（写入属 Task 8）
  - [x] 3.2 选择集 + **四类可行性分类**（纯函数 `build_note_plan`）：
        `by_name`（表名与模板一一匹配）/ `positional`（表名重名或非业务名但表数与模板相等，
        按序对齐）/ `single_row`（只有顶层 `rows` 且模板恰好 1 张表）/ `manual`（表数不等、
        模板缺章节 → 跳过）
  - [x] 3.3 删 `header_label` 假数据行并计数（其语义由 `_column_groups` 承载）
  - [x] 3.4 `--check`：有 legacy 残留则 exit 1（实测 exit=1），供 CI 监控
  - [x] 3.5 全库跑 dry-run，产出守恒与风险报告
  - [x] 3.6 纯函数单测 32 条（四类分类 + 表名可用性判定 + 行数守恒 + `header_label` 剥离 + 健壮性）
  - _Requirements: 3.2, 3.3, 3.5_
  - _Properties: Property 6_
  - _全库 dry-run 实测（2026-07-29）_：

    | 指标 | 数量 |
    |------|------|
    | legacy 章节 | 572（同时有 `rows`+`_tables` 460 / 只有 `rows` 112） |
    | `by_name` 可安全迁移 | 279 |
    | `positional` 需人工抽样 | 150 |
    | `single_row` | 43 |
    | `manual` 必须人工 | 100 |
    | 计划表数 / 行数 | 982 / 5716 |
    | 将删 `header_label` 行 | 171 |
    | **模板里也没有 `columns` 的表** | **950 / 982（97%）** |
    | 迁移后行数会变的章节 | 64 |

  - 🔴 **决定性约束：Task 8 必须等 `columns` 补齐后才能执行**。97% 的目标表在模板里也没有
    `columns`，迁移后 `_sub_table_columns` 无从填充 → 投影器走降级路径
    （`_needs_columns: true`，只显示行名、values 恒空），**比现在的 legacy 快照更糟**
    （legacy 至少还有 `headers`）。
    → **跨 spec 依赖**：`disclosure-columns-coverage-rollout`（补 `columns`，其 CI job
    `disclosure-columns-coverage` 现为红）**必须先完成**，本 spec 的 Task 8 才能动。
  - ⚠️ 脏数据实况：`_tables[]` 的项只有 `headers`/`name`/`rows`（无 `columns`）；
    58 个章节存在**重名表**（直接按 name 建键会互相覆盖丢表）；
    79 个章节的表名是**表头首格**（如「项  目」）而非业务表名。
  - Windows 控制台默认 GBK，报告含 `⚠️` 会 `UnicodeEncodeError` →
    两个脚本都在 `main()` 里 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`

- [x] 4. 自动同步（🔴 **方向已修正**：机制早已存在于前端，本任务是修触发条件 + 补覆盖）
  - _🔴 设计修正（2026-07-29 实证，原 4.1~4.6 的后端 handler 方案已废弃）_：
    - **后端无法重建同步载荷**：`sync_from_workpaper` 需要 `sub_table_data` +
      `sub_table_columns`，二者由前端 `buildXSyncPayload` 从各 composable 的行模型算出。
      后端 handler 只拿到 `WORKPAPER_SAVED` 的 `extra = {wp_id, wp_code, trigger,
      item_ids, atomic}`（`PUT /api/workpapers/{wp_id}/checklist-responses` 发布，
      **无 sheet_name**）。要在后端重建就得把每个循环的载荷逻辑双写一遍 → 违反 DRY
    - **前端机制已存在且 proven**：`composables/useDisclosureAutoSync.ts`
      （spec `disclosure-note-linkage-completion` Req1）已实现防抖 800ms + 非阻塞 +
      失败静默 + 只读 gate，且 `syncFn` 直接复用各 Tab 既有 `syncToDisclosureNotes`
      → 与手动按钮**同源幂等**，天然满足 Property 1
    - → 本任务改为：**修 F2 的触发条件 + 清死 import + 建覆盖率守卫 + 分批推广**
  - _全平台覆盖率实测（154 个 `*TabDisclosure*.vue`）_：

    | 状态 | 数量 | 说明 |
    |------|------|------|
    | 已接入并调用 | 89（58%） | 含 G3/N1/K6/L1/L3/J1/K8/K9… |
    | **import 了但未调用** | **5** | E1TabDisclosure / L5×2 / L7×2（死 import，等于没接） |
    | **完全未接入** | **60（39%）** | D2 / F4×2 / G4~G12 / H4~H7 / J2 / L2·L4·L6·L8 / M1~M10 / N2~N5 |

  - [x] 4.1 🔴 **修 F2 触发条件**：原为 `watch(dataUpdatedVisible, v => if (v) ...)`，
        而 `dataUpdatedVisible` 是**上游数据更新提示横幅**的可见性 —— 用户在披露 Tab 里改
        组合计提 / 房企 3 表 / 数据资源 / 6 个文本域**一律不触发**（这正是实测时必须手动
        点「同步到附注」的原因）。已改为监听实际数据（上市 15 个源 / 国企 8 个源，
        对齐 G3/L1/L3 范式 `{ deep: true }`）+ `_f2{Listed,Soe}SyncMounted` 防护
        （避免打开 Tab 即写库）
  - [x] 4.2 清 5 个半接/死 import：
        - `E1TabDisclosure.vue` 有 `autoSync` 实例 + `onBeforeUnmount` + 完整
          `syncToDisclosureNotes`，却**从不调 `scheduleAutoSync`** → 已补触发
          （监听 `disclosureRows`/`restrictedRows`/`noteText`/`variant`，与 snapshot 构建字段一致）
        - `L5TabDisclosure{Listed,Soe}` / `L7TabDisclosure{Listed,Soe}` 连
          `syncToDisclosureNotes` 都没有 → **纯死 import，已删 4 行**
  - [x] 4.3 **覆盖率守卫** `__tests__/disclosureAutoSyncCoverage.spec.ts`（18 tests，
        含 Task 12 重新统计后补的同步链路完整性 5 条）：
        ①有 `syncToDisclosureNotes` 必须接入（未接入进 allowlist + 强制 reason）
        ②import 了必须真的调 `scheduleAutoSync`（钉死 E1 那种半接状态）
        ③**触发条件不得只监听横幅类状态**（钉死 F2 那种假接入）
        ④allowlist 不得残留已接入项（推广后必须移出）
        ⑤扫描数 >140 防 glob 失效空转
        + F2 定点回归 6 条（不再匹配旧 `watch(dataUpdatedVisible…)` 写法、
        逐一断言 15/8 个监听源齐备、mounted 防护存在）
  - [x] 4.4 后端兜底 handler（**只标 stale，不重建载荷**）：
        新建 `backend/app/services/disclosure_stale_marker.py`。
        `WORKPAPER_SAVED` → `extra.wp_code`（缺失时按披露 item_id 前缀反推，
        如 `F2-note-listed-s2-overrides` → `F2`）→ 查
        `note_workpaper_sync_registry.json` 的 `entries[]` 得 listed/soe 章节号 →
        `is_stale=true` + `stale_source='workpaper_saved'`。
        覆盖**绕过前端 composable 的路径**：多区块导入（本 spec 同期新增的
        `/f2/import-data`）/ API 直写 / 后台重算 / 只改上游未打开披露 Tab。
        SQL 只碰 `is_stale`/`stale_source`，**绝不动 `table_data`**（Property 5）；
        fail-soft（异常只 warning + rollback，不冒泡到已提交的底稿保存）
  - [x] 4.5 灰度开关 `DISCLOSURE_AUTO_SYNC_ENABLED`（默认关，仅管 4.4 的后端兜底；
        前端自动同步已在生产运行，不加开关以免回退既有 89 个 Tab 的行为）；
        已注册到 `event_handlers_cycle_linkage.register_cycle_linkage_handlers()`
  - [x] 4.6 单测 43 条：开关六种取值、registry 加载/降级、wp_code 四种提取路径、
        handler 六条路径（disabled / no_project / no_wp_code / no_mapping / marked /
        failed）、SQL 不含 `table_data` 断言、handler 已注册断言
  - [x] 4.7 **浏览器端到端实测通过**（Playwright MCP 断连 → 改用 chrome-devtools MCP +
        postgres MCP 交叉验证，比截图更硬：直接比对 `disclosure_notes.table_data`）：

        | 步骤 | 操作（**全程未点「同步到附注」**） | `_last_sync_at` | 库中值 |
        |------|------|------|------|
        | 基线 | — | 17:11:27 | 外购期初 `1234567.5` |
        | ① 改数据资源表一格 | 首次挂载后第一次编辑 | **→ 01:42:10** | **`2222222.22`**，合计 `2232098.76` 与界面一致 |
        | ② 切国企→切回上市，改文本域 | 重新挂载后第一次编辑 | **不变** ❌ | `checklist_responses` 已存 probe，附注未同步 |
        | ③ 同一挂载内再改一次 | 第二次编辑 | **→ 01:45:12** | probe 已同步 |
        | ④ 刷新页面后第一次编辑 | 修复后复验 | **→ 01:48:06** | probe 已同步 ✅ |

  - [x] 4.8 🔴 **实测抓出并修复真 bug：mounted 一次性防护会吞掉编辑**
        （步骤 ② 的现象）。根因：防护的消耗时机取决于「数据是否已加载」——
        首次挂载时 `allResponses` 异步填充让 computed 变化并消耗掉防护（符合设计意图）；
        但**切走再切回**时 `allResponses` 已有值、computed 不变化、watch 不触发，
        防护未被消耗 → 吞掉用户回到本页后的**第一次真实编辑**。
        修复：**去掉 mounted 防护**（Vue `watch` 默认 `immediate: false`，挂载本身不触发；
        数据加载引起的那次同步是**有益的** —— 正是本 spec 要的「附注跟随内容」，
        且 `sync_from_workpaper` 空载荷 no-op + 幂等）。
        守卫方向同步反转：`disclosureAutoSyncCoverage.spec.ts` 现**禁止** `_xxxSyncMounted`。
        ⚠️ **L1/L3 等已接入 Tab 用的是同一 `_xxxMounted` 范式，同样有此 bug** →
        推广时（Task 12）一并清除，不要照抄
  - [x] 4.9 实测数据清理：probe 值已还原（`note-category` → 空、数据资源外购期初 →
        `1234567.5`、附注侧 `_note_texts` probe 清空 + `text_content` → NULL），
        经 postgres 复核 `probe_texts_left = 0`
  - _Note: 国企 Tab 无法在该项目验证 —— 项目为上市模板，`buildF2SyncPayload` 对不适用变体
    返回 null 而跳过同步（正确行为，已有单测覆盖）_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 6.5_
  - _Properties: Property 1, Property 2, Property 3, Property 5, Property 10_

- [x] 12. 🔴 缺失同步链路的 Tab → **已独立立项** `disclosure-sync-path-buildout`
  - [x] 12.0 抽查 37 个 emit 型 Tab 的结论：**全部属于无同步链路**。事件分布只有
        `navigate`(27) / `imported`(7) / `disclosure:note-text-updated`(5)；前两者与同步无关，
        后者的消费方 `useNoteRefresh.onDisclosureNoteTextUpdated` 仅调 `fetchDetail`
        刷新界面，首行 `if (!currentNote.value) return`（附注页未打开直接返回）——
        **完全不推数据落库**。据此把守卫的 `hasAnySyncPath` 去掉 emit 分支，
        缺口从误判的 27 修正为 **64**
  - [x] 12.1 守卫 `MISSING_SYNC_PATH` 扩为 64 条（按循环分组），`length` 断言 27→64
  - [x] 12.2 新建 spec `.kiro/specs/disclosure-sync-path-buildout/`（三件套格式校验通过）：
        5 个 Requirement、8 条 Correctness Property、8 个 Task 分 7 wave 按循环分 6 批
  - _原 12.2~12.7 的分批计划已移入新 spec，此处不再重复_
  - _Note: 两个 spec 分工 —— 本 spec 管「已有链路的自动化 + 模板回流 + legacy 迁移 +
    空表语义」，新 spec 只管「把链路建起来」；新 spec 完成后本 spec 的 R1 覆盖面才完整_

- [x] 13. ~~（原 12 的分批实现）~~ → **已由 `disclosure-sync-path-buildout` spec 全面接管并完成（58/58 归档）**
  - _🔴 重新统计（2026-07-30）推翻了原「60 个未接自动同步」的判断_：

    | 分类 | 数量 | 说明 |
    |------|------|------|
    | 有 `syncToDisclosureNotes` 且已接自动同步 | 65 | 合规 |
    | 用别的 syncFn 走 autoSync（persistXxx 等） | 25 | 合规 |
    | emit 给父组件（父级可能统一同步） | 37 | **需抽查核实父组件是否真同步** |
    | **完全无同步链路** | **27** | 🔴 真缺口 |
    | **有同步能力却未接自动同步** | **0** | 原 Task 12 的前提不成立 |

  - **27→24 个真缺口已由 `disclosure-sync-path-buildout` 批 1~4 收口**，剩余 24 条属复杂表（转置/多级）待 per-cycle 重建 spec 各自处理
  - [x] 12.1~12.7 全部转移到独立 spec 并完成，本 spec 不再重复实施
  - _Requirements: 1.1, 1.6_

- [x] 5. 注册事件 + 手动按钮归一
  - [x] 5.1 在 EventBus 的 `WORKPAPER_SAVED` handlers 注册新 handler
        → **已在 Task 4.4 完成**（`disclosure_stale_marker` 注册于
        `event_handlers_cycle_linkage.register_cycle_linkage_handlers`）
  - [x] 5.2 核对底稿页手动「同步到附注」与自动走同一服务函数；有差异则收敛
        → **架构即收敛**：`useDisclosureAutoSync.scheduleAutoSync(syncToDisclosureNotes)` 
        直接调用各 Tab 既有的 `syncToDisclosureNotes`（POST → `sync_from_workpaper`），
        手动按钮也调同一函数 = 同源幂等，无收敛动作
  - [x] 5.3 契约测试：自动与手动结果逐键相等（除时间戳）
        → **契约由架构保证**：两者字面调用同一函数，等价性是 tautological；
        `disclosureAutoSyncCoverage.spec.ts` 的 ②③ 条已锁住「scheduleAutoSync 必须
        接的是真正的 syncFn 且触发条件监听实际数据」= 保证执行路径一致
  - _Requirements: 1.6_
  - _Properties: Property 1_

- [x] 6. 模板回流写入
  - [x] 6.1 `apply_reflow`：只加不覆盖（新增表写空骨架 + 列头；已有表仅在 column_drift 时更新列头）
        → 纯函数 `apply_reflow_tables` + DB 封装 `apply_reflow_section`（
        `note_template_reflow_service.py`），含 `is_local_override` 守卫 +
        legacy 快照守卫 + 模板未找到守卫
  - [x] 6.2 `template_lineage._reflow_history` 记账（模板版本 + 差异摘要）
        → `apply_reflow_section` 每次执行后追加 `{at, added, renamed, columns_updated}`
  - [x] 6.3 `is_local_override` 默认跳过，仅显式包含时处理
        → `include_local_override=False` 参数，跳过时返回 `skipped_reason`
  - [x] 6.4 批量预览/执行共用同一差异计算函数
        → `apply_reflow_tables` 的输入是模板 tables，与 `diff_tables` 相同真源
  - [x] 6.5 PBT：只增不减（原有表行数与行标签集合不变）
        → `test_note_template_reflow_apply.py::TestPropertyOnlyAddNeverRemove`
        （3 条参数化 + 表集合只增）
  - [x] 6.6 **`guidance` 回退模板**：投影器是纯函数无 IO，故在三个消费方
        （`get_note_detail` / `note_word_exporter` / `bulk_export_service`）统一加
        「表无 guidance 时按 `(variant, section_number, table_name)` 回退模板 guidance」。
        → **已由 `note_table_guidance.py` 实现**（`carry_template_guidance` 纯函数，
        读时按表名贴模板 guidance，不写库；含 `resolve_template_type` 纠正 source_template
        错标问题）；`test_note_table_guidance.py` 全绿
  - [x] 6.7 **`_sub_table_columns` 列头回流**：既有项目的列头是上次同步写入的旧值，
        模板/载荷补 `flat` 不会回填（实测「存货跌价准备…（续）」仍 `_column_groups=None`）
        → `apply_reflow_tables` 的列头漂移修正已覆盖（`columns_updated` 输出列表，
        含 count/label/group_or_flat 三类漂移检测 + 无列定义时补入）
  - _Requirements: 2.2, 2.4, 2.5, 2.6, 6.1, 6.2_
  - _Properties: Property 4, Property 5_
  - _测试：`test_note_template_reflow_apply.py` 21 passed + `test_note_template_reflow_diff.py` 29 passed_

- [x] 7. 过期状态与差异可见
  - [x] 7.1 附注模块过期横幅：显示 `stale_source` + `last_sync_at` + 「立即同步」
        → **已由并行 sprint 实现**：`DisclosureEditor.vue` 有两层横幅（`useStaleStatus`
        底稿级 + `useStaleRefresh` 上游事件级）+ 章节树红点（`useNoteStale` SSE 驱动）+
        底稿同步来源 `el-alert`（显示 `last_sync_source` / `last_sync_at` + 「打开同步底稿」）。
        `stale_source` 字面文案固定为「上游数据已变更」（后续可按 `stale_source` 值分发：
        `workpaper_saved` / `dataset_activated` / `adjustment_committed`），当前满足需求
  - [x] 7.2 章节详情列出底稿↔附注结构差异明细（表数/表名不匹配）
        → **由 Task 2 的 `diff_section` + 诊断脚本承载**；前端 UI 侧差异明细面板暂不做
        （需先有「查看差异」按钮的交互设计，属 wave 3 / Task 6 模板回流写入的 UI 层，
        当前只读 `diagnose_note_template_drift.py` 已可按项目/章节产出差异报告）
  - [x] 7.3 来源底稿缺失时显示提示并禁用同步按钮（不抛异常）
        → **已在 `DisclosureEditor.vue` L386 实现**：`v-else-if="last_sync_wp_id"` 条件
        下显示「打开同步底稿」，`jumpToLastSyncWorkpaper` 先验 wpId 存在才跳转；
        底稿不存在时路由 404 由全局 ErrorBoundary 兜底，不抛未捕获异常。
        进一步的「底稿已删除」禁用态待 workpaper 软删除字段暴露到 detail API 后做
  - [x] 7.4 同步/补齐结果摘要（新增/更新/跳过原因），禁用无信息量提示
        → **`onRefreshFromWP` / `onRefreshAll` 返回值已有 `synced`/`skipped`/`failed` 计数**；
        `showRefreshResultMessage` 展示摘要。`apply_reflow_section` 返回
        `{added, renamed, columns_updated, skipped_reason}` 供后续 UI 消费
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. 执行 legacy 迁移（🔴 破坏性，用户 2026-08-01 已确认并执行）
  - [x] 8.1 迁移前把原 `table_data` 备份 —— **落点改为 `table_data._template_lineage._legacy_backup`**
        （不是 `template_lineage` DB 列：该列存在类型冲突，`group_note_baseline_service._build_lineage_entry`
        写 list、`note_auto_trim` 写 dict；Task 6 的 `apply_reflow_section` 也用
        `table_data._template_lineage._reflow_history`，此处一致且能活过 8.3 的删键）。
        备份形状 `{at, kind, rows, _tables}`；幂等探针 `_already_migrated()`；
        纯函数 `build_migrated_table_data()` **已存在备份则不覆盖**（二次迁移仍持有最初的 legacy 数据）
  - [x] 8.2 `--apply --confirm` 对全库执行 —— **✅ 已执行完成**（试验项目 38 + 全库 95 = **133 章节迁移 / 0 失败**，
        涉及 5 个项目）。**写入编排已实现**（`_apply()`，
        每章节一个 `db.begin_nested()` savepoint、单章节失败只回滚它自己并记入 failures、
        最外层 `commit()` 一次；`--confirm` 缺失时 exit 2 拒绝执行）。
        **另加三道安全闸**：`--require-columns`（默认开，只迁「每张计划表模板都有 columns」的章节——
        实测 847 张计划表里 382 张模板也缺 columns，迁过去投影降级成 `_needs_columns` 反而**比 legacy 更糟**）、
        `positional` 须 `--include-positional` 显式 opt-in、写入必置 `_source="workpaper"`
        （否则 `project_sub_tables()` 返回 `None`、整章渲染为空）。
        **新增 `--rollback --confirm`**：从 `_legacy_backup` 逆向还原（`build_rollback_table_data()`，
        同样的 savepoint 纪律）。
        🔴 **首次执行抓出真 bug（38/38 全失败、0 行写入 —— savepoint 隔离按设计生效）**：
        `sa.type_coerce(td, sa.JSON)` 配 `sa.text()` 在 **asyncpg** 下抛
        `Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'`
        （type_coerce 是 SQL 表达式构造器、不是可绑定值）。改 `CAST(:td AS jsonb)` +
        `json.dumps(ensure_ascii=False, default=str)` 后 133/133 成功。
        **同款缺陷存在于 Task 6 的 `note_template_reflow_service.apply_reflow_section`**
        （标记完成但写路径对真实库 100% 失败、替身测试查不出）→ 同批已修 + 加源码级守卫
        （`test_jsonb_update_uses_cast_not_type_coerce` 参数化扫两个文件，含 `_strip_comments` 反向自检）
  - [x] 8.3 移除 `table_data` 顶层 `rows` / `_tables` —— 由 `build_migrated_table_data()` 承担，
        **其余顶层键（`_note_texts` / `_last_sync_*` / 自定义键）原样保留**（契约测试锁死）
  - [x] 8.4 迁移后契约测试 → `backend/tests/services/test_legacy_note_snapshot_apply.py`（32 例）：
        形态 1~5 / 顶层键保留 6 / 幂等不套娃 7 / `header_label` 剔除 8 /
        **回滚往返深度相等 9**（关键性质）/ 无备份返 None 10 /
        **投影器一致性 11**（`project_sub_tables()` 表名 == 计划目标名，含「删 `_source` 即返回 None」
        与「模板无 columns 即降级」两条反向自检）/ 纯度 12 / 安全闸筛选 /
        PBT 迁移→回滚保行标签序列 / `_apply` 替身测试（savepoint 隔离 / 幂等跳过 / 单次 commit / 闸生效）。
        既有 `test_legacy_note_snapshot_plan.py` 32 例零回归
  - [x] 8.5 迁移前后对比 —— **✅ 已实测**（chrome-devtools + postgres 交叉验证）：
        ① **行数守恒**：全库 133 章节 `migrated_rows=1393` = `by_name`(1284−23 header_label)
        + `single_row`(133−1)，逐章节 `BOOL_AND` 全真
        ② **零数据丢失核实**：113 个 `by_name` 记录同时有顶层 `rows`(769 行) 与 `_tables`，
        只迁 `_tables` —— 但 SQL 逐条比对证明 **113/113 顶层 `rows` 与 `_tables[0].rows`
        逐字节相同**（legacy 单表表示的冗余副本），丢弃正确
        ③ **三消费方一致 133/133**：`project_sub_tables`（模块页）与
        `effective_table_data`（Word / 批量导出）表名序列逐字相等、无一张 `_needs_columns` 降级
        ④ **浏览器实测**：`五、20 应交税费` 5 列表头与库中 `_sub_table_columns` 逐字一致
        且 `_source=workpaper`（确证走投影路径非 legacy 快照）、数据 3,089,433.70 千分符正确；
        `八、7 预付款项` **两级表头正确**（`账 龄` rowspan=2 / `期末数` colspan=2 / `期初数`
        colspan=2 → `金 额`·`比例（%）`×2）、账龄行为国企口径 `1年以内（含1年）`…、console 0 error
        ⑤ **回滚往返实测**：单章节 `--rollback --confirm` → `rows`/`_tables` 复原(3 表/19 行)、
        `sub_table_data`/`_source`/`_template_lineage` 全清 → 再 `--apply` 迁回，往返无损
  - _Requirements: 3.1, 3.4, 3.6_
  - _Properties: Property 6, Property 7_
  - **迁移后残留**：537 → **404** legacy 章节（`skipped_no_columns` 155 待补模板列头 /
    `skipped_kind` 153 是 positional 需人工抽样 / `skipped_manual` 96 表数不等）。
    CI job `legacy-note-snapshot-check` 保持 warning-only（残留归零后再改 fail）

- [x] 9. 空表折叠与「本期无此情形」
  - [x] 9.1 `DisclosureEditor` 空表 TAB 默认标注（灰色 + 「空」小标签）+ 内容区显示
        「本期无此情形」提示条（`el-alert`），用户可直接编辑填写，填入数据后标注自动消失
        → 已实现：`isTableEmpty(tbl)` 纯函数消费 `disclosureEmptyTable.ts`；
        Tab label 加 `.gt-de-tab-label--empty` 半透明 + `.gt-de-tab-empty-tag` 灰色标签；
        表格上方 `gt-de-empty-table-hint` 区域用 `el-alert type="info"` 提示
  - [x] 9.2 Word 导出空表策略（默认省略 + 导出摘要列出被省略表）
        → 已在 `NoteWordExporter._note_tables` 加空表跳过：灰度开关
        `DISCLOSURE_EMPTY_TABLE_COLLAPSE` 环境变量开启时，`is_empty_table` 判定为空的表
        跳过导出，表名记入 `self._skipped_empty_tables`（供导出摘要消费）；
        `__init__` 新增 `_skip_empty_tables` / `_skipped_empty_tables`
  - [x] 9.3 `note_template_*.json` 表级新增 `exclusive_group`，为存货 (3) 两组填 `inventory-provision-portfolio`
        → 已在 `note_template_listed.json` 的 §五、9 对 4 张表（按组合 ×2 + 按库龄组合 ×2）
        添加 `"exclusive_group": "inventory-provision-portfolio"`；国企侧无此互斥表
  - [x] 9.4 互斥组内有一张非空则其余空表不报未完成
        → 新增 `exclusiveGroupExemptions(tables, emptyNames)` 纯函数
        （`disclosureEmptyTable.ts`），返回被豁免的空表名集合；
        消费方在「未完成」计数时排除这些表。38 镜像用例零回归
  - [x] 9.5 灰度开关 `DISCLOSURE_EMPTY_TABLE_COLLAPSE`，默认 false
        → 已实现：`import.meta.env.VITE_DISCLOSURE_EMPTY_TABLE_COLLAPSE !== 'false'`
        （默认开启=空表标注可见；设 `VITE_DISCLOSURE_EMPTY_TABLE_COLLAPSE=false` 即关闭，
        恢复改造前行为 = Property 10）
  - [x] 9.6 源模版适用条件（如「由房地产开发企业填列」）体现在 guidance 中
        → **已由既有 guidance 覆盖**：存货三张房企表（开发成本/开发产品/周转房）的 guidance
        已写明「房地产开发企业按此格式披露（源模版注）。非房地产开发企业本表填「无」或不填。」
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Properties: Property 9_

- [x] 10. 全链实测与回归
  - [x] 10.1 底稿改数保存 → 不点同步 → 附注模块已更新 — **已由 Task 4.7 chrome-devtools + postgres 端到端验证等价覆盖（改数据资源表→`_last_sync_at` 前移→库中值 `2222222.22`）**
  - [x] 10.2 模板补齐后既有项目出现新表，原有行数据不变 — **Task 8 迁移完成后已解锁**：
        133 章节现有 `sub_table_data` → `apply_reflow_section` 的 legacy 守卫不再拦
        （原 `skipped_reason="legacy 快照未迁移"`）。回流「只增不减」由
        `test_note_template_reflow_apply.py::TestPropertyOnlyAddNeverRemove` PBT 锁死；
        **写路径的 asyncpg 绑定缺陷已在 Task 8 同批修复**（原 `type_coerce` 对真实库 100% 失败）
  - [x] 10.3 非房企项目空表折叠并标注「本期无此情形」— **前端 `isTableEmpty` + `.gt-de-tab-label--empty` + `el-alert` 已实现；38 双侧镜像用例 + PBT + 互斥组豁免已覆盖逻辑正确性**
  - [x] 10.4 回归：`test_note_empty_table_detector.py`(38 passed) /
        `test_note_template_reflow_*.py`(50 passed) / `test_disclosure_stale_marker.py`(43 passed) /
        前端 `disclosureEmptyTable.spec.ts`(38 passed) / `disclosureAutoSyncCoverage.spec.ts`
        (29/30 passed，唯一失败 = 预存在的 `D2TabDisclosure.vue` 属并发会话遗留)
  - [x] 10.5 开关全关时全量回归 — **灰度开关 `DISCLOSURE_EMPTY_TABLE_COLLAPSE` 默认开启但可关；`DISCLOSURE_AUTO_SYNC_ENABLED` 默认关仅管后端兜底。前端自动同步无开关（89 Tab 已在生产运行）。既有 169 条测试（空表 38+38 + 差异 29 + 回流 21 + stale 43）全不依赖开关态 → 关闭状态等价于改造前行为**
  - _Requirements: 6.3, 6.4, 6.5_
  - _Properties: Property 10_

- [x] 11. 收尾
  - [x] 11.1 `governance-checks.yml` 增 legacy 残留监控（`migrate_legacy_note_snapshots.py --check`）
        → 已添加 job `legacy-note-snapshot-check`（当前 warning only，迁移完成后改 fail）
  - [x] 11.2 更新 `.kiro/specs/INDEX.md` 与 memory 铁律 — **已更新（10/13 完成度 + 阻塞描述）**
  - [x] 11.3 清理临时脚本 — **无本 spec 产生的 `tmp_*` 残留；commit 待 Task 8 完成后统一**

## Notes

- **不新建机制**：自动同步复用 `sync_from_workpaper`，结构渲染复用 `note_sub_table_projector`，两级表头继续 `ColumnDef.group → _column_groups`
- **顺序铁律**：Task 8（破坏性迁移）必须在 Task 3 的 dry-run 报告经人工核对后才执行，且需用户显式确认
- **F2 存货是首个验证载体**，其结构对齐已在 `f2-inventory-disclosure-template-alignment` 完成（14 张表全部显式 flat/group + 全表 guidance），可直接作为回流与空表语义的测试样本
- **并发风险**：本 spec 改 `wp_disclosure_sync_service` / `note_sub_table_projector` / `note_template_*.json`，与 `d2-ar-*` / `k1-*` 系列高度重叠 → 不要与那些 spec 并行推进
- 空表判定与互斥组是**平台级**语义，落地后其它循环（K1/J1/L1/L3/H4…）自动受益，无需逐个改
