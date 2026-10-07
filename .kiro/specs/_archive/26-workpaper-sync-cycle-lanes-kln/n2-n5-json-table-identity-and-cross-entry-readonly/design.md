# N2 / N5 整表 JSON 行身份与跨 entry 只读 — 设计

## 概述

本 spec 是 N 循环三份 sync spec 的 **lane3**，承担 `xlsx/gt-n2-taxes-payable` 与 `xlsx/gt-n5-income-tax-expense` 两条 entry，是三份中**规模最大**的一份（sheets / 公式格 / 带 fx sheet 三项均过半）。共同判据 **NC-1 ~ NC-37** 已在 `n-cycle-sync-foundation-and-first-canary`（foundation）裁定，本文**只引用编号**。

**主题**：整表 JSON 行表身份 + 跨 entry 只读引用。**BP-12（{N5}）完整内聚**；BP-8（{N1,N2,N5}）与 BP-5（{N4,N5}）横跨，本 spec 只处理 N2 / N5 侧。

## 本 spec 归属份额（须与 foundation 算术自检表逐行对齐）

| 量 | N2 | N5 | 本 spec | 全域 | 本 spec 占比 |
|---|---|---|---|---|---|
| sheets | **18** | 16 | **34** | 59 | **58%** |
| 公式格 | **710** | 484 | **1194** | 2185 | **55%** |
| 带 fx sheet | 16 | 14 | **30** | 49 | **61%** |
| HTML child | 14 | 13 | **27** | 45 | 60% |
| prog console | 0 | 0 | **0** | 2 | 0% |
| OO 兜底 | 4 | 3 | **7** | 12 | 58% |
| OO 挂点 mount | 3 | 4 | **7** | 15 | 47% |
| orphan | 1 | 2 | **3** | 8 | 38% |
| live dual-mode | 1 | 0 | **1** | 2 | 50% |
| 宿主内联载体 | 0 | 1 | **1** | 3 | 33% |
| 超列真缺陷（族 A1） | 0 | 2 | **2** | 14 | 14% |
| `definedName` total / broken | 24 / 15 | **0 / 0** | **24 / 15** | 72 / 45 | 33% |
| 真库行数 | 6 | 4 | **10** | 30 | 33% |
| 跨 entry 污染 | 1 | 1 | **2** | 4 | 50% |
| 超宽 256 列表 | 0 | 1 | **1** | 2 | 50% |
| footer 缺斜杠 | 1 | 1 | **2** | 3 | 67% |
| BP 数 | 8 | **10** | — | — | — |

🔴 **N2 是全域 sheets（18）与公式格（710）双料最多的 entry**；**N5 是 BP 最多（10）的 entry**；🔴 **N5 是唯一 `definedName` 为 0 的 entry**（与 N4 并列，但 N4 归 foundation）。

## BP 收口路线

| BP | 成员 | 本 spec 动作 | 收口后 |
|---|---|---|---|
| BP-12 | {N5} | `useN5CrossSheet.ts` 8 键固化为只读契约 | **空集** |
| BP-8 | {N1, N2, N5} | 处理 N2 / N5 侧行身份（N1 归 lane2） | 余 {N1} → lane2 完成后空集 |
| BP-5 | {N4, N5} | 处理 N5 侧 inert 开关（判据在 foundation，N4 先做） | 余 {N4} → foundation 完成后空集 |
| BP-10 | {N1, N3} | 🔴 **本 spec 空分母**（N2 / N5 已采用共享路由） | 不涉及 |
| BP-1 / BP-2 / BP-3 | 全 5 条 | 平台级，标 `[ ]*` 不闭合 | 不变 |
| BP-6 / BP-7 / BP-9 / BP-11 | 全 5 条或含本 spec | 依 foundation 裁定执行 | 见 foundation |

BP 计数校验：N2 = {1,2,3,6,7,8,9,11} 共 **8** ✓ · N5 = {1,2,3,5,6,7,8,9,11,12} 共 **10** ✓。

## 两条 entry 的载体形态

### N2 — `per_entry_wrapper_over_shared_base`（17 行薄封装）

```
useN2DualMode.ts（17 行）
  ├─ 无 localStorage 键（分区逻辑在共享基类内）
  ├─ 生产边 1 条
  ├─ mode.value 赋值处 0（赋值在共享基类内）
  └─ 🔴 贡献共享基类 statement 边 1 条（全域 26 生产 + 1 测试 = 27；移除后 after 25）

门控（宿主）：v-if="isHtmlSheet && renderMode === 'onlyoffice'"
```

改造约束：若移除薄封装，须断言共享基类生产边 26 → 25，不留悬空计数。

### N5 — `host_inline_inert`（与 canary N4 逐字同形）

```
宿主 .vue 内联：
  const dualMode = {
      currentMode: ref<'html' | 'onlyoffice'>('html'),
      modeOptions: [...],            # 🔴 普通数组，不带 .value
      onModeChange: () => {}          # 🔴 空实现 = 结构性死代码
  }

门控（宿主）：v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
```

🔴 改造约束：与 N4 逐字同形 ⇒ BP-5 判据正文由 foundation 定义，本 spec **在 foundation 任务 13 之后**复用其已验证形态，不并行发明。

### N5 的结构异形

```
useN1Adjudication.ts ✓   useN2Adjudication.ts ✓   useN3Adjudication.ts ✓   useN4Adjudication.ts ✓
useN5Adjudication.ts ✗   🔴 不存在 ⇒ N5 的 ElMessageBox.confirm 落在 N5TabAdjudication.vue
```

⇒ 确认门判据按「每 entry 至少一处 confirm」，不按「每 entry 有同名 composable」（依 NC-4）。

## 跨 entry 只读契约（BP-12）

`useN5CrossSheet.ts` 现算 **8** 个外部键，跨 **5** 个命名空间：

| 命名空间 | 键 | 方向 |
|---|---|---|
| A（报表/调整） | `A-accounting-profit` · `A-profit-total` | 只读 |
| I2（无形资产） | `I2-1-audited-total` | 只读 |
| I6 | `I6-1-audited-total` | 只读 |
| N1（本循环） | `N1-1-total-audited` · `N1-1-total-begin` | 只读 |
| N3（本循环） | `N3-1-change-total` · `N3-1-end-balance-total` | 只读 |

另 `N5TabDeferredReconcile.vue` 引用 `N1-1` / `N3-1`。

🔴 **双向都要登记**（依 NC-19）：N 键**被外部引用**的一侧为 `nCycleTaxConsistency.ts` **10** 处 · `cycleImportExportRegistry.generated.ts` **6**（generated）· `workpaperSyncManifest.generated.ts` **4**（generated）· `ForceGraph.stories.ts` 3。其中 🔴 `nCycleTaxConsistency.ts` 连 `^n[1-5]` 正则也不匹配（`nCycle` 开头）却引用 N 键 10 处 ⇒ 文件集判据须三路取并（依 NC-5）。

键总数：**N5 10 键**（含 5 cross，全域最多）· **N2 7 键**。

## 模板层缺陷台账（本 spec 份额，只登记不修改）

| # | 位置 | 形态 | 性质 | 反向分母 |
|---|---|---|---|---|
| T-2 | `N5/加计扣除研发费用情况明细表N5-6-1` **E12** | `=C12+`**`N5`**（应为 `D12`） | 🔴 真缺陷，静默吞第三分量 | **37 : 1** |
| T-3 | `N5/递延所得税费用核对表N5-8` **H12** | `=C12-B12+`**`N5`**`-E12-F12+G12` | 🔴 真缺陷，**连带 r39 `=SUM(H10:H38)` 错** | **28 : 1** |
| T-5b | `N5-6-1 D11` | `=SUM(D5:N16)` | ✅ 合法（SUM 忽略空列） | — |
| T-7 | `附注披露信息（国企`（N5） | 缺右括号 | 脏字面量 | — |
| T-9 | `…N3A (原底稿)`（N5 册） | 同码存在于 N3 册与 N5 册 | 🔴 跨册碰撞，**横跨 lane2** | — |
| T-10a | `表O1A （原底稿）`（N2 册） | 外来字母码 + **全角空格 + 全角括号** | 跨册复制残留 | — |
| T-11b | `N5/附注披露信息（国企` | 255 列 / 有值列 4 / 幽灵 **251** | 遍历性能风险 | — |
| T-12 | `N2/出口退税额复核示例` · `N5/…N3A (原底稿)` | footer `&P&N` 缺斜杠 | 形态不一致 | 49 : 3（本 spec 占 2） |
| T-13b | N2 15 个 broken `definedName` | `#REF!` · `[1]Breakdown!#REF!` · 🔴 `'[2]2004'!#REF!` | 外部工作簿断链 | 24 : 15 |
| T-15 | `N5/纳税调整明细表N5-5` **r63** | 「合计」标签在 **B 列**非 A 列 | 判据须改「首个非空列」 | 33 : 1 |

🔴 **T-3 的扩散**：`N5-8` H12 恒空 ⇒ 其 r39 合计 `=SUM(H10:H38)` 连带错 —— 单元格级缺陷已扩散到合计层，是全域唯一有连带影响的超列缺陷。

🔴 **本 spec 无族 A2**（族 A2 的 11 处全在 lane2 的 `N3-2`）⇒ 本项对本 spec 空分母（依 NC-32 的分族纪律）。

## 契约字段映射（本 spec 份额）

| entry | `conclusion` 非空 | `remark` 非空 | 业务载荷实际所在 |
|---|---|---|---|
| N2 | **4** | 1（🔴 AI 会话 `N2-review-session-*` 261 B） | **100% 在 `conclusion`** |
| N5 | **3** | 1（🔴 AI 会话 `N5-review-session-*` 261 B） | **100% 在 `conclusion`** |
| 本 spec 合计 | **7** | **2**（两行全是 AI 会话） | — |

🔴 **本 spec 的 `remark` 非空行 100% 是 AI 会话** ⇒ 若不按白名单排除 `*-review-session-*`，会把 261 B 的会话记录当行表 JSON 解析（依 NC-34）。

## Property 清单（NB-P1 ~ NB-P22）

| # | 断言 | 现算值 | 关联 NC |
|---|---|---|---|
| NB-P1 | 归属份额 17 行逐行与 foundation 算术表对齐 | 见份额表 | NC-1 |
| NB-P2 | entry 2 条全名 · 科目跨类（2221 负债/贷 vs 6801 损益/借） | 2 | NC-22 |
| NB-P3 | 本 spec 三项过半（sheets 58% / 公式格 55% / 带 fx 61%） | 34 / 1194 / 30 | NC-1 |
| NB-P4 | `useN5CrossSheet.ts` 8 键跨 5 命名空间且**全只读** | 8 / 5 | NC-19 |
| NB-P5 | 无任何指向 A / I2 / I6 / N1 / N3 的写入路径 | 0 | NC-19 |
| NB-P6 | N 键被外部引用 4 源（含 `nCycleTaxConsistency.ts` 10 处） | 10 / 6 / 4 / 3 | NC-5 · NC-19 |
| NB-P7 | N5 10 键（含 5 cross，全域最多）· N2 7 键 | 10 / 7 | NC-19 |
| NB-P8 | BP-12 收口为空集 | 1 → 0 | NC-19 |
| NB-P9 | N2 / N5 行身份改造抄 E 族形态（禁自建） | 86 / 27 文件 | NC-6 |
| NB-P10 | `removeRow` by_index → by_rowid 单调方向 | 18 : 13 | NC-7 |
| NB-P11 | `N2-1-rows` · `N5-1-rows` · `N5-5-rows` 各 0 命中 | 0 | NC-30 |
| NB-P12 | owner 单一声明（N2 `'N2-'` 362 行 · N5 `'N5-'` 406 行） | 1 / 1 | NC-30 |
| NB-P13 | N5 inert → redeemable（复用 foundation 已验证形态） | 1 | NC-13 |
| NB-P14 | N5 `modeOptions` 为普通数组（不带 `.value`） | 1 | NC-2 |
| NB-P15 | N2 薄封装 17 行 · 共享基类边 26 → 25（若移除） | 26 / 25 | NC-11 |
| NB-P16 | 🔴 BP-10 对本 spec 空分母（N2 / N5 已采用共享路由） | 空分母 | NC-19 · NC-20 |
| NB-P17 | 🔴 `useN5Adjudication.ts` 不存在 · confirm 在 `N5TabAdjudication.vue` | 0 / 1 | NC-4 |
| NB-P18 | 发布门本 spec 2 处且不新增第 3 处 | 2 | NC-3 |
| NB-P19 | 契约 `conclusion` 非空 7 · `remark` 2 行全是 AI 会话须排除 | 7 / 2 | NC-34 |
| NB-P20 | 真库污染 2 条落 `wp_code='G8'` | 2 | NC-19 |
| NB-P21 | 族 A1 两处（37:1 / 28:1）· T-3 连带 r39 错 · 本 spec 无族 A2 | 2 / 0 | NC-32 |
| NB-P22 | footer 缺斜杠 2 · 超宽 251 幽灵 · 「合计」B 列 1 处 · N5 definedName 空分母 | 2 / 251 / 1 / 0 | NC-9 · NC-17 · NC-35 · NC-36 |

**编号完整性**：NB-P1 ~ NB-P22 连续 **22** 条，无缺号无重号，每条关联至少一个 NC 编号。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_n2_n5_json_identity_readonly.py`（新建）。

| 类名 | 覆盖 |
|---|---|
| `TestLane3Attribution` | NB-P1 ~ NB-P3 |
| `TestCrossEntryReadOnlyContract` | NB-P4 ~ NB-P8 |
| `TestJsonTableRowIdentity` | NB-P9 ~ NB-P12 |
| `TestN5InertSwitchRepair` | NB-P13 · NB-P14 |
| `TestN2WrapperAndSharedBase` | NB-P15 · NB-P16 |
| `TestConfirmGateAnomaly` | NB-P17 · NB-P18 |
| `TestContractFieldsLane3` | NB-P19 |
| `TestCrossEntryPollutionLane3` | NB-P20 |
| `TestTemplateDefectsLane3` | NB-P21 · NB-P22 |

**原则**（沿用 foundation 测试原则 1 ~ 4）：期望值现读得出禁写死 · 结构性零须配变异证明 · 模板 sha256 断言置前失败即中止 · 真库用 asyncpg 且无库时 skip 标原因。

🔴 **本 spec 额外原则**：① `N3A` 相关断言按 `(册, sheet 名)` 二元组定位并在注释指向 lane2 对应断言；② `*-review-session-*` 白名单必须在解析前生效（本 spec `remark` 非空行 100% 是该类型，漏排除会直接解析失败或产出脏数据）。
