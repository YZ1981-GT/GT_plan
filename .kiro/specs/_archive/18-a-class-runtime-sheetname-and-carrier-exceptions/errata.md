# 勘误（errata）— A 类运行时册名与载体例外车道

> **append-only 审计轨迹**。本文件只登记对上游判据/归因的**再更正**，不回填修改任何
> 已交付或已归档的 spec 文件（项目铁律「历史档案不回填修改」）。每条勘误标注发现时间、
> 现算证据与影响面。

---

## E-1 · AC-46 的 BP-6 归因**再更正**：「没有 A3-8 这本册」是错的

**发现于**：任务 7（实证并更正 BP-6 归因）执行期。
**关联**：AC-15 · AC-46 · AH-P13 · Requirement 4。

### 原结论（已证伪）

本 spec 早期（随 foundation 一同裁定）把 BP-6 的真因写成：

> 「真因是 `backend/wp_templates/A` 下**根本没有** `A3-8` 开头的权威册 ⇒ 即使把
> sheet 名改成纯码也解析不到。」

对应的早期守卫用 `rglob("A3-8*")` 现算命中数来「坐实」这个结论。

### 为什么是错的（现算证据）

该合册**一直在磁盘上**：

```
backend/wp_templates/A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx   （436,152 B）
```

册内含 sheet `A3-8商誉减值测试` 与 `A3-8-1可收回金额测试`。

错误成因是一个 **glob 口径问题**：`rglob("A3-8*")` **锚定文件名开头**，而该合册真名以
`A3-7` 起头 ⇒ 该 pattern **恒 0 命中**，三条断言于是**恒绿**（空分母假绿），
「没有这本册」这个错结论就被固化成了守卫。现算对照：

| 口径 | 命中数 |
|---|---|
| `rglob("A3-8*")`（锚定开头） | **0** |
| `rglob("*A3-8*")`（包含） | **1**（即上面那本合册） |

### 真实归因（两层叠加 + 宿主层）

**解析层（第一步，现已修复）** 两层叠加：

- ① **前缀而非包含**：`_wp_code_filename_prefix_ok(合册名, "A3-8")` 为 `False`（真名以
  `A3-7` 起头），且 `_index.json` 给该册挂的 `wp_code` 是 `"A3"`；
- ② **A-only 子码正则** `_LEGACY_A_ONLY_SUB_CODE_RE = ^A\d+-\d+` 命中 ⇒ 走
  `find_template_file_any` 的「A 子码严格分支」，该分支两次同名前缀尝试都不中就
  `return None`，到不了通用链的「至」范围回退。

这两层由 spec
**`workpaper-sync-pure-static-lane-and-combined-workbook-resolution`**
通过新增 `_find_combined_workbook_declaring`（纯路径合册声明码解析）修复 —— 它插在
`find_template_file_any` A 子码分支的 `return None` **之前**，纯加法。现算：

```
find_template_file_any_unresolved("A3-8")
  → A3-7内部往来核对表、A3-8商誉减值测试.xlsx     （修复后）
```

**宿主层（第二步，已完成）**：宿主传的是**中文字面 sheet 名**
`A3-8商誉减值测试`（`template_ref.resolution_kind == 'literal_sheet_name'`、
`sheet_name_literal == 'A3-8商誉减值测试'`），而不是 wp_code。两步修复**顺序不可
颠倒**：须先确认册存在（已确认）、解析层通（已修），再把宿主的字面 sheet 名收敛到
纯码 —— 已在 `GtA38GoodwillImpairment.vue` 中将 `sheet-name="A3-8商誉减值测试"`
收敛为 `sheet-name="A3-8"`。

### 对守卫的影响

- `test_a38_template_is_on_disk_and_its_filename_declares_the_code`：断言合册**在磁盘上**
  且文件名字面声明码集合含 `A3-8`（≥2 码的合册），并显式校验 `rglob("A3-8*")==0` /
  `rglob("*A3-8*")==1` 两数现算，防止 glob 口径假绿复发。
- `test_other_codes_resolve_and_a38_now_resolves_too`：**双向变异证明重建**。
  - 方向②（修复后 / 生产态）：`A3-8` 解析到合册；
  - 方向①（故障注入）：**在被测函数的下一层注入故障** —— 用 `patch.object` 把
    `_find_combined_workbook_declaring` 临时置为恒返回 `None`，`A3-8` 回到 `None`。
    **不**替换被测生产函数本身（遵守铁律「守卫的故障注入不得替换被测生产函数本身」）。
  - 对照组 `A3-3` / `A5-1` / `A10-1` 在**两个方向下都**解析到各自真实册 ⇒ 证明合册解析
    逻辑是**加法**，没有顺带改掉别人的走向。

### 铁律遵守

AC-46 的本次再更正**只登记在本文件**；**不回填**归档/上游 spec
（`a-cycle-sync-foundation-and-first-canary` 等）的任何文件。

---

## E-2 · `sheet_name_literal == 'A3-8商誉减值测试'` 是 19 条 literal 里的唯一异形

**发现于**：任务 7。
**关联**：AC-15 · Requirement 4.4 · AH-P13。

全 slice 现算 **19** 条 `resolution_kind == 'literal_sheet_name'` 的 entry，其
`sheet_name_literal` 按「纯码」正则 `^[A-Z]+\d+(?:-\d+)*[A-Za-z]?$` 分流：

- 18 条为**纯 wp_code**（如 `A5-1` / `A10-1` 这类）；
- **唯一异形**：`xlsx/gt-a38-goodwill-impairment` 的 `A3-8商誉减值测试`
  —— **码 + 中文连写、无分隔符**，正是上面 E-1 的宿主层第二步已收敛的对象。

守卫 `test_a38_literal_is_the_unique_abnormal_among_19` **从 slice 现读派生**此结论
（遍历全 slice 收集 literal、按纯码正则分流、断言恰 1 条异形且归属 a38），
slice 新增/改动 literal 条目时判据随之变化，不固化过期结论。
