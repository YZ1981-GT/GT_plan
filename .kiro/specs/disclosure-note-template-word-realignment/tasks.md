# 任务：附注模板按四版 Word 重新对齐

> 约束：每组 红测 → 修 → 变异 → 更新本文件 → 提交 → 中转工作树推送。真库写入先 dry-run 报数、再备份、再写。
> 种子只经脚本修改；并发会话也在改种子，运行前看 `git status`，对方有未提交改动时等其提交后重放。

## Phase 1 比对工具

- [x] 1. `backend/scripts/check/check_note_template_word_tree.py`：Word 解析（章 / 节 / 小标题 / 表格归属）、种子解析（按 scope 派生口径）、章配对、节匹配、差异分类、`--json` / `--check`；自检用例用合成 docx 证明放错章 / 缺节 / 多节 / scope / 顺序 / 表头差异都能检出。
- [x] 2. 首跑四个口径：差异计数与清单写入下方「比对基线」；每类抽 3 条打开 Word 核对；守卫 `test_note_template_word_tree_alignment.py` 以 `xfail(strict=True)` 入库。
  - ✅ 实现：`backend/app/services/note_word_tree.py`（章节树解析 / 配对 / 差异）+ `note_word_table.py`（表格网格 / 表头 / 逐张比对，按 800 行门拆出）+ 命令行；自检 6 例（合成 docx + 合成种子：每类差异逐条断言、章正文叶子与模板标记不算差异、国企逐章节层级与多级表头、逻辑列合并、占位行、白名单失效与缺理由）+ 真实守卫 1 例 `xfail(strict=True)`。变异 15 个全部打红且红在对应用例上（去跨章同名 / 去空档对应 / 节层级取最深 / 不剔标记 / 去叶子配对 / 去 scope / 白名单不报失效 / section_title 改记 order / 逻辑列不合并 / 占位行不剔 / 留白表头算一级 / 分组表头不推下一行 / 表数、表头、行标签不比），文件逐字节恢复。抽查：上市单体「在子公司中的权益 / 同一控制下企业合并」在第七章、「分部报告 / 年金计划…」在第十五章、「关联方承诺」在第十一章、「所得税费用」在第五章；国企单体「企业合并 / 合并财务报表编制方法 / 递延所得税资产及递延所得税负债」在第四章、「本公司的子公司情况」在第十章、「销售退回」在第九章，均与报告一致。

## Phase 2 种子修复

- [x] 3. 编号别名：种子 `legacy_section_numbers` + `normalize_section_code` 两个准则都查别名；守卫「别名不与现行编号相同」。
  - ✅ `note_section_catalog.load_legacy_code_aliases` / `clear_template_caches` / `section_title_for_scope`；`normalize_section_code` 先查本准则别名、再走国企「五→八」。守卫 `test_note_section_code_aliases.py`：合成种子两准则解析 + scope 随别名 + 真种子别名不遮现行编号且一旧号一节 + 跨准则同号必同义（首轮实测上市「八、5 政府补助」挤掉国企「八、5 应收账款」绑定，故修复器加撞号规则）+ 口径章名。变异「别名不查」打红 2 例。
- [x] 4. 修复器 `backend/scripts/seed/realign_note_templates_to_word.py`：章（章名、`scope_titles`、缺章、多章）。
  - ✅ 国企 一 / 五 / 七 / 十一 / 十三 / 十四 章名按 Word；十三章（按照有关财务会计制度应披露的其他内容）只在合并版 Word ⇒ `consolidated_only`；上市 十 改「公允价值」，五 加 `scope_titles {"standalone": "财务报表项目附注"}`。上市十六章名「母公司…」与 `十六、营业收入与营业成本` 标题按需求 3.2 守卫保留，进白名单待拍板。
- [x] 5. 修复器：节（放错章改挂并换编号前缀、补 Word 有种子无的节、删提示语节、scope、章内顺序）。
  - ✅ 改挂：国企 1 节（六→四）、上市 36 节（三→五、75~82 / 六、2~3 / 七、2~9 / 八 5 节 / 九、2~5 / 十一 3 节；十四→十五、2~9），`section_id` 不变、旧编号进 `legacy_section_numbers`。补节：国企「七、子公司与母公司会计期间不一致的…」（合并）「十、销售退回」，上市「十一、关联方承诺」「十五、5 重要资产转让及出售」「十五、6 年金计划…」。国企「九、【企业应当…」提示语节改为章正文叶子「或有事项」（带表格与校验预设，不删）。scope：国企 8 / 上市 13 节改 both。章内顺序按 Word 重写 `sort_order` / `sort_index`。
  - 🔴 编号规则：目标章现有编号全是数字、且新数字在另一准则未被占用才发数字编号，否则用标题式编号（上市「八」政府补助 5 节因此是标题式，避开国企 八、2~6）；`numeric()` 再断言一次。可重跑：`--check` 0 项；**HEAD 种子经修复器重放 = 工作树种子逐字节相同**（种子只经脚本改）。变异：撞号规则恒真 ⇒ 第二层断言当场报「八、2」；两层都拆 ⇒ 重放结果上市 5 节编号不同。
- [ ] 6. 修复器：表格（表名、列、多级表头、行标签、表数），保留机器字段；与逐循环表格脚本冲突处逐条登记。
  - ⏸ 待用户拍板：表格以四版 Word 还是底稿 xlsx 为准（国企 51 / 上市 73 节有差异，其中 33 / 42 节已按底稿对齐、被底稿同步 / 公式推送 / `fix_note_*_structure.py` 消费）。表格守卫保持 `xfail(strict=True)`。
  - 另记（与表格同批处理）：上市「三、重要会计政策及会计估计」章首有一句模板正文「本公司根据自身生产经营特点…具体会计政策见附注三、16…」，种子无承载节（其余 6 处章首正文全是填写提示，不建节）；章正文叶子（如上市「七、1 在其他主体中的权益」）在编辑器目录树参与连续编号，导致其后各节序号比 Word 大 1（`compute_section_numbers` 按前缀连续编号），补章首正文节前须先定显示序号规则。
- [x] 7. 运行期按口径取章名（`scope_titles`）：生成链、目录树、Word 导出。
  - ✅ 生成链 `disclosure_engine._load_templates` 的 `section_title` / `account_name` 走 `section_title_for_scope`（守卫 `test_generation_uses_scope_chapter_title`，变异打红）；目录树读库内 `section_title`，新生成行即口径章名，存量行由 Phase 3 改写。Word 导出属交付模块（用户：单独开任务），导出章名取自 Word 模板本身。
- [x] 8. 衍生数据重生成；`backend/scripts/migrate/rename_note_section_codes.py` 改数据文件与前端映射中的旧编号；各 `--check` 通过。
  - ✅ 重生成：`generate_note_template_bindings.py`（内容除改名外不变）、`generate_note_soe_listed_diff.py`、`gen_note_shared_table_segments.py --write`、`gen_note_section_kind_index.py`（「X、数据资源」→「数据资源」）；`gen_note_wp_sync_registry.py --check` OK。改名工具首跑替换 465 处，`--check` 0。
  - 🔴 改名工具的盲区（已人工复核修正，工具 docstring 写明）：①注释 / docstring / 用例名里描述旧编号**形态**的叙述（「上市侧是 md 截断值、不要修正」「长度 10」）换完即失真，复核改写 20 余处；②「旧章号 + 完整标题」不在别名表、换不到：H10 展示常量 `'三、资产处置收益'`（界面可见）、`isH10AssetDisposalNoteSection` 不认 `五、78`、`useNoteRefresh` 按科目号刷新只认关键词（`五、75` / `五、77` / `五、80` 不含关键词 ⇒ 底稿改了附注不刷新），均已修并补用例；③真库快照 `note_legacy_positional_pending.json` 被改成新编号 = 伪造快照，已还原并加入排除表；④`k1NoteSectionMap.isK1OtherReceivableNoteSection`（零调用方副本）前缀匹配会吞掉新出现的 `五、80~82`，已删。
  - 保留不改：`audit_report_templates/section_code_index.json` / `section_content_analysis.json` 镜像 Word 模板 `##SECTION##` 标记（四版 Word 不改，交付导出按 `section_id` 兜底）。并发会话未提交的 `report_row_note_mapping.json`、`tests/services/test_note_deliverable_outline.py` 仍有旧编号，待其提交后跑 `--write` 再 `--check`。
- [x] 9. 既有守卫与测试更新（覆盖率下限、scope、章节类型索引、逐循环测试中的硬编码编号）；`WORD_TITLE_ALIASES` 改为「旧系统标题 → Word 标题」；Task 2 守卫去掉 xfail 转真绿。
  - ✅ 章节树守卫 `test_seed_tree_matches_four_word_templates` 去 xfail 转真绿（白名单 3 条：国企「八、94 一般风险准备」json_only、上市合并十六章名、`十六、营业收入与营业成本` 标题，均待拍板）；表格守卫仍 xfail（Task 6）。
  - ✅ `WORD_TITLE_ALIASES` 翻成「旧系统章名 → Word 章名」（折叠键 = Word 标题）；比对工具章配对改为两侧都折叠后比（方向无关）。变异：删「关联方及关联交易」别名 ⇒ `test_word_title_alias_locates_system_chapter` 打红。
  - ✅ 四版 Word 上传端到端 `test_note_text_batch_word_e2e`：命中叙述 51/69/64/67 → **61/76/99/99**（国企叙述目标全中），不一致 17/14/39/37 → 2/4/3/4（章首提示语正文无同名节 + 待拍板的十六章名）；随之修两处定位缺陷：章下只有同名正文节时整章（含「（1）以公允价值计量的项目和金额」…「（5）…」小标题）并入该节（`_sole_body_leaf`）、Word 占位序号「X、」并入 `normalize_title`（与比对工具同口径）；用例的目标树按口径取章名（与生成链同形）。
  - ✅ 逐循环测试与前端映射改新编号（G13/G14/H10/K11~K13/N5 等）；基线即红的 `test_llm_review_warning_finding` 按 validate_all 现行口径（宽松模式 warning 折进 `warning_summary`）改断言，同类空转的 fail-open 例一并收紧。
  - 预存在、与本组无关（HEAD 干净检出同样红）：`kPlNoteSubtableContract` 12 例与 `k1NoteSubtableContract` 6 例（占位行 / 表名）、`test_note_parent_company_chapter` 同构欠账、`test_bindings_soe_legacy_alias_annotated`、`test_n_sync_registry_matches_rule[N3]`、N 循环 / G 负债脚本 `--check`、`八、5` header_label 假行；`test_d1_notes_receivable_pbt` 与 `test_formula_push_k2_canary_pg` 同进程连跑时后者红（HEAD 同样），单跑各自绿。`TestTableLevelAliasHasNoConsumerYet` 红源于并发会话未提交的 `note_deliverable_outline.py`。

## Phase 3 存量项目修复

- [x] 10. `backend/scripts/fix/realign_project_notes.py` dry-run：改编号、树字段、补章、脱树旧行、关联表；7 个目标项目报数。
  - ✅ 计划 `note_project_realign.py`（纯函数）+ 读取 / 执行 / 备份 / 恢复 `note_project_realign_apply.py` + 命令行（默认 dry-run，`--apply` / `--restore`）。模板取生成链同口径 `DisclosureEngine._load_templates`（口径过滤、编号归一、按口径取名）；补章走生成链 `generate_notes(only_sections=…, strict=True)`，不复制构造逻辑（正文 = 上年附注 → 模板正文，表格按试算表取数，不调大模型）。
  - 首跑报数（2025 年度）：甲 / 乙 / 安徽 —— 改编号 1（`六、递延所得税资产及递延所得税负债` → 第四章）、树字段 16（章名 7：一、一、1、五、八、88、九、十一、十四；第四 / 六 / 十章序号随移节顺移 9）、补章 9；医疗器械 / 华氏 / 宜宾 —— 截断编号（旧缺陷：编号截到 10 字，如 `四、记账基础和计价原`）按「规范化标题 + 章节类型」唯一对上改挂 14、树字段 25、补章 9 / 10 / 10（华氏、宜宾缺 `八、94`）。六个单体项目都有 `十三`「承诺事项」+ `十三、1` 两行（有正文，部分是早期大模型文字）：四版 Word 单体没有第十三章，种子已是合并专属 ⇒ 报「脱树（另一口径专属）」不动、不删，目录树与导出按口径本就隐藏。宜宾另有 `五、5 应收账款` / `五、15 其他债权投资` 两行旧位置编号重复行（表格各 7 KB / 15 KB，有人编辑过）：现行编号已有行 ⇒ 记冲突交人工，不合并。
  - 首汽租车_2025（df5b8403）**项目本身已删除（回收站）**：生成链取不到口径会按单体处理（模板 166 而非合并 190），按它对齐会把合并项目改成单体结构 ⇒ 工具对已删除项目一律跳过并报告。
  - 规则细化（与 design §4.1 的差异，已同步 design）：`section_id` 对上模板的行一律对齐模板（子节点的上级按模板写，不对齐树就断），目标 id 被别的行占着且那行不让出时不改并报告；挂在已对齐行下面的自建节跟着改上级。编号被软删行占着（唯一索引含软删）⇒ 不改编号、不补章（用户删除 / 裁剪过）。
  - 触类旁通：`generate_notes` 遇到已软删的编号原来会 INSERT 撞唯一索引 ⇒ 删章 / 自动裁剪后再点「生成附注」整次 500；改为跳过（不复活，回收站恢复才回来）。另加 `strict`：取数 / 构表 / 公式求值 / 绑数据集 / 版本戳失败即抛（写库修复不得降级成空表还报成功，平台教训「写入方取数一律 strict」）。
  - 测试 `test_note_project_realign.py` 19 例（纯函数规则 10 + 真 SQLite 真 ORM 真生成链执行 9：执行后重算为空、已有行正文表格哈希与编辑人 / 更新时间不变、软删编号不补、已删除项目跳过、执行漏做 / 改了内容 / 补章构表失败都抛错回滚）；变异 19 个全部打红且红在对应用例上。
- [x] 11. 表格结构量化（一致 / 表头文字 / 列增减 / 行增减 / 表数五类）+ 读时增强 `note_table_enrichment` 在新种子下的输出核对。
  - ✅ `note_project_table_diff.py` + 只读命令 `backend/scripts/check/check_note_project_tables.py --all-targets`（库内原样 / 读时增强后两套计数；单测 4 例）。2025 年度，按表计（节数 = 编号在种子里且任一侧有表的节）：

    | 项目 | 比对节 | 一致 | 仅表头文字 | 列增减 | 行增减 | 表数不同（节） |
    |---|---|---|---|---|---|---|
    | 甲 / 乙 | 104 | 195 → 208 | 13 → 2 | 16 → 11 | 18 → 21 | 7 |
    | 安徽 | 101 | 185 → 197 | 12 → 2 | 16 → 11 | 18 → 21 | 7 |
    | 医疗器械 | 95 | 186 → 195 | 7 → 0 | 16 → 11 | 18 → 21 | 4 |
    | 华氏 | 94 | 34 → 42 | 8 → 1 | 38 → 13 | 31 → 55 | 74 |
    | 宜宾 | 94 | 9 → 16 | 6 → 0 | 39 → 26 | 11 → 23 | 83 |

    （「→」= 读时增强后，即编辑器里看到的；空白差异 0。）读时增强补上了表名 / 表头文字 / 列数（模板列多于数据列时扩列），但补不了行增减与表数不同，还会因扩列把一部分列增减变成行增减。差异集中在：`八、4` 应收票据、`八、9` 其他应收款（种子中间插入了新表 ⇒ 按位序整体错一位，读时增强的首列交叉校验拦住了串表）、`八、3 / 八、8 / 八、29 / 八、35` 多出 3 行空标签行、`八、10` 数据资源行（库 21 行 / 种子 13 行）、`八、51` 表头带 `<br/>`；华氏 / 宜宾是早期生成的项目，各有 ~50 节库内根本没有表（`table_data` 为空）。这些差异来自底稿 xlsx 口径的表格脚本改过种子，与 Word 口径的表格定稿（Task 6）同一个待决问题。
- [ ] 12. 表格结构写库：按新结构搬值，孤儿值保留在 `_realign_orphans` 并报告；断言非空值多重集合不变、正文哈希不变。
  - ⏸ 待表格口径拍板（Word 表 vs 底稿 xlsx 表，同 Task 6）：先定种子表，再按 Task 11 的分类搬值。量化与比对工具已就绪，可重跑。
- [x] 13. 备份 / 恢复（先实测恢复路径）；`note_section_instances.section_number` 列宽不足时加 V188 / R188。
  - ✅ 备份存 PostgreSQL 自己输出的 `row_to_json` 原文（不经 Python 解析：`json.loads` 会把 jsonb 里的 `1.10` 变 `1.1`、超 17 位有效数字丢精度），另记值为 JSON null 的 jsonb 列（`row_to_json` 把 SQL NULL 与 JSON null 都写成 `null`；真库纯文字章节 `table_data` 全是 JSON null）；恢复 = 删范围内现有行 → `json_populate_recordset` 按原 id 插回 → 补回 JSON null → 再导出须与备份逐字相等。真库守卫 `test_note_project_realign_backup_pg.py` 4 例（scratch schema，数据 = 测试集团甲 2025 原样拷贝 + 边界值；变异「不补 JSON null」「经 Python 解析」都打红）。真表演练：甲 `--apply` → `--restore` → 计划原样重现（改编号 1 / 树 16 / 补章 9）→ 再 `--apply`。
  - ✅ V188 / R188：裁剪页初始化把口径过滤后的全部种子章节写进 `note_section_instances`，叙述性章节以标题作编号（现算最长 42 字），`VARCHAR(20)` 在 PG 上报 22001、整页初始化失败（真库本表一直 0 行即此故；超 20 字编号在本 spec 之前就有）。V188 放宽为不限长（按列现状判断，可重入），R188 有超长行时报错拒绝截断；ORM 同步改 `String`。守卫：离线 9 例（ORM 列宽 ≥ 各口径最长编号 + 迁移文件）+ 真库 5 例（V188 前 22001 且一行未写 / 跑两遍 / 整批写入 / R188 拒绝截断再恢复 / 本地库已应用）；变异 4 个全部打红。本地库已跑 V188（`python -m app.core.migration_runner`）。
- [x] 14. 测试集团甲 / 乙先行 `--apply` → 再 dry-run 为空 → 浏览器；再安徽 / 医疗器械 / 华氏 / 宜宾 / 首汽。
  - ✅ 甲 / 乙 / 安徽 / 医疗器械 / 华氏 / 宜宾已执行（备份在 `backend/backups/note_realign_{项目}_2025_*.json`，目录不入库）：行数 159→168、159→168、160→169、159→168、160→170、162→172；逐行比对备份：只有编号 / 树字段 / 章名列变化，正文、表格、编辑人、更新时间零变化；再 dry-run 六个项目动作全为 0（只剩上面的待人工报告）。首汽已删除 ⇒ 跳过。
  - ✅ 浏览器（甲、华氏）：目录树章名按 Word（原来前端写死旧章名：「一、公司基本情况」「五、会计政策变更及差错更正」）—— 改为章行标题优先、内置名称兜底（`noteChapterLabels.ts`，编辑器树与四栏目录共用；内置名称逐条钉到种子章名）；第四章 37 节按 Word 顺序（补的企业合并 / 合并财务报表编制方法 / 合营安排在 4–6，递延所得税在 32），第十章含补的「销售退回」；补章打开有模板正文。前端 spec 2 个 8 例，变异 5 个都红在对应用例上。章名较长时树上截断，补了悬停提示。
  - 浏览器实测期间后端反复热重载（并发会话持续改 `backend/app`，每次重载预热约 90 秒），期间点章节会超时，与本改动无关。

## Phase 4 编辑留痕

- [x] 15. 继承上年 / 上年 Word 导入：`note_advanced.py` 补鉴权与当前用户；修 `note.title`、`_extract_to_opening_balance`、年度写死；写入行盖章。
  - ✅ 五个端点原来一个鉴权依赖都没挂（不带令牌 `GET …/notes/cross-references` 实测 200）⇒ 读 `readonly` / 写 `edit`；`year` 改必填查询参数（原取不存在的 `project.current_year`）。导入按 `section_title` 匹配（原 `note.title` 不存在）、两年度都过滤软删；补 `_extract_to_opening_balance`（按表头找期初 / 期末列，千分位与括号负数照解析，只填空格）；改副本再整体赋值（多表 `_tables` 与顶层镜像一并填）；写了才盖章；继承跳过正文没变的与内容模板写过的（`is_local_override`）。`test_note_prior_year_import_stamp.py` 6 例。前端无调用方。
- [x] 16. 集团基线下发、集团模板下发盖章；`_upsert_section` 的 `level` 写数字层级。
  - ✅ 基线：覆盖与新建都记操作人；新建前查编号占用（唯一索引含软删行，原来撞键整次 500）⇒ 跳过并回 `skipped_occupied`。模板下发（裸 SQL）：覆盖分支写 `updated_at` + `updated_by = COALESCE(:uid, updated_by)`；`level` 只写 1~5 的整数（`COALESCE`）——模板 `layer` 是保存时的 `level`，缺省 / 字母是下发策略层：字母在 PG 直接报错、整个项目下发失败，空值把层级清成 NULL；只改结构的分支不盖章。真库 scratch 守卫 `test_note_group_template_stamp_pg.py` 3 例（自检真库拒收字母）。
- [x] 17. 三格式保存、离线导入（路由补 commit）、单元格模式切换（新对象赋值 + 校验行属本项目）、回收站恢复（`note_section`）、程序裁剪联动盖章。
  - ✅ 三格式保存：盖章 + 过滤软删。离线导入：编制指引回写只盖真改了的行（`is_distinct_from`），路由补 `commit`（原来会话关闭即回滚，从未落库）。单元格模式切换：只认本项目本年度未删章节（原按 id 取行）、项目编辑权限（原只校验登录）、副本赋值 + `flag_modified`（原原地改 JSONB 从不落库）、改写行级 `_cell_modes` 边车并把人工值写回 `values`（原把单元格换成字典塞进 `values`，没有读取方认，落库即显示成对象）、多表顶层镜像同改、改了才盖章；行 / 列不存在 404、模式非 auto/manual 422。回收站：名称列 `note_section`（原 `section_code` 不存在 ⇒ 列表只显示 id 前 8 位）、恢复附注盖章。程序裁剪联动：标注 / 撤销都盖章，有内容只报冲突的不盖。
- [x] 18. 系统路径不清空编辑人：公式推送事件、公式运行时附注适配器、模板回流。
  - ✅ 公式推送：有操作人（用户点推送）才写 `updated_by`，事件触发不动（原来赋 `None` 清空上一位编辑人）；`updated_at` 照写（与 `last_sync_at` 同值，冲突判定不误报）。公式运行时附注适配器、模板回流本就只写 `updated_at`，由守卫钉住。
- [x] 19. AST 守卫扩到全部写入方 + 每个写入方一条行为测试 + 变异。
  - ✅ `test_disclosure_note_edit_stamp.py` 守卫（二）：用户写入方 13 个函数必须写编辑人（盖章函数 / `updated_by` 属性、下标、关键字、字典键、裸 SQL `SET … updated_by`；docstring 不算）；系统写入方 19 个函数不许写编辑人，唯一允许「`if X is not None:` 真分支里 `y.updated_by = X`」；10 个写入方的全部调用点必须传操作人关键字（缺省 None，漏传只记时间不记人）；附注相关代码不许出现 `updated_by = None`；判据自检 8 条。行为测试 `test_note_edit_stamp_writers.py` 12 例（真 SQLite 真 ORM，能走路由的走真路由与真项目鉴权）+ PG 3 例 + 上年导入 6 例。
  - ✅ 鉴权基线扫描器盲区（附注 IDOR 漏网的根因）：原两维只认 `@router.<method>("…{project_id}…")`，看不见路由前缀带 `{project_id}`、路由变量不叫 `router`、空路径三类 ⇒ 补第三维（解析模块级 `APIRouter(prefix, dependencies)`），现算 632 个端点：项目级 237 / 仅登录 339 / 无鉴权 56（2 个 OnlyOffice 回调 JWT 与 HMAC 签名下载为自鉴权，豁免须真调校验函数）。其余 54 个（16 个路由文件，写 24 / 读 30）冻结为 `_PREFIXED_KNOWN_GAPS` 只许变短、仅登录档冻结上限 339，另立 spec 修（不擅改他域端点）；`require_project_permission` / `authorize_object` 补进项目级口径；前缀非字面量即红（防整文件静默脱管）。
  - 范围外、如实登记：交付件回写附注正文（`writeback_target_adapters.DisclosureNoteAdapter.write_upstream`）不盖章 —— 属交付模块（用户：单独开任务）；集团基线 / 模板下发、三格式保存、离线导入仍只校验登录（平台「仅登录不校项目」棘轮，另立 spec），回收站整体无项目维度（任意登录用户可恢复 / 永久删除任意项目记录）；离线导入算出的合并表格从不落库（`apply_import` 结果被丢弃，解析器每个 sheet 只读第一张表，界面却报成功）；模板下发的覆盖分支实际走不到（策略比字母、模板存数字层级）且不分年度、从不新建；切换模式端点前端无调用方；`auto_trim_v2` 零调用方。

## Phase 5 大模型只在手动单击时调用

- [x] 20. 全仓核实附注域大模型调用点，分「自动 / 手动」写入本文件。
  - 自动（已全部切断）：生成附注（`disclosure_engine`，Task 21 删）；校验 `LLM_REVIEW`（`note_validation_executors._execute_llm_review_async`，经 `NoteValidationEngine` 默认 `allow_llm=False` 跳过；调用方：生成后 `report_note_sync_service`、就绪度 `note_readiness_service`、审计检查 `audit_check.aggregator`、「校验」按钮 `POST …/validate`）；公式引擎 `note_formula_engine.LLMReview.validate_async`（零调用方，删）。
  - 手动（保留，均为按钮触发，逐个核过前端无 `onMounted` / `watch` 自动调用）：`note_ai.py` 续写 `ai/complete`、改写 `ai/rewrite`、生成政策 `ai/generate-policy`、变动分析 `ai/generate-analysis`、完整性检查 `ai/check-completeness`（前端无调用方）；`ai/check-expression` 是空壳不调大模型；`disclosure_notes.py` 的「AI 填充 / 参照文档填充」`…/ai-fill`、「批量预填充」`…/batch-ai-fill`（`NoteKnowledgeEnricher`）；AI 智能建议面板「分析当前章节」按钮；AI 对话。`NoteAiFillDialog` 打开时只重置结果，生成在按钮里。
- [x] 22. 校验 `LLM_REVIEW` 与公式引擎 `LLMReview` 自动路径跳过并给出「需手动 AI 检查」。
  - ✅ `NoteValidationEngine(db, *, allow_llm=False)`：`LLM_REVIEW` 默认返回 `skipped / manual_only`（原因「大模型审核只在用户手动发起时执行」），不调大模型、不计问题；`allow_llm=True` 才执行（用例覆盖两条路径，变异打红）。
  - ✅ 公式引擎：删 `LLMReview.validate_async`（零调用方、会调 `chat_completion`），`validate_note` 兜底层是同步占位；AST 守卫 `test_note_formula_engine_has_no_llm_reference`（先红后绿）。
  - 说明：现有调用方都用默认值，校验里没有单独的「AI 审核」按钮（功能收敛不新增入口）；需要 AI 看正文时用章节内「AI 填充」或「AI 智能建议 / AI 对话」。
- [x] 23. 前端自动拉取改按钮触发；生成确认框文案。
  - ✅ 附注域前端无自动调用大模型的地方（见 Task 20 清单），无需改按钮。生成确认框去掉「建议先上传到知识库供 AI 参照」，改为「按上年附注与模板生成正文，表格数据来自试算表与报表；不调用大模型（需要 AI 起草时在章节内单击「AI 填充」）」；`useWorkflowGuide.GUIDE_NOTE_GENERATE`、知识库页上传建议同步改口径。相关前端 spec 5 个全绿。⬜ 浏览器实测随 Phase 3 一起做（本轮后端 9980 无响应）。
- [x] 24. 守卫：生成全流程大模型计数桩 0 次、手动入口仍调到、AST；变异。
  - ✅ `test_note_generation_no_llm.py`：生成全流程计数桩 0 次（源模块与引擎模块两处打桩）、生成引擎与公式引擎 AST 无大模型 / 知识库引用、开关已删；变异「生成链偷调大模型」打红 2 例。
  - ✅ 手动入口仍调到：`test_note_ai_knowledge_context.py`（续写 / 改写调 `chat_completion` 并注入所选知识文档）、`test_disclosure_note_ai_fill_endpoint.py`（ai-fill / batch-ai-fill 调 `NoteKnowledgeEnricher`）、`test_note_knowledge_enricher.py`、校验 `allow_llm=True` 路径 —— 本轮复跑 73 例全绿。

## Phase 6 和平药房重建

- [x] 25. 备份；核验 `pg_indexes` 与外键；删除计划报数（dry-run）。
  - ✅ `note_project_rebuild.py`（`plan_rebuild` / `rebuild_project`）+ 命令行 `realign_project_notes.py --rebuild --project <id> --year <y> [--apply]`：前置条件（与「生成附注」同口径）→ 加锁 → 备份（Task 13 同格式：含软删行、推送状态、章节锁、章节实例）→ 物理删除该年度附注、附注域推送状态、章节锁 → `generate_notes(strict=True)`（不调大模型）→ 断言编号集合 = 模板、无软删、无孤儿 → 提交后公式推送（`manual`、无操作人 ⇒ 不盖编辑人）→ 校验；dry-run 报现状 + 推送预演。`test_note_project_rebuild.py` 5 例（只报不写 / 整年度换成现行模板且他年度与底稿域推送状态不动 / 缺报表先拒绝、一行不删 / 项目已删除跳过 / 生成少一节即报错回滚）；变异 6 个全部打红。
  - 约束：`uq_disclosure_notes_project_year_section` 不是部分索引（含软删行）⇒ 软删后重建必撞键，用物理删除；无外键引用 `disclosure_notes.id`。
  - 首跑 dry-run（和平，2026-10-17）：214 行（在用 200 / 软删 14；56 行有编辑人）；57 个编号不在现行模板 —— 旧「五、1~40」整组 40 行（全是脱树孤儿）+ 截断编号 / 旧章号 17 个；附注域推送状态 3 行、锁 0。推送会写底稿 ⇒ 底稿条目另备份 `heping_checklist_responses_20261017_083301.json`（255 行）。
- [x] 26. 物理删除 → 生成（不调大模型）→ 公式推送。
  - ✅ 第一次重建（08:58，备份 `note_rebuild_…_085825.json`）：删 214 行 → 生成 166 节（= 国企单体口径模板节数）→ 推送（附注写 111 格 / 56 节、底稿写 154 格）→ 校验 319 / 319。打开编辑器发现推送的数大多看不见 ⇒ 查出推送引擎三处缺陷（下），修完第二次重建（11:04，备份 `note_rebuild_…_110429.json`）：删 166 行 + 附注域推送状态 152 行 → 生成 166 节 → 推送：附注写 88 格（48 节）、未变 26、合计行兜底 116、跳过 42、保留人工 8；底稿 0 写（183 未变）→ 校验 319 / 319；再 dry-run 推送 0 写（幂等）。两次之间「按备份恢复重推 + 清镜像」几步已被第二次重建取代，备份留存（`note_repush_…_100533 / _101809.json`）。
  - 🔴 推送缺陷①旧格式兜底写镜像：模板生成的章节没有 `sub_table_data`（`_tables` 是真源、顶层 `rows` 只是首表镜像），兜底写顶层 `rows` ⇒ 编辑器 / Word 导出 / 校验都看不见、界面显示「本期无此情形」。真库被推送过的旧格式表 101 张（和平 56 / 安徽 45）全部如此；兜底还按位置认列，其中 43 张会写错列（滚动表期末进期初、年初 / 期末颠倒、期初写进「比例」「减值准备」列）。改：写同名 `_tables`（对不上名用首表），按表头认期末 / 期初列（去空白与 `<br/>` 后精确匹配；期间分组下认「金额 / 余额」），认不出就跳过并写明原因，写完同步首表镜像。
  - 🔴 ②撞行：多条取数行对上附注同一行时逐条覆盖写、后写的留下（H1 固定资产_1601 / _1602 / _1603 → 「固定资产」，留下 1603 的 0；和平 / 安徽 / 宜宾都有）⇒ 都不写、逐格列出来源。
  - 🔴 ③找行包含匹配命中别的行：原规则两边互相包含且唯一即命中，三个有底稿的项目 dry-run 命中 12 / 12 / 10 次，6 类命中的是别的行 —— 长期股权投资 → 「减：长期股权投资减值准备」（安徽下一次推送会把 500,000.00 写进减值准备期末列）、长期借款 / 应付债券 / 长期应收款 → 「减：一年内到期的…」、其他非流动金融资产 → 「其他」、所得税费用 → 「当期所得税费用」；其余没写进去只是被单元格人工模式挡住，资本公积落到合计行兜底只因两行同时命中、碰巧放弃。改：调整 / 构成行（减： / 加： / 其中：）去掉前缀后与取数标签相同才算；其余须一边 = 另一边 + 「项 / 项目 / 净额」或以分隔符开头的限定说明；这些行改走合计行兜底。归档 spec `formula-push-note-row-matching` 的 Property 3 / 4 随之收窄（PBT 后缀改为限定后缀，用例注释写明）。
  - 测试：`test_formula_push_legacy_tables.py` 21 例 + `test_formula_push_note_row_containment.py` 17 例；变异 10 + 1 + 2 + 8 个全部打红。公式推送非 PG 全套 1207 passed，18 failed 与本 spec 开始前（9e57c8ddc）同一批；PG 5 个文件逐个全绿。安徽真库守卫 `test_formula_push_note_skip_pg.py` 按写明的原因重定基线：`_MAX_SKIPPED` 80→85（新增 L 类认不出列 10、M 类撞行 6，原来都是假的「写成功」）、`_MIN_COVERAGE` 320→295（实测 297：写进镜像的 unchanged、写错列、对上别的行都不再算覆盖）。安徽、宜宾未推送（dry-run：下一次推送安徽写 70 格、宜宾 44 格）。
- [ ] 27. 验证：行数、章节树、无「五、N」旧行、抽查科目合计 = 试算表审定数、浏览器。
  - ✅ 行数 166 = 国企单体口径模板节数；软删 0、编辑人 0、孤儿 0、不在模板的编号 0；第五章只剩章行 + 5 个会计政策变更叶子，无「五、N」旧行；首表镜像与 `_tables` 不一致 0；校验 319 / 319。
  - ✅ 抽查（附注合计行 vs 试算表，期末 / 期初）：货币资金 八、1 4,467,536.12 / 53,324,585.63 = 1002 + 1012；应付账款 八、37 267,308,976.77 / 230,461,696.25 = 2202；应付职工薪酬 八、40 7,421,003.20 / 13,119,114.12 = 2211；应交税费 八、41 1,544,716.85 / 3,691,614.86 = 2221；预付款项 八、7「小计」1,301,918.43 / 1,331,207.41 = 1123；长期股权投资 八、18「小计」40,459,060.60 = 1511。
  - ❌ 未达（根因在本 spec 之外，如实登记待拍板）：固定资产 八、22「固定资产」行 74,268,010.13 = 1601 + 1602，累计折旧被加上（净值应为 18,823,146.01；报表 BS-028 为 148,536,020.26，也不对）—— 生成链取数把备抵科目当正数相加，推送因撞行不覆盖；应收账款 八、5、营业收入 八、64 被推送规则的章节标题校验跳过（规则的 `table` / `table_by_template` 与国企章节名对不上，和平这类跳过共 13 处），表为空；存货 八、10 期末 / 期初组下各三列金额，推送不猜列 ⇒ 空；预付款项、长期股权投资的「合计」行为空（兜底写首个合计类行「小计」后不再重算合计；长投减值准备行生成未取到 1512）；生成链给没有取数绑定的格标人工占位，推送按人工值保留（其他应收款项 / 其他应付款项 / 租赁负债净额 / 长期应付款 8 格）。另：校验预设 `基础数据/附注模版/国企版校验公式预设.md` 不在仓库，校验每次告警「preset file not found」、预设规则 0 条（319 条来自其他来源）。
  - ✅ 浏览器（第二次重建后）：目录树第五章 5 节、第八章 94 节；货币资金 银行存款 327,095.20 / 848,871.86、其他货币资金 4,140,440.92 / 52,475,713.77；长期股权投资「小计」40,459,060.60、减值准备行未被写；应付账款 / 应付职工薪酬合计同上。表里有数时仍显示「本期无此情形」横幅（只看数据行不看合计 / 小计行，前后端同一规则），登记待拍板。
  - 🔴 浏览器实测抓到编辑器缺陷：点目录节点偶发中间栏空白「请从左侧目录选择章节」，再点一次才出来（和平 八、1 两次，请求记录都是一条 ERR_ABORTED + 一条 200）。根因：hover 预取（停留 200ms 取同一章节详情）点击后不掐，点击的请求 200ms 内没回时，晚到的预取经 `http` GET 去重把点击的请求取消，`onNodeClick` 当失败置空。修：预取收进 `views/composables/noteDetailPrefetch.ts`，`fetchDetail` 发请求前先 `cancel()`，到点时再查缓存。`noteDetailPrefetch.spec.ts` 7 例（含与真实 `http` 去重一起跑的根因特征用例）；变异 4 个全部打红；单文件 vue-tsc 通过（注入 TS2322 能报出）。浏览器把章节详情 GET 人为延迟 800ms：修复前两次点击都空白、各一条 ERR_ABORTED，修复后都正常、无取消请求。

## Phase 7 收口

- [ ] 28. INDEX / memory 同步；提交推送；汇报。

## 比对基线

2026-10-16 首跑（`python backend/scripts/check/check_note_template_word_tree.py`，四个口径；白名单为空）。同一节在单体、合并两版都出现时各计一次。

| 口径 | 差异计数 |
|---|---|
| listed_consolidated | chapter_title 3，misplaced 36，section_title 1，table_columns 96，table_count 20，table_headers 48，table_rows 64，word_only 3 |
| listed_seed | seed_scope_missing 1 |
| listed_standalone | chapter_title 2，misplaced 36，scope 13，table_columns 96，table_count 16，table_headers 48，table_rows 64，word_only 3 |
| soe_consolidated | chapter_title 6，json_only 2，misplaced 1，section_title 2，table_columns 51，table_count 11，table_headers 38，table_rows 54，word_only 2 |
| soe_standalone | chapter_extra 1，chapter_title 4，json_only 3，misplaced 1，scope 8，section_title 1，table_columns 48，table_count 8，table_headers 33，table_rows 50，word_only 1 |

**soe 树差异**（括号内为出现的口径）：

- `chapter_extra` 十三：「承诺事项」本口径 Word 无此章（standalone）
- `chapter_title` 一：种子「公司基本情况」/ Word「公司（企业）基本情况」（两版）
- `chapter_title` 七：种子「合并范围的变化」/ Word「企业合并及合并财务报表」（consolidated）
- `chapter_title` 五：种子「重要会计政策、会计估计的变更以及前期差错的更正」/ Word「会计政策、会计估计变更及差错更正」（两版）
- `chapter_title` 十一：种子「关联方及关联交易」/ Word「关联方关系及其交易」（两版）
- `chapter_title` 十三：种子「承诺事项」/ Word「按照有关财务会计制度应披露的其他内容」（consolidated）
- `chapter_title` 十四：种子「其他重要事项」/ Word「财务报表之批准」（两版）
- `json_only` 九、【企业应当在附注中披露与或有事项有关的下列信息：：guidance：【企业应当在附注中披露与或有事项有关的下列信息：（两版）
- `json_only` 八、94：other：一般风险准备（两版）
- `json_only` 十三、1：other：按照有关财务会计制度应披露的其他内容（standalone）
- `misplaced` 六、递延所得税资产及递延所得税负债：种子在「六」，Word 在第 4 章「重要会计政策、会计估计」（对应种子章「四」）（两版）
- `scope` 五、其他调整事项【包括同一控制下企业合并和清产核资】：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 八、90：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 八、91：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 十一、本公司的合营企业、联营企业情况：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 十一、本公司的子公司情况：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 四、企业合并：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 四、合并财务报表编制方法：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 四、合营安排的分类及共同经营的会计处理方法：出现在本口径 Word，scope=consolidated_only（standalone）
- `section_title` 七、母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的：种子「母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的」/ Word「母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因」（consolidated）
- `section_title` 八、88：种子「（3）其他数据资源相关信息」/ Word「X、数据资源」（两版）
- `word_only` 企业合并及合并财务报表/子公司与母公司会计期间不一致的，母公司编制合并财务报表的处理方法：第 7 章，H2，0 张表（consolidated）
- `word_only` 资产负债表日后事项/销售退回：第 10 章，H3，0 张表（consolidated）
- `word_only` 资产负债表日后事项/销售退回：第 9 章，H3，0 张表（standalone）

**listed 树差异**（括号内为出现的口径）：

- `chapter_title` 五：种子「合并财务报表项目注释」/ Word「合并财务报表项目附注」（consolidated）
- `chapter_title` 五：种子「合并财务报表项目注释」/ Word「财务报表项目附注」（standalone）
- `chapter_title` 十：种子「公允价值披露」/ Word「公允价值」（两版）
- `chapter_title` 十六：种子「母公司财务报表主要项目注释」/ Word「公司财务报表主要项目注释」（consolidated）
- `misplaced` 三、信用减值损失：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、信用减值损失：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、公允价值变动收益：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、公允价值变动收益：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、其他原因导致的合并范围的变动：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、反向购买：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、同一控制下企业合并：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、在合营安排或联营企业中的权益：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、在子公司中的权益：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、在未纳入合并财务报表范围的结构化主体中的权益：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、处置子公司：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、外购在研项目：种子在「三」，Word 在第 6 章「研发支出」（对应种子章「六」）（两版）
- `misplaced` 三、套期（不适用的删：种子在「三」，Word 在第 9 章「金融工具风险管理」（对应种子章「九」）（两版）
- `misplaced` 三、开发支出：种子在「三」，Word 在第 6 章「研发支出」（对应种子章「六」）（两版）
- `misplaced` 三、所得税费用：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、所得税费用：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、本公司的合营企业和联营企业情况：种子在「三」，Word 在第 11 章「关联方及关联交易」（对应种子章「十一」）（两版）
- `misplaced` 三、本公司的子公司情况：种子在「三」，Word 在第 11 章「关联方及关联交易」（对应种子章「十一」）（两版）
- `misplaced` 三、本公司的母公司情况：种子在「三」，Word 在第 11 章「关联方及关联交易」（对应种子章「十一」）（两版）
- `misplaced` 三、本年返还政府补助情况：种子在「三」，Word 在第 8 章「政府补助」（对应种子章「八」）（两版）
- `misplaced` 三、现金流量表项目注释：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、现金流量表项目注释：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、营业外支出（注：：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、营业外支出（注：：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、营业外收入（注：：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、营业外收入（注：：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、计入其他应收款的政府补助：种子在「三」，Word 在第 8 章「政府补助」（对应种子章「八」）（两版）
- `misplaced` 三、计入递延收益的政府补助：种子在「三」，Word 在第 8 章「政府补助」（对应种子章「八」）（两版）
- `misplaced` 三、资产减值损失（损：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、资产减值损失（损：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、资产处置收益（损：种子在「三」，Word 在第 5 章「合并财务报表项目附注」（对应种子章「五」）（consolidated）
- `misplaced` 三、资产处置收益（损：种子在「三」，Word 在第 5 章「财务报表项目附注」（对应种子章「五」）（standalone）
- `misplaced` 三、资本管理：种子在「三」，Word 在第 9 章「金融工具风险管理」（对应种子章「九」）（两版）
- `misplaced` 三、采用净额法冲减相关成本费用的政府补助情况：种子在「三」，Word 在第 8 章「政府补助」（对应种子章「八」）（两版）
- `misplaced` 三、采用总额法计入当期损益的政府补助情况：种子在「三」，Word 在第 8 章「政府补助」（对应种子章「八」）（两版）
- `misplaced` 三、金融资产转移：种子在「三」，Word 在第 9 章「金融工具风险管理」（对应种子章「九」）（两版）
- `misplaced` 三、非同一控制下企业合并：种子在「三」，Word 在第 7 章「在其他主体中的权益」（对应种子章「七」）（两版）
- `misplaced` 三、风险管理目标和政策：种子在「三」，Word 在第 9 章「金融工具风险管理」（对应种子章「九」）（两版）
- `misplaced` 十四、其他：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `misplaced` 十四、分部报告：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `misplaced` 十四、前期差错更正：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `misplaced` 十四、终止经营：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `misplaced` 十四、重要债务重组：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `misplaced` 十四、重要资产置换：种子在「十四」，Word 在第 15 章「其他重要事项」（对应种子章「十五」）（两版）
- `scope` 三、其他原因导致的合并范围的变动：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、合营安排的分类及共同经营的会计处理方法：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、同一控制下企业合并：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、同一控制下和非同一控制下企业合并的会计处理方法：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、在合营安排或联营企业中的权益：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、在子公司中的权益：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、在未纳入合并财务报表范围的结构化主体中的权益：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、处置子公司：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、控制的判断标准和合并财务报表编制方法：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、本公司的合营企业和联营企业情况：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、本公司的子公司情况：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 三、非同一控制下企业合并：出现在本口径 Word，scope=consolidated_only（standalone）
- `scope` 十四、分部报告：出现在本口径 Word，scope=consolidated_only（standalone）
- `section_title` 十六、营业收入与营业成本：种子「营业收入与营业成本」/ Word「营业收入和营业成本（披露格式参考附注五、62）」（consolidated）
- `seed_scope_missing` 一、1：公司基本情况（seed）
- `word_only` 关联方及关联交易/关联方承诺：第 11 章，H2，0 张表（两版）
- `word_only` 其他重要事项/年金计划主要内容及重大变化：第 15 章，H2，0 张表（两版）
- `word_only` 其他重要事项/重要资产转让及出售：第 15 章，H2，0 张表（两版）

- soe 合并口径表格差异：table_columns 51，table_count 11，table_headers 38，table_rows 54；涉及 51 节
- listed 合并口径表格差异：table_columns 96，table_count 20，table_headers 48，table_rows 64；涉及 73 节

结论：

- 章节树问题集中在：国企 7 处章名（含十三 / 十四两章名与 Word 完全不同）、国企「六、递延所得税资产及递延所得税负债」应在第四章、上市会计政策章「三」挂了 30 个别章的节（8 个科目节 → 五，开发支出 / 外购在研项目 → 六，8 节 → 七，5 节 → 八，4 节 → 九，3 节 → 十一）、上市「十四」6 节应在「十五」；scope 填错 国企 8 / 上市 13 节（单体版 Word 也有，种子标 consolidated_only），国企十三章及其叶子只在合并版 Word 出现；Word 有种子无 国企 2 / 上市 3 节；种子多出 国企提示语节 1、「八、94 一般风险准备」1（国企 Word 无，上市 Word 有）。
- 与 2026-10-14 的数（对上 578、章名 15、放错章 66、缺 38、多 16）口径不同：那次按章逐节比，本工具先跨章找同名，原来记作「缺节 + 多节」的放错章节现在只记一次 `misplaced`；同一节两版各计一次。
- 表格差异较多（国企 51 节、上市 73 节），其中国企 33 / 上市 42 节是此前按底稿模板 xlsx 对齐过的表（底稿同步注册表、公式推送规则或 `backend/scripts/fix/fix_note_*_structure.py` 逐循环修复脚本涉及），底稿 → 附注同步按行列对位写入。按 Word 改这些表会与底稿对不上，**表格以哪个为准待用户拍板**（见本 spec 收口汇报）；章节树部分不受影响，先做。
- 国企母公司章「十二」种子有 37 张表、Word 0 张（Word 写「格式参照附注八」）：是 `test_note_parent_company_chapter` 守护的既有设计，修表时登记白名单（理由引该守卫）。
