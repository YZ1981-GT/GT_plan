# 任务：附注模板按四版 Word 重新对齐

> 约束：每组 红测 → 修 → 变异 → 更新本文件 → 提交 → 中转工作树推送。真库写入先 dry-run 报数、再备份、再写。
> 种子只经脚本修改；并发会话也在改种子，运行前看 `git status`，对方有未提交改动时等其提交后重放。

## Phase 1 比对工具

- [x] 1. `backend/scripts/check/check_note_template_word_tree.py`：Word 解析（章 / 节 / 小标题 / 表格归属）、种子解析（按 scope 派生口径）、章配对、节匹配、差异分类、`--json` / `--check`；自检用例用合成 docx 证明放错章 / 缺节 / 多节 / scope / 顺序 / 表头差异都能检出。
- [x] 2. 首跑四个口径：差异计数与清单写入下方「比对基线」；每类抽 3 条打开 Word 核对；守卫 `test_note_template_word_tree_alignment.py` 以 `xfail(strict=True)` 入库。
  - ✅ 实现：`backend/app/services/note_word_tree.py`（章节树解析 / 配对 / 差异）+ `note_word_table.py`（表格网格 / 表头 / 逐张比对，按 800 行门拆出）+ 命令行；自检 6 例（合成 docx + 合成种子：每类差异逐条断言、章正文叶子与模板标记不算差异、国企逐章节层级与多级表头、逻辑列合并、占位行、白名单失效与缺理由）+ 真实守卫 1 例 `xfail(strict=True)`。变异 15 个全部打红且红在对应用例上（去跨章同名 / 去空档对应 / 节层级取最深 / 不剔标记 / 去叶子配对 / 去 scope / 白名单不报失效 / section_title 改记 order / 逻辑列不合并 / 占位行不剔 / 留白表头算一级 / 分组表头不推下一行 / 表数、表头、行标签不比），文件逐字节恢复。抽查：上市单体「在子公司中的权益 / 同一控制下企业合并」在第七章、「分部报告 / 年金计划…」在第十五章、「关联方承诺」在第十一章、「所得税费用」在第五章；国企单体「企业合并 / 合并财务报表编制方法 / 递延所得税资产及递延所得税负债」在第四章、「本公司的子公司情况」在第十章、「销售退回」在第九章，均与报告一致。

## Phase 2 种子修复

- [ ] 3. 编号别名：种子 `legacy_section_numbers` + `normalize_section_code` 两个准则都查别名；守卫「别名不与现行编号相同」。
- [ ] 4. 修复器 `backend/scripts/seed/realign_note_templates_to_word.py`：章（章名、`scope_titles`、缺章、多章）。
- [ ] 5. 修复器：节（放错章改挂并换编号前缀、补 Word 有种子无的节、删提示语节、scope、章内顺序）。
- [ ] 6. 修复器：表格（表名、列、多级表头、行标签、表数），保留机器字段；与逐循环表格脚本冲突处逐条登记。
- [ ] 7. 运行期按口径取章名（`scope_titles`）：生成链、目录树、Word 导出。
- [ ] 8. 衍生数据重生成；`backend/scripts/migrate/rename_note_section_codes.py` 改数据文件与前端映射中的旧编号；各 `--check` 通过。
- [ ] 9. 既有守卫与测试更新（覆盖率下限、scope、章节类型索引、逐循环测试中的硬编码编号）；`WORD_TITLE_ALIASES` 改为「旧系统标题 → Word 标题」；Task 2 守卫去掉 xfail 转真绿。

## Phase 3 存量项目修复

- [ ] 10. `backend/scripts/fix/realign_project_notes.py` dry-run：改编号、树字段、补章、脱树旧行、关联表；7 个目标项目报数。
- [ ] 11. 表格结构量化（一致 / 表头文字 / 列增减 / 行增减 / 表数五类）+ 读时增强 `note_table_enrichment` 在新种子下的输出核对。
- [ ] 12. 表格结构写库：按新结构搬值，孤儿值保留在 `_realign_orphans` 并报告；断言非空值多重集合不变、正文哈希不变。
- [ ] 13. 备份 / 恢复（先实测恢复路径）；`note_section_instances.section_number` 列宽不足时加 V188 / R188。
- [ ] 14. 测试集团甲 / 乙先行 `--apply` → 再 dry-run 为空 → 浏览器；再安徽 / 医疗器械 / 华氏 / 宜宾 / 首汽。

## Phase 4 编辑留痕

- [ ] 15. 继承上年 / 上年 Word 导入：`note_advanced.py` 补鉴权与当前用户；修 `note.title`、`_extract_to_opening_balance`、年度写死；写入行盖章。
- [ ] 16. 集团基线下发、集团模板下发盖章；`_upsert_section` 的 `level` 写数字层级。
- [ ] 17. 三格式保存、离线导入（路由补 commit）、单元格模式切换（新对象赋值 + 校验行属本项目）、回收站恢复（`note_section`）、程序裁剪联动盖章。
- [ ] 18. 系统路径不清空编辑人：公式推送事件、公式运行时附注适配器、模板回流。
- [ ] 19. AST 守卫扩到全部写入方 + 每个写入方一条行为测试 + 变异。

## Phase 5 大模型只在手动单击时调用

- [ ] 20. 全仓核实附注域大模型调用点，分「自动 / 手动」写入本文件。
- [ ] 21. 生成附注删除 RAG 回退与通用大模型两级；无调用方的函数删除。
- [ ] 22. 校验 `LLM_REVIEW` 与公式引擎 `LLMReview` 自动路径跳过并给出「需手动 AI 检查」。
- [ ] 23. 前端自动拉取改按钮触发；生成确认框文案。
- [ ] 24. 守卫：生成全流程大模型计数桩 0 次、手动入口仍调到、AST；变异。

## Phase 6 和平药房重建

- [ ] 25. 备份；核验 `pg_indexes` 与外键；删除计划报数（dry-run）。
- [ ] 26. 物理删除 → 生成（不调大模型）→ 公式推送。
- [ ] 27. 验证：行数、章节树、无「五、N」旧行、抽查科目合计 = 试算表审定数、浏览器。

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
