# Requirements Document

## Introduction

本 spec 只做一件事：**让审计师能在 OnlyOffice 里编辑底稿 Excel 模板，同时权威模板目录保持运行时只读、跨 sheet 公式关联一个字节都不损失。**

做法是把「编辑模板」从"改那份权威文件"改成"在权威文件之上叠一层可版本化的覆盖"：权威目录 `backend/wp_templates/` 保持字节冻结，编辑产生的新 xlsx 落在覆盖层，`wp_template_finder` 增加一级优先解析。于是「运行时只读」（Requirement 9.9）与「模板可编辑」不再互斥 —— 前者约束的是一个**具体目录**，后者需要的是一个**解析结果**，二者可以解耦。

编辑器本体不新造：复用已交付并实测无损的 OnlyOffice 整本模式（`whole_workbook=true` + `excel_sheet_visibility` 的 zip 级可见性）。**不使用 Univer 或任何前端 xlsx 解析库**参与模板落盘。

## Glossary

| 术语 | 含义 |
|---|---|
| 权威模板目录 | `backend/wp_templates/`，476 条索引，运行时只读（Requirement 9.9） |
| 覆盖层 | `backend/storage/template_overrides/`，编辑产物的落点，可版本化 |
| 作用域 | 覆盖生效范围，复用既有 `TemplateLevel` 枚举：`firm_default` / `group_custom` / `project` |
| 解析优先级 | `project` > `group_custom` > `firm_default` > `authoritative` |
| 来源标记 | 解析结果附带的 `origin` 字段，指出这份模板来自哪一层 |
| 当前版本 | 某作用域下 `is_current=true` 的那一条，唯一，参与解析 |
| 跨 sheet 引用 | 形如 `'明细表K11-2'!F29` 的公式引用；351 份 xlsx 里 188 份含，共 81,955 处 |
| 无损 | 除 `xl/workbook.xml` 外全部 zip 部件字节不变 |

## 背景与既有事实

动手前实测到的既有事实（每条都是判据的地基，不得凭印象改写）：

| 事实 | 取证方式 | 值 |
|---|---|---|
| 权威模板目录 | `backend/wp_templates/` | `_index.json` 476 条：xlsx 349 / docx 107 / xlsm 17 / doc 2 / xls 1；类别 A 99 / B 138 / C 36 / D-N 113 / S 90 |
| 权威目录的写入路径 | 全 `backend/app/**/*.py` 扫描含 `wp_templates` 且含 write/save/copy/unlink/mkdir/open 的行 | **0 条真实写入**（仅 1 条注释误命中）⇒ Requirement 9.9「运行时只读」在实现上成立 |
| 模板解析器 | `backend/app/services/wp_template_finder.py`（374 行） | **纯文件系统**：`session` / `db` / `WpTemplate` 各出现 **0** 次；唯一根常量 `TEMPLATES_DIR`（L19）；三个公开入口 `find_template_file` / `find_all_template_files` / `find_template_file_any` |
| 模板在 DB 里的形态 | `workpaper_models.WpTemplate` | 存 `file_path: String`，**不存文件内容**；有 `version_major` / `version_minor` / `status` 但解析时不被读 |
| 模板库 | `template_library_models.TemplateLibraryItem` | 同样 `file_path: Text` 指向文件 |
| OO 整本编辑 | `GtWpRenderer.vue` L524-537 注入「完整Excel」合成页签；`GtOnlyOfficeSheet.vue` L176 `whole_workbook=true`；router L690 `visible_sheet=None`、L797 不加 actionLink | **已端到端接通** |
| 跨 sheet 引用规模 | 351 份 xlsx 全扫 | 含跨 sheet 引用 **188 份（53.6%）**、引用总数 **81,955**、表名形如 A1 引用 **16,027 次** |
| sheet 可见性 | `excel_sheet_visibility`（本 spec 前置，已交付） | zip 级只改 `xl/workbook.xml`；K11 九步切换序列 **11 项指标 0 漂移**；全模板库 **314 份多 sheet 模板全通过** |

因此「编辑模板」的实质是：**往某处写一份新 xlsx，并让 finder 解析到它**。

---

## Requirements

### Requirement 1: 权威模板目录在任何编辑路径下都不被写入

**User Story:** 作为质量控制复核合伙人，我需要权威模板目录始终是冻结基线，否则「所有项目所有底稿的生成基线」会变成可被单个用户改动的东西。

#### Acceptance Criteria

1.1 覆盖层的任何写入操作，其目标路径都不得落在 `TEMPLATES_DIR` 之下；越界时抛可编程异常而非静默改路径。

1.2 存在一条判据，对覆盖层全部写入函数做 AST 级扫描，证明没有任何一处把 `TEMPLATES_DIR` 直接或经拼接后当作写入目标。

1.3 编辑一次模板后，`backend/wp_templates/` 下全部 476 个文件的 size 与 sha256 逐份不变。

1.4 判据 1.3 必须有变异检验：故意把覆盖层根指向 `TEMPLATES_DIR` 时判据必须打红。

1.5 覆盖层根目录由单一常量声明，且该常量与 `TEMPLATES_DIR` 的关系被断言为「互不包含」。

---

### Requirement 2: 覆盖层解析优先于权威目录，且优先级可解释

**User Story:** 作为现场经理，我需要知道某个底稿到底用了哪一份模板，否则出了差错无法追溯。

#### Acceptance Criteria

2.1 `wp_template_finder` 的三个公开入口在覆盖层存在同 `wp_code` 文件时返回覆盖层路径，否则返回权威路径。

2.2 解析结果附带来源标记（`authoritative` / `override`），调用方可读；不得只返回一个裸 `Path` 让调用方猜。

2.3 覆盖层不存在任何文件时，三个入口的返回值与本 spec 前的返回值**逐份相同**（零回归）。判据须对全部 476 条索引逐条比对。

2.4 覆盖层解析支持四层优先级：`project` > `group_custom` > `firm_default` > `authoritative`。作用域取值**复用既有 `TemplateLevel` 枚举**（实测：平台无独立事务所实体，但该枚举已定义这三档），不新造词汇。同一 `wp_code` 在多层存在时取最靠前的一层，且来源标记指出是哪一层。

2.5 判据 2.4 必须构造四层同时命中的场景，证明取的是 `project`；再逐层撤掉，证明依次回落到 `group_custom` → `firm_default` → `authoritative`，每步断言 `origin` 与 `sha256`。

2.6 覆盖层文件的扩展名必须与被覆盖的权威文件一致（不得用 xlsx 覆盖 docx），否则拒绝并给出 error_code。

---

### Requirement 3: 编辑经 OnlyOffice 整本进行，跨 sheet 关联零损失

**User Story:** 作为审计助理，我需要在编辑模板时看到全部 sheet 与 sheet 间公式，否则改一处会静默打断取数链。

#### Acceptance Criteria

3.1 模板编辑会话走 OnlyOffice，`whole_workbook` 语义为真：全部 sheet tab 可见、不加 actionLink。

3.2 编辑会话建立前后，模板文件除 `xl/workbook.xml` 外全部 zip 部件字节不变（复用 `_assert_only_workbook_part_changed`）。

3.3 编辑落盘后，跨 sheet 引用集合（形如 `'明细表K11-2'!F29` 的去重集合）与编辑前逐项相同，除非用户显式改了公式本身。

3.4 编辑落盘后，共享公式主格数、非空缓存值数、`printerSettings` 部件数、`worksheets/_rels` 部件数、样式索引序列均不得因「保存这一动作本身」而变化。

3.5 判据 3.3 与 3.4 必须在**含跨 sheet 引用的真实模板**上取证，且模板选取有明确理由（不得挑一个恰好没有跨 sheet 引用的）。

3.6 不得引入任何非 OnlyOffice 的 xlsx 读写中间层（Univer / openpyxl 全量重写 / exceljs 再导出）参与模板落盘路径。

3.7 判据 3.6 必须是行为级或 AST 级，不能只查字符串存在。

---

### Requirement 4: 模板编辑有版本与回滚，不是就地覆盖

**User Story:** 作为 EQCR 技术复核人，我需要能看到模板改了什么、谁改的、并能退回上一版。

#### Acceptance Criteria

4.1 每次保存产生一个新版本条目，记录 `wp_code` / 作用域 / 作者 / 时间 / 文件 sha256 / 父版本。

4.2 覆盖层解析取的是该作用域下的**当前版本**；非当前版本仍可读但不参与解析。

4.3 回滚 = 把某个历史版本置为当前，**不删除**任何版本记录。

4.4 同一 `wp_code` 同一作用域在任一时刻只有一个当前版本；判据须在并发写入下验证该唯一性。

4.5 删除覆盖 = 该作用域下不再有当前版本，解析回落到下一层；判据须证明回落后拿到的是权威文件本身（sha256 相等）。

---

### Requirement 5: 编辑入口挂在既有模板界面，不新造孤岛

**User Story:** 作为审计助理，我需要在看模板的地方就能编辑它。

#### Acceptance Criteria

5.1 入口挂在 `components/template-library/WpTemplateDetail.vue`（现有 335 行，已含预览 / 下载 / wp_code / sheet 展示），不新建平行的模板管理页。

5.2 **浏览器内编辑**入口仅对 xlsx 可用（349 份）；对 docx / doc / xls / **xlsm** 置灰，但同一界面 SHALL 提供**上传替换**入口，使这 127 份同样能产生覆盖版本（见 Requirement 7.2 的覆盖面表）。置灰处必须说明原因而不是只是不可点。

xlsm 被排除的实测理由：索引声明的 17 份 xlsm **全部（17/17）含 `vbaProject.bin`**，而 OnlyOffice 往返是否保留 VBA 未取证 —— 在没有证据前放进可编辑集合等于赌它保留。放开条件：在真实 xlsm 上实测「OO 打开→保存后 `vbaProject.bin` 字节不变」，并把该断言固化为常驻判据。

5.5 上传替换入口 SHALL 走与浏览器内编辑**同一条**落盘与版本化路径（`stage_override` + 版本表），不得另开一条绕过越界门与扩展名门的通道。

5.3 界面显示当前解析来源（权威 / 事务所 / 项目）与版本号，且该显示取自后端下发的来源标记而非前端推断。

5.4 UI 全中文；状态用彩色 tag 不用裸英文；符合平台表格 UI 铁律。

---

### Requirement 6: 模板改动对已生成底稿的影响必须显式

**User Story:** 作为业务合伙人，我需要知道改模板会不会动到已经做完的底稿。

#### Acceptance Criteria

6.1 保存模板覆盖时，返回受影响面：该 `wp_code` 下已存在的底稿数量（按项目分组）。

6.2 明确声明本 spec **不**回溯改写已生成底稿；已生成底稿继续用它自己的文件。

6.3 判据 6.2 必须验证：保存覆盖后，随机抽取的既有 `working_paper` 文件 sha256 不变。

---

### Requirement 7: 范围边界

**User Story:** 作为业务合伙人，我需要范围边界写进需求并各自说明理由，以便后续不因失焦把独立劳动量并进来。

#### Acceptance Criteria

7.1 本 spec **不**改 `backend/wp_templates/` 的任何字节。
7.2 本 spec **不**处理 docx / doc / xls / xlsm 模板的**浏览器内编辑**。
🔴 **但覆盖层本身是格式无关的**，不要把 7.2 误读成「非 xlsx 模板不能覆盖」。Requirement 2 的解析链与 Requirement 4 的版本化对全部 476 条索引一律生效（xlsx 349 / docx 107 / xlsm 17 / doc 2 / xls 1），只要覆盖文件的扩展名与权威文件一致（Requirement 2.6）。差别只在**产生覆盖文件的方式**：
| 格式 | 覆盖层解析 | 版本化 / 回滚 | 浏览器内编辑 |
|---|---|---|---|
| xlsx（349） | ✅ | ✅ | ✅ OnlyOffice 整本 |
| docx / doc（109） | ✅ | ✅ | ❌ 需上传替换；Word 编辑器是另一条路（主 spec R7 的 SDT 结构化编辑管的是**底稿**不是模板），单独立任务 |
| xlsm（17） | ✅ | ✅ | ❌ 17/17 含 `vbaProject.bin` 且 OO 保留性未取证（Gate 3），取证后可放开 |
| xls（1） | ✅ | ✅ | ❌ 二进制老格式，非 OOXML |
于是「模板可被覆盖与版本化」的覆盖面是 **476/476**，「可在浏览器里直接编辑」的覆盖面是 **349/476**；剩下 127 份走上传替换，同样进版本表、同样可回滚。
7.3 本 spec **不**引入 Univer 或任何前端 xlsx 解析库参与模板落盘。
7.4 本 spec **不**回溯改写已生成底稿。
7.5 本 spec **不**改 `wp_template` / `template_library` 表已有列的语义；新增能力用新表承载。
7.6 本 spec **不**处理模板的审批流（谁有权改）—— 沿用既有权限体系，不新造审批状态机。
