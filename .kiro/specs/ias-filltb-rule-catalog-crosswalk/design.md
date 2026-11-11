# IAS / FillTbTool 规则目录与编码候选对照（0）：设计

## 1. 当前基线与交付形态
实际基线为 HEAD `9684955683720068cf3aad82dfc5502a0194e73c`，分支 `sj-dev1.0`。本轮交付 0、A 两份 spec 与两本 Excel；Excel 已生成并通过现有自检，平台产品未实施，spec 仅文档交付，无提交或推送。
本设计基于只读源码及静态文件；未查询数据库、未运行 IAS / FillTbTool 或平台，不据此证明项目运行时有效规则。工作表与条目数量以最终验证报告为准。
| 来源路径与锚点 | 核实结果与解释 |
|---|---|
| `backend/data/standard_account_chart.json#/accounts` | 字段 code/name/direction/level/category/parent_code；不是所有客户的完整科目表。 |
| `backend/data/account_to_report_line_seed.json#/mappings` | soe_standalone、soe_consolidated、listed_standalone、listed_consolidated 四口径；字段 standard_account_code/report_type/report_line_code/report_line_name。 |
| `backend/data/report_config_seed.json` 的 applicable_standard/template_variant/scope/report_type/rows | 报表行及公式定义来源；科目映射数不等于各报表行数。 |
| `backend/data/wp_account_mapping.json#/mappings` | 含 wp_code/cycle/account_codes/report_row/note_section 和条件/准则等扩展字段，不全是单纯科目映射。 |
| `backend/data/formula_push_rules.json#/rules` | 保留 rule_id/page_key/stage/policy/target/source/triggers，source.kind 分 formula/derivation/four_table_leaves。 |
| `backend/data/ledger_recognition_rules.json#/table_signatures`、`#/matching_config` | 当前无顶层 column_aliases；表识别与匹配配置单列。 |
| `backend/app/services/ledger_import/identifier.py::_RAW_HEADER_ALIASES/_build_header_alias_table` | 实际上传列别名；年初/期初净额合入 opening_balance 的现状不掩盖。 |
| `backend/app/services/formula_engine.py::COLUMN_ALIASES` | TB 公式列词表，非上传列词表，单独展示。 |
| `backend/app/services/ledger_import/validation_rules_catalog.py::VALIDATION_RULES_CATALOG` | 导入校验规则目录（本次现算 10 条，L1/L2/L3），字段 code/level/severity/formula/tolerance/can_force；作为 import_validation 的平台基线。 |
report seed 相对 chart 的编码差集按来源现算；仅列未解析关系及可能的制度/扩展差异，不自动修码。本轮未取得项目覆盖层和有效定义。
逻辑数据表只用于两本 Excel 与来源清单，不是新增数据库模型或通用执行框架；产物根为 `docs/reviews/ias-filltb-fusion/`。

## 2. 外部证据边界
IAS 服务锚点：`tmp_ias_gitlab/ias-framework/src/cpas-server/nest/cpasApi/logic/methodapi/DisclosureService/dataSource/ds.service.ts::DSService.getDisclosureApiData`。
该服务按 DMName 查询 DataModel 并消费 SqlStr/SqlType，模型缺失返回 []；这只能证明依赖与行为，不能证明部署模型或业务结果。
下表 IAS_SQL 均指 `tmp_ias_research/utf8/DBUpdate/Script/6.0.0.076.sql`，不执行其中 SQL。
| IAS_SQL 符号 | 可收录行为 / 不可推导事项 |
|---|---|
| `PROC_ReportItem_Recal` | 科目与报表方向不同对相关余额/净发生额反号，分 SumLevel 汇总，按报表 Code 取上期；不得推成所有借贷分列统一反号。 |
| `PROC_ReportItem_SubjectRef_KMAnalyze` | 可见父关系继承、子级覆盖及合计关系展开；不能据此给平台未知编码授权前缀推断。 |
| `PROC_CFLKMConfig_AutoAnalysis` | 按 CW_KMB 名称查应收/预收、预付/应付、其他应收/其他应付三组往来，不是固定数字码对。 |
| `PROC_adjustEntries_autoCarryForward` | 有自动结转逻辑，但可见 BillID=@Data_ID 疑点，未实测；仅登记待审，不照搬。 |
`tmp_ias_research/utf8/PDM/workplatform 数据模型/企业基础数据/base.reportItems 报表项目基础数据.sql` 登记模型 `001`、DMName=base.reportItems。
字段字典保留 QCYE/QMYE（账面期初/期末）、QCWSS/QCSDS（期初未审/审定）、WSS/SDS（期末未审/审定）、LJFSE/WSLJFSE/SDLJFSE（账面/未审/审定发生额）及原方向，不混成一个金额字段。
实际 CW_KMB、完整 BB_ReportItemsRef/BB_ReportItemsSumRef、部署 DataModel 未取得；缺口行编码为空，missing_reason 明确，不把现存源码一并报成缺失。
FillTbTool 来源为 `tmp_filltb_research/km/cmp_AH_导入报表科目对照码.tsv`；只人工精选以下事实并追溯原文件 hash，不搬全表。
货币资金 1001 不等于平台库存现金 1001；坏账 1231/1232、其他综合收益 4005、专项储备 4102、盈余 4101、未分配 4103、研发 6605、信用减值 6691、其他收益 6201、资产处置 6811 均只列候选。
8001 系列属现金流项目，不当总账科目；“减：累计折旧和累计摊销”1523 与“减累计折旧和累计摊销”1524 归一后撞名，两条原样保留并标冲突。
平台同名候选可见 3102/3101/320104/6604/6702/6117/6115；专项储备 wp 的 M7→4301 与 chart 的 4301=研发支出另列平台内部冲突，不能用外部码覆盖。
`tmp_filltb_research/km/cmp_F_导入科目余额表.tsv` 的 1-A/2-B 为列位；`tmp_filltb_research/text/` 只作 C 级线索，不据其重建完整字典或声称规则生效。

### 2.1 IAS 数据采集工具（第三份外部来源，2026-11-11 增补）
材料位于 `C:\Users\baiji\Desktop\智审平台\张总发的资料\IAS作业平台\数据采集工具\数据采集工具`，只读复制到被忽略的 `tmp_ias_collector/` 后静态分析，未运行程序。
| 来源与锚点 | 可收录行为 / 不可推导事项 |
|---|---|
| `Excel财务数据采集V4.3.xlam` 宏 `AutoTableHeader.GetTableHeaderList` | 四张标准表（科目余额表、凭证表、核算项目余额表、核算项目明细表）按表分组的列同义词，如科目编号=科目编号/科目编码/科目号/科目代码/会计科目；凭证日期含过账/过帐日期。 |
| 同上 `Macros.ChekcTableFieldExists` | 必选列与字段依赖：期初金额与期初借/贷互斥、借贷成对、发生额方向只能配发生金额；注释写明不校验凭证平衡、科目级次完整、余额平衡。 |
| 同上 `Macros.GetPrimaryKeyForTableName` | 主键组合：余额表=科目编号；凭证表=日期+类型+编号+科目+借+贷+摘要；辅助表各有组合。只用于查重标色，不删除。 |
| 同上 说明表样例 | 余额表“借贷方向”是科目方向，“期初金额”借正贷负（如坏帐准备 借 -3221.62）。 |
| `SAP导出两张表…采集模板.xlsm` 宏 `exportOneFile_KMK/exportOneFile_PZK` | SAP 中文字段（科目、总帐科目、过帐日期、凭证编号、本币金额、借/贷标识 S/H、反记帐、清帐凭证、功能范围）；期初按余额方向拆为年初借/贷；科目级次规则写在说明页 D17。 |
| `三栏账处理规则\永安保险V1.bas` | 级次规则写法 `KMBH_JC="4222"`；按客户脚本解析一科目一页的三栏账，只登记为“需人工脚本的格式”，不收录脚本。 |
| `数据采集工具.exe`、`UFDumpHelp.chm` | 直连/备份/RFC/定时采集能力与支持软件清单，登记为“现场工具能力、平台不接入”。 |
| `DumpModel.mdb` | 有访问密码未打开；各软件采集表与字段标“缺数据”。 |
平台对照：上述同义词与 `identifier._RAW_HEADER_ALIASES` 逐词对照，平台缺失或误判的词（会计科目、科目号、分录序号、借/贷标识、余额、金额）标“候选/冲突”；字段依赖与主键规则与 `validation_rules_catalog.VALIDATION_RULES_CATALOG` 对照，平台没有的标“未实施”，由 A 的 A2.4/A6.4 承接。

## 3. 离线模型与字段字典
流程为“允许使用的本地材料 → 来源快照清单 → 分命名空间目录 → 候选关系/冲突 → Excel 人工审阅”；没有运行时发布出口。
namespace 固定为 import_alias、table_recognition、import_validation、standard_account、report_line、workpaper_note、push_rule、tb_formula_column；origin_system 为 platform/ias/ias_collector/filltb，必须参与身份。ias_collector 与 ias 分开：前者是现场取数工具的 Excel/SAP 模板规则，后者是 IAS 服务端取数与报表规则。
SourceSnapshot 保存来源版本；RuleRecord 保存原规则事实；CrosswalkRelation 保存独立关系边；ReviewDecision 保存决定。Excel 的数据表不另造关系数据库。
| 字段 | 类型与约束 |
|---|---|
| schema_version / catalog_version | 文本；前者描述字段合同，后者绑定本次目录内容，不与来源版本混用。 |
| rule_id / relation_id / source_id | 稳定文本 ID；来源文档有逻辑 ID，规则取系统+命名空间+原生键+适用维度，关系另有自己的 ID。 |
| native_key / identity_key | 原生 rule_id、科目码或带维度的复合键；无可靠键时首次分配明确 identity_key 并随目录保留，不依赖行序/内容 hash。 |
| source_path / snapshot_path / source_commit | 仓库相对路径及真实来源提交；无提交则 null+原因，未提交文件另标 working_tree，分支名不能替代 commit。 |
| source_sha256 / snapshot_sha256 / content_sha256 | 分别为原文件字节、允许保存的快照字节、规范化条目内容的 SHA-256，不相互代替。 |
| json_pointer / symbol / record_locator | JSON 用实际 Pointer；代码用全限定符号；TSV 用原始键+列名，重复时加内容摘要；定位可更新但不重分配 ID。 |
| original_code / original_name / payload | 编码/名称原串及原规则字段；payload 保留可选条件，Excel 按文本，不执行来源公式。 |
| applicable_standard / scope / template_variant / report_type | 文本维度；前两者组成国企/上市×单体/合并四口径，缺失须写原因，不能广播为四套通用。 |
| period_kind / amount_kind / direction / value_basis | 分别记录期间、余额或发生额、借贷/净额、账面/未审/审定等语义；不适用与未知分开。 |
| source_evidence | 源码/静态表/字符串线索/缺数据；可显示 A/B/C/D 证据等级，其中 C 不构成算法或生效证明。 |
| mapping_state | 未建立/候选/冲突/已确认；未建立用于尚无关系，冲突条目同时保持待审，不伪装已确认。 |
| integration_state / integration_evidence | 未实施/平台已有/待验收及依据；平台已有不是部署验收结论，外部候选默认未实施。 |
| source_rule_id / target_rule_id / relation_kind | 每条边各自成行；alias_of、account_to_report、workpaper_to_note、push_target 等须明确，不用单码字典装一对多。 |
| conditions / candidate_reason / conflict_group_id | 适用条件、候选理由和共享冲突组；不匹配的关系保留，不按得分强制选一条。 |
| orphan_reason / missing_reason | 源/目标无法解析、材料未取得或版本已退役的原因；缺失编码为 null/空白，不写“未知”充当码。 |
| source_version / lifecycle_status / supersedes | 原版本、草稿/审阅中/冻结/退役与替代 ID；冻结表示审阅快照固定，不表示生产启用。 |
| reviewed_by / reviewed_at / decision / approved_content_hash | 人工决定及所审关系内容 hash；无审批则空，不能填写生成工具为审阅人。 |
| authorization_status / allowed_use / authorization_evidence | 许可状态、允许用途及证明定位；合法材料获取与转换/发布授权分别记录，未知不推定可复用。 |
| created_at / updated_at | 首次形成及真实内容变更时间；相同输入重生成沿用，不刷新为当前时间。 |
规则可有多个 evidence_refs，但每条证据各自绑定 source_id/定位/hash/证据类型；不把某条源码证据升级成整组关系已证实。
身份维度确实变更时以新 ID 加 supersedes 表达；仅数组排序/位置变化更新 Pointer，内容修改保留 ID 并产生新版本，不靠内容 hash 重新命名规则。

## 4. 冲突、状态与采纳次序
- 四口径各自建立标准科目→报表行关系；同一科目指向多个报表/底稿可合法，记录关系类型与条件后再审，不把边数当唯一科目数。
- 同码异义、归一撞名、同条件互斥目标、未解析源/目标分别标记；编码差集不是自动错误，IAS 未得实际码不是自动孤儿替代码。
- source_evidence 只描述证据类别；mapping_state 描述决定；integration_state 描述接线。平台源码可为“源码/未建立/平台已有”，FillTbTool 候选为“静态表/候选/未实施”。
- 本轮 Excel 中外部映射没有已确认条目；日后审阅决定须绑定关系 hash、端点规则 hash、维度与许可范围。改变被审内容后旧批准只作历史，当前回候选/冲突。
- 采纳排序：已确认且适用的平台规则优先；平台静态源作为候选基线；有授权的 IAS 源码行为可供独立设计；FillTbTool 精选事实仅供人工对照；C 级线索不进入自动采纳。
- 上述优先级不能覆盖语义或许可冲突，未知维度不靠高分补齐；平台本身冲突也须揭示，不能因为“平台已有”就判正确。
- 材料可见≠许可已确认；未来转换/发布须另有明确授权、被选规则清单和平台接入验收，目录状态本身没有执行能力。

## 5. Excel 与来源清单
两本 Excel 已生成，`docs/reviews/ias-filltb-fusion/validation_report.json` 与 `docs/reviews/ias-filltb-fusion/final_validation.json` 均记录 passed。下表说明内容覆盖，不固定页数或规则总数；最终页名、数量及验证结果以最终报告为准，README 说明页名、含义与计数口径。
| 文件 | 内容覆盖 |
|---|---|
| `规则目录_审阅稿.xlsx` | 平台导入别名、表识别、标准科目、报表行、底稿附注、推送规则、公式 TB 词表、IAS 可见规则、FillTbTool 精选事实、差异融合与待确认、来源清单、字段字典。 |
| `编码对照表_审阅稿.xlsx` | 差异融合总览、平台科目基线、国企单体、国企合并、上市单体、上市合并、IAS 候选与缺口、FillTbTool 关键候选、一对多关系、冲突孤儿与待确认、来源清单、字段字典。 |
表头冻结、筛选及换行用于人工审阅；编码和公式字面量写为文本，金额解释不代入运行结果；来源/状态列可见，不能只放颜色。
source_manifest.json 保存 SourceSnapshot、材料缺口、快照/原文件 hash 及真实来源 commit；平台与 IAS 仅保存许可允许的快照，FillTbTool 快照仅为精选事实摘要，不复制整份商业词库。
README.md 说明生成口径、许可边界、数量口径、未查库、候选非批准、重生成规则及未完成项；源文件留在 tmp_* 时必须有允许保存的审阅快照或明确“不可持久复核”原因，不能只给易消失路径。

## 6. 重生成、正确性约束与离线验收
按固定系统/命名空间/维度/稳定 ID 排序；规范化 JSON 仅排序对象键和语义无序集合，保留原码原名、类型及有序数组；内容 hash 排除时间戳和展示行号，来源文件 hash 按原字节算。
目录逻辑摘要覆盖 schema、规则、关系、审阅决定和实际来源引用；同摘要沿用版本/更新时间并不重写文件，避免 xlsx ZIP 时间戳造成假差异；源定位或许可变更也应可追踪。
记录删除不静默丢行，标退役/孤儿；内容变更使当前关系重新待审。首次身份无法稳定匹配时列待人工对齐，禁按名称“猜回”旧批准。
P1 身份/溯源闭合：每行可解析 source_id 与本版定位，改行序不改稳定 ID（R1/R2/R6）。
P2 状态不越级：证据存在、文件生成、平台已有均不能推导 mapping_state=已确认或运行生效（R3/R5/R7）。
P3 原码/维度无损：原串、前导零、四口径及一对多边独立保留，冲突不被归一覆盖（R4）。
P4 重生成幂等：同材料与决定得到同逻辑摘要、版本与更新时间；变更不自动沿用批准（R6）。
离线验收读取真实工作簿，核对工作表及字典、唯一 ID/端点引用、source_manifest hash、文本编码读回、三维状态枚举、精选冲突、四口径计数及重生成差异；最终结果记入验证报告，不代表数据库或平台运行验收。
前导零可用独立且明确标“合成、非真实编码”的内存写入/读回自检验证，不混入事实目录；验证失败如实保留未做，不靠固定总数或空集合证明通过。

## 7. 阶段交接与明确不做
两份 spec 的边界已统一：0 只交离线目录，不提供 runtime alias 包；A 参考 0 已核实目录，在现有 identifier/adapter 规则载体内独立实现经确认的语义。本轮 Excel 不直接加载，外部未确认不启用。
采集工具增补条目经审阅确认后，由 A 的任务 3（同义词、字段依赖、SAP 中文字段）、任务 4（方向与单金额）、任务 6（级次规则）、任务 7（重复检测）、任务 13（标准模板）落地；0 不改平台代码。
A 可继续使用平台既有通用规则及人工确认；单位 spec 的依赖保留，未就绪时仅受影响的激活场景保持未验收，不阻断 A 其他开发。
目录转换/发布及报表、重分类、结转须另行批准并采用现有平台链条；不复制 IAS 过程，不另建 FS_CELL 或万能映射执行器。0 不承诺 API/UI/数据库实现。
离线产物最终验收状态见 tasks.md；文件生成、映射批准与产品接入分别记账，平台产品仍未实施。

## 8. 最终交付核验
实际工作表为规则目录24页、编码对照20页；每本首页均有阅读说明与14项三方横向差异。最终直接核验通过，报告见 `docs/reviews/ias-filltb-fusion/final_validation.json`。完整多轮重建检查超时，未作为最终通过证据；平台运行与外部映射审批仍未执行。
