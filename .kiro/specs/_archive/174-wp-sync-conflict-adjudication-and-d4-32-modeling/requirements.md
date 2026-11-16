# 需求：同步冲突可裁决化 + D4-32 资金流水建模修正

## 背景

承接 `workpaper-writeback-data-loss-and-mirror-consistency-closure` 的 6.3 / 6.4 / 6.5。
那三项原记「待写入型【测试】项目验收」，2026-11-05 在候选环境（3032 / 9981 + 真实
OnlyOffice 容器 + 共享库）实测后判明：**不是待环境，是现在没有任何路径可通**。

在【测试】公式同步乙有限公司_2025 的 D4（`d7fa0522-12b3-4e43-b7d4-5242562e6fd3`，entry
`xlsx/gt-d4-operating-revenue`）上，首版已正式发布、HTML→OO 单向已实测通过（`B16=202`
进入 OnlyOffice）；在 OO 内改成 303 并 forcesave 后，`oo_to_html` operation
`11809f53-a34e-44fc-8182-efc5bc68e019` 落 `state=conflict` / `conflict_count=24`，303
回不到 HTML，且**人工裁决这条路在产品上也走不通**。

两个缺陷叠加，必须一起修 —— 只修任一个都不足以让 OO→HTML 回写可用：

* **D4-32 建模三面皆错** ⇒ 该 entry 每次 OO→HTML 保存恒产 24 条 schema 冲突；
* **平台级：schema 冲突一律无法人工裁决** ⇒ 冲突产生后无出口，对任何 entry 都成立。

逐条代码位置、openpyxl 逐格实测与算术对应关系见本 spec 的 `design.md` §1 / §2，
以及上游 spec 的 6.6 / 6.7 登记。本文件只定「要达成什么」与「怎么算通过」。

## Requirements

### Requirement 1：schema 冲突的可裁决性由单一判据决定

1. WHEN merge 产出一条 `schema` 冲突 THEN 它的 `schema_anomaly` 成因必须随冲突记录
   **持久化**；落库即丢失成因的行为不得保留。
2. WHEN 任何读侧（冲突 preview / 前端面板 / resolve 入口）需要回答「这条冲突能否靠选一侧
   或输入合并值收敛」THEN 结论必须来自**同一个**判据实现；不得存在第二份按
   `kind is schema` 一刀切的口径。
3. WHEN 一条 schema 冲突的成因是 `type_normalization_failure` 或
   `multi_location_divergence` THEN 它必须可被 `keep_current` / `take_incoming` /
   `manual` 裁决；WHEN 成因是行身份类异常 THEN 它必须仍然拒绝按值裁决并要求先修结构。
4. WHEN 历史冲突行没有登记成因（本次迁移之前落的行）THEN 读侧必须按「成因未知 ⇒ 不可按值
   裁决」fail closed，且该结论要与「所有 schema 冲突都不可裁决」在可观测层面**可区分**。
5. WHEN 同一条冲突同时给出 `suggested_action` 与 `adjudicable_by_value_choice` THEN 两者
   不得自相矛盾（例如建议 `manual_merge` 却声明不可按值裁决）。

### Requirement 2：冲突裁决在界面上真正可完成

1. WHEN 用户在冲突面板上对可裁决冲突提交裁决 THEN 请求必须携带服务端要求的全部乐观锁
   字段，且这些字段的值必须取自**正式读取面**，不得由前端编造。
2. WHEN 乐观锁字段缺失或取不到 THEN 必须 fail visible 并给出中文原因，不得静默补默认值。
3. WHEN 裁决成功 THEN 该 operation 必须离开 `conflict` 终态并把合并结果落到 HTML store；
   用户刷新后 HTML / API / 已发布 representation 三方一致。

### Requirement 3：D4-32 受管字段与权威模板一致

1. WHEN 契约声明 D4-32 的受管字段 THEN 每个字段的列、`value_type` 与 `header_text` 必须与
   权威模板 `D/D4 收入底稿.xlsx` 的 `客户、供应商等资金流水检查D4-32` 实际内容一致。
2. WHEN 模板某列是**模板自身的排版/序号内容**而非业务字段 THEN 它不得进入受管字段集；
   回写路径不得改写它。
3. WHEN HTML→OO 物化 D4-32 的业务行 THEN 模板序号列的既有内容不得被清空。

### Requirement 4：D4-32 六段分组载荷的双向保真

1. WHEN D4-32 的 HTML store 载荷是六段分组形态（含可选的未知组）THEN store-projection 必须
   成功产出逐行投影；不得因载荷形态判断错误而使整个 entry 的在线编辑不可用。
2. WHEN OO→HTML 回写 D4-32 THEN 合并结果必须保持分组结构、各行的分组归属、未知组的来源
   `groupLabel` 与行内未受管字段；不得把分组数组压平成行数组。
3. WHEN OO 侧出现 store 里没有的行身份 THEN 若该行是**模板骨架且仍是模板原值**，不得写进
   HTML store；若该行**带了用户内容**，必须进入 store 并落在显式的未映射分组里，由用户经
   既有人工映射出口认定归属，不得猜测归组、不得静默丢弃。
4. WHEN 分组归属无法确定 THEN 处置必须对用户可见，不得以「归到其他关联方」之类的默认值
   掩盖。

### Requirement 5：连带基线与产物同步，不留假绿

1. WHEN D4-32 受管字段集变化 THEN 契约必须经正式生成器重生成，definition 链必须经正式
   provisioning 重新发布，受影响底稿的 representation 必须重新发布。
2. WHEN 受管字段数变化使既有判据常数失效 THEN 这些常数必须**重新实测**后更新，并同步更新
   它们所依赖的理由叙述；不得只改数字而留下与新事实矛盾的注释。
3. WHEN 某处测试补偿是为掩盖本次所修缺陷而存在 THEN 该补偿必须退役，且退役后相关判据仍
   成立；不得让补偿与修复并存。

## Correctness Properties

### Property 1
**Validates: Requirements 1.1-1.5**
对任意 `SchemaAnomalyKind`，读侧 preview 与域内冲突记录对「能否按值裁决」给出相同结论；
把读侧改回按 `kind` 一刀切即可被判据证伪。

### Property 2
**Validates: Requirements 2.1-2.3**
对一条成因可裁决的 schema 冲突，经界面提交 `keep_current` 后 operation 离开 `conflict`，
且 HTML store 的最终内容等于合并结果。

### Property 3
**Validates: Requirements 3.1-3.3, 4.1-4.4**
对任意六段分组载荷（含空组、未知组、未受管字段、骨架行带/不带用户内容），
`store → projection → materialize → extract → merge → store` 往返后：分组结构、分组归属、
行身份、未受管字段与模板序号列逐项不变；骨架模板原值行不进 store；带用户内容的未知身份行
落未映射分组。

### Property 4
**Validates: Requirements 5.1-5.3**
契约与磁盘产物双向锁死；受管字段数、反读字段数等常数与现算值一致；退役补偿后相关判据仍绿。
