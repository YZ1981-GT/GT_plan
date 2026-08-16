# Requirements — 守卫判据归因化改造（全局等值型 → 归因型）

## Introduction

平台有 20+ 处**全量扫描型守卫**用「某集合的总数/清单必须等于硬编码基线」做判据。
在多 spec 并发开发下，这类断言**必然假红**：改动方动了真源、同步了自己视野内的
副本，而别的 spec 拥有的守卫副本看不见也跑不到。

### 触发本 spec 的实测事件（2026-08-15，i 循环收口时发现）

`disclosureSharedTableRowScope.spec.ts` **7 条断言全 RED**：

| 断言 | 硬编码基线 | 实测真源 |
|---|---|---|
| `manifest.counts` | `{listed: 23, soe: 6}` | `{listed: 24, soe: 8}` |
| `manifest.tables.length` | 29 | 32 |
| 窄可写区段数 | 15 | 18 |
| `SCANNABLE.length` | 15 | 26 |
| `项  目*` 泄漏名数 | 4 | 2 |
| 泄漏名含 `<br/>` | true | 两个都不含 |
| 脏名登记表每条仍在清单 | `''` / `'项  目'` 必须在 | 两者都已不在 |

**因果链（已实证）**：2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 给共享表补了段首
`report_row_code` → 真源 `backend/data/note_shared_table_segments.json` 从 23/6/29 变 24/8/32
→ 改动方同步了**生成器** `EXPECTED_COUNTS` 与**后端守卫** `test_note_shared_table_segments.py`
（两处都写了 docstring 说明来源）→ 但**前端守卫属于另两个 spec**
（`disclosure-note-row-level-merge` / `restricted-assets-note-row-scope-rollout`），
改动方的 CI 视野里根本没有它。

🔴 **立项判断的一处修正（2026-08-15 实证后）**：起初写作「3 个 blocking job 在干净
checkout 下必挂」—— **这是错的**。实际状态是 K 循环整套改动（真源 + 生成器 + 后端守卫）
**三个文件在工作树里全是 `M`、从未提交**，git HEAD 里三处副本**全是 23/6**：

| 位置 | git HEAD | 工作树磁盘 |
|---|---|---|
| 真源 `note_shared_table_segments.json` | 23/6/29 | **24/8/32** |
| 生成器 `EXPECTED_COUNTS` | 23/6 | **24/8** |
| 后端守卫 `test_note_shared_table_segments.py` | 23/6 | **24/8** |
| **前端守卫**（本 spec 目标） | 23/6/29 | 23/6/29（**未同步**） |

⇒ **干净 checkout（CI）当前是全绿的**（四处自洽于 23/6/29）；
**红只出现在本地工作树**（三处已改、前端未改）。

这不削弱立项理由，反而让它更准确 —— 问题从「已经挂了」变成**「地雷已埋好，K 循环一 commit 就炸」**：

**后果四条**：
1. **K 循环 commit 的那一刻，3 个 blocking job 立刻挂**：`ci.yml` 的 `frontend-build`、
   `governance-checks.yml` 的 `disclosure-row-level-merge-frontend` 与
   `note-restricted-assets-frontend` —— 而挂的原因在**别人的 spec 的产物**里，
   K 循环推进方既无权限判断也无上下文修
2. **K 循环推进方本地跑测试现在就能看到红**，但极易误判为「别的 spec 的陈账」而忽略
   （本次实测归因耗时约 15 分钟才用 `git status` + `git show HEAD:` 三向比对定位清楚）
3. **等值断言打死同 it 内的归因断言**：`L163` 的 `.toBe(15)` 先失败 ⇒ 紧随其后 6 条
   **仍然成立且有价值**的归因断言（`八、93` 必在 / `外币货币性项目` 必不在 /
   `五、32`·`五、71`·`八、91`·`八、81` 必在）全部拿不到反馈
4. 🔴🔴 **等值断言还掩盖了一个数据丢失级真红达 3 天**：改成地板/不变式判据后，
   同文件里形态 A 的 `Property 15` 才第一次显现真红 ——
   `k1NoteSectionMap.ts` 推《其他应收款》/ `k3NoteSectionMap.ts` 推《其他应付款》
   **均未声明 `_row_scope`** ⇒ 表级整表覆盖会清掉他段（应收股利 `BS-016` /
   应付股利 `BS-055`·`BS-076`）。这两张表正是 K 循环本次补段首码**才变成共享表**的
   ⇒ 缺陷与漂移同源、同样会在 commit 时才在 CI 显现

### 判据形态分级（本 spec 的核心口径）

| 级别 | 形态 | 并发安全 | 举例 |
|---|---|---|---|
| A（目标态） | 违规清单为空 `expect(bad).toEqual([])` | ✅ 新增自动纳管、他人修好不红 | `disclosureAutoSyncCoverage` 的绝大多数断言 |
| B（可接受） | 地板 `toBeGreaterThanOrEqual` / 天花板 `toBeLessThanOrEqual` | ✅ 只防空转与扩张 | `BUILDER_FLOOR=12` / `TABLE_FLOOR=60`（实测 22/92，留余量） |
| C（可接受） | 包含式重点项 `expect(inventory).toContain(x)` | ✅ 结构错才红 | 后端 `test_key_tables_are_in_inventory` |
| D（禁止） | 全局等值 `expect(total).toBe(硬编码)` | ❌ 任何 spec 动真源必红 | 本次 7 条 RED |
| E（禁止） | 跨文件抠源码数字再等值 | ❌ 双向锁死，改一处必红另一处 | `l2l4DisclosureWiring` 正则抠 `MISSING_SYNC_PATH.length).toBe(6)` |

---

## Requirements

### Requirement 1: 立即止血 —— 前端守卫基线与真源对齐

**User Story:** 作为任何分支上的开发者，我需要 CI 的红色反映我自己的改动，而不是别人两周前
改真源留下的陈账。

#### Acceptance Criteria

1.1 WHEN 运行 `disclosureSharedTableRowScope.spec.ts` THEN 必须**在两种真源状态下都通过**：
    ① git HEAD 的 23/6/29（干净 checkout）② 工作树的 24/8/32（K 循环在途改动）
    —— 这正是「不锁规模」的价值：判据对真源规模不敏感，两态同绿

1.2 WHEN 修正基线 THEN 每处修改必须在注释里写明「变更日期 + 变更来源脚本/spec + 数值变化」，
    对齐后端 `test_note_shared_table_segments.py` 已有的 docstring 范式

1.3 WHEN 脏名登记表 `GENERIC_TABLE_NAMES` 的条目已从真源清单消失 THEN 必须按「已修好必删」移出，
    不得改断言方向来保留死条目

1.4 WHEN 修正 `SCANNABLE.length` 相关注释 THEN 注释里的推导链（「N 张表 → M 去重名 → 剔 K 脏名」）
    必须与实际计算一致，不得留下过期算式

1.5 IF 某条断言在修正基线后失去意义（如「泄漏名含 `<br/>` 必须为 true」，而真源已无此类名）
    THEN 必须删除该断言并说明原因，不得改成 `false` 反向锁死一个正在消失的脏数据

### Requirement 2: 单一真源化 —— 消除跨端基线副本

**User Story:** 作为改真源的人，我不希望需要记住「还有哪几个文件抄了这个数字」。

#### Acceptance Criteria

2.1 WHEN 需要断言共享表清单规模 THEN 前端守卫必须**从真源 JSON 读取**并做结构自洽校验，
    不得在测试文件里硬编码 `counts` / `tables.length` 的期望值

2.2 WHEN 需要防「真源被清空导致扫描空转」THEN 使用地板断言（形态 B），且地板值必须显著低于
    实测值并在注释里写明当前实测值与余量

2.3 WHEN 生成器 `gen_note_shared_table_segments.py` 与真源 JSON 漂移 THEN 由**后端** job
    的 `--check` 负责报错（该机制已存在且工作正常），前端守卫不重复承担此职责

2.4 WHEN 前端守卫需要知道「重点表是否仍在清单」THEN 使用包含式断言（形态 C），
    参照后端 `test_key_tables_are_in_inventory` 的 8 条 `in` + 1 条 `not in`

### Requirement 3: 等值断言不得污染归因断言

**User Story:** 作为读 CI 失败的人，我需要一条断言失败时其余判据仍然给我反馈。

#### Acceptance Criteria

3.1 WHEN 一个 `it` 内同时含「规模型断言」与「归因型断言」THEN 必须拆成两个 `it`，
    规模型在前、归因型独立

3.2 WHEN 归因型断言涉及多个具名对象 THEN 必须收集违规清单后一次性 `toEqual([])`，
    不得在 `for` 循环里逐个 `expect`（首个失败即中止，后续对象无反馈）

3.3 WHEN 断言失败 THEN 报错消息必须包含**可归因信息**：涉及的具名对象（表名/文件名/章节号）
    与「该找谁」的线索（真源文件路径或生成器命令）

### Requirement 4: 跨文件外部锚定治理

**User Story:** 作为维护登记表的人，我不希望减少一个条目要同时改两个 spec 的文件。

#### Acceptance Criteria

4.1 WHEN `l2l4DisclosureWiring.spec.ts` 用正则从 `disclosureAutoSyncCoverage.spec.ts` 源码里
    抠出 `MISSING_SYNC_PATH.length).toBe(N)` 并断言 `N === 6` THEN 该断言必须改为
    「豁免理由块存在」这类形态 A 判据，不得锁死数字

4.2 WHEN `disclosureAutoSyncCoverage.spec.ts` 的 `expect(MISSING_SYNC_PATH.length).toBe(6)`
    仅作「收敛提醒锚点」而不校验任何性质 THEN 必须改为天花板（形态 B）并写明
    「只许缩」的语义，使补齐链路的一方不会打红

4.3 WHEN `MISSING_SYNC_PATH` 内混装「永久豁免」与「真实缺口」两种语义
    （实测 6 条 = 4 条永久豁免 + 2 条真实缺口）THEN 必须拆成两个常量，
    使「真实缺口数」可以独立收敛到 0 并被断言

4.4 WHEN 拆分登记表 THEN 每条永久豁免必须保留既有的源模板依据说明（H5 listed 三条实证、
    L2 两版的 K3 撞表论证、N4 soe 的「附注披露信息：无」），不得在搬迁中丢失

### Requirement 5: 天花板贴死的登记表留出余量

**User Story:** 作为改 H1/I1 披露列的人，我不希望顺手补一张表的 `flat` 就要改两个常量。

#### Acceptance Criteria

5.1 WHEN `ALLOWLIST_BUILDER_CEILING` / `ALLOWLIST_TABLE_CEILING`（现值 2 / 11）与
    `INFERENCE_FALLBACK_ALLOWLIST` 实际条目数**完全相等**（无余量）THEN 必须确认这是
    有意设计（「只许缩」）并在注释写明：**缩小时必须同步下调天花板**

5.2 IF 天花板语义是「只许缩」THEN 断言必须能区分「扩张」（违规）与「缩小但没改天花板」（合规），
    后者不得报红

5.3 WHEN `INFERENCE_FALLBACK_ALLOWLIST` 的某个 builder 的表集合被修好一部分
    THEN 「实扫集合 === 声明集合」的等值断言必须给出**差异明细**（多了哪些/少了哪些），
    并在消息里区分「新增 None 态表（违规）」与「已修好未删条目（应删）」

### Requirement 6: 全库同类判据普查与分级

**User Story:** 作为平台维护者，我需要知道还有多少处同类地雷，以及哪些必须改、哪些可以留。

#### Acceptance Criteria

6.1 WHEN 普查 THEN 必须覆盖 `audit-platform/frontend/src/**/__tests__/**/*.spec.ts` 与
    `backend/tests/**/*.py`，输出机器可读清单（文件 / 行号 / 断言代码 / 现值 / 分级 D 或 E）

6.2 WHEN 分级 THEN 判定「必须改」的条件是**该断言的真源被本 spec 之外的其它 active spec 拥有或触及**；
    作用域限于单一循环内的硬计数（如 `g7NoteSubtableContract` 的 27/2/11/3）判为「可留」

6.3 WHEN 普查完成 THEN 已知的 20+ 处必须逐条给出判定与理由，不得只报总数

6.4 WHEN 判定「可留」THEN 必须在该断言处补一行注释说明「作用域限于 X 循环，故硬计数安全」，
    使后来人不必重新推导

### Requirement 7: 守卫本身的反向自检

**User Story:** 作为改守卫的人，我需要确信改完之后它还能抓住真实缺陷。

#### Acceptance Criteria

7.1 WHEN 把等值断言改成地板/天花板/归因清单 THEN 必须对每个被改的判据做变异检验：
    人为制造一个真实违规，确认对应测试变红

7.2 WHEN 变异检验 THEN 必须记录四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST），
    只有 RED 且命中预期测试才算通过

7.3 WHEN 归因清单型断言的扫描面可能变空 THEN 必须有配套的「扫描面非空」地板断言
    （参照 `disclosureSharedTableRowScope` 已有的 `wired.length >= 1`）

7.4 IF 某条反向自检绑定了具体的真实文件（如 `e1FxNoteSectionMap.ts`）THEN 必须评估
    「该文件被改/删后自检是否失效」，并在注释登记风险（G9 已翻车过一次）

### Requirement 8: CI 与验收

#### Acceptance Criteria

8.1 WHEN 改动完成 THEN 3 个受影响的 blocking job 必须在**两种真源状态下都全绿**
    （HEAD 的 23/6/29 与工作树的 24/8/32）：`ci.yml` · `frontend-build`；
    `governance-checks.yml` · `disclosure-row-level-merge-frontend`；
    `governance-checks.yml` · `note-restricted-assets-frontend`
    —— 单测一种状态不足以证明「判据对真源规模不敏感」

8.2 WHEN 验收 THEN 必须串行跑（`--no-file-parallelism`）避免并发 flaky 污染判断，
    并记录 files/tests 通过数

8.3 WHEN 本 spec 的产物完成 THEN 必须 `git status --porcelain` 核查无 `??`，
    避免「spec 全绿但产物未入库、干净 checkout 下 CI 必挂」

8.4 WHEN 改动 `.github/workflows/governance-checks.yml` THEN 验收判据必须是**归因型**
    （变动落在本 spec 的字节区间内），不得用「其他 job 一个都没变」的全局等值
    —— 该文件是多 spec 并发编辑的高发文件

8.5 WHEN 本 spec 完成 THEN 必须在 `.kiro/steering/conventions.md` 补一条守卫判据形态口径
    （A/B/C 可用、D/E 禁用），使后续 spec 不再新增同类地雷
