# IAS / FillTbTool 导入兼容（A）：设计

## 1. 基线与状态
实际基线为 HEAD `9684955683720068cf3aad82dfc5502a0194e73c`，分支 `sj-dev1.0`。本轮交付 0、A 两份 spec 与两本离线审阅 Excel；Excel 已生成并通过现有自检，spec 仅文档交付，无提交或推送。
以下“现状”来自只读源码核实，不代表真实部署或客户数据已验证；“目标”“拟新增/扩展”均待实施。平台产品未实施；0 仅交离线目录，金额单位专属 spec 仍是依赖合同，其未就绪仅影响对应激活场景的验收，不阻断 A 其他开发。

## 2. 现状与可复用机制
| 路径 + 符号 | 已核实事实与边界 |
|---|---|
| `backend/app/services/ledger_import/pipeline.py::execute_pipeline` | 按 sheet 重识别、解析、转换并分别写入；`row_dict[headers[i]]` 覆盖重复表头；unknown 在读取确认映射前被跳过，detect 的 merged_tables 不等于执行端跨表归并。 |
| `backend/app/services/ledger_import_mapping_contract.py::_mapping_dict/normalize_custom_mapping/resolve_sheet_mapping` | mapping_entries 转表头字典，丢 column_index 及确认的表类型/辅助列；自动映射也以表头为键。 |
| `backend/app/services/ledger_import/converter.py::convert_balance_rows/_first_decimal` | 按 company_code/account_code 分组，重复无辅助行取首条；不按 currency 分组，余额 base_row 不保留 accounting_period；年度借贷优先且 0 合法。 |
| `backend/app/services/ledger_import/identifier.py::_RAW_HEADER_ALIASES/_MERGED_HEADER_MAPPING` | 年初/期初净额仍共 opening_balance；不能据年度分列优先推断净额也已区分。 |
| `backend/app/services/tb_balance_rollup.py::leaf_condition/resolved_standard_code/period_movement_query` | 已有父子排重与最近祖先映射，认 `.%`；父子比较缺主体/币种，映射是项目级；`backend/app/services/trial_balance_service.py::TrialBalanceService.recalc_unadjusted` 已消费，不是首次实现。 |
| `backend/app/services/ledger_import/validator.py::validate_l1/validate_l2/validate_l3/evaluate_activation` | 普通 v2 全量只显式调用 L1；L2/L3 存在不等于接线。现行 gate 的 L1 与年度越界不可 force 豁免。 |
| `backend/app/services/ledger_import/append_stage.py::prepare_staged_append` | 已调用 merge_into_staged；冻结基准存在时再跑完整数据集业务校验，首导不进入该分支，无独立 incremental finalize 接线可据名称假定。 |
| `backend/app/services/import_validation_service.py::ImportValidationService.run_dataset_business_validation` | 查询要求 is_deleted=true，而 v2 写 false；仅凭“调用了校验”不能证明覆盖新写数据，尚未运行验证。 |
| `backend/app/services/ledger_import/orchestrator.py::ImportOrchestrator._finalize_detection` | adapter_hint 只查到局部 ID，未据此加载别名重识别；`backend/app/services/ledger_import/adapter_selection.py::select_adapter/merge_aliases` 未见接入该生产链。 |
| `backend/app/services/import_job_runner.py::ImportJobRunner._execute_after_claim` | 经 `backend/app/services/feature_flags.py::is_enabled` 的 ledger_import_v2 决定 v2/legacy；ledger_import_use_calamine 只选择 parser，入口名不能证明实际引擎。 |
| `backend/app/services/ledger_import/confirmed_mapping_dto.py::MappingEntry/NormalizedMappingDTO`；`backend/app/services/ledger_import/submit_gate.py::SubmitGate.validate` | 构件可复用但未见生产链完整接入；DTO 注释所称索引校验不等于已执行，normalized writer 也不能未经语义核查替换。 |
| `backend/app/services/ledger_import/detector.py::_detect_csv_from_path`；`backend/app/services/ledger_import/parsers/csv_parser.py::iter_csv_rows_from_path` | 编码透传，但分隔符分别探测，TSV hint 未贯穿；`converter.py::convert_ledger_rows` 保留逐条分录，辅助拆分不是业务去重。 |
| `backend/app/services/dataset_service.py::DatasetService.create_staged/activate/publish_dataset_activated`；`backend/app/services/import_event_outbox_service.py::ImportEventOutboxService.publish_one/replay_pending` | 已有 staged/active、冻结基准复验及 outbox，不新建增量/激活机制；`backend/app/services/dataset_query.py::get_active_filter` 无 active 的回退尚不保证 staged 不可见，须协调单位专属 spec。 |
| `backend/app/services/event_handlers/_impl.py::classify_auto_map_outcome/_persist_auto_map_outcome/_report_auto_map_outcome` | validation_summary.auto_map 保存 ok/low_coverage/empty/failed；job completed、active、published 与下游完成不同，sync.completed 也不能掩盖低覆盖。 |
| `backend/app/services/ledger_import/converter.py::_resolve_direction` | 方向列一律当“金额方向”：先 `abs()` 再按借/贷定号。合成实测 IAS 样例“坏帐准备 / 借 / -3221.62”转成借方 3221.62，原负号丢失。 |
| `backend/app/services/ledger_import/converter.py::convert_ledger_rows/_resolve_entry_direction` | 只按方向列标 `entry_direction`，不移动金额栏位。合成实测“发生金额+发生额方向”一借一贷 100，写入借 200、贷 0；SAP“本币金额 ±375317094.9”两行都进借方，借方合计 0。 |
| `backend/app/services/ledger_import/identifier.py::_match_header` | 合成实测：会计科目→accounting_period、余额→opening_debit、金额/发生金额/本币金额→debit_amount，均为 70 分模糊命中；科目号、分录序号、借/贷标识未识别。pipeline 以 `confidence >= 50` 自动采用。 |
| `backend/app/services/ledger_import/adapters/sap.py::SapAdapter.get_column_aliases` | 只有英文表头（Posting Date / G/L Account 等），中文 SAP 导出字段不在其中。 |
| `backend/app/services/ledger_import/converter.py::infer_level` | 只按编码总长度推级次（≤4/6/8/10）；SAP 10 位码 `1220100000` 判为第 4 级，无级次规则输入口。 |

## 3. 目标数据流与确认合同（待实施）
`不可变来源 → detect 列位置/语义证据 → 人工确认 → submit 校验并持久化 → worker 核合同 → 原位置解析 → 期间归并/层级选择 → staged 最终校验 → 既有激活/outbox → 下游结果`。
- 优先扩展既有 MappingEntry/ConfirmedMappingDTO/SubmitGate，不另建平行 DTO；拟增来源文件项身份、表头路径、期间类型/区间、借贷角色和规则版本，明确均非现存保证。
- `column_index` 在 sheet 内零基唯一且有界；身份同时绑定 bundle 文件项与指纹，不能仅用显示文件名+sheet 名；canonical_header 仅用于显示，不能重新作取值主键。
- 前端 `audit-platform/frontend/src/components/ledger-import/ColumnMappingEditor.vue::onConfirm` → `backend/app/routers/ledger_import_v2.py::SubmitRequest` → job.custom_mapping → pipeline 全程保留同一确认合同与摘要；辅助列和人工表类型一并消费。
- worker 按原始行位置读值，保留来源行身份与 raw_extra 中未映射/冲突数据；索引、表结构或规则版本变化需重新确认，不能重猜后继续。旧字典仅在唯一定位时转换。
- 期间/借贷语义先作硬约束，再在合格候选内匹配别名；未知子表头无“精确”置信。adapter 证据必须含真实规则版本与匹配来源，不能只回显选中 ID。
- 字段依赖规则在映射确认时执行（参照 IAS Excel 采集模板的规则，独立实现）：期初净额与期初借/贷分列互斥；借、贷分列成对；“单金额+方向”与借/贷两栏二选一；违反即阻止提交并标出冲突列。
- 置信度分档：精确同义词（含 0 审阅确认的按表分组同义词）可自动采用；子串或编辑距离命中一律标“待确认”，用户确认后才进入 `col_mapping`。歧义词（会计科目、余额、金额、借方余额、贷方余额）结合表类型、相邻列与样本值判断，判断不了就问用户。
- SAP 中文字段在现有 `adapters/sap.py` 增加中文别名；`借/贷标识` 的取值 S/H、D/C 归一到借/贷；`反记帐` 只作留痕字段，本 spec 不据此改金额。

## 4. 期间归并与金额语义（待实施）
- 拟新增 `backend/app/services/ledger_import/period_aggregation.py::aggregate_balance_periods`，承担同一批跨 file/sheet/chunk 余额归并；不是新的增量服务，序时账保持流式逐行。
- 中间记录拟保留来源行、主体、币种、科目、辅助组合、年度/区间、月期初/期末、年初净额/月初净额、月借贷与累计借贷。年初净额独立语义键拟为 year_opening_balance，不能提前压成 opening_balance。
- 先按主体/币种/科目/辅助组合/年度分区，再在区间内排序选择；主体或币种不明须确认，不能因共用 default/CNY 合并两个来源。同一期多个来源先裁决，不随文件顺序取首行。
- 年度借贷字段现有优先及零值合法保持；净额/分列须在同一期间内校核，不跨期间拼借贷；非法年度值不能当缺失回退。最终才投影到四表已有金额字段及符号合同。
- 方向列含义判定：在 `_resolve_direction` 之前确定 `direction_semantics ∈ {account_direction, amount_direction, unknown}`。依据依次为人工确认、规则包声明、样本特征（同一方向下金额正负混杂且负值集中在备抵/往来科目 ⇒ 倾向科目方向）。`account_direction` 保留原符号、方向只用于校核；`amount_direction` 沿用现行定号；`unknown` 进入待确认，不默认任何一种。
- 单金额拆分：拆分发生在 `convert_ledger_rows` 写入金额栏之前；方向值归一表（借/贷、D/C、S/H、1/-1）登记在同一处，拆分来源记 `entry_direction_source`。拆分后按凭证（日期+类型+编号）汇总借贷，差额超过 0.01 的凭证进入回执，复用既有 `BALANCE_UNBALANCED` 的明细输出，不另建规则码。
- 月发生额只对互不重叠且覆盖明确的月相加；累计只取截止期，不对各月累计求和。累计和月合计并存则对账；非年初起点须有可证的边界累计或直接月值，不擅自补差。
- 期初取目标区间首期、期末取末期；年度结果必须有年初依据。缺月、重复、跨年或金额冲突记录覆盖与取舍，无法闭合则阻断；乱序本身排序后不改变结果。
- 自洽合成例（借方类、同主体币种）：1 月 `100+30−10=120`；2 月 `120+40−15=145`。1–2 月结果为期初 100、借 70、贷 25、期末 145；月累计 `(30,10)/(70,25)` 只选末期 `(70,25)`，不是 `(100,35)`。
- 来源/选中期间/冲突及人工决定写入既有 raw_extra 与数据集摘要的版本化扩展；无损保留原行。大余额集采用受控分区暂存，不把全部分录读入内存；增量继续调用 prepare_staged_append/merge_into_staged。

## 5. 层级、辅助与解析（待实施）
- 在现有 rollup 单源中消费已确认层级证据：显式父码/级次优先；分段码或紧凑码前缀须有编码方案证据，禁止将 `.%` 简单换成 startswith。最近祖先只沿已验证关系找，存在主体映射冲突则待确认，不凭项目级映射任选一条。
- 科目级次规则（如 `4-2-2-2`）是紧凑码的编码方案证据：导入确认页可填写，按项目保存并在后续导入沿用；`infer_level` 有规则时按规则切分，无规则时保持现行长度推断但标“推断”。持久化位置实施时现核 ORM（优先放项目已有配置字段），不提前占迁移号。
- 同主体/币种/期间内逐字段勾稽父子；例如父级 100、子级 60+40 可选子级合计 100；父级 130、子级 60+40 的残差 30 不得消失。人工选择保留有依据的直记残差或权威层，保留证据且防止父子再相加；未知则不激活。
- 一来源行多辅助维度只计一次主金额；辅助按 aux_type 分开核对，并保留维度组合与原行关联。客户视图/部门视图是同一事实的不同投影，不能作为两份主余额相加；重复维度 token 可按同一原行身份归一，不按金额删分录。
- CSV detect 与 parse 共用已确认 parser 合同；文本编码保留原串和前导零，不猜补已经丢失的位数。坏数/非有限数带位置报错，空值不改成零；数值合法性和单位归一复用专属合同，不再写第二套金额解析规则。
- 重复检测：余额表按主体/币种/科目/辅助组合/期间查重，替换 `convert_balance_rows` 现行“取首条”；分录按日期+类型+编号+科目+借贷金额+摘要查重，只进回执不删除（与 A6.2 一致）。
- 标准导入模板：在现有导入页提供下载，四页表头直接使用 `identifier` 精确同义词，生成逻辑复用平台已有 openpyxl 模板导出写法（参照 `routers/adjustments.py` 的模板下载）；模板表头变更须同步一条“模板表头 ⊆ 精确同义词”的守卫测试。

## 6. 校验、激活和下游（待实施）
- 全量与增量最终 staged 集合都进入 L2/L3 及业务校验；修齐查询软删位与分区口径，按实际写入行数校核扫描分母，缺表/无适用项必须显式说明，不能用空结果证明通过。
- 保留 L1 与不可豁免码，业务 force 仅延续既有权限和错误范围；执行失败、合同不确定、漏跑校验不产生可豁免的“成功”。金额容差不随本 spec 放宽，计算沿用统一 Decimal/符号合同。
- 复用 DatasetService 的激活事务、冻结 active 基准和 outbox；失败不动旧 active。无 active 时读取隔离和单位/attempt 合同由单位 spec 承担，受影响的激活场景须等该合同可执行后验收；其他 A 开发可继续，不复制实现或声称当前已安全。
- 结果回执绑定确认摘要、实际列/期间/层级选择与行数，并分别展示解析写入、校验、激活、投递和下游状态；复用 auto_map 与既有各消费者回执，尚无最终证据显示“待反馈/未验证”，不虚构完成。

## 7. 与 0、单位 spec 的边界
- 两份 spec 已统一：0 仅交离线规则目录、编码候选对照及来源记录，不提供 runtime alias 包；A 不依赖 0 的运行包。
- A 参考 0 已核实目录，在现有 identifier/adapter 规则载体内独立实现经确认的语义，记录实际平台规则版本、匹配依据及人工取舍。本轮 Excel 不直接加载，外部未确认不启用；其他场景可继续使用平台通用规则与人工确认。
- 金额单位参考 `.kiro/specs/platform-global-display-settings-closure/requirements.md::R7/R8`；source unit、换算、舍入、存储单位证明和 staged 可见性改造归该 spec。未就绪时仅受影响的激活场景保持未验收，不阻断 A 其他开发，也不另造转换器。
- 材料可见不等于授权已确认；独立实现前按证据核对许可与允许用途，不复制闭源代码、资源或许可机制。实际样本需登记许可范围与脱敏方式；合成样本注明“合成、非真实客户”。

## 8. 拟改动清单与切换风险
| 拟触达现有位置或新位置 | 待实施内容/依赖 |
|---|---|
| `audit-platform/frontend/src/components/ledger-import/ColumnMappingEditor.vue::onConfirm`；`audit-platform/frontend/src/views/LedgerImportPage.vue` 的确认/提交处理 | 列位置与歧义确认、实际回执；必要时扩展现有结果组件，不另建导入页。 |
| `backend/app/routers/ledger_import_v2.py::SubmitRequest`；mapping_contract 的 normalize/resolve；confirmed_mapping_dto 与 SubmitGate | 统一执行合同、旧字典转换；已可透传的 orchestrator/runner 不为改动而改动。 |
| `backend/app/services/ledger_import/{identifier,adapter_selection,detector,parsers/csv_parser,writer,pipeline}.py` 的识别/解析/写入符号 | 在现有规则载体内独立实现经确认的语义、按位置取值、共同 CSV 合同及生产接线；0 仅作离线参考。 |
| `backend/app/services/ledger_import/converter.py::convert_balance_rows`；拟新增 `period_aggregation.py::aggregate_balance_periods` | 保留期间语义并跨表归并，修首条选择；新符号尚不存在，不作为现状引用。 |
| `backend/app/services/ledger_import/converter.py::_resolve_direction/convert_ledger_rows/infer_level`；`adapters/sap.py` | 方向含义判定、单金额拆借贷、逐凭证平衡、级次规则切分、SAP 中文字段。 |
| 现有导入页 + 一个模板下载端点（挂在 `routers/ledger_import_v2.py`，项目 readonly 鉴权） | 标准导入模板下载；不新建导入页面。 |
| `backend/app/services/tb_balance_rollup.py::leaf_condition/resolved_standard_code` 及其 TB/发生额调用方 | 同一层级与分区口径；持久化若需新字段，在实施时核对 ORM/迁移，不提前占迁移号。 |
| `backend/app/services/ledger_import/{validator,append_stage,pipeline}.py`；`backend/app/services/import_validation_service.py::ImportValidationService.run_dataset_business_validation` | 全量/增量最终校验和现有状态回执；dataset_service/outbox 优先复用，仅按真实接缝修改。 |
- **特性开关/切换点**：沿用 worker 的 ledger_import_v2 分流，不新增同义总开关；在 enqueue 前和 worker 分流前核合同支持范围。开关关闭时仅已证明等价的合同可走 legacy，不支持的新语义拒绝且要求确认，不自动丢字段降级。
- **旧链核查**：实施时从已注册路由核对 legacy 的 smart_import_streaming、现存异步入口和退役入口；全量/增量及两种 flag 均纳入兼容清单。关闭 v2 不是撤销已激活数据，回退数据集只走既有受控流程。
- **风险/降级**：外部语义未确认→不启用该语义；单位合同未就绪→受影响的激活场景保持未验收，其他开发可继续；层级/期间证据不足→待确认；资源不足→受控暂存或失败；下游失败→报告并沿用 outbox 重试，不把解析重跑当恢复。不得以放宽 force 或跳过校验降级。

## 9. 正确性约束与验收矩阵
P1 来源/列身份及确认写入一致（A1/A2/A8）；P2 同边界下行序、sheet/file/chunk 划分不改变归并结果（A3/A4）。
P3 主体/币种/辅助投影隔离且层级选取不丢直记金额（A4/A5/A6）；P4 检查未完成则不激活、下游未知不报成功（A7/A8）。
P5 方向与栏位守恒：同一笔经济事项无论来源是借贷两栏、单金额+方向、还是带符号单金额，转换后借方合计、贷方合计与每张凭证的借贷差额都相同（A3.4/A3.5）。
下表 32 项均为**计划中的隔离合成、非真实客户验收**；本轮未执行，金额均为同一已确认单位。端点/集成使用独立临时库，browser 使用独占服务，不连接共享库或共享 3030/9980。M25~M32 来自 IAS 数据采集工具的样例格式，对应的平台现状已用合成样本调用纯函数实测（证据见 `docs/reviews/ias-filltb-fusion/IAS数据采集工具对比分析.md` §4）。
| 编号 | 场景及明确预期 | 覆盖/未来层级 |
|---|---|---|
| M01 | 两列同名“借方”值 3/7 均保留，人工选列与写入一致 | A1；端点→worker 集成 |
| M02 | 重名文件、索引越界/重复、来源版本改变要求重新确认；唯一旧字典可无损转换 | A1/A8；合同/端点 |
| M03 | 年初借方与期末贷方不能串位，合并表头路径参与判定 | A2；解析 |
| M04 | 未知子表头不获精确置信，显示候选与待确认原因 | A2；解析/browser |
| M05 | adapter 独有别名只有经确认并在现有规则载体中实现后才命中，回执记录实际版本；未实现不伪称生效 | A2；集成 |
| M06 | 年度 0、月度 9 时取 0；年初净额 100 与二月期初 120 分别保留 | A3；转换 |
| M07 | 非年初月缺年度依据或年度字段为坏数时阻断；借贷同期间，净额/方向冲突可定位 | A3/A6；转换 |
| M08 | 设计 §4 两月例产出 100/70/25/145，累计只取 70/25 | A3/A4；跨表集成 |
| M09 | 仅截止期累计可给年初至截止口径；无起点依据不能声称任意子区间 | A4；归并 |
| M10 | 文件乱序、拆成多个 sheet/chunk 后与 M08 相同 | A4/P2；属性测试 |
| M11 | 缺月、重叠来源、重复期间与跨年分别给原因，不补零或取首条 | A4；归并/端点 |
| M12 | 甲 CNY 100、乙 CNY 200、甲 USD 10 保持三个边界，无汇率证据不相加 | A4/A5；集成 |
| M13 | 显式父子 100=60+40 只贡献 100；点分与已证紧凑码同口径 | A5；rollup/TB 集成 |
| M14 | 父 130、子 60+40 的 30 残差待人工决定；同前缀未知码不能静默删父 | A5；集成/browser |
| M15 | 同一 100 行投影客户/部门，主表仍 100，各维度单独核对 | A6；四表集成 |
| M16 | 两条独立来源、同凭证同科目同金额分录保留两条 | A6；转换/写入 |
| M17 | CSV 引号内分隔符、TSV、BOM/GB 编码 detect/parse 同合同，编码 0012 不变 | A6；解析对拍 |
| M18 | 空值、0、坏数、NaN/Infinity 各有明确结果，坏数不入库为 0 | A3/A6；合同/端点 |
| M19 | 首次全量 L1/L2/L3 适用项真执行，扫描行数覆盖实际 staged 数据 | A7；隔离库集成 |
| M20 | 增量 merge 后校验全部最终行，基准已变化则不激活、不改旧 active | A4/A7；隔离库集成 |
| M21 | 校验不可用/意外零扫描阻断；业务 force 不增加权限或可豁免范围 | A7；合同/集成 |
| M22 | 写入、激活、outbox、auto_map 四阶段分别展示；低覆盖/失败/待反馈不全绿 | A8；集成/browser |
| M23 | v2/legacy flag、兼容旧入口及固定退役行为符合清单；新合同不支持时写前拒绝 | A1/A8；端点/worker |
| M24 | 独占 browser 完成确认→导入→刷新读回，与回执逐值相同；合成大账套行数不丢且内存有界 | A1–A8/N2/N3；browser/性能 |
| M25 | 余额表“坏帐准备/借/-3221.62、累计折旧/借/-466243.97、应付账款/贷/-924071.34”确认为科目方向后，三科目均为贷方余额，金额不变；含义未确认时阻止激活 | A3.4；转换/端点 |
| M26 | 凭证“发生金额+发生额方向”借 100 / 贷 100 拆为借 100、贷 100，凭证平衡；把其中一行方向改错后回执定位该凭证 | A3.5；转换/集成 |
| M27 | SAP 中文导出“本币金额 −375317094.9（H）/ +375317094.9（S）”识别借/贷标识，拆为借贷各 375317094.9；总帐科目、过帐日期、凭证编号精确识别 | A2.6/A3.5；解析/转换 |
| M28 | 同时提供期初金额与期初借/贷，或只有期初借方没有期初贷方，确认页阻止提交并标出冲突列 | A2.4；端点/browser |
| M29 | 会计科目、余额、金额、科目号、分录序号以 70 分命中时不自动采用，确认页逐列要求确认；精确同义词仍自动采用 | A2.5；解析/browser |
| M30 | 级次规则 `4-2-2-2`（共 10 位）下 `1220100000` 切为 1220/10/00/00，判第 4 级、父级 `12201000`；长度不符规则的 `12201` 列待确认；无规则时标“推断” | A5.4；转换/rollup |
| M31 | 同科目同期间两条余额行进入回执且阻止激活；完全相同的两条分录只提示、两条都写入 | A6.4；转换/端点 |
| M32 | 下载标准模板 → 按样例填写 → 导入，四页全部精确识别且无待确认列 | A8.4；端点/browser |
