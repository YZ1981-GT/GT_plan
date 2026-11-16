# 任务：在线编辑双向回写收尾

- [x] 1. 基线与现算
  - [x] 1.1 完整检出 `wsr_head`（origin 213f19816）跑同步测试基线，junit 逐例落档；结果记入 design §9（802 失败 / 271 报错 / 15380 通过，530 组）
  - [x] 1.2 字段名接通现算：疑似不通 594 个逐个核（动态拼键 / 别名），确定不通的表逐张写裁定，记入 design §4（R3.1）。收口见 design §12.7：现算缺口 28 组 / 337 名与登记逐值相等、无未登记缺口，28 组理由逐条具体（累计从 50 组 / 473 名降到 28 / 337）

- [x] 2. 受保护字段统一（R7）（4 靶点 P1~P4 全 RED，design §12.2）
  - [x] 2.1 现读 G3-1 / G11-1 的 25 个 cross_sheet 格：模板全是引用明细表的公式；结论记入 design §5
  - [x] 2.2 `FieldValue.is_protected` 与 `merge._protection` 改读 `contracts.PROTECTED_MODES`，cross_sheet 按公式字段处理；`test_protected_mode_single_source.py`
  - [x] 2.3 磁盘变异：任一处改回旧口径必须打红（4 靶点 P1~P4 全 RED，design §12.2）

- [x] 3. 篡改裁决后公式还原（R4）（R1~R3 全 RED，design §12.3）
  - [x] 3.1 先写测试：真 D4 构造「公式格敲成数字 → 保留服务器值 → 物化」，改前红（实测是整次保存抛 `ProtectedRegionWriteError`，design §6）
  - [x] 3.2 `formula_restore.py`：按已发布形态签名在落点几何换回公式，值取合并结果；裁决选 OO 值不还原
  - [x] 3.3 变异：去掉还原 / 还原到错行 / 选 OO 值也还原，三种都必须打红（R1~R3 全 RED；第三条按真实语义落在「受保护格只允许 keep_current」的禁令上，design §12.3）

- [x] 4. 转置表签名（R5）：实证五张转置表契约无公式字段，不需要证据（`test_transposed_tables_have_no_formula_fields` 钉住前提），design §7

- [x] 5. 插行后签名（R6）（4 靶点 S1~S4 全 RED，design §12.4）
  - [x] 5.1 签名按受管表几何归一（`{r}` / `{start}` / `{end}` / `{end+k}` / `{r±k}`），design §8
  - [x] 5.2 测试：插行 / 删行后合计行、区间、表内他行引用签名不变；改写、指向新增行仍不同（`test_formula_signature_geometry.py`；D4-9 不能插行，端到端插行测试不做）
  - [x] 5.3 变异：不做归一 / 偏一行，都必须打红（4 靶点 S1~S4 全 RED；S3 首轮 WRONG-TEST 已订正靶点，design §12.4）

- [x] 6. 模板公式修正（R1，清单 design §2）（27 本 386 格四批已修，design §2）
  - [x] 6.1 修复脚本 `scripts/fix/fix_template_formula_defects.py`（`--check` / `--apply` / `--templates`，幂等，只允许清单内格变化）：三批共 26 本 383 格（#1~#32）；守卫 `test_template_formula_defects_fixed.py`（含变异）；第三批空格补公式带缓存值（`Fix.cached`）
  - [x] 6.2 改过的模板（第一批 19 本）：provider 常量与审核依据、18 份契约、模板快照、预填定位表、slice、golden、变异锚点；全量回归对比由过转红 7 条（测试写死旧值）已改，子集复跑只剩基线既有红（design §9）。第二批 6 本 43 格（#20~#28）同口径，6 份契约，全量回归由过转红 0 条。第三批 4 本 55 格（#29~#32）同口径，4 份契约（D2-2 H 改公式字段），回归见 design §9
  - [x] 6.3 对应前端改到与修正后模板一致：D5-2 / F1-2 / H2-2 / G8-2 / D5-4 / D1-9 / D1-7 / D1-15 / D2-9 / D1-4 / D2-3 / D6-3；K3-2 前端无审定列；K1-3 / D4-27 / D1-1 / D7-1 / D7-6 / G10-1 / G13-1 前端本就一致（design §3.1）。第三批：G9-2 报表数改审定 + 重分类，G14-2 / D6-8 / D2-2 前端本就按正确口径
  - [x] 6.4 第一批：【测试】项目无这些 entry 的发布产物；第二批：发布过 D2 的两个【测试】项目都已删除（在回收站，在线编辑打不开），重发布工具按可见性过滤找不到目标，无需重发布。受影响真实项目两批共列于 design §2，待用户决定
  - [x] 6.5 第四批 N5 三格（#33）：D11 小计区间、E12/H12 的 wp_code↔A1 同形错误按 37:1 / 28:1 反证修复；清单 27 本 386 格；模板哈希 / 契约 / 快照 / prev3 / N slice 更新；旧缺陷守卫翻成正确公式。和平药房_2025 N5 generation=1，按「只做【测试】项目」未重发布

- [x] 7. 前端按模板对齐 D1~F5 登记项（R2.2，design §3.1）（6 靶点 F1~F6 全 RED，design §12.5）
  - [x] 7.1 逐条核模板对错（错的并入任务 6 第二批），按模板改前端，每条配单测（`templateParityDBatch` / `templateParityFGBatch` 等）；D2-10 结构不同，并入 9.4；顺带修 F3 信用证类别崩溃（HEAD 既有）
  - [x] 7.2 变异：每条改回旧口径必须打红（6 靶点 F1~F6 全 RED，design §12.5）

- [x] 8. 前端 ↔ 模板公式对拍守卫与 G~N 普查（R2.3 / R2.4）
  - [x] 8.1 生成器 + `--check`（后端守卫 `test_template_formula_parity_manifest.py` 11 例）；前端 `templateFormulaParity.spec.ts`（50 个 store item 适配器，63 例）+ 例外表（未覆盖 25、逐字段 5，全部 R3，只许减少、失效即红）
  - [x] 8.2 不一致项逐条记入 design §3.2 并处理：模板错 4 处并入任务 6 第三批（#29~#32）；改前端 L1-2 / L5-2 / L6-2（含两张附注取数）/ G1-2 / G9-2 / F2-6 单价，以及守卫首轮抓到的 G13 / G14 核对按分、G14 转回不改号、H2 期初调整反推只限旧行、D1-15 载入不截断、D1-9 / D5-4 日期倒挂出负数；L8-2 合计 / 派生行 / 占比按模板改（读模板逐格核出，守卫看不到跨行公式）；F3-4 口径待用户确认，其余登记 R3
  - [x] 8.3 变异：前端公式、前端改写录入、清单表达式、不生效例外、未覆盖清单冲突与 G13 / G14 / H2 / D5-4 四处改回旧口径，9 条全红、逐字节复原；L8-2 另 6 条变异全红

- [ ] 9. 字段名接通（R3，按 design §4 裁定）
  - [x] 9.1 N 循环（N1~N5，含 N1 几何与 store item 前缀）（子项 9.1a~9.1c 全完成；父任务此前漏勾）
    - [x] 9.1a 批 C（v1.0.31）：N1 几何 29/31→40/42，N1/N2 store item 改 `-detail-rows`，N1/N2/N3 json key 改前端名，五条 N plan 与五份 reviewed 契约落地；field-name 31/388→30/365、UNCOVERED 13→12（明细见 design §4.10 附）
    - [x] 9.1b 复盘收口：三个 provider 补 re-export PAYLOAD_COLUMN（修「声明在 sheets 但运行时仍 remark」假绿）；N2 活导入导出统一 A:Q / `N2-2-detail-rows.conclusion`、补 H=beginRje 与 M=C+G+H、复核上下文按原始行重算 P，真库两键 0 行；N1 生产纯函数 + 对拍适配器；field-name 30/365→29/364；K/N 十一 plan 表驱动（1047→1019 行）；N1 三条磁盘变异 3/3 红；push 工具安全收口（design §4.10、§4.11）
    - [x] 9.1c 语义审查收口：修 N2 跨项目读写、错误表头按位置写、Infinity JSON、国企披露归零、导入后旧快照、N 域新测试/公式数棘轮，以及 push 远端标签 fail-open / 重试竞态 / 本地旧标签基线；定向后端 25、鉴权/挂载 43、前端 643 项通过，候选相对基线新增失败 0（design §4.10、§4.11）
  - [~] 9.2 L4-3 与 M 循环（含 `placeholder` store item）（L4-3 已闭合；M 循环**投影层已修**、键名层仍是形态冲突，见 design §14.1）
  ### 9.2 现算结论（2026-11-15）

**L4-3 已闭合（无需改生产代码）**：契约 `sheets[].tables[].fields[]` 38 个受管字段、provider `MANAGED_FIELD_SPECS_7`、前端 `useL4FinLiabRows.ts` 运行时键**三处逐字段 0 不一致**（column_key / 列标 / json 键 / mode / value_type / header_text 六项全等）；行身份 `rowId`、store item `L4-3-rows` 三处一致；端到端 `build_store_projection` 取到 38/38、`merge_projection_into_store_rows` 回写后行键集合与前端完全相等。
**真实缺陷在守卫扫描器**（不是字段没接）：`contract_field_names_scan.py` 原只做「逐字 + 标识符片段」匹配，认不出「词干 × 后缀」拼键（前端 `const L4_3_PAIR_STEMS = ['priorAje', …]` + `for (const unit of ['Qty','Amount'])` → `` `${stem}${unit}` ``），于是 L4-3 报 **27 条**假缺失——而这 27 个键**从不逐字出现**，全部靠拼键生成。已扩展扫描器为「逐字 ∪ 拼键」（只认源码里真有的三种拼法，不做「凡后缀是 Qty/Amount 就算」的泛化），清掉 exceptions 该组（29→**28** 组 / 364→**337** 名），L4-3 进「已接通正面清单」。影响面量化：扩后仅 L4-3 组变化（27→0），其余 **28 组逐值不变**（无误判成绿）。变异：词干改名需**两处同改**（rows `PAIR_STEMS` + tab `PAIR_LABELS`），单处改守卫照绿（首轮因此存活，已修正靶点并逐字节还原）。测试:守卫 11 + L4 注册 22 = **33 passed**；前端 l4FinLiabStableRowId 9 passed。
**M1~M10 现算为形态冲突，不是漏字段**（探针 `tmp_mcycle_audit/probe_m_contract_vs_frontend.py`，契约真实路径 `sheets[].tables[].fields[]`）：
- 契约 `review.html_store.shape` 一律声明 **`flat_key_value`**（`item_id` 按 `{ITEM_PREFIX}{sheet}-{field}` 逐键），provider `row_identity_kind = template_row_key`；`phase5_m_cycle_common.build_flat_store_projection` / `merge_flat_projection_into_store` / `store_item_id = {prefix}{sheet_key}` 全按此形态实现。
- 前端明细表实际用**整表 JSON**：`M1-M1-2-full-data` / `M2-M2-2-listed-full-data` / `M3-M3-2-full-data` / `M7-2-full-data` / `M9-2-detail-rows` / `M10-2-full-data`（`useM{n}Detail.ts` 的 `debouncedSave(key, { remark: JSON.stringify(detailRows) })`），**10/10 张表都另有 flat `getField(sheet, field)` 通路并存**（M1/M3/M7/M9/M10 明确两种并存，其余 flat 为主但明细行仍整表存）。
- 因此「前端缺字面字段 9~27 个」不是 UI 漏字段，而是**同一张表两套存储形态并存**：flat 键由 `getField` 运行时拼出（扫描器现在已能识别拼键，但这里拼的是 `{sheet}` 参数而非字段词干，仍判不出），整表 JSON 走另一条键。
- **不可顺手改**：改契约形态会改 canonical digest 让已发布 representation 脱钩（须重发布）；改前端存储会动 M1~M10 十个宿主的读写语义。两者都需要真实 OnlyOffice 往返验证，按本 spec 的纪律（标完成须生产代码+针对性测试+故障注入+浏览器实测）不在本批擅自实施。
- 🔴 **本批抓到的真实反例（已回退，留作纪律）**：曾按「模板 R/S/T 三列要有 UI」的推理给前端补 `endAging` / `docIndexRef`、给 M2 补 `beginAje` / `ajeIncrease` / `isVerified` / `verifyReportRef`——而 provider 声明的真名是 `aging` / `refIndex` / `priorAdjAje` / `currentAjeIncrease` / `verified` / `verificationRef`。**六个键全不一致**，写进去就是「前端写 A、后端读 B」的真缺陷，且相关单测（30 passed）照样全绿（那些用例不按 provider 现读键名）。已 `git checkout` 回退并删除中途生成的 `tsconfig._m123-region.json`。⇒ 再次确认：**M/N/G 域的字段名一律以 provider 声明为准现读，禁按中文表头反推英文键**；守卫应按 provider 现读而不是手写期望值。
- **建议裁决方向（供用户选）**：①承认「明细表整表 JSON + 审定表 flat 键」为 M 循环既定形态，把契约 `html_store.shape` 按 sheet 分级声明（detail=row_array / determination=flat），扫描器再补「`{sheet}` 参数拼键」识别；②统一收敛到 flat_key（须重发布）。任一路径都要在真实 OO 上验双向。
- ✅ **已落地棘轮守卫**（`backend/tests/test_m_detail_keys_match_provider.py`，8 例）：把 M1/M2 明细行「provider 有前端没有」与「前端有 provider 没有」两张差异表**冻结成只许减小的基线**（M1: 18/19 条，M2: 19/9 条），判据四条 —— ①provider-only 禁增 ②frontend-only 禁增（抓臆造键）③**基线自证**（已对齐却没删条目会红，防棘轮虚高藏进展）④总量单向棘轮。变异注入 `inventedBogusKey` **2/2 红**且精确点名该键，逐字节还原后 8 passed。这条守卫是「按表头反推英文键」这类缺陷的止损闸：实测 M1 前端 `beginBalance`/`declaredAmount`/`paidAmount`/`resolutionRef` 与 provider `aging`/`refIndex`/`priorAdjAje` 两套并存正是 M 循环形态冲突的量化证据。

  - [x] 9.3 G5-2 / G6-5 / G7 / H 循环（子项 9.3a / 9.3b 完成；G5-2 / G7 属 R2 结构差异按 design §14.2 / §14.3 保持登记；H 循环现算 misses=0，design §14.4）
    - [x] 9.3a 批 B1：G6-5 全表按前端 `FairValueItem` 改名、D 改 auto_source、前端旧数据反推只在键缺失时做（显式 0 单测）；G4-7 证券名称改名、E 总计 auto_source；G11-2 A 序号 auto_source + 幽灵行锚点改 B；H4-2 J / M auto_source；新守卫 `test_ghost_row_anchor_not_protected.py`（全仓锚点不得受保护，F3-1 种子区可伪证例外）；对拍适配器 +1、未覆盖 14 → 13、例外 4 → 1（design §4.5）。G6-5 store 门面与 `{rows, conclusion}` 载荷未接（批 B3），G5-2 / G7 / H 其余未做
    - [x] 9.3b 批 B3a：G1 / G3 / G4 / G5 / G6 多区 store 门面按 provider 绑定（`phase5_section_store_facade`，G9 的伴生门面改为薄绑定）、逐区穿线、G6-5 dict 外壳；载荷列按 provider 声明（`store_payload_columns`，回写镜像 / 出方向 / 采纳覆盖的快照 · 删除 · 回滚审计同一口径，remark 口径 SQL 逐字不变）；G4 / G6 单数 store item 改为受管的那一个，`KNOWN_UNWIRED` 15 → 13；G1 A 列「类别」改绑 investType（区归属不受管）；五份契约复核文字按实际改写；golden 门拒空投影、五家基线更新；AOS 判据改正面断言 + 合成对照；新守卫 `test_section_store_facade_and_payload_columns.py`；20 条磁盘变异全红；和平药房 2025 G1 / G3 / G4 / G6 与重药安徽 G5 待重发布（design §4.9）
  - [x] 9.4 E1 / F2 / D 循环零散字段（子项 9.4a~9.4g 全完成；父任务此前漏勾）
    - [x] 9.4a F2-25 / F2-26 / F2-48 / F2-57 按模板表头接前端字段，F2-48 / F2-57 dict store 走 state 合并；回写合并只合本表的键（平台，8 家串表 + G9 / L5 落错区），守卫 `test_store_merge_table_isolation.py` 与三条磁盘变异；对拍适配器 +5、未覆盖 25 → 20（design §4.1）
    - [x] 9.4b E1-2 / E1-4、D3-rp、D6-3（两区）、D7-4 贷方区按模板接前端字段（D7-4 前端补「与对方科目核对」等三列、导入导出带新列）；触类旁通修后端复算口径四处（D6-2 / D6-3 / D7-2 导入、D1 附注推送）；守卫 `test_d6_03_dual_zone_spec.py` / `test_d7_4_analysis_counter_check.py` / `test_period_end_from_prior_unadjusted_backend.py` / `d7AnalysisTemplateColumns.spec.ts`，14 条磁盘变异全红；对拍适配器 +3、未覆盖 20 → 16、例外 5 → 3（design §4.2）
    - [x] 9.4c D3-4 两区（行身份 rowKey、区② 按 R20 接 counterCheck / remark，表单与导入导出补列）、F3-4、F4-1 性质区按模板接前端字段；F3-1 两区、F4-1 账龄两区只改 json 键（store item 与区判据留批 B）；对拍生成器支持百分点列；守卫 `test_d3_4_analysis_counter_check.py` / `d3AnalysisTemplateColumns.spec.ts`；对拍适配器 +2、未覆盖 16 → 14、例外 3 → 4（新增 F3-4 计息口径，待用户裁决）（design §4.3）
    - [x] 9.4d 批 B1：D3 长期挂账、F4-2（6 列 + 未审账龄组前缀 agingCurrent）按前端改 json 键；字段名登记 50 / 473 → 46 / 445；5 条磁盘变异各自打红（与 9.3a 同批，design §4.5）。剩余：D2-6 / D2-11 / D2-12 / D2-13、D1-8 转让区、K2~K7 分录列（批 B2b / B2c）
    - [x] 9.4e 批 B2a：D7-7 两区按模板重排（原整表错位）、期后结转区按模板改借方（前端迁移旧行、表单补 对方明细科目 / 支持性文件 / 核对内容 1~5 / 索引号 / 备注说明、导入导出改列）；D6-6 区② 改贷方 + 支持性文件；D6-5 按模板 12 列（前端补「发生原因（款项性质）」）；D3-7 改前端键、核对内容接 checkItems/0..4；行表引擎修 percent_points 回写 ×100 从未生效（枚举 str() 比较恒假），新增行内数组缺省形态与勾选列未勾留空（`phase5_row_value_codec`）；守卫 `test_check_table_headers_match_template.py` / `test_phase5_row_value_codec.py` / `test_d6_d7_check_tables_import_export.py` / `dCheckTablesTemplateColumns.spec.ts`；字段名登记 46 / 445 → 42 / 415；D1-13 区② 登记为 R2 待裁（design §4.6）
    - [x] 9.4f 批 B2b：D2-6（J 改接 transactionType、L 改接 indexRef，前端补 发生时间及账龄 / 期后回款 / 索引号，「从 D2-2 导入」期末按 F = C + D − E 算）、D2-11（转回区 G 改接 auditorComment，前端补五列 + 索引号，附注带入随之带列）、D2-12（B 期末余额原与质押金额同接 pledgeAmount ⇒ 改接 endBalance，前端补三列）、D2-13（前端补 具体依据 / 索引号）、D1-8 背书表（前端补 前手 / 背书转让单位 / 背书转让日期 / 说明，备查簿导入映射，D1-8T 导入导出按模板列）；守卫 `test_contract_no_duplicate_field_binding.py` / `test_d1_d2_inspection_import_export_columns.py` / `d1d2InspectionTemplateColumns.spec.ts`，表头守卫补 D1-8 与 D2 五个区；字段名登记 42 / 415 → 36 / 404；14 条磁盘变异全红；和平药房 2025 的 D2 检查工作簿待重发布（design §4.7）
    - [x] 9.4g 批 B2c：K3 ~ K7 调整分录汇总按模板补 类别 / 报表项目 / 附注项目 / 索引（K5 另补备注、G / H 改接前端 debit / credit、合计按列 prop 认；K7「类别」列原放 AJE / RJE，另起「类型」列），类别按类型给缺省、改类型时缺省值跟随（`kAdjTemplateFields.ts`），列序前段 = 模板；导入导出补列登记 optional_headers（旧版文件照常导入、缺列不写键）；K 生成器补登 K2 / K4 / K5 / K7，新守卫跑全部 38 个 phase5 生成器校验模式；K2 载入保留模板列（结构差异 R2 待裁）；守卫 `test_k_adjustment_template_columns.py` / `test_phase5_contract_generators_check.py` / `kAdjTemplateColumns.spec.ts`；字段名登记 36 / 404 → 31 / 388；18 条磁盘变异全红；和平药房 2025 的 K5 待重发布（design §4.8）
  - [x] 9.5 守卫 `test_contract_field_names_in_frontend.py`（现算模块 `contract_field_names_scan.py`）+ 例外登记 `data/contract_field_names_frontend_exceptions.json`（50 组 / 473 个字段名，逐组理由，只许减少）；5 条磁盘变异各自打红（design §4.4）

- [x] 10. 删除死代码（R8）：`usePeriodAdjudication.ts` / `CycleTabAdjudication.vue` 零挂载（全前端无模板标签、无 import），连同只喂给它们的 `cycleAdjudicationConfigs.ts` 删除；6 份 G 复盘守卫里核这份配置的用例随之删除；`components.d.ts` 同步

- [x] 11. 后端测试红清零（R9）：按任务 1.1 清单逐条修，根因写入 design §9。本轮收口见 design §12.6 / §12.8：修好 6 条归档后证据路径失效 + 4 条（3 xfailed + 1 xpassed）F3 item 数过期；本 spec 触碰的 7 个测试文件 144 passed / 0 failed。全量 1759 条共存红逐类登记（归档证据缺失 / lane 锚点漂移 / 真库快照 / 并发会话 manifest 面），不归因本 spec

- [ ] 12. 验收（R10）
  - [x] 12.1 前后端回归与改前 junit 逐条对比，新增失败 0（候选 vs 干净 HEAD 工作树逐节点对比：共存红 1759 / 修复 15 / 新增 10，10 条逐条归因为并发会话区域且已给对照证据；本 spec 改动面 0 新增，design §12.8）
  - [~] 12.2 浏览器实测【测试】项目：D5-2 双向改值、一张字段接通的表双向改值、公式格敲数字 → 保留服务器值 → 核对发布文件（前两项通过：D5-2 期末审定 1650 = 期末未审 1500 + AJE 100 + RJE 50，刷新后不变、落库逐值一致；D6-3 期初AJE=200 时期末未审 1250（新口径）而非 1450（旧口径）。第三项未完成：D5-2 / D6-3 / F3-4 无已发布产物；D1-2 已真实打开 OnlyOffice，但 OO 在 localhost:8080 跨域 iframe 内无法脚本操作、保存只能由 DocServer 自己回调 ⇒ 需人工在 OO 界面操作，如实标注未验证。design §13.4）
  - [x] 12.3 只提交本 spec 文件与改动块，干净 worktree 跑要提交的树，推送；登记 INDEX，更新 memory（干净 worktree 候选树 324 passed / 1 xfailed / 0 failed；INDEX 用私有 blob 只提交本 spec 那一行，并发会话对其他行的改动留在工作区；推送 v1.0.237 / 57fe1768e，主工作区已前移、本 spec 路径零残留。memory 更新见下条）
