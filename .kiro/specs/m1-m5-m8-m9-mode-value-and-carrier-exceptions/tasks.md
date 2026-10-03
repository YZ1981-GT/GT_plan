# M1 / M5 / M8 / M9 —— mode 取值与载体例外收口 · 任务

> **实施纪律**
> - 🔴 **共同裁决只引用 `MC-x` 编号，不复述内容**（唯一出处是 foundation 的 `design.md`）。
> - 🔴 **BP-6 / BP-8 的判据函数引用 lane 2 的定义**，本 spec 不另写一套。
> - 🔴 **所有计数一律现算**，与 `design.md` 等值比对；禁写死。
> - 🔴 **判据锚点用常量名 / 端点字面量 / 形态特征，禁写死行号**。
> - 🔴 **sheet 名禁 `.strip()`**（MC-10）；本 spec 4 册的 sha256 前后**不变**。
> - 🔴 **行数口径统一 `len(text.split("\n"))`**；与 slice / 删除清册比对按 MC-29 加偏移量。
> - 🔴 **含正则的核验一律写探针文件**，禁用 `python -c`。
> - 🔴 **PG 每条查询独立事务**；`checklist_responses` 列名是 `wp_id`，底稿主表是 `working_paper`（单数）。
> - 🔴 **不得抄 L 的四条公式层缺陷**（`#REF!` / 越界 / dangling / 倒挤链）—— M 侧全为 0（MC-20）。
> - 🔴 **每条缺陷判据必须在 M5 上跑一遍并应绿**（M5 是干净对照组），证明判据不是一律判红。
> - `[ ]*` = 依赖外部供给（BP-1 / BP-2 / BP-3）、真库无业务载荷（闭环）、或动生产数据需业务确认。
> - 并发会话正在实施 F3/F4/F5 与 H9 的 spec，其契约与关联产物**一律不碰**。

---

## 阶段 0：BP 归位与补集完备性（Task 0 ~ 3）

- [x] 0. 四条 entry 的 blocked_by 现算门
  - 现算 `capability_target_blocked_by`：M1 **9** 项 / M5 **8** / M8 **9** / M9 **8**
  - 🔴 断言四条**全部不含 BP-4**
  - 现算全 M 域不含 BP-4 的 entry 集合，断言 == 本 spec 4 条 + canary `xlsx/gt-m6-retained-earnings`（5 条），且 `5 + 5 == 10`
  - _Property: MB-P1, MB-P2_

- [x] 1. 区分项归位门 + M5/M9 同 BP 不同组的理由
  - 断言 M1 独含 BP-6、M8 独含 BP-8、M5 与 M9 只含公共 8 项
  - 🔴 断言 M5 与 M9 的 BP 集合**完全相同**，但载体层（`kind`）与 SHEET_MAP 层（missing 数）不同 ⇒ 判据**不得只看 `blocked_by`**
  - _Property: MB-P3, MB-P4_

- [x] 2. 公共 BP 引用门（不重裁）
  - BP-5 引用 **MC-16** · BP-7 引用 **MC-12** · BP-9 引用 **MC-1** · BP-10 引用 **MC-8** · BP-11 引用 **MC-26**
  - 🔴 断言本 spec 三文件里这些 MC 编号**只出现编号不出现判据复述**
  - _Property: MB-P5_

- [ ] 3.* BP-1 / BP-2 / BP-3 外部供给登记
  - 标 `[ ]*`：approved authority model + per-entry contract + non-null bundle / Task 36 published representation / 真实 OnlyOffice 9.4 探针
  - 引用 foundation 的登记，不重复裁决
  - _Property: 不宣称通过_

---

## 阶段 1：M9 四重例外收口（Task 4 ~ 9）

- [x] 4. 载体 `none` 与双孪生皆 orphan 门
  - 断言 M9 `dual_mode_carrier.kind == 'none'` 且 `switch_is_redeemable` 为 `false`，10 条唯一
  - 断言 `useM9DualMode.ts` 与 `useM9EntryDualMode.ts` 的生产边与测试边**均为 0**；`entries_with_two_orphan_twins == 1`
  - 🔴 注释写明「抄『orphan 数 == live 数』会把全域分母算错（11 ≠ 9）」
  - _Property: MB-P6, MB-P7_

- [x] 5. 宿主无开关与无锚点门
  - 断言 `GtM9OtherComprehensiveIncome.vue` 剥注释后**无 `el-segmented`**、`ui_toolbar_gate.anchor is None`（`entries_without_any_ui_gate_anchor == 1`）
  - 断言其 `GtOnlyOfficeSheet` 挂点是**未迁移 sheet 的兜底渲染器**而非模式切换
  - 断言 M9 mount == **1**（其余各 2）⇒ 全域 19
  - _Property: MB-P8, MB-P9_

- [x] 6. mode 类型形态与无键门（两类判据都会漏）
  - 🔴 断言 `useM9EntryDualMode.ts` 用**类型引用** `WorkpaperRenderMode` 而非字面量联合，且**无 localStorage 键**
  - 构造反例：用「扫字面量枚举」与「扫 storage 键」两个判据各跑一遍，断言**都漏掉它** ⇒ 判据须补类型引用分支（引用 **MC-16**）
  - _Property: MB-P10_

- [x] 7. 🔴 不得据「无开关」裁 single 门（三条反驳逐条现算）
  - ① M9 有 HTML 对端（`checklist_responses` 通道实测存在）⇒ AC 12.8 禁 `single_onlyoffice`
  - ② M9 册现算 **9** 张 sheet / 公式格 **470**（10 册第二多）⇒ AC 12.9 的 `single_html` 不适用
  - ③ 宿主经 `htmlRendererRegistry` 可达 ⇒ 非 `unreachable`
  - _Property: MB-P11_

- [x] 8. M9 SHEET_MAP 2 处登记（不修）
  - 断言 `declared 8 == hit 6 + missing 2`，两处逐字登记（`其他综合收益实质性程序表M9A` 丢中间空格 · `OCI核对表M9-4` 中英混写整段不同）
  - 断言 `defect_pairs_in_orphan_modules == 2` ⇒ **M9 不挂 BP-4** ⇒ 🔴 **只登记不修**
  - 断言 `全域 11 == lane 2 的 9 + M9 的 2`；`entries_with_defects == 6` 与「BP-4 五条」**两个数并存**
  - _Property: MB-P13, MB-P14_

- [x] 9. M9 orphan 删除 + 错位随之消失验证
  - 🔴 **删除前**断言两个模块无人消费（生产边与测试边均 0）；防「先修 orphan 里的 MAP 再删文件」的无效功
  - 删两个 orphan（同 commit），现算验证 missing 从 **11 降到 9**
  - notice 落位：引用 **MC-12**，断言 M9 须与 sync bridge 的编辑宿主**一并落位**（无既成锚点）
  - _Property: MB-P15, MB-P12_

---

## 阶段 2：BP-6 的 M1（引用 lane 2 判据）（Task 10 ~ 11）

- [x] 10. M1 mode 枚举门
  - 断言 `useM1DualMode.ts` 声明为 `'structured' | 'onlyoffice'`，与 M2/M3/M4 同批
  - 🔴 **引用 lane 2 定义的 BP-6 判据函数**，不在本 spec 另写；断言 BP-6 总数 `3 + 1 == 4`
  - 断言统一动作**只对 orphan 生效**（活路径 0 键，引用 **MC-16**）⇒ 与 M1 的 orphan 删除合并执行
  - _Property: MB-P16_

- [x] 11. 🔴 分界线同侧/异侧对照门
  - 引用 **MC-15** 断言 M1 同属「BP-6 批（M1~M4）」与「item_id 重复前缀批（M1~M3）」= **两条分界线同侧**
  - 与 lane 2 的 **M4 两侧归属不同**形成对照；断言本 spec 在改 M1 时可同批处理，改 M4 时不可（M4 不属本 spec）
  - _Property: MB-P17_

---

## 阶段 3：BP-8 的 M8（Task 12 ~ 14）

- [x] 12. M8 折叠现算门 + 成因区分
  - 断言 **11 张 sheet → 10 个 dispatch code**，来源是 `一般风险准备实质性程序表 Q8A  (修订前)`（**双空格**）折叠到本版 `procedure`
  - 🔴 断言成因是**完全没有拦截代码**（`实质性程序表` 先命中），与 M10 的**死代码**不同 ⇒ 动作是「**新增**」而非「移动」
  - 🔴 **引用 lane 2 定义的 BP-8 判据**；断言 BP-8 总数 `2 + 1 == 3`
  - _Property: MB-P18, MB-P20_

- [x] 13. M8 历史 sheet 判断新增
  - 引用 **MC-27** 的正面样板（foundation 抽出的共用判据函数），新增历史 sheet 判断并排到业务 sheet 判断**之前**
  - 复刻 dispatch 顺序验证：修后 `Q8A  (修订前)` 不再命中 `procedure`
  - 🔴 引用 **MC-24** 断言后端单一过滤是根治、本条是前端补救，两者不互相替代
  - _Property: MB-P18, MB-P20_

- [x] 14. `针对性测试M8-5-删除` 正确处置门
  - 断言「删除」二字是**源模板作者的标注**，该 sheet 落 OO 兜底是**正确处置**
  - 🔴 断言**不得据此裁 single、不得真删 sheet**（引用删除清册 `excluded_from_plan`）
  - 现算 M8 的 OO 兜底 == **2**（`GT_Custom` + 该 sheet），并声明与按 hidden 状态分类的差异（引用 **MC-11** 第 ⑤ 项）
  - _Property: MB-P19_

---

## 阶段 4：M1 的两项独有属性（Task 15 ~ 18）

- [x] 15. 🔴 M1 科目性质现算门（禁推演）
  - **现算科目码**确认 M1 应付股利属**负债类**；判据须落真实科目码或 `backend/data/wp_account_mapping.json` 的现算查询结果
  - 断言 M2 ~ M10 属**权益类**（贷方）⇒ M1 是 10 条唯一负债类 ⇒ 四表判据按 **1 : 9 两分支**写（引用 **MC-22**）
  - 现算 M1 的 TB 发布调用实参形态，结论**如实登记**（🔴 不预设答案）
  - 🔴 注释写明「判据写成『M 全域都是权益类』会让 M1 假绿」
  - _Property: MB-P21_

- [x] 16. M1 ↔ K3 跨循环键守卫落地（MC-19 欠账）
  - 现读 `_archive/08-disclosure-notes/m-cycle-four-table-extraction-and-disclosure-alignment/tasks.md`，断言该守卫任务**未勾选**
  - 🔴 注释写明「不得因该 spec 已归档就认为已完成」
  - 实现守卫：现算 M1 推送的子表键集合与 K3 推送的键集合，断言**交集为空**；不为空则逐键登记并判红
  - 🔴 键集合**从代码现算**（`ITEM_PREFIX` 常量 + 模板串展开），不得只查真库（M 域仅 6 行，分母不足）
  - _Property: MB-P22_

- [x] 17. 守卫扩展到任意两循环两两无交集
  - 现算全部循环的子表键集合，两两比对断言无交集；违例逐条登记
  - 引用 **MC-19** 断言 M 是**被引用方**；断言本 spec 不改动 M 键的四类跨循环消费者
  - _Property: MB-P22_

- [ ] 18.* M1 真库 AI 会话记录行处置（🔴 阻塞：动生产数据需业务确认）
  - 现算 M1 真库 **2** 行：`M1-M1-2-full-data`（`remark` 为 `NULL`）· `M1-review-session-20260725075149`（`remark` 现算字节数）
  - 🔴 断言后者是 **AI 复核会话记录不是业务数据** ⇒ **不得用于闭环验证**、不得据此宣称「M1 有真载荷」
  - 🔴 断言该键**不符合** `ITEM_PREFIX` + sheet 段 + field 段三段式命名（引用 **MC-15**）⇒ 登记为「命名空间被非业务用途借用」的实证
  - 处置裁定：在「迁移到专用表」与「只登记不动」之间**写明理由**；默认只登记 + 标 `[ ]*`
  - _Property: MB-P23_

---

## 阶段 5：正面样板与污染溯源（Task 19 ~ 21）

- [x] 19. `procedure` 键三条 hit 抽取为逐条参照（MC-23）
  - 断言 hit 恰 **3** 条且**全在本 spec**：M1 `'应付股利实质性程序表M1'`（🔴 10 册唯一不带 `A`）· M5 `'盈余公积实质性程序表 M5A'`（中间空格）· M8 `'一般风险准备实质性程序表 M8A '`（中间 + 尾随空格）
  - 🔴 断言三条**写法互不相同** ⇒ 「碰巧与真名一致」而非「按统一规则生成」⇒ 只作逐条参照**不作规则抄**
  - 断言 **M6 根本没有 `procedure` 键** ⇒ 全域状态是「4 种写法 + 1 处缺键」
  - 产出「sheet code → 真名」逐条对照表供 lane 2 引用，断言每个值 ∈ 权威册 sheet 名集合
  - _Property: MB-P25_

- [x] 20. definedName 污染溯源门（不清理）
  - 现算本 spec 4 册的 `total` / `broken`，断言 **M9 与 M1 显著高**、M5 / M8 与其余 6 册**彼此相同**（引用 **MC-9**）
  - 断言 M1 / M9 另含**中文名与跨循环名**（列出 ≥ 3 个样本）⇒ **从别的底稿册复制来的**
  - 断言解析器对 `{#N/A,…,"BBPREP"}` 与 `[1]Breakdown!#REF!` 两形态**不崩**
  - 🔴 断言短名污染与 **L 循环同源**、中文名与跨循环名是 **M 独有** ⇒ 两类来源不同，清理不可一刀切
  - 🔴 断言**本 spec 不清理污染**（归全域批次，避免清一半），只冻结基线
  - _Property: MB-P24_

- [x] 21. M5 干净对照组门（判据必须应绿）
  - 现算 M5 四项全干净：`must_fix_before_wiring` 只 8 项公共 · SHEET_MAP **9/9/0** · `switch_is_redeemable == true` · 载体 `per_entry_wrapper_over_shared_base`
  - 🔴 **把本 spec 全部缺陷判据在 M5 上跑一遍并断言应绿** ⇒ 证明判据能区分「有缺陷」与「无缺陷」
  - 断言与 canary M6 的差异只两项：公式格 **193 > 175**、M5 册**无 Q 表**故无「正确处理先例」
  - _Property: MB-P26_

---

## 阶段 6：位置化与模板基线（Task 22 ~ 24）

- [x] 22. 位置化四族本 spec 份额门（含 M9 特有模块）
  - 按 **MC-8** 四族口径现算本 spec 份额，覆盖 4 条 entry 的 `useM{n}Adjudication.ts` / `useM{n}FormData.ts` / `M{n}Tab*.vue`
  - 🔴 断言 `useM9OciReconcile.ts` 是持久化键族 11 个命中文件里**唯一非 `useM{n}Adjudication.ts` 形态**的一个，且同样恰 **1** 处 `const n = idx + 1` ⇒ 判据**不能只扫 `Adjudication` 命名**
  - 引用 **MC-8** 断言迁移映射同时处理 0-based 与 1-based
  - _Property: MB-P27_

- [x] 23. removeRow 双套映射链收口
  - 按 **MC-7** 四元组逐一登记本 spec 名下变体，含 **`M9TabDetail.vue` 的 `handleRemove(displayIndex)` → `removeRow(globalIdx)`** 这条链
  - 🔴 两层映射**同时消除**；构造用例证明只改一层会造成新的错位（引用 **MC-6**）
  - 🔴 **复用 foundation 在 M6 上建立的正面样板形态**，断言**不新造第二种形态**（与 lane 2 同一形态）
  - item_id 迁移映射按 entry 分别写：M1 重复前缀型 + snake_case；M5 / M8 / M9 不重复型 + kebab-case（引用 **MC-15**）
  - _Property: MB-P28_

- [x] 24. 模板层基线引用（只引不改）
  - 现算本 spec 4 册的逐册值：M9 公式格 **470**（第二多）· M9 明细表属宽表（列 × 行现算）· M1 `明细表M1-2` 公式格最多（现算）· M8 有 `针对性测试M8-5-删除` · **M8 与 M6 的 Q 表 sheet 名双空格**（M10 单空格，引用 **MC-27**）· 「合计 / 小计」中文分散对齐在 M7 / M8 / M9 的分布（现算处数，🔴 项数与计数相等）
  - 🔴 断言本 spec 4 册的 sha256 在本 spec 前后**不变**（与 lane 2 改 M10 册形成对照）
  - 幽灵行现算并声明 `max_row − last_value_row` 口径（引用 **MC-11**）
  - _Property: MB-P29_

---

## 阶段 7：闭环与自检（Task 25 ~ 26）

- [ ] 25.* 四条 entry 的端到端闭环（🔴 阻塞：真库无业务载荷）
  - 标 `[ ]*`：现算 M1 **2** 行（1 行 `NULL` + 1 行 AI 复核会话记录）· M9 **1** 行（`M9-2-detail-rows`，`remark` 为 `NULL`）· **M5 / M8 各 0 行**
  - 预置动作（不阻塞）：起草 per-entry contract 草案，字段映射只映 `remark`，`conclusion` 标不使用（全域 `conclusion` 非空现算 0）
  - BP-1 / BP-2 / BP-3 引用 foundation 的登记，不重复裁决
  - _Property: 不宣称通过_

- [x] 26. 本 spec 自检
  - 断言 `MC-x` 引用**只出现编号不出现复述**（扫本 spec 三文件）
  - 断言 entry 用 `entry_id` 全名、4 条无重无漏
  - 算术自检：sheets `11+10+11+9 = 41` 且 `41 + 51 + 10 = 102` · HTML 36 + OO 5 = 41 且 `36+44+9 = 89`、`5+7+1 = 13` · 公式格 `1228` 且 `1228+1534+175 = 2937` · MAP `35 = 33 + 2` 且 `35+43+6 = 84`、`2+9+0 = 11` · mount `7` 且 `7+10+2 = 19` · BP-6 `1+3 = 4` · BP-8 `1+2 = 3` · 补集 `4 + 1(M6) = 5`、`5+5 = 10`
  - 断言 `MB-P1 ~ MB-P30` 无缺号无重号；断言无 U+FFFD；断言「N 处」与列举项数相等
  - _Property: MB-P30_
