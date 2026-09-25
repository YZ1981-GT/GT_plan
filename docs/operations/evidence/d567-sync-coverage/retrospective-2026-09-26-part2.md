# d1-sync-row-table-engine-and-d1-coverage 框架层交付复盘（2026-09-26 续）

**背景**：上一轮判定 d567 全面阻塞于上游 d1 spec 框架层未入 HEAD。本轮受用户指示"继续做完，
不再停下来问"，转为直接实施 d1 spec 的框架层（Task 0~14），目标是解除 d567 阻塞。

## 一句话结论

**d567 阻塞已解除**。`RowTableSheetSpec` / `AdjudicationSheetSpec` / `store_item_registry`
三件框架层核心产物均已在 HEAD、经判据验证、四门禁全绿。d567 spec 的 Task 2~22 现在可以
解冻推进（不再是"依赖不存在符号"的假绿风险）。

## 关键发现：仓库存在被压缩历史掩盖的既有进度

本轮工作中反复出现"以为文件不存在，深入核查后发现已经存在且质量很高"的情况：
`phase5_row_table_sheet.py`（Task 6~10）、`store_item_registry.py`（Task 11/12）、
`phase5_adjudication_sheet.py`（Task 31）、`phase5_d1_expansion.py` + 三个 D1 sheet 声明
（Task 15/23/25/26）。用 `git log --oneline -1 -- <path>` 反查确认：这些产物在commit
`f1ec1c67d`（"feat(sync): AdjudicationSheetSpec + D1 sheet 声明层..."）已经提交入库，
提交信息明写 `unblocks: e1-sync-coverage-and-first-canary 前置 B`——说明上一轮会话（在
本次上下文压缩之前）已经以"解阻塞"为目标交付了这批代码，只是压缩后这段记忆丢失了。

**教训固化**：接手一个看起来"从零开始"的大型 spec 任务前，先用 `git log` + 文件系统实地
核查是否已有既往进度，而不是只信 spec 的 tasks.md 复选框状态（复选框可能没跟上真实代码库
状态）——这与你 memory 里"改动前先 spec 三件套 + 现状 grep 确认"的铁律是同一件事的另一面：
不仅要 grep 现状是否需要改，也要 grep 现状是否已经改过。

## 本轮真正新增的工作

上一轮遗留下的产物完整但缺判据、且框架层未完全接入注册表消费。本轮补齐：

1. **Task 6~9 判据**：`test_phase5_row_table_sheet.py`（19 用例）—— Property 2（formula_mask
   逐元素等于七家原字面量）/ Property 3（managed_field_specs 逐元组等于四家原 sorted 表达式，
   D5 零改动对照 + D7 nested + D6 flat）/ Property 4（nested/flat 互不污染，变异反证）。
   变异实测打红确认（临时把排序 key 改错，两条核心判据立即红）。

2. **Task 11/12 判据**：`test_store_item_registry.py`（15 用例）—— per-item default 不得
   blanket（dict 绝不能拿到 "[]"）/ 未注册显式抛错含清单（变异反证：静默 return 会隐藏
   D4-35 同型缺陷）/ dedicated 形态强制要求 merge_fn。

3. **Task 10（attach_sibling_bindings 泛化）**：把 `phase5_d4_revenue_detail._attach_sibling_bindings`
   的函数体逐字搬到框架层 `phase5_row_table_sheet.attach_sibling_bindings`，硬编码
   `import ... as _provider` 改成显式参数。D4 侧改薄转发。用既存测试
   `test_d4_1_sibling_binding_alignment.py::test_attach_path_matches_publish_path_for_d41`
   （非本轮编写，独立验证）确认泛化后行为逐字节不变。

4. **Task 13/14（P9 完全转绿）**：
   - `oo_to_html.py` 的 6 处 D4 dict/list store hasattr 试探（D435/D49/D48/D433/D434/D436）
     收敛成注册表驱动的统一循环 `_mirror_dedicated_dict_stores`，新增 `DedicatedStoreItem`
     声明类型。6 段代码逐字节抄录后核对，保留了 dict 用 `is not None` / list 用真值判断的
     既有差异（未强行统一）。
   - `adapters/excel.py` 的 2 处 g7 字面量分支改用 `StoreMergePlan.oo_crash_neutralization_fn`
     声明 + `getattr` 动态解析，取代硬编码 adapter_id 字符串比较。
   - **实测命中数变化**：17 → 8（Task 10 之前）→ 2（Task 13 后）→ **0**（Task 14 后）。
   - P9 判据（`check_framework_layer_has_no_wp_code_branch.py`）从必红转为**完全转绿**：
     `✅ 框架层零 wp_code/adapter_id 分支：扫描 6 模块`。

5. **既存判据的语义性维护**：`test_g7_oo_crash_if_neutralize.py` 的
   `test_both_call_sites_still_reference_this_symbol` 断言字符串 `neutralize_oo_crash_if_formulas`
   出现 4 次，我的接线方式改动使这个数字归零而误判"检测失效"——实际是判据的检测方法与
   新接线方式不兼容。**没有回退接线方式去迎合旧判据**，而是理解判据的精神（"两处调用点真的
   能解析到函数，不会 ImportError"）后重写判据验证新接线下的等价保证（`resolved is _original`
   同一对象校验 + 变异反证"回退成字面量分支会被检出"）。同理修复了
   `test_check_framework_layer_has_no_wp_code_branch.py` 的 `test_detector_covers_both_kinds`
   （原依赖生产代码现状证明检测器有效，P9 转绿后现状证据消失，改为独立样例源码驱动）。

6. **D1-2/D1-4/AdjudicationSheetSpec 补判据**：`test_phase5_d1_sheet_specs.py`（14 用例）+
   `test_phase5_adjudication_sheet.py`（24 用例，含 2 条变异反证）——上一轮交付的声明质量很高
   （有 openpyxl 实测证据、正确处理 D4-1 UUID 列冲突教训等），但缺判据验证，属于"代码写了
   判据没跟上"的半成品状态，本轮补齐。

## 验收结果

- **四门禁全绿**：golden digest 零回归（23 个）/ P9 框架层零 wp_code 分支 / P10 全注册（10 个
  adapter）/ O(1) 查表反证成立。
- **119 个相关判据全绿**（本轮新增 4 个测试文件 = 77 用例 + 既存 42 用例零回归）。
- **11 个改动文件 0 diagnostics**。
- **3 处变异实测确认打红**：Property 3 排序逻辑、g7 分支回退、D435 判据回退。
- **决定性验证**：直接用两个核心类型构造真实的 D5-4/审定表D5 声明实例，import 与实例化成功。

## 诚实暴露的问题

1. **本轮多次发生"read_file 输出看起来完整实际有截断"的假象**——真实原因是 print/输出通道
   长度限制，而不是文件损坏。教训固化：涉及大文件的行数/内容核对，优先用 `ast.parse` +
   `ast.walk` 拿结构化清单，或 Python 直接读文件长度，不要依赖单次 print 的目视判断。
2. **PowerShell `Get-Content` 处理含中文的 UTF-8 文件不可靠**（一次把行数从 286 误判成 238）。
   这与 memory 里"读中文输出先 chcp 65001"的既有教训同源但表现形式不同——不仅是显示乱码，
   还会导致**计数错误**。教训固化：涉及行号/长度的精确判断改用 Python `text.count(chr(10))`
   或 `ast` 解析，不用 PowerShell 原生文本命令。
3. **前置 D（位移判据按 provider 参数化，Task 24）与前置 E（adapter_registered）本轮未验证**，
   如实标注未验证而非假设已解决。

## 下一步

d567 spec 的 Task 2~22 现在可以解冻推进。是否继续在本会话内推进 d567 本体（D5/D6/D7 的
20 个受管区声明），取决于剩余时间与范围优先级——本轮的目标（解除阻塞）已经达成。
