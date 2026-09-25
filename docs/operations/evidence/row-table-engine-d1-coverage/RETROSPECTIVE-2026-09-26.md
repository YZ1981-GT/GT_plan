# 复盘：D1 行表引擎 + E1 canary 两 spec 实施（2026-09-26）

**spec**：`d1-sync-row-table-engine-and-d1-coverage`（20/35）+ `e1-sync-coverage-and-first-canary`（8/23）
**commit**：`fbb55eead` → `f1ec1c67d` → E1 批次
**测试**：459 passed（workpaper_sync 相关全量）· 4 个 CI 卡点全绿 · golden digest 23 个零回归

---

## 一、交付了什么

### 框架层（全平台唯一实现，零 wp_code 分支）

| 模块 | 内容 | 判据 |
|---|---|---|
| `sheet_geometry.py` | 收敛 `_snake` / `_col_index` 四份复制 | 3 用例（含逐字节等价） |
| `phase5_row_table_sheet.py` | `RowTableSheetSpec`（七家实测共性）+ `formula_mask` property + 形态谱系三维 + `AgingLayout` nested/flat + 投影合并引擎核心 | 20 用例（11 等价 + 9 核心） |
| `phase5_adjudication_sheet.py` | `AdjudicationSheetSpec` + `row_mode` 三形态 + `AdjudicationValueSource` 五来源 + 逐格 `cell_mask` | 10 用例 |
| `store_item_registry.py` | `StoreItemSpec` 四形态 + per-item default + `STORE_MERGE_REGISTRY` O(1) + 三态入口 | 6 用例 |

### 声明层（第 1 层，只有数据没有算法）

D1：`phase5_d1_02_category`（3 固定行）· `phase5_d1_03_customer`（已交付 sheet）·
`phase5_d1_04_bad_debt`（三区，含一个 static_region）
E1：`phase5_e1_monetary_fund`（provider 从零建）· `phase5_e1_02_cash_detail`（canary）·
`phase5_e1_04_digital`（最小行表）· `phase5_e1_11_commitment`（唯一 static_region）

### CI 门禁（4 道 + 2 个 job）

`check_sync_provider_golden_digest`（23 digest 零回归）·
`check_framework_layer_has_no_wp_code_branch`（17 处 → 0）·
`check_sheet_specs_fully_registered`（module_missing → 11 adapter）·
`check_sync_registry_lookup_is_o1`（dict 比 1.0 / 线性反证 600+ 倍）
→ 接入 `governance-checks.yml` 两个新 job（`row-table-engine-and-registry-guards` 10 steps
+ `e1-sync-coverage-guards` 5 steps）

---

## 二、判据真打红了什么（不是装饰）

这是本轮最有价值的部分 —— **判据打红了三次我自己的真实错误**：

### 1. D1-4 footer marker：目测终端输出 ≠ 实测

首版据终端渲染**目测**记成「两个全角空格」（`合计\u3000\u3000`）。按 codepoint 断言的判据打红后
实测为**一个半角空格**（`0x5408 0x8ba1 0x20`）。

> **教训**：终端把 `0x20` 与 `0x3000` 渲染成相似宽度 ⇒ 目测终端输出不算实测，
> marker 必须按 codepoint 断言。证据 JSON 已加 `probe_lesson` 字段固化此教训。

### 2. E1-11 store 键：搜索范围漏了 `.vue`

只在 `composables/useE1*.ts` 里 grep，找不到 `E1-account-commit-check-summary` 就以为键名错了。
实际该组件明写 **"No composable — directly uses allResponses"**，键在 `.vue` 宿主里。

> **教训**：「按值 grep」的**范围**也必须实证。E1 spec 的裁决 H8 把禁推演从键名扩展到形态，
> 但没覆盖「搜索范围」这一维 —— 本轮补上。

### 3. E1-2 行身份字段名：照 D 类推演会打挂整个 entry

D 类惯用 `rowId`，E1-2 实测是 **`id`**（`useE1CashDetail.ts:104/144/285`）。
若照抄会让 store-projection fail-closed 抛「缺稳定行身份」把**整个 entry 打挂** ——
D4-1 曾因 `rowKey`/`rowId` 之误踩过同款。

### 4. 自省变异真的复现了 spec 首版的错法（E1-P3）

spec Task 4 要求一条**自省变异**：把 `binding_kind` 判据改回公式数阈值。判据实现后确认：
E1-9/E1-10/E1-11 实测**各只 7 公式**，`< 10 ⇒ static_region` 会把三张**全部**误判，
而实证只有 E1-11 成立。这条判据能打红 spec 自己的历史错误，不是摆设。

---

## 三、实测推翻 / 补正 spec 六处

| # | spec 的说法 | 实测 | 后果 |
|---|---|---|---|
| 1 | D1-2 是「固定 2 + 动态行」混合 | **3 个固定票据种类行、零动态区** | 应按 D4-6 范式判稳定 key 固定行（`row_identity_key='key'`） |
| 2 | D1-4 第三区按动态行接入 | 在 **footer 之下** ⇒ `ExcelInstrumentationSpec` 强制 `footer_row > last_data_row`，构造即抛 | `static_region` 是唯一正解（有判据作硬证据） |
| 3 | 24 个 golden digest（8×3） | **23 个** —— B60 是 simple_checklist，无 `build_store_projection` 路径 | 脚本按能力自适应并如实记 `null`，不假造 |
| 4 | E1-2「键独立」（未提行身份） | 行身份是 `id` + 有不可删除固定行 `fixed-rmb` ⇒ **混合身份** | 同在 `id` 字段，无需拆区 |
| 5 | E1-11 键为 `E1-account-commit` + `-check-summary` | 另有 `E1-commit-audit-note` / `-audit-conclusion`，**前缀不同** | 按统一前缀推演会造出不存在的键 |
| 6 | E 循环 slice 含 `parent_duplicate_count` 等字段 | slice 的 `independent_entries` **不含**这些字段（那些值来自 umbrella 的 D 循环 slice 对照） | `parent_duplicate` 路线裁决的依据须改述 |

---

## 四、发现并显式化的既存缺陷

### `b60` / `g7` / `h1` 三家 provider 缺 merge 门面（既存，非本次引入）

`git show HEAD:` 逐个实测确认：

| provider | `STORE_ITEM_ID` | merge 函数 |
|---|---|---|
| `pilot_simple_checklist`（b60） | **无** | **无** |
| `pilot_g7_two_level_dynamic` | 有 | **无** `merge_projection_into_store_state` |
| `pilot_h1_grouped_dynamic` | 有 | **无** `merge_projection_into_store_rows` |

而原 `oo_to_html` 的 elif 链对它们写了 `bridge.STORE_ITEM_ID` /
`bridge.merge_projection_into_store_rows` ⇒ 那三个分支**一旦被执行就是 AttributeError → opaque 500**。

**处置**：注册表以 `mirror_unavailable_reason` 显式化（抛可归因的 domain 错误取代运行时
AttributeError）。修它们归各自 provider 的 spec —— 本 spec 只暴露不掩盖。

---

## 五、注册表化的一个关键设计教训

改 `oo_to_html` 时我先把「未命中 ⇒ 抛错」一刀切实现，结果**打挂 49 个判据**。

根因：`test_task26_oo_to_html_pg` 的 harness 用
`adapter_id = "xlsx/gt-d2-accounts-receivable"`（**entry_id 形态**）。原 `else: return` 覆盖了
两种截然不同的「查不到」：

* **形如 adapter_id 却未注册** ⇒ 真漏接（D4-35 恒空 / D4-13 写不进 OO 的根因形态）⇒ 必须打红
* **压根不是 adapter_id**（entry_id 等）⇒ 它本来就没有 store 计划 ⇒ 跳过是正确行为

**修法**：三态入口 `store_merge_plan_or_skip`（plan / None / 抛错）+ `looks_like_adapter_id`
形态判定。这比二态更贴合现实，且把「真漏接」从「本就不镜像」里精确切出来。

> **教训**：删「静默跳过」时必须先问清它覆盖了几种情形。一刀切换成 fail-closed 会把合法的
> 那部分也打死 —— 而 49 个判据同时红时，很容易误判成「既存失败」。
> 本轮靠 `git stash` 对照才没误判（stash 后 283 passed 全绿，证明是我改的）。

---

## 六、诚实的边界：什么没做完

### 卡 upstream_gap（平台级，不是本 spec 能解）

D1 与 E1 的 adapter **都未注册**（`legacy_fake_bidirectional` / `adapter_id=None`），
根因是 umbrella BP-61-1：`working_paper_sync_entry_state` / `working_paper_content_version` /
`working_paper_content_representation` 三表近空，**186 个 planned entry 一个都注册不上**。

⇒ 以下全部跑不起来，已如实标 `[ ]*`，**未以合成测试冒充真栈**：
整册 materialize + `verify_unmanaged_regions` · §9.6 三谓词 · Playwright 全盘 ·
三端点真实耗时（P13 的可离线部分 O(1) 查表已做）· E1-P16 OCR 禁用真栈验证。

### 未开工（有明确前置或属后续批次）

D1：阶段 3 的 D3/D6/D7/D5/D2 声明化（Tasks 16~19）· 阶段 6~8 的 D1-8/16/9/10/11/12/15/7/14/13/6
与 D1-1 审定表迁移（Tasks 24/27~30/32/33）
E1：Tasks 10~12（宿主接桥 + canary 验收 + e2e 骨架，依赖 Task 9）· 15~22（E1-6/7/8/9/10/3/1
接入 + E1-5 可行性核 + 变异真栈收口）

### 一个明确的自评：Task 15 未达标

spec 要求 D1 循环层 provider ≤150 行。实际：拆出了 `phase5_d1_03_customer.py` 薄声明与
`phase5_d1_expansion.py` 伴生模块，但 entry 主模块仍 **1059 行** —— 瘦身本体未做，
已标 `[ ]*` 而非假绿。

> 附带教训：追加扩容代码时被 pre-commit 的**文件行数门禁**挡住（1224 行 > 基线 1040 +5%），
> 门禁的措辞「打磨应让文件变小不变大」是对的 ⇒ 按它的建议抽了伴生模块，而不是提高 whitelist 基线。

---

## 七、给下一轮的具体建议

1. **先解 upstream_gap，六个循环一起受益**。D1/D3/D5/D6/D7/E1 卡在同一个供给缺口，
   在六个 spec 里各自重做发布链是纯浪费。归 umbrella Tasks 36/77。
2. **禁推演铁律再加一维：搜索范围**。本轮的 E1-11 教训证明「按值 grep」不够 ——
   还得问「grep 的是哪些文件」。建议写进各 spec 的实测纪律。
3. **marker / 键名类常量一律按 codepoint 断言**。终端渲染会骗人（0x20 vs 0x3000）。
4. **删「静默跳过」前先枚举它覆盖的情形**，并为每种给出显式处置（跳过 / 打红 / 降级），
   否则一刀切会连累合法路径。
5. **D1 Task 15 的 entry 瘦身可独立做**：已有 `phase5_d1_expansion.py` 的先例，
   把契约装配段（`_rows_table_payload` / `build_contract_payload` 等）再抽一个伴生模块即可。
