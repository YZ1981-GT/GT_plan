# 任务：统一合并附注模板与单体附注模板的表头格式

> 可与批 C/D/E 并行，不依赖附注推送规则。

## 阶段 1：模板层

- [x] 1. `seed_consol_note_sections.py` 加 `_column_groups` 推导
  - `multi_header_to_column_groups()` 纯函数（含 span=1）
  - 重生成两版合并附注模板（soe 4/4, listed 13/13 multi_header 表均有 _column_groups）
  - `--check` 幂等
  - 测试：7 个纯函数 + 4 个模板 JSON 验证 = 11 passed

- [x] 2. 现算 `_column_groups` 覆盖情况
  - soe：4 张 multi_header 表，4 张有 _column_groups（五-5-1/五-5-2/五-9-6/五-57-2）
  - listed：13 张 multi_header 表，13 张有 _column_groups
  - 无 multi_header 的保持 null

## 阶段 2：后端消费

- [x] 3. `consol_note_formula_service.value_column()` 改进
  - 新增可选 `column_groups` 参数，优先按 `_column_groups` 分组名定位（路径 A）
  - 降级到 `headers` 匹配（路径 B）
  - `plan_seed` 两处调用传入 `table.get("_column_groups")`
  - 测试：7 个新增 value_column 测试 + 22 既有全绿

- [x] 4. `refresh_note_by_formula` 按列 key 取数（可选）
  - 无代码改动需要：fill_rows 用种子注册时的 col_index，Task 3 改进后 col_index 正确
  - 已有 dict 行兼容（_row_to_list + _apply_to_dict_row）
  - 既有 22 测试覆盖向后兼容

## 阶段 3：前端渲染

- [x] 5. ConsolNoteTab.vue 渲染优先级调整
  - 后端 `get_section_detail` 返回 `_column_groups` 字段
  - 前端 `selectedNoteSection` 存储 `columnGroups`
  - `parsedMultiHeader` 路径 A：`_column_groups` → 分组表头（与 DisclosureEditor 同逻辑）
  - 路径 B（降级）：`multi_header` → P0 的 `parsedMultiHeader` 解析
  - 路径 C（兜底）：扁平 `headers`
  - getDiagnostics 无错误

## 阶段 4：公式种子验证

- [x] 6. 验证 3 张 multi_header 表的公式种子
  - 关键修复：span=1 分组不应排除（与单体模板一致，那里有 4 个 span=1 分组）
  - 五-5-1 应收账款账龄表：新增种子 `REPORT('BS-006')` 合计行
  - soe `report_total` 基线 45→46（SEED_COUNTS 已更新）
  - 40 测试全绿（18 新增 + 22 既有）

- [x] 7. 回归与收尾
  - 40 测试全绿
  - INDEX.md 更新
