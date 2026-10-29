# 设计：在线编辑双向回写收尾

## §1 现状（2026-10-26 现算，探针在仓库外，交付后删除）

- 91 份生产契约，受管字段 3841：可编辑 3168、公式 641、自动取数 7、跨表 25。按 merge 实际的逐格口径，遮罩格保护 0 个（旧普查按整列判遮罩，标出的 317 个「遮罩格无公式」是口径错误）。
- 后端 89 个 entry 都有 provider，91 份契约都是已审核态。上一份 design §9「已开启 45 / 未开启 32」口径不明，作废，不再引用。
- 字段名接通：2723 个带 store item 的受管字段里，至少 198 个字段名在整个前端源码里一次都不出现（§4）。这些格两侧不通：OO 改了写进 store，表单读不到；表单的值也到不了 OO。上一轮复盘「可编辑数值格都能回写」的说法据此更正。
- 模板公式错误：逐格核实 19 组（§2）。同型错误「审定数漏引期末未审 / 重分类」在 D5-2、F1-2、K3-2、N1-2、N3-2、N4-2 六张表出现；其余是首行 / 个别行写错、漏公式、小计行乱写、跨表引用指错行。

## §2 模板公式修正清单（R1）

判定依据：同表其他行、同循环同结构的表、表头语义三者一致指向的写法。只改公式与表头错字，不改样式、合并区、行列。逐格清单只有一份：`backend/scripts/fix/fix_template_formula_defects.py` 的 `fixes()`（第一批 19 本 285 格 #1~#19；第二批 6 本 43 格 #20~#28，其中 D1 两批都有；第三批 4 本 55 格 #29~#32；第四批 N5 1 本 3 格 #33 ⇒ 合计 27 本 386 格），守卫 `tests/workpaper_sync/test_template_formula_defects_fixed.py` 直接读它。

| # | 模板 / sheet | 格 | 现状 → 改为 | 依据 |
|---|---|---|---|---|
| 1 | D5 / 明细表D5-2 | O12:O16 | `=J+N+M` → `=L+M+N` | L=期末未审余额；D1-3/D2-2/D3-2/D7-2/F4-2/K1-2 同结构全是「期末未审+账项+重分类」 |
| 2 | F1 / 明细表F1-2 | X14:X34 | `=O+V+W` → `=Q+V+W` | 同 #1（Q=期末未审余额） |
| 3 | K3 / 明细表K3-2 | T10:T30 | `=O+R+S` → `=Q+R+S` | 同 #1 |
| 4 | N1 / 明细表N1-2 | H11:H40、N11:N40；G42、M42 | `=F+E`、`=L+K` → `=E+F+G`、`=K+L+M`；补 `SUM` | 表头含「重分类调整」列却不计入审定 |
| 5 | N3 / 明细表N3-2 | H11:H21、N11:N21、E23；G23、M23；H10 | `=F+O3`…、`=L+K`、`=SUM(E3:O22)` → `=E+F+G`、`=K+L+M`、`=SUM(E11:E22)`；补 `SUM`；「…资产期初审定数」→「…负债期初审定数」 | O3 起是空格；合计区间整块错 |
| 6 | N4 / 明细表N4-2 | E9、D19 | `=B9+C9+N4`、`=SUM(D4:N18)` → `=B9+C9+D9`、`=SUM(D9:D18)` | 第 10~18 行都是 B+C+D；D9 被写成本册 wp_code（与 A1 引用同形，Excel 不报错、恒取空） |
| 7 | H2 / 明细表H2-2 | D13:D20、AV13:AV20、AW13:AW20 | `=IF(AH=0,0,AH/B)`、`=R-AL`、`=AH-AS` → `=IF(B=0,0,AG/B)`、`=Q-AL`、`=AG-AS` | 期初侧 AT=J−AI / AU=Z−AP 用的是余额列；三处都错成右边一列（「其中：累计资本化」）；比例列除数是预算 B |
| 8 | G8 / 明细表G8-2 | M11；P11、P13:P20；R13:R20；T12；K21、L21、R21 | `SUM(I:L)` → `SUM(I:K)`；`=D+J` → `=D+J+K`；空 → `=F+J+L`、`=Q+S`、`SUM` | 其余行 M=SUM(I:K)、P12=D+J+K、R11/R12=F+J+L、T 其余行 Q+S；合计行其余列都有 SUM（M 的裁定见下） |
| 9 | D5 / 公允价值测算表D5-4 | G13:G16、I13:I16、J13:J16 | 空 → 与首行同式 | K 列五行都有公式 |
| 10 | D6 / 减值准备明细表D6-3 | N12、N17 | `=E+SUM(H:I)-SUM(J:L)` → `=K+L+M` | 同行其他列是小计，明细行 N=K+L+M |
| 11 | K1 / 坏账准备明细表K1-3 | L11 | `=D11+SUM(G11:G11)-SUM(I11:K11)` → `=J11+K11` | 明细行 L=J+K |
| 12 | D1 / 备查簿核对D1-7 | Q23 | `YEAR(A23)` → `YEAR(C23)` | 同列其他行取 C 列日期 |
| 13 | D4 / 识别未披露的关联方D4-27 | M17:M19（两本 D4 工作簿） | 空 → `=SUM(C:L)` | M15/M16 同式 |
| 14 | I3 / 明细表I3-2 | AA23:AD23、I14 | `=SUM(x27:x30)` → `=SUM(x14:x22)`；空 → `=SUM(D14:E14)-G14` | 同行 S23..Z23 全是 14:22；I 列其余行同式（原「覆盖层修」登记） |
| 15 | H3 / 明细表（公允价值模式）H3-2 | R13:R26 | 空 → `=P+Q` | 首行 R12 有；H7 同位列满格（原登记） |
| 16 | G5 / 余额明细表G5-2、审定表G5-1 | R40/R72/R104 的 D..R；B35；G9、H9 | 段合计漏加第三子区小计；`=B9-B225` → `=B9-B22`；`K13`/`L13` → `K18`/`L18` | 同段四个小计；同行 C..H 都是 `X9-X22`；同行 B..F 都取小计行 R18 |
| 17 | G7 / 长期股权投资审定表G7-1 | C39:E39 | `M62`/`N63`/`O63` → `M63`/`P63`/`Q63` | 同块 R40/R41 是 M/P/Q 小计；明细表 R79 S=H+N+P、T=I+O+Q ⇒ P/Q 是重分类增减。原式把账项调整重复计入「审定数2」 |
| 18 | K6 / 附注披露信息（上市公司） | E8:E11 | `=L12` / `L13`~`L15` → `=SUM(E9:E11)` / `L12`~`L14` | 上年年末数整列错位一行（同行 A/B 列取 R12~R14）；E8 应与 B8 一样是小计 |
| 19 | L4 / 附注披露信息核对（上市公司）、L4-3 | H30、H31；T18:W18 | `I17`/`I18` → `I19`/`I20`；`=N18+P18-R18` 类 → `=SUM(x13:x17)` | 同行其余列取 R19/R20（I17 是小计、I18 是区标题）；合计行期初调整四列是错位交叉式（原登记「只登记不改」） |
| 20 | D1 / 审定表D1-1 | B8:D8 | 取 D1-2 合计行 R14 → 取银行承兑汇票行 R11 | 同行期末 F..H 取 R11、下一行取 R13；取合计会让小计 B10 把商业承兑汇票算两遍。前端按票据种类逐行取 D1-2，本就一致 |
| 21 | D1 / 坏账准备测试表D1-15 | E14:E17、E22:E24；E13、E21 | `=B−D` → 录入格；表头「④=①-③」→「④」 | ④ 是被审计单位已记录的坏账准备（A8「与被审计单位已记录的坏账准备进行比较」）；写成 ①−③ 时 ⑤=③−④ 恒为 2×③−①；同结构 D2-9 的 ④ 是录入格 |
| 22 | D2-6至D2-13 / 应收坏账准备测算D2-9 | F14:F18；C19、D19 | `=B−E` → `=D−E`；C19 的 `SUM` 与 D19 的比例式互换 | 表头 ⑤=③−④，两个组合区各行都是 D−E；小计行「损失率」列在加总比例、「应计提」列在算比例 |
| 23 | D7 / 关联方关系及交易检查表D7-6 | F12:F14 | `=C+D−E` → `=C−D+E` | 合同负债是贷方科目，同册 D7-2 P=F−N+O、F4-6 同为 +贷−借；前端 `useD7RelatedParty` 本就按贷方 |
| 24 | D7 / 审定表D7-1 | D14 | `=SUM(D7:D13)` → `=SUM(D8:D13)` | 同行其余列 SUM(x8:x13)，R7 是表头行（数值不变） |
| 25 | G10 / 审定表G10-1 | H9、I9、G29 | 引 G8 → 引 G9 | 同行 D..F 与其他行都取本行，G8 是上一行小计 |
| 26 | D2-1至D2-4 / 坏账准备明细表D2-3 | B17:D17、F17:J17、L17:M17；N18:N21 | `SUM(x18:x20)` → `SUM(x18:x21)`；`=K+L` → `=K+L+M` | 组合区数据行 R18~R21，小计的 E/K/N 已求和到 R21；单项区 N13:N16 与同结构 D1-4 都是 K+L+M |
| 27 | D2-6至D2-13 / 预期信用损失的计量测试D2-10 | C90 | `=G70` → `=G69` | 方法 2 前瞻性调整逐行取 G64~G69，R70 是说明文字行 |
| 28 | G13 / 审定表G13-1 | G17、I7 | 引 G9 → 引 G7 | 合计行上期审定其余项取小计 R7（G9 是「衍生金融资产」）；R7 变动率分母同 |
| 29 | G14 / 明细表G14-2 | K11:K19 | `=G+H` → `=G-H` | 同行 J = F+G−H−I 把 H「本期转回」（正数）作减项；会计口径 信用减值损失 = 计提 − 转回。provider 原登记「模板缺陷、前端按 G−H」，改为已修留痕 |
| 30 | D6 / 减值准备测算D6-8 | F13:F17；C18、D18 | `=B−E` → `=D−E`；C18 的 `SUM` 与 D18 的比例式互换 | 表头 ⑤=③−④（应计提 − 账面），同结构 D1-15 / D2-9；小计行与 D2-9 #22 同一处错 |
| 31 | G9 / 明细表G9-2 | L、Y（R12~16、R19~23、R26~28） | `=E+K` / `=R+X` → `=J+K` / `=W+X` | 「期初 / 期末报表数」= 审定公允价值 + 重分类；原式取未审 E / R，同结构 G1-2 是 J+K / W+X |
| 32 | D2-1至D2-4 / 明细表D2-2 | H13:H25 | 空 → `=E+F+G`（带缓存值 0） | 期初审定余额漏公式；同表期末审定 AB=S+Z+AA，D1-3 / D3-2 / D5-2 / D6-2 / D7-2 期初审定都是未审 + 账项 + 重分类。同行 Q/S/AB 模板格是 `<f>…</f><v>0</v>`，只写 `<f>` 时未经 OO 重算的反读读不到 H（键缺失） |
| 33 | N5 / 加计扣除研发费用情况明细表N5-6-1、递延所得税费用核对表N5-8 | D11、E12；H12 | `SUM(D5:N16)`→`SUM(D12:D16)`；`C12+N5`→`C12+D12`；`…+N5…`→`…+D12…` | D11 是人员费用小计，仅覆盖 D12:D16；E12 同列 37:1、H12 同列 28:1 的正确形态都引用 D12。`N5` 与 A1 引用同形，Excel 静默当作 N5 单元格，吞掉 D12 分量；修后三族超列引用 17→0 |

- #15~#19 中的 G5-1 G9/H9、G7、K6、L4 附注是本轮用「同行跨表单格引用指向不同行」普查（117 条候选，逐条核后 4 处真错，其余是标签 / 目录引用或减值与余额分行）新发现的；L4-3 合计行、I3、H3、G5 是 provider 早就登记、原定「覆盖层修」或「只登记不改」的。
- 登记了但核实不是错误：F2-26!J9（模板已是 `=G9+H9-I9`）、F5-7!G31（已是 `G24+G25+G26-G27-G28-G29-G30`）——登记文字过期；F4-6 B8:B11 下拉来源指向空列、L3-7 的 `#REF!` 与断开的定义名不是可按同表推出正确写法的公式错误，不改。
- **G8 M 的裁定（请用户确认）**：取 `M = SUM(I:K)`（不含 L），推翻 C-6 §3.3「M 应含 L」。依据：M 是投资账面的本期变动，必须满足 `E + M = Q`（Q = O + P = C+I + D+J+K）；L「其他综合收益转入留存收益」是终止确认时权益内部结转，只减少 R 列 OCI 累计、不改投资账面；修复前 10 行里 9 行本就是 SUM(I:K)。含 L 会在处置时把 L 重复计入。前端随之改为 I+J+K。
- 落地方式沿用 `fix_d3_template_footer_defects.py`：直接改 worksheet XML（共享公式只改主格），openpyxl 逐格比对作判据，只允许清单内的格变化，幂等。**不走模板覆盖层**：原「覆盖层修」从未实现（库里没有覆盖文件，没有代码读覆盖层），且契约按权威模板冻结。
- 连带更新：provider `TEMPLATE_SHA256` 与审核依据文本、`generate_phase5_*` 重生成 18 份契约（K3 / K6 原先不在 K 生成器清单里，补上）、`g7_column_source_facts.json`、`tests/_snapshots/wp_templates_baseline.json`（同时补回 29 本早已提交却从未回填的净化改动，守卫在 HEAD 上本就是红的）、`data/prev3_prefill_locator.json`（只变 16 行 sha）、12 份 manifest slice（文本级刷新，`D4收入底稿.xlsx` 改名登记）、`_sync_provider_golden_digest.json`、两个变异脚本的锚点；归档 spec 证据与 `definition_store` 历史不改。
- 第二批同口径：13 个 provider + `delivered_contracts_ledger`、6 份契约（d1.notes_receivable_detail / d2.inspection / d2.receivable_detail / d7 / g10 / g13）、模板快照（模板总字节 45_834_727 → 45_795_461）、预填定位表、D / G 两份 slice、golden、两个变异脚本锚点、D2 大 JSON 试点的模板字节数常量（123_162 → 105_407，解压后只有 sheet9 变）。契约顺带两处：D1-15 E 列由公式字段改为可编辑（#21）；D1-4 G「其他增加」→ `currentOther`、J「其他减少」→ `currentRecovery`（原映射位置对、加减方向反：前端「收回」是减项、「其他」是加项）。
- 第三批同口径：provider（G14 / D6 / G9 / D2 大 JSON 试点）与 `delivered_contracts_ledger`、`wp_surfaced_g` 文案、4 份契约（d2.receivable_detail / d6.contract_assets_detail / g9.other_noncurrent_detail / g14.credit_impairment_detail）、模板快照（45_795_461 → 45_775_626）、预填定位表、D / G 两份 slice、golden、三个变异脚本锚点（task41 / task46 / task49）。契约顺带：D2-2 H「期初审定」由可编辑改为公式字段（#32）；G14 provider 的 `TEMPLATE_ROW_DEFECTS_G1402` 改为已修留痕 `TEMPLATE_DEFECT_K_G1402`。
- 第四批同口径：N5 三格（#33）、`phase5_n5_sheets.TEMPLATE_SHA256`、N5 reviewed 契约、模板快照、prev3 哈希与 N slice 两处模板事实；旧 N lane 守卫由「缺陷存在」翻成正确公式，超列三族现算从 17（A1 3 / A2 11 / B 3）清零，错口径扫描 193→176。
- 前端无对应计算的组（G5-1 期末账项 / 重分类是手填、G7-1 / K6 附注 / L4 附注与 L4-3 合计行前端不逐格复刻）只改模板。

### 存量产物（真实项目）

已发布的在线编辑产物冻结的是旧契约身份。模板与契约变了之后，下列真实项目的这些底稿再打开在线编辑会报「冻结身份与生产契约脱钩」，重新发布前不能在线编辑；HTML 表单编辑不受影响。用户只批准【测试】项目，未重发布，待用户决定（`scripts/fix/republish_entry_from_template.py --wp-id … --apply`）：

- 重庆和平药房连锁有限责任公司_2025（14）：D5、D6、G7、G8、H2、H3、I3、K1、K3、K6、L4、N1、N3、N4
- 重药控股安徽有限公司_2025（4）：D1、D4、F1、G5
- 第二批（契约 d1 / d2.inspection / d2.receivable_detail / d7 / g10 / g13）：重庆和平药房_2025 的 D2、G10、G13；重庆和平药房_2024 的 D2；重药安徽_2025 的 D1、D2、D7
- 第三批（契约 d2.receivable_detail / d6 / g9 / g14；`working_paper_sync_entry_state` 现查）：新增重庆和平药房_2025 的 G9、G14；D2（和平药房_2024 / _2025、重药安徽_2025）与和平药房_2025 的 D6 已在前两批名单内。L1 / L5 / L6 / L8 只改前端、契约未变，不需要重发布
- 第四批：重庆和平药房连锁有限责任公司_2025 的 N5 已有 generation=1；模板和 N5 契约已变，按「只做【测试】项目」约束未重发布，列入待用户放行清单。真库没有 N2-2 旧键或新键数据，本轮无需迁移。

第一批没有【测试】项目发布过这些 entry，【测试】项目首次打开即按新模板发布。（原设计「未重发布的项目 OO 侧仍是旧公式」的假设不成立，以此为准。）第二批发布过 D2 的两个【测试】项目（OO公式重算验收、在线编辑回表单验收）都已删除（项目在回收站），重发布报「冻结 bundle 与契约脱钩」、provisioning 按可见性过滤找不到目标——打不开的产物无需重发布。

## §3 前端按模板对齐（R2）

### §3.1 上一轮登记的 D1~F5 不一致项

| 项 | 处置 |
|---|---|
| 贴现利息天数（D1-9、D5-4 前端 360，模板 365） | 前端改 365（`useD1FormulaEngine` / `useD5FormulaEngine`） |
| D5-2 期末审定、F1-2 审定 | 模板改为含重分类（§2 #1/#2），前端改回以期末未审 L / Q 起算 |
| H2-2 进度比例 | 模板 D=AG/B（比例）；前端 `calcBudgetInputRatio` 存比例、显示 ×100，「超预算」判 >1 |
| G8-2 M | 前端 M=I+J+K（§2 裁定） |
| 差额方向 D1-15 / D2-9 | 模板先改（§2 #21 / #22）；前端 `calculateDifference` 改为「应计提 − 账面坏账准备」（模板 ⑤=③−④，原为反向），D1 / D2 引擎与废弃的 `useD1NotesReceivable` 同改 |
| D7-6 期末方向 | 模板改为 +贷−借（#23）；前端本就按贷方，不改 |
| D1-4 / D2-3 / D6-3 坏账 / 减值明细 | 期末未审改从期初未审起算（模板 K = B+SUM(F:G)−SUM(H:J)）。D1-4 列序按模板 F~J 重排（其他增加 / 其他减少（含收回）），契约映射见 §2 第二批；D2-3「转入 / 收回」两列绑的是行模型里不存在的 `currentTransferIn` / `currentRecovery`（录入恒被丢弃），改绑 `currentOtherIncrease` / `currentOtherDecrease` 并补「其他减少」列 |
| D1-7 备查簿核对 | 前端按模板重做：Q~W 七列由公式派生、只读（`deriveMemoRow`）；状态取值改为模板的 背书 / 贴现 / 到期承兑 / 未到期，旧值（已背书 / 已贴现 / 到期 / 持有）载入时映射；核对表改为 期初 / 本期增加 / 本期减少 / 期末四列，备查簿侧取 Q25 / R25 / S+T+U，账面侧取 D1-2 未审 B / F / G；未到期汇总按 X / K / A 分「终止确认 / 未终止确认」（G29:G32 的 SUMIFS）并给 H34 差异 |
| F4-6 关联方 | 联动行期初取 F4-2 期初未审、核对来源取 F4-2 期末余额 K；期末恒为 期初 + 贷 − 借；风险标记改为「与F4-2期末余额不一致」 |
| 变动率分母为 0 | 新增 `templateChangeRate.ts` 统一模板式 `IF(AND(期初=0,本期=0),"",IF(AND(期初=0,本期>0),1,变动/期初))`：两者都 0 → 空，本期 >0 → 1，本期 <0 → 'N/A'（模板 #DIV/0!，原先记 100% 或 −1）；空值按模板变体（D 类 ''，F1-1 / F4-1 为 0）。D1 / D2 / D3 / D5 / D6 / D7 / F1 / F4 审定表都改用它 |
| F3-1 / G3-1 / G10-1 期末未审 | 改从期初未审起算；F3 披露分类无明细行时用已存的本期贷方 / 借方 |
| D2-10 | 结构不同（模板是平铺情景行、两年现值；前端是嵌套 `scenarios[]`、单一现值），并入 R3（任务 9.4）；模板 C90 错格已修（#27） |
| D6-3 / K1-3 小计、D4-27 总计、D1-1 / D2-3 / D7-1 / G10-1 / G13-1 模板修正 | 前端小计是逐列线性求和、K1 合计按 J+K 重算、D4-27 行总计本就计算、其余前端按行取数，修正后的模板与前端一致，不改前端 |

另：核 F3-1 时发现 HEAD 既有崩溃（`f2d7334ac` 引入）—— `letter_of_credit` 在 `F3_CATEGORY_META` 里却不在 `aggregateDetailByCategory` 的累加器里，有信用证明细时 `TypeError: Cannot read properties of undefined (reading 'count')`；累加器与 `activeCategoryKeys` 改为由 `F3_CATEGORY_META` 生成，测试补 5 类。

### §3.2 G~N 普查

普查工具就是 R2.4 的对拍守卫：守卫首轮现算出的不一致项逐条记入本节表格并处理（改前端，或登记理由）。

首轮现算（2026-10-26，生成器 `gen_template_formula_parity.py` 读 wsr_head：行表公式字段 480 个，换成字段名表达式 372 个、跳过 108 个——占位 store item 74、引用他表 9、非受管录入列 11、SUMPRODUCT / SUMIF / YEAR 10、他行 4；再逐表读前端行计算核对）。同字段映射下前端算法与模板不同的：

| 表 | 现象 | 处置（第三批已做，除注明 R3 / 待定） |
|---|---|---|
| L1-2 / L5-2 | 审定列（L1 R~U、L5 L~O 与披露 R/S）前端声明了字段却从不计算，恒 0 | 前端按模板公式计算（`recalcL1DetailRow` / `recalcL5DetailRow`，载入、渲染、编辑、保存都经它） |
| L6-2 | 审定四列（P~S）是手填，账项 / 重分类调整进不了审定 | 前端按 P=C+H+I 等计算、四列改只读；两张附注改读 `L6-L6-2-rows`（原读的 `L6-L6-2-row{i}-*` 键没有写入方） |
| G14-2 | 模板 K「计入损益」= G+H，同行 J = F+G−H−I 把 H（转回，正数）作减项 | 模板改 K=G−H（#29），前端本就 G−H |
| D6-8 | 模板单项区 F =「审定余额 − 账面坏账准备」B−E；同结构 D1-15 / D2-9 是「应计提 − 账面」D−E | 模板改 D−E（#30） |
| G9-2 | 模板「报表数」L = E+K、Y = R+X 取未审公允价值；同结构 G1-2 取审定（J+K / W+X） | 模板改 J+K / W+X（#31），前端报表数同改 |
| D2-2 | 期初审定 H 模板无公式，前端按 E+F+G 算 | 模板补公式（#32），契约改公式字段 |
| H3-2 成本区 | 前端期末多算「转入 / 转出」两列（模板没有）、审定三列按「未审 + AJE + RJE」而模板是审定滚动（O=L+M−N 等），模板 I~N / V~AA / AI~AN 前端无字段 | R3（对拍未覆盖清单） |
| H4-2 | 审定减值期末前端 = 期末减值 + 一个净调整，模板 AS=AP+AQ−AR 分期初 / 增加 / 减少调整；J / M 是前端由子项推出、契约当录入 | R3（对拍例外 2 条：J / M） |
| G13-2 骨架 / G14-2 | 核对列按 `|差| ≤ 0.01` 判，差一分时浮点结果落在 0.00999… 就判成一致，模板 `=J=D` 判不一致 | 前端改按分相等（`templateAmountEquals.ts`），与模板同结论 |
| G1-2 | D 为 0 而旧行带期初公允价值时前端反推 D；N 为 0 而有单位公允价值时前端用市价推 N | 去掉替代，空即 0；旧行修复只留在 `migratePartial`（D 未定义时） |
| G11-2 | 序号契约是录入列，前端按位置重编；占比契约现读已是 auto_source | R3（对拍例外 1 条：seq 改 auto_source） |
| F3-4 | 应计利息前端按「面额 × 利率% × 天数 / 360」，模板 `ROUND(F*G,2)`（无天数）；字段名也不同 | 待用户确认口径；字段名随 R3 |
| F2-6 单价 | 数量为 0 时前端给空，模板 `IF(数量=0,0,…)` 给 0 | 前端改 0（只改 F2 明细表，共用引擎 `calcUnitPrice` 未动） |
| H4-2 单价 | 数量为 0 时前端给 null，模板 `=J/H` 是 #DIV/0! | 不改（两侧都不显示数） |
| D1-9 / D5-4 天数 | 日期倒挂时前端给 0，模板出负数 | 前端按模板出负数；日期没填完仍记 0（模板按序列号 0 算出几万天，不采纳） |
| D1-15 损失率 | 载入时截断到 0~1（OO 侧填 150% 会被表单改掉） | 载入不截断；表单录入时仍校验区间 |
| G14-2 转回 | 载入时把负数转回取绝对值（OO 侧填的负数被表单改正，J / K 两侧不同） | 载入不改号，与后端 `_g14` 校验同改；「填正数」是填报口径（真库 G14-2 无数据） |
| H2-2 期初调整 | 期初调整为 0 时按存库期初审定反推（OO 侧清掉调整、而期初审定是上一版公式缓存值时会把调整算回来） | 只对根本没有 `adjustBegin` 键的旧行反推（真库 H2-2 无数据） |
| D6-3 | 契约 B~D 错一列（B→category、C→priorUnadjusted、D→priorAje） | R3（对拍例外 2 条） |
| L8-2 | 合计把 13 行全加（利息费用总额 / 利息费用 / 利息净支出重复、「减：」行当加项）；R13 读未计算的 R11；派生行调整列恒 0；占比 ×100 且不落库（R 列 auto_source ⇒ OO 侧恒 0.00%） | 前端按模板：合计 = R13+R14−R15+R16+R20+R21、派生行月度与 O/P（R20 含 T/U/V）跨行算且只读、占比存比值并落库。对拍守卫只看数据首行公式，这条是按模板逐格读出来的 |

另：B60-1 预算成本列前端不算（模板独有）；E1-4 汇率空时前端按 1、字段名不同；N1-2 期末暂时性差异为 0 时前端按「计税基础 − 账面」回退、store item 不同——都在对拍未覆盖清单，随 R3 处理。L8-2 新增行插在 R21 之后，模板合计公式不含插入行（OnlyOffice 侧同样漏算），前端跟模板不计入并提示用户并入相应项目。

### §3.3 对拍守卫（R2.4）

- 生成器 `backend/scripts/gen/gen_template_formula_parity.py`（`--check` 幂等）：读契约 + 权威模板，对每个行表的 formula 字段取数据首行公式，换成「store 字段名表达式」写入 `audit-platform/frontend/src/components/workpaper/sync/__tests__/templateFormulaParity.generated.json`；引用了非受管格 / 他行 / 他表的公式标 `skip` 并写原因。非受管公式列同行展开，表头也空的间隔列按 0；只有 editable 列随机录入，auto_source / cross_sheet 单列 `auto_fields`。现算 481 个公式字段，换成表达式 373、跳过 108。后端守卫 `test_template_formula_parity_manifest.py`：入库清单 = 现算（等价 `--check`）、换算口径单测、改一格模板公式清单随之变。
- 前端 `templateFormulaParity.spec.ts` + `.eval.ts`（表达式求值）+ `.adapters.ts`（50 个 store item → 前端真实行计算函数；私有函数已导出或外提为纯函数，H1 / H5 / H9 / L7 / L8 / F5 的闭包外提）+ `.exceptions.ts`。每个 store item 用自己名字的哈希做种子造 24 行：一半样本给公式列塞旧值（前端必须重算）、比例字段固定样本取区间外、契约标成文本的日期列按字段名给日期。逐行核两件事：前端算出的公式字段 == 模板表达式在前端这一行上的值（按分，模板 #DIV/0! 时前端空 / 0 算一致）；前端不改写数值录入列。
- 例外登记只许减少、且每条必须仍在生效：未覆盖清单 25 个 store item、逐字段例外 5 条，全部是 R3（字段名 / store item / 列接错，任务 9 逐条删）。批 A1 后适配器 55 个、未覆盖 20 个（§4.1）。首轮 63 例 10 红：上表 G13 / G14 / G14 转回 / H2 / D1-15 / D1-9 / D5-4 七处改前端，其余进 R3 登记。
- 变异（任务 8.3）：改前端公式（L5 期末审定）、前端改写录入（D1-15 截断）、清单表达式（D2-2 期末余额）、加不生效例外、未覆盖清单登记已有适配器的 item、把 G13 核对 / G14 转回 / H2 反推 / D5-4 天数改回旧口径，9 条各自只打红对应用例，复原后 sha256 一致。
- 公式求值只支持行内四则、`SUM`（同行区间）、`IF` / `AND` / `OR` / `ROUND` / `ABS` / `MAX` / `MIN` / `IFERROR`；超出范围的标 `skip`，不猜。看不到的：跨行公式（小计 / 合计 / 派生行，如 L8-2）、数据首行以外与首行不同式的行、空日期（前端记 0、模板按序列号 0 算，属 UI 选择）。

## §4 字段名接通（R3）

- 现算口径：契约字段 json_pointer 末段，在前端「含该 store item 字面量的文件 + 直接 import 它们的文件」中不出现 ⇒ 疑似不通（594 个）；在整个前端源码都不出现 ⇒ 确定不通（198 个）。疑似项逐个人工核（动态拼键、`check${i}` 一类）。
- 确定不通的表：N1-2、N2-2、N3-2、N4-2、N5-2、L4-3、M1~M10（契约 store_item_id 写成 `placeholder`）、G5-2、G6-5、G7 少数股东、E1-2 / E1-4、F2-25 / F2-26 / F2-47 / F2-48 / F2-57、D 循环若干零散字段。真库这些 store item 只有 G6-5、G7、H1-8 有数据。另：N1 provider 几何写的是 `LAST_DATA_ROW=29` / `FOOTER_ROW=31`，模板数据行是 11~40（R40「……」）、合计在 R42；前端 N1 的 store item 是 `N1-2-detail`，契约是 `N1-2-rows`。
- 普查（§3.2）又发现一类：字段名前端有，但契约把模板列接到了**错的字段**（OO 改的值写进别的字段）。D6-3 B~D 错一列（B→`category`、C→`priorUnadjusted`、D→`priorAje`，`priorRje` 没接）；D7-4 契约把「期末主要债权人余额分析」区接到前端存「贷方发生额分析」的 `D7-4-credit-rows`，且期末 / 期初对调；F2-25 / F2-26 / F2-47 / F2-48 / F2-57 列名与模板表头整体错位；F4-1 账龄区契约 store item 是 `…-aging-seed-rows` / `…-slot-rows`（前端 `F4-1-adj-aging-rows`），性质区字段名 prior* / end*（前端 opening* / closing*）；F3-4、D3-rp、E1-2 / E1-4 字段名整体不同；L7-2 前端字段名本身标错了模板列义（如 `beginAje` 实为本期增加），契约照抄。
- 处置顺序：前端已有同义字段 ⇒ 改契约映射到前端字段名（改 provider spec + 重生成契约，不动前端、不迁数据）；前端没有 ⇒ 前端补该列（按模板列名与公式）；模板列确实不该受管 ⇒ 从契约移出并写理由；前端字段语义本身错（L7-2）⇒ 改前端标签与公式说明。每张表的裁定记入本节表格。守卫按「模板表头 ↔ 契约字段 ↔ 前端字段」三方对拍（任务 9.5）。
- 守卫 `test_contract_field_names_in_frontend.py`：上述现算口径固化为测试，例外表只许减少。
- 运行时是否真接通另看注册表：单 item 回写路径只镜像 provider 的 `STORE_ITEM_ID`，多 item 而没有 `dual_store_fn` 的契约其余 item 两个方向都没接（`check_store_item_two_way_parity.KNOWN_UNWIRED` 冻结，如 F2-25 区二、F2-26 日后表、F2-47、E1-4）。这类表改字段名只修契约声明，接通后才生效。

### §4.1 批 A1：F2 与回写串表（2026-10-27）

| 表 / 面 | 原状 | 处置 |
|---|---|---|
| F2-25 两区 | 照另一种版式写（A 盘点地点、H 盘点数量、I 盘点金额、J~L 差异、N 处理意见），与 R14 / R15 表头整体错位 | 字段键逐字取前端 `StocktakeSampleRow`（A 存货编码 … M 品质状况；J / K / L = I−F / I−H / H−F）；差异原因、备注只在 HTML 侧 |
| F2-26 两区 | 同上，且两区共用一份声明 | 日后表 H 发出、I 入库，日前表 H 入库、I 发出，分区声明；C「品名及规格」接 `itemName` |
| F2-48 | A 存货编号、E 数量、F 单位成本、H 库龄金额 … | A~N 按模板，库龄四档接 `aging/*`（I5 组表头），H 结存金额 = F × G |
| F2-57 | C 合同收入、D 合同成本、I 审定期初（模板 I 是「是 / 否」判断式） | A~L 按模板，五个公式列逐字记原式；备注只在 HTML 侧。前端 J 改为模板的分支式：原 `max(0, C − H) − D` 在已计提准备为负时与模板不同 |
| F2-47 | 前端双价、销售费用 / 税费可手改、应补提截 0，与模板不同构；回写未接通 | 不改，留未覆盖清单 |
| F2-48 / F2-57 的 store | dict（`{products}` / `{projects}`）却走 rows 回写分支：基线恒 `[]`、写回裸数组，外层键与非受管字段丢失，前端读到裸数组按旧版形态迁移、行身份重新生成 | 注册 `merge_state_fn`，provider 新增 state 门面只换行数组；出方向按名取行数组（原取「第一个列表值」）；`test_dict_store_rows_path` 由只断言常量改为两头实测（原表 F2-57 / F2-58 写的 `products` 实为 `projects`） |
| 回写串表（平台） | 框架引擎合并只按列名过滤，而单 item 回写路径交进整份契约的投影：d3 / d5 / e1 / f2 两家 / f3 / h3 / h7 八家，别表在 OO 里新增的行被建进本表 store；G9 / L5 逐段穿线时，区②/③ 的新增行在区① 那一趟建出、带区① 归属 | 引擎只合 `{table_key}/` 前缀的键；守卫 `test_store_merge_table_isolation.py`（全注册表逐表探针、引擎层、dict 合并）。D1 / D2 / D4 多 item 路径本就逐表切片，前后普查一致；D1 的切片留作纵深防御 |

- 复读重裁两条旧登记：aos8 多 item 场景「F3-5 新增行没长出来」原归因于中文业务名被值类型归一成 null，实测是别表同名 `note_type`（值为 null）在本表之后合并、把锚点覆盖掉（KEEP 行还被写进 F3-2 的 `ticketNo`）——修后新增行落库、KEEP 行带上 OO 改过的名称；D1「去掉切片必须膨胀」的变异反证改为「去掉切片也不串」。
- 留给批 B：G1 门面只取区① 的 spec（区②/③ 两个方向都没接）；G3 重导出的 store 门面绑死在 G9 的 spec 上（出方向投影恒空、回写按 G9 的列写）；G1 / G3 的载荷在 `conclusion`，镜像写的是 `remark`。

### §4.2 批 A2：E1 / D3-6 / D6-3 / D7-4 与后端复算口径（2026-10-27）

| 表 / 面 | 原状 | 处置 |
|---|---|---|
| E1-2 现金明细 | json 键 closingOriginal / closingRmb / adjustmentOriginal / closingAudited / remark，前端存 endingFc / endingRmb / adjustment / auditedRmb / note | 契约 json 键改前端名（列键不变）；载入行计算外提 `normalizeE1CashDetailRow` 供对拍 |
| E1-4 数字货币 | json 键 *Original / *Local；A 序号当录入（前端按位置编号）；M~Q 未受管（docstring 称模板无表头，实测 R9 有）；前端载入 `parseNum(fxRate) \|\| 1` 把录入的 0 汇率改成 1 | json 键改前端名；序号改 auto_source（幽灵行锚点改 B 开户银行）；补管 M 查询余额 / N 差异 = M − K / O、P 索引号 / Q 备注；行计算外提 `e1/e1DigitalRowCalc.ts`，只在汇率缺省时按 1 |
| D3-6 关联方 | json 键 relatedPartyName / openingBalance / debitAmount … 整表不通 | 改为前端 partyName / priorBalance / debit / credit / endBalance …（F = C + E − D） |
| D6-3 减值准备 | 只受管单项区；B 接 category、C / D 错一列、priorRje 没接；组合区的行全投影进单项区 | 双区（单项 R13-16 / 组合 R18-21，共用 `D6-3-rows`，`row_section_field=category`，各用 O / P 列），B / C / D 接期初未审 / 账项调整 / 重分类调整；对拍例外 2 条删除 |
| D7-4 分析表 | 区② 接「期末主要债权人余额分析」R27-36（期末 / 期初对调），而前端 `D7-4-credit-rows` 存的是「贷方发生额分析」 | 区② 改接 R21-22（A 项目 / B 金额 / C 数据来源 / D 与对方科目核对 / E 说明，footer R24「差异合理性分析」无公式）；前端补 `counterCheck`，表单借方区补显示「备注」、贷方区补「与对方科目核对」「说明」；导入导出带上新列（旧文件缺该列照常导入、字段留空）。债权人区由前端按 D7-2 现算、不落库 ⇒ 不受管（同 D3-4 段③） |
| 后端复算（R2 同族，触类旁通） | D6-2 / D6-3 / D7-2 导入复算派生列、D1 附注推送（`tier_a._d1_note_rows_from_entries`，docstring 自称与前端同口径）仍从期初审定起算，有期初调整时与前端 / 模板差一个期初调整额；导入写库的 endUnadjusted 还被预填锚点直接读 | 改为期初未审起算；守卫 `test_period_end_from_prior_unadjusted_backend.py`（每例带非零期初调整）；三个旧判据钉的是旧口径，改写并注明。全仓普查后端其余 `prior_audited ±` 写法只剩注释与变动率 |

- 对拍：适配器 +3（E1-2 / E1-4 / D3-rp），未覆盖 20 → 16（含 D7-4 贷方区已无公式），逐字段例外 5 → 3。
- 新发现、未改（并入任务 9.5；批 A2c 已修，见 §4.3）：D3-4 贷方区与 D7-4 同版式（R20 金额 / 数据来源 / 与对方科目核对 / 说明），契约 D 列仍接 `remark`、E 列未管；D3-4 前端行身份是 `rowKey`，契约声明 `rowId`（接通后整表 fail-closed）。行身份键属字段名对拍的一部分，由 9.5 守卫一并纳入。
- D1 契约 `reviewed_basis` 仍写「前端 recalcRow 用 priorAudited+inc-dec，数值语义等价」：前端早已按模板改、两式也不等价。只是冻结的说明文字，改它会让已发布 D1 产物与契约脱钩，不改，记此备查。
- E1-4 / D3-6 / D6-3 / D7-4 所在 provider 仍在 `KNOWN_UNWIRED`（出 / 回两方向只镜像主 store item），D6 / D7 扩容面也还不在已发布 instrumentation 里：契约改对后要接通才生效。

### §4.3 批 A2c：D3-4 / F3-4 / F4-1 性质区与 F3-1、F4-1 账龄区字段名（2026-10-27）

| 表 / 面 | 原状 | 处置 |
|---|---|---|
| D3-4 分析表（两区） | 行身份键写 `rowId`（照抄 D3-6），前端与导入只写 `rowKey` ⇒ 一接通每行都按「缺少稳定行身份」拒收；区② 共用区① R10 的四列，D「与对方科目核对」接成备注、E「说明」没管 | 两区身份键 `rowKey`；区② 表头取 R20，D 接 `counterCheck`、E 接 `remark`（受管区 A22:E23）；表单贷方区补显示「与对方科目核对」「说明」；导入导出带新列（旧文件缺该列照常导入，同 D7-4） |
| F3-4 利息测算表 | json 键 noteNumber / maturityDate / term / faceAmount / accruedInterest / diff / remark 整表不通；C / D 日期按文本、E 期限当录入、G 利率按金额 | 改前端 ticketNo / dueDate / termDays / faceValue / payableInterest / variance / note；C / D 改 date（同册 F3-5），E 改 auto_source（前端按到期日 − 出票日现算、载入即覆盖存值），G 改 percent_points（模板 `0.00%`，物化 ÷100） |
| F4-1 性质区 | prior* / end* / reason，K 变动率按金额 | opening* / closing* / reasonAnalysis，K 改 ratio |
| F3-1 两区、F4-1 账龄两区 | json 键 prior* / end* / category / reason | json 键同上改前端名（项目列接 `label`）；store item 仍是前端没有的 `…-seed-rows` / `…-slot-rows`（前端两区共存一个 item：`F3-1-adj-rows` / `F4-1-adj-aging-rows`），要区判据 + 多区门面（同 G1 / G3），留批 B |
| 对拍生成器 | percent_points 列不算数值录入（落进文本录入）、公式里按原值代入 | 百分点列算数值录入；公式引用它时 ÷100 换回小数（F2-47 的 N / O 两列同受益）；百分点公式字段跳过（现无） |

- 对拍：适配器 +2（F3-4、F4-1 性质区），未覆盖 16 → 14；例外 3 → 4，新增一条不是接错列，是字段接通后才看得见、待用户裁决的计息口径：模板 F3-4 H = ROUND(F*G,2)（不含天数），前端有出票日 / 到期日时按 票面金额 × 利率% × 期限 / 360，没有日期时两侧一致。H 是公式列、不回写，裁决前两侧各按自己的口径显示。
- F3-1 前端行模型与模板不同构（R2）：模板首区（银行承兑 / 商业承兑 / 信用证 / 供应链）期初未审与期末三列全是 F3-2 的 SUMPRODUCT，前端期初未审可录（并从试算表带出）、期末账项 / 重分类调整在本表录入、另存本期借贷。并入批 B 一起裁。
- F3 只注册 `F3-5-rows`、F4 只注册 `F4-6-rows`（`KNOWN_UNWIRED`），本批改的是契约声明，接通后才生效（同 §4.2 末条）。

### §4.4 字段名对拍守卫（任务 9.5，2026-10-28）

- 守卫 `tests/workpaper_sync/test_contract_field_names_in_frontend.py`，现算在伴生模块 `contract_field_names_scan.py`。字段名 = 契约字段 json_pointer 行内路径各段 + 行表的行身份键；前端语料 = 生产代码（不含测试），按标识符记号比对。两类对不上：① 前端全无；② 前端有，但不在处理该 store item 的代码里（含该键的文件、它们直接 import 与被 import 的文件、对拍适配器给该 item 调用的模块、手工登记的入口 `EXTRA_SCOPE`）。
- 与 §4 开头的旧口径（确定 198 / 疑似 594）不可直接比：旧口径按字段数、范围只算「含字面量的文件 + 直接 import 它们的文件」，键动态拼接（`` `${ITEM_PREFIX}-entries` ``、逐格键 `D2-adj-…`）的都算疑似。新口径认同文件常量拼出的键、逐格存储只核键本身，误报的几类（K 循环调整分录、D4 IPO 四张、逐格键）由此消掉。
- 现算（9.4c 之后）50 组、473 个字段名，逐组写理由登记在 `data/contract_field_names_frontend_exceptions.json`，只许减少：现算对不上又没登记、登记了却已接通，都报红；组数 / 字段名数等于基线。理由里「待核」的组是字段另名或缺列、尚未逐列核对的（D1 / D3 / D7 抽查表、D2 检查表、D3 长期挂账、F4-2、G4-7），由批 B 起逐组处理。
- 新发现（登记在册，未改）：D1-8 背书区前端沿用贴现行字段、缺模板 K / L 两列；D7-7 前端核对内容存为 5 项布尔数组 `checkItems`（模板 7 项）、支持文件键 `supportDocs`；K2 / K3 / K4 / K5 / K6 / K7 调整分录前端缺 类别 / 报表项目 / 附注项目 / 索引列（K11 已有）；G4-9 / G6-11 三阶段转置表与 B60-1 表头、G3-1 部分列契约未声明 store item。
- 变异 5 条各自只打红对应用例、逐字节复原：契约把已接通表的字段改名、前端把已接通字段改名、登记了的名字在前端出现、去掉手工入口、去掉常量拼键识别。

### §4.5 批 B1：D3 长期挂账 / F4-2 / G4-7 / G6-5 / G11-2 / H4-2（2026-10-28）

| 表 / 面 | 原状 | 处置 |
|---|---|---|
| D3 长期挂账 | json 键 counterpartyName / endingBalance / businessReason / unsettledReason / settledByAuditDate 前端全无 | 改前端与导入导出同名 customerName / endBalance / businessDescription / reason / settlementAmount |
| F4-2 明细表 | 借贷发生、被审单位重分类、期末账项 / 重分类、期后付款 6 列与未审账龄组前缀另名；模块头「前端已对齐」只核了公式口径 | 改 currentDebit / currentCredit / entityReclassification / closingAje / closingRje / subsequentPayment，账龄组前缀 agingUnadjusted → agingCurrent（与导入导出同） |
| G4-7 有价证券盘点 | B 写 securityName（前端 securitiesName）；E 总计模板无公式、前端按 面值 × 数量 现算 | B 改 securitiesName；E 改 auto_source |
| G6-5 公允价值 | 15 个键前端全无；D 未审公允价值前端恒按 数量 × 单价 现算 | 全表改前端 `FairValueItem` 名，D 改 auto_source；前端旧数据反推单价 / 数量改为只在键缺失时做（原按「为 0」判，OO 侧录的 0 单价会被 HTML 用上次的公允价值反推改回，两侧来回变） |
| G11-2 投资收益明细 | A 序号 editable，前端载入与重算都按位置重编（OO 改的序号回流后下次载入即被覆盖）；对拍例外登记 | A 改 auto_source，幽灵行锚点改 B；删例外 |
| H4-2 工程物资 | J 增加金额 / M 减少金额模板是录入格，前端由子项推出（子项模板没有）；对拍例外两条 | J / M 改 auto_source；删两条例外 |

- 对拍：适配器 +1（G6-5），未覆盖 14 → 13；例外 4 → 1（剩 F3-4 计息口径）。字段名守卫：4 组 28 个名字接通、删登记，50 组 / 473 → 46 / 445。
- 新守卫 `test_ghost_row_anchor_not_protected.py`：回写合并跳过受保护字段，幽灵行防护对新增行判「锚点空 ⇒ 剔除」⇒ 锚点若受保护，OO 侧新增的行全部丢弃、零报错（G11-2 序号改 auto_source 时锚点仍是 A，变异实测即此）。全仓现扫 186 个 `RowTableSheetSpec`，锚点不得越界、不得受保护，导入失败判红。例外 1 条：F3-1 种子区（R7-R8 固定两行，A 类别是 SUMPRODUCT 匹配键、不受管，B 是公式；新增行走空槽区），登记可伪证：锚点列与 mode、标签列不受管、同 sheet 扩展区的锚点与标签列可编辑，任一不成立即红。
- 仍未接通（契约改对、接通后才生效）：D3 长期挂账、F4-2、G4-7、G6-5 都在 `KNOWN_UNWIRED`；G6-5 另有两处：前端 store 是 `{rows, conclusion}` 对象、存 conclusion 列（契约按行数组声明），provider 的 store 门面借自 G9（`specs_for` 只取 G9 的 spec）。留批 B3。
- 变异 5 条各自打红、逐字节复原：G6-5 反推退回「为 0」（显式 0 单测）、G11-2 序号退回 editable（同构测试 + 对拍）、H4-2 J 退回 editable（对拍）、G11-2 锚点退回 A（锚点守卫 + 同构测试）、F4-2 借方发生退回旧键（字段名守卫）；改契约的三条同时打红 golden 摘要门。
- 同口径子集（57 个文件）对 30849124c：由过转红 1 条，`test_g11_column_isomorphism` 钉着「A 序号 editable」，改为钉 auto_source + 锚点 B + 前端按位置重编的两处源码；由红转过 12 条是 G6 的 AI 端点 503：基线所在的检出没有仓库根 `.env`（AI 服务未配置），提交树在同一检出上同样 12 条 503，非本批。提交树（a39c94827 + 本批）同口径对基线：由过转红 0。

### §4.6 批 B2a：D 循环检查表 / 关联方表与行表引擎值换算（2026-10-28）

| 表 / 面 | 原状 | 处置 |
|---|---|---|
| D7-7 检查表（两区） | 契约整表错位：声明 A..R（F 借方 / G 贷方 / H 支持性文件 / I..O 七个检查 / P 索引 / Q 异常 / R 备注），模板 A..Q（F 对方明细科目、G/H 借贷、I 支持性文件、J..N 核对内容 1~5、O 索引号、P 是否异常、Q 备注说明）；区② 照抄区①，模板区② 只有 G「借方金额」、H:I 支持性文件；单级表头让叶子表头行落进数据区 | 两区按模板重排（两级表头 R16/R17、R33/R34），json 键改前端（counterDetail / supportDocs / checkItems/0..4 / indexRef / isAbnormal）。前端期后结转区按模板由贷方改借方：旧行载入即迁移，D7-2 期后结转与交叉核对经 `postTransferAmount` 兼容没重新保存过的旧行；表单补对方明细科目 / 支持性文件 / 核对内容 1~5 / 索引号 / 备注说明（拆出 `D7VoucherCheckTable`）；导入导出期后区改「借方金额」，旧文件按「贷方金额」列读 |
| D6-6 检查表区② | 「为简化按区①同列声明」：G 接 debitAmount（区② 行没有这个键，恒空）、H 接 creditAmount（贷方金额写进支持性文件列） | G 贷方、H 支持性文件（H:I 合并）；两区改两级表头，表头文字取模板 |
| D6-5 关联方表 | 照另一种关联方表写了 14 列（J 未结转原因 / K 至审计日结转金额 / L 处理计划 / M 索引号 / N 备注），模板 12 列，I..L = 发生时间及账龄 / 发生原因（款项性质）/ 索引号 / 备注 | 按模板 12 列；前端补 `transactionReason`（表单、导入导出，旧文件缺列照常导入）；「未结转原因 / 至审计日结转金额 / 处理计划」三列模板没有，留在 HTML 侧、不进 OO |
| D3-7 检查表（两区） | json 键 voucherDate / counterSubAccount / check1..5 / indexNo，前端存 date / counterDetailAccount / checkItems[0..4] / indexRef | 改前端键，核对内容按布尔数组接 |
| 行表引擎 | ① percent_points 回写判 `str(vtype) == "percent_points"`，`FieldValue.value_type` 是枚举、str() 得「ValueType.percent_points」⇒ ×100 从未生效（F3-4 票面利率、F2-47 费率回写成 0.035，前端按 3.5 读）；② 数组元素路径在 OO 侧新增行上 fail closed（行里还没有数组）；③ 勾选列未勾在 OO 里写成 FALSE | 换算与建数组拆到 `phase5_row_value_codec`（引擎文件逼近 800 行）：比较取枚举值；`row_array_defaults` 声明缺省数组；`boolean_unchecked_as_blank` 让未勾留空、回写空格 → False |

- 新守卫：`test_check_table_headers_match_template.py`（D1-13 / D3-7 / D6-5 / D6-6 / D7-7 九个区逐格对模板叶子表头、组标题合并区、首数据行与 footer，判据自检两条）；`test_phase5_row_value_codec.py`（真 `FieldValue`，不用字符串冒充枚举）；`test_d6_d7_check_tables_import_export.py`；`dCheckTablesTemplateColumns.spec.ts`。
- 字段名登记 46 组 / 445 → 42 / 415。D1-13 区② 改登记为 R2 待裁：模板区② 是「期后贴现\背书\调整等检查」凭证表（16 列，同区①），前端 `D1-sampling-specific-samples` 是「特定样本」清单（项目描述 / 金额 / 原因），不是同一张表，前端没有期后检查表。守卫只报出 4 个名字，是因为其余列名在同一文件区① 的行模型里出现 —— 按标识符记号比对的盲区（D3-7 的 `voucherDate` 同因漏报，`SampledVoucherLike` 里有这个名字）。
- 全量表头普查（91 份契约 3750 个字段，1205 个与表头格不逐字相等）多数是组合标签、编号叶子、多级表头重复标签，做不成通用门；本批只把检查表与关联方表钉成逐格判据。
- 待用户确认：D3-7 区② 模板写「贷方金额」，预收账款期后结转按理是借方（同结构的 D7-7 合同负债写的是借方）。本批没改 D3。
- D3 / D6 / D7 这几张都还在 `KNOWN_UNWIRED`（扩容面未进已发布 instrumentation），契约改对后接通才生效，不需要重发布。

### §4.7 批 B2b：D2 检查工作簿四张表与 D1-8 背书表（2026-10-28）

| 表 | 原状 | 处置 |
|---|---|---|
| D2-6 关联方表 | J「发生原因（款项性质）」接 `transactionReason`（前端没有）；L「索引号」接 `remark`（前端「备注」⇒ 备注写进索引号列）；I 发生时间及账龄 / K 期后回款前端缺列；前端「交易类型」与 J 是同一概念 | J 改接 `transactionType`（表单改名「发生原因（款项性质）」）、L 改接新增的 `indexRef`；前端补 `agingPeriod` / `postPayment` / `indexRef`，列序按模板。「从 D2-2 导入」原直接写期末、借贷留 0，随即被行公式改回期初（导入的期末从未生效）⇒ 借贷取 D2-2 本期发生、期末按模板 F = C + D − E 算 |
| D2-11 转回 / 核销 | 转回区 G「合理性分析」接 `reasonableness`（前端没有）；F 的 header_text 与模板不符；前端缺 收回方式 / 原确定坏账准备的依据 / 累计已计提 / 应收账款性质 / 是否由关联交易产生 五列，也不显示索引号 | G 两区同接 `auditorComment`（表单改名「合理性分析」，原「合理性」下拉改名「合理性判断」、留在 HTML 侧）；前端补五列与索引号，列序按模板；转回区加累计已计提合计（模板 F16）；D2 附注「从 D2-11 带入」随之带上这几列（原注释写「无数据源需手工」） |
| D2-12 质押区 | B「期末余额」与 C「质押金额」同接 `pledgeAmount`：HTML → OO 期末余额恒等于质押金额，OO 两格改得不一样时回写互相覆盖；前端缺 期末余额 / 质押条件 / 质押协议 | B 改接新增的 `endBalance`；前端补三列、列序按模板，汇总加期末余额合计（模板 B19） |
| D2-13 分组表 | 前端缺 具体依据 / 索引号 | 前端补 `basis` / `indexRef`，列序按模板 |
| D1-8 背书表 | 契约按模板声明 F 前手 / K 背书转让单位 / L 背书转让日期 / M 说明，前端背书表沿用贴现表 16 列（已计利息 / 贴现银行 / 贴现金额 / 贴现息），两个方向都不通；导入导出 D1-8T 也共用贴现表列 | 前端补四个字段，背书表列按模板（`ENDORSE_COLS`）；从备查簿导入映射 前手 / 被背书人 / 流转日，不再把贴现字段带进背书行；D1-8T 导入导出按模板列（新模块 `_d1_8t_endorse.py`），旧文件缺新四列照常导入、旧列读进原键不丢 |

- 导入导出：D2 四张表新列进 `SHEET_COLUMNS`（导入只拒未知列 ⇒ 旧文件照常导入）；D2-11「原累计已计提」原导出恒空、导入不读，现接 `cumulativeProvision`。
- 新守卫：`test_check_table_headers_match_template.py` 补 D1-8 两区与 D2 五个区（自写 provider、单级表头；判据自检一条）；`test_contract_no_duplicate_field_binding.py`（同一张表两个字段不得绑同一个 store 键，全仓 458 张表现算只有 D2-12 这一处）；`test_d1_d2_inspection_import_export_columns.py`；`d1d2InspectionTemplateColumns.spec.ts`（表单列序前段 = 模板列序；契约每个字段绑的键，表单里那一列的标签就是模板表头 —— 字段名对拍只看键有没有，L 接 remark、B 接 pledgeAmount 这种查不出来）。
- 字段名登记 42 / 415 → 36 / 404（D2 五组、D1-8 背书一组接通）。14 条磁盘变异各自打红、逐字节复原。
- 两份历史大文件登记白名单（HEAD 已超限且此前未登记，改一行即被门禁拒）：`_d1_import_export/_impl.py`（3643）、`useD2DisclosureNote.ts`（1752），基线取 HEAD 值，写了拆分方向。
- 范围外（未改）：D2 导入导出把「序号」列当索引号读、空则补行号（D2-4 / D2-7 / D2-9 / D2-11 / D2-12 五处），列名也与表单对不上（D2-11「合理性分析」列装的是合理性判断、「备注」列装的是合理性分析）—— 这套导入导出本就不是模板格式，改列义会让旧文件读错，另立任务；D2-12 模板（二）出售区未受管，前端对应的是保理表（结构不同，R2 同类）。
- 真实项目：和平药房 2025 已发布 `xlsx/gt-d2-inspection`（1 代，2026-10-12）。本批改了该契约 5 个字段，契约 digest 变了，已发布的表示在线编辑会报「冻结身份与生产契约脱钩」，要重发布才按新契约走；只做测试项目，未重发布（列入重发布清单）。

### §4.8 批 B2c：K3 ~ K7 调整分录汇总（2026-10-28）

模板十列六册逐字相同：A 调整事项说明 / B 类别（报表调整/账项调整/其他）/ C 报表项目 / D 科目名称 / E 附注项目 / F ……（空占位）/ G 借方调整金额 / H 贷方调整金额 / I 索引 / J 备注，契约逐列声明了。

| 表 | 原状 | 处置 |
|---|---|---|
| K3-3 / K4-3 / K6-3 | 前端分录行缺 类别 / 报表项目 / 附注项目 / 索引，载入只挑已知字段 ⇒ OO 侧填的这几列回到表单、下一次保存就被擦掉 | 前端补四列（`kAdjTemplateFields.ts`），载入展开 `...e` 保留未知键；列序 序号 / 编号之后前段按模板，类型 / 科目代码 / 编制人 / 对方科目 / 来源（模板没有）排在表尾 |
| K5-3 | 同上缺 类别 / 报表项目 / 附注项目 / 备注；契约 G / H 接 `debitAmount` / `creditAmount`，前端存 `debit` / `credit`（借贷两列两个方向都不通）；合计行按位置 idx 4 / 5，落在「摘要」「借方」两列下 | 契约 G / H 改接 `debit` / `credit`（六册里唯一不叫 debitAmount 的，导入导出契约与集中登记早已用这两个键）；前端补四列；合计按列 prop 认 |
| K6-3 | 合计行按 prop 或位置 idx 5 / 6 认，金额列原没写 prop（实际靠位置），列序改后会落到别的列上 | 金额列补 prop，只按 prop 认 |
| K7-3 | 前端「类别」列放的是 AJE / RJE 类型（模板的类别是 报表调整 / 账项调整 / 其他），只缺 `category` | 「类别」列改显示 `category`，另起「类型」列放表尾；金额列名按模板改「借方调整金额 / 贷方调整金额」 |
| K2-3 | 前端分录行「借方科目 / 贷方科目」分列（一行两科目，K2-5 / K2-6 推送的建议分录也按此格式），模板一行一个科目 | R2 待裁（改单科目行要迁移已存分录、改推送格式），字段名登记理由改写；载入先展开 `...e`，OO 侧填的模板列至少不在下一次保存被擦掉 |

- 类别 ≠ 类型：类型（AJE / RJE）决定回写审定表的 AJE / RJE 合计与集中登记，类别是模板分类。新行按类型给缺省（重分类只调报表 = 报表调整，审计调整调账 = 账项调整；G12 / G14 已用同一映射），旧行缺键同；空串 = 用户清空，照留；改类型时类别仍是旧缺省才跟着换，用户改过的不动。否决：类别经值编码映射到 entryType（「其他」无处可去，有损）。
- 导入导出：K3 ~ K7 调整分录补 类别 / 报表项目 / 附注项目 / 索引（K5 补备注，K7 只补类别），登记为 Sheet_Spec 的 `optional_headers`：旧版导出文件缺这几列照常导入，缺的列不写键（写成空串会盖掉前端按缺键给的缺省）；其余列缺一列照旧拒收。否决 `allow_missing_headers`（任何列都能缺，太松）。共用工厂 `_cycle_import_export_common.py`（HEAD 925 行、此前未登记）登记白名单并写拆分方向。导入导出契约清单 `adjustment_ie_contract.json` 五张的 field_keys / frontend_row_model 随改。
- 生成器：`generate_phase5_k_contracts.py` 原只登记 K1 / K3 / K6 / K8 ~ K13，K2 / K4 / K5 / K7 改了 provider 磁盘契约没法重算，补登。全仓原先没有测试或 CI 跑任何 `generate_phase5_*` 的校验模式（38 个现算全 OK）⇒ 新守卫 `test_phase5_contract_generators_check.py`：逐个跑校验并看输出（只看退出码会被空跑骗过）、K 生成器登记全部 K provider、校验真会拒绝漂移。
- 新守卫：`test_k_adjustment_template_columns.py`（导入导出列 ⊇ OO 契约受管键、后加列 = optional_headers、旧版文件缺列照常导入且不写键、原有列缺一列照旧拒收）；`kAdjTemplateColumns.spec.ts`（五张表列序前段 = 模板、契约列 ↔ 表单列标签逐列一致、载入保留未知键 / 类别缺省 / 改类型跟随 / 新行带四列、K5 / K6 合计落在借贷两列下、K2 载入不丢模板列）。
- 字段名登记 36 / 404 → 31 / 388（K3 ~ K7 五组接通）。按标识符记号比对的盲区又一例：K2 / K4 / K5 的「附注项目」守卫没报，是因为载入函数里有同名局部变量 `noteItem`（审计说明那一项）。
- 18 条磁盘变异各自打红、逐字节复原（列序、键绑定、载入展开、类别缺省与跟随、两处合计、K5 契约键、导入导出缺列两条与漏登两条、IE 契约清单、生成器三条）。
- 顺带（R9 一条）：`test_adjustment_ie_characterization` 的 export-summary 列头断言过期 —— 07-27 调整分录集中登记（f3354f539）起导出末尾加了「所属循环」「协作状态」两列只读信息，中央导入按列头取值不受影响；改钉当前 10 列，HEAD 同红。
- 真实项目：和平药房 2025 已发布 `xlsx/gt-k5-provisions`（1 代，10-07），本批改了该契约 G / H 两个字段，要重发布；K2 / K3 / K4 / K6 / K7 契约没变（前端补列后两侧自然接通）。只做测试项目，未重发布（列入重发布清单）。

### §4.9 批 B3a：G1 / G3 / G4 / G5 / G6 多区 store 门面与载荷列（2026-10-28）

原状四处叠加，这五张表两个方向都不通（出方向空、回写合不进或写进前端不读的列）：

| 缺陷 | 原状 | 处置 |
|---|---|---|
| 门面借别家 | G3 / G4 / G5 / G6 原样重导出 G9 的门面（`_provider()` 写死 G9）⇒ 投影 / 合并用 G9 的 spec：G3 行没有 G9 的 `section` ⇒ 出方向恒空，回写按 G9 的表键一格都合不进，带 store item 调用直接抛「不在 G9 受管清单里」。G1 自己的门面按 store item 取**第一条** spec ⇒ 三区只通区① | 新模块 `phase5_section_store_facade.SectionStoreFacade(provider_module, rows_key)`：spec / 错误类型 / STORE_ITEM_ID 从绑定的 provider 现取，投影 / 合并逐区穿线（上一区的合并结果喂下一区）；六家各自绑定，`phase5_g9_store_facade` 只剩 G9 的绑定（G9 golden digest 不变） |
| 载荷列 | 回写镜像 / 出方向投影 / 采纳覆盖一律读写 `remark`；G1-2 / G3-2 / G6-5 前端只写 `conclusion`，G4-7 / G5-2 两列同写、读 conclusion 优先 | 新模块 `store_payload_columns`：按 provider `PAYLOAD_COLUMN` / `PAYLOAD_COLUMN_MODE` 推口径（conclusion / 两列同写读 conclusion 优先 / 其余 remark），remark 口径 SQL 与原调用点逐字相同；接到单 item 回写、多 item 行数组循环、出方向读取、采纳覆盖的两次快照 / 删除侧 / 回滚审计（非 remark 口径记 `rollback_snapshot_columns`，恢复时知道写回哪一列） |
| 单数 store item 与外壳 | G4 / G6 的 STORE_ITEM_ID 照抄成 G4-2-rows / G6-2-rows；G6-5 前端存 `{rows, conclusion}` 对象 | 改为受管的 G4-7-items / G6-5-fair-value-data；G6 门面 `rows_key="rows"`（投影取 rows、回写只换 rows 其余键原样），注册表 `merge_state_fn` + `kind=dict`；`iter_store_rows` 不拆外壳（采纳覆盖按行数组枚举，对象载荷照旧 fail visible，不会把外壳写丢）。`KNOWN_UNWIRED` 15 → 13 |
| G1 A 列 | 模板 A 列「类别」数据行预填「债务工具投资」一类（投资品种），契约绑的是区归属 `acctClass` ⇒ 区②③ 接通后，OO 侧在 A 列填文字（含新增行）回写就把行改到三区之外（三区都投不出它，前端按未知分类单独成组） | A 列改绑 `investType`（与 G2 / G4 / G6 的 A 列「投资种类」同口径），`acctClass` 不受管：已有行不被改，OO 侧新增行由引擎补所在区的值。新守卫：区归属字段不得是受管列（全仓现算只 G1 一处） |

- 契约声明：G4 `PAYLOAD_COLUMN_MODE` remark_only → dual_write（`useG4SppiInventory` 两列同写、读 conclusion 优先）、G6 `PAYLOAD_COLUMN` remark → conclusion（原「真库 remark 605 B」是照抄 G9 的）；五家 `ROW_IDENTITY_STORE_KEY` 原照抄 G9 写成 "rowId"，改为与 spec / 前端一致的 "id"；`_HTML_STORE_NOTE` / `payload_column_source` / `_REVIEWED_BASIS` 原是从 G9 整段抄来的，按各自实际改写；html_store 的 `row_section_field` 由 `section_specs()` 现算。
- golden digest：五家的基线原来都是**空投影**的 digest（G1 区字段受管被合成占位值盖掉 ⇒ 三区都过滤空；G3 ~ G6 按 G9 的 spec 投影）。门禁加一条：合成 payload 投影为空即判 skip ⇒ 打红；基线只更新这五家（instrumentation 不变）。
- AOS（采纳覆盖）：`_facade_module_name` 认绑定式门面绑定的 provider（`__module__` 恒为实现模块）；原先钉住「门面借给 G9」「G1 只覆盖 1/3」的断言改成正面断言（① 级可枚举、两路对账 `ReconcilingRowReader`），判据本身用合成门面守住（G3 外壳 + 绑 G9 的门面、只 yield 区① 的门面）；OO 路径门面体 sha 基线按 J2 规定登记新旧两值（旧 `41acda28…` / 112 行 → 新 `bb42107a…` / 101 行，只改了三条 SQL 的列口径，条件② 零命中）。同文件里 G5「12 段」的两处期望 2026-10-08 起就过期（G5 只受管主区 s1r1），改为现读。
- 多 item 回写里 D4 的专用块 / dedicated dict store 仍写死 remark：守卫钉住走到它们的 provider 只能是 remark 口径（现算 d1 / d2 / d4）。
- 变异 20 条各自打红、逐字节复原（门面借别家 / 只取首区 / 不穿线 / 外壳丢键 / 迭代拆外壳 / 口径恒 remark / 两列同写读序与写列 / 回写与出方向不认声明 / 采纳覆盖三处 / 基线回填 / 单数 store item / G1 A 列 / golden 空投影 / AOS 不认绑定 / G6 外壳 / 前端列序）。
- 顺带（R9）：`test_check_store_item_two_way_parity::test_baseline_is_exactly_thirteen…` 因 8edf1d45a 加 F2/F4 后基线 15 条一直红（登记在预存失败清册），G4 / G6 接通后回到 13，清册删该条。未修：AOS 跳过清单棘轮（现算 92 > 62，absent 37 / item_blind 55 来自别 lane 新增 adapter）与白名单分母棘轮、golden 分派判据（清册已登记），HEAD 同红。
- 待裁：G1 A 列在 OO 侧显示投资品种代码（bond / stock …，前端下拉存代码），与 G2 / G4 / G6 同；要显示中文类别需值编码换算，未做。
- 回归（对 dbd010b28）：后端 528 个文件新增失败只有「已提交代码 import 未提交模块」（两个新模块入库即消），另 10 条由红转绿；PG 11 个文件新增 0；前端 244 个文件新增 1 条 `useG5FormulaEngine.pbt` P15 —— 6 个 1e9 量级正数正反序求和、按 1e-6 比较，浮点尾差超容差；失败种子 -1895920294 在 base 上复跑同样红，与本批无关（R9 登记）；vue-tsc 单区域（useG1Detail.ts）无新增。
- 真实项目：和平药房 2025 的 G1 / G3 / G4 主表 / G6 主表与重药安徽的 G5 已发布，五份契约都变了（列口径、复核文字、G1 A 列键），在线编辑会报「冻结身份与生产契约脱钩」，要重发布；只做测试项目，未重发布（列入重发布清单）。

### §4.10 批 C 与复盘收口：N 循环 store 契约、N2 A:Q、N1 对拍（2026-10-28~29）

批 C（v1.0.31）先完成 N1 几何 29/31→40/42、N1/N2 store item 改 `-detail-rows`、N1/N2/N3 json key 改前端名、五条 N plan 登记和五份契约生成。复盘重新按**运行时调用链**而非声明检查，发现三处假绿并在本批收口：

1. **载荷列声明未生效**：`PAYLOAD_COLUMN=conclusion` 只加在 `phase5_n{1,2,3}_sheets.py`，三个 provider 的显式 import 列表没有重导出；`payload_columns_of(provider)` 因而仍走默认 remark。现将两常量从三份 provider 重导出，运行时逐条实测 read_order 都是 conclusion。
2. **N1 对拍空窗**：N1 已从 `UNCOVERED_ITEMS` 删除，但 `templateFormulaParity.generated.json` 没重生成、`PARITY_ADAPTERS` 也没有 N1，守卫在旧清单上仍绿。现把 N1 行计算抽成生产纯函数 `enrichN1DetailRow`，生成清单改为 `N1-2-detail-rows`，加真实适配器；模板四公式与前端逐样本对拍。
3. **N2 活路径仍是旧模型**：前端实际调用长前缀 `/api/n2-taxes-payable/*`，其 service 仍导入导出旧 23 列、动态拼出双前缀 `N2-N2-2-rows` 并写 remark；批 C 只改了未挂载的短前缀工厂。新增 `n2_detail_model.py` 作后端单一来源，N2-2 统一为 `N2-2-detail-rows.conclusion`、A:Q 17 列；导入补 `project_id`，只存可编辑列，导出重算 F/M/N/O/P。前端补模板 H 列 `beginRje`，M 改 C+G+H，跨表勾稽和 AI 复核上下文均按原始行实时算 P，不读不存在的 `endBalance`。导入 `sheet` 改走 query 参数（原放 multipart body，FastAPI Query 收不到）。真库两个键现查均 0 行，无迁移。

其余收口：

- `store_item_registry.py` 的 K2~K7 与 N1~N5 十一条同构单 rows plan 改 `_row_plans` 表驱动；运行时 dataclass 序列化与改前逐值相等，76 条顺序不变，1019 行（从 1047 降 28，低于白名单上限）。
- N5 第四批修 3 格，见 §2 #33；用户已授权「模板错按正确口径」，否决继续增加“已知缺陷仍存在”守卫。模板哈希、N5 契约、快照、prev3 与 N slice 同步。
- field-name 例外 30/365→29/364（N2 `beginRje` 清零）；公式对拍未覆盖仍保留 N2 一条，理由改为模板 B 列自由文本与前端数值 taxRate 的 R2 待裁。
- 新增 N1 三条语义靶子；在 `wsr_head` 磁盘变异 store item / payload column / LAST_DATA_ROW，3/3 由目标断言打红、无 collection error，每轮及最终 sha256 恢复。
- `push_version.py` 的 push 路径先 `fetch --prune --no-tags`，失败立即停在打标签前；`check-push` 取不到远端标签清单同样 fail-closed。atomic push 失败仅在远端分支 SHA 与**完整版本标签映射**逐值未变时原样重试一次，远端前移或新增任一版本标签都不自动重放。标签说明的上一版本优先取远端 tag map 的 peeled commit，不再依赖本地是否抓过标签对象；流程写入 `docs/operations/git-workflow.md`，6 条安全边界测试通过。

首轮语义审查（报告 `semantic-review/2026-10-29-072447-pr-local.md`）另抓出 8 项，复核后逐项处置：

1. N2 长前缀导出 / 导入在读正文或上传体前分别执行 `authorize_wp_read` / `authorize_wp_edit`，并以 `read_checklist` / `save_checklist` 进入 Wp_Bound_Gate；非法 UUID 统一按不可枚举资源返回。
2. 导入由“前三列表头不符只告警、缺列按位置兜底”改为完整 17 列逐位等值，缺列 / 多列 / 调序 / 重复列都拒绝；NaN / Infinity 在 JSON 序列化前拒绝，`allow_nan=False` 作第二道门。整本先解析、后按稳定 item_id 锁行并原子写，记录 `updated_by`、冲突更新递增 `content_version`；router 统一 commit / rollback，提交后只发一次 `WORKPAPER_SAVED`。
3. 国企披露不再直接读取已退出持久化形状的 `audBegin/audPayable/audPaid`，而是在读取 `N2-2-detail-rows` 时调用生产 `enrichN2DetailRow`；带非零 C/G/H、D/I/K、E/J/L 的回归证明 opening / payable / paid / end 分别为 112 / 36 / 14 / 134，陈旧 `aud* = 999` 不被采纳。
4. N2-2 导入成功后子 Tab 发 `imported`，宿主唯一 `selfLoad` 重读 render-config；失败不发事件。宿主同时补齐必需的 `projectId`。
5. `n2ImportExportWire.spec.ts` 进入 N 域测试事实；lane2 公式数从 `n_cycle_facts.LANE2_FORMULA_CELLS` 派生。N1 纯函数抽取移除一个展示序号源码站点，slice 的 family 与两处汇总计数按现算 8→7；N5 模板净减 1 B，模板总字节基线同步为 45,775,625。`test_n_cycle_foundation_canary.py` 改前已超 800 行，本批把旧缺陷断言翻为修复态后净减 9 行至 1065；按当前真实行数登记白名单并冻结 5% 膨胀，拆分轴写在白名单注释中。
6. `push_version.py` 的三个安全缺口按上段收口；源码稳定后才运行 `install.ps1`，避免在验证中途把共享 hook 换成半成品。
7. 回归中随机命中 `JSON.stringify(-0) → 0`，原 PBT 用 `Object.is` 把数值等价的零判成改写；断言改为金额数值相等，失败种子对应反例转为稳定通过。

验证证据：N2 / push / 模板与 N 域目标后端 25 passed，项目鉴权与真实 router 挂载 43 passed；N2 前端 27 passed，相关前端 23 文件 643 passed，相对基线新增失败 0、修复 2；单区域 vue-tsc 候选 53 / 基线 54，新增 0、消除 1；N1~N5 契约生成器、公式对拍 `--check`、27 本 386 格模板修复清单、N5 OOXML 定向差异、字段名守卫、ruff / py_compile / ESLint / JSON / `git diff --check` 均通过。相关后端成对全组的最终结果见 §9 末段。

## §5 受保护字段统一（R7，已做）

- 修前三处口径不同：`contracts.PROTECTED_MODES` = {formula, auto_source, cross_sheet}；`adapters.base.FieldValue.is_protected` = {formula, auto_source}；`merge._protection` 把 cross_sheet 当可编辑。影响 25 个字段（G3-1 审定表 21、G11-1 4），模板里全是引用明细表的公式，OO 改了不报冲突、直接合并，物化时还按字面量写进公式格。
- 现在：唯一来源 `contracts.PROTECTED_MODES` / `FORMULA_MODES`；`FieldValue.is_protected` 与 `merge._protection` 都读它；cross_sheet 按公式字段处理（有签名且一致 ⇒ 采纳重算；没有证据 ⇒ 受保护冲突）。守卫 `test_protected_mode_single_source.py`：三处逐 FieldMode 一致、25 格逐格、代码里不再单写 `mode is FieldMode.formula`（AST，一处登记例外）。

## §6 篡改裁决后公式还原（R4，已做）

- 实测修正现状：真 D4 上「公式格被敲成数字 → 保留服务器值 → 物化」不是「发布出一个数字」，而是 `_emit` 判「契约说是公式但 substrate 没公式」抛 `ProtectedRegionWriteError`，整次保存失败；公式被改写且值没变时，改写后的公式原样进文件。
- 修法（`formula_restore.py`）：OO→HTML 物化外层进入作用域，取已发布形态的公式签名，按落点行与 incoming 表几何换回公式文本，值取合并结果；作用域外（HTML→OO、首版发布、离线工具）行为不变。裁决选 OO 值时不还原。守卫 `test_tamper_keep_current_restores_formula.py`。

## §7 转置表签名（R5，不需要）

实证：五张转置表（D4-29 / D4-12 / G4-9 / G5-9 / G6-11）的契约里没有公式字段，签名证据无从产生也无需产生；R5 不做，`test_formula_signature_geometry.py` 钉住这一点（转置表出现公式字段即红）。

## §8 插行后签名（R6，已做）

- 签名按受管表几何归一：本行 `{r}`、表首末 `{start}` / `{end}`、表下方第 k 行 `{end+k}`、表内他行 `{r±k}`。OO 在表内插行 / 删行后合计行、表首末行、表内他行引用的签名不变；引用真被改、指向新增行、换成数字，签名仍不同（按原规则报冲突）。只用于比较与还原，不改写入。
- 限制：D4-9 这类不能插行的表不做端到端插行测试（物化拒绝位移）。

## §9 后端测试红（R9）

以 `wsr_head`（完整检出，origin `213f19816`）跑 `tests/workpaper_sync` 与 4 个同步相关文件为准（上一轮「1937 失败 / 771 报错」来自缺文件的稀疏检出，作废）：HEAD 上 **802 失败 / 271 报错 / 15380 通过**，按原因归 530 组（最多的几组：K foundation 契约草案路径失效 94、文件不存在 74+25、`n_cycle_scanner` 函数改名 55+33+21+19+8+7+3、`_spec_dir` 模块缺失 14+8）。第一批改动后全量同口径对比：787 失败 / 271 报错 / 15429 通过。由过转红 7 条，都是测试写死了旧值（F2 车道测试抄的模板哈希 4 份里 3 份早已过期、golden 摘要前缀 6 份、N3 公式格数 162、N3-2 H 列旧公式文本），改为读 provider 常量或新值后子集复跑，只剩 5 条基线既有红（全量未重跑）；由红转过 22 条（模板 / slice 刷新顺带）；断言旧缺陷存在的 44 条改写成断言缺陷已修；另 8 条是参数化 ID 内嵌 zip 时间戳的漂移，不是丢测试。逐组修复与根因在下一批完成后记入本节。

第二批（模板 #20~#28 + 前端 §3.1）同口径全量：后端 780 失败 / 271 报错 / 15442 通过，对第一批基线由过转红 0 条（子集阶段抓到的 `test_task41` 模板字节数常量已改）、由红转过 8 条（PG 路由 6、LibreOffice 转换 1、延迟导入基线 1，不是本批改动所致）。前端全量以 13120d6d6 为基线：216 → 208 失败、37595 → 37626 通过，由过转红 1 条（`a173ConsultationRecord.pbt` 随机用例，单跑 13/13 通过、本批未动该组件）；基线既有红：`d3CellOverrideRender` 5 条、`formulaEngineInventory` S34 属性 1 条。

第三批（模板 #29~#32 + §3.2 前端 + 对拍守卫 + L8-2）同口径全量对第二批：后端 779 失败 / 271 报错 / 15446 通过，由过转红 3 条，都是按源码文本 / 行号取证的守卫跟着本批前端重构失效：H5 行归一外提后 `_normalizeRow` 只剩转发（守卫按 `function _normalize*` 函数体找 `rowId: raw.rowId ??`，改为模块级 `_normalizeRow` 本体 + 导出别名）、L8 保存改存算好的行（守卫断言改为 `rowsForStore(computedRows.value)`）、H slice 行号锚点（H4 / H6 / H9 行身份行、H6 展示序号行、H5 读写行随函数外提移位）。锚点处理：引号内的整条锚点用 `resync_data_line_anchors.py --only <本批改过的 7 个前端文件>` 平移 18 处；工具不认的连写 / 带括号说明 / 正文锚点逐条改（H slice 10 处、G 删除计划 3 处）；L slice 两组锚点 HEAD 起就指错，一并改正——L6-2 展示序号锚点指的是 `rowId` 行（改指 `seq` 行），L1 读写锚点自 1b617652c 起指向空行与无关行（第一轮回归里因本批给该文件加了 20 行、碰巧落到非空行而「转过」，改指 `api.get` / `api.put` 两行后 `test_formdata_refs_really_hit_the_checklist_calls` 也转过）。子集复跑由过转红 0；由红转过 6 条（延迟导入守卫 3 条：基线里的 `phase5_f4_01_adjudication` 已由 5cb7ebe70 交付，按「修好必须删」移出；L slice 锚点 3 条）。根目录 12 个相关文件（模板快照、prev3 定位表、G9 / G14 / D6 / D2、对拍清单守卫等）对第二批提交逐条对比新增失败 0，既有红 134 条（`test_g_cycle_export_import_verification` 131 条；`test_wp_templates_readonly` 3 条，其中 2 条报错只在与其他文件同跑时出现、单跑不出现，1 条是真库 81 份底稿 `file_path` 指向模板库），R9 处理。合并到上游新提交后，双方改过的 52 个后端测试文件对上游干净检出逐条对比新增失败 0，前端 78 个相关文件只剩基线既有的 `useF5Integration` 1 条。前端全量对第二批：38017 例，由过转红 2 条，都是本批未动组件的随机属性用例（`DefaultLayoutNavigation.pbt` 反例 `"toString"` 落到对象原型上、`useG5FormulaEngine.pbt` P15 十亿级金额浮点求和次序差 9.5e-7 超容差），记入 §11；由红转过 2 条（a173 / a81 随机用例）。

批 A1（任务 9.4a）同口径全量对第三批推送提交 083f5e774：后端 699 失败 / 182 报错 / 15702 通过（基线 704 / 182 / 15616），由过转红 2 条都是本批改对了行为、旧判据钉着旧缺陷（aos8 多 item 登记、D1 去切片变异反证，见 §4.1），已改写；由红转过 7 条（PG 路由 6、模板覆盖层 1，非本批改动）。前端全量 38142 例由过转红 1 条：`transposeGrid` 随机属性用例（反例里 `-0` 经 JSON 克隆变 `0`），用失败种子在 083f5e774 上复现同红，非本批引入。

批 C 与语义审查收口的最终同口径回归（候选 `oo_parity_push` 对基线 `oo_review_base`，两者基点均为 `8107371f0`）：后端按 78 文件清单，候选 **2621 passed / 112 failed / 24 skipped / 6 errors**，基线 **2571 / 124 / 24 / 6**；逐 node 比较 `new_bad=0`、`both_bad=118`、候选修复 5。候选仍红的 112+6 全在基线同红，主要是归档 spec 证据目录缺失、旧 N/M/L 锚点与真库快照漂移，不归因给本批。前端按 23 文件清单 **643 passed**，基线 22 文件 633 passed / 2 failed，`new_bad=0`、修复模板对拍 2；单区域 vue-tsc 候选 53 / 基线 54，新增 0、消除 1。首轮语义报告的代码问题全部闭合；共享 `.git/hooks/push_version.py` 安装副本在提交前刻意不更新，提交并同步主工作树后运行 `install.ps1` 作为最后部署门。

推送前远端又前移 8 个提交到 `35c49967a`。在该提交上新建分离头 worktree 重放，远端 71 个改动路径与本批 56 个路径交集为 0；重放后的 56 个暂存 blob 与已验证提交 `e513e85a8` 逐字节相同。再以 `35c49967a` 建干净基线串行复跑：后端计数与上段完全相同（`new_bad=0`、修复 5），前端仍 643 passed / 基线 2 failed（新增 0、修复 2），vue-tsc 仍 53 / 54（新增 0、消除 1）；暂存树自洽两道门均通过。

浏览器首轮在和平药房 2025 的 N2-2 只读走查确认 H「期初重分类调整」及 M=C+G+H 已渲染，同时发现方法说明仍写“源模板 16 列”，与 A:Q 17 列不一致；跟随修复改为 17 列并增加挂载断言，随后再走查确认。主提交已推送，故该修复按不可改写历史原则另发跟随版本，不 force / amend 已发布提交。

浏览器继续点“导出模板”复现 404；项目 `authorize_wp_read` 已通过，真正拒绝点是精确门禁把业务选择码 `N2-2` 误当 `requested_sheet_key`。同一 admin / 同一底稿去掉该参数后门禁立即返回可访问上下文。N2 长前缀本就是整份 checklist 的导入导出入口，router-level dedicated gate 与显式 read/edit + checklist gate 已覆盖资源、项目与写权限；移除这个错误的 sheet 绑定，并用路由参数捕获测试钉住“不传伪 sheet key”。

## §10 被否决的方案

| 方案 | 理由 |
|---|---|
| 模板覆盖层修模板 | 覆盖层从未实现；覆盖文件在库外、只对本环境生效；契约按权威模板冻结，覆盖后两边不一致 |
| 前端照抄模板错误公式 | 用户裁定模板错的按正确口径来 |
| 真实项目也重发布 | 用户只批准【测试】项目 |
| 字段名不通的表整表降级为单侧 | 双向回写是本轮目标；只有模板列确实不该受管时才逐个移出 |
| 插行签名改为全量行身份重映射写入 | 只需要比较与还原，不需要改写入 |
| G8 M 含 L | 处置时重复计入 L，且破坏 E+M=Q |
| 前端载入截断 / 改号登记为「录入校验」例外 | OO 侧填的值回到表单被改掉，两侧来回变值；表单录入时的区间校验保留 |
| G13 / G14 核对保留 `\|差\| ≤ 0.01` | 浮点结果 0.00999… 会把差一分判成一致，与模板 `=J=D` 结论不同 |
| 对拍适配器里把契约字段名翻译成前端字段名 | 会把 R3 的接线错误藏起来；字段名不通的表登记例外、由任务 9 改接线 |
| L8-2 新增行计入合计 | OO 侧合计公式不含插入行，两侧合计不同 |
| L8-2 模板合计改成 SUM 区间 | 合计项有减项与派生行，不是连续区间求和；引擎只扩展起点不晚于首个数据行的区间 |
| 串表只在 F2 门面里按表切片 | 普查同病 8 家，逐家照抄 D1 的切片是 8 份副本；框架层按表前缀过滤是唯一修复点，单表 provider 行为不变 |
| F2-48 / F2-57 留在 rows 分支、门面里把裸数组包回 dict | rows 分支给门面的基线恒为 `[]`（镜像只把数组当基线），非受管字段与外层键无从保留 |

## §11 范围外

- 断网时错误文案变英文（`utils/http.ts` 动态 import 失败）、冲突后在线编辑租约留到过期：属在线编辑壳层，另立 spec。
- 全量 vue-tsc 内存不足：沿用单区域 tsconfig。
- HEAD 已提交的 `wp_template_files.py` 引用了未入库的 `wp_generate_file.bind_lazy_workpaper_file`（并发会话 procedure-chain 的工作区改动），干净检出时 `test_prev3_prefill_locator::test_router_first_init_annotates_prior_year` 红；真库 81 份底稿 `file_path` 仍指向模板库（`test_no_workpaper_points_into_template_library`）——都不是本 spec 引入，报告给用户。
- `l4.bonds_payable.candidate.json` 与 reviewed 生产契约并存，L 生成器 `--apply` 因此 exit 1（HEAD 既有）。
- 前端两条随机属性用例偶发红（本 spec 未动这两处）：`tabToRoute` 用对象字面量查表，反例 `"toString"` 取到 `Object.prototype` 上的函数（生产代码缺陷，入参来自路由 query）；`useG5FormulaEngine` P15 断言浮点求和与次序无关，十亿级金额下不成立（用例口径问题）。
- L8-2 在 R21 之后插入的新增行不计入合计（模板合计公式只列 R13 / R14 / R15 / R16 / R20 / R21，OO 侧同样不计），前端提示并入相应项目；要计入需改模板合计结构，未做（§10）。
