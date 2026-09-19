# Task 5 实证记录：真实 OnlyOffice 9.4 Excel identity instrumentation 黑盒 probe

- **spec**：`workpaper-html-onlyoffice-bidirectional-writeback-closure`
- **Requirements**：6.13 / 6.14 / 6.15 / 6.16 / 6.17 / 14.5 / 14.16
- **Property**：66（Excel identity 经真实 OO 往返保留）
- **OnlyOffice build**：`onlyoffice-documentserver 9.4.0-129`（容器 `audit-onlyoffice`，`docker exec dpkg -l` 实测）
- **采集时间（UTC）**：2026-08-24 16:02 – 17:03
- **探针端口**：9993（Task 4 用的 9991 未复用）
- **驱动方式**：Playwright MCP 驱动真实 OO 编辑器（canvas 网格用 OO 自身的名称框/编辑栏/功能区，非模拟）
- **契约（单一真源）**：`backend/data/onlyoffice_excel_identity_carrier_contract.json`
- **守卫**：`backend/tests/test_workpaper_excel_identity_carrier_contract.py`
- **探针脚本**：`backend/scripts/diagnose/probe_oo94_excel_identity.py`
- **可复用模块（Task 17 直接 import）**：`backend/app/services/excel_structure_fingerprint.py`
- **变异 runner**：`backend/scripts/diagnose/mutate_task5_excel_identity_guards.py`（走 `backend/scripts/_mutation_kit` 共享件）

---

## 0. 结论速览

| 载体 / 锚点 | `probe_verdict` | 可否进入 Task 17/36/37 |
|---|---|---|
| hidden `_GT_SYNC` metadata sheet | **passed** | ✅ 可以 |
| workbook 级 + sheet-local defined names（`GT_` 前缀） | **passed** | ✅ 可以 |
| Excel Table（`headerRowCount=0`） | **passed** | ✅ 可以 |
| 隐藏 row UUID 列（预生成字面量） | **passed** | ✅ 可以 |
| 锚点：`defined name` 的 ref | **passed** | ✅ 可以（首选 sheet 锚点） |
| 锚点：Excel Table ↔ sheet 关系 | **passed** | ✅ 可以（首选区域边界锚点） |
| 锚点：`sheetId` | **failed（已证伪）** | ❌ **不可以** |
| 锚点：sheet 展示名 | **failed（已证伪）** | ❌ **不可以** |

未覆盖（**不得当作通过**）：pivotTable/pivotCache、VBA/xlsm、external link workbook、条件格式与数据有效性扩展部件、「用户在 OO 内手工删除隐藏 UUID 列」、多人并发结构编辑。

---

## 1. 探针文档：平台自有真实模板（权威源只读）

`backend/wp_templates/` 是运行时权威源，**全程只读**。两份模板各复制到
`evidence/task5-oo94-excel-identity/staging/` 后才做 instrumentation。

| | K11 | C24 |
|---|---|---|
| 路径 | `backend/wp_templates/K/K11 资产减值损失.xlsx` | `backend/wp_templates/C/C24 会计分录 - 细节测试.xlsx` |
| 源 sha256（开工/收工均核） | `dc0e5434…4a9190` | `b70229f4…7d5c6` |
| instrumented sha256 | `4408f116…acad22` | `ca0a7449…aa9d1` |
| 结构 | 7 sheet / 450 公式 / 54 merge / 1 drawing / 无 external link | 11 sheet / 21671 公式 / 137813 单元格 / 8 chart + 3 drawing + 1 media / 既有 1 个 Excel Table |
| 注入载体 | 隐藏 sheet + 4 defined name + Excel Table + 19 个 row UUID | 隐藏 sheet + 4 defined name + 13 个 row UUID（不注 Table） |
| 覆盖操作 | 全 10 个 | edit / forcesave / download / reopen（4 个） |

**选型依据（实扫 351 个模板，`with_*` 数字见契约 `template_population_scan`）**：

- C24 是**全平台唯一**含 `xl/charts/` 部件的模板（8 个 chart）⇒ Requirement 6.17 的 drawing/chart 判据只能靠它。
- **0 个**模板含 `xl/pivotTables/`、`xl/pivotCache/` 或 `xl/vbaProject.bin` ⇒ pivot/VBA 判 `not_covered` 有事实依据，不是偷懒。
- K11 选它是因为「审定表 K11-1」有 `A7:A25` 跨表引用动态行 + `A26` 的 `SUM` footer，正是 Requirement 6.3/6.5/6.9 描述的真实形态；且无 external link，OO 打开不会弹外链提示干扰操作。
- 开工/收工两次 `verify-source` 均确认 `backend/wp_templates/` 无 `~$` 锁文件、两份源模板 sha256 **未变**（`source_template_sha_before.json` / `source_template_sha_after.json`）。

### instrumentation 做法（zip 级定点注入）

按 design「优先使用 zip-level OOXML 定点修改」，不做 openpyxl 全量重写（C24 含 chart，全量重写有风险）：

- 新增 `xl/worksheets/sheetGtSync.xml`，在 `xl/workbook.xml` 的 `<sheets>` 末尾加 `state="hidden"` 的 `_GT_SYNC`，补 rel 与 content-type override。
- 在 `<definedNames>` 追加 4 条 `GT_*`（3 条 workbook 级 + 1 条 sheet-local）。
- 在受管 sheet 的 `N` 列逐行插入 `inlineStr` UUID 单元格、加 `<col hidden="1">`、更新 `<dimension>`。
- K11 另加 `xl/tables/tableGtRowId.xml`（`headerRowCount="0"`，14 列）+ sheet 的 `<tableParts>` + rel + content-type。

`headerRowCount="0"` 是刻意选择：业务模板的两级合并表头不能当 Table 表头行，置 0 可以在**不改任何可见单元格**的前提下圈出受管行区域。

---

## 2. 操作矩阵：10 操作 × 4 载体 逐格实测

数据源 `operation_matrix.json`（每格都是从真实 OO 回传 artifact 重采的 OOXML 结构指纹）。
`✅` = 载体存活且符合期望；`—` = 该文档未注入该载体。

| 操作 | 文档 | callback | `_GT_SYNC` | `GT_*` defined name | Excel Table | 隐藏 UUID 列 |
|---|---|---|---|---|---|---|
| edit | K11 | status 6 | ✅ 15 键全在 | ✅ 4/4，0 缺失 | ✅ `GT_K11_1_ROWS` `A7:N25` | ✅ 19 个 / 19 distinct，仍隐藏 |
| insert_row | K11 | status 6 | ✅ | ✅ 4/4 | ✅ ref 自动扩到 **`A7:N26`** | ✅ 19 个；新行**无 UUID**（判据：ref 20 行 − 19 = 1） |
| delete_row | K11 | status 6 | ✅ | ✅ 4/4 | ✅ ref 回到 `A7:N25` | ✅ 18 个；`GTROW-K11-0012` 整条消失 |
| sort | K11 | status 6 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个，集合不变、**行号↔UUID 映射整体改变**（UUID 随行迁移） |
| copy | K11 | **无 artifact** | — | — | — | — （见下「copy 那一格」） |
| paste | K11 | status 6 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个 / **17 distinct**，出现重复 `GTROW-K11-0018`；目标行原 UUID 被覆盖 |
| **rename_sheet** | K11 | status 6 | ✅ | ✅ 4/4，**ref 自动改写成新 sheet 名** | ✅ 随 sheet 走 | ✅ 18 个；**`sheetId` 与 sheet 名两条定位路径同时失效，只有 Table 路径还能定位** |
| forcesave | K11 | status 6 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个 |
| download（callback status 2） | K11 | status 2 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个 |
| download（编辑器「文件→下载为→XLSX」，**不经 callback**） | K11 | 浏览器下载 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个 |
| reopen（关编辑器→新 doc_key 重开→再编辑→forcesave） | K11 | status 6 + status 2 | ✅ | ✅ 4/4 | ✅ | ✅ 18 个 |
| edit | C24 | status 6 | ✅ 13 键全在 | ✅ 4/4 | — | ✅ 13 个，仍隐藏 |
| download（status 2） | C24 | status 2 | ✅ | ✅ 4/4 | — | ✅ 13 个 |
| reopen | C24 | status 6 + status 2 | ✅ | ✅ 4/4 | — | ✅ 13 个 |

共 **15 个 OO 回传 artifact + 1 个编辑器下载文件**，逐个 sha256 见契约与 `operation_matrix.json`。
**16/16 全部保留三类载体，0 处采集 ERROR。**

### 关键格：sheet 改名后 identity 是否仍可定位？

**答案：可以，但只能靠 defined name 或 Excel Table，不能靠 sheetId / sheet 名。**

改名 `审定表K11-1` → `审定表K11-1改名后` 后，三条定位路径的实测结果：

| 定位路径 | 解析到的 sheet | 该 sheet 上找到的 UUID 数 |
|---|---|---|
| `sheetId=1`（instrumentation 时刻记录的值） | `底稿目录` ← **完全另一张 sheet** | **0** |
| sheet 展示名 `审定表K11-1` | 解析失败（`null`） | **0** |
| Excel Table `GT_K11_1_ROWS` 的 sheet 归属 | `审定表K11-1改名后` ✅ | **18** |

同时 4 条 `GT_*` defined name 的 ref 被 OO **自动改写**：

```
GT_MANAGED_REGION_K11    '审定表K11-1'!$A$7:$L$25   →  '审定表K11-1改名后'!$A$7:$L$25
GT_FOOTER_ANCHOR_K11     '审定表K11-1'!$A$26        →  '审定表K11-1改名后'!$A$26
GT_ROW_UUID_RANGE_K11    '审定表K11-1'!$N$7:$N$25   →  '审定表K11-1改名后'!$N$7:$N$25
GT_SYNC_ANCHOR_K11       _GT_SYNC!$A$1              →  _GT_SYNC!$A$1（未变）
```

### copy 那一格

纯复制不改文档 ⇒ Command Service `c=forcesave` 返回 **error 4**（自上次保存无新变更），OO 不产生 artifact。
identity 因此不可能变化；复制的真实影响由 `paste` 一格取证（实测产出可检出的重复 UUID）。
契约把这一格记成 `artifact_produced: false` + `command_service_error: 4`，守卫按 `commands.jsonl` 反算校验，
**不允许**以「无 artifact」当作「没测」蒙过去。

另：紧接一次 forcesave 之后再发 forcesave 也返回 **error 4**，与 Task 4 契约的
`command_service.return_codes` 一致（交叉验证成立）。

---

## 3. 🔴 证伪：`sheetId` 不能当 identity 锚点

这是本次探针**最贵的发现**，直接改掉了原先「`_GT_SYNC` 里存 `GT_MANAGED_SHEET_ID` 作为锚点」的设计意图。

| sheet | instrumented（未过 OO）的 `sheetId` | 过 OO 保存一次后的 `sheetId` |
|---|---|---|
| 底稿目录 | 6 | **1** |
| 实质性程序表 K11A | 7 | **2** |
| 审定表K11-1 | **1** | **3** |
| 附注披露信息（上市公司） | 10 | **4** |
| 附注披露信息（国企） | 9 | **5** |
| 明细表K11-2 | 4 | **6** |
| 调整分录汇总K11-3 | 8 | **7** |
| `_GT_SYNC` | 11 | **8** |

**OO 9.4 每次保存都把 `sheetId` 按 tab 顺序重编号为 `1..N`。** 15 个 artifact 全部如此，
`sheet_id_anchor_holds` = **0/15**。第一个失败的操作就是 `edit` —— 只是打开、改一格、forcesave，
与任何结构编辑无关。

后果：
- `sheetId` 退化成「当前 tab 位置」，sheet 顺序变化即漂移；
- 以 `GT_MANAGED_SHEET_ID=1` 定位会解析到 `底稿目录`（另一张 sheet），实测该列 UUID 数 = 0；
- Requirement 6.14 本就禁止依赖 sheet 展示名 ⇒ **两个直觉上的锚点同时不可用**，
  只剩 defined name（随改名自动跟踪）与 Excel Table（部件关系维护 sheet 归属）。

因此契约把 `sheet_id` 与 `sheet_display_name` 两个锚点固定为 `probe_verdict: failed`，
`gate_for_downstream_tasks.task_17_instrumentation_definition.forbidden_anchors` 明确列出，
Task 17 的 loader 必须 fail-closed 读它。

`_GT_SYNC` 里的 `GT_MANAGED_SHEET_ID` 键**保留但降级**为「instrumentation 时刻的审计线索」，
不得当运行时锚点（契约 `carriers[hidden_sheet].usage_rules` 已写死）。

### 采集器的相应设计约束

`identity_inventory()` 对三条 sheet 定位路径**各自独立求解并全部上报**（`sheet_resolution_candidates`），
**绝不静默 fallback**。静默 fallback 会把「某锚点已被 OO 破坏」掩盖成「定位成功」——
正是 memory 里记的假绿第①源形态。

---

## 4. Requirement 6.15 的三种异常形态：实测可判定

| 形态 | 实测 | 判据 | contract 处置 |
|---|---|---|---|
| OO 内新增行的空 UUID | insert_row 后 Table ref 覆盖 20 行、UUID 只 19 个 | `ref 行数 − 非空 UUID 数 > 0` | 分配新 ID |
| 复制行产生重复 UUID | paste 后 18 个 UUID 只 17 distinct，`GTROW-K11-0018` 重复 | 同列出现重复值 | 结构冲突 |
| 复用已删除 UUID | delete_row 删掉 `GTROW-K11-0012`，其后 6 个 artifact 均未再出现 | 删除集 ∩ 现存集 = ∅ | OO 侧不会自动违反 |
| 用户删掉整列 identity | **未实测** | `row_uuid_count == 0` 且 ref 仍覆盖数据行 | 拒绝（判据为结构投影，**标 not_covered**） |

排序取证的判据是「行号→UUID 映射改变 **且** UUID 集合不变」，不是「个数没少」：

```
delete_row 后:  行7=GTROW-K11-0007  行8=GTROW-K11-0008  行9=GTROW-K11-0009
sort 后:        行7=GTROW-K11-0014  行8=GTROW-K11-0018  行9=GTROW-K11-0020
```

集合相同、映射全变 ⇒ UUID 跟着业务行走了，而不是留在原行号上。

---

## 5. Requirement 6.17 等价性

### 5.1 instrumentation 前后：**严格等价**（6/6 aspect）

| aspect | K11 diff | C24 diff |
|---|---|---|
| visible_sheets | 0 | 0 |
| business_values | 0 | 0 |
| formulas | 0 | 0 |
| styles | 0 | 0 |
| merges | 0 | 0 |
| protected_parts（drawing/chart/media，byte digest） | 0 | 0 |

白名单内的新增只有 4 样：隐藏 `_GT_SYNC` sheet、`GT_` defined names、受管 sheet 的一列隐藏 UUID、
`headerRowCount=0` 的 Table 部件（不占任何可见单元格）。隐藏 metadata sheet 被业务 sheet 枚举显式排除。

**C24 的 8 个 chart / 3 drawing / 1 media 部件字节完全未变** ⇒ zip 级注入对 chart 是安全的。

### 5.2 过一次 OO 之后：**非字节等价**，且差异 100% 归因于 OO 自身

用控制组把「OO 归一化」与「instrumentation 影响」分开（`oo_normalization_attribution.json`）：

| 对比 | business_values | formulas | styles | merges | protected_parts |
|---|---|---|---|---|---|
| A：源模板 vs instrumented（不过 OO） | 0 | 0 | 0 | 0 | 0 |
| B：源模板 vs 源模板过 OO（**控制组**） | 1 | 0 | 487 | 0 | 1 |
| C：instrumented vs instrumented 过 OO | 1 | 0 | 487 | 0 | 1 |

**A 全零、B 与 C 逐项相等** ⇒ OO 往返的全部差异都由 OO 自身重序列化造成，
instrumentation 贡献为 **0**。这是实测控制组，不是归因推理。

实测到的 OO 归一化种类：

| 种类 | 细节 | 规模 | 不带 instrumentation 也发生 |
|---|---|---|---|
| 填充色调色板重映射 | fgColor `indexed:14`→`indexed:6`；bgColor `indexed:64`→`rgb:00000000` | K11 487/767 个带样式单元格 | ✅ |
| **字体替换** | `宋体` → `Calibri`（容器内未装宋体） | C24 大量 | ✅ |
| 公式空白归一化 | 带换行/缩进的长公式被压平 | C24 10535/21671；**K11 0/450** | ✅ |
| 受保护部件重序列化 | chart/drawing/vml 字节全部重写，**部件数量不减**（8 chart / 1 media 不变），C24 多出 1 个 drawing | K11 1 处；C24 9 处 | ✅ |
| OO 追加自有 defined name | C24 39 → 41（多出 `Print_Titles`） | — | ✅ |

**对 Task 17/36/37 的硬性后果**：

1. Requirement 6.11 / 8.10 的往返等值只能按**语义 / 受管字段**比对，
   **不得**按 protected part 字节 digest 或全量 style 指纹判等 —— 否则每次 OO 保存都会误判成结构漂移。
2. 受保护部件的判据固定为「部件名集合与计数不减少」+「业务值 / merge / 受管公式等值」。
3. identity 读取必须按 `GT_` 前缀过滤而非 defined name 总数比对（OO 会追加自有名称）。
4. `宋体 → Calibri` 是**容器字体缺失**导致的真实可见变化，属部署层问题（要在 OO 镜像里装中文字体），
   不是 instrumentation 层能解决的；中文底稿上线前必须处理。

---

## 6. 采集器自身修掉的两个真实缺陷

写守卫过程中发现 `excel_structure_fingerprint.py` 有两处会**制造假差异**，已修（否则 Task 17 的
upgrader 会拿它误判「不等价」而拒绝发布）：

1. **`repr(ArrayFormula)` 带内存地址**。openpyxl 把数组公式包成 `ArrayFormula`、数据表公式包成
   `DataTableFormula`，两者都没实现 `__repr__`/`__eq__` ⇒ `repr()` 输出 `<... object at 0x0000...>`，
   同一份文件读两次都不相等。实测：C24 的「参考-本福特定律测试」有 100 个数组公式，
   未规范化时 instrumentation 前后凭空出现 **100 处 diff**。已改为 `ArrayFormula(ref=…,text=…)` 规范串，
   并按 `data_type == 'f'` 归类到 formulas 而非 values。
2. **`Color.rgb` 对 indexed/theme 色返回错误占位串**。openpyxl 的 `Color.rgb` 只在 `type=='rgb'` 时有值，
   对 indexed/theme/auto 返回 `"Values must be of type <class 'str'>"`。直接拼进样式指纹会让
   indexed 与 rgb 色互判不同。实测：K11 只改一个格，styles 却报 444/767 处 diff，全是这个占位串。
   已改为 `_color_sig()` 输出 `(type:value)`，修后剩下的 487 处才是**真的** OO 调色板重映射。

两处都属于「守卫把错值当基线锁死」的反面：如果不修，Task 17 的 visible-equivalence 会恒判不等价。

---

## 7. Playwright 实测截图（`screenshots/`）

| 文件 | 证明什么 |
|---|---|
| `01_k11_instrumented_opens_no_error.png` | instrumented 文件在真实 OO 打开无 error/warning 弹窗；标签栏**不显示** `_GT_SYNC` |
| `02_k11_sorted_namebox_shows_GT_K11_1_ROWS.png` | 选中受管区域时 OO 名称框显示 `GT_K11_1_ROWS`、功能区出现「表格设计」⇒ 注入的 Table 是活的 Table 对象；排序后 `GT-EDIT-J7` 从第 7 行移到第 17 行 |
| `03_k11_pasted_footer_and_merge_intact.png` | 粘贴落在第 20 行；第 26 行「合计」及其 merge、第 27/28 行 TB 数据/差异 footer 均完好 |
| `04_k11_reopen_renamed_sheet_tab.png` | 关闭后新 doc_key 重开：标签为 `审定表K11-1改名后`、排序结果与两处标记值都在、`_GT_SYNC` 仍隐藏 |
| `05_c24_reopen_name_manager_with_GT_names.png` | C24 重开后名称管理器里 `GT_*` 与 OO 自有 `Print_Area`/`Print_Titles`/`Benford数据范围` 并存；Benford 表公式重算出值 |


驱动过程通过 OO 自身 DOM（名称框 `#ce-cell-name`、编辑栏 `#ce-cell-content`、
功能区「插入单元格→整行」「删除单元格→整行」「降序排序」、标签右键「重新命名」、
「文件→下载为→XLSX」）完成，网格是 canvas 但这些控件是真实 DOM。

过程中观察到的 UI 侧证据：

- 打开 instrumented 文件**无任何 error/warning 弹窗**，`onDocumentReady` 正常触发 ⇒ OO 9.4 接受
  `headerRowCount=0` 的 Table 与隐藏 metadata sheet。
- sheet 标签栏**不显示** `_GT_SYNC`（审计师不可见）。
- 选中受管区域时 OO 名称框显示 **`GT_K11_1_ROWS`**、功能区出现「表格设计」选项卡
  ⇒ 注入的 Table 在 OO 内是**活的** Table 对象，不是死 XML。
- 注入的 Table **没有**给业务区域叠加可见表格样式（`tableStyleInfo` 不带 `name`、stripes 全 0）。
- 名称管理器里能看到 `GT_*` 与 OO 自有的 `Print_Area`/`Print_Titles`/`Benford数据范围` 并存。

---

## 8. 未覆盖项（明确不标通过）

| 项 | 原因 | 阻塞什么 |
|---|---|---|
| pivotTable / pivotCache | 351 个真实模板中 **0 个**含该部件，无平台自有样本可取证 | Task 17/36/37 若要处理含 pivot 的 custom/user-upload xlsx，必须先补一次带 pivot 的真实 OO 探针 |
| VBA / xlsm | 全量模板 0 个含 `xl/vbaProject.bin` | 同上 |
| external link workbook | 162 个模板含 `xl/externalLinks/`，但两份探针文档刻意选了无外链者（避免 OO 弹外链提示干扰操作矩阵） | 外链模板的 OO 往返行为待补测 |
| 条件格式 / 数据有效性扩展部件 | openpyxl 读 C24 时对这两类 extension 发 UserWarning 并丢弃，采集器当前不覆盖 | 不能对其等价性下结论 |
| 用户在 OO 内手工删除隐藏 UUID 列 | 未实操；处置分类只有结构投影判据 | Requirement 6.15 的「拒绝」分支缺实测 |
| 多人并发结构编辑（一人排序另一人插行） | Task 5 是单用户 identity 探针，多人语义在 Task 4 | 二者交叉行为未取证 |
| C24 的 insert/delete/sort/copy/paste/rename | 该文档只用于 chart 部件取证；结构矩阵由 K11 承担（137813 单元格上重复十操作代价过高） | 契约已显式声明 `operations_not_covered` |
| Requirement 14.5 的动态公司列 / 两级表头 / 公式保护 / footer 下移 / 结构漂移拒绝 | 属 Wave 4 pilot（Task 40–45）范围 | 本任务只覆盖 identity 载体与动态行增删重排复制 |

---

## 9. 复现步骤

```powershell
# 0. 核权威源未被改
python backend/scripts/diagnose/probe_oo94_excel_identity.py verify-source --stage before

# 1. 复制到 staging 并注入三类载体 + 生成 instrumentation 等价报告
python backend/scripts/diagnose/probe_oo94_excel_identity.py instrument

# 2. 起 document host + callback collector（端口 9993）
python backend/scripts/diagnose/probe_oo94_excel_identity.py --port 9993 serve --doc k11

# 3. 浏览器打开 http://127.0.0.1:9993/editor，逐操作执行；每步之后：
python backend/scripts/diagnose/probe_oo94_excel_identity.py --port 9993 mark --op insert_row
python backend/scripts/diagnose/probe_oo94_excel_identity.py --port 9993 command --c forcesave --userdata op-insert_row

# 4. reopen：用上一轮 status 2 artifact 作宿主文档重开
python backend/scripts/diagnose/probe_oo94_excel_identity.py --port 9993 serve --doc k11 --seed <artifact>

# 5. 汇总 + 归因 + build + 收工核权威源
python backend/scripts/diagnose/probe_oo94_excel_identity.py analyze
python backend/scripts/diagnose/probe_oo94_excel_identity.py attribute
python backend/scripts/diagnose/probe_oo94_excel_identity.py build
python backend/scripts/diagnose/probe_oo94_excel_identity.py verify-source --stage after

# 6. 守卫 + 变异检验（变异走 backend/scripts/_mutation_kit 共享件）
python -m pytest backend/tests/test_workpaper_excel_identity_carrier_contract.py -q
python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --list
python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --check-anchors
python backend/scripts/diagnose/mutate_task5_excel_identity_guards.py --run all --out <evidence>/mutation_report.json
```

---

## 11. 守卫与变异检验结果

- **守卫**：`backend/tests/test_workpaper_excel_identity_carrier_contract.py`，**31 passed**。
  每一条 `probe_verdict` / 期望值都从 `operation_matrix.json` / `instrumentation_report.json` /
  `oo_normalization_attribution.json` / `source_template_sha_*.json` **重新计算**后比对，
  契约与实证任一侧被改动都会打红（双向互锁）。
- **变异**：35 条，**RED 35 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0**，还原核验 35/35 md5 一致。
  - 契约侧 24 条（手填 passed、抹掉重复 UUID 期望、把 not_covered 改 passed、
    改源模板 sha256、删 Property 66 结论…）
  - evidence 侧 11 条（篡改 sheetId 锚点实测、抹掉 `_GT_SYNC`、注入采集 ERROR、
    让改名后 defined name ref 停在旧名、chart 部件数归零、排序映射复原…）
- **「不是一改就红」的反向证据**两条：
  1. **爆炸半径**：每条变异只打红 1–3 例（共 31 例，均值 1.06），且命中的正是声明的 `want`。
  2. **守卫内自检**：`test_negative_control_is_field_specific` 往 evidence 副本塞未知键，
     断言判据**保持通过**；再把该管的字段改坏，断言必须失败。
     （这条放在守卫里而非当 GREEN 对照变异，因为共享件把 GREEN 一律判成守卫缺陷。）

### 变异脚本迁移到共享件时踩到的两点

- 共享件要求**单行锚点**（多行锚点在 CRLF 工作树下必 ANCHOR-MISS，`spec.validate_mutation`
  在声明期就拒绝）。原先自写 runner 用的多行 JSON 片段锚点全部改成整行 + `scope`/`offset`
  相对定位（evidence JSON 里的重复行用该行 artifact 的 `artifact_sha256` 作唯一 scope）。
- 共享件要求 `guard_files` 覆盖面分母为**必填关键字参数**，并对 `probe_verdict` 类结构变异
  提供 `scope_check` 作用域自证 —— 用来排除「锚点命中了同名文档说明而非被测结构」这种
  会被四态判定误报成 GREEN 的脚本缺陷。本脚本对 8 条结构型变异都写了 `scope_check`。

---

## 10. Property 66 判定

design.md 的 oracle：

> 选定 hidden metadata/defined name/Table UUID 载体在编辑、插删、排序、复制、forcesave、下载、重开后
> 满足 identity inventory 预期；任一缺失阻断 engine gate。

逐条对照：

| oracle 要素 | 实测 | 判定 |
|---|---|---|
| hidden metadata 载体经全部操作满足预期 | 16/16 artifact present + hidden + 必需键 0 缺失 | ✅ |
| defined name 载体经全部操作满足预期 | 16/16 artifact 4/4 present，改名后 ref 自动跟踪 | ✅ |
| Table + UUID 载体经全部操作满足预期 | Table 16/16 present、ref 随插删伸缩；UUID 逐操作与 `per_operation_expectations` 逐项相等 | ✅ |
| 「任一缺失阻断 engine gate」 | 无载体缺失；但 `sheetId`/`sheet 展示名`两个**锚点**被证伪 ⇒ 以机器可读 `probe_verdict: failed` + `forbidden_anchors` 阻断以它们为前提的 engine 建设 | ✅（阻断已落到契约的机器字段） |

**Property 66：通过。** 三类载体全部可进入 Task 17/36/37；`sheetId` 与 sheet 展示名两个锚点
必须被 Task 17 的 loader fail-closed 拒绝。
