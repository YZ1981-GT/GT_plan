# 任务：在线编辑双向回写收尾

- [ ] 1. 基线与现算
  - [x] 1.1 完整检出 `wsr_head`（origin 213f19816）跑同步测试基线，junit 逐例落档；结果记入 design §9（802 失败 / 271 报错 / 15380 通过，530 组）
  - [ ] 1.2 字段名接通现算：疑似不通 594 个逐个核（动态拼键 / 别名），确定不通的表逐张写裁定，记入 design §4（R3.1）

- [ ] 2. 受保护字段统一（R7）
  - [x] 2.1 现读 G3-1 / G11-1 的 25 个 cross_sheet 格：模板全是引用明细表的公式；结论记入 design §5
  - [x] 2.2 `FieldValue.is_protected` 与 `merge._protection` 改读 `contracts.PROTECTED_MODES`，cross_sheet 按公式字段处理；`test_protected_mode_single_source.py`
  - [ ] 2.3 磁盘变异：任一处改回旧口径必须打红

- [ ] 3. 篡改裁决后公式还原（R4）
  - [x] 3.1 先写测试：真 D4 构造「公式格敲成数字 → 保留服务器值 → 物化」，改前红（实测是整次保存抛 `ProtectedRegionWriteError`，design §6）
  - [x] 3.2 `formula_restore.py`：按已发布形态签名在落点几何换回公式，值取合并结果；裁决选 OO 值不还原
  - [ ] 3.3 变异：去掉还原 / 还原到错行 / 选 OO 值也还原，三种都必须打红

- [x] 4. 转置表签名（R5）：实证五张转置表契约无公式字段，不需要证据（`test_transposed_tables_have_no_formula_fields` 钉住前提），design §7

- [ ] 5. 插行后签名（R6）
  - [x] 5.1 签名按受管表几何归一（`{r}` / `{start}` / `{end}` / `{end+k}` / `{r±k}`），design §8
  - [x] 5.2 测试：插行 / 删行后合计行、区间、表内他行引用签名不变；改写、指向新增行仍不同（`test_formula_signature_geometry.py`；D4-9 不能插行，端到端插行测试不做）
  - [ ] 5.3 变异：不做归一 / 偏一行，都必须打红

- [ ] 6. 模板公式修正（R1，清单 design §2）
  - [x] 6.1 修复脚本 `scripts/fix/fix_template_formula_defects.py`（`--check` / `--apply` / `--templates`，幂等，只允许清单内格变化）：三批共 26 本 383 格（#1~#32）；守卫 `test_template_formula_defects_fixed.py`（含变异）；第三批空格补公式带缓存值（`Fix.cached`）
  - [x] 6.2 改过的模板（第一批 19 本）：provider 常量与审核依据、18 份契约、模板快照、预填定位表、slice、golden、变异锚点；全量回归对比由过转红 7 条（测试写死旧值）已改，子集复跑只剩基线既有红（design §9）。第二批 6 本 43 格（#20~#28）同口径，6 份契约，全量回归由过转红 0 条。第三批 4 本 55 格（#29~#32）同口径，4 份契约（D2-2 H 改公式字段），回归见 design §9
  - [x] 6.3 对应前端改到与修正后模板一致：D5-2 / F1-2 / H2-2 / G8-2 / D5-4 / D1-9 / D1-7 / D1-15 / D2-9 / D1-4 / D2-3 / D6-3；K3-2 前端无审定列；K1-3 / D4-27 / D1-1 / D7-1 / D7-6 / G10-1 / G13-1 前端本就一致（design §3.1）。第三批：G9-2 报表数改审定 + 重分类，G14-2 / D6-8 / D2-2 前端本就按正确口径
  - [x] 6.4 第一批：【测试】项目无这些 entry 的发布产物；第二批：发布过 D2 的两个【测试】项目都已删除（在回收站，在线编辑打不开），重发布工具按可见性过滤找不到目标，无需重发布。受影响真实项目两批共列于 design §2，待用户决定

- [ ] 7. 前端按模板对齐 D1~F5 登记项（R2.2，design §3.1）
  - [x] 7.1 逐条核模板对错（错的并入任务 6 第二批），按模板改前端，每条配单测（`templateParityDBatch` / `templateParityFGBatch` 等）；D2-10 结构不同，并入 9.4；顺带修 F3 信用证类别崩溃（HEAD 既有）
  - [ ] 7.2 变异：每条改回旧口径必须打红

- [x] 8. 前端 ↔ 模板公式对拍守卫与 G~N 普查（R2.3 / R2.4）
  - [x] 8.1 生成器 + `--check`（后端守卫 `test_template_formula_parity_manifest.py` 11 例）；前端 `templateFormulaParity.spec.ts`（50 个 store item 适配器，63 例）+ 例外表（未覆盖 25、逐字段 5，全部 R3，只许减少、失效即红）
  - [x] 8.2 不一致项逐条记入 design §3.2 并处理：模板错 4 处并入任务 6 第三批（#29~#32）；改前端 L1-2 / L5-2 / L6-2（含两张附注取数）/ G1-2 / G9-2 / F2-6 单价，以及守卫首轮抓到的 G13 / G14 核对按分、G14 转回不改号、H2 期初调整反推只限旧行、D1-15 载入不截断、D1-9 / D5-4 日期倒挂出负数；L8-2 合计 / 派生行 / 占比按模板改（读模板逐格核出，守卫看不到跨行公式）；F3-4 口径待用户确认，其余登记 R3
  - [x] 8.3 变异：前端公式、前端改写录入、清单表达式、不生效例外、未覆盖清单冲突与 G13 / G14 / H2 / D5-4 四处改回旧口径，9 条全红、逐字节复原；L8-2 另 6 条变异全红

- [ ] 9. 字段名接通（R3，按 design §4 裁定）
  - [ ] 9.1 N 循环（N1~N5，含 N1 几何与 store item 前缀）
  - [ ] 9.2 L4-3 与 M 循环（含 `placeholder` store item）
  - [ ] 9.3 G5-2 / G6-5 / G7 / H 循环
    - [x] 9.3a 批 B1：G6-5 全表按前端 `FairValueItem` 改名、D 改 auto_source、前端旧数据反推只在键缺失时做（显式 0 单测）；G4-7 证券名称改名、E 总计 auto_source；G11-2 A 序号 auto_source + 幽灵行锚点改 B；H4-2 J / M auto_source；新守卫 `test_ghost_row_anchor_not_protected.py`（全仓锚点不得受保护，F3-1 种子区可伪证例外）；对拍适配器 +1、未覆盖 14 → 13、例外 4 → 1（design §4.5）。G6-5 store 门面与 `{rows, conclusion}` 载荷未接（批 B3），G5-2 / G7 / H 其余未做
  - [ ] 9.4 E1 / F2 / D 循环零散字段
    - [x] 9.4a F2-25 / F2-26 / F2-48 / F2-57 按模板表头接前端字段，F2-48 / F2-57 dict store 走 state 合并；回写合并只合本表的键（平台，8 家串表 + G9 / L5 落错区），守卫 `test_store_merge_table_isolation.py` 与三条磁盘变异；对拍适配器 +5、未覆盖 25 → 20（design §4.1）
    - [x] 9.4b E1-2 / E1-4、D3-rp、D6-3（两区）、D7-4 贷方区按模板接前端字段（D7-4 前端补「与对方科目核对」等三列、导入导出带新列）；触类旁通修后端复算口径四处（D6-2 / D6-3 / D7-2 导入、D1 附注推送）；守卫 `test_d6_03_dual_zone_spec.py` / `test_d7_4_analysis_counter_check.py` / `test_period_end_from_prior_unadjusted_backend.py` / `d7AnalysisTemplateColumns.spec.ts`，14 条磁盘变异全红；对拍适配器 +3、未覆盖 20 → 16、例外 5 → 3（design §4.2）
    - [x] 9.4c D3-4 两区（行身份 rowKey、区② 按 R20 接 counterCheck / remark，表单与导入导出补列）、F3-4、F4-1 性质区按模板接前端字段；F3-1 两区、F4-1 账龄两区只改 json 键（store item 与区判据留批 B）；对拍生成器支持百分点列；守卫 `test_d3_4_analysis_counter_check.py` / `d3AnalysisTemplateColumns.spec.ts`；对拍适配器 +2、未覆盖 16 → 14、例外 3 → 4（新增 F3-4 计息口径，待用户裁决）（design §4.3）
    - [x] 9.4d 批 B1：D3 长期挂账、F4-2（6 列 + 未审账龄组前缀 agingCurrent）按前端改 json 键；字段名登记 50 / 473 → 46 / 445；5 条磁盘变异各自打红（与 9.3a 同批，design §4.5）。剩余：D2-6 / D2-11 / D2-12 / D2-13、D1-8 转让区、K2~K7 分录列（批 B2b / B2c）
    - [x] 9.4e 批 B2a：D7-7 两区按模板重排（原整表错位）、期后结转区按模板改借方（前端迁移旧行、表单补 对方明细科目 / 支持性文件 / 核对内容 1~5 / 索引号 / 备注说明、导入导出改列）；D6-6 区② 改贷方 + 支持性文件；D6-5 按模板 12 列（前端补「发生原因（款项性质）」）；D3-7 改前端键、核对内容接 checkItems/0..4；行表引擎修 percent_points 回写 ×100 从未生效（枚举 str() 比较恒假），新增行内数组缺省形态与勾选列未勾留空（`phase5_row_value_codec`）；守卫 `test_check_table_headers_match_template.py` / `test_phase5_row_value_codec.py` / `test_d6_d7_check_tables_import_export.py` / `dCheckTablesTemplateColumns.spec.ts`；字段名登记 46 / 445 → 42 / 415；D1-13 区② 登记为 R2 待裁（design §4.6）
    - [x] 9.4f 批 B2b：D2-6（J 改接 transactionType、L 改接 indexRef，前端补 发生时间及账龄 / 期后回款 / 索引号，「从 D2-2 导入」期末按 F = C + D − E 算）、D2-11（转回区 G 改接 auditorComment，前端补五列 + 索引号，附注带入随之带列）、D2-12（B 期末余额原与质押金额同接 pledgeAmount ⇒ 改接 endBalance，前端补三列）、D2-13（前端补 具体依据 / 索引号）、D1-8 背书表（前端补 前手 / 背书转让单位 / 背书转让日期 / 说明，备查簿导入映射，D1-8T 导入导出按模板列）；守卫 `test_contract_no_duplicate_field_binding.py` / `test_d1_d2_inspection_import_export_columns.py` / `d1d2InspectionTemplateColumns.spec.ts`，表头守卫补 D1-8 与 D2 五个区；字段名登记 42 / 415 → 36 / 404；14 条磁盘变异全红；和平药房 2025 的 D2 检查工作簿待重发布（design §4.7）
  - [x] 9.5 守卫 `test_contract_field_names_in_frontend.py`（现算模块 `contract_field_names_scan.py`）+ 例外登记 `data/contract_field_names_frontend_exceptions.json`（50 组 / 473 个字段名，逐组理由，只许减少）；5 条磁盘变异各自打红（design §4.4）

- [x] 10. 删除死代码（R8）：`usePeriodAdjudication.ts` / `CycleTabAdjudication.vue` 零挂载（全前端无模板标签、无 import），连同只喂给它们的 `cycleAdjudicationConfigs.ts` 删除；6 份 G 复盘守卫里核这份配置的用例随之删除；`components.d.ts` 同步

- [ ] 11. 后端测试红清零（R9）：按任务 1.1 清单逐条修，根因写入 design §9

- [ ] 12. 验收（R10）
  - [ ] 12.1 前后端回归与改前 junit 逐条对比，新增失败 0
  - [ ] 12.2 浏览器实测【测试】项目：D5-2 双向改值、一张字段接通的表双向改值、公式格敲数字 → 保留服务器值 → 核对发布文件
  - [ ] 12.3 只提交本 spec 文件与改动块，干净 worktree 跑要提交的树，推送；登记 INDEX，更新 memory
