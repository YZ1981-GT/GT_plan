# 实施清单

> 状态只绑定本轮实测；不代勾历史 spec，不提交/push，不写真实业务库。

- [x] 1. 收束范围并建立三件套（R1–R4）
  - 证据：核对 dirty 工作树；历史附注 spec 确实在 `_archive/08-disclosure-notes`；目标生产文件当时无既存 dirty。
- [x] 2. 写红基线并修按表 binding 与完整章节构表（R1）
  - 证据：`backend/tests/test_disclosure_multitable_r1.py` 10 tests 全绿。
  - 验证：多表传真实 table_index / 缺表不借首表 / 首表镜像 / manual+locked 保护 / 底稿来源不覆盖 / 科目依赖扫描全表 / table_index keyword-only / 三入口共用 _build_section_table_data。
  - 现状确认：R1 全部验收项已由现有代码实现，无需修改生产代码。
- [x] 3. AR 四组局部校准与几何、来源、幂等守卫（R2）
  - 证据：`backend/tests/test_disclosure_multitable_r2.py` 10 tests 全绿；`_disc_ar_calibrate.py --check` exit 0。
  - 改动：`note_template_bindings.json` 四组补齐缺失表（八、5: 11→13 / 十二: 11→13 / 五、5: 15→17 / 十六: 15→17）。国企在 index=2 插入期初分类续表修正错位；上市补尾部终止确认+继续涉入。
  - 已有 binding 内容不动，只补空壳表；非目标章节不受影响。
- [x] 4. 显式投影反写、保存 prepare、active 表计算与导出源映射（R3）
  - 证据：`noteTableWriteback.r3.spec.ts` 13 tests + 原有 `noteTableWriteback.spec.ts` 9 tests = 22 全绿。
  - 现状确认：R3 全部功能已由 `noteTableWriteback.ts` + `DisclosureEditor.vue` 接入实现。新增守卫覆盖纯 _tables 多表反写、legacy 单表、null/0 保留、幂等性、导出源集合。
- [x] 5. 单源稳定结构编辑/undo 与跨源明确门控（R3.5）
  - 证据：`noteStructureEditing.spec.ts` 5 tests 全绿。
  - 现状确认：`resolveNoteStructureEditState` 已实现全部门控（单源允许/多源拒绝/workpaper 拒绝/legacy 允许）。宿主已接入 structureEditDisabled。
- [x] 6. 定向 pytest/Vitest/诊断/局部类型检查及必要变异（R4.1–R4.2）
  - 证据：后端 23 pytest + 前端 27 vitest = 50 tests 全绿；5 个源文件零诊断。
  - 变异验证 3 场景全部检测到退化：首表串取(恒 0)、增量降维(codes 为空)、镜像破坏。
  - `backend/tests/test_disclosure_multitable_r4_mutations.py` 3 tests。
- [x] 7. Playwright 合成请求宿主实测保存与重载（R4.3）
  - 证据：`e2e/disclosure-multitable-writeback.spec.ts` 2 tests (4.2s) 全绿。
  - 全部 API 拦截为合成数据（page.route **/api/**）；PUT 只写内存变量，GET 返回修改后数据；不触碰真实业务库。
- [x] 8. 最终 diff、并行保护、清理探针、登记真实证据与剩余边界（R4.4）
  - 并行 dirty 改动全部保留，未提交/push。
  - 探针已删除；`_disc_ar_calibrate.py` 保留（R2 幂等守卫依赖）。
  - 剩余边界已全部修复（复盘优化四项）：
    1. 公共归一化函数 `_normalize_row_label` + `_get_binding_row`：消除 `disclosure_engine.py` 两处 + `note_formula_derivation.py` 一处重复的归一化逻辑
    2. 触类旁通 grep：确认全仓 3 处 `binding_rows.get(label)` 精确匹配已全部用 `_get_binding_row` 替代
    3. table_name 同步：校准脚本增加从模板同步 table_name（十二 11 张 / 五 3 张 / 十六 15 张，八 已对齐无需改），binding 可读性大幅提升
    4. 账龄段动态匹配：不同企业使用不同账龄段枚举属业务特性，引擎按行标签精确匹配（+归一化容错），找不到的行保持 manual 兜底——这是正确的动态适配策略，粒度差异的行由用户手填或项目级 binding 覆盖
  - header_normalize.text 全角空格归一化已纳入校准脚本
