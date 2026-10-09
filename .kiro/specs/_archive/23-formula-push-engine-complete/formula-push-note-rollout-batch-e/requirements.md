# 需求：公式推送批 E — 附注推送铺开

> 前置：批 C/D（审定表族）审定数据就绪。
> 交叉引用：`formula-push-all-subjects-rollout` design §六 6.3（附注写入通用化）、Task 7（已完成）。

## 1. 目标

将各底稿披露表数据推送到对应的附注章节。**核心约束：按准则变体隔离——上市版底稿的披露表数据只推上市版附注章节（五、N），国企版只推国企版章节（八、N）**。

## 2. 准则变体隔离机制

### 2.1 已有基础（E1 先例，Task 7 已实现）

- 规则 `target.section_by_template` 声明 `{"listed": "五、1", "soe": "八、1"}`
- 引擎 `_push_note` 按项目的 `template_type`（上市/国企）选择对应章节号
- `build_main_skeleton(template_type, section, table_name)` 按章节 + 表名从附注模板取行列
- `NOTE_FIELDS` 登记表 + `rule.target.fields` 声明要写的字段

### 2.2 铺开要做的

- 每个科目的附注规则须声明 `section_by_template`，章节号从 `*NoteSectionMap.ts`（前端唯一真源）提取
- 章节号与 `note_workpaper_sync_registry.json` 逐条对齐
- 附注表名从附注模板 JSON（`note_template_listed.json` / `note_template_soe.json`）取
- 每个科目的披露表行标签（`note_rows` 方法返回）从底稿渲染数据提取（`buildXSyncPayload` 同口径）

### 2.3 注意事项

- **上市版和国企版的行标签可能不同**（如 E1 上市多「存放财务公司款项」「存款应计利息」）
- **部分科目只有一侧有披露表**（如 H5 上市版无独立油气资产章节，`H5_DISCLOSURE_SHEET_LISTED = ''`）
- **同一科目上市/国企的章节号不同**（如 D1 → `{"listed": "五、4", "soe": "八、4"}`）
- **损益类科目（G13/G14/H10）部分变体走关键词章节**（`gen_note_wp_sync_registry.py` 的 `load_reverse_map` 补全逻辑）

## 3. 范围

| # | 需求 | 验收标准 |
|---|------|----------|
| E1 | 每科目附注规则声明 `section_by_template` | 章节号与 `*NoteSectionMap.ts` + `note_workpaper_sync_registry.json` 一致 |
| E2 | 行标签与前端 `buildXSyncPayload` 同口径 | 推送写入的行 = 前端同步写入的行（逐标签对拍） |
| E3 | 上市项目只推上市章节 | `template_type=listed` 时只查 `五、N` 章节 |
| E4 | 国企项目只推国企章节 | `template_type=soe` 时只查 `八、N` 章节 |
| E5 | 单侧缺章节的科目 | H5 上市无章节 → 跳过并说明；国企有章节 → 正常推 |
| E6 | 字段声明 | 每科目的 `target.fields` 按附注表结构声明（不是所有表都只有 `end_amount`/`prior_amount`，部分有 `current_amount`/`prior_amount`） |
| E7 | 骨架构建 | 缺表时按 `build_main_skeleton(template_type, section, table_name)` 建骨架（Task 7 机制） |
| E8 | 独占键 + 清册 | 附注规则不进独占集合（policy=editable）；清册 `has_note_rules` 更新 |
| E9 | 附注同步指纹 | 推送写入后 `_last_sync_wp_id` / `last_sync_source=formula_push` 正确；pull-from-workpapers 不重复拉取 |
| E10 | 附注 stale 与报表联动 | 推送写入附注后报表对应行标 stale；附注编辑器显示同步提示 |
| E11 | 多科目不互相覆盖 | 同一附注章节被多科目推送时各写各的行 |
| E12 | manual/locked 保护 | 附注 `_cell_modes` manual/locked 在铺开后仍保留（各科目参数化验证） |

## 4. 科目清单（按披露表存在性分组）

### 4.1 已有 `*NoteSectionMap.ts` 的科目（从 `noteDisclosureJump.ts` 提取）

D1~D7 / E1 / F1~F2 / G1~G14 / H1~H10 / I1~I6 / J1 / K1~K9 / K11/K13 / L1~L7 / M 循环 / N1~N5

### 4.2 铺开顺序

1. **canary = D1**（应收票据，五、4 / 八、4，结构简单：主表 + 受限表）
2. D2~D7（应收账款族，结构同 D1）
3. K1~K9（其他应收款族，K1 已有先例）
4. G1~G14（投资族，结构较复杂）
5. H1~H10（固定/无形资产族）
6. I1~I6、J1
7. L1~L7（筹资/债务族）
8. M 循环（权益族）
9. N1~N5（税费族）
10. F1~F2（存货族）

## 5. 不做

- 合并附注推送（consol disclosure，独立体系）
- 附注编辑器改造
- 附注模板维护
