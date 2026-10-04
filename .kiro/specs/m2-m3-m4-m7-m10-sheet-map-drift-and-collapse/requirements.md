# M2 / M3 / M4 / M7 / M10 —— SHEET_MAP 错位与粒度折叠收口 · 需求

## 引言

**上游**：`m-cycle-sync-foundation-and-first-canary`（MC-1 ~ MC-29 共同裁决的唯一出处）+ M slice（`backend/data/workpaper_sync_m_cycle_manifest_slice.json`）+ 删除清册（`backend/data/workpaper_sync_m_cycle_deletion_plan.json`）+ 既存守卫 `backend/tests/workpaper_sync/test_task55_m_cycle_migration.py`。

**本 spec 的 entry 范围（5 条，全名）**：
- `xlsx/gt-m2-paid-in-capital`（M2P）
- `xlsx/gt-m3-treasury-stock`（M3T）
- `xlsx/gt-m4-capital-reserve`（M4C）
- `xlsx/gt-m7-special-reserve`（M7S）
- `xlsx/gt-m10-other-equity-instruments`（M10O）

**切分依据**：以 **BP-4（`M{n}_SHEET_MAP` 错位，M 独有且最贵的一条）** 为主轴 —— 本 spec 恰是**全部含 BP-4 的 5 条 entry**，承载 11 处错位里的 **9 处活映射**。

🔴 **共同裁决只引用编号**：本 spec 出现的 `MC-x` 一律只写编号，**不复述内容**；判据内容以 foundation 的 `design.md` 为唯一出处。

🔴 **缺陷集合重合是事实不是失误**：M2 同时含 BP-4 / BP-6 / BP-8；M10 同时含 BP-4 / BP-8 / BP-12；M3 / M4 含 BP-4 / BP-6；M7 只含 BP-4。BP 集合在 M 循环是**交叉重叠**，不存在 L 那样的互斥二分（见 foundation `design.md` 的切分依据节）。

## Requirement 1：五条 entry 的 BP 归属现算门

**User Story:** 作为实施者，我需要五条 entry 的阻塞项被逐条现算归位，这样我不会把不属于本 spec 的缺陷做进来、也不会漏掉属于本 spec 的。

### 验收准则

1. WHEN 现算五条的 `capability_target_blocked_by` THEN 系统 SHALL 得到：M2 **11** 项 · M3 **10** 项 · M4 **10** 项 · M7 **9** 项 · M10 **11** 项，且**全部含 BP-4**。
2. WHEN 断言 BP-4 的完备性 THEN 系统 SHALL 现算全 M 域含 BP-4 的 entry 集合，断言它恰等于本 spec 的 5 条（多一条或少一条都红）。
3. WHEN 现算 BP-6 归属 THEN 系统 SHALL 断言本 spec 含 **M2 / M3 / M4**（3 条），而第 4 条 BP-6 成员 **M1 归 lane 3** ⇒ 🔴 **BP-6 横跨两份 spec 是有意的**，两份 spec 的 BP-6 判据必须交叉引用、不得各自定义。
4. WHEN 现算 BP-8 归属 THEN 系统 SHALL 断言本 spec 含 **M2 / M10**（2 条），第 3 条 **M8 归 lane 3**，同样交叉引用。
5. WHEN 现算 BP-12 归属 THEN 系统 SHALL 断言它是**全 M 域唯一一条**且只在 M10。
6. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 系统 SHALL 标 `[ ]*` 并引用 foundation 的登记，**不重复裁决**。
7. WHEN 处理 BP-5 / BP-7 / BP-9 / BP-10 / BP-11 THEN 系统 SHALL 引用 MC-16 / MC-12 / MC-1 / MC-8 / MC-26，**不重新裁决**。

## Requirement 2：BP-4 的 9 处活映射逐对修（MC-23）

**User Story:** 作为实施者，我需要每一对错位映射都被逐字修到 openpyxl 真名，这样改线时不会把缺陷搬到 sync bridge 侧。

### 验收准则

1. WHEN 现算本 spec 的 SHEET_MAP 规模 THEN 系统 SHALL 得到 `declared 43 = hit 34 + missing 9`（M2 9/6/3 · M3 8/7/1 · M4 8/7/1 · M7 9/8/1 · M10 9/6/3），并断言 9 == 全域 11 减去 M9 的 2（orphan 模块，归 lane 3 登记不修）。
2. WHEN 逐对修 THEN 每个 value SHALL 被换成 openpyxl 真读的 sheet 名，🔴 **含前导 / 中间 / 尾随空格逐字保留**，不得 `.strip()`（引用 MC-10）。
3. WHEN 修「丢空格」类 THEN 系统 SHALL 覆盖 5 处（M2 / M3 / M4 / M7 / M10 各 1 的 `procedure` 键），并断言 M7 的真名是**前导 + 中间 + 尾随三重**空格。
4. WHEN 修「名字整段不同」类 THEN 系统 SHALL 覆盖 3 处：M2 的 `检查表M2-5` → `实收资本（股本）检查表M2-5`（少前缀）· M10 的 `附注披露信息（上市公司）` → `附注披露信息核对（上市公司）` · M10 的 `附注披露信息（国有企业）` → `附注披露信息核对（国企）`（**双重差异**）。
5. WHEN 修「同码压成一个」类 THEN 系统 SHALL 覆盖 1 处：M2 的 `明细表M2-2` 在真册是 `明细表（上市公司）M2-2` 与 `明细表（非上市公司）M2-2` **两张** ⇒ 一个 sheet code 映到两张，必须先解决 sheet_key 唯一性（见 Requirement 8）。
6. WHEN 计数自检 THEN 系统 SHALL 断言 `5 + 3 + 1 = 9`（🔴 与全域的 `6 + 4 + 1 = 11` 差的正是 M9 的 1 处丢空格 + 1 处整段不同）。
7. WHEN 修法被选定 THEN 系统 SHALL 在两条路线间**显式裁定并写明理由**：① 硬编码真名（抗改名弱但简单）；② 规范化键查表（去空格去括号后查真 sheet 名，抗改名强但**必须在 sheet 名集合上做唯一性校验** —— M2 的两张同码明细表正是唯一性会失败的例子）。
8. WHEN 修完 THEN 系统 SHALL 使 foundation 新增的守卫「SHEET_MAP 的每个 value ∈ 权威册 sheet 名集合」在本 spec 的 5 条上**转绿**，并断言 fail closed 生效（value 不在集合里时报错并指出首个漂移项）。

## Requirement 3：BP-12 —— M10 「国企」判断的死代码（MC-25）

**User Story:** 作为实施者，我需要 M10 国企 Tab 的判断串被修到真名，这样国企项目不会永远命中不到该 sheet。

### 验收准则

1. WHEN 现算 M10 宿主的判断串 THEN 系统 SHALL 定位以「附注披露信息（国有企业）」为字面量的分支，并断言该字面量**不在**权威册 sheet 名集合里 ⇒ 该分支不可达。
2. WHEN 根因被登记 THEN 系统 SHALL 引用 MC-25，断言错名来自已归档 spec `_archive/05-business-features/m10-other-equity-instruments/requirements.md`，且**另一份已归档 spec 记对了名** ⇒ 代码采纳了错的那份。
3. WHEN 修正被执行 THEN 系统 SHALL 把字面量改为 `附注披露信息核对（国企）`，并断言修后国企项目能命中该 sheet。
4. WHEN 回归被保护 THEN 系统 SHALL 断言上市公司版分支同时修正为 `附注披露信息核对（上市公司）`，🔴 **两处必须同 commit 修** —— 只修一处就是半修（M10 的两个附注 sheet 名都错）。
5. WHEN 与既有门控的关系被说明 THEN 系统 SHALL 断言 `applicable_standards` 门控（国企项目编辑上市 Tab 被 409 拦截）**已交付**，本条修的是 sheet 名而非门控 ⇒ 两者不冲突。
6. WHEN 防复发被落位 THEN 系统 SHALL 要求宿主判断串与 SHEET_MAP **共用同一常量**，不得两处各写一遍字面量。

## Requirement 4：BP-8 粒度折叠（M2 / M10）

**User Story:** 作为实施者，我需要 M2 与 M10 的 sheet 折叠被区分开，这样双向回写时 sheet_key 能一一对应。

### 验收准则

1. WHEN 现算 M2 的折叠 THEN 系统 SHALL 断言 **11 张 sheet → 10 个 dispatch code**，重复码恰 1 个，来源是 `明细表（上市公司）M2-2` 与 `明细表（非上市公司）M2-2` 两张同尾码 sheet。
2. WHEN 现算 M10 的折叠 THEN 系统 SHALL 断言 **11 张 sheet → 10 个 dispatch code**，来源是 `Q10A (修订前)` 被折叠到本版 `procedure`（不可达死代码导致，引用 MC-27）。
3. WHEN 两种折叠被区分 THEN 系统 SHALL 写明性质不同：M2 是**两张真实业务 sheet 同码**（必须都能到达）· M10 是**历史 sheet 折叠到现版**（历史 sheet 应被过滤掉而非到达）⇒ 🔴 修法相反，不可用同一方案。
4. WHEN M2 的修法被定义 THEN 系统 SHALL 采用 `sheet_key = "{尾码}#{上市/非上市判别}"` 形态，判别源须现算确认（项目的 `applicable_standards` 或宿主 Tab 状态，**不得推演**）。
5. WHEN M10 的修法被定义 THEN 系统 SHALL 采用 MC-27 的正面样板（把历史 sheet 判断排到业务 sheet 判断**之前**），并引用 MC-24 说明后端过滤是根治、本条是前端补救。
6. WHEN 解析层被改造 THEN 系统 SHALL 要求「多张同时 `endswith` 同尾码」时**不再静默取第一个**，而是要求调用方带判别参数，否则返回明确错误（fail closed）。
7. WHEN 无歧义 entry 被保护 THEN 系统 SHALL **两侧都验**：歧义 entry（M2 / M10）走新路径；无歧义 entry（M3 / M4 / M7）**不受影响**。

## Requirement 5：BP-6 —— M2 / M3 / M4 的 mode 枚举统一（跨 spec）

**User Story:** 作为实施者，我需要 mode 枚举的 `structured` 被统一成 `html`，且与 lane 3 的 M1 用同一判据。

### 验收准则

1. WHEN 现算本 spec 的 mode 枚举 THEN 系统 SHALL 断言 M2 / M3 / M4 的 orphan 孪生声明为 `'structured' | 'onlyoffice'`，而 M5 ~ M10 是 `'html' | 'onlyoffice'`（引用 MC-16）。
2. WHEN 统一被执行 THEN 系统 SHALL 把 `structured` 归一到 `html`，并断言 🔴 **该动作只对 orphan 生效**（活路径 0 键、mode 存内存 `ref`）⇒ 与 orphan 删除动作合并执行即可，不需要独立迁移脚本。
3. WHEN 与 lane 3 的交叉引用被落位 THEN 系统 SHALL 断言 BP-6 的第 4 条成员 M1 在 lane 3，且两份 spec 的判据函数**同一个**（本 spec 定义，lane 3 引用；或反之，须显式指定归属）。
4. WHEN 分界线差异被登记 THEN 系统 SHALL 引用 MC-15 断言 🔴 **BP-6 的分界（M1~M4 / M5~M10）与 item_id 命名分界（M1~M3 / M4~M10）不重合，M4 在两侧归属不同** ⇒ 统一 mode 枚举时**不得顺手改 M4 的 item_id 命名**。
5. WHEN M9 的例外被登记 THEN 系统 SHALL 断言 M9 的第二个孪生用**类型引用** `WorkpaperRenderMode` 而非字面量联合 ⇒ 扫字面量的判据会漏掉它（M9 归 lane 3）。

## Requirement 6：M10 合计漏加小计 10 列（MC-17）

**User Story:** 作为实施者，我需要 M10 明细表的合计行被修正，这样「三、转股特征」整段金额不会在合计里消失。

### 验收准则

1. WHEN 现算 `明细表M10-2` 的结构 THEN 系统 SHALL 断言三段式（第一段小计在 r15 · 第二段小计在 r20 · 第三段小计在 r25）且合计行在 r26。
2. WHEN 现算漏加 THEN 系统 SHALL 断言 **10 列**的合计公式形如 `=SUM(x15,x20)` ⇒ **漏掉 r25**，并逐列列出（🔴 列举项数必须 == 10）。
3. WHEN 现算加齐的列 THEN 系统 SHALL 断言 **4 列**形如 `=x25+x20+x15`（三段都加）⇒ 🔴 **同一行内两种写法并存**是缺陷的直接证据。
4. WHEN 现算派生污染 THEN 系统 SHALL 断言 **2 列**（`Y26` / `Z26`）基于漏加的 `S26` / `T26` ⇒ 污染「审计调整后期末账面价值」列。
5. WHEN 修正被执行 THEN 系统 SHALL 把 10 列补成三段全加，并断言修后 `Y26` / `Z26` 自动正确（派生关系不变）。
6. WHEN 全域复扫被要求 THEN 系统 SHALL 限 A 列扫行标签（引用 MC-11 第 ④ 项），断言全 M 域 `missing_subtotal` **只有这一处**（现算 10 列）。
7. WHEN 模板基线被同步 THEN 系统 SHALL 在改模板后**同步更新 slice `template_ref` 的 M10 册 sha256 基线**，🔴 不更新会让既存守卫 `test_task55_m_cycle_migration.py` 红。
8. WHEN 与 L 的对照被登记 THEN 系统 SHALL 引用 MC-17 写明 🔴 **L 的 `审定表L4-1` 的 `=B11+B16+B17` 是正确的避重复，M10 这处是真错** —— 两者性质相反，判据必须能区分。

## Requirement 7：M10 跨册复制残留登记（MC-21）

**User Story:** 作为实施者，我需要 M10 的跨科目文案残留被登记，且与 M2 的正当业务表述区分开。

### 验收准则

1. WHEN 现算 M10 册的跨科目文案 THEN 系统 SHALL 逐处定位并现算处数（🔴 禁写死，列举项数必须与计数相等），至少覆盖：`其他权益工具实质性程序表 M10A` 的审计目标段整段写「其他综合收益」· 同册「获取或编制**实收资本（股本）**明细表」（抄 M2）· `Q10A (修订前)` 同样抄 M2 · `明细表M10-2` 的审计目标同样写「其他综合收益」。
2. WHEN 🔴 反例被一并登记 THEN 系统 SHALL 断言 M2 册里的跨科目命中经核是**正当业务表述**（如 `实收资本实质性程序表 M2A` 的「如果存在库存股交易：…」）⇒ **不算残留**，并要求判据能区分两者（判别方式须写明：是否出现在「审计目标 / 表名 / 字段标签」位置）。
3. WHEN 处置被裁定 THEN 系统 SHALL 在「修文案」与「只登记不修」之间**显式裁定并写明理由**（文案属业务内容，改动需业务确认 ⇒ 默认只登记 + 标 `[ ]*`）。
4. WHEN 与 BP-4 / BP-12 的同源关系被写明 THEN 系统 SHALL 引用 MC-21 断言 M10 的附注 sheet 命名抄了 M2 / M9 形态 ⇒ **BP-4 的 M10 两处 + BP-12 同源**。

## Requirement 8：M2 同码双 sheet 的键唯一性（与 Requirement 4 配套）

**User Story:** 作为实施者，我需要 M2 的两张同码明细表在契约层有不同的 sheet_key，这样上市与非上市数据不会互相覆盖。

### 验收准则

1. WHEN 现算两张 sheet 的差异 THEN 系统 SHALL 断言它们**结构不同不是简单复制**：`明细表（上市公司）M2-2` 与 `明细表（非上市公司）M2-2` 的裸 IF 数相同但**公式格数不同**（现算两个数，差值现算）。
2. WHEN 宽表事实被登记 THEN 系统 SHALL 断言 `明细表（上市公司）M2-2` 是 M 全域**最宽**的 sheet（现算列数 × 行数）。
3. WHEN 契约 sheet_key 被定义 THEN 系统 SHALL 保证两张各有唯一 key，且 🔴 **该 key 不含 MC-10 的空格缺陷**（不得把带空格的真名直接当 key）。
4. WHEN 规范化路线被评估 THEN 系统 SHALL 断言「去空格去括号后查真 sheet 名」这条路线在 M2 上**唯一性校验会失败**（两张都规范化成同一个键）⇒ 必须额外带判别位。

## Requirement 9：位置化与 removeRow 在本 spec 的份额收口

**User Story:** 作为实施者，我需要本 spec 名下的位置化行身份与 removeRow 变体被完整枚举处理。

### 验收准则

1. WHEN 现算本 spec 份额 THEN 系统 SHALL 按 MC-8 的四族口径分别报数，并断言本 spec 覆盖的模块集合 = 5 条 entry 对应的 `useM{n}Adjudication.ts` / `useM{n}FormData.ts` / `M{n}Tab*.vue`。
2. WHEN removeRow 变体被枚举 THEN 系统 SHALL 按 MC-7 的四元组逐一登记本 spec 名下变体，含 `removeRow('capital', $index)` 与 `removeRow('expense', $index)` 这类**双参**形态。
3. WHEN 去位置化被执行 THEN 系统 SHALL 🔴 **自建正面样板**（引用 MC-6：M 域按行身份删为 0，无可抄模块），并断言样板形态与 foundation 在 M6 上建立的一致 —— **不新造第二种形态**。
4. WHEN 双索引映射被处理 THEN 系统 SHALL 引用 MC-8 断言本 spec 名下若存在 `rawIdx` / `globalIdx` / `displayIndex` / `tableIndex` 变量，**两层映射必须同时消除**。
5. WHEN item_id 命名轴被处理 THEN 系统 SHALL 引用 MC-15 断言 M2 / M3 属重复前缀型 + snake_case，M4 / M7 / M10 属不重复型 + kebab-case ⇒ 🔴 **本 spec 内部就横跨两批**，迁移映射须按 entry 分别写。

## Requirement 10：模板层基线引用（不修，除 Requirement 6）

**User Story:** 作为实施者，我需要本 spec 的模板层基线只引用不改，除了已明确裁定要修的那一处。

### 验收准则

1. WHEN 模板层事实被引用 THEN 系统 SHALL 只引用 foundation 的基线（MC-9 / MC-10 / MC-11），**不重新现算全域**，但 SHALL 现算本 spec 5 册的逐册值。
2. WHEN 本 spec 5 册的特征被登记 THEN 系统 SHALL 覆盖：M2 公式格最多（现算）· M2 参考页无 / M3 有参考页（`参考－会计规定`，全角连字符）· M10 有 unmatched_by_dispatch 的 OO 兜底 · 裸 IF 集中在 M2 的两张同码明细表（现算各自数值）。
3. WHEN 唯一的模板修改被限定 THEN 系统 SHALL 断言只有 Requirement 6（M10 `明细表M10-2` 的 r26）改模板，其余**一律不改**。
4. WHEN definedName 污染被引用 THEN 系统 SHALL 断言本 spec 5 册的 broken 数**彼此相同**（引用 MC-9 的「其余 8 册相同」结论），且 🔴 **本 spec 不清理污染**（归全域批次，避免 5 册清一半）。

## Requirement 11：端到端闭环（阻塞）

**User Story:** 作为质控，我需要知道本 spec 的闭环为什么不能现在验。

### 验收准则

1. WHEN 闭环被排期 THEN 系统 SHALL 标 `[ ]*`，理由是现算：M2 真库 1 行（`M2-M2-1-auditNote`，`remark` 为 `NULL`）· M7 真库 1 行（`M7-disclosure-soe-row-0-policy`，`remark` 为 `NULL`）· **M3 / M4 / M10 真库 0 行** ⇒ 五条均无有效业务载荷。
2. WHEN 前提被预置 THEN 系统 SHALL 允许起草 per-entry contract 草案（字段映射只映 `remark`，`conclusion` 标不使用），但**不得**据此宣称闭环通过。
3. WHEN BP-1 / BP-2 / BP-3 被引用 THEN 系统 SHALL 引用 foundation 的登记，不重复裁决。

## Requirement 12：本 spec 自检

**User Story:** 作为质控，我需要本 spec 的引用与计数自洽。

### 验收准则

1. WHEN 自检被执行 THEN 系统 SHALL 断言本 spec 三文件里的 `MC-x` 引用**只出现编号不出现判据复述**。
2. WHEN entry 被引用 THEN 系统 SHALL 用 `entry_id` 全名，断言 5 条无重无漏。
3. WHEN 计数自检被执行 THEN 系统 SHALL 断言：sheets `11+10+9+10+11 = 51` · HTML 覆盖 44 + OO 兜底 7 = 51 · SHEET_MAP `declared 43 = hit 34 + missing 9` · 三种错法 `5+3+1 = 9` · BP-4 成员数 5 == 本 spec entry 数。
4. WHEN 「N 处」表述被使用 THEN 它 SHALL 与紧随其后的列举项数相等。
5. WHEN Property 编号被检查 THEN `MA-P` 系列 SHALL 无缺号无重号。
