# Task 6 实证记录：真实 OnlyOffice 9.4 Word tagged SDT 载体黑盒 probe

- **spec**：`workpaper-html-onlyoffice-bidirectional-writeback-closure`
- **Requirements**：7.2 / 7.5 / 7.6 / 14.4 / 14.16
- **Property**：33（Word pilot tag 往返保留）
- **OnlyOffice build**：`onlyoffice-documentserver 9.4.0-129`（容器 `audit-onlyoffice`，`docker exec dpkg -l` 实测）
- **浏览器**：`Chrome/151.0.0.0`（Playwright Chromium, Windows NT 10.0 x64）
- **采集时间（UTC）**：2026-08-24 23:18 – 2026-08-25 00:10
- **探针端口**：9995（Task 4 的 9991、Task 5 的 9993 均未复用）
- **source commit**：`d330d7cea6bb112709edce5bf287877df0a5f60c`（分支 `work/2026-08-23-advanced-query-hardening-closure`）
- **契约（单一真源）**：`backend/data/onlyoffice_word_sdt_carrier_contract.json`
- **守卫**：`backend/tests/test_workpaper_word_sdt_carrier_contract.py`（36 例）
- **探针脚本**：`backend/scripts/diagnose/probe_oo94_word_sdt.py`
- **独立重算器**：`backend/scripts/diagnose/verify_task6_word_sdt_evidence.py`（不 import 探针，另一套实现）
- **变异 runner**：`backend/scripts/diagnose/mutate_task6_word_sdt_guards.py`（走 `backend/scripts/_mutation_kit` 共享件）

---

## 0. 结论速览

**Property 33 判定：FAIL（分载体，不是整体不可用）。**

Property 33 的原文判据是「tag 集合、层级和 row_uuid 集合不减少」。实测里 **tag 集合确实减少了** ——
row 级 `w:sdt` 的 3 个 `gt:row:` tag 在 **9/9** 个 b30112 artifact 上全部消失，包括只打开再保存的
baseline 格。按判据原文这就是 FAIL，不做「主要通过」之类的软化。

| 载体 | `probe_verdict` | 可否进入 Word engine（Tasks 59/60/61） |
|---|---|---|
| inline field SDT（`gt:field:`，含表格单元格内） | **passed**（26/26 artifact） | ✅ 可以 |
| block field SDT（`gt:block:`，包整段 + 嵌套 inline） | **passed**（17/17 artifact） | ✅ 可以 |
| **row-level SDT（包 `w:tr`，tag 内含 row_uuid）** | **failed（已证伪）** | ❌ **不可以** |
| SDT 外正文（Word-only 自由正文） | **passed**（0 行非预期丢失） | ✅ 可以 |

| 候选锚点 | `probe_verdict` | 可作身份锚点 |
|---|---|---|
| `w:tag` | passed | ✅ 唯一正式锚点（作用域仅 field/block，不含 row） |
| `w:alias`（展示名） | passed（26/26 保留） | ❌ 可重复、可被审计师改名 |
| `w:id` | passed（26/26 未重编号） | ❌ 同 stable key 两实例**共享同一 id**，不唯一 |
| 段落绝对序号 | **failed** | ❌ 文首插 2 段后整体位移 |
| SDT 内 run 序号 | **failed** | ❌ 注入 3 run 经 OO 往返变 2 run |

**对 design 的结论**：Requirement 7.2 现写的「重复行/区块 SHALL 使用 row-level SDT」在 OO 9.4 上
不成立，必须回到 design 重选行身份载体。本探针**顺手量到**一个可行候选（把 row_uuid 写进单元格内
inline field SDT 的 tag），9/9 artifact 存活；但**选不选它是 design 的裁决**，本 probe 不代替，
契约里它单独放在 `row_identity_fallback_measured`、**不进** `carriers` 列表。

**本 probe 明确未宣称**（Task 6 正文点名禁止提前自证）：生产 Word extractor、tag 缺失 fail-closed、
operation 回写 / merge / rematerialize、F2 pilot 门第 6/7 步 —— 由 Tasks 59 / 61 / 68 承接。
另有 6 项 `not_covered`（多人并发、MS Word 桌面端、`w:lock` 保护下行为、dataBinding/customXml 等），
逐条带理由登记在契约里，守卫 `test_not_covered_items_are_never_marked_passed` 禁止它们被标成 passed。

---

## 1. 探针文档：平台自有真实模板（权威源全程只读）

`backend/wp_templates/` 是运行时权威源。三份模板各复制到 `staging/{doc}_before.docx` 之后才注入。

| | f222 | f223 | b30112 |
|---|---|---|---|
| wp_code | F2-22 | F2-23 | B30-11-2 |
| 路径 | `backend/wp_templates/F/F2-22 存货监盘计划.docx` | `backend/wp_templates/F/F2-23 存货监盘小结.docx` | `backend/wp_templates/B/B30-11-2 内部控制缺陷汇总与评估.docx` |
| 源 sha256 | `f19aa64a…6662ba` | `09106818…32b080` | `b4facd6b…0bbb247` |
| 角色 | Requirement 7.6 指定 pilot（field 载体全场景） | 第二 pilot（证明结论非单文档偶然） | **row 载体取证**（两个 pilot 零表格） |
| 表格 | **0 个** | **0 个** | 1 个（表头 + 3 个同构数据行 × 10 列） |
| 注入 | 8 个 field SDT / 9 个 SDT | 3 个 field SDT / 4 个 SDT | 1 个 field SDT + **3 个 row SDT** / 7 个 SDT |
| 覆盖操作 | 8 个（含 insert/delete_paragraph、edit_outside_sdt） | 5 个 | 7 个（含 insert_row / delete_row） |
| artifact | 10 个 | 7 个 | 9 个 |

### 为什么行载体不能在 pilot 文档上取证

F2-22 与 F2-23 的 `word/document.xml` 里 `w:tbl` / `w:tr` 计数**实测均为 0**（
`instrumentation_report.docs.{f222,f223}.pre_injection_inventory.tables == []`）。
Requirement 7.2 的 row-level SDT 在这两份文档上物理上无处可注。

这个缺口显式记在契约 `pilot_template_row_carrier_gap` 并由守卫
`test_pilot_row_carrier_gap_is_backed_by_template_facts` 用模板事实反查 —— 否则
「Word pilot 通过」会被误读成「行载体也通过」，而这恰好是本任务最贵的一个误读。
另取 B30-11-2 补测，守卫同时断言取证文档**不能**还是那两个零表格 pilot。

### 注入做法（zip + 字符串级定点手术）

按 design「不得用 python-docx 重建整文档」：解 zip 取 `word/document.xml`，在原字符串上定点包
`<w:sdt><w:sdtPr><w:tag w:val="…"/><w:id …/></w:sdtPr><w:sdtContent>…`，再按固定 entry 时间重打包
（`zip_determinism=fixed_entry_datetime=(2026,1,1,0,0,0)`，让 sha 可复现）。

注入后立刻重开 zip 回读校验，四项全绿：`tags_match_manifest` / `tag_multiset_match` /
`row_uuids_match` / `hierarchy_match`，且 `visible_skeleton_preserved=true`（把注入涉及的 token 与
seed 全抹掉后剩下的可见文本连写串未变）。

**刻意不加 `<w:lock w:val="sdtLocked"/>`**：加锁会让 OO 无法删除 SDT，等于替载体作弊；本探针要证的
是**无保护下** OO 是否自发保留 tag。守卫 `test_lock_policy_is_no_lock_and_matches_instrumentation`
不止比契约字段，还直接解 `staging/*_instrumented.docx` 的 zip 断言 `<w:lock` 不存在。

---

## 2. 操作矩阵：26 个真实 OO 回传 artifact 逐格实测

数据源 `operation_matrix.json`（每格都从真实 OO 回传的 DOCX 重采 SDT 清册）。
callback 统计：**29 条**（status 1 × 6 / status 2 × 6 / status 6 × 17）。
Command Service `c=forcesave` **21 次**：`error: 0` **17 次**，`error: 4`（自上次保存无新变更）**4 次** ——
其中 3 次是 f222/f223/b30112 各自**紧接一次 forcesave 之后再发一次**（`userdata=op-forcesave-2`），
1 次是 f222 打开后未编辑就发 forcesave。这与 Task 4 契约的 `command_service.return_codes`
及 Task 5 的同类实测一致，构成跨任务交叉验证。

| 操作 | 文档 | `gt:field:` tag | `gt:block:` tag | `gt:row:` tag | 层级 | SDT 外正文 |
|---|---|---|---|---|---|---|
| baseline（仅打开+保存） | f222 | ✅ 7/7 | ✅ 1/1 | — | ✅ | ✅ 逐字未变 |
| edit_in_sdt | f222 | ✅ | ✅ | — | ✅ | ✅ 逐字未变 |
| edit_outside_sdt | f222 | ✅ | ✅ | — | ✅ | 按操作意图变化（见 §4） |
| insert_paragraph | f222 | ✅ | ✅ | — | ✅ | 按操作意图变化 |
| delete_paragraph | f222 | ✅ | ✅ | — | ✅ | 按操作意图变化 |
| forcesave | f222 | ✅ | ✅ | — | ✅ | 继承前序外部编辑 |
| download（编辑器「另存为」，不经 callback） | f222 | ✅ | ✅ | — | ✅ | 继承 |
| reopen（换 doc_key 重开 → 再编辑 → forcesave） | f222 | ✅ | ✅ | — | ✅ | 继承 |
| baseline / edit_in_sdt / forcesave / download / reopen | f223 | ✅ 3/3 | ✅ 1/1 | — | ✅ | ✅ 逐字未变 |
| **baseline（仅打开+保存）** | b30112 | ✅ 4/4 | — | ❌ **0/3** | ❌ | ✅ 0 行丢失 |
| edit_in_sdt | b30112 | ✅ | — | ❌ 0/3 | ❌ | ✅ 0 行丢失 |
| insert_row | b30112 | ✅ | — | ❌ 0/3 | ❌ | ✅ 0 行丢失（新增 1 行标记文本） |
| delete_row | b30112 | ✅ 3/3（R02 为有意删除） | — | ❌ 0/2 | ❌ | ✅ 0 行丢失 |
| forcesave / download / reopen | b30112 | ✅ | — | ❌ 0/2 | ❌ | ✅ 0 行丢失 |

`op` 标签**以 callback 的 `userdata` 为权威**（发 forcesave 时写死），probe mark 只作兜底。
实测 b30112 有 **3 格**因「同一行命令里 command 后紧跟 mark」产生竞态，mark 贴错了标签；矩阵
如实保留 `marked_op` 与 `op_label_disagreed_with_mark=true`，未用 mark 的值冒充。若只留 mark，
b30112 baseline 的结果会被写成 edit_in_sdt 的结果 —— 而 baseline 恰好是判断「剥离时机」的关键格。

---

## 3. 🔴 证伪：row-level SDT 在 OO 9.4 上不是稳定载体

这是本次探针**最贵的发现**，直接推翻 Requirement 7.2 现写的载体选择。

| 判据 | 注入后（未过 OO） | 过 OO 一次之后 |
|---|---|---|
| `gt:row:` tag 数 | 3 | **0**（9/9 artifact） |
| 表格里被 SDT 包住的 `w:tr` 数 | 3 | **0**（9/9 artifact） |
| 表格行数 | 4 | **4**（未变） |
| 单元格内 `gt:field:…rows/{uuid}/…` tag | 3 | **3**（全保留） |

三条必须分开说，混在一起会得出错误改法：

1. **剥离发生在 baseline 格**，不是被某个行操作触发。`baseline` 这一格只做了「打开 → 保存」，
   row tag 就已经全没了 ⇒ 这是 OO 的**加载/保存路径固有行为**，不是插行删行的副作用。
   守卫 `test_row_sdt_stripping_happens_at_baseline_not_by_row_edits` 从 baseline 格的
   `tags_present` 反算，锁死这个区分。
2. **只丢 SDT 包装，不丢行数据**。表格仍是 4 行 × 10 列，单元格文字完好。把「载体不支持」
   写成「数据损坏」是夸大，守卫 `test_row_sdt_stripping_did_not_destroy_table_rows` 拦这个。
3. **行身份本身没丢** —— 因为同一个 row_uuid 被冗余写进了单元格内 inline field SDT 的 tag。
   这是注入时刻意做的双写，正因为双写，才能把「行载体失效」与「行身份丢失」两件事分开测。

### 顺手量到的替代候选（**未采纳**，仅供 design 裁决）

候选 = `cell_level_field_sdt_tag_carrying_row_uuid`，即 tag 形如
`gt:field:{contract}:rows/{row_uuid}/{column_key}`，不依赖任何 row 级包装。实测：

| 场景 | 实测结果 |
|---|---|
| 经 OO 往返（row SDT 已被剥离的同一批 artifact） | 9/9 存活 |
| OO 内插入新行 | 已有 3 个 row_uuid 不变；**新行不带任何 identity** |
| 审计师在 OO 内删除某行 | 恰好该行的 uuid 消失（`86f54ae5…`），另 2 个保留 |

`status` 字段写的是「probe 级已取证可行；是否采纳为正式行身份协议属 design 修订，本 contract
不代替裁决」，守卫 `test_row_identity_fallback_is_not_declared_adopted` 同时断言两件事：
status 不能读起来像「已采纳」，且这个候选**不得**出现在正式 `carriers` 列表里。变异 M23 专门
试图把 status 改成「已采纳，Task 59 可直接实现」，被打红。

**OO 新增行无 identity** 这条要单独接住：它是 Requirement 6.15 的 Word 侧同类问题。contract 必须
显式分类为「分配新 ID / 结构冲突 / 拒绝」三者之一，不得静默猜测。本探针只登记事实，不裁决走法。

---

## 4. Requirement 7.3 / 7.5 的正向结论

### 7.3：SDT 外正文（Word-only 自由正文）

**26/26 artifact 零行非预期丢失。**判据分两层：

- **仅改结构化岛的格**（每个文档的 `edit_in_sdt`）：SDT 外正文 digest **逐字不变**。守卫
  `test_sdt_internal_edit_does_not_touch_free_text` 独立于契约数字硬断言这一条。
- **刻意改外部正文的格**（f222 的 `edit_outside_sdt` / `insert_paragraph` / `delete_paragraph`）：
  digest 变化，且变化**逐行可归因到操作者自己的键入**：改标题 `9．特别关注事项：` →
  `9．特别关注事项（审计师现场补充）：`、加 `WORDONLY-FREE-TEXT-A`、插两段
  `GT-PROBE-INSERTED-PARA-1/2`、删段时多删掉一个「项」字。11 个格 digest 未变、15 个格
  按操作意图变化，两个数字都写进契约由守卫重算比对。

b30112 的 9 个格 `lines_lost` 全为空、只多出 OO 新增行的 `GT-NEWROW-NO-UUID` —— 也就是说
row SDT 被剥离**没有**造成任何正文丢失，只是原本算在「SDT 内」的单元格文字变成了「SDT 外」。

### 7.5：跨 run、同段多 token、插删段落后仍可按 tag 读写

三种硬场景都落到了具体注入记录上（契约 `requirement_7_5_scenarios.instrumented` 逐条钉住
`doc / inj_id / run_split`）：

| 场景 | 注入记录 | 实测 |
|---|---|---|
| `cross_run` | f222/F02（3 run）、f223/G02（2 run） | tag 保留；**run 数被 OO 重排成 2**（见下） |
| `same_paragraph_multi` | f222/F03、f222/F04 | 同段两个独立 SDT 各自保留、互不吞并 |
| `duplicate_instance` | f222/F03、f222/F05 | 同 stable key 两实例都保留（实例计数不减） |

**插删段落后仍能按 tag 定位**：`insert_paragraph` / `delete_paragraph` 两格的 tag 集合与层级
全保留 —— 这正是「按 tag 读写」相对「按段落序号读写」的价值所在，下一节给反面对照。

---

## 5. 两个被证伪的锚点（附实测反例）

不是引用条文，是给反例。

- **段落绝对序号**：f222 文首插入 2 段后，同一 tag 的段落绝对序号整体位移
  （反例格 `f222/insert_paragraph`，26 个 artifact 里 1 个不稳定）。任何按段落序号定位的
  提取器都会读错字段 —— 这就是 Requirement 7.1 禁它的实证依据。
- **SDT 内 run 序号**：`gt:field:f2.stocktake.plan:plan/scope` 注入时切成 **3 个 run**，经 OO
  一次往返变成 **2 个 run**，内容不变。run 切分由 OO 自行重排 ⇒ 既不能作定位键，也不能作等值判据。

另两个「保留了但仍不可采纳」的，两个事实都要写：

- **`w:alias`**：26/26 保留，但它是可重复的展示字符串、审计师能在 OO 的内容控件设置里改名。
- **`w:id`**：26/26 未被 OO 重编号 —— 很容易被误当成可用锚点。但注入时故意给同一 stable key 的
  两个实例写了**相同**的 `w:id`（`gt:field:f2.stocktake.plan:plan/entity_name`），OO 原样接受 ⇒
  该值在本协议下不唯一，无法定位到具体实例。守卫
  `test_sdt_id_duplicate_claim_is_backed_by_instrumentation` 回注入清单核这两个 id 真的相等。

---

## 6. 权威模板未被改动的自证（三点交叉）

| 判据 | 结果 |
|---|---|
| 开工快照 `source_template_sha_before.json`（2026-08-24T23:18:07Z） | 3 份模板 sha256 已记录 |
| 收工快照 `source_template_sha_after.json`（2026-08-25T00:10:25Z） | 3 份**逐项相等**，`lock_files: []` |
| **本次会话重新实测**（`verify_task6_word_sdt_evidence.py` 直读 `backend/wp_templates/` 重算） | 3 份 sha256 与快照**全部一致** |
| `staging/{doc}_before.docx` 副本 sha256 | 3 份与权威模板**全部一致**（证明注入确实在副本上做） |

`~$` 锁文件检查为空，快照可信。守卫两条独立断言：
`test_authority_templates_were_not_modified_by_the_probe`（before/after 逐项相等）与
`test_template_shas_match_readonly_authority_source`（契约记录值 vs 当前磁盘实算）。
变异 M25（把契约里的模板 sha 改成全零）与 M36（伪造收工快照制造「被改过」形态）都被打红。

---

## 7. 独立重算：另一套实现交叉验证 26 个 artifact

`operation_matrix.json` 是探针自己的输出，用它验收探针属于被测方自证。
`backend/scripts/diagnose/verify_task6_word_sdt_evidence.py` **不 import 探针任何函数**，只吃
`staging/*_instrumented.docx`（基线字节）+ `artifacts/*.docx`（OO 回传字节），用另一套实现重算：

| 维度 | 探针实现 | 独立重算实现 |
|---|---|---|
| SDT 层级 | 按**父节点标签**（`w:body`/`w:p`/`w:tbl`/`w:tr`）判 | 按 **`w:sdtContent` 直接子节点形态**判 |
| SDT 外正文「行」 | 按单个 `w:t` 聚合 | 按**所属段落**聚合（对 run 重排更不敏感） |

结果：**26/26 artifact、5 项判据（tag 不减 / 层级保留 / row_uuid 不减 / SDT 外正文 / row 载体存活）
逐格比对，0 分歧**；artifact sha256 逐个重算与矩阵记录一致；基线 `document.xml` sha256 与
`instrumentation_report` 一致。落盘 `independent_recompute.json`。

重算过程中发现一处**我方 rollup 的缺陷并已修**：初版把 row 载体失败摊进了 field/block 桶，
导致「field/block SDT」被误报 FAIL。现在按 tag namespace（`gt:row:` vs 其余）分桶，并把
「差异只是 row 祖先被剥掉」的层级变化单列为 `row_strip_side_effect`；与探针比对时仍用**严格**
层级判据（row 祖先丢失也算回归），确保分桶不是偷偷放宽。

---

## 8. Playwright 实测截图（`screenshots/`）

9 张，全部是真实 OO 编辑器画面（非模拟）：

1. `01_f222_instrumented_opens_no_error.png` —— 注入后 OO 正常打开，无损坏提示
2. `02_f222_cross_run_and_same_para_edits_applied.png` —— 跨 run / 同段多 token 编辑生效
3. `03_f222_oo_renders_sdt_content_control_frame.png` —— OO 把 SDT 渲染成内容控件边框
4. `04_f222_reopen_tags_still_addressable.png` —— 重开后 tag 仍可定位
5. `05_b30112_row_sdt_rows_render_as_content_controls.png` —— 行 SDT 在 OO 里的渲染形态
6. `06_b30112_oo_inserted_row_has_no_row_uuid.png` —— **OO 新增行不带 row_uuid**
7. `07_b30112_row_sdt_deleted_via_context_menu.png` —— 通过右键菜单删行
8. `08_b30112_reopen_cell_field_sdt_still_addressable.png` —— 重开后单元格 field SDT 仍可定位
9. `09_f223_pilot_parity_edits_applied.png` —— 第二 pilot 结论一致

截图只作辅助，全部判据均以 artifact 字节为准（Requirement 14.14：截图不能替代逐 scenario 证据）。

---

## 9. 守卫与变异检验结果

守卫 `backend/tests/test_workpaper_word_sdt_carrier_contract.py`：**36 passed**。
每条裁决都从 evidence 目录**重新计算**，不采信契约里手填的数字或布尔。

变异 `python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --run all`：

| 态 | 数量 |
|---|---|
| **RED**（守卫有效，且命中声明的 `want`） | **38** |
| GREEN（守卫缺陷） | **0** |
| WRONG-TEST（污染残留 / 锚点错行） | **0** |
| ANCHOR-MISS（脚本缺陷） | **0** |
| ERROR | **0** |

锚点自检 `--check-anchors`：**38/38 唯一命中，0 MISS**，且跑完目标文件 md5 全不变、无 `.mutbak` 残留。
每条变异的备份还原都做 md5 逐字自证（`restored=true`）；跑完后 evidence 的 `generated_at` 仍是探针
原值，独立重算器复跑仍 0 分歧 ⇒ 变异未污染 evidence。

**「不是一改就红」的反向证据**两条：① 每条变异只打红 1–4 例（守卫共 36 例），且命中的正是声明的
`want`；② 守卫内 `test_negative_control_is_field_specific` 往契约副本塞未知键并断言判据**保持通过**
（放在守卫里而不是当 GREEN 对照变异，因为共享 kit 把 GREEN 一律判成守卫缺陷）。

### 首轮 3 GREEN + 1 ERROR 的逐条归因与收口

上一会话首轮 36 条跑出 RED 32 / GREEN 3 / ERROR 1。**没有直接采信**，逐条归因后补判据重跑：

| 变异 | 首轮 | 根因 | 收口 |
|---|---|---|---|
| M30 | GREEN | 守卫只断言 `intentional_deletions` 字典非空，键改名照样过 —— 键错了等于没声明，删行会被重新算成载体失效 | 补「键必须解析到真实 `doc/op` 格」+「逐行 `intentionally_removed_injections` 对齐」 |
| M31 | GREEN | 守卫只按行校验 `op_label_source`，不校验矩阵自述的 `op_label_policy`；自述改成「以 mark 为准」而 17 行仍标 `callback_userdata`，自相矛盾却无人打红 | 新增 `test_op_label_policy_statement_matches_observed_label_sources` |
| M34 | GREEN | 7.5 场景只比**全局集合**：f222/F02 的 `cross_run` 被改名后，f223/G02 仍贡献同名场景 | 契约新增 `requirement_7_5_scenarios.instrumented`（逐条 `doc/inj_id/run_split`），守卫按条比对；并补 M37/M38 给这段新声明本身上反向锁 |
| M29 | ERROR → 二轮 GREEN | ERROR = 备份文件被别的进程移走（`stale_backups()` 是全仓 `rglob`，别的 spec 跑变异时会互相干扰）。独占后重跑露出**真实缺口**：所有裁决都绕开 `tag_set_not_reduced` 直接重数，布尔本身没人校验，evidence 可以自相矛盾地躺着而下游会读它 | 新增 `test_evidence_derived_verdict_flags_agree_with_their_own_raw_measurements`，把 5 个派生布尔与各自原始测量锁死 |

净增 3 条守卫（33 → 36）、2 条变异（36 → 38）、契约 1 段新声明。

### 最贵的一条反向锁

**M01**：把 `row_sdt` 的 `probe_verdict` 从 `failed` 手改成 `passed`。若守卫放过，Tasks 59/61 就会
按 Requirement 7.2 的现设计去建 row-level 回写，整条 Word lane 返工。实测打红 4 例
（`test_row_sdt_carrier_is_disproven_by_evidence` / `test_downstream_gate_lists_exactly_the_passed_items`
/ `test_w_tag_anchor_scope_matches_carrier_verdicts` / 负向自检），且守卫是从 9 个 artifact 的
`tags_present` 重新数出「0 个保留 row tag」的。

---

## 10. Property 33 判定

**FAIL** —— 且失败点是**可定位的单一载体**，不是整个 tagged SDT 机制。

| Property 33 的三个子判据 | 结果 |
|---|---|
| tag 集合不减少 | field/block **26/26 通过**；**row 级 0/9，减少了 3 个 tag** ⇒ **不满足** |
| 层级不减少 | field/block 通过；b30112 的 field SDT 因 row 祖先被剥离而祖先链变空 ⇒ **不满足** |
| row_uuid 集合不减少 | **满足**，但只因注入时把 uuid 冗余双写进了单元格 field tag；**经由设计指定的 row 载体则是 0/9** |

按 Task 6 正文「失败时只回到 design 选择新稳定载体，不创建通用 Word engine；禁止 paragraph/regex
fallback」，本任务的正确产出是把失败事实固化，**不是**放宽判据让任务变绿。据此：

- **Word engine 门（`gates.word_engine = ["6"]`）对 field/block/SDT-外正文放行，对 row 载体阻断。**
  契约 `downstream_gate` 机器可读，守卫按裁决反算准入名单，不允许手写。
- **Requirement 7.2 需 design 修订**。已量到的候选（cell-level field SDT tag 携带 row_uuid）
  9/9 存活，可作修订输入；但采纳与否属 design 裁决，本 probe 不代替，也未写进 `carriers`。
- **Tasks 59/60/61/62/63/64 里任何依赖 row 级 SDT 的部分必须先过 design 换载体**，
  这句话写在契约 `downstream_gate.blocked_consequence` 里，随契约一起被守卫锁住。
- Requirement 7.6 的两个 pilot（F2-22 / F2-23）在 **field 载体维度全部通过**：打开、编辑、
  跨 run、同段多 token、插删段落、forcesave、下载、重开后 tag 与层级均未减少，
  且第二 pilot 结论一致（非单文档偶然）。design §OO 9.4 pilot 门 的第 6/7 步
  （extract/merge、二次 materialize 保留自由正文）不在本探针范围，由 Tasks 59/61 承接。

---

## 11. 复现步骤

```powershell
# 0. 核权威源未被改（开工）
python backend/scripts/diagnose/probe_oo94_word_sdt.py verify-source --stage before

# 1. 复制到 staging 并注入 field/row SDT + zip 级回读校验（--doc 可限定单份）
python backend/scripts/diagnose/probe_oo94_word_sdt.py instrument --run-id task6-r1

# 2. 起 document host + callback collector（端口 9995）
python backend/scripts/diagnose/probe_oo94_word_sdt.py serve --doc f222 --doc-key t6f222r1

# 3. 浏览器开 http://127.0.0.1:9995/editor，逐操作执行；每步之后：
#    python ... mark --op <op>                              # 贴操作标签（仅兜底）
#    python ... command --c forcesave --userdata op-<op>     # userdata 才是标签权威
# 4. reopen：用上一轮 status 2 artifact 作宿主文档重开
#    python ... serve --doc f222 --doc-key t6f222r2 --seed artifacts/f222_reopen_cb08_status2.docx
# 5. 汇总操作矩阵 + build 信息 + 收工核权威源
python backend/scripts/diagnose/probe_oo94_word_sdt.py analyze
python backend/scripts/diagnose/probe_oo94_word_sdt.py build
python backend/scripts/diagnose/probe_oo94_word_sdt.py verify-source --stage after

# 6. 独立重算（不 import 探针，交叉验证 26 个 artifact）
python backend/scripts/diagnose/verify_task6_word_sdt_evidence.py --write

# 7. 守卫 + 变异检验（变异期间 evidence 目录必须独占）
python -m pytest backend/tests/test_workpaper_word_sdt_carrier_contract.py -q
python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --check-anchors
python backend/scripts/diagnose/mutate_task6_word_sdt_guards.py --run all `
  --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task6-oo94-word-tagged-sdt/mutation_report.json
```

### 两个复现陷阱

- **变异期间 evidence 目录必须独占**：`_mutation_kit` 的 `stale_backups()` 是全仓 `rglob("*.mutbak")`，
  别的 spec 正在跑变异时本 harness 会直接 ABORT；反过来，本 harness 跑到一半时若有人动
  evidence JSON，会得到 M29 首轮那种 `FileNotFoundError` 假 ERROR。**判成败一律看四态统计，
  不看退出码。**
- **别用 PowerShell 的 `Get-Content | Set-Content` 改含中文的脚本**：会把 UTF-8 中文腌成乱码并加
  BOM（本次收口时踩过一次，靠 Kiro local history
  `%APPDATA%\Kiro\User\History\<hash>\entries.json` 恢复）。改文件一律用编辑器工具或
  Python `Path.write_bytes`。

---

## 12. Evidence 文件清单

| 文件 | 说明 |
|---|---|
| `findings.md` | 本文件 |
| `run_meta_f222.json` / `run_meta_f223.json` / `run_meta_b30112.json` | 每份文档的运行元数据（doc_key、staged sha、声明操作序、前序 run） |
| `oo_build.json` | 容器内 `dpkg -l` 实测 build（9.4.0-129）+ endpoint 探测 |
| `instrumentation_report.json` | 注入清单（field/row 逐条 tag、sdt_id、run_split、scenario）+ 注入前后清册 + zip 回读校验 |
| `operation_matrix.json` | 26 个 artifact × 4 载体 × 5 锚点逐格实测 + 覆盖面 + 有意删除声明 + 基线一致性 |
| `independent_recompute.json` | 独立重算器输出（另一套实现，0 分歧） |
| `mutation_report.json` | 38 条变异四态结果 |
| `source_template_sha_before.json` / `source_template_sha_after.json` | 权威模板开工/收工 sha 快照 |
| `callbacks.jsonl` | 29 条 OO callback（脱敏 URL） |
| `commands.jsonl` | 21 次 Command Service forcesave 请求/响应 |
| `staging/*_before.docx`（3） | 权威模板的只读副本 |
| `staging/*_instrumented.docx`（3） | 注入后的隔离副本（探针基线） |
| `artifacts/*.docx`（26） | 真实 OO 回传件 / 编辑器另存件 |
| `screenshots/*.png`（9） | Playwright 驱动真实 OO 编辑器的实测截图 |

配套代码（均在 evidence 目录之外）：

- `backend/data/onlyoffice_word_sdt_carrier_contract.json` —— 载体真值表（单一真源）
- `backend/tests/test_workpaper_word_sdt_carrier_contract.py` —— 守卫 36 例
- `backend/scripts/diagnose/probe_oo94_word_sdt.py` —— 探针
- `backend/scripts/diagnose/verify_task6_word_sdt_evidence.py` —— 独立重算器
- `backend/scripts/diagnose/mutate_task6_word_sdt_guards.py` —— 变异 runner 38 条
