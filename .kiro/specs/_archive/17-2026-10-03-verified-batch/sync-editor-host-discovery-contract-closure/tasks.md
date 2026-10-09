# Implementation Plan — 同步编辑器宿主纳入挂点发现契约

## Overview

**spec**：`sync-editor-host-discovery-contract-closure`　**创建**：2026-10-01　**状态**：16/16 ✅ 全完成
**缺陷**：发现器不认 `WorkpaperSyncEditorHost` ⇒ 宿主完成双向迁移后其 entry 直接消失
（现算 51 个宿主无 entry：34 个 `d4/**` tab 已消失、17 个 A 类本轮消失）。
**上游事实**：全部现算于 2026-10-01，见 design §一。

`[ ]*` = 依赖外部供给（并发会话未提交文件 / 真栈环境）。

🔴 **三条不得违反的边界**（design §六.3）：不改任何既有 entry_id · 不翻 45 个双挂 entry 的
能力裁决 · 不代各 lane 重生成其冻结 slice/record。

## Tasks

### 阶段 0 — 红基线（先让缺口可见）

- [x] 0. 建守卫骨架 + 缺口不变量的**红基线**
  - 新建 `backend/tests/workpaper_sync/test_sync_editor_host_discovery_contract.py`
  - 判据「每个挂 EditorHost 的宿主都有 entry」**现在必须是红的**，且红的内容要点名
    51 个无 entry 宿主（分母现算、禁写死 96）
  - 判据「L1/L2/L3 三层覆盖之和 == EditorHost 宿主总数」先以**纯扫描**形态成立（不依赖生成器）
  - _Requirements: 4.1, 4.2, 2.6_

- [x] 1. `manifest.stats` 自洽判据（独立于本缺陷，但同属「没人守住」的一类）
  - 断言 `capability_counts` / `entry_count` 与 `entries` 现算逐值相等
  - 🔴 变异证明：手改一份内存副本的 stats 后判据须打红
  - 登记实证来由：`1ec6a1050` 曾手改 D1 的 capability 而未重跑生成器，stats 与 entries 不一致长期无人发现
  - _Requirements: 4.3_

### 阶段 1 — 发现器纳入 EditorHost（前端）

- [x] 2. `TARGETS` 增加第 4 条，`documentType: null`
  - `workpapersynceditorhost` → `{component, canonicalFile: '…/sync/WorkpaperSyncEditorHost.vue', localName, documentType: null}`
  - 断言静态 import 与 `defineAsyncComponent` 两种绑定都能命中（现算两种都有）
  - _Requirements: 1.1, 1.2_

- [x] 3. 实现 L1（同文件兄弟挂点继承 document_type）
  - 同文件其他挂点的 `documentType` 集合 size==1 取之；size>1 抛错
  - 新增挂点字段 `documentTypeSource: 'sibling_mount'`
  - 判据：L1 覆盖现算 **45**，且 legacy document_type 全为 `xlsx`、零冲突
  - _Requirements: 2.1_

- [x] 4. 实现 L2（模板 AST 里的 `entry-id` 静态字面量）
  - 🔴 扫**属性节点**，与读 `sheet-name` 同口径；**不扫注释、不跨文件**
  - 去重后 size==1 取之并解析前缀为 document_type；size>1 抛错
  - 新增挂点字段 `entryIdDeclaration` / `documentTypeSource: 'entry_id_declaration'`
  - 判据：L2 覆盖现算 **21**（17 self + 4 parent）
  - 🔴 变异证明：把某宿主的 `entry-id` 声明挪进注释后，它须落到 L3（而不是仍被 L2 命中）
  - _Requirements: 2.2, 风险表第 3 行_

- [x] 5. L1/L2 交叉校验 + fail closed
  - 41 个同时有 L1、L2 信号的宿主，两者 document_type 须一致（现算冲突 0）；不一致抛错
  - L1、L2 均不成立时**保留 `documentType: null` + `needsOverlayRule: true`**，交生成器 L3
  - 🔴 **不得**在发现器里兜底成 `xlsx`（design §二 C 方案被否决的理由）
  - _Requirements: 2.4, 2.5, 1.3_

- [x] 6. mountId 唯一性与 `stats.byComponent`
  - EditorHost 挂点的 `sheetExpression` / `wpExpression` 恒空 ⇒ 只靠 `templateNodeOrdinal` 区分
  - 判据：全量挂点 mountId 零重复（发现器既有检查）+ 变异证明（人为造同 ordinal 须打红）
  - `stats.byComponent` 现算含第 4 键
  - _Requirements: 1.4, 5.1 的 digest 归因输入_

### 阶段 2 — 生成器：分组键换轨 + L3

- [x] 7. `_group_source_facts` 分组键 `(file, component)` → `(file, document_type)`
  - 🔴 前置现算确认：没有宿主同时挂 xlsx 与 docx 的 legacy 组件（现算 **0**）⇒ 不会并掉现有 entry
  - `_entry_id` 签名与算法**逐字不变**
  - 判据：45 个双挂 entry 的 `entry_id` 在改动前后逐值相等（按 HEAD 产物对账）
  - _Requirements: 3.1, 3.2_

- [x] 8. `_primary_component(group)` + 组件优先级
  - 优先级元组：`GtOnlyOfficeSheet > OnlyOfficeWordDialog > WorkpaperWordEditor > WorkpaperSyncEditorHost`
  - `defaults_by_component` / `_source_match` / `_assert_expected_profile` 全部改用主组件
  - 🔴 **零 churn 判据**：45 个双挂 entry 的 `capability` / `html_store` / `canonical_resolver` /
    `migration_state` 在改动前后逐值相等
  - _Requirements: 3.3_

- [x] 9. overlay 新增 `sync_host_entry_rules`（L3）+ `defaults_by_component["WorkpaperSyncEditorHost"]`
  - L3 规则一条：`d4/**/*.vue` × `WorkpaperSyncEditorHost` → `xlsx/gt-d4-operating-revenue`，
    reason 写明它是被删掉的那条 `d4/**` parent_rule 的新载体表达
  - 新 default 的 `expected_profile` **必须由 51 个新 entry 的真实派生结果实证**，不可照抄
    `GtOnlyOfficeSheet` 的取值域（照抄会让 `_declared_expectations` 的 stale 门失效）
  - `sync_host_entry_rules` 接入 stale-rule 门（零匹配规则 ⇒ 抛 `stale overlay sync_host_entry_rules`）
  - _Requirements: 2.3, 3.6_

- [x] 10. 「独立 entry / parent_duplicate」判定 + 两条 parent 来源互斥
  - 声明值 == `_entry_id(doc, file)` ⇒ 独立；!= ⇒ `parent_duplicate` + `parent_entry_id` = 声明值
    + `adapter_id = None` + `migration_state = "parent_duplicate"`（复用既有机制）
  - 既有 `parent_rules` 与 L2/L3 声明同时命中 ⇒ 抛错（不得静默取其一）
  - 判据：34 个 d4 tab 全部成为 `xlsx/gt-d4-operating-revenue` 的 parent_duplicate；
    17 个 A 类全部独立且 entry_id == 其历史值（`xlsx/gt-a51-cashflow-audit` 等）
  - _Requirements: 3.6_

- [x] 11. entry 新增 `mount_components` / `sync_editor_host_mounted`
  - 加入 `_REQUIRED_ENTRY_FIELDS`；判据断言 manifest 内无 `document_type: null`
  - 判据：`sync_editor_host_mounted == true` 的 entry 数 == 现算 EditorHost 宿主去重后的 entry 数
  - _Requirements: 3.4, 1.3_

- [x] 12. `stable entry_id collision` 回归锁
  - 保留该检查；🔴 变异证明：人为构造同 `(file, document_type)` 的第二组须抛错
  - _Requirements: 3.7_

### 阶段 3 — 复核门、产物与 a51 归位

- [x] 13. 复核 mount diff 并更新 `approved_source_digest`
  - 🔴 用**不含行号的语义键**做 diff（`mountId` 内嵌 `sourceSpan`，按它比会得出假象）
  - 现跑 discoverer **两次**确认 digest 稳定（并发会话在改 17 个 A 类宿主）
  - `review_basis` 如实写明：新增 96 条 EditorHost 挂点 · 未提交文件清单与数量 · 本 spec 编号
  - SHALL NOT 顺手批准任何与本 spec 无关的挂点变化
  - _Requirements: 5.1_

- [x] 14. 重生成四件产物 + a51 归位
  - `generate_workpaper_sync_manifest.py --apply` + `generate_workpaper_sync_legacy_baseline.py --apply`
  - 验收：`entry_count == 189`（17+34 现算核对）· `independent_entry_count == 142` ·
    `parent_duplicate_count == 46` · 45 个双挂 entry 零 churn
  - a51 裁决从 `deferred_overrides` 移回 `overrides`，`deferred_overrides` 删空；
    删除 `test_g_cycle_bidirectional_overlay_adjudication.py::TestDeferredOverrideStaysRestorable`
    整类与 `TestDiscoveryContractGap` 整类（其存在前提已消失）
  - 验收：`xlsx/gt-a51-cashflow-audit` 在 manifest 内且 `capability == bidirectional`、
    `build_manifest_registration_plan` 判其 `blocked_reason is None`
  - _Requirements: 4.4, 5.2, 5.3_

- [x] 15. 阶段 0 的红基线转绿 + 全部变异证明复跑
  - 「每个挂 EditorHost 的宿主都有 entry」从红转绿，无 entry 宿主数 **0**
  - 🔴 变异证明逐条跑：摘掉 `TARGETS` 第 4 条 ⇒ 该判据打红；删掉 L3 glob 规则 ⇒
    生成器 fail closed（而非静默少 30 条 entry）
  - _Requirements: 4.1, 4.5, 1.5, 2.3_

- [x] 16. 回归归因（**只登记不代改**）+ 门禁与收尾
  - A/B 归因：把四件产物临时还原为 HEAD 跑同一组测试，按 sha256 **强制还原**；
    🔴 **禁 `git stash`**（工作树有并发会话在途改动）
  - 把「本轮引入」的红逐条登记到各 lane 的 tasks.md，写明根因「冻结 slice/record 编码了旧 entry 数」
    与「重生成需 owner 复核」；**不代改**
  - `check_sync_provider_golden_digest.py`：断言 G 域零漂移；他人未提交改动导致的漂移如实归因，
    **不执行 `--update`**
  - 清理 `_fx_*` 探针；INDEX.md 登记本 spec
  - _Requirements: 5.4, 5.5_

## Task Dependency Graph

```json
{
  "0": [], "1": [],
  "2": ["0"], "3": ["2"], "4": ["2"], "5": ["3", "4"], "6": ["2"],
  "7": ["5"], "8": ["7"], "9": ["5"], "10": ["9"], "11": ["8", "10"], "12": ["7"],
  "13": ["6", "11", "12"], "14": ["13"], "15": ["14"], "16": ["15"]
}
```
