# M2 / M3 / M4 / M7 / M10 —— SHEET_MAP 错位与粒度折叠收口 · 任务

> **实施纪律**
> - 🔴 **共同裁决只引用 `MC-x` 编号，不复述内容**（唯一出处是 foundation 的 `design.md`）。
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对；禁写死。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**。
> - 🔴 **sheet 名禁 `.strip()`** —— 任何归一化都会让本 spec 的 5 处丢空格缺陷凭空消失（MC-10）。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**；与 slice / 删除清册比对按 MC-29 加偏移量。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`。
> - 🔴 **PG 每条查询独立事务**；`checklist_responses` 列名是 `wp_id`，底稿主表是 `working_paper`（单数）。
> - 🔴 **不得抄 L 的四条公式层缺陷**（`#REF!` / 越界 / dangling / 倒挤链）—— M 侧全为 0（MC-20）。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3）、真库无业务载荷（闭环）、或需业务确认（文案残留）。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：BP 归位与前置门（Task 0 ~ 3）

- [x] 0. 五条 entry 的 blocked_by 现算门
  - 现算 `capability_target_blocked_by`：M2 **11** 项 / M3 **10** / M4 **10** / M7 **9** / M10 **11**
  - 断言五条**全部含 BP-4**；现算全 M 域含 BP-4 的 entry 集合，断言恰等于本 spec 5 条
  - _Property: MA-P1, MA-P2_

- [x] 1. 横跨 spec 的 BP 交叉引用门
  - 断言 BP-6 成员 = {M1, M2, M3, M4}，本 spec 含 3 条、**M1 在 lane 3** ⇒ 🔴 判据函数**单一归属**（本 spec 定义、lane 3 引用），不得各自定义
  - 断言 BP-8 成员 = {M2, M8, M10}，本 spec 含 2 条、**M8 在 lane 3** ⇒ 同样交叉引用
  - 断言 BP-12 只在 M10 且是全 M 域唯一
  - _Property: MA-P3, MA-P4, MA-P5_

- [x] 2. 公共 BP 引用门（不重裁）
  - BP-5 引用 **MC-16** · BP-7 引用 **MC-12** · BP-9 引用 **MC-1** · BP-10 引用 **MC-8** · BP-11 引用 **MC-26**
  - 🔴 断言本 spec 三文件里这些 MC 编号**只出现编号不出现判据复述**
  - _Property: MA-P6_

- [ ] 3.* BP-1 / BP-2 / BP-3 外部供给登记
  - 标 `[ ]*`：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针
  - 引用 foundation 的登记，不重复裁决
  - _Property: 不宣称通过_

---

## 阶段 1：BP-4 逐对修（Task 4 ~ 9）

- [x] 4. SHEET_MAP 规模现算门
  - 正则从 5 个 `useM{n}EntryDualMode.ts` 现读 `M{n}_SHEET_MAP`，断言 `declared == 43`
  - 对每个 value 断言它 ∈ openpyxl 真读的 `wb.sheetnames`（🔴 **不得 strip**），得 `hit == 34` / `missing == 9`
  - 🔴 断言 `9 == 全域 11 − M9 的 2`（M9 的 MAP 在 orphan 模块里 ⇒ 归 lane 3 登记不修）
  - _Property: MA-P7_

- [x] 5. 三种错法分类门
  - 断言 `① 丢空格 5 + ② 整段不同 3 + ③ 同码压成一个 1 == 9`，逐条列出「声明值 → 权威册真名」
  - 🔴 列举项数必须与计数相等；「丢空格」判据是「去空格后能命中真 sheet」
  - 断言 M7 的真名是**前导 + 中间 + 尾随三重**空格
  - _Property: MA-P9_

- [x] 6. 🔴 修法裁定（本 task 的产物是裁定书）
  - 在 ①**硬编码真名** 与 ②**规范化键查表** 之间裁定，**写明理由**
  - 🔴 构造用例证明路线 ② 单用在 M2 上唯一性校验**必失败**（两张同码明细表规范化成同一个键）
  - 裁定结论：采纳 ① + CI 守卫补抗改名短板 + M2 额外带判别位
  - _Property: MA-P10_

- [x] 7. 逐对改写（9 处）
  - 把 9 个 value 逐字改为 openpyxl 真名，**含前导 / 中间 / 尾随空格逐字保留**
  - 🔴 反例自检：对同一集合做 `.strip()` 后重跑 Task 4 的比对，断言 5 处丢空格缺陷**凭空消失**
  - _Property: MA-P8_

- [x] 8. 反向判据门（证明比对器不是恒判不存在）
  - 断言本 spec 5 条的 fallback 字面量 `审定表M{n}-1` **全部命中**真 sheet（现算 5/5）
  - 🔴 注释写明这正是危害长期不可见的机制（引用 **MC-23**）
  - _Property: MA-P12_

- [x] 9. 守卫转绿 + fail closed 验证
  - 使 foundation 新增的「SHEET_MAP 的每个 value ∈ 权威册 sheet 名集合」守卫在本 spec 5 条上**转绿**
  - 断言 fail closed 生效：注入一个不存在的 value 后守卫报错**并指出首个漂移项**
  - _Property: MA-P11_

---

## 阶段 2：BP-12 死代码修正（Task 10 ~ 12）

- [x] 10. 死代码定位门
  - 定位 M10 宿主以「附注披露信息（国有企业）」为字面量的分支，断言该字面量**不在**权威册 sheet 名集合里 ⇒ 不可达
  - 现算根因链：错名来自 `_archive/05-business-features/m10-other-equity-instruments/requirements.md`；`_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md` **记对了名**
  - 🔴 引用 **MC-25**，不重复裁决根因
  - _Property: MA-P13, MA-P14_

- [x] 11. 两处字面量同 commit 修
  - 国企版 → `附注披露信息核对（国企）`；上市版 → `附注披露信息核对（上市公司）`
  - 🔴 **两处必须同 commit** —— 只修一处是半修
  - 断言修后国企项目能命中该 sheet（用国企项目的 `applicable_standards` 跑通）
  - _Property: MA-P15_

- [x] 12. 防复发 + 门控不冲突门
  - 🔴 宿主判断串与 SHEET_MAP **共用同一常量**，断言全文件内该 sheet 名字面量只出现 1 次
  - 断言 `applicable_standards` 门控（国企项目编辑上市 Tab 被 409 拦截）已交付且与本条不冲突
  - 🔴 **不回填修改已归档 spec**（append-only），勘误引用 foundation 的登记
  - _Property: MA-P16_

---

## 阶段 3：BP-8 粒度折叠（Task 13 ~ 17）

- [x] 13. 两种折叠现算门
  - M2：断言 **11 张 sheet → 10 个 dispatch code**，重复码恰 1 个，来源是两张同尾码明细表
  - M10：断言 **11 张 sheet → 10 个 dispatch code**，来源是 `Q10A (修订前)` 折叠到本版 `procedure`
  - _Property: MA-P17, MA-P18_

- [x] 14. 🔴 性质相反的登记（修法不可共用）
  - 断言 M2 是「两张真实业务 sheet **都该到达**」· M10 是「历史 sheet **不该到达**」
  - 🔴 在测试文件注释里写明「用同一方案会把 M2 的非上市版也过滤掉、或把 M10 的历史 sheet 也放进来」
  - 引用 **MC-24** 说明后端单一过滤是根治、本阶段是前端补救
  - _Property: MA-P19_

- [x] 15. M2 判别位现算与 sheet_key 定义
  - 现算确认判别源（项目 `applicable_standards` 或宿主 Tab 状态），🔴 **不得推演**
  - 定义 `sheet_key = "{尾码}#{上市/非上市判别}"`；🔴 断言该 key **不含 MC-10 的空格缺陷**（不得把带空格真名直接当 key）
  - _Property: MA-P19, MA-P27_

- [x] 16. M10 历史 sheet 判断顺序修正
  - 引用 **MC-27** 的正面样板（foundation Task 44 抽出的共用判据函数），把历史 sheet 判断排到业务 sheet 判断**之前**
  - 复刻 dispatch 顺序验证：修后 `Q10A (修订前)` 不再命中 `procedure`
  - _Property: MA-P18_

- [x] 17. 解析层 fail-closed 改造（两侧都验）
  - 「多张同时 `endswith` 同尾码」时不再静默取第一个，要求调用方带判别参数否则返回明确错误
  - 🔴 **两侧都验**：歧义 entry（M2 / M10）走新路径；无歧义 entry（M3 / M4 / M7）**不受影响**
  - _Property: MA-P20_

---

## 阶段 4：BP-6 mode 枚举统一（Task 18 ~ 19）

- [x] 18. mode 枚举现算门
  - 断言 M2 / M3 / M4 的 orphan 孪生声明为 `'structured' | 'onlyoffice'`，M5~M10 是 `'html' | 'onlyoffice'`（引用 **MC-16**）
  - 断言 🔴 统一动作**只对 orphan 生效**（活路径 0 键、mode 存内存 `ref`）⇒ 与 orphan 删除合并执行，不需要独立迁移脚本
  - 断言 M9 的第二个孪生用**类型引用** `WorkpaperRenderMode` ⇒ 扫字面量的判据会漏掉它（M9 归 lane 3）
  - _Property: MA-P21_

- [x] 19. 🔴 分界线不重合门（防顺手改错）
  - 引用 **MC-15** 断言 BP-6 分界（M1~M4 / M5~M10）与 item_id 命名分界（M1~M3 / M4~M10）**不重合**
  - 🔴 断言 **M4 在两侧归属不同** ⇒ 统一 mode 枚举时**不得顺手改 M4 的 item_id 命名**
  - 构造用例：若把 M4 的 item_id 一并改成重复型，断言相关持久化键读侧必红
  - _Property: MA-P22_

---

## 阶段 5：MC-17 模板修复（Task 20 ~ 22）

- [x] 20. r26 漏加现算门
  - 现算 `明细表M10-2` 的三段结构（小计行 r15 / r20 / r25）与合计行 r26
  - 断言漏加 **10 列**（形如 `=SUM(x15,x20)`，逐列列出，🔴 项数 == 10）+ 加齐 **4 列**（形如 `=x25+x20+x15`）+ 派生污染 **2 列**（`Y26` / `Z26`）
  - 🔴 注释写明「同一行内两种写法并存」是缺陷的直接证据
  - _Property: MA-P23_

- [x] 21. 修复 + 全域唯一性复扫
  - 把 10 列补成三段全加；断言修后 `Y26` / `Z26` 自动正确（派生关系不变，不改）
  - 🔴 限 A 列扫行标签（引用 **MC-11** 第 ④ 项）复扫全 M 域，断言 `missing_subtotal` 只此一处
  - 🔴 与 L 对照断言：`审定表L4-1` 的 `=B11+B16+B17` 是正确避重复，判据能区分两者（区分点是「被跳过的行是否已被其他项包含」）
  - _Property: MA-P24, MA-P25_

- [x] 22. 模板基线同步
  - 🔴 改模板后**同步更新 slice `template_ref` 的 M10 册 sha256 基线**，守卫现算比对
  - 🔴 不更新基线会让既存守卫 `test_task55_m_cycle_migration.py` 红；改完必须重跑该文件确认零回归
  - _Property: MA-P24_

---

## 阶段 6：文案残留与键收口（Task 23 ~ 26）

- [ ] 23.* M10 跨册文案残留登记（🔴 阻塞：需业务确认）
  - 逐处定位并现算处数（🔴 禁写死，列举项数与计数相等）：`M10A` 审计目标段整段写「其他综合收益」· 「获取或编制实收资本（股本）明细表」· `Q10A (修订前)` 抄 M2 · `明细表M10-2` 审计目标同样写「其他综合收益」
  - 🔴 **反例一并登记**：M2 册的跨科目命中是**正当业务表述**（如「如果存在库存股交易：…」），判据须能区分（判别点：是否出现在「审计目标 / 表名 / 字段标签」位置）
  - 标 `[ ]*`：文案属业务内容，改动需业务确认；本 task 只登记
  - _Property: MA-P26_

- [x] 24. M2 同码双 sheet 结构差异门
  - 现算两张的裸 IF 数（相同）与公式格数（不同，差值现算）⇒ 🔴 **不是简单复制**
  - 断言 `明细表（上市公司）M2-2` 是 M 全域**最宽** sheet（列 × 行现算）
  - 契约给两张**各自**的字段映射，不共用一份
  - _Property: MA-P27_

- [x] 25. 位置化与 removeRow 收口（本 spec 份额）
  - 按 **MC-8** 四族口径现算本 spec 份额；按 **MC-7** 四元组枚举 removeRow 变体（含 `removeRow('capital', $index)` / `removeRow('expense', $index)` 双参形态）
  - 🔴 **自建正面样板**（引用 **MC-6**：M 域零可抄模块），断言形态与 foundation 在 M6 上建立的一致 —— **不新造第二种形态**
  - 🔴 双层索引映射（`rawIdx` / `globalIdx` / `displayIndex` / `tableIndex`）**同时消除**
  - item_id 迁移映射按 entry 分别写（🔴 本 spec 内部横跨两批命名，引用 **MC-15**）
  - _Property: MA-P28_

- [x] 26. 模板层基线引用（只引不改）
  - 现算本 spec 5 册的逐册值：公式格（M2 最多）· M3 有参考页 `参考－会计规定`（全角连字符）· M3 / M10 各 2 张 OO 兜底 · 裸 IF 集中在 M2 两张同码明细表 · 幽灵行
  - 断言本 spec 5 册的 definedName broken 数**彼此相同**（引用 **MC-9**）；🔴 **本 spec 不清理污染**（归全域批次，避免清一半）
  - 🔴 断言唯一的模板修改是阶段 5，其余一律不改
  - _Property: 引用 MF-P39, MF-P41_

---

## 阶段 7：闭环与自检（Task 27 ~ 28）

- [ ] 27.* 五条 entry 的端到端闭环（🔴 阻塞：真库无业务载荷）
  - 标 `[ ]*`：现算 M2 1 行（`M2-M2-1-auditNote`，`remark` 为 `NULL`）· M7 1 行（`M7-disclosure-soe-row-0-policy`，`remark` 为 `NULL`）· **M3 / M4 / M10 各 0 行**
  - 🔴 M7 那行的 `row-0` 是 **0-based**（引用 **MC-8**），迁移映射须同时处理两种基准
  - 预置动作（不阻塞）：起草 per-entry contract 草案，字段映射只映 `remark`，`conclusion` 标不使用
  - _Property: 不宣称通过_

- [x] 28. 本 spec 自检
  - 断言 `MC-x` 引用**只出现编号不出现复述**（扫本 spec 三文件）
  - 断言 entry 用 `entry_id` 全名、5 条无重无漏
  - 算术自检：sheets `11+10+9+10+11 = 51` · HTML 44 + OO 7 = 51 · SHEET_MAP `43 = 34 + 9` · 错法 `5+3+1 = 9` · 与全域差额 `11 − 9 = 2` == M9 的 2 处 · BP-6 `3 + 1 = 4` · BP-8 `2 + 1 = 3` · BP-12 `1`
  - 断言 `MA-P1 ~ MA-P28` 无缺号无重号；断言无 U+FFFD；断言「N 处」与列举项数相等
  - _Property: 全部_
