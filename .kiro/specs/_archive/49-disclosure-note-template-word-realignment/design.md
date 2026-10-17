# 设计：附注模板按四版 Word 重新对齐

## 1. 总体顺序

```
Phase 1 比对工具（只读）──► Phase 2 种子修复 + 编号别名 + 衍生数据 ──► Phase 3 存量项目修复
                                         │
Phase 4 编辑留痕（独立）   Phase 5 大模型手动化（独立）──► Phase 6 和平药房重建（依赖 2 / 3 / 5）
```

Phase 4、5 与种子无关，可穿插。Phase 6 必须在种子修好、生成链不再调大模型之后做，否则重建出来的仍是旧树和大模型正文。

## 2. 比对工具 `backend/scripts/check/check_note_template_word_tree.py`

只读，不连库。解析与比对逻辑在 `backend/app/services/note_word_tree.py`（章节树）与 `note_word_table.py`（表格）（docx 延迟导入，请求期不调用；先例 `note_section_kind.build_kind_index_from_word`），命令行、种子修复器与守卫测试共用。

### 2.1 Word 侧

- 逐个遍历 body 子元素（段落与表格按文档顺序，内容控件 `w:sdt` 下钻），段落样式 `Heading N` / `标题 N` 取层级，复用 `note_section_kind._heading_level`。
- 模板标记不是内容：`##SECTION:…##`、`##STYLE_REF:…##`、`{{seq:七}}`、`{{section:…}}`、`{{table:…}}` 从段落文字中剔除，剔除后为空的段落跳过（不进正文、不当表前段落）。
- H1 = 章。节层级：上市恒为 H2；**国企逐章取本章出现的最高一级（H2 或 H3）**——第七章「企业合并及合并财务报表」节是 H2、其下 H3（少数股东 / 主要财务信息…）是节内小标题，第四、八章节是 H3。更深的标题记为所在节的小标题。
- 标题比对键 = `normalize_title`，另去掉模板占位序号「X、」（「X、数据资源」）。
- 表格归属：节标题之后、下一个节或章标题之前的表格属于该节；章标题与第一个节标题之间的表格属于章正文。
- 每张表抽取：表前最近的非空段落、逻辑列数、表头行数、每列表头路径（自上而下的非空表头文字）、首列行标签。合并单元格按 OOXML `gridSpan` / `vMerge` 解析。
  - 表头行数：沿用 `sync_note_templates_from_word.detect_header_row_count` 的规则，多一条「横向合并的分组表头之下必有一行子表头」。原规则把首列未纵向合并的两级表头（「账龄」下格留白）判成一行，实测漏掉国企 八、5 / 八、9 两张表的真实列差异。
  - 逻辑列：相邻网格列在全部表头行属于同一单元格 ⇒ 并为一列（Word 手工拆格常多出网格列）。
  - 表头里的留白单元格不算一级。
- 节正文：节标题之后、第一张表之前的非标题段落，供补节时生成 `text_sections`。

### 2.2 种子侧

- 读 `note_template_{std}.json` 的 `sections`，按 `sort_index` / `sort_order` 排序，`level=1` 为章、`level=2` 按 `parent_section_id` 归章。
- 每个口径先按 `section_applies_to_scope` 过滤，再与该口径 Word 比对；节匹配时另查全部 scope 的节，用于判断 scope 是否填错。

### 2.3 配对规则

1. 章配对：规范化标题相同 → `note_section_kind.WORD_TITLE_ALIASES` 章名别名 → 种子章的首节（章正文叶子）标题等于 Word 章名（国企十三 / 十四、上市十：种子章名错、叶子用的是 Word 章名）→ 两侧对上的节最多的章 → 仍对不上记为单侧章。
2. 节匹配：① 已配对章内规范化标题相同，同名多节按出现顺序一一对应；② 剩余的跨章找同名（放错章），同名多节优先本口径适用的；③ 已配对章内，以对上的节为锚点，两侧锚点之间的未匹配节按序找标题相似的一一对应（较短一方 ≥4 字被另一方包含，或相似度 ≥0.8；「营业收入与营业成本 / 营业收入和营业成本」0.89 命中，「其他应收款 / 应收账款」0.67 不命中），记 `section_title` 差异。
3. 章正文叶子：未匹配的种子节标题等于所属章或所配对 Word 章的标题（「X、1 章名」）⇒ 对应 Word 的章正文，不当作多余节。
4. 顺序：每章内对上的节按 Word 顺序取最长递增子序列，不在其中的记为顺序错。

### 2.4 差异类别

| kind | 含义 |
|---|---|
| `chapter_title` | 配对章标题不同 |
| `chapter_missing` / `chapter_extra` | Word 有种子无 / 种子有 Word 无 的章 |
| `chapter_order` | 章顺序不同 |
| `misplaced` | 节在种子的 A 章、Word 的 B 章 |
| `word_only` | Word 有、种子无的节 |
| `json_only` | 种子有、Word 无（子类：`guidance` 标题以【开头 / `other`） |
| `scope` | 节的 scope 与它在单体 / 合并 Word 中的出现情况不符 |
| `order` | 章内节顺序不同 |
| `section_title` | 节对上了但标题不同（截断、措辞） |
| `table_count` / `table_columns` / `table_headers` / `table_rows` | 表格差异：按表序逐张比表数、逻辑列数、每列表头路径（分组 + 列名；种子「中级-叶」与 Word 三级表头视为同一路径）、行标签（忽略「……」「可无限量添加行」、纯序号占位行与尾部冒号） |
| `seed_*` | 种子自身问题：缺 scope、父节点解析不到、同号、同 section_id |

不比表名：Word 表前段落多为编制指引或「续：」，不是表名。种子把部分宽表拆成「期末 / 续：期初」两张（`continuation_of_index`），差异照实报出；同一标记在种子里也用于「后续采用总额法 / 净额法」这类并列表，按续表并组试过，误报从 96 / 20 升到 117 / 30，已放弃。

每条差异的键 = `(variant, kind, 种子编号或 Word 标题, 表序)`，输出按键排序，无时间戳。

### 2.5 命令行

- 默认打印各口径各类计数 + 每条差异一行。
- `--json <path>` 写完整报告（用于审阅，不入库）。
- `--check`：存在白名单外差异或白名单失效条目 ⇒ exit 2 并点名。白名单 `backend/data/note_template_word_alignment_allowlist.json`：`{variant, kind, key, reason}`，理由必填。
- 守卫 `backend/tests/test_note_template_word_tree_alignment.py` 在进程内调用同一函数。Phase 1 交付时差异真实存在：守卫用 `xfail(strict=True)` 标明「Phase 2 修复前」，Phase 2 修完删掉标记转为真绿。不把现状差异写进白名单充当通过（假绿）。另有不带 xfail 的工具自检用例（合成 docx：放错章 / 缺节 / 多节 / 表头差异各能检出）。

## 3. 种子修复 `backend/scripts/seed/realign_note_templates_to_word.py`

输入 = 比对结果，输出 = 修改后的两份种子。`--check`（会改动则 exit 2）/ `--write`；对当前文件重放，第二次运行无改动。

### 3.1 章

- 章名改为 Word 章名。章名随口径不同（上市项目附注章）时，`section_title` 取合并版名称，另加 `scope_titles: {"standalone": "财务报表项目附注"}`；生成链与目录树按项目口径取名。
- Word 有、种子无的章：按 Word 位置插入，编号取未用的章号（不重排已有章号）；单体 / 合并 Word 都没有的种子章按 §3.3 处理其下的节后删除。
- 章 scope 由其下节的 scope 推出（有 both 节即 both）。

### 3.2 节

- **放错章**：`parent_section_id` 改为 Word 所在章；编号前缀改为新章号：
  - 目标章现有编号全是数字（`五、12`）⇒ 取 `{章}、{该章已用最大数字 + 1}`，按 Word 顺序依次分配；
  - 否则保留旧编号「、」之后的部分，只换前缀（`三、本公司的母公司情况` → `十一、本公司的母公司情况`）；冲突时加「（2）」。
  - 「已用」包含该章当前编号与所有 `legacy_section_numbers`。国企「五」章不分配数字编号（数字 `五、N` 是旧国企科目编号的别名，会被归一到 `八、N`）。
  - 旧编号追加到 `legacy_section_numbers`（列表，保持顺序）。`section_id` 不变。
- **Word 有、种子无**：新建节。`section_id` 用现有 slug 规则（`chapter-NN-{章拼音}-{节拼音}`）且全种子唯一；`section_title` / `account_name` = Word 标题；`content_type` 有表为 `mixed`、无表为 `text`；`text_sections` 取 Word 节正文段落；表格按 §3.4 由 Word 生成；`scope` 按 §3.2 末条。
- **种子有、Word 无**：标题以「【」开头的提示语节删除（其正文并入同章前一节的 `text_sections`，不丢文字）；章正文叶子保留；其余逐条列入白名单或删除，需在 tasks.md 写明依据。
- **scope**：只在合并版出现 ⇒ `consolidated_only`；两版都出现 ⇒ `both`；只在单体版出现 ⇒ `standalone_only`。
- **顺序**：每章内 `sort_index` / `sort_order` 按 Word 顺序重写（两版顺序不同时以合并版为准，单体版的相对顺序须与之一致，不一致的报差异）。

### 3.3 表格

- 对上的节按表序逐张比：表名、列数、叶子表头、多级表头分组（写入 `columns[].group` 与 `_column_groups`）、行标签。
- 只改展示结构。列数不变时按位置改 `label` / `group`，保留 `key` / `format` / `is_label`；列数变化时按「表头文字」把旧列对应到新列，对不上的新列生成新 `key`（`col_{序号}`），删掉的列记入报告。
- 行标签按「规范化文字」对应：保留旧行的 `row_type` / `is_total` / `report_row_code` / `account_codes` / `values`；Word 新增的行按 Word 生成（合计类标签置 `is_total`）。
- 表数量不同：缺的表按 Word 生成追加，多的表列入报告（多为续表 `continuation_of_index` 或额外表，逐条判定后进白名单或删除）。
- 并发会话的逐循环表格脚本（`fix_note_*_structure.py`，来源是底稿模板 xlsx）改过的表若与 Word 不一致，以 Word 为准；冲突逐条写进 tasks.md。

### 3.4 编号别名

- `note_section_catalog.normalize_section_code` 增加一层：先查 `legacy_section_numbers` 构成的「旧编号 → 新编号」表（两个准则都查），再走国企「五、N → 八、N」。别名表在种子加载时构建（`lru_cache`）。
- 别名不得与任何现行编号相同（工具与守卫都检查），否则旧编号会把现行节吞掉。

### 3.5 衍生数据与引用

种子写入后依次重生成并各自 `--check`：`build_section_code_index.py --all-poc --write` + `validate_section_code_index_consistency.py`、`scripts/generate_note_template_bindings.py`、`gen/generate_note_formula_data.py`、`gen/generate_note_soe_listed_diff.py`、`gen/gen_note_shared_table_segments.py --write`、`gen/gen_note_section_kind_index.py`、`gen_note_wp_sync_registry.py --write`（源是前端 `*NoteSectionMap.ts`，先改映射再生成）。

无生成器、按编号引用的文件由 `backend/scripts/migrate/rename_note_section_codes.py` 按「旧 → 新」表做**整串精确替换**（键与值都替换，`note://{旧编号}/` 前缀同样替换）：`formula_push_rules.json`、`wp_account_mapping.json`、`note_template_variant_matrix.json`、`note_columns_rules.json`、`note_guidance_rules.json`、`note_table_name_corrections.json`、`note_table_headers_source_facts.json` 等 `backend/data/note_*.json`，以及前端 `*NoteSectionMap.ts`、`noteDisclosureJump.ts`、`noteDisclosureReverseJump.ts`、`useNoteRefresh.ts`、`DisclosureEditor.vue`。文件清单由工具扫描得出（扫描全部 `backend/data/*.json` 与前端源码中出现的旧编号），不写死；`--check` 报告剩余旧编号所在文件。`note_template_bindings_backup`、迁移历史与 spec 文档不改。

## 4. 存量项目修复 `backend/scripts/fix/realign_project_notes.py`

参数：`--project <id> | --all-targets`、`--year`、`--dry-run`（默认）/ `--apply`、`--backup-dir`。每个项目一个事务；写入前把该项目该年度的 `disclosure_notes`（含软删）、`formula_push_state`、`note_section_instances` 导出到 `backend/backups/note_realign_{项目}_{时间}.json`。

### 4.1 计划

1. **改编号**：行的 `note_section` 在别名表中 ⇒ 改为新编号。新编号已被同项目同年度任何行占用（**含软删行**：唯一索引 `uq_disclosure_notes_project_year_section` 不排除软删）⇒ 不改，记冲突交人工（不合并两份内容）。
2. **树字段**：按种子（项目口径过滤后）重写 `parent_section_id`、`level`、`sort_index` / `sort_order`、`section_id`、`section_title`（仅当行标题等于该节某个已知标题——现名、口径名、`legacy_titles`；用户改过的标题不动）。`section_id`（实施时细化）：对上模板的行一律对齐模板 —— 子节点的上级按模板写，上级不对齐树就断；目标 id 被别的行占着且那一行不会让出时不改并报告；挂在被对齐行下面的自建节，上级跟着改。
3. **补章节**：种子中适用本口径、项目没有的节，走生成链 `generate_notes(only_sections=…, strict=True)` 插入（与新生成项目一致：正文 = 上年附注 → 模板正文，表格按试算表取数，`status=draft`，不调大模型；实施时由「空章」改为此口径，避免存量项目与新项目同一节内容不同）。编号被软删行占着 ⇒ 不补（用户删除 / 裁剪过，回收站可恢复）。生成链本身同步修：遇到软删编号原来会 INSERT 撞唯一索引（删章 / 裁剪后再生成整次 500），改为跳过。已删除（回收站）的项目整体跳过：生成链取不到其口径。
4. **表格结构**：见 4.2。
5. **脱树旧行**：编号不在种子（含别名）且父节点不存在的行。规则：能按「规范化标题 + 所属章类型」唯一对上种子节、且该节在项目内无活动行 ⇒ 改挂为该节；对上但该节已有行 ⇒ 不动，报告两行内容差异；对不上 ⇒ 不动，报告。脱树行一律不删除（删除只在用户确认后由单独命令执行）。
6. **关联表**：`formula_push_state.note_section` 与 `addr_id` 中 `note://{旧}/` 前缀（新 `addr_id` 撞唯一索引则不改并报告）、`note_section_instances.section_number`、未释放的 `note_section_locks`，按同一「旧 → 新」表（改编号 + 改挂）改写。`wp_template_metadata.note_section` 是模板级、无项目维度且库内 0 行有值，不在逐项目修复范围。`note_section_instances.section_number` 为 `String(20)`，新编号超长时先迁移放宽列宽（`V188` / `R188`，与 `disclosure_notes.note_section` 同为不限长 `String`），不截断。
7. 不改写：`note_validation_findings`、`note_text_batch_applications.detail`、trace 事件、`deliverable_section_state`（历史留痕，按旧编号记录是事实）。

### 4.2 表格结构

- 先量化：逐项目逐表比较库内 `table_data` 结构（表名、列元数据、表头、行标签）与修复后种子表，分「一致 / 仅表头文字不同 / 列增减 / 行增减 / 表数不同」五类计数，写进 tasks.md。
- 读时增强 `note_table_enrichment` 已按模板回填表名、表头、列分组、行类型的部分，确认其在新种子下输出与种子一致后，库内只改它覆盖不到的部分；两者口径不一致时以本工具写库为准，并让读时增强在结构已一致时为空操作（守卫断言）。
- 写库时按新种子表重建结构，旧单元格按（规范化行标签，列 key；key 对不上时按表头文字）搬入，`_cell_modes` / `_cell_meta` 随值搬。搬不进的值（行或列在新结构中不存在）写入报告并保留在 `table_data._realign_orphans`（不显示、不导出），用户确认后再清。
- 不用生成链的三态合并：它对 auto 单元格取新算值，结构修复时新值为空，会把数清掉。

### 4.3 验证

- dry-run 报每个项目各类计数；`--apply` 后再 dry-run 必须为空（幂等）。
- 写入前后对每个项目算「非空单元格值的多重集合」，必须相等（减去报告里的孤儿值）；正文哈希逐行相等。
- 浏览器：每个准则至少一个项目，章节树顺序对照 Word，抽三张多级表头表核对表头与数值。

## 5. 编辑留痕（「最近一次编辑」）

盖章函数：`note_edit_stamp.stamp_note_edit(note, user_id)`（逐行）/ `stamp_section_edit(...)`（按章）。写入方都要拿到当前用户；router 没有 `current_user` 的先补鉴权依赖。

| 写入方 | 现状 | 改动 |
|---|---|---|
| `note_prior_year_import_service.import_from_docx` / `inherit_from_prior_year` | 不盖章；`note.title` AttributeError、`_extract_to_opening_balance` 不存在、年度写死 2025；路由 `note_advanced.py` 无鉴权无用户 | 路由补项目 edit 鉴权与 current_user；修三处缺陷；写入行盖章 |
| `group_note_baseline_service.apply_baseline` | 写 updated_at 不写 updated_by | 盖章（路由已有 current_user） |
| `note_group_template_service._upsert_section` | 裸 SQL；覆盖分支；把层级字母写进 `level` | 覆盖分支同时写 updated_by / updated_at；`level` 写数字层级 |
| `triple_format_adapter.update_note_from_structure`（路由 `excel_html.save_edits`） | 不盖章 | 盖章 |
| `note_offline_import_service._persist_guidance_from_meta` | 不盖章；路由不 commit | 盖章；路由统一 commit |
| `note_wp_mapping_service.toggle_cell_mode` | 原地改 JSONB 无 `flag_modified`（不落库）；按 ID 不校验项目 | 新对象赋值；校验行属本项目；盖章 |
| `recycle_bin.restore_item`（附注） | 注册表引用不存在的 `section_code` | 改用 `note_section`；恢复时盖章 |
| `procedure_trim_note_linkage.apply_note_linkage` | 不盖章 | 盖章（用户裁剪程序触发） |

不盖章（系统路径）：生成、刷新、交叉引用重算（`note_cross_reference_service`）、国企↔上市转换（`note_conversion_service`）、`report_note_sync_service`、过期标记、公式推送。`formula_push/engine.py` 事件推送把 `updated_by` 置 NULL ⇒ 改为不动 `updated_by`；`formula_runtime/adapters/note.py`、`note_template_reflow_service` 同样只许不动，不许清空。

守卫：`test_disclosure_note_edit_stamp.py` 由「只扫 `routers/disclosure_notes.py`」扩为「表中每个写入函数的 AST 里必须调用盖章函数」+「系统路径不得出现 `updated_by = None`」。另每个写入方一条行为测试（真 SQLite + 真 ORM，断言 updated_by 为操作人）。

实施补充（2026-10-16，与上表的差异）：

- 公式推送：用户点推送（`triggered_by` 有值）记推送人，事件触发不动编辑人；`updated_at` 照写（与 `last_sync_at` 同值）。守卫允许的唯一写法是 `if X is not None:` 真分支里 `y.updated_by = X`。
- 单元格模式切换：除上表三项外，原实现把单元格换成 `{"value", "mode", "manual_value"}` 字典塞进 `values`，没有任何读取方认这个形态（模式边车是行级 `_cell_modes`，按列索引建键）—— 只修「落库」会让这个坏形态真的写进库 ⇒ 一并改为写边车、人工值写回 `values`；路由由「仅登录」升为项目 `edit` 权限（校验行属本项目的前提）。
- 集团模板下发：裸 SQL 只能在真 PostgreSQL 上验（SQLite 下 `str(uuid)` 与 ORM 存储形态不一致、也不拒绝字母写进整数列）⇒ 行为测试走 scratch schema。
- 守卫另查调用点：10 个写入方的 `user_id` / `actor_user_id` 缺省为 None，路由漏传只记时间不记人 ⇒ 全部调用点必须传。
- 鉴权基线扫描器补「路由前缀 / 非 `router` 变量名 / 空路径」第三维（`note_advanced` 五个端点无鉴权却没被发现的根因），他域欠账冻结不修。

## 6. 大模型只在手动单击时调用

| 调用点 | 触发 | 处置 |
|---|---|---|
| `DisclosureEngine.generate_notes` 第 2 级 `_generate_text_with_llm` | 生成附注（自动遍历全部章节） | 删除该级；生成正文 = 上年附注 → 模板正文。`_generate_text_with_llm` 无其他调用方则删除 |
| `generate_notes` 第 1b 级 RAG 回退（`DISCLOSURE_NOTE_RAG_ENABLED`） | 同上 | 删除该级（开关保留给手动入口时再评估，见 tasks） |
| 校验 `LLM_REVIEW` 规则（`_execute_llm_review_async`） | 生成后自动校验、校验按钮 | 自动校验不执行，结果记「需手动 AI 检查」；只在用户点 AI 检查时执行 |
| `note_formula_engine.LLMReview` 兜底 | 公式校验 | 不调大模型，返回跳过 |
| 前端 `NoteAiSuggestionPanel` 等自动拉取 | 打开面板 / 切换章节 | 改为按钮触发（先核实是否真的自动调用） |

保留（用户单击）：`routers/note_ai.py` 全部端点、`ai-fill`、`batch-ai-fill`、`disclosure_notes.py` 中用户触发的知识库生成端点、AI 对话。

守卫：①生成附注全流程把大模型客户端（`llm_client.chat_completion` 及知识库生成入口）替换为计数桩，断言 0 次；②AST 守卫：`disclosure_engine.py` 与校验引擎自动路径不得引用大模型客户端；③手动端点用计数桩断言确实调到（防止误删）。

前端：生成确认框说明改为「按上年附注与模板生成正文，数据来自试算表与报表；不调用大模型」。

## 7. 和平药房重建（2aa00f57，国企单体，2025）

1. 备份：该项目 2025 年度 `disclosure_notes`（含软删）、`formula_push_state`、`note_section_instances`、`note_section_locks` 导出 JSON 到 `backend/backups/heping_notes_2025_{时间}.json`，记录行数与内容摘要。
2. 核验约束：查 `pg_indexes` 中 `disclosure_notes` 的唯一索引（若存在非部分唯一索引，软删后重建会冲突 ⇒ 用物理删除）；确认无外键引用 `disclosure_notes.id`。
3. 物理删除该项目 2025 年度附注与 `formula_push_state` 中附注目标行（一个事务）。
4. 生成：调用与 `POST /api/disclosure-notes/generate` 同一服务（需 `financial_report` 有行；Phase 5 后不调大模型）。
5. 填数：`POST /api/projects/{pid}/formula-push/run`。
6. 验证：行数与种子国企单体口径一致；无脱树行、无「五、N」旧行；抽查货币资金 / 应收账款 / 存货 / 固定资产 / 营业收入附注表合计与试算表审定数一致；浏览器打开编辑器核对章节树与表格。

实施记录（2026-10-17，数字见 tasks.md Task 25~27）：

- 1~6 收进 `note_project_rebuild.py` + `realign_project_notes.py --rebuild`（一个事务：备份 → 删 → `generate_notes(strict=True)` → 结构断言；提交后推送、校验）。约束核验结论与 2 相同：唯一索引含软删行、无外键 ⇒ 物理删除。
- 推送这一步暴露公式推送引擎三处缺陷，按「写入方不得静默写错」一并修在 `formula_push/note_writer.py` / `engine.py`：旧格式兜底改写编辑器显示的 `_tables` 并按表头认列（认不出就跳过说明）、多条取数行撞同一附注行都不写、找行包含匹配只认「同一项目的另一种写法」。修完整年度再重建一次，两次的备份都留着。
- 抽查 5 个科目只有货币资金对上：固定资产（生成链把累计折旧当正数加）、应收账款 / 营业收入（推送规则标题校验跳过）、存货（三列组不猜列）都是生成链或推送规则数据的问题，不在本 spec 范围，登记待拍板。

## 8. 风险与衔接

- 并发会话频繁改两份种子（逐循环表格脚本）：本 spec 的种子修改只经脚本、改完立即提交；每次运行前看 `git status`，对方有未提交改动时等其提交后重放。
- `deliverable-trio-generation-accuracy` 按编号匹配模板块、并维护报表附注列映射：编号变化后，交付侧的块匹配已有 section_id 兜底；旧编号经 `normalize_section_code` 可解析为新编号（§3.4），交付侧按需调用，不另出别名文件。
- 编号改动后旧前端缓存 / 书签里的旧编号：运行期别名归一兜底（NFR-3）。
- 回滚：种子与数据文件走 git；真库按 4 / 7 的备份 JSON 用 `realign_project_notes.py --restore <backup>` 恢复（工具自带，写入前先测一次恢复路径）。
