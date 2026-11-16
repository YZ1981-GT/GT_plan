# Requirements — M 循环键名统一（前端驼峰 ↔ 契约下划线）

> **状态：占位 spec（2026-11-16 立项，未开工）**
> 来源：`oo-writeback-template-parity-closure` 任务 9.2 的键名层，用户 2026-11-16 拍板
> 「按 A」——投影层随原 spec 完成并归档，键名层另立本 spec 承接。

## 1. 背景与现算事实

原 spec 在任务 9.2 把「M 循环对不上」拆成了两层，本 spec 只承接第二层：

| 层 | 症状 | 归属 |
| --- | --- | --- |
| **投影层**（已修） | 即使键名对上了，整表 JSON 载荷的值也进不去投影 | 原 spec 已修（`phase5_m_cycle_common._build_store_projection` 加容器键展开；守卫 `test_m_detail_payload_projection.py` 6 例 + 2 条变异 RED） |
| **键名层**（本 spec） | 前端行模型是**驼峰**，契约是**下划线** | 本文 |

现算（2026-11-16，`backend/tests/test_m_detail_keys_match_provider.py` 的基线）：

- **M1**：provider-only 18 条 + frontend-only 19 条
- **M2**：provider-only 19 条 + frontend-only 9 条
- 合计 **65 条**差异，由该守卫冻结成**只许减小**的棘轮

根因不是「字段没接」，而是**同一张表两套存储形态并存**：

- 契约 `review.html_store.shape` 一律声明 **`flat_key_value`**（`item_id` 按 `{ITEM_PREFIX}{sheet}-{field}` 逐键），provider `row_identity_kind = template_row_key`；
- 前端明细表实际用**整表 JSON**（`M1-M1-2-full-data` / `M2-M2-2-listed-full-data` / `M3-M3-2-full-data` / `M7-2-full-data` / `M9-2-detail-rows` / `M10-2-full-data`，`useM{n}Detail.ts` 的 `debouncedSave(key, { remark: JSON.stringify(detailRows) })`）；
- 10/10 张表都另有 flat `getField(sheet, field)` 通路并存（M1/M3/M7/M9/M10 明确两种并存，其余 flat 为主但明细行仍整表存）。

## 2. 需求（待细化）

- **R1** 明确 M 循环的**唯一**存储形态：或统一到 `flat_key_value`，或按 sheet 分级声明（detail=row_array / determination=flat）。两条路径的代价与风险见 design §2。
- **R2** 键名单一来源：前端行模型键名与契约 `column_key` 必须能机械对拍（不是人工对照表）。现扫描器 `contract_field_names_scan.py` 已能识别「词干 × 后缀」拼键（L4-3 那类），但**识别不了** `{sheet}` 参数拼键（`g7SoeDisclosureModel.ts` 的 `MINORITY_FS_SLOT` 那类），见原 spec design §14.3 的备查记录。
- **R3** 存量数据迁移：若改契约则 canonical digest 变 ⇒ 已发布 representation 脱钩、须重发布；若改前端则动 10 个宿主的读写语义 + 导入导出列。
- **R4** 棘轮只许减小：`test_m_detail_keys_match_provider.py` 的 65 条基线逐条偿还，每偿还一条删一条；守卫须断言「已对齐却没删条目会红」（防空转）。
- **R5** 真实 OO 往返验证：按仓库纪律，改 M 循环读写语义必须在真实 OnlyOffice 上验双向（参照 `oo-writeback-template-parity-closure` 12.2 的 D1-3 做法：`page.frames()` 穿透 `frameEditor`、点「结构化视图」触发 `forceSave()`、裁决后核对发布文件）。

## 3. 不在本 spec 范围

- M 循环的**投影层**（已由原 spec 修完并归档）。
- 其他循环的同类形态冲突（G5-2 / G7 / D1-13 / D2-10 / F2-47 / F3-1 / F4-1 / K2-3 / N3 / N4 / N5）—— 原 spec 已逐条登记在 `contract_field_names_frontend_exceptions.json` 与 design §14.2 / §14.3，各自按需另立。

## 4. 开工前置

1. 现读 `backend/tests/test_m_detail_keys_match_provider.py` 的当前基线（棘轮可能已被其他会话改动）；
2. 现读 10 个 `useM{n}Detail.ts` 的存储形态（哪些 flat / 哪些整表 JSON / 哪些并存）；
3. 现读契约 `m*.json` 的 `review.html_store.shape` 与 `store_item_id`；
4. 用户拍板 R1 的路径（统一 flat vs 分级声明）后再写 design 与 tasks。
