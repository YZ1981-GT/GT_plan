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

- [ ] 4. 自动同步（🔴 **方向已修正**：机制早已存在于前端，本任务是修触发条件 + 补覆盖）
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

- [ ] 13. ~~（原 12 的分批实现）~~ → 见 `disclosure-sync-path-buildout`
  - _🔴 重新统计（2026-07-30）推翻了原「60 个未接自动同步」的判断_：

    | 分类 | 数量 | 说明 |
    |------|------|------|
    | 有 `syncToDisclosureNotes` 且已接自动同步 | 65 | 合规 |
    | 用别的 syncFn 走 autoSync（persistXxx 等） | 25 | 合规 |
    | emit 给父组件（父级可能统一同步） | 37 | **需抽查核实父组件是否真同步** |
    | **完全无同步链路** | **27** | 🔴 真缺口 |
    | **有同步能力却未接自动同步** | **0** | 原 Task 12 的前提不成立 |

  - **27 个真缺口的严重性**：这些 Tab **没有 `syncToDisclosureNotes`、不打
    `sync-from-workpaper` 端点、也不 emit** —— 披露数据只停在 `checklist_responses`，
    附注模块**永远拿不到**。抽查 `N2TabDisclosureListed` / `L2TabDisclosureListed`
    确认 `disclosure-notes` 端点 0 命中。这是全库 569 个章节仍是 legacy 快照的
    根本原因之一（不是「没人点同步」，而是**压根没有同步入口**）。
  - 清单：D2 / F4×2 / G4×2·G5×2·G6·G8Base·G12×2 / H4·H5·H6×2·H7×2 /
    J2×2 / L2×2 / M7×2 / N2×2 / N5×2（守卫 `MISSING_SYNC_PATH` 已固化，只允许变短）
  - **单个 Tab 的补齐工作量对齐 F2/K1 单循环量级**：sheet→section 映射
    （`XNoteSectionMap.ts`）+ 载荷构建器（`buildXSyncPayload`）+ `columns` 定义 +
    `syncToDisclosureNotes` + 自动同步接线 + 附注模板侧表结构核对
  - [ ] 12.1 先核实 37 个 emit 型 Tab 的父组件是否真的同步（可能有一批是假 emit）
  - [ ] 12.2 批 1：D2 / F4×2（与 `d2-ar-disclosure-*` in-flight spec 重叠，需协调）
  - [ ] 12.3 批 2：G4×2 / G5×2 / G6 / G8Base / G12×2（8 个）
  - [ ] 12.4 批 3：H4 / H5 / H6×2 / H7×2（6 个）
  - [ ] 12.5 批 4：J2×2 / L2×2 / M7×2（6 个）
  - [ ] 12.6 批 5：N2×2 / N5×2（4 个）
  - [ ] 12.7 每批完成后从守卫的 `MISSING_SYNC_PATH` 移出，`length` 断言同步下调
  - _Requirements: 1.1, 1.6_
  - _Note: 本任务实质是「给 27 个循环建披露→附注链路」，规模接近一个独立 spec；
    若单独立项，本 spec 的 R1 应改为只覆盖「已有链路的 Tab 自动同步」_

- [ ] 5. 注册事件 + 手动按钮归一
  - [ ] 5.1 在 EventBus 的 `WORKPAPER_SAVED` handlers 注册新 handler
  - [ ] 5.2 核对底稿页手动「同步到附注」与自动走同一服务函数；有差异则收敛
  - [ ] 5.3 契约测试：自动与手动结果逐键相等（除时间戳）
  - _Requirements: 1.6_
  - _Properties: Property 1_

- [ ] 6. 模板回流写入
  - [ ] 6.1 `apply_reflow`：只加不覆盖（新增表写空骨架 + 列头；已有表仅在 column_drift 时更新列头）
  - [ ] 6.2 `template_lineage._reflow_history` 记账（模板版本 + 差异摘要）
  - [ ] 6.3 `is_local_override` 默认跳过，仅显式包含时处理
  - [ ] 6.4 批量预览/执行共用同一差异计算函数
  - [ ] 6.5 PBT：只增不减（原有表行数与行标签集合不变）
  - [ ] 6.6 **`guidance` 回退模板**：投影器是纯函数无 IO，故在三个消费方
        （`get_note_detail` / `note_word_exporter` / `bulk_export_service`）统一加
        「表无 guidance 时按 `(variant, section_number, table_name)` 回退模板 guidance」。
        实测依据：F2 存货 14 张表补 guidance 后，既有已同步项目投影结果仍全为 0 字
        （guidance 只经 `_carry_seed_table_guidance` 在 seed 路径生效）
  - [ ] 6.7 **`_sub_table_columns` 列头回流**：既有项目的列头是上次同步写入的旧值，
        模板/载荷补 `flat` 不会回填（实测「存货跌价准备…（续）」仍 `_column_groups=None`）
        → 回流须能按模板修订既有章节的列头元数据
  - _Requirements: 2.2, 2.4, 2.5, 2.6, 6.1, 6.2_
  - _Properties: Property 4, Property 5_

- [ ] 7. 过期状态与差异可见
  - [ ] 7.1 附注模块过期横幅：显示 `stale_source` + `last_sync_at` + 「立即同步」
  - [ ] 7.2 章节详情列出底稿↔附注结构差异明细（表数/表名不匹配）
  - [ ] 7.3 来源底稿缺失时显示提示并禁用同步按钮（不抛异常）
  - [ ] 7.4 同步/补齐结果摘要（新增/更新/跳过原因），禁用无信息量提示
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 8. 执行 legacy 迁移（🔴 破坏性，须用户显式确认）
  - [ ] 8.1 迁移前把原 `table_data` 备份到 `template_lineage._legacy_backup`
  - [ ] 8.2 `--apply --confirm` 对全库执行；失败章节跳过并记报告，不部分写入
  - [ ] 8.3 移除 `table_data` 顶层 `rows` / `_tables`
  - [ ] 8.4 迁移后契约测试：三消费方（模块页 / Word / 批量导出）结构一致
  - [ ] 8.5 单项目 Playwright 迁移前后对比（表集合 + 截图）
  - _Requirements: 3.1, 3.4, 3.6_
  - _Properties: Property 6, Property 7_

- [ ] 9. 空表折叠与「本期无此情形」
  - [ ] 9.1 `DisclosureEditor` 空表 TAB 默认折叠 + 标注，可展开填写，展开即取消标注
  - [ ] 9.2 Word 导出空表策略（默认省略 + 导出摘要列出被省略表）
  - [ ] 9.3 `note_template_*.json` 表级新增 `exclusive_group`，为存货 (3) 两组填 `inventory-provision-portfolio`
  - [ ] 9.4 互斥组内有一张非空则其余空表不报未完成
  - [ ] 9.5 灰度开关 `DISCLOSURE_EMPTY_TABLE_COLLAPSE`，默认 false
  - [ ] 9.6 源模版适用条件（如「由房地产开发企业填列」）体现在 guidance 中
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Properties: Property 9_

- [ ] 10. 全链实测与回归
  - [ ] 10.1 Playwright：底稿改数保存 → 不点同步 → 附注模块已更新
  - [ ] 10.2 Playwright：模板补齐后既有项目出现新表，原有行数据不变
  - [ ] 10.3 Playwright：非房企项目空表折叠并标注「本期无此情形」
  - [ ] 10.4 回归：`test_note_inventory_structure.py` / `test_note_word_export_sub_table.py` / `test_f2_disclosure_import_export.py` / `f2NoteSectionMap.spec.ts` 全绿
  - [ ] 10.5 开关全关时跑一遍全量，确认与改造前一致
  - _Requirements: 6.3, 6.4, 6.5_
  - _Properties: Property 10_

- [ ] 11. 收尾
  - [ ] 11.1 `governance-checks.yml` 增 legacy 残留监控（`migrate_legacy_note_snapshots.py --check`）
  - [ ] 11.2 更新 `.kiro/specs/INDEX.md` 与 memory 铁律
  - [ ] 11.3 清理临时脚本；单 commit

## Notes

- **不新建机制**：自动同步复用 `sync_from_workpaper`，结构渲染复用 `note_sub_table_projector`，两级表头继续 `ColumnDef.group → _column_groups`
- **顺序铁律**：Task 8（破坏性迁移）必须在 Task 3 的 dry-run 报告经人工核对后才执行，且需用户显式确认
- **F2 存货是首个验证载体**，其结构对齐已在 `f2-inventory-disclosure-template-alignment` 完成（14 张表全部显式 flat/group + 全表 guidance），可直接作为回流与空表语义的测试样本
- **并发风险**：本 spec 改 `wp_disclosure_sync_service` / `note_sub_table_projector` / `note_template_*.json`，与 `d2-ar-*` / `k1-*` 系列高度重叠 → 不要与那些 spec 并行推进
- 空表判定与互斥组是**平台级**语义，落地后其它循环（K1/J1/L1/L3/H4…）自动受益，无需逐个改
