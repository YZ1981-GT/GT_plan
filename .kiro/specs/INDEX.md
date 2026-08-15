# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-08-14
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active **8**（2026-08-14 行首锚定正则 `^\s*-\s\[([ x~-])\]\s+\d+\.` 实扫得 9，本轮归档 `frontend-excel-io-single-entry-convergence` 后为 8；**8 个目录全部带 tasks.md、无空壳**）/ Archived **551**（2026-08-12 按 `_archive/*/*` 一级子目录实扫 550 + 本轮 1，含 6 个仅剩 evidence 无三件套的历史残留目录）

> **2026-08-14 实扫结果（9 个目录逐一，供下一轮比对）**：
> `e-cycle-…completion` 24/24 · ~~`frontend-excel-io-single-entry-convergence` 15/18~~（**本轮已归档**，终态 15/18 + `## Notes` 写明 3 个 `[-]` 的阻塞原因）·
> `g7-column-alignment-and-extraction-closure` **24/24（2026-08-12 全交付，待归档）** · `i-cycle-…closure` 18/24 ·
> `k-cycle-…closure` 14/25 · `l-cycle-…completion` 3/26 ·
> `procedure-trim-report-line-account-resolution` 0/16 ·
> `workpaper-import-export-lifecycle-closure` 24/25 · `x3-adjustment-entry-import-export` 25/49
>
> 🔴 **下表有两行的进度数已过时**（本轮只更新了 `frontend-excel-io-*` 一行，其余属并发
> 会话在办、未擅自改其详情以免与正在写的内容打架）：`workpaper-import-export-lifecycle-closure`
> 表内记 3/25 而实扫 **24/25**；`e-cycle-…completion` 已 **24/24 全完成**（可评估归档）。
> 另 `x3-adjustment-entry-import-export`（25/49）是并发会话新建，**下表尚无该行** ——
> Active 从 8 变 9 即因它。
> 🔴 **2026-08-12 实扫修正了表头三处过时记载**：①Active 写 6 而真实是 7；②「另有 3 个无 tasks.md 的空壳目录」已不成立 —— 其中两个（`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening`）早在 2026-08-05 清理入归档区，而 `workpaper-import-export-lifecycle-closure` **有 tasks.md 且进度 3/25**，把它记成空壳会让一个在办 spec 从索引上消失；③Archived 549 → 550（本轮归档 `procedure-trimming-and-delegation-intelligence`）。再次印证本文件 §四 的「凭印象禁令」：完成度与数量一律实扫，别信上一轮写下的数。
**最高迁移**：**V146**（`procedure_instance_suggestion_state`，并发会话 `procedure-trimming-*` 所加；本 spec 贡献 **V145** `report_config` 双族使用权资产/租赁负债。以磁盘 `backend/migrations/V*.sql` 实扫为准，`R1xx__` 是配对回滚脚本非同号冲突）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs

| spec | 进度 | 一句话 |
|------|------|--------|
| `e-cycle-extraction-formula-and-disclosure-completion` | 21/24（`[-]`1 / `[~]`2） | E 类（E0/E1）取数/公式/披露收口。账户级取数走 `tb_aux_balance` 银行账户维度（客户 1002 不分户，叶子恒 1 行） |
| `i-cycle-extraction-formula-and-disclosure-closure` | 9/25 | I 类（无形资产/商誉/长期待摊）取数/公式/披露收口 |
| `k-cycle-extraction-formula-and-disclosure-closure` | 5/25 | K 类取数公式与披露收口 |
| `g7-column-alignment-and-extraction-closure` | **24/24（全交付 2026-08-12）** | G7 长期股权投资列结构对齐与取数闭合。补上「源 xlsx ↔ 模板 seed ↔ 运行时载荷」三向锁死的第三条边（56 个偏差点 → 0），并新增**第四边：渲染层**（浏览器实测发现两级表头 **0/38 张从未渲染** —— 模型的 `group` 是 additive 死代码，任何 `.vue` 零引用；修复后 20 张）。另修掉平台级假绿「`_note_structure_kit` 的 `--check` 弱于 `--dry-run`」（24 个幂等脚本共用）。🔴 **10 个正式产物仍 `??` 未跟踪**（含 facts JSON 与全部守卫本体）⇒ CI job 在干净 checkout 下必挂，需先 `git add` |
| `l-cycle-extraction-formula-and-disclosure-completion` | 3/26 | L 类（借款/应付债券）取数公式与披露收口 |
| `workpaper-import-export-lifecycle-closure` | 3/25 | 底稿导入导出生命周期收口（**此前被表头误记为「无 tasks.md 的空壳」，2026-08-12 实扫纠正**） |
| ~~`frontend-excel-io-single-entry-convergence`~~ | **已归档** | → `_archive/06-engineering-governance/`（2026-08-14 收敛完成 46 → 0，commit `f049a11f`）。**登记的 4 处既有缺陷已处置：2 修 / 1 撤回误判 / 1 整链删除**（`batchExport.ts` 孤儿链「合并导出」用户不可达，用户裁决删）。动因是 `xlsx@0.18.5` 带两个永不会修的 CVE（SheetJS 已撤出 npm），25 处读上传文件各是独立攻击面。性质为**行为等价重构**，迁移默认姿势是三个显式关闭（`applyStyles`/`includeNoteRow` 两个默认 true 会给 42 个原本无样式的产物加三线表、并在表头前插行）。<br>**两处立项假设被实测推翻**：B5 不是换引擎批而是「入口收两个引擎」（换 SheetJS 要对齐五处语义差异且写不出冻结窗格）；B3 不能用 `parseFile` 而须另开低层薄封装。<br>**顺带修掉三个既有缺陷**：`parseFile` 列索引错位 · 样式模板写出非法 OOXML `vertical:'middle'` 致 openpyxl 打不开文件（影响 12 个走默认样式的调用点，后端 674 处 openpyxl 连带）· 本轮改造引入的括号不配平致 Vite 500（`get_diagnostics`/vitest/变异三层全绿，只有浏览器暴露 ⇒ 已固化成 `check_vite_transform.mjs` 守卫）。<br>**提交前发现的清单漏记（最贵一课）**：B2 那批 13 个 confirmation 文件只写在基线 `note` 的自然语言里、`files` 数组为空 ⇒ 按 files 精确 stage 的脚本漏掉它们（远端仍带裸 import，CI 必红）+ Vite 编译扫描只覆盖 33/46 + 进度失真。**此前所有守卫都在验「代码符不符合清单」，没有一条验「清单本身完不完整」** ⇒ 补 R6.7 / Property 38 + 2 条守卫 + 3 条变异（M18/M19/M20 全 RED）。同域次级坑两个：对账脚本不剥注释会漏检 `import(/* @vite-ignore */ 'exceljs')`；「数量相等 ≠ 集合相等」（曾出现基线 46 / HEAD 46 但各差一个元素）。<br>**终态**：守卫 8 文件 **119** 例全绿 · 变异 **18/18** 全 RED（静态自检 18/18）· Vite 编译 **46/46** · 三件套机器校验零 warning。剩 3 个 `[-]` 均在 tasks.md `## Notes` 写明阻塞原因：Task 2（迁移前快照窗口已关闭，事后补抓＝把错值当基线）· Task 16（变异 18/38 Property，缺口三类各有判据形态原因）· Task 18（B4 需多公司合并数据、C24-4 空态不渲染导出入口） |
| `procedure-trim-report-line-account-resolution` | 0/16 | **2026-08-12 新建**。裁剪判据的科目金额定位从「程序名 ↔ 科目名子串匹配」改为「程序 → 报表行 → 报表公式 → 金额」。立项实证：E 循环 5 条程序名全是「货币资金 …」而 `trial_balance` 只有明细「其他货币资金」(1012)/「银行存款」(1002) ⇒ 单向子串匹配全部落空 ⇒ 重要性判据（决策内核档 7/8）整体空转。净新增仅 2 个后端模块 + 1 处前端优先级调整 —— 三段映射的每一段都已有生产真源（`four_table/*_cycle_specs.py` 的 `row_code` 声明 · `report_config.formula` · `ReportFormulaParser`），索引只做 dispatch、**零 `row_code` 字面量** |

> 🔴 上表 7 个 spec 中前 6 个由**并发会话**推进（tasks.md mtime 秒/分钟级刷新）。
> 跨会话协作时不要并行推进同一 spec（memory 已实证并发会话会互相回退同一文件）。
> 🔴 **判 Active 数量一律行首锚定正则实扫 `.kiro/specs/*/tasks.md`，别信本表旧数** ——
> 2026-08-10 实扫发现表头写「Active 4」而真实是 6 个带 tasks.md 的活 spec
> （`i-cycle` / `k-cycle` / `l-cycle` 三个漏登记）。
> `f0`(144/144) / `parent-company`(18/18) / `report-config`(12/12) /
> `sampling-evaluation-and-governance-closure`(19/19) / `k0`(18/18) /
> **`sampling-compliance-closure`(25/25)** 已于 2026-08-08 归档（见 §二）；
> **`soe-listed-note-conversion-correctness`(19/19)** 已于 2026-08-09 归档。
> **`note-template-columns-and-legacy-snapshot-closure`(23/23)** 已于 2026-08-09 归档（见 §二）。
> **`h-cycle-extraction-formula-and-disclosure-completion`(18/18)** 已于 2026-08-10 归档（见 §二）。
> **`procedure-trimming-and-delegation-intelligence`(26/26)** 已于 2026-08-12 归档（见 §二）。

**2026-08-12 归档（1 个，→ `05-business-features`，与前身 `procedure-applicability-trimming` /
`procedure-delegation-notification` 同分类）**：

`procedure-trimming-and-delegation-intelligence`(**26/26**) —— 程序裁剪三维判据（风险评估 →
重要性 → 数据存在性）+ 人员委派智能化。把裁剪从「单维（科目有无余额）」升级为九档短路的
决策内核（`procedureTrimDecision.decideTrim`）+ 汇总闸（`trimAggregateGate`）+ 完整性豁免
（`completenessExemption`，11 个循环各带 ≥20 字 rationale）+ 建议态/确认/驳回三态 +
理由码真源统一（`TrimReasonCode` 扩 4 值，canonical trim entry additive 扩 `reason_code?`）+
裁剪充分性复核视图 + 附注反向联动（复用 `disclosure_notes.is_empty`，不新建第二套不适用字段）+
委派建议分配算法（按风险降序 × 加权负载最小）。
**Task 26 浏览器实测收口（2026-08-12）**：只读部分 5 passed / 写库项两轮各 2 passed。
**核心链路在真实库首次完整跑通** —— 用 Task 14 的覆盖开关把 D 循环改判为完整性不敏感后，
D3 预收账款 13,656,018.02 < 实际执行重要性 26,104,487.00 ⇒ 档 8 产出 `below_materiality`，
逐条确认后落库 `suggestion_state={'reason_code':'below_materiality'}`（`jsonb_typeof=object`，
未踩「写成 JSON 字符串标量」那个坑）+ 含判据数值的 `skip_reason` 并列同事务；汇总闸真算出
「建议裁剪科目 1 个（已按科目去重），金额合计 13,656,018.02 元，低于实际执行重要性
26,104,487.00 元」。**顺带修掉一个真产品缺陷**：Task 14 的写入端点
`PUT /procedure-trim/completeness-scope` 在真实库上**恒 500** —— `CAST(:ts AS timestamptz)`
配 `now.isoformat()` 触发 asyncpg `DataError`（**UUID 与 timestamptz 的正确写法方向相反**：
UUID 是 `CAST + str`，timestamptz 是 `CAST + datetime 对象`）；而该模块 112 例守卫
（56 后端 + 56 前端）+ 14/14 变异全绿，因为写入 9 例全走替身而**替身不做参数编码** ⇒
补 3 条守卫（连库真写往返 INSERT/UPDATE/list/DELETE 末尾 rollback · 反向自检钉死驱动行为事实 ·
源码级），变异检验双双 RED。**实测 5 条失败全是判据缺陷无一产品缺陷**（按文案猜按钮 ——
真实是「保存覆盖」/「撤销覆盖」· `.el-message--success` 被前置步骤自己满足 ⇒ 改用网络请求作硬判据 ·
复核端点漏 cycle 段 · `locator.click()` 命中假阳性 ⇒ 改 `page.mouse.click` 真实输入事件 ·
交叉核实查询漏 `is_deleted` 过滤差点误报漂移）。数据按基线复原并经 postgres 只读交叉核实
（已裁剪 0 / `suggestion_state` 0 / `B50-T3-*` 0 行 / `row_tasks` 27 全部回到基线）。
**遗留议题已立后继 spec** `procedure-trim-report-line-account-resolution`（见 §一）。

**2026-08-10 归档（1 个，→ `08-disclosure-notes`，与前序 `h-cycle-four-table-extraction-and-account-mapping` /
`h-cycle-legacy-cleanup-and-platform-hygiene` 同分类）**：

`h-cycle-extraction-formula-and-disclosure-completion`(18/18) —— H 类（H1~H10）取数 / 公式 /
披露收口。**双族并存取数**（新族 `1651`/`1652` 使用权资产与旧族 `1641`/`1642` 在同一项目内互斥，
真源 `four_table/dual_family_codes.py` + 迁移 **V145** 改 `report_config` 公式为并取）+
`h_cycle_adjudication_prefill` 共享件（H1~H4 审定表段预填，四个 render 策略共用）+
H3 前端槽真源 `h3AccountScope.ts` + 金额控件登记 `hCycleAmountControlRegistry.ts` +
会计政策章 + 八、26 `text_sections`。真实库 **80 组合验收 0 违规**
（`verify_h_cycle_extraction_live.py`，9 项目 × 10 循环）。
**Task 18 浏览器实测 5/5 全过**（2026-08-10，实测项目 `2aa00f57` 重庆和平药房_2025 / soe）：
H8 审定表 TB 核对块出 `352,406,145.74` · H3 溯源面板四槽全渲染 · H1 溯源面板出数 +
预填按钮 enabled · 披露推送后附注「八、26 使用权资产」`last_sync_at` 由 NULL 前移且
`sub_table_data['使用权资产']` 25 行列结构未压扁 · 金额控件千分符生效。
**实测修正 tasks 原文三处**：H1 按钮真实文案是「从TB子科目预填」（非「从四表库带入未审数」，
后者宿主是 N1/N3/N4/N5·K1/K2·J1/J2·G8/G9·H2/H4）· H3 用 `WpFourTableSourcePanel`
而 H1/H2/H4/E1 用 `WpSemanticAccountSourcePanel`（DOM 与展开方式都不同）·
立项预设「三个底稿是空底稿」被推翻（实为已有 37 行 `checklist_responses`）。
**登记未修两项**：H8-1 四个金额列用裸 `el-input-number` 未传 `formatter`（EP 2.13.6 无该 prop，
A/B 对照实测确认千分符不生效，属存量替换待单独 spec）· `H8TabDisclosureSoe.syncToNotes()`
裸 `catch {}` 在 HTTP 全 200 时仍弹「同步附注失败」（fail-open 误报）。
实测后按基线**逐字节复原**并双重核实（脚本 verify `diff_count=0` + 独立 SQL 直查九项吻合），
复原后重跑验收脚本仍 0 违规。

**2026-08-08 归档（1 个，→ `05-business-features`，与 `voucher-sampling-*` /
`cutoff-test-*` / `voucher-check-sampling-integration` 同分类）**：

`sampling-evaluation-and-governance-closure`(19/19) —— 抽样评价与治理闭环
（`sampling-compliance-closure` 的后继）。四波：**Wave 1** 撤销回填同步软删两张投影表
+ 合规判据修正（特定项目占比不再用勾选数、MUS 样本量改比系统建议值）+ 覆盖率阈值
单一真源（底稿 > 项目 > 平台默认 0.60，显式标注"非准则数字"）· **Wave 2** CAS 1314
四条评价缺口（未检查样本二选一处置 / 偏差性质结构化复用 C 类口径 / 完整性核对阻断 +
≥10 字理由放行 / 分层层内评价灰度）· **Wave 3** 平台级 P0 —— `qc_rule_definitions`
**0 行**使 `_get_enabled_rule_codes` 返回空集 ⇒ **20 条 QC 规则全部静默不执行**，
门控语义改「禁用黑名单过滤」三态后真实库实测恢复 **20/20** 条；QC-12 判据重写为
不依赖已软弃用的 `SamplingConfig`；新增归档章节 `06-抽样记录汇总.txt` + 归档完整性
第 5 类（非阻断）· **Wave 4** 属性抽样接线控制测试 + 抽样引擎复核入口 + CI 两 job +
真实库只读验收（PASS=10 / FAIL=0 / SKIP=2）+ 浏览器实测。
**收口期修掉一个只有浏览器 + 独立算术复核才会暴露的真缺陷**：`alternative_performed`
的样本 `checkResult` 仍为空 ⇒ 被 `inferMisstatement` 的既有过滤整体排除 ⇒ 既不进
分子也不进分母，推断错报被**放大 2.26 倍**（真实库落库取证 3,412,422.05 vs 正确
1,511,272.73），不符 R3.3 且方向是虚高；修法 = 新增 `applyAlternativeTreatment` +
统一入口 `applyUncheckedDisposition`（留痕计数读原数组、逐位不变），
Property 28 守卫 8 例 + **变异检验 5/5 全 RED**。

**2026-08-05 空壳目录清理（2 个，Active 区不再有非 spec 目录）**：

`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening` 两个目录只剩
`evidence/artifacts/`（无三件套、**未被 git 跟踪**），其 spec 文档早已完整归档在
`_archive/06-engineering-governance/`（86 个 tracked 文件）。逐文件哈希比对确认这批 evidence 是
**更早且已被取代的测量轮次**（canonical 是 6000 请求 / 64 并发，空壳里是 1500 / 48，项目 UUID 亦不同），
其中 6 个文件与两份归档副本都不同 ⇒ **不删除**，整体移入
`_archive/06-engineering-governance/{spec}/evidence/artifacts-superseded-run/`（零覆盖、移动前后哈希逐一相等）。
Archived 计数不变（未新增 spec，只是归位证据产物）。
> 🟡 `_archive/99-superseded/` 下另有这两个 spec 的**同名 evidence-only 目录**（24 个 tracked 文件，
> 其中 `visibility-isolation-go-live-hardening` 还嵌套了一层同名目录）—— 是更早一次未完成的归档搬移残留。
> 清理它需要删除 tracked 文件，留待确认。

**2026-08-05 归档（1 个，→ `05-business-features`）**：

`deliverable-lineage-wiring-and-writeback-closure`(25/25 + 40 个复选框全 `[x]`) —— 交付件溯源接线与回填闭环。
立项时的实证基线：`write_section_anchors` / `snapshot_on_confirm` / `_classify_change` 三者**生产零调用方**
⇒ 溯源/stale/刷新/回填整条链空转（前序 spec 22/22 全绿是**假绿**，测试自己合成带锚点的 docx）。
四波交付：**Wave 1** 锚点写入 + 章节状态落库 + 回填 rowcount 五桶 + 就地刷新 + 能力矩阵单一真源（真实链路验收 **12/12**，
真实项目写入 141 个锚点、`/section-states` 从全库 0 行变 141 行）· **Wave 2** 快照继承 + `doc_key` 去时间戳 +
真实编辑人（V142）+ 护栏接线（**实证席位从来没真正释放过**：占用用 `current_user.id`、释放用 `created_by`
且版本号取的是 OO 内部号，全靠 1h TTL 自愈）· **Wave 3** 报告正文段落级回填（真实链路验收 **18/18**，
发现 Word 模板模式下 `report_body_json` 只有 6 个元数据键、段落文字只在 docx 里 ⇒ 补 additive `sections`）·
**Wave 4** xlsx 差异告警（V143）+ 溯源可视化（版本链 `is_stale` 三态 + 三件套三列对照 + 列表行级溯源抽屉）。
**收尾修正推翻了自己上一轮的归因**：真实库那 22 处「Cell_Mapping 配置错位」实为**检测器自身缺陷** ——
资产负债表拆「主表 + 续表」而 JSON 两侧共用 `balance_sheet` 键且坐标重叠，按 `sheet_aliases` 取第一个匹配
sheet 会让续表 49 个 row_code 去主表取值；改为与 exporter 同源（逐 sheet 扫内联 `{{row:}}` 占位符 +
按真实 sheet 名取值）后 22→5 处（逐格核对确认真差异），另一真实报表变 `checked=452 / diffs=0` 完全一致。
真实库跑 detect 还揪出 naive/aware datetime 裸比较抛 `TypeError` 被 fail-open 吞成「无数据」的真 bug。
**遗留**：浏览器层肉眼实测（后端真实链路验收已 12/12 + 18/18 通过）· 尚未 commit。

**2026-08-04 归档（3 个，→ `11-confirmation-d0-module`）**：

`g0-confirmation-source-alignment`(23/23) —— G0 投资循环函证源模板对齐。逐格精读 10 张 sheet（全 visible）后
补齐 G0-1 下区四块（8 品种×8 指标矩阵「有就显示没有隐藏」+ 防死锁开关 / 样本选择 6 项 / 审计说明 5 段 / 审计结论）、
按循环解析跨表导航（删写死 `D0-*`）、G0A 补回 12 条 `program_category`（备选与 IPO 专项不再默认勾选）、
公式预设从「审定表口径 + `TB_SUM('1101~1511')`」改为 8 条 PLACEHOLDER、G0-6 三区块按源模板重排（删自造记账凭证列、
`support_doc` 拆成支持性文件 1/2 各三列）、9 条源模板缺陷显式登记并在 UI 逐条可追溯。
**顺带修掉两个真实数字/口径错误**：证券差异表三列方向全反（源 `M=J−G` 与表头 `③=①−②` 矛盾，平台照抄了缺陷方向 →
统一为账面 − 回函，两张差异表此前互相矛盾）· 该表组表头字面遗留 `差异（②−①)` 与派生方向自相矛盾（Task 23 浏览器实测抓出）。
**Task 23 实测 8 项 7 通过**，1 项受阻于平台级孤儿组件（`CrossWorkpaperNav.vue` 全仓零渲染宿主 →
Task 11 的修复正确但用户不可达；Property 13 只断言了链条上游有消费方，整条链仍是死的）。
遗留两条平台级议题已登记该 spec §Notes：孤儿导航组件接线（建议与 `e1-orphan-components-wiring` 合并）·
替代程序区块 `CheckBlock.vue` 可编辑金额列用 `el-input type="number"` 致千分符结构上不可能出现（七枢纽同款）。

`h0-confirmation-source-fidelity-and-linkage`(24/24) —— H0 固定资产循环函证源模板保真度与联动补齐。
逐格精读 9 张 sheet（**全 visible**）后修掉三个 P0（「账户/交易」下拉三处互不一致且无 H 类科目 /
H0-1 下区四块完全缺失 / H0-5 四段编号与源模板全部错位），并在真实库直跑与浏览器实测中挖出
**6 个额外缺陷**（其中 2 个是活的错数：H3 裸通名兜底把固定资产累计折旧扣进投资性房地产致账面金额为负；
H0 聚合忽略 `closing_direction` 把 contra 子科目加成正数）。

**2026-08-03 归档（4 个，→ `08-disclosure-notes`）**：
`h-cycle-four-table-extraction-and-account-mapping`(25/25) ·
`d4-four-table-extraction-and-disclosure-alignment`(33/33) ·
`n-cycle-note-template-and-disclosure-completion`(13/13) ·
**`semantic-account-resolver-full-rollout`(31/31)** —— 结论是「应立即迁移的策略 = 0 个」，
交付物是**三道守卫**而非批量迁移：定向裁决交叉锁死（未迁移清单 ⊆ 已登记裁决理由，
33 条逐条带实证）· 旧制编码数据触发守卫（旧制码一带非零余额即打红，把「该迁移了」
交给数据判断）· F2 展示元数据错码纠正。

新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）。

---

## 二、已归档 Spec（551 个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          3
├── 04-infra-architecture/            39
├── 05-business-features/            239
├── 06-engineering-governance/        14
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              80   ← 2026-08-14 实扫修正（原记 78，并发会话归档 2 个未更新树状图）
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/  31
├── 11-confirmation-d0-module/        17
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     7
```

### 最近归档（2026-08-14）

**→ 06-engineering-governance（+1，前端工程治理域第 4 个 spec）**

| Spec | 说明 |
|------|------|
| frontend-excel-io-single-entry-convergence | 前端 Excel 库调用收敛到单一入口（**15/18**，commit `f049a11f`）。**46 个生产文件 / 93 处裸 import → 0，`exempt[]` 为空、无一豁免**。动因：`xlsx@0.18.5` 是 SheetJS 在 npm 的最后一版（已撤出 npm 改 CDN 分发），带 CVE-2023-30533（原型污染）与 CVE-2024-22363（ReDoS），**两个修复版永远不会进 npm**，而项目有 25 处在读用户上传的 xlsx ⇒ 25 个独立攻击面。收敛后防护单点化。<br>性质是**行为等价重构**（产物逐格不变），迁移默认姿势是三个显式关闭 —— `applyStyles`/`includeNoteRow` 两个默认 true 会给 42 个原本无样式的文件加三线表并插行。<br>**顺带修 2 个既有缺陷**：样式模板写非法 OOXML `vertical:'middle'` 致 openpyxl 打不开产出文件 · `ConsolNoteTab.uniqueSheetName` 只 add 不 check（去重是死参数，撞名则整批导出失败）。<br>**删除 2 类零消费方代码**（用户裁决「没用就删」）：`batchExport.ts` + `BatchQueryResultGroup.vue` 整条孤儿链（「合并导出」用户不可达）连带 `headerStyle` 覆写通道 · `sheetMatcher` / `customInstructionSheet` 两项 API（各被后来补出的 `readWorkbookAoa` / 多 sheet 纯 AOA 覆盖，属设计冗余）。<br>🔴 **最贵一课在提交前才发现**：基线 `_progress[].files` 漏记 13 个 confirmation 文件（只写在 `note` 的自然语言里）⇒ 精确 stage 漏文件 + Vite 编译扫描只覆盖 33/46 + 进度失真。**此前全部守卫都在验「代码符不符合清单」，无一验「清单本身完不完整」** ⇒ 补 R6.7 / Property 38 + 2 守卫 + 3 变异。<br>终态：守卫 **119** 例全绿 · 变异 **18/18** RED · Vite 编译 **46/46** · 三件套零 warning。与同分类 `frontend-consistency-m1` / `dev-tooling-modernization` / `workpaper-maintainability-convergence` 同域 |

### 上一轮归档（2026-08-12）

**→ 05-business-features（+1，程序裁剪/委派域第 3 个 spec）**

| Spec | 说明 |
|------|------|
| procedure-trimming-and-delegation-intelligence | 程序裁剪三维判据 + 委派智能化（**26/26 全完成** + 浏览器实测 + 数据复原经 postgres 只读交叉核实）。详见 §一「2026-08-12 归档」段。要点：九档决策内核 + 汇总闸 + 完整性豁免 + 建议态三态 + 理由码真源统一 + 复核视图 + 附注反向联动；**真实库历史上第一次产生裁剪结果**（`procedure_instances` 此前 436 行全为 `execute`、0 条已裁剪 ⇒ 「裁剪→委派联动」逻辑正确但从未有数据流经过）；收口期修掉 Task 14 写入端点恒 500 的真产品缺陷（asyncpg timestamptz 参数编码，112 例守卫因替身不做参数编码而全绿）。与同分类前身 `procedure-applicability-trimming`、`procedure-delegation-notification` 同域；后继 spec = `procedure-trim-report-line-account-resolution` |

### 最近归档（2026-08-09）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| soe-listed-note-conversion-correctness | 国企↔上市附注转换正确性（**19/19 全完成**，守卫 549 passed / 0 failed）。修「生产 6 步里 3 步空操作 + v2 映射是孤儿」：`_map_disclosure_notes` 原先只 `SELECT count(*)` 一行不改却把该数报成 `mapped_notes` = **假成功反馈**；`_map_report_rows` / `_update_formula_references` 是 `return 0`。四处立项判断被实证推翻 —— ①跨变体 row_code 必须按 `(entity, scope)` **四象限**统计（按 entity 合并会虚构出「78 条一码两义」）②「同义两码」standalone **14** 条 / consolidated **13** 条（非 12），且 `EQ-030`/`EQ-033` 两 scope 目标码冲突 ⇒ 映射常量必须 `dict[scope, list]`③需求 3.8「两清单互斥」按字面**不成立**（14 条映射的 listed 目标码全部属「一码两义」，正因两侧异名才需要改写）→ 真不变量 = 「改写源不得落在该 scope 禁止清单里」④公式改写在 `report_config` 域内**零可改写对象**（该表无 `project_id` 列 = 纯模板表 / 全库 formula 对那批 row_code 引用 0 条 / `wp_formula` 0 行 / 附注 `binding_id` 是「章节号.行标签.列键」不含 row_code）⇒ 保留 `return 0` 但补原因码 `no_mapping_needed`。Task 10 裁决 = **删除 v2 不接线**（生产 Step 4 已调 `_map_disclosure_notes`、v2 零调用方且生产版严格更强），21 条断言迁移到生产测试 + 52 例移除守卫。Task 19 达成状态是**诚实输出「无法验收（缺授权）」**（`eligibility=NO_CANDIDATE` + rc=1，需求 10.7 明确允许）—— 8 个 live 项目里技术可切换 4 个、已授权 0 个，建议 `c8621493`（规模最小）。新建件：`note_conversion_row_codes.py` / `note_section_matcher.py`（5 对别名穷举 + 禁止匹配对 + 零相似度实现）/ `note_variant_matrix_null_audit.py`（35 条 null 三态裁决）/ `fix_variant_matrix_false_nulls.py`（三闸门：撞码 / 落点形态 / additive）/ `verify_note_conversion_live.py`；CI job `note-conversion-correctness`（jobs 136→137）。5 个生产文件收尾 md5 与开工基线逐字节一致 = 零净改动 |

### 最近归档（2026-08-08）

**→ 05-business-features（+1，抽样域第 5 个 spec）**

| Spec | 说明 |
|------|------|
| sampling-compliance-closure | 抽样/抽凭合规闭环（**25/25 全完成** + 浏览器实测 + 数据逐项复原）。四波：dataset 版本绑定（抽样查询原先只走 `get_active_filter`，序时账重导后同 seed 同参数得到不同样本且无提示 ⇒「seed 可复现」是假的）· 推断错报持久化 + A13 **`projected`** 通路（改造前 `misstatement_type` 硬编码 `factual`，PG enum 的 `judgmental`/`projected` 是死枚举 ⇒ CAS 1314 的核心输出进不了错报汇总）· 删 legacy `wp_sampling_engine`（金额口径 `debit+credit` 与 canonical 的 `GREATEST` 不同、分层权重写死、不落 log 不可撤销）+ V139/V140 迁移（**加唯一索引前必先查既有唯一约束** —— `uq_sampled_voucher_project_year_no` 全局唯一会让引擎登记撞它并被 fail-open 吞成 WARNING）· 78 宿主 methodology 收口（字段集判据按行模型语义分层：凭证明细型强制四要素 / 合规检查·计价测试型只要求样本可回溯，源模板实证 F2-33 只有源单据日期号、H4-5 只有入账凭证号，加「凭证日期」列属自造底稿列）。**用户裁决**：同一凭证被多底稿抽取必须弹窗人工确认（三出口 + 处置随回填留痕），不由配置项静默决定。**Task 24 收口修掉 4 个前端 dead output 缺陷**（`filled` 载荷缺 `batchId`/`datasetId` 致 bar 恒显「未绑定账套版本」· `wpCode` 是死 prop（78/78 宿主未传）致 `source_wp_code` 恒 null → 改 setup 顶层 `inject(WorkpaperRuntimeContextKey)` 传 getter · 回读态卡片被 `sampledVouchers.length > 0` 藏起来 · A13 描述批次号与样本量/种子不同源）+ 2 处后端修正（`cutoff_fill` 复用 `_normalize_evaluation` · `record_extraction_log` 两条幂等重放分支补回 `batch_id`）。新增 Property 22 + 守卫 46 例，**变异检验三轮 21/21 全 RED**，数据复原后独立只读查询逐项相符。与同分类 `sampling-evaluation-and-governance-closure`（其后继）、`voucher-sampling-engine`、`voucher-sampling-hardening`、`voucher-check-sampling-integration`、`cutoff-test-*` 同域 |

**→ 11-confirmation-d0-module（+2）**

| Spec | 说明 |
|------|------|
| k0-confirmation-source-alignment | K0 管理循环函证源模板对齐（18/18 全完成 + 浏览器实测 + 数据逐字复原）。**接手时三件套在工作树里被并发会话删掉**（`git checkout HEAD --` 恢复；恢复出的是 7/18 旧快照而磁盘产物远超它 ⇒ 「spec 文档被删导致进度记载整体回退」是新的一种假红成因）。**归档副本此前已被并发会话扫进 `d720d522`（无关 spec 的 commit）带进 HEAD，而 active 副本也还在 HEAD ⇒ 两份重复**；本轮按「以归档副本为基底、逐条施加增量」合并（保留并发会话两段实录，10 项结构性核验）后 `git rm` 掉 active 重复副本。**本轮唯一真缺口 = Property 22/23 无守卫**（design 的 Testing Strategy 表点名 `k0LowerZone.spec.ts` 而该文件不存在，Property 覆盖矩阵实扫「22 零引用、23 只被 H0 的同号 Property 偶然命中」）→ 新建 20 例守卫、**变异 6/6 全 RED + md5 逐字节还原**。另修三处三件套缺陷：悬挂引用（补 design 的 Property 24/25）· Testing Strategy 表路径漂移（`x0SummaryMatrix` 已随泛化内核撤回而不存在）· AC 11.1 无人引用。浏览器实测证实 29 叶子列六段分组 / 8 指标出数 / 账面金额自动取数 87,794,660.16（K1 BS-009 净额口径）/ 手工覆盖优先 / 下区键落 `checklist_responses`（**立项写的 `html_data` 是错的**）。新登记两个平台级缺口：保存后切走再切回回到 render-config 初始载荷（潜在数据丢失路径）· 详情面板不套用列剔除与 label 覆盖 |
| f0-confirmation-linkage-and-structural-enhancement | F0 存货循环函证联动增强（144/144 全完成）。矩阵自动聚合（三行取数 + 五派生比例 + 勾稽）+ F0-5/F0-6 供应商自动带入 + B50/A13 推送 + F0-7 邮箱域名可靠性 + F0-3 工号字段。Wave 7 九项返工其中三项修法与立项相反（舞弊迹象/矩阵取值/AI prompt 均按源模板忠实实现或撤回自造）；Task 20/21/22 浏览器实测于 2026-08-05/08-06 三轮补做全通（含 http 客户端形态错配、请求去重 abort、三循环键名各异三个只有浏览器能发现的缺陷）。与同分类 g0/h0/confirmation-orphan 同域 |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| parent-company-note-chapter-and-sourcing | 母公司附注章节结构与取数修复（18/18 全完成 + 已 push 8 个分层 commit）。判据真源 = `docs/模版/` 两份源 docx。修 5 类缺陷：soe 第 12 章标题误为「股份支付」+ slug 错、母公司 93 张表 columns/guidance/report_row_code 全缺、长期股权投资三表两级表头压扁、listed 表名首格泄漏且重名、母公司章 100% 无数据来源。核心件 `parent_company_note_sections.py`（母公司口径单一真源，按章节号逐字相等匹配）。收尾修 3 条守卫红（docstring 剥注释 / removed 键基线由 HEAD 名集推导 / 中间名留痕降级为条件断言），13/13 变异 RED |

**→ 04-infra-architecture（+1）**

| Spec | 说明 |
|------|------|
| report-config-account-code-integrity | `report_config` 科目码完整性（12/12 全完成）。全表对账 132 条 `TB()` 引用扫出 16 行错码（本 spec 修 V138 13 行 + V144 3 行），远超此前手工发现的 6 处。Task 7 挖出立项未见的第二写入路径 `ReportFormulaService.fill_all_formulas()`（按行名索引 + 只填 NULL 行 = 恰是 V138 置 NULL 那批 ⇒ 不修等于白做）+ 未完成重构残留副本 `fill_report_formulas.py`。修 6701/6702 互换 6 处（约 1.5 亿）。核心交付 = 平台级一致性守卫（此前零校验，错码可静默存在数年，先打红 13 行再改数据）+ CI job。V138/V144 均已应用真实库。撤 4 个已到期的 `trust_report_config=False`（零回归双证：40 组合仅 3 组变 resolved_from、码不变） |

**→ 05-business-features（+1）**

| Spec | 说明 |
|------|------|
| sampling-evaluation-and-governance-closure | 抽样评价与治理闭环（19/19 全完成 + 真实库只读验收 PASS=10/FAIL=0/SKIP=2 + 浏览器实测 + 数据逐位复原）。**Wave 3 是平台级 P0**：`qc_rule_definitions` **0 行** ⇒ `_get_enabled_rule_codes` 返回空集 ⇒ **20 条 QC 规则全部静默不执行**（非 except 分支、连 WARNING 都没有），门控语义改「禁用黑名单过滤」三态后真实库恢复 20/20。另修：撤销回填从不清两张投影表（撤销的凭证永久抽不到 + 项目级统计虚高）· 合规判据把「有没有全选」当准则风险 · 60% 覆盖率阈值写死在函数体 · CAS 1314 四条评价缺口（未检查样本处置 / 偏差性质 / 完整性阻断 / 分层层内评价）· 归档完整性完全不感知抽样。**收口期浏览器实测挖出并修掉一个数字级缺陷**：`alternative_performed` 样本被静默挤出比率估计基数、推断错报放大 2.26 倍（真实库落库取证 3,412,422.05 vs 正确 1,511,272.73），Property 28 + 变异 5/5 全 RED。**两项诚实登记未做浏览器实测**：分层明细（灰度默认关，开启需重启共享 dev server）与撤销后重复提示（会在真实批次留下不可逐字节复原的软删痕迹），均由守卫 + 只读脚本 SKIP 承担 |

### 最近归档（2026-08-07）

**→ 04-infra-architecture（+2）**

| Spec | 说明 |
|------|------|
| prefill-wp-prev-resolution-repair | `WP()`/`PREV()` 死链修复（17/17）。两个 resolver 读 `parsed_data['cells']`，该键真实库**零命中**（407 个非空 parsed_data 中 0 条）⇒ 337 条预设恒返 `None` 且 fail-soft 无告警。新建声明式真源 `prefill_anchor_map.py`（三元组键 `(wp_code, sheet, cell_ref)` → `AnchorSpec`，四种聚合 + **六态** `AnchorReadStatus`），取值改走 `checklist_responses(wp_id, item_id).remark`。**核心守卫 Property 4**：读前端 composable 源码抽 `serializeRows()` 持久化字段集与映射列键交叉锁死 ⇒ 「后端复刻前端派生列公式」这一双真源风险变成编译期可检测（D1-2 一族派生列因此进待对齐清单，宁缺勿造）。`PREV()` 改 **fail-closed** 恒返 `None`（`working_paper`/`wp_index` 都无 year 列，取本年值填「上年数」列属数字级错误，161 条里 118 条是「上年审定数」）。**落地时抓到 1 个 P0**：取值层 SQL 写 `checklist_responses.workpaper_id` 而真实列名是 `wp_id` ⇒ 被 `except Exception` 吞成 WARNING、8 条已对齐锚点全部仍返 None，而源码守卫/纯函数单测/characterization 三层全绿（characterization 恰好与「已修好」不可区分）⇒ 新增 **Property 17 真实执行守卫**。另修 `PL` 灰区（`WP('PL','利润表','净利润')` 目标是**报表**不是底稿，硬编码字母表 `"EFGHIJKLMN"` 结构上表达不了 ⇒ 改预设实时派生 + 独立登记表，Property 18）。实测 **6 HIT / 0 ERROR**，`624,025,343.06`（1260 行）经独立 SQL 交叉核对同值同行数；**10/10 变异 RED**；零回归双证（6 个未触碰 resolver 与 HEAD 逐字节相同 + 广域两侧失败集合逐条相同 126 条）。 |
| formula-management-runtime-closure | 公式管理运行层闭环（18/18 + 归档前双轮复核）。修六类实证缺陷：**48 格数字错**（`COLUMN_ALIASES` 缺 4 个发生额列名，两条求值路径静默回退期末余额 → 现 8→14 键 + 三态 helper `_resolve_tb_column`，未注册列名格数 48→**0**）· 用户公式与 Tier A **两套存储收敛**进 `wp_formula`（0 行 = 零迁移压力，GET 保留读兼容分支且守卫钉死）· `logic_check` 结果落库 `cross_check_results` · 删 **4 个同族孤儿**（`useFormulaStatus.ts` / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` / `FormulaDependencyGraph.vue`，均 0 消费方 + 调后端零命中端点）· 底稿公式面板补 issue/hint/计算时间/中文类型标签 · 27 处硬编码 URL 收敛进 `apiPaths/formula.ts` + **平台级「前端公式 URL ⊆ 后端真实路由」守卫**。另修 3 处 spec 未记缺陷（`SUM_TB` 丢弃列名 / `_COLUMN_MAP` 把发生额映到无该列的 `TrialBalance` 静默返 0，24 个消费方 / TB 正则缺词边界误匹配 `SUM_TB` 后半段）。归档复核再修 2 处：**`test_wp_formula_layer_contract.py` 恒红零信号**（列清单只到 V100 而 V104 又加 3 列 → 判据改为扫全部 `V*.sql` 抽取，自动跟随迁移）· `draftRefresh` 漏进 `apiPaths` barrel（+ barrel 完整性守卫）。后端守卫 133 passed / 前端 60 passed / 变异 6/6 RED。与同分类 `formula-engine-unification`、`formula-runtime-convergence` 同族 |

### 最近归档（2026-08-05）

**→ 05-business-features（+1）**

| Spec | 说明 |
|------|------|
| deliverable-lineage-wiring-and-writeback-closure | 交付件溯源接线与回填闭环（25/25，四波全收口 + 两次真实链路验收 12/12、18/18）。与同分类的 `deliverable-lineage-and-writeback`（被它修的前序 spec）、`deliverable-lineage-content-control`、`audit-report-deliverable-center` 同域 |

### 最近归档（2026-08-03）

**→ 08-disclosure-notes（+3）**

| Spec | 说明 |
|------|------|
| h-cycle-four-table-extraction-and-account-mapping | H1~H10 语义科目定位收口（25/25 + 复盘 5 项 + 浏览器实测）：修 3 个「取错整个科目族」P0（H3 `1503/1504`→`1521/1525/1526/1527`、H8 `1901` 待处理财产损溢→`1641/1642/1643`、H9 `2205` 合同负债→`2601/2602`）；实测挖出 `parent_check` 揭示的 `trial_balance` 父子双算平台级缺陷 |
| d4-four-table-extraction-and-disclosure-alignment | D4 营业收入四表取数与披露/附注对齐（33/33） |
| n-cycle-note-template-and-disclosure-completion | N 循环附注模板与披露收口（13/13） |

### 最近归档（2026-08-01，第四批）

**→ 08-disclosure-notes（+14）**

| Spec | 说明 |
|------|------|
| f1-four-table-extraction-and-disclosure-alignment | F1 预付款项四表库取数链路根治+披露/附注收尾（28/28 全完成+实测） |
| f1-extraction-chain-and-disclosure-source-fidelity | F1 取数链路数据源忠实度（16/17，仅缺浏览器活测；实现已完成） |
| h3-investment-property-disclosure-alignment | H3 投资性房地产披露对齐（11/11 全完成+实测） |
| h5-oil-gas-disclosure-alignment | H5 油气资产披露对齐（8/8 全完成+实测） |
| h7-biological-assets-disclosure-rebuild | H7 生产性生物资产披露重建（12/12 全完成+浏览器实测） |
| h8-right-of-use-disclosure-alignment | H8 使用权资产披露对齐（7/7 全完成+实测） |
| h9-h10-remaining-disclosure-alignment | H9 租赁负债 + H10 资产处置损益披露对齐（9/9 全完成+实测） |
| k1-extraction-chain-and-note-alignment | K1 其他应收款取数级联第二轮收口（28/28 全完成+实测） |
| k1-four-table-extraction-and-disclosure-alignment | K1 四表库取数口径根治+披露/附注结构对齐（27/27 全完成+实测） |
| k2-four-table-extraction-and-dynamic-rows | K2 其他流动资产四表取数+动态行（13/13 全完成+实测） |
| n1-four-table-extraction-and-disclosure-alignment | N1 递延所得税资产四表取数+披露对齐（24/24 全完成+实测） |
| n2-disclosure-and-extraction-alignment | N2 应交税费披露与取数对齐（19/19 全完成+实测） |
| n2-vat-calc-source-alignment | N2 增值税计算源模板对齐（19/19 全完成+实测） |
| n345-four-table-extraction-alignment | N3/N4/N5 四表取数对齐（26/26 全完成+实测） |

**→ 99-superseded（+1）**

| Spec | 说明 |
|------|------|
| n2-source-alignment | 被 `n2-disclosure-and-extraction-alignment` 取代（仅含未落盘的 implementation-checklist） |

**清理空壳（2个）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 早已归档（2026-07-18），残余 evidence 目录清除 |
| visibility-isolation-go-live-hardening | 残余 evidence 目录清除 |

### 2026-07-31 归档

**→ 08-disclosure-notes（+19，含并发会话完成的 spec）**

| Spec | 说明 |
|------|------|
| h2-construction-in-progress-disclosure-alignment | H2 在建工程披露结构对齐（7/7 全完成+实测）：两级表头重建 + 「项  目」→「工程物资」改名 + 10 表 columns/guidance + 契约守卫 + CI job + 浏览器实测通过 |
| d2-ar-disclosure-template-alignment | D2 应收账款上市披露三层对齐（31/31 全完成+实测+已提交） |
| d2-ar-disclosure-soe-alignment | D2 应收账款国企披露结构对齐（25/25 全完成） |
| f2-inventory-disclosure-template-alignment | F2 存货披露对齐（Sprint 1~8 全完成+已提交） |
| f1-prepayment-disclosure-template-alignment | F1 预付款项披露对齐（全完成+实测+待 commit） |
| disclosure-columns-coverage-rollout | 披露表 columns 覆盖推广（Task 1~16 全完成+已提交） |
| j1-disclosure-template-alignment | J1 应付职工薪酬披露对齐（61/61 全完成+待 commit） |
| k2-other-current-assets-disclosure-alignment | K2 其他流动资产披露对齐（22/22 全完成+实测） |
| n1-deferred-tax-disclosure-template-alignment | N1 递延所得税资产披露对齐（57/61 实现+实测完成） |
| n-cycle-tax-disclosure-alignment | N 循环税务类披露对齐（N2/N4/N5 全完成+实测） |
| d-cycle-remaining-disclosure-alignment | D3/D5/D6/D7 披露结构对齐（Task 1~9 全完成+实测） |
| k-cycle-disclosure-alignment | K1~K13 三批披露对齐（全完成+实测） |
| d1-notes-receivable-disclosure-alignment | D1 应收票据披露对齐（四阶段全完成+实测） |
| f-cycle-disclosure-parity | F 类披露复盘对齐（R1~R9 全完成） |
| applicable-standards-frontend-wiring | 准则前端全链接通（全完成+实测） |
| applicable-standards-runtime-and-sync-guard | 准则运行时守卫（全完成+实测） |

**→ 05-business-features（+2）**

| Spec | 说明 |
|------|------|
| f1-prepayment | F1 预付款项（含四表库自动取数补齐） |
| k2-other-current-assets | K2 其他流动资产 |

**→ 06-engineering-governance（+1，清理空壳）**

| Spec | 说明 |
|------|------|
| procedure-delegation-visibility-isolation | 服务端底稿可见性隔离（18/18，2026-07-18 已归档，空壳清理） |

### 2026-07-29 归档（12 个，详见 git log）

**→ 05-business-features（+9）**

| Spec | 说明 |
|------|------|
| advanced-query-consolidation | 高级查询模块合并收敛（12/12） |
| attachment-workpaper-linkage-convergence | 附件↔底稿联动收敛（23/23） |
| f2-adjudication-import-export | F2 审定表导入导出（9/9） |
| f2-detail-ledger-pull | F2 明细表序时账取数（11/11） |
| f2-four-table-extraction-refresh | F2 四表取数刷新（22/22） |
| hi-cycle-four-table-extraction | H/I 循环四表取数（14/14） |
| lmn-four-table-extraction | L/M/N 循环四表取数（12/12） |
| template-library-formula-preset-custom | 模板库公式预设（16/16） |
| work-hours-auto-collect-and-edit | 工时自动采集与编辑（18/18） |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| d-cycle-disclosure-note-enhancement | D3-D7 审定↔披露差异告警（13/13） |

**→ 09-consolidation-phases（+1）**

| Spec | 说明 |
|------|------|
| consol-disclosure-note-persistence | 合并附注 V2 按项目灰度（9/9） |

**→ 11-confirmation-d0-module（+4）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（19/19） |
| h0-confirmation-source-fidelity-and-linkage | H0 固定资产循环函证源模板保真度与联动（24/24） |
| g0-confirmation-source-alignment | G0 投资循环函证源模板对齐与联动补齐（23/23） |
| confirmation-orphan-and-amount-format-closure | 函证域孤儿件与金额格式收口（13/13）：删 3 个 G0 零消费方 composable · `CrossWorkpaperNav.vue` 挂上首个渲染宿主（改造前全仓零宿主 = 用户不可达）· `BlockColumnDef.render:'amount'` + 七枢纽 76 个金额列标注 + 17 个非金额列登记 · 新增平台守卫「渲染宿主存在性」（组件基线 2 / 模块基线 23，只许缩短） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
