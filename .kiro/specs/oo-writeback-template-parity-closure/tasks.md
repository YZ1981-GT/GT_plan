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
  - [x] 6.1 修复脚本 `scripts/fix/fix_template_formula_defects.py`（`--check` / `--apply` / `--templates`，幂等，只允许清单内格变化）：19 本 285 格；守卫 `test_template_formula_defects_fixed.py`（含变异）
  - [x] 6.2 改过的模板（第一批 19 本）：provider 常量与审核依据、18 份契约、模板快照、预填定位表、slice、golden、变异锚点；全量回归对比由过转红 7 条（测试写死旧值）已改，子集复跑只剩基线既有红（design §9）
  - [ ] 6.3 对应前端改到与修正后模板一致：已做 D5-2 / F1-2 / H2-2 / G8-2 / D5-4 / D1-9；K3-2 前端无审定列；待做 D1-7、D6-3 / K1-3 小计、D4-27
  - [x] 6.4 【测试】项目无这些 entry 的发布产物，无可重发布；受影响真实项目 2 个 18 张底稿列于 design §2，待用户决定

- [ ] 7. 前端按模板对齐 D1~F5 登记项（R2.2，design §3.1）
  - [ ] 7.1 逐条核模板对错（错的并入任务 6），按模板改前端，每条配单测（已做贴现天数；核模板新发现 D1-15 / D2-9 / D7-6 / D7-1 四处模板错）
  - [ ] 7.2 变异：每条改回旧口径必须打红

- [ ] 8. 前端 ↔ 模板公式对拍守卫与 G~N 普查（R2.3 / R2.4）
  - [ ] 8.1 生成器 + `--check`；前端对拍测试 + 例外表（含无失效条目断言）
  - [ ] 8.2 首轮不一致项逐条记入 design §3.2 并处理（改前端 / 模板错并入任务 6 / 登记理由）
  - [ ] 8.3 变异：改一处前端公式、改一处生成 JSON，都必须打红

- [ ] 9. 字段名接通（R3，按 design §4 裁定）
  - [ ] 9.1 N 循环（N1~N5，含 N1 几何与 store item 前缀）
  - [ ] 9.2 L4-3 与 M 循环（含 `placeholder` store item）
  - [ ] 9.3 G5-2 / G6-5 / G7 / H 循环
  - [ ] 9.4 E1 / F2 / D 循环零散字段
  - [ ] 9.5 守卫 `test_contract_field_names_in_frontend.py` + 例外表只许减少；变异必须打红

- [x] 10. 删除死代码（R8）：`usePeriodAdjudication.ts` / `CycleTabAdjudication.vue` 零挂载（全前端无模板标签、无 import），连同只喂给它们的 `cycleAdjudicationConfigs.ts` 删除；6 份 G 复盘守卫里核这份配置的用例随之删除；`components.d.ts` 同步

- [ ] 11. 后端测试红清零（R9）：按任务 1.1 清单逐条修，根因写入 design §9

- [ ] 12. 验收（R10）
  - [ ] 12.1 前后端回归与改前 junit 逐条对比，新增失败 0
  - [ ] 12.2 浏览器实测【测试】项目：D5-2 双向改值、一张字段接通的表双向改值、公式格敲数字 → 保留服务器值 → 核对发布文件
  - [ ] 12.3 只提交本 spec 文件与改动块，干净 worktree 跑要提交的树，推送；登记 INDEX，更新 memory
