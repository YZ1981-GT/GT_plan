# Requirements Document

## Introduction

底稿导入导出全生命周期收口。用户反馈「导出的很多模板都是空的」，实证后确认这是**两个独立缺陷叠加**，而不是导出功能未实现：

**缺陷 A — 录入数据与导出数据源是两套不通的存储**（真实库 2798 份未软删底稿实测）：

| 存储位置 | 有内容的底稿数 | 唯一消费方 |
|---|---|---|
| `checklist_responses`（底稿录入真实落点） | **131 份 / 1,034,515 行** | 底稿界面 |
| `parsed_data.html_data`（`export-xlsx` 唯一数据源） | **73 份** | `_sync_export_workpaper_xlsx` |

两集合几乎不相交。`_sync_export_workpaper_xlsx` 只从 `html_data.get(sheet_name)` 取 `rows` 写模板，那 131 份有录入的底稿里绝大多数 `html_data` 键**根本不存在**（探针 `hd_type=ABSENT`）⇒ 模板被原样另存 ⇒ 用户看到空模板。

**缺陷 B — `file_path` 指向全平台共享的模板库原件**：`resolve_wp_file` 判定分布 `file=1063 / template_fallback=1670 / empty=54 / missing=11`，其中 **120 份**底稿 `file_path` 直接存 `wp_templates/...` 且确有 checklist 录入。这些不是「回退」而是本来就指向模板库：`git status` 确认 `wp_templates/` 零改动、同一路径被 **4 个项目共享**（`A1 财务报告程序表.xlsx` 等 `projects=4`）⇒ 该路径必须只读，一旦真写入即跨项目污染。

**而能力侧的实证结论与直觉相反**：per-cycle 导入导出**早已建成**并全部注册 —— 后端 `wp_render_strategies/*_import_export.py` **102 个模块 / 87 个 wp_code**，真实 `app.routes` 里 `export-template`/`export-data`/`import-data` 三态端点**各 36 组、合计 314 个导入导出端点**，共享层 `_cycle_import_export_common.py` 19 个符号被 **94 个模块**消费。缺口在**接线与统一入口**：

- 前端 `CYCLE_IMPORT_EXPORT` 注册表只登记 **10 个 key / 7 个 wp_code 前缀**（F1/F2/F3/F4/F5/G0/H0），**80 个 wp_code 有后端能力但前端未登记**
- `CycleImportExportDropdown` 只挂在 **35 个 .vue（7 个循环）**
- **10 个 composable 是真孤儿**（`useG13/G14/H5/H7/K12/K5/L4/K0/L0/K1WriteoffImportExport`，import 路径与符号双 0 命中）
- 用户四场景里**场景④（归档导出）零端点**（11 个 archive 模块中无任何底稿正文批量导出）

本 spec 的目标不是重造导入导出，而是：①让空产物自证而非伪装成「内容本来就空」②把已建成的 87 个 wp_code 能力接到 UI ③补齐场景④ ④断开模板库引用这条污染路径。

### Glossary

- **四场景**：① 一键导出空白模板 ② 填完导回 ③ 四表取数后二次编辑再导回 ④ 归档前后导出已完成底稿。
- **三态端点**：`export-template`（空白模板）/ `export-data`（含数据）/ `import-data`（回传），per-cycle 各 36 组。
- **`verdict`**：`resolve_wp_file` 的四档判定 `file` / `template_fallback` / `empty` / `missing`（真源 `WP_FILE_VERDICTS`）。
- **空产物自证**：产物内首行写明「本份为空白模板／导出失败」+ 原因，使「导出不全」可被用户直接看见，而非误认为底稿本来无数据。
- **registry**：前端 `components/workpaper/shared/cycleImportExportRegistry.ts` 的 `CYCLE_IMPORT_EXPORT`，决定哪些底稿页出现导入导出下拉。
- **`apiPrefix`**：registry 条目里的 API 前缀，与后端 router `api_prefix` 逐字对应。
- **sheet key ≠ wp_code**：registry 的 `sheets[]` 存的是**后端 API 的 sheet 键**（如 `G0-3S`），不是底稿编码；改字面量会让端点 400。

---

## Requirements

### Requirement 1: 空产物必须自证（缺陷 A/B 的止损层）

**User Story:** 作为审计师，当导出的底稿是空白模板时，我要在文件里直接看到「这是空白模板、原因是什么」，而不是以为这份底稿本来就没数据。

#### Acceptance Criteria

1.1. WHEN `resolve_wp_file` 返回 `verdict != 'file'` THEN 单份下载与批量打包产出的文件内 SHALL 含「本份为空白模板」字样及 `VERDICT_LABELS` 对应的中文原因。
1.2. WHEN `export-xlsx` 路径下 `html_data` 为空或缺对应 sheet 键 THEN 产物首行 SHALL 写明「录入内容未包含」及可操作提示。
1.3. 自证文案 SHALL 只取 `VERDICT_LABELS` 单一真源，不得在调用方硬写中文字面量。
1.4. WHEN 批量打包中存在 `verdict == 'template_fallback'` 的底稿 THEN `_未导出清单.txt` SHALL 列出这些底稿（改造前仅列 `empty`/`missing` 共 65 份，遗漏 1670 份 `template_fallback`）。
1.5. 清单 SHALL 按 `verdict` 分组并给出每档的处置建议。
1.6. WHEN 全部底稿均为 `verdict == 'file'` 且 `html_data` 非空 THEN 产物 SHALL 不含任何自证文案（不得给正常导出加噪声）。
1.7. 自证行 SHALL 不占用数据区首行语义：既有 `_build_failure_fallback_workbook` 范式（第 1 行原因、第 2 行留空、第 3 行起数据）SHALL 被复用。
1.8. WHEN 底稿 `verdict == 'file'` 但 `html_data` 为空而 `checklist_responses` 有行 THEN 自证文案 SHALL 明确区分「文件已就绪但结构化录入未写入 xlsx」这一情形。

### Requirement 2: 导出数据源接通 `checklist_responses`

**User Story:** 作为审计师，我导出的底稿要包含我实际录入的内容，而不只是 `html_data` 里那 73 份。

#### Acceptance Criteria

2.1. 导出 SHALL 在 `html_data` 之外增加 `checklist_responses` 作为数据源。
2.2. WHEN 某底稿 `checklist_responses` 有行 THEN 产物 SHALL 含一个结构化清单 sheet，列含 `item_id` / 值 / 结论 / 备注。
2.3. 清单 sheet SHALL 作为**附加** sheet 追加，不得改写模板既有 sheet 的单元格（模板单元格回填需 per-cycle 地址映射，`structure.json` 全库实测 0 个、`item_id` 形态 211 种，本 spec 不做）。
2.4. WHEN `checklist_responses` 行的值、结论、备注全为空 THEN 该行 SHALL 不进清单（C24 实测 1,033,230 行里 `remark` 有值仅 8 行，全量倾倒会淹没有效内容）。
2.5. 清单 sheet 名 SHALL 不与模板既有 sheet 名冲突。
2.6. WHEN 某底稿 `checklist_responses` 无行 THEN 产物 SHALL 不含清单 sheet。
2.7. 清单行数 SHALL 有上限保护，超限时截断并在 sheet 内标注被截断的行数。
2.8. 清单 sheet SHALL 标注数据来源与导出时点，使其可与底稿界面交叉核对。

### Requirement 3: 四场景统一入口与语义区分

**User Story:** 作为审计师，我要在一个入口完成四件事：拿空白模板、把填好的传回来、把四表刷出来的数据导出去二次编辑再传回、归档时导出成品。

#### Acceptance Criteria

3.1. 四场景 SHALL 复用既有三态端点（`export-template`/`export-data`/`import-data`），不新造第二套 per-cycle 实现。
3.2. 场景①（空白模板）SHALL 走 `export-template`，产物**不含**项目数据。
3.3. 场景③（四表取数后二次编辑）SHALL 走 `export-data`，产物含已取数内容，且 SHALL 标注哪些列来自四表取数（不可直接改写）、哪些列可编辑。
3.4. 场景②与③的回传 SHALL 走同一 `import-data` 端点。
3.5. WHEN 用户把场景①的模板用于场景③回传（或反之）THEN 系统 SHALL 校验并给出可读错误，不得静默写入错位数据。
3.6. 场景④（归档导出）SHALL 产出已完成底稿的批量包，且 SHALL 可在归档前与归档后两个时点执行。
3.7. 四场景在 UI 上 SHALL 语义可辨（各自说明产物内容与适用时点），不得只给「导出/导入」两个裸按钮。
3.8. WHEN 底稿处于归档态 THEN 导入类操作 SHALL 被拒绝并给出原因，导出类操作 SHALL 仍可用。

### Requirement 4: registry 覆盖面从 7 扩到 87

**User Story:** 作为审计师，后端已经支持的 80 个底稿的导入导出，我在界面上要能用到。

#### Acceptance Criteria

4.1. `CYCLE_IMPORT_EXPORT` SHALL 覆盖后端已有 `*_import_export.py` 的全部 wp_code。
4.2. registry 条目的 `apiPrefix` SHALL 与后端 router `api_prefix` 逐字一致，并由守卫交叉锁死。
4.3. registry 的 `sheets[]` SHALL 取后端 sheet 键真源，不得凭 wp_code 推断（`G0-3S` 是 API sheet 键而非底稿编码，改字面量会让端点 400）。
4.4. WHEN 后端新增 `*_import_export.py` 而 registry 未登记 THEN 守卫 SHALL 打红。
4.5. WHEN registry 登记了后端不存在的 `apiPrefix` 或 sheet 键 THEN 守卫 SHALL 打红。
4.6. 扩充 registry SHALL 不改变既有 10 个 key 的行为（F1/F2/F2-val/F2-spe/F2-st/F3/F4/F5/G0/H0 逐字节不变）。
4.7. 无法登记的 wp_code SHALL 进显式登记表并写明理由，不得静默遗漏。

### Requirement 5: 10 个孤儿 composable 处置

**User Story:** 作为维护者，我不要仓库里躺着 10 个写好但从未被渲染的导入导出 composable。

#### Acceptance Criteria

5.1. `useG13/G14/H5/H7/K12/K5/L4/K0/L0/K1WriteoffImportExport` 十个孤儿 SHALL 逐个处置为「接线」或「删除」或「豁免登记」三者之一。
5.2. 处置为「接线」的 SHALL 有真实渲染宿主（不只是被 import）。
5.3. 处置为「删除」的 SHALL 确认其后端端点亦无其他消费方，或该端点仍由别的入口覆盖。
5.4. 处置为「豁免」的 SHALL 写明理由并配 stale 检测（成为真消费方时打红）。
5.5. 孤儿判定 SHALL 按 import 路径而非符号名（符号级匹配只产生假阴性）。
5.6. 平台级守卫 SHALL 递归到「有渲染宿主」为止（A 被 B 消费而 B 自己是孤儿，仍是孤儿链）。
5.7. 孤儿基线条目数 SHALL 只许下调。

### Requirement 6: 断开模板库引用（缺陷 B 根治）

**User Story:** 作为审计师，我保存底稿时不能污染全平台共用的空白模板。

#### Acceptance Criteria

6.1. `file_path` 指向 `wp_templates/` 的底稿 SHALL 在首次写入前复制到项目独立存储。
6.2. `wp_templates/` 下文件 SHALL 永不被写入（守卫按此断言）。
6.3. WHEN 迁移执行 THEN 原 `file_path` 与新路径的对应关系 SHALL 可回滚。
6.4. 迁移 SHALL 幂等（二次执行零变更）。
6.5. 迁移 SHALL 逐条隔离失败，单条失败不影响其余。
6.6. WHEN 同一 `wp_templates` 路径被多项目共享 THEN 每个项目 SHALL 各得独立副本。
6.7. 迁移前后 `resolve_wp_file` 的 `verdict` 分布变化 SHALL 被记录并核对。
6.8. 迁移 SHALL 为破坏性操作，需显式确认参数。

### Requirement 7: 守卫与验收

**User Story:** 作为维护者，我要这四个场景的能力不会在下一轮改动中静默退化。

#### Acceptance Criteria

7.1. 守卫 SHALL 覆盖「产物自证」「数据源接通」「registry 交叉锁死」「孤儿基线」「模板库只读」五类不变量。
7.2. 守卫 SHALL 配变异检验，每条判据须能被对应变异打红。
7.3. 变异检验 SHALL 区分 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态。
7.4. 验收 SHALL 在真实库上跑，且 SHALL 覆盖四场景各一次往返。
7.5. WHEN 真实库无合法验收对象 THEN 脚本 SHALL 诚实输出「无法验收」而非用 fixture 冒充。
7.6. 验收 SHALL 包含浏览器实测，且实测数据 SHALL 完整复原。
7.7. 零回归 SHALL 按「前后对照」判定（当前态 → 施加改动 → 对照），禁用 HEAD-swap（本仓库并发度下会破坏他人未提交成果）。
7.8. CI job SHALL 挂载本 spec 全部守卫。
