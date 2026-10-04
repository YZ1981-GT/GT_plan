# Task 2 / 3 / 4 证据：红判据先行

**执行时间**：2026-09-27

## 交付的三个判据文件（另起文件的理由）

| 文件 | 覆盖 | 结果 |
|---|---|---|
| `backend/tests/workpaper_sync/test_g_foundation_p1_p3_fc_reinterpretation.py` | GF-P1 / P2 / P3 | **36 passed** |
| `backend/tests/workpaper_sync/test_g_foundation_p4_p8_p17_p18_red_baselines.py` | GF-P4 / P8 / P17 / P18 | **5 failed / 35 passed**（红基线，见下） |
| `backend/tests/workpaper_sync/test_g_foundation_p20_golden_digest_baseline.py` | GF-P20 | **6 passed** |

GF-P21 要求「新判据加在既有文件内，或有显式『为何另起文件』的证据」：
既有 `test_task49_g_cycle_migration.py`（3,147 行）属 **umbrella Task 49**（冻结 slice 的交付物），
本 spec 是其**下游实施 spec**、Property 编号自成一套（`GF-P{N}`）。混在一个文件里会让
「slice 冻结事实」与「下游实施判据」的基线分不清动了谁。F 循环已确立每 spec 独立判据文件的做法
（`test_f1_property1_5_entry_selectable.py` / `test_f2_p3_p4_p6_p9_p10_red_baselines.py` …），本轮照它。
上游守卫 / 变异脚本 / 51 KB 删除清册**均未被替换、未被改动**。

## 现状必红的 5 条（对应 Task 5/6/7/8 的转绿点）

```
FAILED TestGfP4Bp5G1SheetLabels::test_all_18_labels_hit_real_tabs          ← Task 5
FAILED TestGfP4Bp5G1SheetLabels::test_trailing_space_is_preserved_verbatim ← Task 5
FAILED TestGfP8BareIfNeutralization::test_all_13_store_merge_plans_declare_neutralization ← Task 6
FAILED TestGfP17PrefillSheetNames::test_every_block_sheet_exists_in_template ← Task 7
FAILED TestGfP18TbPublishGateGap::test_g6_main_wrong_account_comment_is_fixed ← Task 8
```

红的具体内容（pytest 原文摘要）：

1. **BP-5**：`G1_SHEET_LABEL_MAP` 5 条指向模板不存在的 sheet。
2. **BP-5 空格半条**：`G1A` 标签 `'交易性金融资产实质性程序表G1A'` 与模板真名
   `'交易性金融资产实质性程序表G1A '`（尾部空格）不逐字相等。
3. **GC-2**：17 个 G adapter 在 `STORE_MERGE_REGISTRY` 里**一个都没有**（G 循环零 provider）。
4. **GC-8**：prefill 块 `[169]` / `[170]` 指向不存在的 sheet。
5. **GC-9**：`useG6MainAdjudication.ts` 那条「已纠正为 1505」的错注释仍在
   （1505 在 `KNOWN_BAD_CODES['G6']` 里）。

## 🔴 GF-P1 现算推翻了 spec 的一条裁决：FC-8 在 G **适用**

spec `requirements.md` 写「OCR ✅ 全仓 **零命中** ⇒ FC-8 在 G 不适用」；
`design.md` §FC 适用性重裁写「FC-8 | 🔴 **不适用** | G 循环全仓零 OCR 命中」。

本轮按 **workpaper 域唯一的 OCR 写入端点字面量** `d4/contract-ocr` 现算，
G 循环（除 G0/G7）实测 **10 个写入站点**：

| 文件 | entry |
|---|---|
| `g1-trading-financial-assets/inspection/G1TabSecuritiesCount.vue` | G1 |
| `g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue` | G1 |
| `g2-interest-receivable/G2TabVoucherCheck.vue` | **G2（canary）** |
| `g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue` | G4 |
| `composables/useG6EclVoucherCheck.ts` | G6 |
| `components/workpaper/composables/useG8VoucherCheck.ts` | G8 |
| `g8-other-equity-instruments/voucher/G8TabVoucherCheck.vue` | G8 |
| `g9-other-noncurrent-financial/voucher/G9TabVoucherCheck.vue` | G9 |
| `g10-trading-financial-liabilities/voucher/G10TabVoucherCheck.vue` | G10 |
| `g12-net-hedge-gains/voucher/G12TabVoucherCheck.vue` | G12 |

`useG6EclVoucherCheck.ts#L600` 逐字确认是真实写入方，不是标签字符串：

```ts
const response = await http.post(`/api/workpapers/${wpId.value}/d4/contract-ocr`, body, {...})
...
Object.assign(row, patch)          // ← 写行字段
row.attachment = file.name
row.attachmentId = attachmentId
```

**原判为何会错**：那次只扫了顶层 `GtG*.vue` / `useG*.ts`，而 OCR 站点在
子目录 tab 组件与 `src/composables/useG6EclVoucherCheck.ts`（不在
`components/workpaper/composables/` 下）。

### 重裁结论（不是「不适用」，是「适用且当前不冲突」）

**FC-8 在 G 适用，但对本批受管区无第二写入方** —— 10 个 OCR 写入方的 store 键全部落在
**非受管 sheet**（凭证检查表 / 监盘表）上。canary G2 逐值实证：

| 侧 | store 键 | 来源 |
|---|---|---|
| 受管 | `G2-2-detail-rows` | `useG2Detail.ts:122` `STORAGE_KEY` |
| OCR | `G2-8-rows` / `G2-8-audit-note` / `G2-8-audit-conclusion` | `G2TabVoucherCheck.vue:693 / 818 / 819` |

⇒ 交集为空。判据 `test_fc8_ocr_targets_disjoint_from_managed_store_keys` 把这个「空交集」
锁成不变式：**将来任一 lane 把凭证检查表纳入受管，立刻打红**。

两种表述的判据形态完全不同 —— 「不适用」会让人删掉判据，「适用且不冲突」必须保留判据。
这正是 slice 原文警告的那类失配（「正则找不到 `api.get` 就当没有写入路径」）。

⇒ **三份 spec 的 FC-8 行须改写**（foundation requirements 现状表 + design §FC 重裁表；
两份 lane spec 引用 foundation 故自动跟随）。

## 其余现算修正（判据里已逐条锁住）

| 项 | spec 原文 | 实测 | 判据 |
|---|---|---|---|
| RG-4 裸 IF 数 | G1 141 / G4 186 / G5 122 … 标为「格」 | 那是 `findall` **出现次数**；**格数**为 G1 71 / G4 154 / G5 61（G7=1065 与生产模块 docstring 一字不差） | `test_occurrence_count_caliber_differs_from_cell_caliber` 锁住 2:1 关系 |
| BP-7 覆盖面 | 「只命中 G6-sppi 一条」 | 正文/`dynamic_row_identity` 只命中 G6-sppi；`blocked_by` 列了 **9 条** | 两条并存：`test_bp7_blocked_by_covers_nine_entries` + `test_bp7_actual_defect_surface_is_only_g6_sppi`（含严格包含关系断言） |
| BP-9 | GF-P3「BP-9 仅 G1」 | **不在任何 `blocked_by`**（其 `must_fix_before` 是 Task 72，不是受管前置） | `test_bp9_is_not_in_any_blocked_by` |
| BP-6 | 正文 17 条 | `blocked_by` 只标 5 条（G4-ecl / G5 / G6-main / G6-sppi / G6-ecl） | `test_bp6_marked_on_five_but_text_covers_all_17` 两面都锁 |
| G 块数正则 | — | `r"G(?:[1-9]|1[0-4])"` 的 `[1-9]` **含 7** ⇒ 必须显式排 G7，否则 47→51 | 判据注释已写明 |
| `PROVIDERS` 成员 | 「含 …(+g7/h1)」 | g7/h1 **不在**，f1 **在** | P20 改「非 G 逐项不减」，不断言大小 |

## GF-P2 两条「缺陷不存在」的判据形态

* 候选①「整册码回落打开错工作簿」：13 整册码 + 8 子码 × **三个解析入口**
  （`find_template_file` / `find_template_file_any` / `find_all_template_files`）逐一现算，
  全部解析到首段等于自身整册码的册子 ⇒ 不存在。
* 候选②「磁盘有、索引无的冗余合册」：磁盘 15 vs `_index.json` 的 G 项，**双向差集为空**；
  配一条自省变异（合成 `G99 合成冗余合册.xlsx`）证明差集算法真能抓到。

两条都**现算**，不读 slice 快照 —— 满足需求 1.4「现算而非读 slice 快照」。
