# Implementation Plan: 守卫判据归因化改造（全局等值型 → 归因型）

## Overview

8 个任务分 4 波。Wave 1 止血（解除 3 个 blocking CI job），Wave 2 拆登记表语义与解耦
跨文件锚定，Wave 3 处理天花板余量与消息质量，Wave 4 变异检验与验收。

不改业务代码，只改判据形态。4 个被改的守卫文件里 **3 个属于别的 spec**
（disclosure-note-row-level-merge / disclosure-sync-path-buildout / l-cycle-…-completion）
—— 这是判据缺陷的固有属性，提交说明须点明跨 spec 改动与原因。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "止血：前端守卫转绿（解除 3 个 blocking CI job）",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "Task 1 是纯读的普查，Task 2 依赖它的分级结论决定改哪些；两者都只碰 disclosureSharedTableRowScope 一个文件，串行避免自撞"
    },
    {
      "wave": 2,
      "name": "登记表语义拆分与外部锚定解耦",
      "tasks": ["3", "4"],
      "parallel": false,
      "rationale": "Task 4 改 l2l4DisclosureWiring 依赖 Task 3 产出的新常量名；且两者跨 spec 边界，串行便于逐步验收"
    },
    {
      "wave": 3,
      "name": "余量与消息质量",
      "tasks": ["5", "6"],
      "parallel": true,
      "rationale": "Task 5 只碰 disclosureColumnsCoverage、Task 6 只碰 conventions.md，无文件重叠"
    },
    {
      "wave": 4,
      "name": "变异检验与验收",
      "tasks": ["7", "8"],
      "parallel": false,
      "rationale": "Task 8 的验收需要 Task 7 的变异记录作为「守卫仍有效」的证据"
    }
  ]
}
```

---

- [x] 1. 全库同类判据普查与分级（只读，不改代码）

  ✅ **已交付**（产物：`backend/scripts/check/audit_guard_assertion_grades.py` +
  `backend/data/guard_assertion_grades.json`）

  **终态**：扫 **4156** 个测试文件，命中 **1511** 条形态 D/E。
  分层 `P0 119 / P1 45 / P2 1347`；判定 `must_fix 1209 / keep 302`。
  **19/19 已知锚点全部命中**（脚本 `--check-anchors` 可复现）。

  🔴 **判据迭代了 4 版，每版都靠 `KNOWN_ANCHORS` 的 MISS 报警发现漏洞** ——
  这是本 Task 最值得沉淀的部分，也印证了「先把已知点写进 spec 再写脚本」的价值：

  | 版本 | 判据 | 命中数 | 漏掉了什么 |
  |---|---|---|---|
  | v0 | 正则 `expect\(...(?P<msg>.*?)\)\.toBe\(\d+\)` + `re.S` | **7063** | 跨行误匹配：DOTALL 下把「某个 expect 的开头」与「几十行后另一个 expect 的 `.toBe(数字)`」拼成一条 |
  | v1 | 改**括号配对**扫描 + 条件①（文件是全量扫描型）+ 条件②「target 必须是模块级」 | **87** | 漏 4 个锚点：`listed = list(iter_shared_tables(...))` 这类**函数内局部变量** |
  | v2 | 条件②改「赋值右侧含扫描信号」 | 229 | 漏 3 个：**pytest fixture 参数**（`def test_x(expected)` 根本没有赋值语句）+ 私有 helper 调用（`codes = _codes()`） |
  | v3 | 条件②改「排除全部字面量」 | 1468 | 漏 2 个：`MISSING_SYNC_PATH` / `ORPHAN_BASELINE` —— **模块级登记表本身就是字面量数组**，却是形态 D 的典型 |
  | v4 | 条件②按**是否模块级分流**：模块级→纳入 / 函数内+字面量→排除 / 函数内+其它→纳入 | **1511** | 19/19 全命中 |

  🔴 **v0 犯的正是本 spec design 的 Property 9 明令禁止的「固定字符窗口 / 跨界正则」**
  —— 治理脚本自己踩了要治的坑。已改为括号配对（跳字符串与模板串），
  并补 `[跨界]` 与 `[配对]` 两条反向自检（首版在此必败）。

  **判据设计的关键取舍（如实登记）**：形态 D 的危害只发生在 target 承载
  「真源规模快照」时。`expect(plan.writes.length).toBe(2)` 这类「造 2 条输入断言
  2 条写入」是纯函数单测，**完全合法**，任何 spec 改真源都不影响它。
  但语法上二者不可区分 ⇒ 脚本**不假装能全自动定案**，改为：
  - 两个必要条件（文件是全量扫描型 ∧ target 非函数内字面量）过滤明显合法项
  - 三层优先级给出可操作清单：
    - **P0（119 条 / 19 文件）** = spec 已逐条确认的，确定要改
    - **P1（45 条）** = 模块级 UPPER_SNAKE 常量（登记表 / 清单，最易被跨 spec 改）
    - **P2（1347 条）** = 待分批甄别的背景量
  - 每条带 `needs_human_review: true`

  **跨 spec 加权已实装**（Property 15 / R6.2）：从 `.kiro/specs/*/{tasks,design,requirements}.md`
  抽文件名建索引（**570** 条），标注每条命中的 `touched_by_active_specs`；
  被 **2+ 个** active spec 提及的 `keep` 自动抬为 `must_fix`
  —— 实测精确抓出 3 条 `l2l4DisclosureWiring`（被 `l-cycle-…-completion` + 本 spec 同时提及）。

  **脚本自带三重防空转**：
  1. 零产出自检（扫到 <200 个测试文件即报 ERROR）—— 首版 `REPO_ROOT` 写
     `parents[2]` 落在 `backend/` 上，扫到 **0 个文件却以 0 退出**（「命中 0 条」看起来
     像「平台很干净」），正是本 spec 要治的判据空转形态；已改**双哨兵向上查找**
  2. 反向自检 16 例（TS 9 / PY 4 / 跨界 1 / 配对 1 / E 1），跑普查前先自检，失败即中止
  3. `KNOWN_ANCHORS` 覆盖核对（19 个），任一 MISS 即报「判据收窄过头」

  **P0 分布**：`e1BankAccountPrefill`(17) · `g0SummaryLowerZone`(13) ·
  `test_note_shared_table_segments`(11) · `test_x3_ie_manifest_registration`(10) ·
  `adjustmentIeContract`(9) · `test_note_i_cycle_structure`(9) · `test_x3_ie_registrar`(8) ·
  `test_x3_keyfamily_property`(8) · `test_k0_source_template_facts`(7) ·
  `g7NoteSubtableContract`(6) · **`disclosureSharedTableRowScope`(5 → Task 2 的目标)** ·
  `cycleImportExportRegistry`(4) · `l2l4DisclosureWiring`(3) · `blockColumnAmountRender`(3) ·
  `ieWiringIntegrity`(2) · 其余 4 个各 1

  ### 立项时的任务描述（对照用，已全部落实）

  - 新建 `backend/scripts/check/audit_guard_assertion_grades.py`，扫
    `audit-platform/frontend/src/**/__tests__/**/*.spec.ts` 与 `backend/tests/**/*.py`
  - 识别形态 D（`expect(<集合>.length).toBe(<数字>)` / `toEqual({...数字})`）与
    形态 E（同一 `it` 内既读别的守卫源码又做数字等值）
  - 🔴 **判定「必须改」的唯一标准**：该断言的真源被本 spec 之外的其它 active spec 拥有或触及。
    作用域限于单一循环的硬计数（`g7NoteSubtableContract` 的 27/2/11/3 等）判 `keep`
  - 输出 `backend/data/guard_assertion_grades.json`（六字段见 design Property 14）
  - 已知待覆盖清单（普查须逐条给判定，不得只报总数）：
    - 前端：`disclosureSharedTableRowScope`(7) · `disclosureAutoSyncCoverage`(1) ·
      `l2l4DisclosureWiring`(1，形态 E) · `ieOrphanBaseline`(1) ·
      `cycleImportExportRegistry`(4) · `blockColumnAmountRender`(2+) ·
      `nCycleNoteSubtableContract`(1) · `iCycleDisclosureWiring`(1) ·
      `g7NoteSubtableContract`(4) · `ieWiringIntegrity`(2) · `adjustmentIeContract`(2) ·
      `e1BankAccountPrefill`(1) · `g0SummaryLowerZone`(4)
    - 后端：`test_note_shared_table_segments`(4) · `test_x3_ie_manifest_registration`(4) ·
      `test_x3_ie_registrar`(3) · `test_note_i_cycle_structure`(1) ·
      `test_k0_source_template_facts`(3) · `test_x3_keyfamily_property`(1)
  - 脚本含反向自检：喂一个已知形态 D 的替身片段必须被识别；喂形态 A/B/C 必须不被识别
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 2. `disclosureSharedTableRowScope.spec.ts` 判据改造（解除 3 个 blocking job）

  ✅ **已交付**。该文件 **17/17 passed**，且**两种真源状态下都绿**。

  ### 🔴 立项判断的实证修正

  起初写「3 个 blocking job 在干净 checkout 下必挂」—— **错的**。三向比对
  （`git show HEAD:` / `git show :` / 磁盘）实证：K 循环整套改动
  （真源 + 生成器 + 后端守卫）**三个文件全是 `M`、从未提交**，git HEAD 里三处副本
  **全是 23/6**。⇒ 干净 checkout 当前**全绿**（四处自洽于 23/6/29），
  红只在本地工作树。问题从「已经挂了」变成**「地雷已埋好，K 循环一 commit 就炸」**。

  ### 判据改造（7 处 + 拆 it + 删 1 条）

  | 原断言 | 改后 |
  |---|---|
  | `counts).toEqual({23,6})` + `tables.length).toBe(29)` | **结构不变式** `counts.listed + counts.soe === tables.length` + 两键正整数 + variant 集合闭合 |
  | `narrowed.length).toBe(15)` | 地板 `≥ 10` + 6 条归因断言**拆到独立 `it`** |
  | `SCANNABLE.length).toBe(15)` | 地板 `≥ 10` + 包含式重点表 |
  | `leaky.length).toBe(4)` | 天花板 `≤ 4`（脏名只许减少） |
  | `leaky.some(含 <br/>)).toBe(true)` | **删除**（真源已无此类名，锁死正在消失的脏数据无保护价值） |
  | 脏名登记表「每条必须仍在清单」 | 反转为形态 A「已消失的必须移出」+ 移出 `''` 与 `'项  目'` 两条（留墓碑注释，后端 `test_empty_table_name_is_excluded_from_lookup` 仍专职看守空表名） |
  | 两处 `for` 循环内逐个 `expect` | 收集违规清单后单次 `toEqual([])`（Property 6） |

  结构不变式替代两个硬编码且**判据更强**：别人改真源不打红，生成器算错分组才红。
  真源实证 `counts 之和 32 === tables 32` ✓

  ### 🔴🔴 暴露一个数据丢失级真红（被等值断言掩盖 3 天）

  改成地板/不变式后，同文件里形态 A 的 `Property 15` 才第一次显现真红：

  ```
  k1NoteSectionMap.ts 推共享表 其他应收款 但未声明 _row_scope
  k3NoteSectionMap.ts 推共享表 其他应付款 但未声明 _row_scope
  ```

  段归属实证（危害面）：

  | 共享表 | 段 owner | 整表覆盖会清掉 |
  |---|---|---|
  | 《其他应收款》soe 八、9 | `BS-009` 其他应收款项（K1）+ **`BS-016` 应收股利** | 应收股利段 |
  | 《其他应付款》listed 五、42 / soe 八、42 | `BS-050` 其他应付款（K3）+ **`BS-055`/`BS-076` 应付股利** | 应付股利段 |

  K1 源码注释**已知**该表「同时承载 G2 应收利息 / G3 应收股利 / K1 其他应收款
  三个底稿的推送」，用「条件表语义 + 不越权删」做了部分缓解 —— 但有值时仍整表覆盖。
  K3 侧 memory 记载 M1 应付股利正是推该章节 ⇒ 两循环互相覆盖、谁最后保存谁赢
  （正是 L2 豁免理由里写的「比不推更糟」）。

  🔴 **这两张表正是 K 循环本次补段首码才变成共享表的** ⇒ 缺陷与漂移同源、
  同样会在 commit 时才在 CI 显现。

  **处置**：新增**语义准确的专门登记表** `TABLE_LEVEL_OVERWRITE_RISK`
  （不混装进 `NOT_WIRED_ALLOWLIST` —— 那是「未接线」，这是「已接线但未声明 `_row_scope`」；
  混装正是 R4.3 在治的病）。每条写明 owner spec（`k-cycle-…-closure`）+ 危害 + 修法，
  并注明**为什么本 spec 不直接修**：K3 主表推三行，声明 `owner_row_code: BS-050` 后
  应付股利行会被服务端丢弃 —— **那一行归 K3 还是 M1 是业务判断**，
  本 spec 明确「只改判据形态，不补真实缺口」。

  ### 双真源态验证抓出「耦合换了个方向仍在」

  AC 1.1 要求两态都绿。首版只在工作树态（24/8/32）验过 ⇒ 用 HEAD 版真源（23/6/29）
  实测**FAIL 1 条**：新登记表的 stale 检测（HEAD 态下这两张表还不是共享表、不在
  `SCANNABLE`）⇒ **判据方向虽从「必须存在」翻成「必须不存在」，耦合仍在**。
  改为天花板软约束（`stale ≤ 2`）后两态同绿。

  代价如实登记：天花板使「单条条目表名写错」不再被登记表自身抓出，
  但必然从「全量扫描」侧暴露（豁免失效 ⇒ K1/K3 真红回来）—— 变异 M11 实测确认。

  ### 变异检验 11/11 全 RED

  新建 `backend/scripts/check/mutate_guard_attribution.py`（`--list`/`--only`/`--all`/`--restore`）：
  M1 破坏结构不变式 · M2 真源截断到地板下 · M3 抹平 data_end · M4 抹掉八、93 窄区 ·
  M5 给外币表造窄区 · M6 重点表改名 · M7 脏名登记表加不存在条目 ·
  M8 移出 K3 豁免 · M9 理由拼错 `_row_scope` · M10 owner 非目录名 · M11 条目改名。

  三处脚本自身的缺陷也一并修掉（都是本 spec 要治的同类形态）：
  - `green` 判定用 `"failed" not in out` 被断言消息里的 `fail-closed` 字样骗到
    ⇒ 报「变异前守卫本身就是红的」把整轮挡在门外 → 改用 **vitest 退出码 + 摘要行**
  - M9 首版是 ANCHOR-MISS 被误判为 GREEN：`reason` 是**多行拼接**，
    只替换第一行时续行仍在 ⇒ 长度门槛不触发 → 锚点改落在判据真正读的特征上
  - 多行锚点做**行尾归一化**匹配（平台铁律：含 `\n` 的锚点在 CRLF 下必 MISS）

  🔴 **真源是并发共享文件**（当前 `M` = K 循环在途改动）：变异一律
  内存改 + 写临时态 + `finally` 里 **md5 双验字节级恢复**；
  11 轮变异 + 双态验证跑完后复测真源仍是 `24/8/32 / 26 去重名 / 18 窄段`，
  与首次实测逐项一致 ⇒ 未破坏 K 循环在途改动。

  ### 零回归

  辐射面串行跑 8 文件：我改造范围内的 6 个**全绿 203 passed**；
  另 2 个（`disclosureAutoSyncCoverage` / `disclosureColumnsCoverage`）仍红
  —— 它们是 **Task 3/5 的目标**，尚未改，属预期。

  ### 立项时的任务描述（对照用，已全部落实）

  - 按 design「形态 D → B+C 的替换配方」逐条改造 7 处
  - 🔴 核心替换：`counts).toEqual({23,6})` + `tables.length).toBe(29)`
    → **结构不变式** `counts.listed + counts.soe === tables.length` + 两键为正整数
    （替代两个硬编码且判据更强 —— 生成器出 bug 才红，别人改真源不红）
  - 地板常量命名声明 + 注释记「当前实测 N」：`tables.length ≥ 20`（实测 32）、
    `narrowed.length ≥ 10`（实测 18）、`SCANNABLE.length ≥ 10`（实测 26）
  - 天花板：`leaky.length ≤ 4`（脏名只许减少，实测已降到 2）
  - **删除** `leaky.some(含 <br/>)).toBe(true)`（真源已无此类名，锁死正在消失的脏数据无意义）
  - `GENERIC_TABLE_NAMES` 判据反转为形态 A：「登记条目若已不在真源清单则报请移出」并列出条目
    （当前 `''` 与 `'项  目'` 两条都已不在 → 改造后应报请移出 ⇒ **本 Task 需一并移出这两条**，
    同时确认移出后 `SCANNABLE` 仍不含它们（真源里已没有））
  - 拆 `it`：原 L155-171 的规模断言与 6 条归因断言分离（`八、93` 必在 / `外币货币性项目` 必不在 /
    `五、32`·`五、71`·`八、91`·`八、81` 必在），归因断言改为收集清单后单次 `toEqual([])`
  - 每条失败消息补真源路径 `backend/data/note_shared_table_segments.json` 与重生成命令
  - 修正注释里的过期推导链（「29 张表 → 17 去重名 → 剔 2 脏名 = 15」已全错）
  - 🔴 **不重复承担生成器职责**：前端不得自行重算 payload 与真源逐字比对
    —— 「生成器与真源漂移」已由后端 `test_note_shared_table_segments.py` 的
    `gen.main() == 0`（`--check`）覆盖且工作正常（它正是本次唯一没红的那一侧）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_

- [ ] 3. `MISSING_SYNC_PATH` 语义拆分

  - 拆为 `PERMANENT_EXEMPT`（4 条：H5 listed / L2 ×2 / N4 soe）与 `SYNC_PATH_GAP`（2 条：L4 ×2）
  - 🔴 拆分中**不得丢失**既有依据说明：H5 的三条实证（variant_matrix 两键 null / listed 模板
    204 章节含「油气」0 个 / `H5_NOTE_SECTION` 只有 soe 键）、L2 的 K3 撞表论证
    （含「源 xlsx 应付利息行清单逐字相同」）、N4 的「附注披露信息：无」+ variant_matrix null
  - 形态 A 关系断言保留并调整：`unexpected = actual − (exempt ∪ gap)` 必须为 `[]`；
    「已补齐必须移出」拆成两条（分别针对两个常量）
  - `expect(MISSING_SYNC_PATH.length).toBe(6)` → 两个天花板（`≤4` / `≤2`），注释写明「只许缩」
  - 新增可收敛断言：`SYNC_PATH_GAP.length` 的地板为 0（允许清零，L4 重建后自然归零）
  - 保留那段递减史注释（49→…→6）作为演进记录，但标注「数字不再作为断言」
  - _Requirements: 4.2, 4.3, 4.4_

- [ ] 4. 外部锚定解耦（跨 spec 边界，改 `l-cycle` 拥有的文件）

  - `l2l4DisclosureWiring.spec.ts` L842-849 的正则抠数字 + `toBe(6)` 改为语义存在性断言：
    `PERMANENT_EXEMPT` 段内含 `L2TabDisclosureListed.vue`、`SYNC_PATH_GAP` 段内含
    `L4TabDisclosureListed.vue`
  - 🔴 改造后的语义变化要在注释里写清：**L4 补齐时这条会红，且这是正确的红**
    （L 循环守卫应当感知自己关注的缺口被填），而不再因为「别人把 6 改成 4」而红
  - L1293-1310 的「豁免注释块字面存在」断言保留（它已是形态 A 的合理用法），
    但需随 Task 3 的常量改名同步锚点
  - 🔴 本 Task 改的是 `l-cycle-extraction-formula-and-disclosure-completion` 的产物
    ⇒ 提交说明须点明跨 spec 改动与原因，避免该 spec 推进方误判为回退
  - _Requirements: 4.1_

- [ ] 5. 天花板余量与失败消息质量

  - `ALLOWLIST_BUILDER_CEILING` / `ALLOWLIST_TABLE_CEILING`（现值 2 / 11，与实际条目数贴死）：
    确认「只许缩」是有意设计，注释补「缩小时必须同步下调天花板」，
    并验证「条目数 < 天花板」时不报红（design Property 13，用替身 fixture）
  - `INFERENCE_FALLBACK_ALLOWLIST` 的「实扫集合 === 声明集合」失败消息拆成两类明细：
    「新增 None 态表（违规，请补 flat/group）」与「已修好未删条目（请从 allowlist 删除）」
  - 复核 `BUILDER_FLOOR` / `TABLE_FLOOR`（12/60，实测 22/92）余量是否仍充足，
    注释更新实测值
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. 口径写入 steering

  - `.kiro/steering/conventions.md` 补守卫判据形态分级：A（违规清单为空）/ B（地板天花板）/
    C（包含式重点项）可用；D（全局等值）/ E（跨文件抠数字再等值）禁用
  - 给出本次实测的代价数据作为说服力：一次真源变更（K 循环补段首码）导致
    **3 个 blocking job 挂、7 条断言红、6 条有效归因断言被连坐、约 15 分钟归因成本**
  - 补一条操作口径：新建全量扫描守卫时，规模型断言一律用地板 + 注释记实测值，
    禁止 `toBe(<实测值>)`
  - _Requirements: 8.5_

- [ ] 7. 变异检验（每个被改判据必须 RED）

  - 新建 `backend/scripts/check/mutate_guard_attribution.py`，支持 `--list` / `--only X` / `--restore`
  - 锚点至少覆盖：
    - 结构不变式（人为让 `counts.listed + counts.soe ≠ tables.length`）
    - 地板（人为把真源清单截断到地板以下）
    - 天花板（人为给 `GENERIC_TABLE_NAMES` 加第 3 条）
    - 归因清单（人为从真源删掉 `八、93` 段的 `data_end` 使其不再窄）
    - 登记表拆分（人为把 L4 从 `SYNC_PATH_GAP` 移除但不补链路 → `unexpected` 非空）
    - 外部锚定（人为从 `PERMANENT_EXEMPT` 移除 L2 → `l2l4DisclosureWiring` 必红）
  - 四态判定：RED / GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）/ WRONG-TEST（污染）；
    只有 RED 且命中预期测试名才算通过
  - 🔴 变异真源 JSON 时必须走临时副本 + `monkeypatch`/环境变量重定向，**不得直接改**
    `backend/data/note_shared_table_segments.json`（并发会话可能正在读）
  - 每个归因清单型断言补「扫描面非空」地板（design Property 17）
  - 绑定 `e1FxNoteSectionMap.ts` 的反向自检处补风险注释（design Property 18）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. 验收与入库

  - 串行跑（`--no-file-parallelism`）：`disclosureSharedTableRowScope` ·
    `disclosureAutoSyncCoverage` · `disclosureColumnsCoverage` · `l2l4DisclosureWiring` ·
    `e1FxNoteSectionMap` · `e1DisclosureConsistency` · `restrictedAssetsNoteSectionMap` ·
    `restrictedAssetsSources` · `restrictedAssetsConsistency`，记录 files/tests 通过数
  - 后端侧确认未被波及：`backend/tests/test_note_shared_table_segments.py` 仍全绿
  - 🔴 三个 blocking job 的**干净 checkout 模拟**：`git stash` 无关改动或在临时 worktree 上
    跑 job 的命令行，证明不依赖工作树里的未提交文件
  - 🔴 `.github/workflows/governance-checks.yml` 若需改动（如给普查脚本加 job）：
    验收判据用**归因型**（变动落在本 spec 的字节区间内），不得用「其他 job 一个都没变」
    —— 该文件多 spec 并发编辑，全局等值必假红
  - `git status --porcelain -- <本 spec 产物清单>` 必须无 `??`
  - 清理 `_wip_*` 临时产物（只删本 spec 前缀，不动他人的）
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

## Notes

### 本 spec 的立项证据（2026-08-15 实测，i 循环收口时发现）

`disclosureSharedTableRowScope.spec.ts` 7 条断言全 RED：

| 断言 | 硬编码基线 | 实测真源 |
|---|---|---|
| `manifest.counts` | `{listed:23, soe:6}` | `{listed:24, soe:8}` |
| `manifest.tables.length` | 29 | 32 |
| 窄可写区段数 | 15 | 18 |
| `SCANNABLE.length` | 15 | 26 |
| `项  目*` 泄漏名数 | 4 | 2 |
| 泄漏名含 `<br/>` | true | 两个都不含 |
| 脏名登记表每条仍在清单 | `''` / `'项  目'` 必须在 | 两者都已不在 |

因果链：2026-08-12 K 循环 `fix_note_k_report_row_codes.py` 补了共享表段首
`report_row_code` → 真源 23/6/29 变 24/8/32 → 改动方同步了生成器 `EXPECTED_COUNTS`
与后端 `test_note_shared_table_segments.py`（两处都写了 docstring 说明来源）→
**前端守卫属于另两个 spec，改动方 CI 视野里没有它**。

### 三条注意事项

1. **不要跑前端全量**：本仓 1999 个测试文件、4-worker 并发下会产出大量资源竞争型
   flaky（实测全量报 73 files failed，抽样单独复跑只剩 1 个真红，失败原因是 mock 的
   `HTTP 500`/`Network error`）。一律按引用关系反查辐射面 + `--no-file-parallelism`
2. **改真源 JSON 做变异时走临时副本**：`backend/data/note_shared_table_segments.json`
   可能被并发会话读取，直接改会污染他人判断
3. **`governance-checks.yml` 的验收判据必须归因型**：该文件多 spec 并发编辑，
   「其他 job 一个都没变」这类全局等值必假红（实测拍快照 144 job → append 后复核 147）

### 与其它 spec 的边界

- 本 spec **只改判据形态**，不补任何真实缺口。`SYNC_PATH_GAP` 里的 L4 ×2 由
  `l-cycle-extraction-formula-and-disclosure-completion` 负责重建，本 spec 只是让
  「缺口数」变成可独立收敛的断言
- `INFERENCE_FALLBACK_ALLOWLIST` 里 H1/I1 的 11 张表补 `flat` 不属本 spec，
  本 spec 只改天花板语义与失败消息分类
- 普查判为 `keep` 的单循环硬计数（如 `g7NoteSubtableContract` 的 27/2/11/3）
  一律不动，只补一行「作用域限于 X 循环，故硬计数安全」的注释
