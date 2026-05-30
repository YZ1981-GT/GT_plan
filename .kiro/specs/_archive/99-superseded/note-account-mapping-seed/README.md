# 附注↔底稿映射数据补齐（档 2 小型 spec - 已完成）

## 背景

`global-linkage-bus` UAT #4（附注改→底稿 stale）+ #7（URI 覆盖 6 模块）阻塞于 `note_account_mappings` 表 0 行数据，依赖图缺失整个 NOTE 模块的连接边。

## 关键设计决策（V2 版重做）

**核心原则**（用户明确指出）：
- **合并版（consolidated）多家加总**，附注**不直接对应底稿**（不生成种子条目）
- **单体版（standalone）单家维度**，附注精确对应底稿（本 spec 唯一处理对象）

**编号方案**：种子用**稳定的业务名称**（如"应收账款"）作为 `note_section_code` 字段，**不存机械编号**（"五、N"/"八、N"）。运行时由 `LinkageGraphBuilder._from_note_account_mapping` 按 `disclosure_notes.section_title` 反查实际章节编号生成 NOTE URI。

理由：不同项目不同附注模板章节编号都不一样（合并版 SOE 用"五、3"，单体版 SOE 用"八、5"，listed 又是另一套）。机械编号会导致跨项目不通用。业务名称作单一真源 → 项目无关 → 一份种子打天下。

## 实施成果

✓ **`backend/data/note_account_mappings_seed.json`**：280 条种子（140 SOE_standalone + 140 listed_standalone）
- 来源：wp_account_mapping.json 的 D-N 类 + 手工补充
- 排除：A/B/C/S 循环（业务承接/控制测试/完成阶段，不对应附注）
- 清洗：去掉"审定表/明细表/分析表/分析程序/循环"后缀
- 过滤：业务名称含"测试/评价/控制/复核"等程序类关键词的跳过

✓ **`backend/scripts/seed_note_account_mappings.py`**：PG 加载脚本（幂等，支持 --reset）

✓ **`backend/app/services/linkage_graph_builder.py::_from_note_account_mapping`** 重构：
- 加载 `disclosure_notes.section_title → [note_section]` 索引（项目无关）
- 仅查询 `template_type IN ('soe_standalone', 'listed_standalone')`
- 按 section_title 反查实际章节编号生成精确 NOTE URI
- 项目无附注时仍生成业务名称占位 URI 以保持依赖图完整性

## 实测结果（陕西华氏 2025 — 单体版 SOE）

| 触发底稿 | 影响章节 | 实际命中 |
|---------|---------|---------|
| WP:D2 应收账款 | 八、5（项目注释）+ 十二、应收账款（母公司）| ✓ 全精确 |
| WP:H1 固定资产 | 八、22（项目注释）+ 四、固定资产（会计政策）| ✓ 全精确 |
| WP:E1 货币资金 | 八、1（项目注释）| ✓ 精确 |

依赖图统计：48,440 节点 / 38,891 边 / NOTE 模块 115 节点（之前 0 → 76 → 115）
6 模块全覆盖：WP / TB / REPORT / NOTE / ADJ / MAPPING ✓

## 已知缺口（转 TD）

- **TD-A**：listed（上市版）业务名称与 SOE 一致（资产/负债类），但实际 listed 章节命名可能差异未充分验证；需用真实 listed 项目跑一次
- **TD-B**：fetch_mode 全部默认 total，detail/category/change 类别需后续按章节精化
- **TD-C**：validation_role 默认 balance，宽表/交叉规则需后续配 NoteValidationEngine
- **TD-D**：合并版项目（多家加总）当前不在依赖图（仅单体版精确联动），如果未来要支持"合并附注↔合并 TB 联动"需独立 spec

## 验收

✓ `note_account_mappings` 表行数 = 280（≥ 100 目标达成）
✓ `disclosure_notes.section_title` 反查机制完整工作
✓ LinkageGraphBuilder NOTE 模块节点 ≥ 100（实际 115）
✓ UAT #4 通过：3 测试全精确命中真实业务对应章节
✓ UAT #7 通过：6 模块全齐
