# 交付中心三件套生成准确性 — 任务清单

> 约束：先复现后修复；每组修完跑相关回归 + 四个真实项目复验（探针在仓库外、事务回滚不落库）；并发会话在
> `note_word_exporter.py`（7.6 段）、`deliverable_writeback_service.py` 的未提交改动不得覆盖；service 只 flush。

## Phase A 财务报表

- [x] 1. 新建 `report_template_binding.py`（模板行名读取、行名规范化、三级绑定、结果统计），单测覆盖错位 / 同名多行 / 标记不一致 / 编码冲突。
  - 证据：`tests/services/test_report_template_binding.py` 22 例；变异（关「合计引用优先」/ 关「同码本位」/ 换回按编码直取）各自打红对应用例。
- [x] 2. 导出器接入绑定：填充、母公司个别列、差异检测 `_compute_expected` 同源；绑定异常回退并告警。
  - 出现位改为从即将填充的工作簿扫描（合成模板测试据此暴露：从磁盘另读模板会与实际填充的文件不同源）。
- [x] 3. 减值表键别名 + 权益 / 减值 sheet 多关键词匹配；合并变体母公司 sheet 取母公司索引。（manifest `sheet_aliases` 未改：多关键词已覆盖四变体，现算真实模板全部命中）
- [x] 4. 表头期间（资产负债表日期 / 其余年度）+ 表头写死年份替换 + General 金额格。
- [x] 5. 减值表期初 / 期末取值与期末公式覆盖。
- [x] 6. `ReportFormulaParser._use_opening` + `PriorPeriodResolver`；`_generate_report` 与未审路径共用；权益表净利润按行名。
  - 证据：`tests/services/test_report_prior_period.py` 3 例；`test_report_engine.py::test_prior_period_data` 按新口径改写（期初 = 本年试算表期初数、利润表无来源为 None）。
- [x] 7. 导出提醒（不平衡 / 合计不一致 / 未绑定有金额 / 过期 / 现金流量表全零 / 上期无来源），路由回传，前端展示。
  - 追加：权益变动表年末 / 年初 ↔ 资产负债表所有者权益合计；减值表全零而利润表有减值损失。`tests/services/test_report_export_checks.py` 4 例。前端展示待 Task 24 浏览器实测。
- [x] 8. `report_row_note_mapping.json` 修正（现算 57 条）+ 附注显示编号用于报表附注列（`note_deliverable_outline.py`，含合并模板复合占位）。
  - 证据：`tests/services/test_note_deliverable_outline.py` 24 例（含四版真实模板章号 / 块外标题）；`test_report_excel_deliverable_accuracy.py`。
- [x] 8a. 模板自算行分项全空写库内总额（实收资本）+ 单体「带 *」合并专用行公式清空 + 绑定「合计引用优先 / 同码本位」。
  - 证据：四项目事务内重新生成报表后导出，资产负债表 / 利润表 332 格逐值比对，剩余差异仅「实收资本净额 / 持续经营净利润」（模板按公式算出、库内 seed 行为空，导出值正确）与和平 seed 行 BS-126 自身口径不一。
- [x] 8b. 公式求值正则容忍参数间空白（`formula_grammar`），减值表 / 补充资料 / 权益表 27 行不再静默为 0。
  - 证据：`tests/test_formula_grammar_whitespace.py` 7 例，换回旧正则即复现 `Decimal('0') != 150`；公式引擎 / 报表引擎 / 合并取数相关 19 个测试文件 549 passed（唯一失败 `test_adj_not_in_report_engine_zero_substitution_list` 在 HEAD 干净检出同样失败，非本次引入）。

## Phase B 附注

- [x] 9. `note_deliverable_filter.py`：段落 / 表格过滤谓词与块过滤；`append_note_text`、`fill_paragraph_with_note_text`、`note_text_elements` 接入 `block_filter`（默认不过滤，既有调用零变化）；模板模式与程序化导出都接入。
  - 证据：`tests/services/test_note_deliverable_filter.py` 43 例（含第二轮真实导出抓到的 8 种行形态、旧导入表题 / 跨行括注、全 0 表）；本轮新增规则磁盘变异 15 条逐条打红（首轮 5 条见前次记录）。
- [x] 10. `note_template_block_fill.py` 预处理：块外同级标题包合成块、块尾内容收进前一块、块间指引按章删除、页眉页脚占位、无块章样板文字落款、编号重启记录。
- [x] 11. 块删除规则：未匹配 / 未勾选 / 交付过滤后无内容 / 报表零余额只有文字 → 整块删，一级标题与分节符保留；删块后变空的横向节并掉。
- [x] 12. 保留块重建：表位按表题 / 子标题 ↔ 表名对位（按序号兜底只在不会张冠李戴时用）、续表进模板续表表位或紧跟主表、额外表补表题、
  子标题连同上级取舍、字面编号重排、块内与章内编号重启转移、独立 `{{seq}}` 删段、标题指引括注剔除、分项节保留上级标题。
  - 证据：`tests/services/test_note_template_block_fill.py` 22 例（合成块按真实模板结构 + 真实国企模板端到端 5 例）；磁盘变异
    （块重建 14 + 导出接线 5 + 轮廓 / 编号 5）逐条打红，唯一存活的是 `_replace_in_paragraph` 首行快速判断改用去空白文字 ——
    只影响「有无 `{{`」判断，等价变异。附注 / 报表 / 交付件锚点回填刷新相关测试 31 个文件 493 passed
    （`test_deliverable_lineage_properties.py::test_property_16` 的 hypothesis 反例「0．㐀」打在未改动的 `_is_title_paragraph` 上，与本次无关）。
- [x] 13. 表格渲染（回退路径，见 design §2.9 更正）：样例表外观 + 金额列放宽 + 字号随样例表 / 宽表 9→8 磅 + 最小行高 + 表头重复 + 合计加粗。
- [x]* 13a. 模板克隆路径（列数一致时直接克隆样例表行、保留表头合并）。2026-10-17 用户强制执行此前延后项，已落实。
  - 实现：`note_template_table_look.render_cloned_table`（样例表叶子列数 = 库内表列数时深拷贝样例表、保留表头行含 `gridSpan`/`vMerge`
    合并、按行标签三级选原型行「同名→合计/小计/总计→首个数据行」逐行克隆写值、金额右对齐千分位 0/空留白、列宽/边框/字体全继承模板）
    + `sample_leaf_columns` / `lib_leaf_columns`（与 `_render_table` 同口径的有效列）；`rebuild_block._render` 克隆优先、列数不一致回退，
    `BlockRebuildStats.tables_cloned` 记数。lxml 代理 `id()` 复用坑规避：全程 `copy.deepcopy(w:tbl)` + 持有元素引用，不按裸 `id()` 判定。
  - 证据：`tests/services/test_note_template_clone_path.py` 10 例（列数分流 / 无样例表或无数据回退 / 表头两行合并保留 /
    原型三级选择 / 0 与空留白 + 文本透传 / 模板列宽保留 / 端到端 `rebuild_block` 克隆与回退分流）；磁盘变异 3 条逐条打红
    （关克隆优先 → 端到端克隆用例红；关表头合并保留 → 合并保留用例红；原型恒取首行 → 两个原型用例红），变异均注在被测生产函数内、
    未替换函数本身。回归：block_fill / 克隆 / filter / outline / 导出清理 / 锚点 / cp02 叶子列 / 多级表头 / 子表 / 模板填充共 162 passed。
  - 真实模板验证（解除延后理由）：soe/listed standalone+consolidated 四套模板现扫，样例表 245~428 张、含表头合并 61~124 张、
    多行原型 241~418 张、列数 2~13。对 listed 块「五、4 应收票据」（7 叶子列、两行合并表头「期末余额→账面余额/坏账准备/账面价值」）
    跑 `rebuild_block`：克隆路径触发、输出 2 表头行 + 3 数据行、合并保留、6 个数值列逐格落值、0 留白、另存重开文档结构合法。
    原延后担心的「行名不规整」风险实测为低：原型行只决定继承的格式/边框，所有值都被库内值覆盖，行身份不影响数据正确性。
- [x] 14. 交叉引用显示映射（含旧编号别名、指向未导出章节的提醒）；章级附注放入空章（章名相近才放）。
  - 偏离 AC-3.5：模板无位置的其余附注不追加、只提醒（实测全为章级大模型综述 / 旧编号重复 / 指引误导入，见 design §2.9）。
- [x] 15. 导出提醒：剔除行数、残留占位章节、报表有余额附注无表、报表零余额未导出、勾选未导出、模板无位置、空章、悬空交叉引用、样板文字待填；
  `NoteExportMeta.delivery_warnings` → 路由合并回传 → 前端既有提醒弹窗。
- [x] 16. ~~`disclosure_engine` 通用大模型提示词与输出过滤~~ → 移交 `disclosure-note-template-word-realignment` US-5（自动路径不再调用大模型）；
  本 spec 确认库内已有 AI 草稿经 Task 9 交付过滤剔除：四项目交付件分别剔除 630 / 625 / 374 / 8 行（安徽 / 和平 / 华氏 / 宜宾），残留单占位句子逐章提醒。
- [x] 16a. 报表附注列与附注交付件编号同源：`build_fs_note_ref_plan` 与导出共用 `region_is_kept` + `container_orders` + `number_regions`。
  - 证据：真实模板端到端测试（零余额只有文字的节不编号、后续顺延；分项节不占号）；四项目报表附注列 78 个编号与交付件 LibreOffice 渲染编号逐个一致（0 不符）。
- [x]* 16b. 交付件增量刷新（`deliverable_refresh_service._replace_block_content`）按模板重建块 + 交付过滤。2026-10-17 用户强制执行此前延后项，已落实。
  - 实现：新模块 `deliverable_refresh_rebuild.py`（272 行）—— `_adapt`（marker 直传；anchor 在内容宿主 body/`w:sdtContent`
    内首尾插哨兵空段作 open/close，适配 `rebuild_block` 的「elements[0]/[-1] 作标记、兄弟插删」约定，重建后删哨兵、持引用不按裸 `id()`）、
    `_has_rebuildable_structure`（认 `w:tbl` 或标题样式段 → 走 `rebuild_block`；纯文字 / 空区间回退）、`rebuild_refresh_block`
    （与全量生成同套：`rebuild_block` + `make_block_filter`，正文过滤与结构判定共用块标题 `extra_titles` + 子标题 / 表题
    `structure_titles`）、`_fallback_text`（纯文字块接 `make_block_filter` 过滤后 `note_text_elements` 渲染）。
    `deliverable_refresh_service`：`_latest_note_text`→`_latest_note`（取整条 ORM 行含 `table_data`，无记录返 `_EmptyNote` 占位）、
    `_replace_block_content` 改签名 `(doc, block, note, locate_mode, section_code)` 调重建后用 `_current_block_elements`
    重扫块算 `block_text_hash`（口径不变、与导出 / 人工编辑检测同一函数）、`_exporter()` 惰性建 `NoteWordExporter`；单 / 批两调用点均改。
  - 关键发现：交付件块里已无模板样例表（全量导出已消费），但块内已渲染表 + 标题足以让 `rebuild_block` 用库内 note 重渲染表 + 过滤正文；
    anchor / marker 两套 block 结构不同（anchor `.elements` 是纯内容、`start_el` 在 body 级而内容可能在 `w:sdtContent` 内），
    必须哨兵适配不能硬塞。`_has_rebuildable_structure` 首版认「非空 `w:p`」太松 —— 纯文字块被 `rebuild_block` 当标题保留致旧文字残留，
    收窄为只认表 / 标题样式。
  - 证据：`tests/services/test_deliverable_refresh_rebuild.py` 5 例（模板重建重渲染表 + 过滤草稿 × anchor/marker 两模式 + 纯文字回退过滤
    × 两模式 + Rendered_Block_Hash 口径）；磁盘变异 2 条逐条打红（关 `_has_rebuildable_structure` 分流 → 模板用例红；
    关 `make_block_filter` 内层退化恒等 → 过滤用例红），变异注在被测 `rebuild_refresh_block` / `_replace_block_content` 的下一层、
    未替换生产函数，复原后全绿无残留。回归：refresh / lineage / filter / note_template / clone / 锚点 + 导出相关 152 passed；
    `_replace_block_content` 改签名牵连 4 处旧 fixture（e2e `MockDBResult` 补 `scalars()`、property_13 mock 改按语句内容路由 + 补
    `scalars().first()`、`test_note_text_word_render` 刷新用例改传 note 对象 + 新签名）已按新契约更新；其余 8 个失败经 `git stash`
    归因为并发 spec 的模板 JSON 改动 / OnlyOffice 密钥内置默认（HEAD 同样失败，非本任务引入）。`check_file_size` 两文件（service 539 /
    新模块 272）均 ≤800、无需白名单。

## Phase C 审计报告正文

- [x] 17. 强调事项段插入与标题顺延（新模块 `report_body_postprocess.py`，preview 阶段 `prepare_report_body`）。
  - 插在「形成审计意见的基础」（及其后的持续经营段）之后、下一节 OPT 开标记之前；措辞同致同详版模板；锚点识别为 `emphasis`。
  - 追加（普查发现）：上市 / 三板模板 16 份里 12 份 OPT 开闭标记错配（模板加工脚本倒序插入致相邻两段交错），可选段识别不到、
    标记原样进交付件；`normalize_optional_markers` 按章节标题重放标记，删可选段后序号顺延（B 类否定模板自身「三 → 五」跳号一并修正）。
- [x] 18. NOTE / 编制提示框 /【…】/ 残留标记清理，单体口径集团条款处理（confirm 阶段 `finalize_report_body`，含指引副本另存之后）。
  - 证监会指引单格表删除；「##NOTE:单体复核」未闭合标记：单体删集团审计条款、示例段「合并资产负债表 / 合并财务报表」改单体；
    「【非上市实体删除（项目合伙人）】」非上市删「（项目合伙人）」；无法表示意见模板二选一措辞取「（如适用）」口径。
  - 修 `strip_guidance_notes` 死循环（`##/NOTE:label##` 认不出、闭标记在前时同一段无限重试）。
- [x] 19. 落款日期（报告日期 → 中文日期；无则年份 = 审计年度 + 1、月日待填）、权益变动表名称（非股份公司 → 所有者权益，含目录表）、
  签字合伙人取数（角色认 `signing_partner`；姓名取本人 `name` 而非「所属合伙人」`partner_name`；SAVEPOINT）。
  - 触类旁通：`wp_prefill_context.py` / `wp_editor_router.py` 的签字合伙人查询同样只认 `partner`、不滤删除，一并改。
- [x] 20. `missing_fields` 中文且只报模板实际用到的字段 + 生成后待补写清单（强调事项段 / 非标意见示例段 / 「×」待填 / 落款月日 / 残留占位）；
  confirm 建 / 同步 `audit_report`（草稿态；软删行复用防唯一索引冲突）、`report_body_json.opinion_choice` 供一键全套沿用、传试算表快照引用。
  - 证据：`tests/services/test_report_body_postprocess.py` 31 例（真实模板参数化 16 份 OPT 模板）、`test_report_placeholder_partner.py` 3 例、
    `test_template_fill_service.py` 新增端到端 1 例并按新口径改写 2 处断言；磁盘变异 36 条全部打红（`D:\gt_probe_dlv\mutate_rb.py`）。
    四项目 × 五种意见（另加 A / B 类）事务回滚生成核对：强调事项段与序号、指引框 / 标记 / 集团条款 / 合并措辞全部清除。
- [x] 21. 前端报告弹窗改「报告模板类型」（自动 / A~D 类）并传 `company_subtype`（原「公司类型 / 公共利益实体」两项从未传给后端）；
  待补充字段由后端返回中文。浏览器实测见 Task 24。
- [x] 21a. （普查追加）`routers/deliverable.py` 在线编辑配置端点调用未导入的 `deliverable_doc_key` ⇒ 草稿交付件在线编辑必 500；
  补导入 + `tests/test_deliverable_modules_names_resolve.py`（`symtable` 判函数体引用的模块级名字都有定义，覆盖交付链路 15 个模块；
  原守卫按源码文本判「引用了该名字」，名字写着就算过）。

## Phase D 验证

- [x] 22. 回归：报表导出 / 差异检测 / 附注模板模式 / 锚点 / 回填 / 报告正文相关测试。
  - 证据：112 个测试文件 1777 passed / 11 failed（2026-10-17，HEAD `ff9320490` + 工作树；比上轮 1740 多出的 37 例全是本轮新增），
    11 个失败均非本 spec 引入：其中 9 个在 HEAD 干净检出
    （临时 worktree）复跑同样失败、失败信息相同；`property_16` 用同一反例在 HEAD / 工作树分类结果相同；`docx_template_filler`
    被测模块只依赖标准库、模块与测试均未改。逐个：`test_full_deliverables_executor` 5 例（2026-06-17
    `a1102af85` 去掉未审交付步骤后测试仍按 4 步断言）、`test_deliverable_center_p1::test_onlyoffice_disabled_without_secret` 与
    `test_deliverable_onlyoffice::test_property_54`（OnlyOffice 密钥有内置默认值）、`test_deliverable_routes::test_unsupported_format_downgrade`
    （xlsx 已支持预览）、`test_deliverable_lineage_properties::test_property_16`（hypothesis 生成「0．㐀」被判为编号标题，HEAD / 工作树分类结果相同）、
    `test_docx_template_filler::test_property_red_placeholder_always_replaced`（hypothesis 库重放控制字符，模块只依赖标准库、两文件均未改）、
    `test_note_text_hygiene::...[soe]`（并发 spec 的种子改挂，HEAD 同样 4 处）。
  - 前端：`src/components/deliverable/__tests__` 16 个文件 158 passed / 3 failed（`DeliverableShortcut` 1、`OnlyOfficeEditor` 2）；
    两组件及其 import 闭包本 spec 未改（只有 `deliverableApi.ts` 加了 2 行类型声明），HEAD 干净树跑不起 vitest（junction 的
    node_modules 报「找不到 runner」），按 import 闭包判定为预存。
- [x] 22a. （复验追加）附注交付过滤第三轮：段内「【需补充信息】」提示清单整段删（限同一段）、≥13 字长「【…】」行内剔除（未闭合截到行尾并丢后续行到「】」）、
  短「【A 公司】」保留并计入待补占位。
  - 证据：`test_note_deliverable_filter.py` 新增 9 例（共 52）；磁盘变异 8 条全部打红（含「提示清单跨段」与「去掉行首长括注规则后行内规则兜住」两条设计取舍）。
- [x] 23. 四个真实项目复验三类产物（事务回滚、不落库）。
  - 报表：事务内重新生成后导出，资产负债表 / 利润表 332 格 / 项目逐值比对，剩余差异只有已知三处（实收资本净额 / 持续经营净利润模板自算、和平 BS-126 seed 口径）。
  - 附注：报表附注列 78 个编号与交付件 LibreOffice 渲染编号 0 不符；渲染件「{{」「##」0 处；残留只有短「【A 公司】」类占位（已提醒）。
  - 正文：四项目 × 五种意见（另加 A / B 类）生成核对，见 Task 20。
- [x] 24. 浏览器实测交付中心三个入口（重药安徽 2025，admin）。
  - 生成报表：五表勾选 → 提醒弹窗 8 条（资产负债表差额 -3,940,244.54、权益表年末与资产负债表不一致、期初为空、利润表上期无来源、
    现金流量表全零、减值表全零而利润表有减值损失、2 行过期、附注列 2 项留空）→ 下载件与探针产物 1278 个非空格逐格一致、无残留公式、表头期间与编制单位正确。
  - 生成附注：勾选树一键预设 165 节（探针 167，差的「十三」「十三、1」被目录树按口径隐藏、导出也按口径删块，产物相同）→ 质量预检确认 → 提醒弹窗 →
    下载件与探针产物 657 段逐段一致。
  - 生成报告：「报告模板类型」自动 → 预览（业务类型 C 类、模板 2025-v1；C 类简版模板本身无可选段）→ 确认生成 v15 → 下载件无「##」「{{」「【」OPT / NOTE 残留，
    「[报告文号]」与落款月日待填且已列入预览待补充。
  - 实测写库（正常用户操作、只增不改）：安徽交付件报表 v11、附注 v10~v13、报告正文 v15（含 `audit_report` 草稿行）。
- [x] 24a. 实测抓到并修复（单测抓不到的界面 / 文案问题，详见 design §6）：
  - 附注提醒称呼重复「四、存货 存货」→ `note_display_label`（2 例；变异 2 条打红）；
  - 章级附注混进「模板没有对应位置」→ 单列「本章整体说明未导出」（端到端用例加强；变异 1 条打红）；
  - 勾选树分组不显示章名、章级附注像首节重复、名称编码节标题重复 → `leafLabel` / `isChapterRow` / 分组取章名（vitest 2 例；变异 4 条打红；
    单区域 tsc 通过且注入类型错误能报 TS2322；ESLint 无问题）；
  - 34 份报告模板目录页码「1-X」「7-X」未列入待补充 → `toc_pending_pages`（35 例；变异 4 条打红）；
  - 「报告模板类型」默认值「自动」显示成「请选择」→ `:empty-values="[null, undefined]"`（浏览器复核）。
  - 未复现、未改：附注提醒弹窗出现过一次自行关闭，带埋点复跑停留超过 1.5 分钟（见 design §6）。
- 提交须知：`report_excel_exporter.py`（HEAD 1405 → 1648 行）与 `financial_report_drift_service.py`（906 → 915）在 HEAD 就超 800 行且不在白名单，
  提交时须登记 `check_file_size` 白名单（写本 spec 增量与拆分方向）；本 spec 新模块与新测试全部未跟踪，须同一次提交。
