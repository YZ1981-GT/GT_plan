# N1 / N3 宿主内联路由与共享路由采纳 — 设计

## 概述

本 spec 是 N 循环三份 sync spec 的 **lane2**，承担 `xlsx/gt-n1-deferred-tax-assets` 与 `xlsx/gt-n3-deferred-tax-liabilities` 两条 entry。共同判据 **NC-1 ~ NC-37** 已在 `n-cycle-sync-foundation-and-first-canary`（foundation）裁定，本文**只引用编号**。

**主题**：宿主内联 sheet 路由 + 未采用共享路由。两条 entry 构成 slice 的 `hosts_using_host_inline_regex: 2` 集合；**BP-4（{N3}）与 BP-10（{N1, N3}）完整内聚**，无跨 spec 协调成本。

## 本 spec 归属份额（须与 foundation 算术自检表逐行对齐）

| 量 | N1 | N3 | 本 spec | 全域 | 本 spec 占比 |
|---|---|---|---|---|---|
| sheets | 10 | 6 | **16** | 59 | 27% |
| 公式格 | 593 | 162 | **755** | 2185 | 35% |
| 带 fx sheet | 8 | 4 | **12** | 49 | 24% |
| HTML child | 8 | 4 | **12** | 45 | 27% |
| prog console | 1 | 0 | **1** | 2 | 50% |
| OO 兜底 | 1 | 2 | **3** | 12 | 25% |
| OO 挂点 mount | 2 | 3 | **5** | 15 | 33% |
| orphan | 1 | 1 | **2** | 8 | 25% |
| live dual-mode | 1 | 0 | **1** | 2 | 50% |
| 宿主内联载体 | 0 | 1 | **1** | 3 | 33% |
| 超列真缺陷 | 0 | 11 | **11** | 14 | 79% |
| `definedName` total / broken | 24 / 15 | 24 / 15 | **48 / 30** | 72 / 45 | 67% |
| 真库行数 | 17 | 2 | **19** | 30 | 63% |
| 跨 entry 污染 | 1 | 1 | **2** | 4 | 50% |
| 超宽 256 列表 | 1 | 0 | **1** | 2 | 50% |
| footer 缺斜杠 | 0 | 0 | **0** | 3 | 0% |
| BP 数 | 9 | 9 | — | — | — |

🔴 本 spec 在**超列真缺陷（79%）**与 **definedName broken（67%）**两项上占绝对多数，是模板层缺陷最集中的 lane。

## BP 收口路线

| BP | 成员 | 本 spec 动作 | 收口后 |
|---|---|---|---|
| BP-4 | {N3} | N3 宿主直调 health 收敛到统一能力层 + 修静默 return | **空集** |
| BP-10 | {N1, N3} | 新增 `n1SheetRouting.ts` / `n3SheetRouting.ts`，采用方 3 → 5 | **空集** |
| BP-8 | {N1, N2, N5} | 仅处理 N1 侧（N2/N5 归 lane3） | 余 {N2, N5} |
| BP-1 / BP-2 / BP-3 | 全 5 条 | 平台级，标 `[ ]*` 不闭合 | 不变 |
| BP-6 / BP-7 / BP-9 / BP-11 | 全 5 条或含本 spec | 依 foundation 裁定执行 | 见 foundation |

BP 计数校验：N1 = {1,2,3,6,7,8,9,10,11} 共 **9** ✓ · N3 = {1,2,3,4,6,7,9,10,11} 共 **9** ✓。

## 两条 entry 的载体形态（改造前后）

### N1 — `per_entry_composable_three_modes`（257 行）

```
useN1DualMode({ wpId, supportsMatrix })      # 三值：html | onlyoffice | matrix
  ├─ 被消费成员 9 个：mode / modeOptions / switchMode / fetchingConfig
  │                  / isOOHealthy / ooConfigReady / isOnlyOffice / isMatrix / onOoLoadFailed
  ├─ 生产边 5 条：宿主 + 4 个子 Tab
  ├─ localStorage 键 n1-dual-mode（按 wp 分区）
  └─ 🔴 直调两端点：onlyoffice/health + onlyoffice-config（全 N 域唯一同时直调两者）

门控（宿主）：v-if="isSwitchableSheet && dualMode.isOnlyOffice.value"
  🔴 用 isSwitchableSheet（其余 4 条 entry 用 isHtmlSheet）
  🔴 用 isOnlyOffice 计算属性（其余用 renderMode/currentMode 比较）
```

改造约束：保留 matrix 分支与 9 个成员对外契约；`isSwitchableSheet` 语义不得替换为 `isHtmlSheet`；若统一能力层不支持三值，在能力层扩展而非在 N1 砍功能。

### N3 — `host_inline_real`

```
宿主 .vue 内联：
  renderMode = ref<'html' | 'onlyoffice'>('html')     # 🔴 带泛型，M 轮正则漏此形态
  ooHealthy  = ref(...)
  checkOoHealth() → http.get('/api/workpapers/onlyoffice/health')   # BP-4 触点
  onModeChange(val):
      if (val === 'onlyoffice' && !ooHealthy.value) return          # 🔴 静默失败，无提示
      renderMode.value = val

门控（宿主）：v-if="isHtmlSheet && renderMode === 'onlyoffice' && ooHealthy"   # 🔴 三条件
```

改造约束：health 收敛后 `onlyoffice/health` 生产命中数仍须为 **5**（不增不减）；三条件门控不得简化为两条件；静默 return 须给明确用户反馈（原因 + 已回落 HTML），不可仅加日志。

## 模板层缺陷台账（本 spec 份额，只登记不修改）

| # | 位置 | 形态 | 性质 | 反向分母 |
|---|---|---|---|---|
| T-4 | `N3/递延所得税负债明细表N3-2` **H11 ~ H21** | `=F#+O#`（行偏移 −8，列 O(15) > max_column 14） | 🔴 结构残留，**整列失效**（H ≡ F） | **无**（11 行全同形） |
| T-5a | `N3-2 E23` | `=SUM(E3:O22)` | ✅ 合法（SUM 忽略空列） | — |
| T-8 | `递延所得税资产审计程序表的N1A` · `可用以后年度税前利润弥补的亏损检查表的N1-5` · `递延所得税负债审计程序表的N3A` | 「表的{码}」多字 | 脏字面量（slice 未记） | **3 处全在本 spec** |
| T-9 | `N3A` | 同码存在于 N3 册与 N5 册 | 🔴 跨册碰撞，**横跨 lane3** | — |
| T-11a | `N1/附注披露信息（国企）` | 256 列 / 有值列 7 / 幽灵 **249** | 遍历性能风险 | — |
| T-13a | N1 15 个 + N3 15 个 broken `definedName` | `#REF!` · `[1]Breakdown!#REF!` · 🔴 `'[2]2004'!#REF!` | 外部工作簿断链 | 48 : 30 |
| T-14 | `本循环科目` | 中文 definedName 且 broken | 断链 | — |

🔴 **T-4 与族 A1 不可合并计数**（依 NC-32）：A1 三处（foundation 1 + lane3 2）有 9:1 / 37:1 / 28:1 强反向分母，属个别行录入事故；T-4 无反向分母，属整列结构残留。合并计数会把「11 行同一个残留」当成「11 个独立缺陷」。

🔴 **T-9 跨 spec**：本 spec 与 `n2-n5-json-table-identity-and-cross-entry-readonly` 须互相引用；判据按 `(册, sheet 名)` 二元组定位，不得仅按 sheet 码。

## 契约字段映射（本 spec 份额）

| entry | `conclusion` 非空 | `remark` 非空 | 业务载荷实际所在 |
|---|---|---|---|
| N1 | **14** | 1（🔴 该 1 行是 AI 会话 `N1-review-session-*` 261 B） | **100% 在 `conclusion`** |
| N3 | **2** | 0 | **100% 在 `conclusion`** |
| 本 spec 合计 | **16** | 1 | — |

N1 的 `conclusion` 载荷清单：`N1-disclosure-listed-unoffset` 1201 B · `N1-disclosure-soe-unoffset` 1198 B · `N1-disclosure-soe-netoffset` 1196 B · `N1-disclosure-soe-synced-tables` 298 B · `N1-5-rows` 363 B。

🔴 **后缀规则的例外**：NC-34 的冲突优先级规定 `-rows` 后缀取 `remark`，但 `N1-5-rows` 实际数据在 `conclusion`（363 B）⇒ 本 spec 采用「**实际非空列优先于后缀规则**」，并把该例外写入守卫。理由：后缀规则是启发式，真库现值是事实；若按规则去 `remark` 取值会读到空值并静默丢 363 B 数据。

## Property 清单（NA-P1 ~ NA-P22）

| # | 断言 | 现算值 | 关联 NC |
|---|---|---|---|
| NA-P1 | 归属份额 17 行逐行与 foundation 算术表对齐 | 见份额表 | NC-1 |
| NA-P2 | entry 2 条全名吻合 · 科目借贷相反（资产/借 vs 负债/贷） | 2 | NC-22 |
| NA-P3 | 共享路由采用方 3 → 5 · BP-10 收口为空集 | 3 → 5 | NC-19 |
| NA-P4 | N1 `isSwitchableSheet` 语义保留（不替换为 `isHtmlSheet`） | 1 | NC-13 |
| NA-P5 | N3 三条件门控保留 | 3 条件 | NC-13 |
| NA-P6 | N3 载体识别覆盖带泛型 `ref<...>(` | 1 | NC-13 |
| NA-P7 | N3 `onModeChange` 静默 return 已修为显式反馈 | 1 | NC-13 |
| NA-P8 | health 收敛后 `onlyoffice/health` 生产命中仍为 5 | 5 | NC-3 |
| NA-P9 | N1 `onlyoffice-config` 直调已收敛（全域现算 1 处） | 1 | NC-37 |
| NA-P10 | N1 三值含 matrix · 9 个成员契约不减 · 5 条生产边 | 3 / 9 / 5 | NC-2 |
| NA-P11 | N1 localStorage 键 `n1-dual-mode` 且按 wp 分区 | 1 | NC-16 |
| NA-P12 | `parent_duplicate` 4 条全挂 N1 且逐条全名吻合 | 4 | NC-31 |
| NA-P13 | N1 双 owner 声明（`'N1-'` + `'N1-1-adj'`）· N3 单 owner | 2 / 1 | NC-30 |
| NA-P14 | TK-2 用双条件判据 · `N1_ADJUDICATION_CATEGORIES` 长度 7 | 7 | NC-30 |
| NA-P15 | `N1-1-rows` · `N1-1-adjudication-rows` · `N3-1-rows` 各 0 命中 | 0 | NC-30 |
| NA-P16 | A 族 3 处全在 `useN1Adjudication.ts` · 改造后降为 0 | 3 → 0 | NC-6 · NC-8 |
| NA-P17 | 契约双列映射 · `conclusion` 非空 16 · `N1-5-rows` 例外已登记 | 16 | NC-34 |
| NA-P18 | 真库污染 2 条落 `wp_code='G8'` | 2 | NC-19 |
| NA-P19 | 族 A2 = 11 行全同形无反向分母 · 与 A1 不合并计数 | 11 | NC-32 |
| NA-P20 | 「表的{码}」3 处 · `definedName` 48 / broken 30 含中文名 | 3 / 48 / 30 | NC-9 · NC-10 |
| NA-P21 | 超宽表 256 列 / 幽灵 249 · 遍历取 `last_value_col` | 249 | NC-35 |
| NA-P22 | 🔴 N3 无附注披露（空分母）· sheets 最少 6 · 公式格最少 162 | 0 / 6 / 162 | NC-20 · NC-22 |

**编号完整性**：NA-P1 ~ NA-P22 连续 **22** 条，无缺号无重号，每条关联至少一个 NC 编号。

## 测试策略

**测试文件**：`backend/tests/workpaper_sync/test_n1_n3_host_inline_router.py`（新建）。

| 类名 | 覆盖 |
|---|---|
| `TestLane2Attribution` | NA-P1 · NA-P2 |
| `TestSharedRouterAdoption` | NA-P3 ~ NA-P5 |
| `TestN3HostInlineHealth` | NA-P6 ~ NA-P8 |
| `TestN1ThreeModeCarrier` | NA-P9 ~ NA-P11 |
| `TestParentDuplicateData` | NA-P12 |
| `TestTransportKeyN1N3` | NA-P13 ~ NA-P15 |
| `TestRowIdentityMigration` | NA-P16 |
| `TestContractFieldsLane2` | NA-P17 |
| `TestCrossEntryPollutionLane2` | NA-P18 |
| `TestTemplateDefectsLane2` | NA-P19 ~ NA-P21 |
| `TestN3StructuralExceptions` | NA-P22 |

**原则**（沿用 foundation 测试原则 1 ~ 4）：期望值现读得出禁写死 · 结构性零须配变异证明 · 模板 sha256 断言置前失败即中止 · 真库用 asyncpg 且无库时 skip 标原因。

🔴 **本 spec 额外原则**：`N3A` 相关断言须按 `(册, sheet 名)` 二元组定位，并在测试注释中指向 lane3 的对应断言，防止两侧漂移。
