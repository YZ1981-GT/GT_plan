# 任务：公式推送附注铺开 · 批 D

> 顺序即依赖。依赖批 C 完成（章节映射基础设施 + Tier A note_rows）。

## 阶段 1：族 binding 框架

- [x] 1. 新建 `note_direct.py`：NoteDirectBinding 族 binding + `note_direct_for(code)` 工厂
  - 从 `wp_account_mapping.json` 读科目码
  - 损益类识别（首位 `6`）
  - `load_sources` / `workpaper_targets` / `apply` / `note_rows` / `entry_warnings`
  - 测试：15 例（协议校验/工厂实例化/注册表字符串形式/损益类识别/多科目）

- [x] 2. `note_rows()` 实现
  - 单科目：一行数据（label=科目名, ending=TB审定数, opening=TB年初数）
  - 损益类：ending=TB本期发生额, opening=上期发生额
  - 不生合计行（单科目无需合计）；多科目追加合计行
  - 测试：单科目 + 损益类 + 多科目合计 + 无数据（全零）+ TB 不可用

## 阶段 2：批量注册

- [x] 3. 现算目标科目精确清单
  - 57 个未注册主编码（D5/F1~F4/G1~G14/H2~H4/J1~J2/K2~K13/L1~L8/M1~M10/N1~N5）
  - 其中 13 个损益类（6 开头科目码）

- [x] 4. 注册表批量追加
  - `_REGISTRY` 追加 57 个科目（总数 20→77），全部 `get_binding` 成功
  - 修复预存校验失败：Tier A `tb_columns` 补 `本期发生额`（D4/H10/I6）
  - 修复 M3/N4 规则中 `section_by_template` 的 null soe（删除 null 键）

- [x] 5. 规则批量生成
  - 119 条规则已预存（底稿锚点 62 条 + 附注推送 57 条），非本轮生成
  - 176 条规则清单校验全部通过
  - NoteDirectBinding `derivations` 声明各科目的 `{code}_note_main` 派生名

## 阶段 3：验收

- [x] 6. 独占键 + 清册重生成
  - 独占键 113 个（`--check` 通过）
  - 清册 77 条（`--check` 通过）
  - 修复 `test_formula_push_e1_binding` 的 `load_rules` 调用和 derivation 断言

- [x] 7. 参数化集成测试
  - 57 科目实例化验证 + 57 科目规则存在验证（source+note）
  - 9 个代表性科目 note_rows 格式 + 取数口径验证
  - 共享章节测试（G2/G3 各写各的行）
  - 注册表总数守卫（≥77）+ 规则总数守卫（≥176）
  - 全套 141 passed（15 单元 + 126 集成）

- [x] 8. 收尾
  - 一次性探针脚本清理（5 个 `_dp_*` 文件已删）
  - tasks.md 更新
