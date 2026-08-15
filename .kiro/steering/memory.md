---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤200 行**。明细下沉：完成事项 → `#dev-history`；架构决策 → `#architecture`；踩坑/编码约定 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**单次回复不要过长 —— 分段输出、每段一个可交付进展**（2026-08-05 用户明确要求）；**任务标记不能假绿**；**彻底解决不绕开**；**optional(*) 任务也要做完**
- **调查完必须主动给改进建议，别只堆实证就停下**（2026-08-05 用户催「明明都已分析好了呀」）
- **🔴 codegraph 优先于 grep**：146k 节点/312k 边/8673 文件；grep 仅用于非符号纯文本
- **触类旁通**；**改动前先 spec 三件套**（>500 行 / 3+ 组件 / 跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表/附注金额默认「元」**；**中文场景全链路不能崩**
- **不要考虑轻量**：要针对性、联动性、美观性、实操性、易懂性；审计 UI 必须有逻辑追溯能力
- **四表取数新循环一律复用 `app/services/four_table/`**（`ReportLineAccountSpec` 声明报表行 + 兜底码 + `extra_standard_codes`；`select_leaves`/`aggregate_leaves` 做叶子聚合），禁止再抄一份科目定位/聚合逻辑
- **死代码立即删除**（不留 DEPRECATED/fallback 注释，否则每次复盘重复提议）
- **🔴 避免硬编码（2026-08-01 用户明确要求，全局适用）**：科目码/分类标签/章节号/表名/列 label/行集/列数/行数一律走**单一真源 + 守卫与真源双向锁死**。落法：①科目 → per-cycle `xAccountScope.ts`（`k2AccountScope.ts` 是范式），运行态取 render 下发的 `tb_source_codes`，常量只作兜底+展示 ②分类桶 → 一份声明式 dataclass（含 `source_ref` 指向源 xlsx 单元格），后端分类器/prefill 行标签/前端 seed 共同读，前端不抄第二份 ③章节号/表名字面量无法避免时（registry 生成器要求内联）**必须**与 `note_template_variant_matrix.json` / `note_template_*.json` 交叉锁死 ④列 label/行集真源 = 源 xlsx，守卫 openpyxl 直读三向比对 ⑤**按公司/单位横向展开的表禁写死列数**（`公司1..公司N`），改动态列 + 稳定 key `{slot}_{seq}`（H7 范式，**key 不能用 label** 会撞键）⑥**动态区骨架行数禁写死**（`blankRows(p,3|5|10)`），改 `max(seed 行数,1)`，预置空占位会被推成占位披露行 ⑦守卫读源码前必 `stripComments()` + 反向自检
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- **会话结束前清掉自己的 `tmp_*` 诊断产物**（用户 2026-08-01 明确要求删；曾积到 68 个 / 18.7 MB，含 6.8 MB 的 vitest JSON 与带 token 的 `tmp_login.json`）。`.gitignore` **尚未收 `tmp_*`**（已向用户提议加、待答）
- **spec 归档按功能分类**（05-business-features / 04-infra 等），不按日期批次
- 目标并发 6000 人；底稿编码 = 致同 2025 修订版
- 5 角色轮转：审计助理 / 现场经理 / 业务合伙人 / 质量控制复核合伙人 / EQCR 技术复核人
- **v3.0 愿景（当前不做）**：项目级知识自动提取 + 跨年度续审继承

## 平台级 UI/数值铁律

> 完整机制与代码位置见 `#architecture` §平台级数值格式 / §表格 UI 规范。

- **金额格式单一真源** = `stores/displayPrefs.ts` 的 `fmtAmount()`（千分符 + 2 位小数 + 默认「元」+ localStorage 持久化）。只读金额一律走它。**🔴 它是 store 成员、不是模块级导出** —— 写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩成「页面渲染出错：does not provide an export named 'fmtAmount'」（`get_diagnostics` 与 vitest 全绿，只有浏览器暴露）；正解 = setup 顶层 `const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 再 `displayPrefs.fmtAmount(v)`（`useDisplayPrefsStore` 是 setup 作用域 composable，写进函数体静默失效）。
- **防折行全局** = `styles/global.css` 的 `.el-table td.is-right .cell{white-space:nowrap;font-variant-numeric:tabular-nums}`。
- **🔴 可编辑金额千分符只能用 `el-input`（2026-07-29 已定论，双证）**：①源码 —— EP **2.13.6** 的 `node_modules/element-plus/es/components/input-number/**` 全文无 `formatter`/`parser`，该 prop 不存在；②浏览器实测 —— `el-input-number :formatter` 下输 1234567.5 显示 `1234567.50`（**无千分符**），换 `el-input` 后显示 `1,234,567.50`。故平台现存 40+ 处 `el-input-number :formatter`（K1TabDisclosureListed·Soe / K1StageEclTable / E1TabCashCount / E1TabCreditReport）**全是空操作，千分符从未生效**；`wpAmountInput.ts` 的用法注释写错。→ 统一用 `components/workpaper/shared/WpAmountInput.vue`（失焦千分符 / 聚焦原始值便于编辑 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）；存量替换待单独 spec 收口。`:precision="2"` 是真 prop 可留。**绝不套用**利率/汇率/比例/笔数/年度/月份。
- **🔴 `fmtAmount(0)` 默认返回「-」不是 bug**：`stores/displayPrefs.DEFAULTS.showZero = false` + `utils/formatters.fmtAmountUnit` 的 `if (n === 0 && !showZero) return '-'` → 「0 显示成 -」现在是**用户可切换的平台级偏好**（已收敛到单一真源），不再是组件私自写死。要让 0 恒显 `0.00` 得改 `showZero` 默认值 = 波及全部表格的平台级变更，别在单个循环里绕。
- **底稿表格统一**：13px 字号；AI+复核按钮右对齐在 section 标题同行；公式列虚线下划线 + tooltip 来源；审计说明/结论 `el-card` 包裹；编制提示 `details` 折叠底部。
- **`GtPageHeader` 操作按钮**放**默认插槽**用 `margin-left:auto` 推右（放 `#actions` 会被拉伸成整条）；列表页表格禁 `border stripe`，改无边框 + `el-card shadow="never"`。
- **列表页打磨范式**：状态列全中文彩色 tag（禁裸英文）；操作列 >4 项收「更多▾」；`highlight-current-row` 代替"选中"按钮；文件名带类型图标；状态面板禁空洞 `el-card` 改紧凑单行 bar。
- **🔴 Vue 模板属性禁用中文引号/特殊 Unicode**（`content="…"XX""` 的 U+201C/201D 触发 Vite 编译崩溃，`get_diagnostics` 查不出）。
- **导入导出统一** `el-dropdown「导入导出▾」`（导出模板/导出数据/导入数据）+ 复用 `useXImportExport`；多区块分 sheet。

## 底稿交互铁律

- **交互点选优先**（尤其 C 类控制测试）：判断/枚举字段一律下拉/单选/多选 tag/按钮点选；长文本才 autosize textarea + AI 辅助。
- **动态行新增**需命名的必须先 `ElMessageBox.prompt` 输入名称再创建。
- **多 section 底稿每个文本区都要 AI 辅助**（section 标题行右侧放 AI 按钮，不只底部有）。
- **宽表（>10 列）录入**改引导式弹窗（分组卡片 + 内嵌方法论 + 实时联动分析面板 + 点点点 select）；>15 列必须拆分（区段 Tab / 借贷双区块 / 固定列+滚动 / 左右视觉分组）+ ⚙列设置。
- **源模板红字内容**嵌入对应功能区上方作"方法论上下文"（琥珀色左边线+浅黄背景）；示例内嵌到编制界面可一键套用，不藏 Drawer。
- **必要处加 📎 附件上传 + OCR**（样本证据/凭证/审计证据/过程记录），复用 `/d4/contract-ocr` → 确认弹窗 → merge 填充。
- **结论/缺陷/偏差回写**：→ B50 EventBus / → A14 缺陷底稿 / → C21-1 汇总 / → A13 错报（`a13:push-misstatement`）。
- **叙述式底稿**（仅核对+结论）不加独立审计意见区；textarea 用 `:autosize="{minRows:5}"`。

## MCP 使用铁律

- **🔴 工具选型阶梯**：符号/调用链/影响面→`codegraph`；wp_code/componentType/spec 进度→`gt-plan`；库表实证→`postgres`；容器日志/健康→`docker`；PR/CI→`github`；框架 API→`context7`；用户可见行为→`playwright`；非符号纯文本→`grep`（末位）
- **🔴 gt-plan 优先于手翻 JSON**：查 wp_code、spec tasks、迁移 V 号先 `wp_lookup` / `spec_status` / `migration_status`
- **🔴 postgres 只读**：仅 `restricted` 模式；禁经 MCP 写库；写库验证用 pytest 或现有脚本
- **docker / github 默认只读**：破坏性操作须用户明确要求
- **禁止 MCP 叠床架屋**：同一问题只选一主工具；失败降级回退终端命令并说明；密钥仅 `.cursor/mcp.env`

## 底稿开发铁律

- **风险导向审计**：B50 风险 → D~N 程序表 → A13 评价错报，全链可追溯
- **componentType 选型**：结构化=`d-form-table` / 复杂 Excel=OnlyOffice / 文档=`word-template` / 程序表=`a-program-console` / 函证=`confirmation-*`（9 类）
- **三表 HTML 渲染**：底稿目录+审定表+附注全走 HTML，仅复杂公式/DCF/图表留 OnlyOffice
- **联动是核心价值**：`ref_index` chip + `auto_data_source` 实时取数；孤立底稿=无价值
- **🔴 函证模块跨循环共享**：D0 的 9 个 `confirmation-*` 组件跨循环复用（E0/F0/G0/H0/K0/L0），不为每循环独立开发
- **开发前必先逐 sheet 读源模板**（openpyxl 读 xlsx + BCD 类 md 交叉验证）
- **🔴 源模板 xlsx 只认 `backend/wp_templates/`（运行时权威）**：`wp_template_init_service` 生成底稿时从这里复制、`wp_template_finder` 以 `_index.json` 索引。`基础数据/致同通用审计程序及底稿模板…` 是**参考副本且已落后**（实测 G4/G5/G6 两处不一致：权威版多「项目N（可改名）」占位行 +「（预留，可填或在本区内插入行）」预留区 + 6 条「编制说明」；G4 国企三阶段用语统一为「减值准备」；G4/G6 上市**只有「期末第一阶段」末列是「理由」**其余为「划分依据」；G5 删了「应收保证金/应收关联方款项」两行。G8~G12 两处字节一致）。2026-07-30 曾据参考副本重建 G4/G5/G6 后返工。**读模板前先比对两处 size**，并注意 `~$` 锁文件要跳过（用户开着 WPS 时可能还有未保存改动）
- **🔴 增强打磨禁止自造披露内容**：附注/披露表增强必先看源模板，禁按"常识"造表（D5 曾自造"金融资产风险敞口"）。**存量已发现自造组件：`G6TabDisclosureListed.vue`**（7 个虚构小节「一、其他债权投资成本/二、利息调整/…/七、其他披露事项」+ `generateRows()` 批量生成 137 行 `成本项目N`，列头亦自拟；源表实为 14 张表）→ **不得接附注同步**（会污染附注），须按源模板重写；G6 国企侧结构正确（仅行名是可改名占位，可接）
- **模板预填优先于 AI 生成**：有固定骨架的章节用 CHAPTER_TEMPLATE + 变量替换，AI 仅用于复杂章节
- **🔴 底稿→附注同步不得压扁列结构**：底稿 UI 已按源模板渲染宽表时，`{X}NoteSectionMap.ts` 必须推同构列头（D2 曾把 6 列分类披露压成 2 列，附注/Word 双双缩水）；双期表拆两张、续表键补「（续：上年年末余额）」
- **`sub_table_data` 唯一规范形态 = `{key: list[dict]}`（业务键行）**：投影结果（`{rows,_column_groups}` / 位置化 `values`）被回写时由 `note_sub_table_projector.normalize_sub_table_data` 读写两端逆投影，禁止再写 skip 分支丢整表
- **底稿改版重命名子表**须随载荷上报 `sub_table_data._removed_table_keys`（后端删旧键，跳过本次推送键），否则附注永久残留空表
- **附注行真源 = `rows[].label` + `rows[].values`（`_cell_meta`/`_cell_modes` 按 value 列索引键，标签列不算数据列）**；离线导入 xlsx 中间结构才是 `cells`（`cells[0]` 是标签列，对齐时须 -1）。`note_offline_import_service` 曾两侧都读 `cells` → 对真实附注 diff 恒「本地全空+全 ADD」、OVERWRITE 还把 `cells` 写回库（渲染器读不出），已修
- **D~N 专属组件 8 步**：registry+yaml → composable 分层（`useXFormulaEngine` 纯函数）→ 主入口 sheetName v-if 分发 → 后端 3-4 py → 注册四件套 → 联动（TB 回写+EventBus+GtIndexChip）→ UI 铁律 → 功能方向（联动/美观/溯源/易操作/导入导出/AI/双三模式）
- **OO sheet-name 必须与源 xlsx tab 名完全一致**；多 sheet workbook OO 隐藏非目标 tab
- **通用 schema 复用** `{wp_code}-generic.yaml` + pattern matching
- **🔴 列式转置结构**（投资项目作列头+检查项作行，如 G4-9）前端必须转为行式交互视图

## 审定表预填充铁律

- **X-1 审定表未审数从 `tb_balance` 明细子科目预填**（render 策略 `_build_adjudication_prefill`）：`get_active_filter` 查 `{code}%` → **优先叶子科目防双算** → 按 code 段分类 → 负债 `abs()` → snake_case 对齐前端；**仅无持久化时预填**（编辑后不覆盖）。`trial_balance` 只有一级总额+期末，故分类行必须从 `tb_balance` 取。
- **审定表双期结构**：源模板若有「期初数/期末数各（未审/账项调整/重分类/审定）」分组表头即双期，单期 roll-forward 是误用；有一年内到期则加「减一年内到期→最终审定数」。
- **四表取数 Tier A vs Tier B**：固定类别审定表（每类=一个科目，如 F2/H/I/L/M/N）适合 Tier A 可编辑 `TB()` 公式；动态分类审定表（D 循环信用风险/账龄）只能 Tier B 预填。**宁缺勿造**：无法干净映射的分类行不 seed。

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- vLLM：Qwen3.5-27B-NVFP4，APC+fp8 kv-cache
- Docker：postgres(5432)/redis(6379)/metabase(3000)/pgbouncer(6432)/OCR(8200)/onlyoffice(8080)
- DB_DISABLE_SSL=True；连接池 150 / PG max_connections=200
- 前端唯一路径：`audit-platform/frontend/`
- **codegraph v0.9.9**；**MCP 7 个**（codegraph/playwright/postgres/github/gt-plan/docker/context7，配置 `.cursor/mcp.json`）；**rtk 0.42.1**；**OnlyOffice 9.4.0**
- 部署 v2.0：瘦客户端（Electron）+ 内网全栈

## PG schema

- `trial_balance` = standard_account_code / unadjusted_amount / aje_adjustment / audited_amount（v2 正数口径，只有一级总额+期末）
- `tb_balance` = account_code / opening_balance / closing_balance / debit_amount / credit_amount / closing_direction（多级子科目；**无符号绝对值 + 方向列**，recalc 必按方向带符号求和）
- `working_paper` 无 wp_code（在 `wp_index`，需 JOIN）
- recalc 铁律：只汇总**叶子**科目；未映射叶子按**最长前缀**继承祖先映射；损益取发生额
- `tb_ledger` 人员列仅 `preparer`（无 poster/reviewer）；`counterpart_account` 填充率低（~9%）不可靠
- `tb_aux_balance` 按维度**冗余存储**（校验须 GROUP BY aux_type，见 `#architecture`）
- 契约测试：schema_contract（表级）+ column_contract（列级）+ componentType 契约 vitest
- **迁移** = `backend/migrations/V*.sql`（MigrationRunner，非 alembic），新加必须 `IF NOT EXISTS` 幂等

## 任务状态

> 完整 spec 进度、编排器历轮判定、各循环（G7/I/K/L/M/N/E/F 等）深度调查结论、各类复盘明细 → 全部下沉 `#dev-history` 末尾「从 memory.md 下沉的任务状态与复盘明细」。此处只留每次对话必用的活状态。

- **当前在做**：`k-cycle-extraction-formula-and-disclosure-closure`（最新实测 5/25，Wave1 全交付 + Wave2 Task4/5，未 commit）。
- **`g7-column-alignment-and-extraction-closure` 已 24/24 全交付并归档**（2026-08-15 → `_archive/08-disclosure-notes/`，commit `83ccf630`，分支 `work/2026-08-12-g7-column-alignment-closure`）：56 偏差点→0；补第三边（源xlsx↔seed↔运行时）+ **新增第四边「渲染层」**（两级表头 0/38→20 张）；契约 11→38 张；2 个 CI job；变异 **15 锚点**全 RED；前端 887 passed / 后端 G7 主域 2297 passed。收口复盘追加修 **fail-open**（两个披露 Tab 的 `syncToDisclosureNotes()` 真同步与收尾共用一个 `try`，失败被成功文案盖掉 ⇒ 拆两段 + 失败 `return`，文案下沉 `g7DisclosureSyncFeedback.ts`）。**16 个新文件已入库，此前登记的「10 个正式产物 `??` 未跟踪」已解除。**
- **`e-cycle-extraction-formula-and-disclosure-completion` 已 24/24 全交付并归档**（2026-08-15 复盘后 → `_archive/08-disclosure-notes/`，归档 commit `267111b6`，主交付 commit `2ee7929e`）：账户级取数走 `tb_aux_balance` 的 `aux_type='银行账户'` ⇒ E1-3 出 22 行逐户（此前叶子口径恒 1 行汇总）；浏览器实测抓出两处真实缺陷（① `resolveRestrictedRows` 按数组下标重算 id 覆盖稳定序号 ⇒ 删后再增复用已删序号、历史 reason 串到新类别 —— **已修**；② E1-3 multi 版 variant 切换抹零 —— **登记未修**，见下）；变异 **29 条全 RED**；后端 368 / 前端 568 passed；CI 两个新 job。**复盘沉淀两条通用做法**：变异脚本 `--check-anchors` 是「已归档 spec 是否还可复现」的最便宜判据（只读、秒级、证明 29 处结构未漂移，不必重跑全量变异去改带并发在途改动的文件）· 工作树 dirty 文件**必须逐个 diff 归因**（`E1TabDisclosure.vue` 名字是 E 循环的却是并发 K 循环改的）。
- 🔴 **E 循环遗留缺陷（未修，非该 spec 引入，建议单独立任务）**：E1-3 先点`仅人民币`再点`人民币及外币` ⇒ 22 行金额全变 `-` + 一条错的「审定合计 0.00 ≠ TB」横幅。根因 = 宿主 `seedFromFourTable()` 只在 `onMounted` 跑一次且 `seedRowsKey` 有 persist-first 短路，种子形态一会话内只按当时 variant 定型；`recalcRow(row,'multi')` 又把六个金额全由「原币 × fxRate」派生，rmb 形态种子无 `openingFc` ⇒ 恒 0。29 条变异 + 568 例守卫全没拦住，因为**没有一条把「种子的 variant」与「消费它的 Tab 的 variant」串起来断言** = 假绿第①源第三种变体。改法要动种子键按 variant 分离 + 新守卫。可与「E1-10 交叉核对把科目码当账号比对」并入存量口径回填 spec。
- **Active spec = 6 个带 tasks.md + 2 个空壳**（🔴 数字一律以 `.kiro/specs/` 复选框实扫为准，行首锚定正则 `^\s*-\s\[([ x~-])\]\s+\d+\.`，别信 memory 旧数）。2026-08-15 实扫：`i-cycle-…closure` **23/24** · `k-cycle-…closure` **19/25** · `l-cycle-…completion` 3/26 · `procedure-trim-report-line-account-resolution` 0/16 · `workpaper-import-export-lifecycle-closure` 24/25 · `x3-adjustment-entry-import-export` **33/53**（`e-cycle-…completion` 24/24 已归档，见上）。空壳 2 个（`procedure-delegation-visibility-isolation` / `visibility-isolation-go-live-hardening`，git 里 `??` 未跟踪，2026-08-12 曾误记为「已清理入归档区」）⇒ **报 Active 数必须区分「目录数」与「带 tasks.md 的 spec 数」**。Archived **553**。
- 🔴 **4 个在办 spec 目录在 git 里全是 `??` 未跟踪**（2026-08-15 归档 e-cycle 时 `git status` 实录：`i-cycle` / `k-cycle` / `l-cycle` / `x3`，连同 2 个空壳）⇒ **丢工作树即全部蒸发**，且 INDEX/memory 登记的进度数无法从 HEAD 复核。已归档 spec 不受影响（`_archive/**` 已跟踪）。建议各推进方尽快把自己的 spec 目录入库。
- **🔴 run-all-tasks 编排器累计逾二十次均判「不接管」**（最近 2026-08-09）。判据三条，任一不满足即不启动子代理：①本会话是否真发起过批量执行（用户说「继续」≠「run all tasks」，编排器只恢复被中断的批量、不替用户发起）②带 `[-]`/`[~]` 的任务，其 tasks.md 正文是否写明了阻塞原因（写明=有意驻留，如 `h-cycle` Task18「浏览器实测待做」；未写明才可能是被中断）③该 spec 的 tasks.md mtime 是否秒/分钟级（=并发会话正在写，勿碰）。
- **git/迁移**：当前分支 `work/2026-08-12-g7-column-alignment-closure`（并发会话另在 `work/2026-05-30-wp-specs` / `work/2026-08-12-e-cycle-extraction-closure`）；最高迁移 **V146**（2026-08-15 实扫 `backend/migrations/V*.sql` 得 146 个文件、最大号 146，`R1xx__` 是配对回滚脚本非同号冲突）；新迁移须重启后端才应用（MigrationRunner 只在启动时跑）；**push 前必先 fetch 看远端真实 base**（memory 里的旧 commit hash 会过期）；协作走 PR 不直推 main。
- **并发多会话现状**：工作树长期不干净、根目录 `tmp_*`/`backend/scripts/diagnose/_wip_*` 多为他人在用（按 mtime + 内容关键词判归属，勿按文件名里的任务号误删）；同一文件禁与并发会话并行编辑；判 spec 是否真完成一律**工作树 + HEAD 双查**（防「从未提交」与「被回退」两类假红）。
- **🔴 「spec 全绿」≠「产物已入库」**：多个 spec 的正式产物（守卫测试、诊断脚本、判据 JSON、新建实现文件）长期 `??` 未跟踪 —— G7 收口时实测本 spec **10 个正式产物全未跟踪**，同目录另有他人 20 个 `??` 测试文件。后果两条：①挂进 `governance-checks.yml` 的 job 在干净 checkout 下**必挂**（文件不存在）②工作树一丢全部蒸发。**每个 spec 收口必查 `git status --porcelain -- <产物清单>`**，见到 `??` 即登记待 add。
- **`.gitignore` 已于 2026-08-15 补收 `tmp_*` 与 `_wip_*`**（此前只收带前导下划线的 `_tmp_*`，G7 收口前根目录积了 **487** 个 `tmp_*`）。补之前用 `git check-ignore -v` 验证过 0 个正式产物被挡（`tmpHeadBaseline.spec.ts` / `_wipG7RuntimeProbe.spec.ts` 因无下划线分隔不受影响）。清理时仍按前缀 + mtime 判归属（今日仍有产出 = 并发会话在用，勿碰）。
- **pre-push 的「6 维核查」不达标≠push 有问题**：`.git-hooks/pre-push` 在 `GIT_MODE=single` 下只警告（multi 才阻断）。维度 1（工作树 clean）与 5（untracked 0）在本仓库**长期不可能达标**（并发多会话在途 + 数百 `tmp_*`/`_wip_*`）；判自己的 push 完不完整只看**维度 2/3/4**（本地 HEAD == 远程 / ahead 0 / behind 0）。核查脚本 = `backend/scripts/check/check_git_sync_state.py`。

## 踩坑铁律（完整 500+ 条见 `#conventions`）

> 每写一段代码/守卫前先过一遍下列高频坑；具体某模块的坑在 `#conventions` 对应小节。

- **假绿三源**：①additive 注入即死代码（新加的取数/字段无消费方）②grep 式守卫只查字符串存在（改成 `if False:`/删调用/改名残留仍绿）③守卫把错值当基线锁死（把真源改对反而打红）。→ 判据一律用「行为/结构/真实执行」而非「字符存在」；**每写完守卫必做变异检验**（改一字看是否变红），没打红=守卫有缺陷不是代码没问题。
- **🔴 第①源的最隐蔽形态 = 守卫层级不够，渲染层死代码结构性不可见**：G7 实测「模型声明 `column.group`（三向守卫拿它跟源 xlsx 合并单元格逐张对齐、39 例全绿）而任何 `.vue` 零引用」⇒ 两级表头 **0/38 张从未渲染**，审计师看到 5 组一模一样的 `期末数|期初数` 分不清属于哪家公司。守卫只比「源↔seed↔模型」三层数据，**从不看 DOM**。→ 判「某声明是否真生效」必须落到**浏览器 DOM** 或**模板形态判据**（遍历+外层门控+内层嵌套三要素缺一即红），并把 DOM 结论沉成可测投影当第四边。
- **多 spec 混合文件（`governance-checks.yml` / 共享模板 JSON）的「只加不动」验收必须用归因型判据**（变动是否落在**我的字节区间**内），不能用全局等值型（「其他 job 一个都没变」）—— 并发会话同时改同一文件是常态，全局等值必假红（实测拍快照 144 job → 我 append → 复核 147）。`fs_append` 与并发编辑不互相覆盖。
- **真实库写入/复原三坑**：①timestamptz 回写必须在 **Python 侧**转 `datetime`（备份用 `::text` 导出后回写会被 asyncpg 拒；**SQL 层 `CAST(:x AS timestamptz)` 无效**，驱动发送前就按目标类型编码）②`engine.begin()` 内**一处失败全部回滚**（复原脚本第 3 步抛错把前两步撤回）③**被 `^C` 中断的运行可能已提交部分变更** ⇒ 判成败一律查数据不看 exit code。
- **别跑全量 `backend/tests`**（根目录 **1522** 个测试文件，前台跑数分钟无输出会被当卡死）⇒ 按**引用关系反查辐射面**：扫测试文件里对本次改动物的实际引用（G7 得 77 个文件，2分49秒跑完）。
- **「源侧物理结构」字段不能直接当期望值**：facts 的 `is_two_level` 描述源 xlsx 有几行表头（含父行为空的占位合并），须剔除已登记的 `single_slot_exemption` 才是「应渲染两级」的期望（24 → 20）。同理任何 `_exemption`/`_adjudicated` 登记表都要参与期望值推导。
- **变异检验四态**：RED（打红且正是预期那条测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷：锚点未命中或命中 >1，含 `\n` 跨行锚点在 CRLF 必 MISS）/ WRONG-TEST（打红了但不是预期项=污染残留或锚点错行）。只看退出码会把后三态误判成 RED。
- **fail-open 掩盖接线错误（最贵一类）**：`except Exception` 把「函数名/列名拼错、单参调用 async、传错客户端形态」全吞成 WARNING → 表现为「本项目无此数据/静默取空」，而 Volar/vitest/get_diagnostics/HEAD-swap 四层全绿 → 取值层守卫必须**真跑一次并把异常记 ERROR 态**，反向自检要「故意写错必失败」。
- **Vue 传不存在的 prop / 绑不存在的字段** = 静默失效（渲染空串、门控恒开、录入不落库），四层全查不出，只有浏览器挂载才暴露。判「某能力接没接」要落到**唯一消费方 + 有渲染宿主**，不能只 grep 符号名。
- **截函数体禁固定字符窗口、禁 `strip_comments` 剥 SQL**：一律花括号/圆括号配对 + **先跳参数列表**（TS 返回类型注解 `): Promise<{...}>`、Python 多行签名都会骗到「第一个 `{`」）；`strip_comments` 会把 `sa.text("""...SQL...""")` 一起剥掉。
- **磁盘真相与编码**：`read_file` 对并发/自己刚改的文件返回**陈旧版本** → 判磁盘一律 `python -c "open(p,encoding='utf-8').read()"`；PS `>`/`Out-File` 会把 python 的 UTF-8 中文腌成乱码 → 脚本内 `Path.write_text(encoding='utf-8')` 或 `cmd /c "... > f 2>&1"`；含 emoji/中文的破坏性脚本先 `$env:PYTHONIOENCODING='utf-8'`，判成败查数据不看 exit code（`--apply` 常被 Ctrl+C 中断但写入已提交）。
- **pytest 一律从仓库根跑**（从 `backend/` 跑用相对路径的测试会 `FileNotFoundError` 假红 17 例）；连库守卫用**一次 `asyncio.run` 取全部快照**（每测试各自 async 会污染共享连接池，第二个起 `NoneType has no attribute send`）；`-k "a or b"` 经 shell 会被拆成多个位置参数 → 用 `subprocess.run([...])` 不经 shell + 加「passed<N 即中止」自检。
- **改共享数据文件前 grep 其他 active spec 是否也要改它**（`note_template_*.json`/`prefill_formula_mapping.json`/`report_config` 等是回退高发文件）；并发会话会互相回退，**幂等脚本 `--check` + 契约测试**是唯一可靠恢复手段，测试红了先重跑对应 `scripts/fix/fix_*.py`。
- **三件套校验（`get_diagnostics` 对 `.kiro/specs/**/*.md` 生效）**：`### Property N` 只认整数、`**Validates: Requirements X.Y**` 只认 `X.Y`、tasks 的 `## Task Dependency Graph` 必含 waves JSON。除机器校验外还要人工核：**未被引用的 AC**（悬挂 0 也可能整条 Requirement 零实现）+ **design 承诺的新函数/新取值是否真在生产代码 grep 得到**。
- **改 .md 禁用 `index()` 算边界**（会一次删掉整段，Markdown 无结构校验查不出）：一律 `str_replace` 传完整旧文本；非要脚本切片则边界用行首锚点 + assert + 改完做结构核验（`### `/`## ` 计数、字符数、尾部锚点）。**Kiro local history**（`%APPDATA%\Kiro\User\History\<hash>\entries.json`）可恢复误删、也可取证「文件被谁何时覆盖」。

## 关键引用

- spec 状态 → `.kiro/specs/INDEX.md`
- 领域术语 → `glossary.md`（inclusion:always）
- 底稿内容结构权威来源 → `基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/`
- 附注章节号权威源 → `backend/data/note_template_variant_matrix.json`
- 附注 section↔wp 映射真源 → `backend/data/note_workpaper_sync_registry.json`
- 报表科目映射真源 → `report_config` DB 表（非 `formula_presets_seed.json`）
