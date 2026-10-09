# Task 7 证据：BP-7 处置 + G1/G3 行身份修复

spec `g-cycle-single-region-detail-lanes` · Task 7 · _Requirements: 1.3_　实施 2026-09-27

---

## 1. 处置范围：只修两条，登记四条

| entry | slice 标 BP-7 | 按值实测 | 本 Task 动作 |
|---|---|---|---|
| **G1** | ✅ | 🔴 下标派生 `useG1Detail.ts:442` + 裸时间戳 `:704` | **修** |
| **G3** | ✅ | 🔴 下标派生 `useG3Detail.ts:288` + 裸时间戳 `:358` | **修** |
| G10 | ✅ | `:423` 的 `i+1` 只喂 `seq`；`genId` 带 `Math.random()` | 登记误标，**不动代码** |
| G11 | ✅ | `:162` 同上；`generateId` 带 `Math.random()` | 登记误标，**不动代码** |
| G12 | ✅ | `:114` 同上；`:50` `rowId: String(raw.rowId ?? genId())` | 登记误标，**不动代码** |
| G13 | ✅ | `:143` `r.rowId \|\| generateRowId()`；`i+1` 只喂 `seq` | 登记误标，**不动代码** |
| G8 / G9 / G14 | ❌ | 无 | 与 slice 一致 |

🔴 **未伪造缺陷、未静默抹掉 slice 的四条 BP-7 标记**（裁决 G1R-H7 的要求）：
逐字反证见 `evidence/task2-geometry-and-field-probes.md` §3.2；slice 字节**未改**（它是别人的裁决取证）。
判据 `g1g3RowIdentityBp7.spec.ts` 的最后一组断言四条 entry 的源码**仍带** `Math.random()` 且
**未引入** `g1g3RowIdentity` —— 钉住「没被顺手改动」。

## 2. 三种旧形态与各自处置

| 旧形态 | 出处 | 处置 | 理由 |
|---|---|---|---|
| `String(i + 1)` → `"1"`/`"2"`… | `useG1Detail:442` `useG3Detail:288` | **重铸** | 纯下标：删中间一行后其后所有缺 id 的行身份整体前移；且**不同底稿的第 1 行 id 都是 `"1"`** |
| `emptyRow('1', 1)` 空表兜底 | 两文件各 3 处 | **重铸** | 同上（固定字面量 `'1'`） |
| `` `row-${Date.now()}` `` | `useG1Detail:704` `useG3Detail:358` | 🔴 **保留，仅同载荷内撞 id 时重铸** | 见 §2.1 |

### 2.1 🔴 为什么 `row-<ts>` 不无条件重铸（与 F5 同族修复的差异）

F5 的同族修复（`f5RowIdentity.ts`，并发会话产物）把三处旧形态**一律重铸** —— 那是对的，
因为它的三处旧形态**都含数组下标**（`m-<ts>-<i>` / `oc-migrated-<i>` / `cmp-migrated-<i>`）。

G1/G3 的 timestamp 形态**不含下标**，唯一风险是**同毫秒连加两行撞 id**。若照抄 F5 的「一律重铸」：
载入时每个 `row-<ts>` 都被换成新 UUID ⇒ **每次载入身份都变** ⇒ 比原缺陷更糟
（原缺陷只在存量缺 id 的行上，新缺陷会打到所有行）。

⇒ 正确修法拆成两半：
- **生成端**加随机后缀（`newRowId()`）⇒ 新增行不再撞
- **载入端**只在「同一份载荷里 id 重复」时对后来者重铸 ⇒ 修掉存量已撞的，不动没撞的

判据 `G1R-P2 ②` 的 `test_两次载入同一份载荷得到同一批身份` 正是钉这条（身份稳定性）。

## 3. 产物

| 文件 | 性质 | 说明 |
|---|---|---|
| `composables/g1g3RowIdentity.ts` | **新建** | 单点铸造：`resolveStableRowIds`（批量，去重需要看到同载荷其它 id）· `newRowId` · `mintStableRowId`（优先 `crypto.randomUUID()`）· `isOrdinalRowId` / `isBareTimestampRowId` · `RowIdentityMintStats{minted, deduped}` |
| `composables/useG1Detail.ts` | 改 | `loadRows(map, stats?)` 走单点铸造 + `loadRowsAndPersistIfMinted()` + `addRow` 用 `newRowId` |
| `composables/useG3Detail.ts` | 改 | 同上（两文件结构同构） |
| `__tests__/g1g3RowIdentityBp7.spec.ts` | 新建 | **17 tests 全绿**，六组 |
| `tsconfig._g-single-region.json` | 新建 | 局部类型检查（照并发会话的 `tsconfig._g2-canary.json`），`vue-tsc` **0 错** |

### 3.1 🔴 `resolveStableRowIds` 必须是**批量** API

去重需要看到同一载荷里的其它 id。逐行 API（如 F5 的 `resolveStableRowId`）**无法发现**
`` `row-${Date.now()}` `` 同毫秒撞出的两个相同 id —— 这正是 G1/G3 要修的形态之一。

### 3.2 立即回写的三个载入点 + 一个 TDZ 坑

三处载入点（初始 `ref` / `loadAll()` / `watch`）都要回写，否则 store 里仍是旧 id、下次载入又铸一批。

🔴 **TDZ 坑**：不能在 `ref(loadRows(...))` 的初始化表达式里直接调 `persistAll()` ——
`persistAll` 读 `rows.value`，而 `rows` 此刻尚未完成初始化。
⇒ 改为「先记账、稍后回写」：
```ts
const initialMint = createMintStats()
const rows = ref<...>(loadRows(opts.allResponses.value, initialMint))
// …（persistAll 定义）
if (initialMint.minted > 0) persistAll()   // 此刻 rows 已初始化
```
另两处走 `loadRowsAndPersistIfMinted()`（局部 stats，铸造 > 0 才写）。

## 4. 验证

| 项 | 结果 |
|---|---|
| `vue-tsc -p tsconfig._g-single-region.json` | **0 错** |
| 新判据 `g1g3RowIdentityBp7.spec.ts` | **17 passed** |
| 零回归（既有 G1/G3 相关 8 个 spec + 新判据共 9 个 test file） | **9 passed** |
| Task 3 的 `G1R-P1` map-index 判据 | 🔴 见 §5 |

### 4.1 判据自身的一处修正

首版「源码形态防护」直接扫全文 ⇒ 被**修复说明注释里逐字引用的旧写法**打红
（注释写「原写法 `p.id ?? String(i + 1)` …」是有意的文档价值）。
⇒ 判据语义改为「旧写法不得出现在**代码行**里」，加 `stripCommentLines()`（按行首 `//` / `*` / `/*` 过滤），
并**自检**注释里确实还留着逐字记录（`expect(raw).toMatch(...)` + `raw.length > code.length`）。
局限已写在判据 docstring：不解析行尾注释与字符串字面量。

## 5. 🔴 交棒：Task 3 的一条判据需要同步更新

`test_g_single_region_p1_p3_p5_p6.py::TestG1rP1RowIdentityThreeFamilies::test_map_with_index_alone_is_not_a_violation_signal`
末尾断言 `idx_id == {"G1", "G3"}`（Task 2 实测的下标派生集合）。本 Task 修复后该集合应为 **空集**。

⇒ 已在该判据的断言消息里预留指引：「若是 Task 7 已修，把本断言改为 `set()` 并在 evidence 里记修复 commit」。
**本 Task 执行该更新**（见下一节的 tasks.md 记录），使后端判据与前端修复保持同源。
