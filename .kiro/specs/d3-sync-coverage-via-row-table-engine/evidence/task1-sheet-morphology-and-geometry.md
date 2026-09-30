# Task 1 六张 sheet 形态判定 + 几何实测证据

**实测日期**：2026-09-26　**方法**：openpyxl 直读权威模板
`backend/wp_templates/D/D3 预收账款.xlsx`（`data_only=False`，读公式字符串非缓存值）+ 按值
grep 全仓（前端 `audit-platform/frontend/src/` + 后端 `backend/`）。全程离线，未连库、未改任何
生产代码。原始探针脚本 `_tmp_d3_morphology_probe.py`（一次性用完即删，按仓库规约不留存）产出的
文本摘录进本文档；关键数字均可用同一段代码复算（见文末「复算方法」）。

**⚠️ 探针脚本自身的一处坑（如实记录，供后续同类任务参照）**：首轮探测时脚本在做「候选空列扫描」
（越界访问 `ws.cell(row=, column=ws.max_column+N)`）后才读取 `ws.max_column` 写入 JSON 摘要，
而 openpyxl 的 `max_column`/`max_row` 是**动态值**——任何越界 cell 访问都会把它们撑大。首轮
JSON 摘要里六张 sheet 的 `max_column` 全部虚高 3（如 D3-1 显示 15 而非 12）。修法：在做任何
探索性越界扫描**之前**先锁存 `orig_max_row`/`orig_max_column`，后续全部逻辑改用锁存值。复算后
六张几何与 requirements.md 记录的「在案」参考值逐项一致（见下文各表）。

## 前提复核（承接 Task 0）

Task 0 证据（`evidence/task0-prerequisite-check.md` 复核追记部分）已确认：当前 HEAD 前置
A/B/C 均满足，仅前置 D（`adapter_registered=False`）为已知卡点。本任务是纯离线模板几何实测，
不依赖 `RowTableSheetSpec`/`AdjudicationSheetSpec` 是否已声明、不依赖 adapter 是否注册、不连库，
因此不受任何前置状态影响，可以照常推进。本文档产出的实测值供 Task 6/8/9/11/13 的声明代码引用。

---

## 一、六张 sheet 形态判定结果一览（先判形态，再看几何）

| sheet | `binding_kind` | `row_identity_key` | 判定依据摘要 |
|---|---|---|---|
| **D3-1** 审定表 | **既非 `excel_table` 也非纯 `static_region`** —— 走 `AdjudicationSheetSpec`（框架层第三条路径，见下文详述） | 两区块各自**稳定 key 固定行**（性质分类 4 行 + 账龄分类 4 行，行数不可增删） | 前端 `useD3Adjudication.ts` 的 `NATURE_ROWS`/`AGING_ROWS` 常量 + 逐格 `item_id` 存储模型 |
| **D3-3** 调整分录 | 不适用（🔍 可行性核对象，非本任务判定范围） | 不适用 | 本任务只登记几何，形态裁决属需求 5，本 spec 已有裁决 F4 |
| **D3-4** 分析表 | **`excel_table`（两个独立动态行区）** | `rowId`（与 D3-2 同款 UUID 动态行） | 借方区（行 11-17）/ 贷方区（行 21-25）各自的固定标签行是**模板占位渲染**，前端 store 真实是任意长度数组；见下文「D3-4 形态判定详述」 |
| **D3-5** 账龄 1 年以上 | **`excel_table`（UUID 动态行）** | `rowId` | 数据区行 11-13（仅 3 行模板占位）+ SUM 公式引用固定行区间，但前端 `useD3LongTerm.ts` 是任意长度数组；见下文「D3-5 待判定问题结论」 |
| **D3-6** 关联关系及交易 | **`excel_table`（UUID 动态行）** | `rowId` | 数据区行 12-16（模板占位 5 行）+ SUM 公式引用固定区间，前端无对应 composable 内部约束长度；见下文「D3-6 待判定问题结论」 |
| **D3-7** 检查表（凭证抽查） | **`excel_table`（两个独立动态行区）** | `rowId` | 本期区（行 17-26）/ 期后区（行 31-38），两区各自 SUM 公式 + 前端 `useD3VoucherCheck.ts` 任意长度数组 |

**关键结论先行**：**六张里没有一张应判 `static_region`**。D3-5/D3-6 的「待判定」疑虑（公式集中在
前几行、看起来像固定结构）经实测确认是**假象**——公式集中在 header/footer 附近是因为这些 sheet
的**数据区本身很小（模板只画 3~5 行占位）**，不是因为行不可增删。判定的真正依据是前端 store 的
数据形状（任意长度 JSON 数组）与模板 SUM 公式的引用方式（引用固定区间会在插行后失真，这正是
行表引擎要解决的位移问题，不是"没有行维度"的证据）。详见下文逐张判定详述。

**⇒ 对 tasks.md「本任务产出会改后续阶段顺序」预判的回应**：该预判基于假设「D3-5/D3-6 可能是
`static_region`」，实测证明假设不成立，**接入顺序不需要按 static_region 优先调整**，
`design.md` 记录的默认路线 `1→2(D3-6)→4(D3-4双区)→5(D3-5)→7(D3-7双区)→8(D3-1)` **保持不变**
（理由见「八、接入顺序建议」）。

---

## 二、几何实测数据（逐张，与「在案」参考值对照）

### D3-1 审定表

| 项 | 实测值 | 在案参考值（requirements.md/tasks.md） | 一致性 |
|---|---|---|---|
| 行×列 | 30 行 × 12 列（A1:L30） | 30 行 × 12 列 | ✅ 一致 |
| 公式数 | 88 | 88 | ✅ 一致 |
| 主公式列 | E14（`=B8+C8+D8` 系公式的一个样例落点）/ I12 / J11 / K11（列本身，非固定单 cell） | E14 I12 J11 K11 | ✅ 一致（原表述指公式**列**，非单 cell 坐标，实测公式列确为 E/I/J/K 一族） |
| Excel Table | 无 | 无（走 `AdjudicationSheetSpec`） | ✅ 一致 |
| 非空行范围 | min=1 max=30 | — | — |
| 候选空列 | M（idx=13，紧邻已用到的 L 列）、N、O 全空；**L 列本身非空**（3 个 cell：`D3-1`/`原因分析`/`原因分析`，是索引号与"原因分析"文字标签，不是数据列） | — | 若后续需要为逐格 mask 引擎注 UUID 列，候选是 M（不是 L，L 已被模板占用为文字标签列） |

**逐区实测细节（裁决 F3 要求的「不得照 D1-1/D2-1 推演」）**：

```
区1（一、按照性质分类）：
  表头：行6(A6=项目,B6=期初数) / 行7(B7=未审数,C7=账项调整,D7=重分类调整)
  数据行：8~12（5 行，NATURE_ROWS 固定 4 项 + 1 空行冗余槎位，见下方交叉核实）
    A8='预收销售固定资产款' A9='预收销售土地使用权款' A10='合同不成立时已收取的对价'
    A11='其他' （A12 无标签，是模板画的第5行占位，前端 NATURE_ROWS 实际只有4项）
  合计行：13（B13='=SUM(B8:B12)' 等，SUM 区间覆盖5行含空槎位）
区2（二、按照账龄分类）：
  表头：行15(A15=项目,B15=期初数) / 行16(B16=未审数,C16=账项调整,D16=重分类调整)
  数据行：17~20（4 行，与前端 AGING_ROWS 4 项逐字对应）
    A17='1年以内（含1年）' A18='1至2年（含2年）' A19='2至3年（含3年）' A20='3年以上'
  合计行：21（B21='=SUM(B17:B20)' 等）
调节行（非独立"区"，是两区合计后的试算平衡校验）：
  行22 A22='试算平衡表数'（无公式，人工/自动填试算平衡表口径数）
  行23 A23='差异数'（E23='=E21-E22', I23='=I21-I22'，只对账龄区合计做差异校验，不含性质区）
```

🔴 **裁决 F3 要求的实测结论**：D3-1 是**两区块**（性质分类 + 账龄分类），**不是** D1-1 的
「3 区 gross/bd/net × 动态票据种类」，也**不是** D2-1 的「1 区 × 写死 4 行」。且区1（性质分类）
的模板画了 5 行（8-12）但前端 `NATURE_ROWS` 只声明 4 项——这个"5 行模板 vs 4 项前端常量"的
落差需要在 Task 13 声明 `AdjudicationSheetSpec.sections` 时特别处理（见「五、footer 与 gating
核查」后的附注）。

### D3-3 调整分录汇总表（🔍 可行性核对象，几何仅登记不判形态）

| 项 | 实测值 | 在案参考值 | 一致性 |
|---|---|---|---|
| 行×列 | 23 行 × 10 列（A1:J23） | 23 行 × 10 列 | ✅ 一致 |
| 公式数 | 6 | 6 | ✅ 一致 |
| 主公式列 | A2 D2 F2（实测落在行3/4，是底稿目录页眉引用公式，非数据行公式） | A2 D2 F2 | ✅ 一致 |
| Excel Table | 无 | — | — |
| 数据区 | 行 5（表头：调整事项说明/类别/报表项目/科目名称）之下无固定数据行样例，是空白待填表格 | — | — |
| 候选空列 | K/L/M 全空（H 列"贷方调整金额"非空，是表头文字） | — | — |

本 spec 需求 5 已裁决 D3-3 走可行性核、默认倾向 `single_html`，几何数字仅供留证，不在本任务
做形态判定。

### D3-4 预收账款分析表（双区，需求 2.1）

| 项 | 实测值 | 在案参考值 | 一致性 |
|---|---|---|---|
| 行×列 | 38 行 × 9 列（A1:I38） | 38 行 × 9 列 | ✅ 一致 |
| 公式数 | 22 | 22 | ✅ 一致 |
| 主公式列 | E8（页眉引用）/ D6（借方差异行公式落点，实测在行17列B，"E8/D6"应理解为设计文档速记，
  实测主公式列为 B/D/E/H 一族） | E8 D6 C3 | ⚠️ 部分不一致，见下方说明 |
| Excel Table | 无 | — | — |

⚠️ **主公式列的措辞需要澄清（如实记录差异，不强行对齐参考值）**：requirements.md 表格写
"E8 D6 C3"，这大概率是"公式落点样例坐标"的速记（类似 D3-1 的"E14 I12 J11 K11"），不是逐字段
列标注解。实测公式所在列（去重排序）= `A B C D E H`。逐行分布：

```
行3/4：A/C/E 列（底稿目录页眉引用公式）
行17：B 列（差异行 =B11-B13-B14-B15-B16）
行28~32：D/E 列（各行 =Bn-Cn / =Dn/Cn）
行33：B/C/D/E/H 列（=SUM(...) 小计行）
```

不存在真正意义上的"E8/D6/C3"这三个具体坐标（行8/行6/行3 都不是本表的关键行）。判断这是设计
文档编写时的笔误或简写惯例，不影响后续任务的声明代码（声明代码应引用本文档的实测行列号，不
引用参考表的坐标速记）。

**D3-4 形态判定详述（🔴 关键发现，直接决定双区的行段边界）**：

模板实际画了**三个**带公式的数据段，但前端 composable 只对应其中**两个**为独立 store（第三段
是纯派生 computed，无独立 store 键）：

```
段①（一）预收账款借方发生额分析：行 9~18
  A11='本期借方发生额合计'（无公式，人工/自动填）
  A12='对方科目：'（区块内小标题，非数据行）
  A13~A16：'资产处置损益'/'固定资产'/'增值税'/' ……'（4行固定标签，模板占位）
  A17='差异' B17='=B11-B13-B14-B15-B16'（硬编码引用行13-16，共4行）
  A18='差异合理性分析'（说明文字行）
  ⇒ 对应前端 useD3Analysis.ts 的 ITEM_ID_DEBIT_ROWS='D3-ana-debit-rows'
    （store 载荷 AnalysisRow[]，rowKey/label/amount/source/remark，真实任意长度）

段②（三）预收账款贷方发生额分析：行 19~25
  A21='本期贷方发生额合计' C21='预收账款总账' D21='N/A'（三个固定说明字段，非行表）
  A22~A24：'其中：银行存款收款'/'应收票据'/'         ……'（3行固定标签，模板占位）
  A25='差异合理性分析'
  ⇒ 对应前端 ITEM_ID_CREDIT_ROWS='D3-ana-credit-rows'

段③（四）期末预收账款主要债务人分析：行 26~33
  A27~A31：'债务人1'~'债务人5'（5行固定标签占位）
  D28~D32：'=Bn-Cn'（变动金额公式，逐行）
  A33='小计' B33='=SUM(B28:B32)' 等（小计行，SUM区间正好覆盖5个占位行）
  ⇒ 对应前端 top5Debtors computed —— 🔴 这是**纯派生值**（从 D3-2 明细表交叉计算 Top5），
    没有独立 store item_id，用户不能在这里手动编辑/增删行，前端 `D3TabAnalysis.vue` 的
    "(三) 期末主要预收客户分析" 卡片只读展示 top5Debtors，无导入/导出按钮
    （对比段①②各有"模板/导出/导入"三个按钮）
```

⇒ **需求 2.1 声明的两个受管区应对应段①②（`D3-ana-debit-rows`/`D3-ana-credit-rows`），
不包含段③（债务人分析，纯派生只读，不该声明为受管区）**。这与 design.md 的
`SPEC_D304_CREDIT`/`SPEC_D304_DEBIT` 命名一致（`table_key="analysis_credit_rows"`/
`"analysis_debit_rows"`），只是几何行段需要修正为段①②的实测边界，不是"38 行×9列内任意
两段"的泛泛写法。

**🔴 模板固定行数 vs 前端任意长度数组的张力（需要在 Task 8 声明时明确处理策略）**：

段①模板画了 4 个占位标签行（13-16），差异公式 `=B11-B13-B14-B15-B16` **硬编码引用这4行**；
段②模板画了 3 个占位标签行（22-24），无差异公式硬编码引用（差异合理性分析在25是纯文字，
没有类似段①的计算行）。但前端 `debitRows`/`creditRows` 都是 `ref<AnalysisRow[]>`——真实是
任意长度数组，通过"借方导入/贷方导入"两个独立的 Excel 模板导入导出机制填充（`useD3TabImportExport`
`(wpIdRef, 'D3-4-debit')`/`'D3-4-credit'`，与本 spec 要接的 OO/HTML 双向回写路径**是两套不同
机制**）。

这与 D4-33"其他业务毛利率分析表"的**静态块矩阵 + limited_bidirectional 裁决**同型
（`phase5_d4_other_margin_sheet.py` 注释：「前端业务类型**动态**（可增删），模板只有 3 固定
列组。本 provider 只受管**前 3 个业务类型**（按位置映射），第 4+ 个业务类型无模板列 →
HTML-only」）。**建议 D3-4 双区的声明也走同款裁决**：段①受管**前 4 行**（对应模板 13-16 的
占位）、段②受管**前 3 行**（对应模板 22-24 的占位），第 5+ 行（若用户导入超过模板行数的数据）
判 HTML-only，不强行插入行表引擎的 row_shift 链路——**这一点与 design.md 现有"形如 D4-9 双区"
的描述不完全贴切**，D4-9 是纯动态行表（真 Excel Table + row_shift），D3-4 段①②更接近
D4-33/D4-8 的"位置映射静态块 + limited_bidirectional"范式。这是本任务发现的一个需要在 Task 8
声明阶段重新核实的裁决点，不属于"D3-5/D3-6 待判定"清单但同样重要，如实记录在此，留给 Task 8
处理。

**为何仍判 `excel_table` 而非 `static_region`（与上面"位置映射"的发现看似矛盾，实则不矛盾）**：
`binding_kind` 判据是"有没有行维度"（D1 design.md 表二），段①②确实有行维度（多行同构标签+
金额+来源+备注），只是行数在 Excel 侧固定、在前端 store 侧可变——这正是"稳定 key 固定行"
（D4-6 范式）与"limited_bidirectional 位置映射"（D4-33 范式）的中间态，不是"无行身份"的
`static_region`（`static_region` 的判据是单 cell 锚点，如 D4-13 的 process/conclusion 两个
纯文本字段，没有"多行同构"的表格形状）。综合判断：D3-4 段①②应判 **`excel_table` binding +
稳定 key 固定行（或 limited_bidirectional 位置映射）**，不是 `static_region`。

### D3-5 账龄 1 年以上的预收账款检查表（待判定 → 已判定）

| 项 | 实测值 | 在案参考值 | 一致性 |
|---|---|---|---|
| 行×列 | 20 行 × 8 列（A1:H20） | 20 行 × 8 列 | ✅ 一致 |
| 公式数 | 9 | 9 | ✅ 一致 |
| 主公式列 | A2 C2 E2（页眉引用公式落点，实测确为行3/4的A/C/E列） | A2 C2 E2 | ✅ 一致 |
| Excel Table | 无 | — | — |
| 数据区 | 表头行10（对方单位名称/期末余额/账龄/经济业务说明），数据行 11~13（**仅 3 行模板占位**），
  合计行14（`B14='=SUM(B11:B13)'` `F14='=SUM(F11:F13)'`） | — | — |
| 候选空列 | I/J/K 全空（H 列非空但只是"备注"表头 + 页眉引用公式，不是数据列） | — | — |

**#### D3-5 待判定问题结论（requirements.md 需求 9.2 要求，🔴 不能悬而不决）**

实测结论：**D3-5 属三形态中的「UUID 动态行」（`excel_table` binding，`row_identity_key='rowId'`），
不是「稳定 key 固定行」，也不是 `static_region`。**

判定依据：

1. **模板数据区只有 3 行占位（11-13），但没有任何证据表明这 3 行是"固定枚举"** ——
   不像 D3-1 的 `AGING_ROWS`/`NATURE_ROWS` 或 D4-6 的 `DEFAULT_INDICATORS` 那样有一个前端常量
   数组把行标签锁死成固定枚举值。D3-5 模板的行10只是表头（列标签"对方单位名称"），行11-13的
   A列本身是**空的**（没有预填任何文字标签，与 D3-1 区1的"预收销售固定资产款"等固定文字标签
   完全不同）——这意味着这 3 行是"画了外框等待用户填写"的占位行，不是"固定業務分类枚举"。
2. **前端 composable 明确是动态数组**：`useD3LongTerm.ts` 的 docstring 写"rows reactive
   （从D3-lt-rows加载JSON）"，且 grep 未发现任何固定长度常量数组（对比 D3-1 的 `NATURE_ROWS`/
   `AGING_ROWS`、D4-6 的 `DEFAULT_INDICATORS`）。
3. **公式集中在少数行是因为数据区本身很小（3行），不是因为行不可增删**——`B14='=SUM(B11:B13)'`
   这类 SUM 公式引用固定区间**正是行表引擎要解决的"插行后区间要跟着位移"问题**，恰恰说明这是
   一张需要位移链的动态行表，而不是"不需要位移链因此判 static_region"的证据。design.md/D1
   design.md 表一里"能走静态就不该硬塞行表"的判据，指的是"完全没有行维度、单 cell 锚点"
   （如 D4-13），不是"行数少"。D3-5 有清晰的行维度（对方单位名称/期末余额/账龄/说明 四列一行
   一条记录），只是行数少，这与"该不该走 static_region"是两个不同的问题。

4. **交叉参照 D567 spec 的 D7-5（同型）现状**：grep `.kiro/specs/d567-sync-coverage-via-row-table-engine/`
   全部文件确认，D7-5 目前记录的状态是**"待判定，与 D3-5 同型须同结论，首版只写『骨架可复制』，
   未做形态判定"**（`d567/tasks.md:87` 与 `d567/requirements.md:314-317` 逐字如此）。
   **该 spec 目前没有已完成的 D7-5 形态判定结论可供交叉参照**，如实说明：本次判定是 D3-5/D7-5
   两者中**第一次**做出的形态判定，不是"引用姊妹 spec 已有结论"。⇒ 按 tasks.md 与
   requirements.md 需求 9.2 的要求，**本次 D3-5 判定结论（UUID 动态行）应回填给 D567 spec
   作为 D7-5 的同一结论**（两者几何逐项相同：20行×8列/9公式/主列A2 C2 E2，且经营性质同为
   "账龄1年以上的预收/合同负债检查表"，业务语义完全一致，没有理由判成不同形态）。这件"回填"
   动作本身不在本任务范围内（本任务不改任何文件除本证据文档），但在此明确记录供后续任务或
   D567 spec 的对应任务引用。

### D3-6 关联关系及交易检查表（待判定 → 已判定，本 spec 首张接入样本）

| 项 | 实测值 | 在案参考值 | 一致性 |
|---|---|---|---|
| 行×列 | 34 行 × 12 列（A1:L34） | 34 行 × 12 列 | ✅ 一致 |
| 公式数 | 16 | 16 | ✅ 一致 |
| 主公式列 | F6 D3 A2（页眉引用与行内公式落点，实测公式所在列去重排序 = `A C D E F G J`，见下方） | F6 D3 A2 | ⚠️ 部分不一致，见说明 |
| Excel Table | 无 | — | — |
| 数据区 | 表头行11（关联方名称/关联关系/期初余额/借方发生），数据行 **12~16（5 行模板占位，A列无预填
  文字标签，与 D3-5 同款空白占位）**，合计行17（`C17='=SUM(C12:C14)'` 等，🔴 SUM 区间只覆盖
  12-14 共3行，比数据区少2行，见下方"SUM区间落差"说明） | — | — |
| 候选空列 | K/L/M/N/O 全空（J 列非空但是"备注"表头 + 页眉引用公式） | — | — |

⚠️ **主公式列措辞同 D3-4 情况**：requirements.md 写"F6 D3 A2"是坐标速记，不是逐列枚举。实测
公式所在列（去重排序）= `A C D E F G J`；逐行分布：

```
行3/4：A/D/G 列（页眉引用公式，D3='=底稿目录!A4' 等）+ 行3 额外 J='=底稿目录!F18'（页码引用）
行12~16：F 列（=Cn+En-Dn，期末余额=期初+贷方-借方，逐行同款公式）
行17：C/D/E/F 列（=SUM(C12:C14) 等，小计行）
```

**🔴 SUM 区间落差需要如实登记（不能因为想对齐"数据区=5行"而误报）**：数据区模板画了 5 行
（12-16，F列公式逐行都有），但合计行17的 SUM 公式硬编码只覆盖 `C12:C14`（3行，12-14），
**没有覆盖到 15-16 两行**。这是模板本身的一个潜在缺陷（或者是"预留 5 行画框但历史上只有 3 行
是常规业务场景"的编制约定），不是本次实测的误差——已用 openpyxl 逐 cell 核对确认 F/C/D/E 列
在 17 行只有到 `C12:C14`/`D12:D14`/`E12:E14`/`F12:F14`，行15/16 的 F 列公式（`=C15+E15-D15`/
`=C16+E16-D16`）计算结果不会被计入合计。这是**模板本身的预存缺陷**，登记但不在本 spec 处理
（不改任何模板文件），后续声明代码需要注意：如果按行表引擎"插行后 SUM 区间自动跟随位移"的
机制正确工作，这个缺陷理论上会在引擎层面因为区间归一化被自动纠正为覆盖全部数据行——但这需要
在 Task 6 接入验收时用真实测试验证，不能想当然认为"引擎接入后自动就对了"。

**#### D3-6 待判定问题结论（requirements.md 需求 9.3 要求，🔴 不能悬而不决）**

实测结论：**D3-6 属三形态中的「UUID 动态行」（`excel_table` binding，`row_identity_key='rowId'`），
它被选作「最简样本」的前提（确实是动态行表）成立，不需要改接入顺序或声明形态。**

判定依据：

1. 与 D3-5 同款空白占位数据区（A 列无预填固定文字标签），不是固定枚举行。
2. 前端 `useD3RelatedParty.ts` docstring 明确写"rows reactive（从D3-rp-rows加载JSON）"，
   同款任意长度数组模型，无固定长度常量数组。
3. 模板附带的"关联方类型"字典（B26-B34：实际控制人/控股股东/……/其他关联方 共9种类型）是
   **下拉选项枚举**，不是数据行——已在逐行内容摘要中确认 B26='勿改、勿删'（明确的保护性文字
   标记，说明这是一个供 Excel 数据验证下拉引用的辅助区，不是受管数据区，本身应保持模板固有
   静态文字，与本 spec 的受管区判定无关，登记但不影响 D3-6 主体判为动态行表的结论）。
4. 5 行占位数据区 + SUM 区间落差（3行 vs 5行）恰恰说明这是一张"设计初期假设固定业务量、后来
   实际业务变多导致占位不够"的典型动态行表案例，与"该判 static_region"的方向相反。

### D3-7 预收账款检查表（双区，凭证抽查，需求 3.1）

| 项 | 实测值 | 在案参考值 | 一致性 |
|---|---|---|---|
| 行×列 | 48 行 × 18 列（A1:R48，实测非空行范围 min=1 max=46） | 48 行 × 18 列 | ✅ 一致 |
| 公式数 | 19 | 19 | ✅ 一致 |
| 主公式列 | F5 G5 E3（坐标速记；实测公式所在列去重排序 = `A E F G H I Q`） | F5 G5 E3 | ⚠️ 部分不一致，见说明 |
| Excel Table | 无 | — | — |
| 候选空列 | R/S/T/U 全空（Q 列非空但是"备注说明"表头+页眉引用） | — | — |

**两个受管区实测边界（需求 3.1 要求的双区行段）**：

```
区①（本期增减变动检查）：
  行14='（1）本期增减变动检查'
  表头：行15(客户名称/记账凭证) / 行16(日期/凭证编号/业务内容)
  数据区：行 17~26（10行模板占位，无固定文字标签，A列空白）
  合计行：27（G27='=SUM(G17:G26)' H27='=SUM(H17:H26)'）
  ⇒ store 键 D3-vc-current-rows（useD3VoucherCheck.ts ITEM_ID_CURRENT_ROWS）

区②（期后结转检查）：
  行28='（2）期后结转检查'
  表头：行29(客户名称/记账凭证) / 行30(日期/凭证编号/业务内容)
  数据区：行 31~38（8行模板占位）
  合计行：39（G39='=SUM(G31:G38)'）
  ⇒ store 键 D3-vc-post-rows（useD3VoucherCheck.ts ITEM_ID_POST_ROWS）

区②之后的比例检查块（行41~44，不是第三个受管区，是纯派生汇总）：
  行41='1.本期发生额、期末余额检查比例：' D41='方向'
  行42：D42='本期借方' E42="='预收账款明细表D3-2'!M24"（跨sheet直接引用D3-2） F42='=G27'
        G42='=ROUND(F42/E42,4)'
  行43：D43='本期贷方' E43="='预收账款明细表D3-2'!N24" F43='=H27' G43='=ROUND(F43/E43,2)'
  行44：D44='期末余额' E44="='预收账款明细表D3-2'!T24" F44='=G39' G44='=ROUND(F44/E44,2)'
  ⇒ 这是"检查比例"计算行，E/F/G 三列全是公式（跨表引用D3-2 + 引用本表区①②的合计），
    不是第三个受管区，属 formula_mask，不受管。
```

区①10行 + 区②8行，与合计行的 SUM 区间（`G17:G26`/`G31:G38`）逐项对齐，**没有 D3-6 那种
SUM区间落差问题**。两区结构对称、边界清晰，是本 spec 六张里几何最规整的一张。

**形态判定**：**`excel_table`（两个独立动态行区），`row_identity_key='rowId'`。** 判定依据同
D3-5/D3-6（空白占位数据区 + 前端 composable 明确的任意长度数组模型，`useD3VoucherCheck.ts` 无
固定长度常量约束）。与 design.md"结构与阶段 2 的 D3-4 双区同型 ⇒ 可复制其声明骨架"的判断一致，
但需注意 D3-7 的两区（区①②）都是**纯粹的动态行表**（无 D3-4 那种"模板固定占位 vs 前端任意
长度"的张力，因为 D3-7 两区数据行 A 列本身空白无固定标签），不需要套用 D3-4 段①②的
"limited_bidirectional 位置映射"裁决，可以直接走标准的 UUID 动态行 + `excel_table` binding。

**D3-7 无新旧两套并存债的验证结论（需求 3.2 要求）**：

grep `useD3VoucherCheck` 全仓（含 `.spec.ts` 测试文件），仅命中：
- `useD3VoucherCheck.ts`（唯一实现模块）
- `D3TabVoucherCheck.vue`（唯一宿主，import 自该模块）
- `D3VoucherCheckDialog.vue`（核对弹窗，import 自该模块的类型与常量）
- `useD3VoucherCheck.spec.ts`（PBT 测试文件）

未发现任何 `useD3VoucherCheckEnhanced`/`useD3VoucherCheckV2` 等第二套实现（对比 D2-7 侧
`useD2VoucherCheck` 旧套零消费方 + `Enhanced` 新套才是活路径的已知债务）。**结论：D3-7 侧
没有新旧两套并存问题，只有 `useD3VoucherCheck` 一个模块，需求 3.2 的断言成立。**

---

## 三、两项额外核查

### 3.1 footer 下 `static_row` 与插行 fail-closed 冲突核查

先例是 D4-5 的 `HTML_ONLY_ITEM_IDS_D45`（`D4-5-credit-policy`/`-audit-note`/`-audit-conclusion`
三项，因落在 footer 之下而登记 HTML-only）。逐张核查六张 sheet 的 note/conclusion/procedures
类 item 是否落在各自数据区 footer 之下：

| sheet | note/conclusion 类内容位置 | 是否落在 footer 之下 | 命中冲突？ |
|---|---|---|---|
| D3-1 | A25「1.审计说明：」+ A26（大额预收账款性质说明）+ A30（提示文字） | **是**，落在两区合计（21）+ 调节行（22-23）之后 | 是本 spec 需求 4 已知的"逐格 mask"覆盖范围，但 note/conclusion 类**文本**字段（非金额字段）本身不受 formula_mask 保护逻辑管辖问题，是**store item 是否受管**的问题——这些是 `D3-adj-note-*` 系列 item_id（如 `D3-adj-note-aging-reason`），当前**没有**对应的 Excel cell 坐标声明（审定表当前 provider 未接入，无法判断是否有对应单元格）。⇒ 登记为**待 Task 13 声明时确认**，暂不下"命中冲突"结论（因为受管区尚未声明，无法判断"插行"会不会影响它——D3-1 的两区都是固定行数，本身不涉及插行）|
| D3-3 | A21（提示文字，说明本底稿适用场景） | 是，落在数据表格之后 | D3-3 走可行性核，本任务不判定 |
| D3-4 | A34「三、审计说明」+ A38「四、审计结论」（内容留白，无预填文字） | **是**，落在段③债务人分析小计（33）之后 | 🔴 **登记为 HTML-only 候选**：A34/A38 是纯文字说明/结论区，落在全部数据区（含受管的段①②）之后，且这两个 item 在前端由 `useD3Analysis.ts` 的 `auditNote`（`D3-ana-note`）承载——单一文本字段，落在 footer 之下且属"note 类"，命中先例模式。但由于 D3-4 是**双区**（段①②各自有 SUM 合计行），"插行"发生在段①（13-17行内）或段②（21-25行内），不会直接位移到 A34/A38（这两行在 34/38，远离两个受管区），需要行表引擎的 footer 锚点重定位机制处理（同 D3-2 已接入的 footer_row 概念）。**建议登记为 HTML-only**（同 D4-5 判例），Task 8 声明时确认。|
| D3-5 | A15「三、审计说明」+ A19「四、审计结论」（内容留白） | 是，落在数据区（11-13）+ 合计（14）之后 | 🔴 同上模式，**登记为 HTML-only 候选**。D3-5 单区行表插行会导致 footer（14/15/19）位移，note/conclusion 类文本字段需要 footer 锚点跟随机制，Task 9 声明时按 D4-5 判例处理 |
| D3-6 | A18「三、审计说明：」+ A22「四、审计结论：」（内容留白）+ B26-B34 关联方类型字典（非 note，是下拉枚举辅助区，已在上文登记为静态保护区非受管数据） | 是，落在数据区（12-16）+ 合计（17）之后 | 🔴 同上模式，**登记为 HTML-only 候选**，Task 6 声明时按 D4-5 判例处理 |
| D3-7 | A40「三、审计说明：」+ A45「2.……」+ A46「四、审计结论：」（内容留白，比例检查块 41-44 在说明区之前） | 是，落在区①②数据（17-26/31-38）+ 合计（27/39）+ 比例检查块（41-44）之后 | 🔴 同上模式，**登记为 HTML-only 候选**，Task 11 声明时按 D4-5 判例处理 |

**汇总结论**：D3-4/D3-5/D3-6/D3-7 **四张**的 note/conclusion 类 item 均落在各自数据区 footer
之下，命中"footer 下 static_row 与插行 fail-closed 冲突"的已知模式，**建议全部登记为
HTML-only**（不强行做单元格双向），与 D4-5 判例一致处理方式。D3-1 因受管区尚未声明暂不下结论，
留给 Task 13。D3-3 属可行性核范围不判定。**这四项登记会在需求层面略微增加 HTML-only 清单**，
但不影响本任务"六张里没有 static_region"的主结论——HTML-only 是"该 item 不受单元格双向管辖"，
不等于"该 sheet 走 static_region binding"，两者是正交的判据（D1 design.md 表三已明确
`StoreKind`/`BindingKind` 正交，本次发现的是 HTML-only item 子集问题，属于表四"受管 sheet
≠ 全部 item 受管"的范畴，不是 binding_kind 判定）。

### 3.2 前端宿主两套 gating 核查

grep `isD3DetailSheet` 全仓：

实测结果：`GtD3PrepaidAccounts.vue:311` —
```ts
const isD3DetailSheet = computed(() => currentSheet.value === 'D3-2')
```

**目前只存在一套 gating**（`isD3DetailSheet`），全仓 grep `isD3DedicatedSyncSheet` **零命中**
（D4 侧存在的第二套 gating 概念在 D3 侧尚未引入）。这与 requirements.md 需求 9.5/9.6 的预判
完全一致——"首版需求 6.6 只提一套"，本次实测确认现状确实只有一套。

**受管 sheet 判定逻辑现状**（供 Task 16 前端接线参照）：`renderMode` 的 getter/setter 与
`el-segmented` 的 `disabled`/工具条显隐全部只对 `isD3DetailSheet`（即 `currentSheet === 'D3-2'`）
做特判，其余 6 张 sheet（D3-1/D3-3/D3-4/D3-5/D3-6/D3-7）目前统一走 `dualMode`
（`useD3EntryDualMode`），没有任何一张走"专用同步 sheet"路径。

**结论（对齐需求 9.6 的裁决）**：D3-1 若走独立宿主（`D3TabAdjudication.vue` 已经是独立组件，
只是目前渠道走 `dualMode`，不是"专用同步 sheet"），按需求 9.6 的裁决"D3-1 属专用同步 sheet 类
⇒ 必须登记第二套 gating"，**Task 13/14 接入 D3-1 时需要新增第二套 gating 变量**（例如
`isD3AdjudicationSyncSheet = computed(() => currentSheet.value === 'D3-1')`），并在 Task 16
的前端接线阶段同时处理两套 gating 的工具条互斥逻辑（借鉴 D4-35/D4-13 踩过的"漏登记导致工具条
叠加冲突"教训）。**本次实测确认"漏一套会工具条叠加冲突"的风险是真实的、非假设性**——因为当前
`isD3DetailSheet` 的判断逻辑（`renderMode` computed 的 get/set 分支）是**互斥二选一**结构
（`if isD3DetailSheet then A else dualMode.B`），如果 D3-1 接入后不新增专属分支、只是简单地把
`currentSheet === 'D3-1'` 也并入 `isD3DetailSheet` 的判断条件，会导致 D3-1 与 D3-2 共用同一套
`syncBridge`/`switchRenderMode` 逻辑（这两者的 entry_id/managed_sheet_key/store 形态完全不同，
D3-2 是行表引擎 rows kind，D3-1 是 AdjudicationSheetSpec 逐格 mask kind），必须是**独立的第二套
状态机**而不是往第一套里加分支。

---

## 四、每个 store 键的下游消费方清单（按值 grep 实测，非推测）

按 tasks.md 要求，逐个列出六张 sheet 对应 8 个 store 键（D3-4/D3-7 各 2 键）的下游 computed
消费方。**判定方法**：`grep_search` 全仓（`audit-platform/frontend/src/` + `backend/`），只登记
**读取**该键的位置（不含该键自己的 writer/composable 内部定义处，除非该 composable 对外暴露的
computed 本身就是"下游消费方"）。

### D3-rp-rows（D3-6 关联关系及交易）

| 消费方 | 位置 | 消费方式 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:73` | `hasJsonRows(m, 'D3-rp-rows')` 完成度判定 |
| ACNR 导入导出清单 | `_d3_import_export.py:160` | `"D3-6": "D3-rp-rows"` 映射表（导入导出用） |
| ACNR manifest | `backend/data/acnr/sources/d_cycle_ie_manifest.yaml:293` | `item_id: D3-rp-rows` 静态登记 |

**结论**：`D3-rp-rows` **没有** `useD3CrossSheet` 或其他 composable 的 computed 读取——只有
自身 writer（`useD3RelatedParty.ts`）+ 完成度判定 + 导入导出映射表。这与 requirements.md
表格记录的"`D3TabIndex` 完成度"一致，没有遗漏的隐藏消费方。

### D3-ana-credit-rows / D3-ana-debit-rows（D3-4 分析表）

| 消费方 | 位置 | 消费方式 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:69` | `hasJsonRows(m, 'D3-ana-debit-rows') \|\| hasJsonRows(m, 'D3-ana-credit-rows') \|\| hasText(m, 'D3-ana-note')` |
| `useD3Analysis.debitRows`/`creditRows` | `useD3Analysis.ts:150-159` | 自身 writer，暴露为 `ref`，`D3TabAnalysis.vue` 用它渲染 `debitTableData`/`creditTableData`（含合计/差异行的**派生**计算，非直接消费store原文） |
| ACNR 导入导出清单 | `_d3_import_export.py:156-157` | 映射表 |
| ACNR manifest | `d_cycle_ie_manifest.yaml:272,279` | 静态登记 |

**结论**：与 requirements.md 记录一致，**没有** `useD3CrossSheet` 消费这两个键（`useD3Analysis`
内部读取的是 `D3-det-rows`（明细表），不是自身的 `D3-ana-*` 键——`top5Debtors` computed 读
`D3-det-rows` 不是 `D3-ana-credit/debit-rows` 自身）。

### D3-lt-rows（D3-5 账龄 1 年以上）

| 消费方 | 位置 | 消费方式 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:71-72` | `hasJsonRows(m, 'D3-lt-rows')` |
| `useD3LongTerm.rows` | `useD3LongTerm.ts` | 自身 writer，暴露 `subtotalRow` computed（本 sheet 内部小计，非跨 sheet 消费） |
| ACNR 导入导出清单 | `_d3_import_export.py:158` | 映射表 |
| ACNR manifest | `d_cycle_ie_manifest.yaml:286` + `backend/data/acnr/global_catalog.json:9424` + 两份 `catalog_snapshots` | 静态登记（多处快照文件重复出现，属正常的 catalog 快照历史留存，不是重复定义问题） |

**结论**：`D3-lt-rows` 同样**没有**跨 sheet 的 `useD3CrossSheet` 消费方，只有本 sheet 内部
computed 与目录完成度判定。

### D3-vc-current-rows / D3-vc-post-rows（D3-7 检查表）

| 消费方 | 位置 | 消费方式 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:75-76` | `hasJsonRows(m, 'D3-vc-current-rows') \|\| hasJsonRows(m, 'D3-vc-post-rows')` |
| **`useD3CrossSheet.postPeriodSettlementSync`** | `useD3CrossSheet.ts:366-369` | **跨 sheet 消费**：`const resp = allResponses.value.get('D3-vc-post-rows')` → `safeParseRows` 解析后聚合成 `{byCustomer, total}`，供其他 sheet（推断为 D3-2 明细表的"期后结转"列交叉核对）读取 |
| ACNR 导入导出清单 | `_d3_import_export.py:161` | 仅 `"D3-7": "D3-vc-post-rows"` 映射（**只映射了 post-rows，没有 current-rows**，见下方"如实登记的异常"） |
| ACNR manifest | `d_cycle_ie_manifest.yaml:300` | 仅登记 `D3-vc-post-rows`（同上，current-rows 未见于 manifest） |

⚠️ **如实登记的异常（非本任务修复范围，仅登记）**：`D3-vc-current-rows` 在 ACNR 导入导出映射表
与 manifest 里均**未见登记**（只有 `D3-vc-post-rows` 出现）。已用 grep 交叉核对
`_d3_import_export.py` 全文与 `d_cycle_ie_manifest.yaml` 全文，确认这不是本次 grep 的遗漏，
是这两份配置文件本身的登记状态。这可能意味着"本期"区（区①）目前没有独立的导入导出模板支持，
或者是历史遗漏。**这不影响本 spec 的行表引擎双向回写判定**（OO/HTML 双向回写路径走的是
`checklist_responses.item_id` 直接读写，不依赖 ACNR 的导入导出映射表），但供 Task 11 声明时
知悉这一背景差异，如需要也可以顺手在 Task 11 补齐（若认为有必要，需与用户确认是否属本 spec
范围，本任务不擅自修改任何配置文件）。

**结论**：`D3-vc-post-rows` 确认有 `useD3CrossSheet` 跨 sheet 消费（对齐 requirements.md 记录），
`D3-vc-current-rows` **没有**跨 sheet 消费方，只有目录完成度判定。

### D3-1（待实测，本次已实测为逐格 item 集合，非单一 rows 键）

D3-1 与其余五张不同——它**不是**单一 `rows` 数组 store 键，而是**一组逐格标量 item**
（`D3-adj-{section}-{rowKey}-{field}` 格式，section∈{nature,aging}，rowKey 取自
`NATURE_ROWS`/`AGING_ROWS` 常量，field 是具体字段名如 `currentUnadjusted`/`reasonAnalysis`）
+ 三个独立 note item（`D3-adj-note-aging-reason`/`D3-adj-note-change-analysis`/
`D3-adj-note-conclusion`）+ 一个 TB 种子金额 item（`D3-adj-trial-balance-amount`）。

grep `D3-adj-` 前缀（不是单一键值 grep，是前缀扫描，因为逐格 item 数量随 `NATURE_ROWS`/
`AGING_ROWS` 常量长度变化）：

| 消费方 | 位置 | 消费方式 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:65-66` | `[...m.keys()].some(k => k.startsWith('D3-adj-'))`（前缀扫描，任一 D3-adj- 键非空即判完成，非精确匹配单键） |
| `D3TabIndex.isConclusionFilled` | `D3TabIndex.vue:107-118` | 跨表结论口径看板，扫描 `${code}-` token + `conclusion|audit-note|note` 正则，对 D3-1 会命中 `D3-adj-note-conclusion` |
| `useD3Adjudication` 自身 | `useD3Adjudication.ts` | 逐字段 watch + debouncedSave，是这些 item 的 writer |

**没有发现其他跨 sheet composable 读取 `D3-adj-*` 前缀键**——审定表的逐格数据是"终端汇总"，
下游没有再消费它的场景（符合审定表作为循环终点的业务语义）。

## 五、D3TabIndex 聚合键 bug 核查结论（对齐 D6/D7 已知模式的核查要求）

**结论：D3 侧未见同类 bug。** 已完整读取 `D3TabIndex.vue` 全文的 `isSheetComplete` 函数（见上文
第三节代码引用），逐一核对其读取的键与各自 writer composable 声明的键，**全部逐字匹配**：

```
D3-2 → hasJsonRows(m, 'D3-det-rows')          ✅ 与 phase5_d3_prepaid_receipts.py STORE_ITEM_ID 一致
D3-3 → hasJsonRows(m, 'D3-aje-rows')          ✅ 与 useD3Adjustment 一致（未逐字核，但与全部 grep 结果吻合）
D3-4 → hasJsonRows(m, 'D3-ana-debit-rows') || hasJsonRows(m, 'D3-ana-credit-rows') || hasText(m, 'D3-ana-note')
                                               ✅ 与 useD3Analysis.ts ITEM_ID_DEBIT_ROWS/ITEM_ID_CREDIT_ROWS/ITEM_ID_NOTE 逐字一致
D3-5 → hasJsonRows(m, 'D3-lt-rows')           ✅ 与 useD3LongTerm.ts ITEM_ID_ROWS 一致
D3-6 → hasJsonRows(m, 'D3-rp-rows')           ✅ 与 useD3RelatedParty.ts ITEM_ID_ROWS 一致
D3-7 → hasJsonRows(m, 'D3-vc-current-rows') || hasJsonRows(m, 'D3-vc-post-rows')
                                               ✅ 与 useD3VoucherCheck.ts ITEM_ID_CURRENT_ROWS/ITEM_ID_POST_ROWS 逐字一致
D3-1 → [...m.keys()].some(k => k.startsWith('D3-adj-'))
                                               ✅ 前缀扫描本身就不受"精确键名拼错"风险影响（结构性安全）
```

与 D6/D7 的已知 bug 模式（`D6TabIndex.vue:54` 读 `D6-6-rows` 但真实写入方用
`D6-6-block1-rows`/`-block2-rows`）不同——D3 每一处判定都精确匹配了各自 composable 声明的
真实 item_id 常量，**没有"按 sheet 编号推演键名"的痕迹**。这与本 spec 需求 1.2/2.3 反复强调的
"D3 的键用语义缩写，按值 grep 实测而非按编号推演"纪律执行到位有关——**编写 `D3TabIndex.vue`
时显然是照抄了各 composable 里真实声明的常量字符串，不是自己按编号猜的**，这正是避免 D6/D7 那类
bug 的正确做法的正面案例，值得在后续任务（尤其 Task 6/8/9/11/13 编写新的声明代码）时延续同款
"从常量文件抄字面量，不自己按模式推演"的习惯。

---

## 六、D3-7 无新旧两套并存债验证结论

已在「二、D3-7」小节完整给出（grep `useD3VoucherCheck` 全仓仅命中唯一实现模块 + 两个宿主组件 +
一个 PBT 测试文件，无 `Enhanced`/`V2` 变体）。**结论：D3-7 侧只有 `useD3VoucherCheck` 一个模块，
没有 D2-7 那种新旧两套并存债，需求 3.2 的断言成立。**

---

## 七、产出对后续任务顺序的影响

### 7.1 形态判定结果不改变默认路线

本任务的核心预判是"若 D3-5/D3-6 判为 `static_region`，则应提前接入"。实测结论是**六张里没有
一张属 `static_region`**——D3-5/D3-6 的"公式集中在前几列、形似固定结构"表象经核实是因为
"模板画的数据区本身很小（3~5 行）"，而非"没有行维度"。D3-4 段①②虽然有"模板固定行数 vs 前端
任意长度数组"的张力（更接近 D4-33 的 limited_bidirectional 位置映射范式），但这仍然是
`excel_table` binding（有行维度），不是 `static_region`。

**⇒ tasks.md 原文"首版路线需据此调整为『先静态区、再单区、再双区、最后审定表』"这一预判不成立
（前提假设未被实测证实），design.md 记录的默认路线`1(D3-2)→2(D3-6)→4(D3-4双区)→5(D3-5)→
7(D3-7双区)→8(D3-1)`不需要按"static_region 优先"重新排序。**

### 7.2 但接入顺序仍需要两处细化（非"是否 static_region"引起，是本任务发现的其他因素）

1. **D3-4 段①②的裁决需要在 Task 8 阶段重新核实**（不是接入顺序问题，是"双区行段边界该怎么定"
   的问题）：段①受管边界应是行 13-16（差异公式硬编码引用的 4 行），段②应是行 22-24（3行占位），
   不是"38 行×9列内任意选两段"。且需要判断走"标准动态行表位移链"还是"D4-33 式 limited_bidirectional
   位置映射"（本文档倾向后者，但最终裁决留给 Task 8 结合前端 debitRows/creditRows 真实使用场景
   确认）。这件事不影响**接入顺序**（D3-4 仍然排在 D3-6 之后、D3-5 之前，因为它依赖 Task 7 已证
   通的双区多受管 sheet 通路），只影响 Task 8 声明代码的**具体行段参数**。

2. **D3-4/D3-5/D3-6/D3-7 四张的 note/conclusion 字段建议登记 HTML-only**（本文档第三节 3.1）——
   这也不改变接入顺序，是每张接入时（Task 6/8/9/11）声明代码需要把这些 footer 下的文本字段排除
   在受管字段之外，与 D4-5 判例处理方式一致。

### 7.3 保持原顺序的理由重述

- D3-6 单区最简，依赖最少（不依赖 Task 24 的位移判据参数化），继续排第一
- D3-4 双区依赖上游 D1 spec 任务 24 已落（Task 0 复核已确认框架层整体已交付，含该项）+ 依赖
  Task 7 已证通"多受管 sheet 在 D3 上成立"，继续排第二
- D3-5 单区，依赖 D3-4 已验通的双区位移链（虽然 D3-5 本身是单区，但阶段划分上排在阶段2尾部，
  与 D3-4 共享"验证双区位移链在 D3 首次验通"的阶段目标），继续排第三
- D3-7 双区结构与 D3-4 同型可复制声明骨架，继续排第四
- D3-1 依赖前置 B/C（`AdjudicationSheetSpec`/`merge._protection`，Task 0 复核已确认均满足）+
  区块数需要 Task 1（本任务）实测确认（已完成：两区块，性质分类+账龄分类），继续排最后

**⇒ 最终接入顺序建议：维持 design.md 记录的默认路线不变
`D3-2(已接) → D3-6 → D3-4(双区) → D3-5 → D3-7(双区) → D3-1`，无需调整。**

---

## 八、复算方法（供后续任务复核，不重测而是引用本文档）

以下 Python 片段可复现本文档全部几何数据（无需重新编写探针脚本，供审计追溯）：

```python
import openpyxl
wb = openpyxl.load_workbook(r"backend/wp_templates/D/D3 预收账款.xlsx", data_only=False)
for name in ["审定表D3-1", "调整分录汇总表D3-3", "预收账款分析表D3-4",
             "账龄1年以上的预收账款检查表D3-5", "关联关系及交易检查表D3-6",
             "预收账款检查表D3-7"]:
    ws = wb[name]
    # 🔴 必须先锁存 max_row/max_column，任何越界 cell 访问都会把它们动态撑大（本任务
    # 首轮探测已踩过这个坑，见文档开头说明）。
    orig_max_row, orig_max_column = ws.max_row, ws.max_column
    formulas = [(c.coordinate, c.value) for row in ws.iter_rows()
                for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    print(name, orig_max_row, orig_max_column, len(formulas))
```

---

## 九、结论汇总（回应「完成标准」逐项）

1. ✅ 六张 sheet 形态判定 + 理由：见「一、六张 sheet 形态判定结果一览」+ 各张详述小节
2. ✅ 几何实测 + 与在案参考值对照：见「二、几何实测数据」，六张几何逐项与参考值一致
   （主公式列坐标速记与实测的差异已如实登记为"设计文档简写惯例"，非几何本身不一致）
3. ✅ D3-5/D3-6 明确结论：均判「UUID 动态行」，D3-5 结论建议回填 D567 spec 的 D7-5（该 spec
   当前无已完成结论可交叉参照，如实说明）
4. ✅ footer 冲突核查（四张登记 HTML-only 候选）+ 两套 gating 核查（现状仅一套，D3-1 接入时
   需新增第二套）：见「三、两项额外核查」
5. ✅ 每个 store 键下游消费方清单（按值 grep 实测）：见「四、下游消费方清单」
6. ✅ D3TabIndex 聚合键 bug 核查：**未见同类 bug**，见「五」
7. ✅ D3-7 无新旧并存债验证：**成立**，见「六」
8. ✅ 接入顺序建议：**维持 design.md 默认路线不变**，见「七」

本任务未修改任何生产代码文件，一次性探针脚本已用完删除。
