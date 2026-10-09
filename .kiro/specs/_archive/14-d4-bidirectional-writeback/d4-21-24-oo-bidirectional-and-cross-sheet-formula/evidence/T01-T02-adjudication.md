# D4-21~24 Wave 1 模板裁决证据（Task 1.1 / 1.2，Requirement 1，DEC1/DEC2）

> 只读核定，无代码变更。逐格证据见同目录 `T01-adjudication-census.json`
> （`d4_21_24_wave1_adjudication.py` 产出，openpyxl `data_only=False` + 运行时 finder 定位）。
> mapping_digest（绑定 sheet 名/几何/表头/公式列/O列保留值/导航引用）：
> `57a55ec323e5881e78a254d29d7e2e405f714588a9253b39584e6f547e37c4a2`

## 运行时权威 workbook 裁决（DEC1，关键）

`find_template_file('D4-21'..'D4-24')` 对裸 wp_code 命中两份**独立 IPO 单册**
（`D/D4-21…（Leap-常规程序）.xlsx`、`D/D4-22至D4-32…IPO…舞弊应对.xlsx`）。**但不走它们**：
D4-21~24 的前端同步宿主在 `workpaperSyncManifest.generated.ts` 里全部
`independentEntry:false` / `migrationState:parent_duplicate` /
`parentEntryId:"xlsx/gt-d4-operating-revenue"`。该父 entry 的运行时权威 workbook =
**`D/D4 收入底稿.xlsx`**，openpyxl 实测该合册**已包含** D4-21~24 五张 sheet，且几何/表头/
公式/O列/导航引用与独立单册**逐字节一致**（census `mapping_digest=57a55ec3…` 双跑相同）。

**裁决**：双向 descriptor 挂**合册 `D/D4 收入底稿.xlsx`**（与 D4-2/3/5 同 template blob /
同 entry `xlsx/gt-d4-operating-revenue`），作为该 entry 的追加受管 sheet；**不**为 D4-21~24
新建独立 entry（那属 d_cycle_migration 域）。独立 IPO 单册仅作参考副本，不接入运行时。

（census 的 `workbook_adjudication.finder_standalone_hits` 记录了 finder 命中的独立册路径，
证明「不走独立册」是有意裁决而非漏看。）

---

## 逐表几何与公式（实测）

### D4-21 关联方销售情况及价格分析D4-21（A1:R49）
- 表头行 **15**；数据区 **16–30**（15 行）；无「合计」footer；A31「三、审计说明」/A34「四、审计结论」是文本带，不入数据区。
- 受管字段 **12 列**：A 关联方客户名称 / B 关联关系 / C 产品名称 / D 销售数量 / E 销售额 / F 销售额占同类产品比例 / G 平均单价 / H 非关联方销售平均单价 / J 可比公允价格 / L 上年度销售额占比 / M 上年度销售平均单价 / N 备注（14 列 A–N 扣除 I/K 差异率 = 12）。
- **FORMULA_MASK = I、K**：`I=(G-H)/H`、`K=(G-J)/J`（差异率，内部 OO 算术，15 行逐行）。非受管，projection 不得写入。
- **O 列保留枚举**（O16–O24，9 行）：`勿删、勿改`（O16 指示标记）/ `实际控制人` / `控股股东` / `控股股东、实际控制人的附属企业` / `持有5%以上股份的法人或其他组织` / `联营企业` / `合营企业` / `董高监等关键管理人员` / `其他关联方`。这是**静态关联关系图例**，与行数据无关，须逐字保留。
- **UUID 列**：数据止于 N，O 为图例，故 UUID 用 **P 列**（O 之外的空列，DEC2）。

### D4-22A 程序表D4-22A（A1:K37）
- 表头行 15/16（两级），程序行 **17–34**（18 条编号程序，序号 1–18）；A35「提示」文本。
- 列：序号 / 对应 Leap 程序 / 审计程序 / 程序分类 / 财务报表认定（E–I 打 √）/ 底稿索引号（J，含导航 refs：F2-63/D4-22/D4-23、D4-24、D4-26、D4-27… 等）。
- **无金额、无行内业务公式**（仅 row3/4 `=底稿目录` 外链，属抬头非数据）。程序内容是固定清单，无可稳定合并的货币行身份。

### D4-22 重要指标分析表D4-22（A1:H30）
- 表头行 **11**；固定指标行 **12–23**（12 行命名指标：年度预算 / 主营业务收入 / 销售人员数量 / … / 运输费用/营业收入）；无 footer；A24/A28 文本带。
- 列：A 指标名称（fixed 行身份）/ B 本期 / C 上期 / **D 同行业公司1 / E 同行业公司2 / F 同行业公司3 / G ……**（横向同业列，可扩）/ H 合理性分析。
- 数据区无内部公式。同业列 → DEC3 `{slot}_{seq}` 稳定键动态展开（禁写死 3 家）。

### D4-23 收入与开具发票金额比较分析D4-23（A1:M32）
- **两级表头 10+11**（A10「月份」跨 A10:A11；B10「本期账面确认收入」跨 B:D；E10「本期开具发票的金额」跨 E:K）；数据区 **12–23**（1月–12月，月份天然键）；footer **24「合计」**（B24…J24 `=SUM(x12:x23)`）。
- **FORMULA_MASK = D、I、J**：`D=B+C`（营业收入合计）、`I=E+G`（申报合计）、`J=D-I`（差异），内部算术，逐行 + footer SUM。
- 受管字段：A 月份（key）/ B 主营业务收入 / C 其他业务收入 / E 增值税发票金额 / F 防伪税控份数 / G 普通发票金额 / H 普通发票份数 / K 索引号（导航）。

### D4-24 第三方回款检查D4-24（A1:N27）
- 表头行 **14**；数据区 **15–22**（8 行空模板行）；无 footer；A23「三、审计说明」+ A24「第三方回函检查明细详见银行流水双向核对表<E1-31>、应收账款检查表<D2-7>」+ A27「四、审计结论」。
- 列：A 序号 / B 客户名称 / C 本年度销售金额 / D 期末应收账款余额 / E 本年度第三方回款金额 / F 回款方名称 / G 回款原因 / H 回款方与客户关系 / I 回款方与被审计单位关系 / **J 是否有代付协议 / K 是否函证**（枚举）/ L 合理性分析 / M 索引。
- **导航引用**：A24 含 `<E1-31>`、`<D2-7>`（Req 5.1「D4-24 的 D2 引用先做语义裁决」——见下）。
- 无内部业务公式。UUID 用 N/O 之后空列（数据止于 M）。

---

## Task 1.2 裁决结论

| wp_code | 裁决 | 依据 |
|---|---|---|
| **D4-21** | `full_bidirectional` | 稳定行身份（每行一关联方×产品）；11 受管列；I/K 内部公式入 mask；O 列图例保留、UUID 用 P。 |
| **D4-22** | `full_bidirectional`（同业列动态） | 固定指标行身份（A 列指标名称，12 行）；同业列横向可扩，用 `{slot}_{seq}`；无内部公式。 |
| **D4-23** | `full_bidirectional` | 月份天然键（12 行）；两级表头；D/I/J + footer SUM 入 mask；结构稳定。 |
| **D4-24** | `full_bidirectional` | 每行一客户×第三方回款；枚举列 J/K；无内部公式；D2/E1 导航引用先裁决后接入。 |
| **D4-22A** | `single_html` | **程序表**：无金额、无行内业务公式、无可稳定合并的货币行身份，程序内容为固定清单（DEC + Req 1.2 / 2.4）。保持结构化视图 + 导航 refs（J 列索引号），**不扩双向代码、不伪造在线编辑**。 |

### D4-24 D2/E1 导航引用语义裁决（Req 5.1）
- A24 文本 `<D2-7>` = 应收账款检查表；`<E1-31>` = 银行流水双向核对表。二者是**用户导航关系**（「明细详见」），非公式取数依赖。
- 裁决：作为 `cross_wp_references` 的**导航条目**登记（relation=`detail_reference`，方向 D4-24 → D2-7 / D4-24 → E1-31），GtIndexChip 可跳转；**只增不删**既有关系；不进入 `wp_formula` refs（公式 refs 与导航 refs 分离，DEC6）。

---

## 与已有基础设施的接线口径（供 Wave 2+ 落地）
- 双向：clone `phase5_d4_revenue_detail.py` 的 descriptor / contract / row-identity / FORMULA_MASK / store-projection 全链路；OO/HTML 提交统一走 `ContentMutationService.commit` / `commit_html_projection`。
- 公式：`WpFormulaService.save`（versioned effective definition，refs 走 ACNR，definition_hash 含 params）；执行/失败隔离/stale 走 `formula_runtime`。D4-21 取 D4-1 审定营业收入用 four_table `report_line_accounts`（IS-001 / 6001）。
- 导入导出：`useD4ImportExport`（union 已含 D4-21/23/24，**缺 D4-22 需补**）。
