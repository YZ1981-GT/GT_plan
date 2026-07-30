---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤200 行**。明细下沉：完成事项 → `#dev-history`；架构决策 → `#architecture`；踩坑/编码约定 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；启动 `start-dev.bat`（后端 9980 + 前端 3030）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**；**optional(*) 任务也要做完**
- **🔴 codegraph 优先于 grep**：146k 节点/312k 边/8673 文件；grep 仅用于非符号纯文本
- **触类旁通**；**改动前先 spec 三件套**（>500 行 / 3+ 组件 / 跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表/附注金额默认「元」**；**中文场景全链路不能崩**
- **不要考虑轻量**：要针对性、联动性、美观性、实操性、易懂性；审计 UI 必须有逻辑追溯能力
- **死代码立即删除**（不留 DEPRECATED/fallback 注释，否则每次复盘重复提议）
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- **spec 归档按功能分类**（05-business-features / 04-infra 等），不按日期批次
- 目标并发 6000 人；底稿编码 = 致同 2025 修订版
- 5 角色轮转：审计助理 / 现场经理 / 业务合伙人 / 质量控制复核合伙人 / EQCR 技术复核人
- **v3.0 愿景（当前不做）**：项目级知识自动提取 + 跨年度续审继承

## 平台级 UI/数值铁律

> 完整机制与代码位置见 `#architecture` §平台级数值格式 / §表格 UI 规范。

- **金额格式单一真源** = `stores/displayPrefs.ts` 的 `fmtAmount()`（千分符 + 2 位小数 + 默认「元」+ localStorage 持久化）。只读金额一律走它。
- **防折行全局** = `styles/global.css` 的 `.el-table td.is-right .cell{white-space:nowrap;font-variant-numeric:tabular-nums}`。
- **🔴 可编辑金额千分符只能用 `el-input`（2026-07-29 已定论，双证）**：①源码 —— EP **2.13.6** 的 `node_modules/element-plus/es/components/input-number/**` 全文无 `formatter`/`parser`，该 prop 不存在；②浏览器实测 —— `el-input-number :formatter` 下输 1234567.5 显示 `1234567.50`（**无千分符**），换 `el-input` 后显示 `1,234,567.50`。故平台现存 40+ 处 `el-input-number :formatter`（K1TabDisclosureListed·Soe / K1StageEclTable / E1TabCashCount / E1TabCreditReport）**全是空操作，千分符从未生效**；`wpAmountInput.ts` 的用法注释写错。→ 统一用 `components/workpaper/shared/WpAmountInput.vue`（失焦千分符 / 聚焦原始值便于编辑 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）；存量替换待单独 spec 收口。`:precision="2"` 是真 prop 可留。**绝不套用**利率/汇率/比例/笔数/年度/月份。
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

- **A~N + S 全部循环底稿 100% 完成**；基础设施 100% 完成
- **Active spec = 9**（并发会话 2026-07-30 新建 `d1-notes-receivable-disclosure-alignment` 26 任务 / `n1-deferred-tax-disclosure-template-alignment` 53 任务）。**🔴 `f2-inventory` 11.3 与 `disclosure-columns-coverage` 12.3「单 commit」不可按 spec 切分**（实测 381 改动文件：f2 专属仅 8 个 / columns-coverage 专属 9 个，但两者的核心交付都落在 `note_template_{listed,soe}.json`·`disclosure_engine.py`·`note_sub_table_projector.py` 这些**被 8 个在飞 spec 同时改**的共享真源上；仓库历史本身也是按层分批 commit，非按 spec）→ 待用户定提交口径，**不得假绿**：`d2-ar-disclosure-soe-alignment`（**实现 25/25 完成**：国企 八、5 底稿 6 处结构欠账 + 附注 11→13 表 + 附带修掉核销表假父表头、国企多推的「1年以内小计」行；**遗留 2 项待用户定口径**见下）/
  `d2-ar-disclosure-template-alignment`（**31/31 全完成**：Task 10 交互实测已补 —— 上市 TAB 正确挂载证明 wp_code 后缀分发修复生效，落库 §五、5 共 12 表、分类披露与续表各 6 列两级表头、`text_content` 10 节说明齐备；实测顺带修掉 `D2DisclosureNoteBody.vue` **缺 `portfolio` 说明文本域**（`D2_NOTE_TEXT_SECTIONS` 声明 10 节、AI 也备好上下文，但没文本域 → AI 生成的组合说明看不见改不了、同步永远只落 9 节））/
  `f2-inventory-disclosure-template-alignment`（**全部任务完成**，含多区块导入导出；前端 95 + 后端 123 绿；仅剩 commit）/
  `disclosure-columns-coverage-rollout`（**2026-07-30 本轮：R8(16) 补勾完成 / R6 账龄口径 6 循环全收敛(13.6，守卫 15/15 strict 绿) / R7 孤儿清理 14.5·14.6 实测通过 + 新增 14.7 基线播种(R7.5)**；顺带修 3 个实质缺陷：D2 披露 sheet 分发被 wp_code 后缀抢占（披露组件此前完全挂不上）、D3 静默校对 `section1Subtotal.current` 恒 0、`（续：期初数）` 续表键双真源。前端 `src/components/workpaper` 全量 1294 文件绿 / 失败 86 全在未触碰文件（较改动前 −1 文件 −1 例，新增 43 例通过）。**待做**：3.3 Playwright 复验 / 批1~4（14 Tab 补 `columns`，CI job 现为红）/ 10.2 / 11.x / 12.x 收尾。**原 Task 16 说明**：`sheet_name` 断言漂移 10 条全修（改引用 `X_DISCLOSURE_SHEET_NAME` 常量，非改字面量）+ 守卫 `disclosureSheetNameRegistry.spec.ts` 6/6 绿：`sheet_name` 断言漂移 10 条全修（改引用 `X_DISCLOSURE_SHEET_NAME` 常量，非改字面量）+ 守卫 `disclosureSheetNameRegistry.spec.ts` 6/6 绿；全量 sheet_name 类失败归零（87 条剩余失败全在未触碰文件）。**Task 4.2 已补**（allowlist `reason` 必填，空白视为未登记）；**Task 13/14 (R6/R7) 由并发会话完成**（共享模块 + D2 全链 + F1 改用共享表，本会话误覆盖后已复原，125 测试全绿）；**Task 1/2/3.1/3.2 经实测确认早已在 F2 spec 内落地**（`ColumnDef.flat` + `defineColumns` 透传 + 4 条透传断言 / 后端三态 `is None` 守卫 + 30/30 测试 / F2 房企 3 表+数据资源标 flat + 反向断言）。**待做**：3.3 Playwright 复验 / 4.2 allowlist reason / 批1~4（14 Tab 补 `columns`，CI `disclosure-columns-coverage` job 现为红）/ R6 账龄标签方案A / R7 动态孤儿表清理）/
  `k1-other-receivable-disclosure-alignment`（**已完成**：底稿两版补齐源模板 10/8 段 + 附注 §五、8 18 表 / §八、9 15→19 表 + 全表 guidance + 6 表两级表头；**含可选 6.8**：vue-tsc 全项目已跑通，见踩坑铁律）/
  `f1-prepayment-disclosure-template-alignment`（**已完成**：两版按账龄表 3 列→5 列两级表头 + 小计/减：减值准备/合计 三行尾；上市超1年表改「账面余额/占比/减值准备」（原因移入 `type="expand"` 行 + 「据此生成说明」）；国企第 3 表消重名、上市第 3 表「单位名称」→完整表名 + `_removed_table_keys`；6 表补 columns/guidance/空白行骨架；国企逐段减值准备同步时聚合为一行。脚本 `fix_note_prepayment_structure.py` + **存量回填 `backfill_note_prepayment_snapshots.py`**（4 条空骨架已回填、1 条有数据按安全门跳过）；后端 44 + 前端 58 全绿；国企底稿 + 附注 §八、7 Playwright 实测通过（5 年段 6 档联动正确）。上市变体活体未测：**8 个在册项目 `applicable_standard_v2.entity_type` 全为 soe**，唯一 listed 适用项目已软删）/
  `disclosure-sync-path-buildout`（**批1（G 循环）已收口**：Task 1 脚手架 + G4/G5/G6/G8/G9/G12 全部完成，**缺口 64→60→50→49**。G6 上市是整体重写（旧组件自造 7 虚构小节 + 137 行 `成本项目N` → 按权威模板重建 6 小节/14 表，新增 `g6ListedDisclosureRows` / `useG6DisclosureListed` / `g6NoteSectionMap` / `g6DisclosureSyncPayload`，52 契约测试），**G6/G12 均已浏览器实测**（不点按钮 3s 自动落库、两级表头 group 落 `_sub_table_columns`、清空后 `last_sync_at` 二次前移）。已建 `fix_note_g_cycle_structure.py`（幂等/`--check`/CI job `note-g-cycle-structure`）+ 4 份 `gXNoteSubtableContract.spec.ts` + `test_note_g_cycle_structure.py` 439 测试。**下一步**：批2 H(6)→L(12)→M(19)→N(7)→D2·F4·J2(5)）/
  `disclosure-note-follow-actual-content`（**平台级；wave 1+2+6 已完成 5/13**：空表判定双侧同口径（各 38 测试镜像）+ 模板差异计算五类（`diff_tables`/`diff_section`/`diff_project` + 诊断脚本 `diagnose_note_template_drift.py`，29 测试）+ legacy 迁移 dry-run 四类分类（`migrate_legacy_note_snapshots.py`，`--apply` 暂 BLOCKED，32 测试）；**wave 2 自动同步**：修 F2 触发条件（原只 watch 提示横幅）+ 清 5 个半接/死 import + 覆盖率守卫 13 测试 + 后端兜底 stale marker 43 测试。**待做**：4.7 Playwright 实测（MCP 断连）/ 4B 推广 60 个未接入 Tab / wave 3~6 模板回流·破坏性迁移·空表折叠）/
  `procedure-delegation-visibility-isolation`（并发会话推进）
- **工作树不干净**（多会话并发改动 + 根目录残留 `tmp_*` / `_fresh_d2*.txt`）；**Chrome 实例被多会话共享**，驱动 Playwright 前先确认当前 URL
- **🔴 并发会话会互相回退同一文件**（实测 2 次：`disclosure_engine.py` 新增函数 + `note_template_listed/soe.json` 的存货对齐、其他应收款对齐各被回退一次）→ 幂等脚本 + 契约测试是唯一可靠恢复手段，测试红了先重跑对应 `scripts/fix/fix_note_*_structure.py`；**多 spec 改同一批文件时不要并行推进**
- **🔴 新建共享模块前必先 grep 消费方**：`git status` 显示 `??`（未跟踪）**不等于不存在** —— 并发会话可能已建好并接线。本会话用 `fs_write` 整文件覆盖了别人已写的 `disclosureAgingLabels.ts`/`disclosureSyncedTables.ts`，打断 D2/F1 的 import（git 无法恢复，靠对方**路径不同**的契约测试 + 调用点才还原 API）。**规矩**：① 可能已存在的文件用 `str_replace` 而非 `fs_write`；② 改共享模块后 `get_diagnostics` 必须查**全部消费方**，不只查自己新写的文件；③ **tasks.md 的 `[ ]`/`[~]`/`[x]` 标记不可信**（对方完成不回写、IDE 还会自动标绿）→ **以代码 grep 为准**
- **🔴 禁用 `git stash` 做基线对比**：stash 期间并发会话/IDE 缓存会把那些文件回写成**另一版本**，`stash pop` 必冲突且丢自己的改动（本次踩中，靠幂等脚本 + 增量 str_replace 恢复）。要判「失败是否预存在」改用：看失败断言是否触及本次改动的符号 / 单独跑该测试文件
- **分支** `work/2026-05-30-wp-specs`；**最高迁移 V133**（以 `migration_status` 实测为准）

- **run-all-tasks 侦测噪声**：`.kiro/specs/_archive/` 下 6 处归档 spec 残留 `- [-]` / `- [~]` 标记（consol-phase1/2、voucher-sampling-hardening、schema-drift-full-sync 等），批量编排器扫 `specs/**/tasks.md` 会误判为"被中断" → 侦测须排除 `_archive`；活跃 6 spec 实测均为 0

### 已知遗留（低优先，无 spec）

- 附注三灰度开关默认关（`DISCLOSURE_NOTE_FORMULA_ENABLED` / `RAG_ENABLED` / `CONSOL_NOTES_V2_ENABLED`）待项目 opt-in；RAG 须先补知识库索引
- `report_note_linkage.json` 仅 1 条 seed（BS-002 货币资金）→ stale 分级的 `report` 定向分支基本空转；补映射须逐节人工核对源模板后**同时加入 `test_report_note_linkage_diagnose._VERIFIED_SEED_ROW_CODES` 白名单**（守卫只禁批量派生、总数 ≤5，不禁人工核实 seed）
- **账龄披露口径单一真源 = `composables/disclosureAgingLabels.ts`**（用户定方案 A：同步层映射，项目账龄配置继续只服务底稿内部）。`toDisclosureAgingLabel(seg, overrides)` / `lookupDisclosureAgingLabel(key, overrides)`（后者未命中返回 undefined，供自定义回退链）/ `buildDisclosureAgingLabelMap(overrides)`（供已有 `X_NOTE_AGING_LABEL` 常量的循环收敛）/ `DISCLOSURE_TOTAL_LABEL`（`合 计`）。**国企首档字面单一真源 = `DISCLOSURE_AGING_WITHIN1_SOE` + `SOE_AGING_OVERRIDES`**（D2 soe / F1 soe / F4 / D3 soe 四处统一引用，禁各写 `'1年以内（含1年）'`）。**已收敛完毕**：D2/F1/F4/K1/G5/D3，守卫 `check_disclosure_aging_label_coverage.py` 按循环判定 **15/15 · `--strict` exit 0**；**D6/D7 是假阳性**（只出现「账龄」二字，与档位无关），信号已收紧为 `agingRows|agingSegments|AgingSegment|AGING_BANDS|AGING_LABEL`
- **🔴 `DISCLOSURE_TOTAL_LABEL`（`合 计`）不可全局硬套**：D3 附注模板（五、38 / 八、38）合计行字面就是 `合计`（**无空格**），套了反而制造漂移 → 结构行映射只对**已实证**的章节用；D3 只映射账龄段数据行，合计行原样透传（`d3NoteSubtableContract.spec.ts` 正向锁死）
- **孤儿子表清理单一真源 = `composables/disclosureSyncedTables.ts`**（`dataTableNames` / `buildRemovedTableKeys({previouslySynced, legacyObsolete, pushed})`）：底稿持久化「上次同步表名」`{prefix}synced-tables`，同步**成功后**才 `markSynced`（失败也写会把现存表当孤儿删）。静态遗留键降级为 `legacyObsolete` 种子。
- **R7.5 基线播种（已落地，解决「上线前既存孤儿表不自愈」）**：同模块 `TableNamespaceSpec` / `isOwnedTableName` / `noteExistingTableNames` / `seedSyncedTableBaseline`；D2 声明 `D2_TABLE_NAMESPACE`（固定表名全集 ∪ `组合计提项目：` 前缀 ∪ `（续：期初数）` 后缀 ∪ 上市历史静态旧名），`useD2DisclosureNote.seedSyncedTablesFromNote(table_data)` 首次同步前播种（清单非空即幂等空操作），HTTP 留组件层。**谓词宁漏不误杀**（同章节可被别的底稿推送）；续表只认「已知表名+后缀」；**只取 `sub_table_data` ∪ `_sub_table_columns` 的键**（`_tables` 是读时投影，removed 键删不动，纳入只会虚报）。实测 §八、5 13 表→11 表清掉历史孤儿，再同步 11→11 稳态
- **🔴 `applicable_standards` 前端全链缺失 → D3 上市/国企披露 Tab 对所有项目都显示「当前项目不适用…」**（2026-07-30 实证）：`/api/projects/{id}` 响应体**不含任何 standard 字段**（库里 `applicable_standard_v2 = {scope,stage,entity_type}`）；`useWpRenderSchema` 显式写 `applicable_standards: undefined`；`GtD3PrepaidAccounts` 只从 `htmlData` 取 → 恒为 `''`。且共享 `normalizeApplicableStandards`（`useF2FormData.ts`）对 v2 对象只认 `type/code/value`，不认 `{entity_type, scope}` → 即便后端补字段仍返回 `[]`（**应派生 `soe_standalone`**）。属跨前后端 schema 变更 + 影响全部 gating 循环（F1/F2/F3/D1/D3/D5/G*/I*/K* 等），**须先立 spec**
- 11 张空 `note_*` 表 + 2 张备份表待清理（破坏性，须显式确认）
- 6000 VU 容量压测待专用环境（工具链已就绪）
- 大文件技术债：`g7_consol_linkage_service` 2267 行 / `G7TabAdjudication` 1200+ 行 / `event_handlers` / Top-5 巨型 Vue

## 踩坑铁律

> **完整清单（后端/前端/OnlyOffice 各 30+ 条）见 `#conventions`**。最高频三条：

- **🔴 禁用 PowerShell `Set-Content`/`Get-Content` 操作 .vue/.md**（破坏 UTF-8 中文 + 加 BOM）→ 只用 `str_replace`/`fs_write`；批量改用 Python 显式 `encoding='utf-8'`
- **🔴 Playwright MCP 断连（`Not connected`）时的替代方案**：用 **chrome-devtools MCP**（`list_pages`/`new_page`/`evaluate_script`/`fill_form`/`click`/`navigate_page`）驱动浏览器 + **postgres MCP** 只读比对落库结果。这套比截图更硬（直接验 `_last_sync_at`/字段值），2026-07-30 的自动同步实测就是这么做的（登录 `admin`/`admin123`，底稿 URL = `/projects/{pid}/workpapers/{wpId}/edit`；HMR 旧错误覆盖层会残留，判真实状态先 `navigate_page reload`）；缺点是要自己写 `dispatchEvent('input'/'change'/'blur')` 模拟录入
- **🔴 长命令会打崩 PSReadLine**（`SetCursorPosition ... top 为负` 后终端持续吐异常，输出不可读）→ 长/多参命令走 `control_pwsh_process` + `> file 2>&1` 再 `read_file`；**别用 PS 重定向存 JSON**（会按控制台宽度折行导致 JSON 损坏），用 `curl.exe -o` 或 python 落盘。**🔴 `vue-tsc --noEmit` 全项目其实能跑通**（2026-07-30 推翻旧结论）：`NODE_OPTIONS=--max-old-space-size=32768 npx vue-tsc --noEmit -p tsconfig.json`，约 5~6 分钟；8 GB / 12 GB 都 OOM，机器本身 189 GB 不是瓶颈。**12 GB 那次"看起来成功"是在语法错误处提前 bail**，别当通过。基线 **3380 errors / 881 files**（多为 `el-input-number @change` 签名，TS2322 1779 条）。**它能查出 Volar 逐文件诊断 + vitest 全查不出的三类问题**：SFC 语法级损坏（`{{ x }.` 少括号 / 多余 `}` → Vite 实为 500）、共享类型不兼容波及多循环（helper 的 `[k: string]: unknown` 索引签名让 8 个循环的契约 spec 全报 TS2322 —— **带索引签名的类型不能从无索引签名的 interface 赋值**）、引用不存在的字段（11 个宿主读 `runtime.applicableStandards`，`WorkpaperRuntimeContext` 里没这字段 = 死 fallback，正是「变体门恒开」的类型层证据）→ **日常仍用 `get_diagnostics` 逐文件，收口/验收跑一次全项目**
- **🔴 `readFile` 对「本会话已修改 / 并发会话在改」的文件会返回陈旧版本**（实测 3 次：`d2NoteSectionMap.ts` 返回 HEAD 版、`useD2DisclosureNote.ts` 显示已删除的旧函数、测试文件断言与实跑结果相反）→ 判定落盘真相一律 `python -c "open(p,encoding='utf-8').read()"`；`read_file` 还按路径缓存，同名临时文件会读到上一次内容 → 落盘用**每次不同的文件名**
- **🔴 改前先确认函数是否已存在**（本次给 `disclosure_engine` 加列元数据透传，实为重复造 `_carry_seed_column_meta`，靠 `inspect.getsource` 显示的实现与"我写的"不一致才发现）→ 加公共 helper 前先 `grep def <name>` + 看是否已有姊妹 spec 的未提交测试在引用
- **🔴 Playwright 认证 token 在 sessionStorage（不跨 page 共享）**→ `page.context().newPage()` 开的新页面必被重定向到 `/login`，**无法用开新页面规避并发会话抢占**。只能复用已登录 tab，并把「goto + 点 tab + 等选择器 + 读取」全部压进**单个 `run_code_unsafe` 原子脚本**（分步调用之间会被别的会话导航走，实测 3 次）。读多变体 tab 时选择器必须带组件根作用域（`.h1-tab-disclosure-soe .xxx`），否则 `querySelector` 取到的是另一个 tab 已挂载的同名节点
- **披露内部勾稽校验范式**（H1 首建，可复用到各循环）：纯函数引擎 `h1DisclosureConsistency.ts`（`eqCheck` 相等类容差 0.01 元 / `subsetCheck` 子集类，返回 `{label, rule, left, right, diff, level, detail, refs}`）+ 展示组件 `H1DisclosureConsistencyPanel.vue`（紧凑单行 bar + 折叠明细表 + 规则 tooltip + `GtIndexChip` 追溯）。校验项只取**源模板可判定**的勾稽：汇总表↔变动表账面价值、子表对主表的子集约束、模板「—」列示约定（如土地不提折旧/减值）、源模板红字要求的联动（如政府补助须在「其他减少」列示）
- **🔴 崩溃类 bug 以 Vite transform 为权威**：`curl.exe http://localhost:3030/src/.../X.vue` 看 200/500。`get_diagnostics`(Volar) 查不出 SFC 结构损坏/import 解析失败/未声明 binding/`export` in script-setup；HMR 长开页面会累积旧态，判真实状态必全新导航
- **🔴 `note_template_*.json` 是 md 重建产物**（`scripts/fix/rebuild_note_from_md.py` 会压扁多级表头、把双期两张表并成一张）→ 结构修订必须做成**幂等脚本**（`scripts/fix/fix_note_ar_listed_structure.py` / `fix_note_inventory_structure.py` 范式，带 `--dry-run` / `--check` + `_aligned_by` 标记）+ 契约测试兜底，禁止直接手改 JSON；压扁的第二行表头会残留成 `row_type: header_label` **假数据行**，修订时必删
- **🔴 附注两级表头唯一机制**：`ColumnDef.group` →（后端 `note_sub_table_projector._extract_column_groups`）→ `_column_groups`，消费方 `DisclosureEditor.activeTableColumns`（嵌套 el-table-column）+ `note_word_exporter._build_two_level_header_rows`。**不要新建机制**；同步载荷别把两级压平成「期末账面余额」，用 `label` 子列名 + `group` 父表头。seed 路径另需 `disclosure_engine._carry_seed_column_meta` 透传（`_build_table_data` 只返回 `{headers, rows}` 会丢弃 `columns`/`_column_groups`）
- **`_extract_column_groups` 三态**：`None`=未声明（回退 `_infer_groups_from_headers` 前缀推断）/ `[]`=任一列带 `ColumnDef.flat` 即显式单级（禁推断）/ 非空=显式分组。**源模板单行表头的表必须标 `flat`**，否则 `本期增加`/`本期减少` 会被反猜出凭空的「本期」父表头（F2 房企 3 表 + 数据资源表已标）
- **🔴 `_source=workpaper` 时底稿推送是唯一权威**：投影器只渲染推过来的 `sub_table_data`，**不与模板 `_tables` 合并** → 模板 seed 的示例组合/账龄档位一旦同步就被完全覆盖，其定位只是「骨架 + 示例」（给从未同步过的项目看）。所以「结构要按实际项目走」靠推送侧解决，不是改模板
- **🔴 披露自动同步机制早已存在 = 前端 `useDisclosureAutoSync`**（防抖 800ms + 复用各 Tab `syncToDisclosureNotes` → 与手动按钮同源幂等）。**后端做不了自动同步**：`sub_table_data`/`columns` 由前端 `buildXSyncPayload` 算出，`WORKPAPER_SAVED` 的 extra 只有 `{wp_id,wp_code,trigger,item_ids,atomic}`（无 sheet_name/表结构），后端重建会把每个循环载荷逻辑双写。后端只做兜底 `disclosure_stale_marker`（标 `is_stale`，覆盖导入/API 直写/后台重算等绕过前端的路径）
- **🔴 披露 Tab 同步链路实测（154 个 `*TabDisclosure*.vue`，2026-07-30 定稿）**：**90 有链路**（65 自有 `syncToDisclosureNotes` + 25 用别的 syncFn 走 autoSync）/ **64 无链路**（三个标记全无 → 披露数据只停在 `checklist_responses`，附注**永远拿不到**；抽查 N2/L2 确认 `disclosure-notes` 端点 0 命中）。「有同步能力却未接自动同步」实测为 **0** → 缺口不是"没接自动同步"而是**压根没有同步入口**，这是 572 个 legacy 章节的根因之一。收口 spec = `disclosure-sync-path-buildout`（按循环分 6 批），清单固化在 `disclosureAutoSyncCoverage.spec.ts` 的 `MISSING_SYNC_PATH`（只允许变短）
- **🔴 变体薄壳（`<Base variant="x" v-bind="$props" />`）两个坑**：①**守卫要做委托解析**，否则虚报缺口（G10/G11 的 Listed/SOE 各 15~21 行薄壳，链路在 Base 里 → 缺口从 64 修正为 60；`disclosureAutoSyncCoverage.spec.ts` 已加 `resolveDelegate`，反向自检用**替身**不绑真实循环）；②**薄壳漏声明 prop = 静默锁死**（`v-bind="$props"` 只转发**已声明**的 prop，G9 两壳原无 `projectId` → Base 接了同步按钮也永久 disabled）
- **🔴 `sync_from_workpaper` 定位键只有 `(project_id, year, note_section)`，`current_standard` 不参与匹配**：而国企项目的「五、xx」是另一套压缩编号（实测项目 2aa00f57：`五、19`=应付职工薪酬 / `五、20`=应交税费）→ 在国企项目上编辑**上市**披露 TAB 会把数据写进错误章节。本应由 `isXDisclosureApplicable` 拦，但 `applicableStandards` 前端全链缺失（恒 `[]` → 门恒开）。约 90 个已接链路 Tab **共有**此风险，根治须单独立 spec
- **🔴 新 `build*Columns` 必须登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`**，且**变体入参型 builder 不能叫 `buildXColumns`**（会被 sweep 用空入参调用 → 列头为空触发 Property 6）→ 参数化的命名 `gXColumnsFor(variant)`，对外只导出零参 `buildXListedColumns` / `buildXSoeColumns`
- **🔴 `gen_note_wp_sync_registry.py` 曾有跨语句正则 bug**：`_DISCLOSURE_SHEET_(...)[^=]*=` 会让**文档注释里提到的常量名**咬到下一条语句的等号（实测把 G12 两个变体都写成 `listed`）→ 已锚定 `const/let/var` 声明；写映射文件的注释时也别原样写常量名
- **🔴 seed 常量可能本来就是错的（零消费方的死常量）**：`G8_MAIN_SUBTABLE`/`G9_MAIN_SUBTABLE` 原值指向不存在的表 / 第 2 张表 → 接同步前必须逐字核对模板 `tables[].name`，别信既有常量
- **🔴 `emit` 不算同步链路**（曾据此把缺口低估为 27）：37 个 emit 型披露 Tab 的事件只有 `navigate`(27) / `imported`(7) / `disclosure:note-text-updated`(5)。前两者与同步无关；后者消费方 `useNoteRefresh.onDisclosureNoteTextUpdated` 仅 `fetchDetail` 刷新界面且首行 `if (!currentNote.value) return`（附注页未打开直接返回）→ **不推数据落库**。判断"有没有同步链路"只认 `syncToDisclosureNotes` / `sync-from-workpaper` / `scheduleAutoSync`
- **🔴 F2 曾是"假接入"**：只 `watch(dataUpdatedVisible)`（上游更新提示横幅的可见性），用户自己改数据一律不触发 → 接自动同步必须监听**实际数据**（与 `syncToDisclosureNotes` 构建载荷所用字段一致）
- **🔴 `_xxxMounted` 一次性防护会吞掉编辑（L1/L3 等在用，是 bug，勿照抄）**：防护消耗时机取决于「数据是否已加载」—— 首次挂载时 `allResponses` 异步填充让 computed 变化并消耗掉防护；但**切走再切回**时数据已在、computed 不变、watch 不触发、防护未消耗 → 吞掉回到本页后的**第一次真实编辑**（浏览器实测：`checklist_responses` 已存但附注 `_last_sync_at` 不变，同一挂载内再改一次才同步）。Vue `watch` 默认 `immediate:false` 挂载本身不触发，**无需防护**；数据加载引起的那次同步反而是有益的（幂等 + 空载荷 no-op）
- **🔴 附注 legacy 快照全库规模（2026-07-29 dry-run）**：**572 个章节**仍是生成时快照（`sub_table_data` 空 + 有 `rows`/`_tables`），占有差异章节的 **98.9%**；共 982 张待迁移表里 **950 张（97%）在模板里也没有 `columns`** → **直接迁移比现状更糟**（投影降级为只显示行名，legacy 至少有 headers）。脏数据：58 章节有重名表（按 name 建键会覆盖丢表）、79 章节表名是表头首格「项  目」。→ **跨 spec 依赖：`disclosure-columns-coverage-rollout` 补完 `columns` 才能做 legacy 迁移**
- **🔴 附注根本不跟随底稿内容（2026-07-29 实证，6 条 `note_section IN ('五、9','八、10')` 记录）**：只有人工点过「同步到附注」的那 1 个项目 `sub_table_data` 有 9 张表，其余 5 个项目**全是 0 张**，界面显示的是生成时持久化的旧 `rows`/`_tables` 快照（3 张表 + 已从模板删掉的 `header_label` 假数据行）→ 底稿保存未接 `WORKPAPER_SAVED` 自动同步、模板升级不回流既有项目、脏快照与 `sub_table_data` 双真源。收口 spec：`disclosure-note-follow-actual-content`
- **🔴 改模板 JSON / 改前端载荷代码对既有项目一律不生效**（实测：F2 存货 14 张表补 `guidance` + 5 张补 `flat` 后，拉真实后端投影仍 guidance 全 0 字、`（续）`表 `_column_groups=None`）→ `guidance` 只经 `disclosure_engine._carry_seed_table_guidance` 在 **seed 路径**生效；`_sub_table_columns` 是上次同步写入的旧值。交付说明必须写清「新建项目/重新生成才可见」，别把"模板改了"当成"用户看到了"
- **🔴 `flat` 必须同时加在「同步载荷」与「模板 JSON 的 `columns`」两处**：只加前者会让 **seed 路径**（新建项目/重新生成附注）继续被 `_infer_groups_from_headers` 塞凭空父表头。实测模板 columns 无 flat 时：开发产品→凭空「本期」+「期末」、周转房→「本期」、开发成本→**「预计」**（把「预计竣工时间」与「预计总投资」凑成一组）。守卫必须覆盖 seed 路径，只测同步载荷会漏
- **🔴 `disclosure_notes.table_data._tables` 是生成时快照**：改 `note_template_*.json` 只对**新建项目 / 重新生成附注**生效，既有项目 TAB 数不变；「🔄 恢复模板结构」只重置当前单表（`templateStructure` 返回单个 `{headers,rows}`），**不新增表**。改完模板须在交付说明里写清此点。**存量修复范式** = `backend/scripts/fix/backfill_note_prepayment_snapshots.py`（默认 dry-run / `--apply` / `--check`；安全门：`_tables`+顶层 rows+`sub_table_data` 任一格有值即跳过，改由底稿「同步到附注」整表覆盖）
- **🔴 附注 `tables[].guidance` = TAB 页签编制提示**（K1 §五、8 / §八、9 共 37 张表首次启用；H1 §五、22 6 表 + §八、22 5 表已跟进）：内容只许取源模板红字 / 附注模版括注 / 15号文条款，或以「勾稽：」前缀标注的工具提示。seed 显式 guidance 经 `disclosure_engine._carry_seed_table_guidance` **优先于** `per_table_guidance` 段落游标推断（仅已声明的表受影响 → 其余 300+ 章节零回归）。
- **🔴 模板 `rows` 里的占位说明是假数据行**：源模板「可无限量添加行」（H1 上市 A65 闲置表 / A74 租出表）被 md 重建脚本当数据行落进 `rows`，会渲染成一行空披露数据 → 必删，语义移入 `guidance`。同类还有压扁的第二行表头残留成 `row_type: header_label`
- **🔴 `……` 占位列头必须展开成实际类别**：H1 上市「固定资产情况」headers 原样保留源模板 E13 的 `……`，而底稿 `buildH1ListedColumns` 按 `H1_LISTED_DEFAULT_CATEGORIES` 推 5 类 → 附注侧「办公设备/其他设备」两列无落点（孤儿列 + 数据丢失）。展开依据 = 源模板红字「此处分类应与固定资产项目注释的分类保持一致」+ 平台共用口径 `H1_FA_CATEGORIES`（**电子设备归一到办公设备**，`normalizeFaCategory` 显式约定，不要按会计政策表的「电子设备」去改底稿默认类别）
- **🔴 披露列结构三源裁决**：底稿源 xlsx / `附注模版/*.md` / `note_check_preset_formulas.json`（`{循环}{节号}-n` 如 F7-1~F7-14，按 `listed`/`soe` 两份）三者冲突时，**校验预设是裁决者**（它直接写明「上市版②表无『账龄』『未结算的原因』列」「③表无减值准备列，跳过」「合计行 = 小计行 − 减值准备行」）。`consol_note_sections_{listed,soe}.json` 可作第 4 方印证。**附注是交付物 → 列结构随附注模版 + 校验预设；底稿可多留审计列，但同步时必须投影成附注形状**（F1 国企逐段减值准备列 → 聚合为「减：减值准备」行）
- **🔴 行型判定必须先去空白**：源模板写的是「小 计」「合 计」（中间带空格），`startsWith('小计')` 会漏判 → 小计/合计行被当普通数据行推给附注，丢 `is_total`、加粗与勾稽（G4 载荷曾中招）。同理阶段表的「其中：」结构行不能省（附注是交付物，缺了看不出明细归属），空值列写 `null` 保列键齐备。**但结构标签不能同时当明细行默认名**：`emptyDetail('其中：')` + 载荷单独发 `whichRow()` → 附注出现两行「其中：」（一行全零幽灵数据行，G4/G6 共有，浏览器实测才发现）→ 默认名留空 + 共享谓词 `isPlaceholderStageDetail()`（无名或名=结构标签 且 金额全零）在载荷侧跳过空白骨架行
- **🔴 披露子表名契约**：`X_*_SUBTABLE` 每个值必须与 note_template `tables[].name` **逐字一致**，且同步 `columns` 的标签列头 = 该表 `headers[0]`，否则同步出**孤儿子表**（附注 TAB 永空 + 底稿数据丢失）。范式：`k1NoteSubtableContract.spec.ts`（含 headers 无空串 / `_column_groups` 齐备 / 全表 guidance 断言）。K1 曾一次性踩中 5 处错位。
- **🔴 披露同步 `sheet_name` = 源 xlsx 中文 tab 名**（如 `附注披露信息（上市公司）`），非 `F2-note-listed` 式 wp_code、也非 `附注上市` 短名 —— 匹配不上会让附注「打开同步底稿」落到底稿首个 sheet；全平台 N1/K1~K13/J1/I3~I6 统一。**8 种括号写法并存**（F1/F3 半角 / G 系全角 / H·I·J·K·M 系 8 处「国有企业」/ D6 混括号）→ **测试断言必须引用 `X_DISCLOSURE_SHEET_NAME` 常量，写死字面量必再分叉**；守卫 = `disclosureSheetNameRegistry.spec.ts`（常量 ↔ `note_workpaper_sync_registry.json` 逐字 + 禁合成标识/短名，`import.meta.glob` 自动纳新循环）。`X-note-listed` 作 **wp_code**（`_WP_CODE_OVERRIDE` / registry 契约 / sheet 归一化输入样本）是合法用法，别一起改
- **🔴 披露 sheet 分发会被 wp_code 后缀抢占**（2026-07-30 Playwright 实测，D2 中招）：`workpaper_sheet_classification` 里 D2-1 的披露 tab 名是 `附注披露信息（国企）D2-1` / `附注披露信息(上市公司）D2-1` —— **尾部带 wp_code**。`GtD2AccountsReceivable.currentSheet` 先跑 `/D2(?:-\d+)?[A-Z]?$/` → 判成 `D2-1` → 渲染「应收账款审定表」，**披露组件永远挂不上**；`get_diagnostics` 与 vitest 均查不出。修法：抽纯函数 `d2Constants.normalizeD2SheetName()`，「附注」判定**前置**于 wp_code 正则 + 「国企」「国有」都认；守卫 `composables/__tests__/d2SheetRouting.spec.ts`。**其他循环若源模板 tab 名也带 wp_code 后缀，同样中招，须逐个核**
- **🔴 sheet 名「国有企业」≠「国企」→ 国企 TAB 渲染上市组件**：**24 份源模板**（H1~H7 / I1~I6 / J1 J2 / K7 / M1~M9）用的是「附注披露信息（**国有企业**）」，而 `Gt*.vue` 的 `currentSheet` 分发普遍只写 `/附注.*国企/` → 不命中后落到末尾 fallback `name.includes('国企') ? soe : listed` → 同样不命中 → **误判成上市**。H1 实测踩中（`.h1-disc-listed` 挂载、`.h1-tab-disclosure-soe` 完全不挂载），`get_diagnostics` 与 vitest 全绿查不出，**只有 Playwright 实测能发现**。已修 H1/H2/H5/H7/I1/I2（H3/H4/H6/H8/H9/I3 早前已修，I4/I5/I6 用 `/附注.*国/` 本就安全）；守卫 = `__tests__/disclosureSheetDispatch.spec.ts`（重放各组件真实正则 + 自检替身）。**新增循环组件必须两种写法都认**
- **🔴 `text_sections` 的 `#### ` 标题行会被丢弃**（`_is_table_title_paragraph` 认 `#` 即标题，标题本身不进任何输出）→ 把实质披露正文写成 `#### xxx` 会**静默丢失**（H1 上市 R84「政府补助金额为XXX元」曾中招，改为无前缀纯文本后才进 `text_content`）。且 `_match_title_to_table_idx` 第 3 级**包含匹配**会把含表名子串的非标题段吞成表标题 → 游标跳位、后续括注错落到别的表（H1 上市 R85 落到表 4 未办证表）。**结论：多表章节的 TAB 提示不要依赖段落游标，一律 seed 显式声明 `tables[].guidance`**（推断为空的表也才有提示 —— H1 国企 5 表推断结果全空、上市汇总表与经营租出表推断为空）
- **`validate_note_docx_placeholders.py`**（2026-07-29 由 `validate_note_template.py` 更名，旧名曾被误当 JSON 守卫）**只校验 docx 模板的 `【`/使用说明/XXXX 占位符**，其 29/103 失败为既有基线 → **附注 JSON 结构守卫**用 `fix_note_*_structure.py --check` + `test_note_*_structure.py`（前者已挂 `governance-checks.yml` 的 `note-inventory-structure` job）
- **🔴 traceback 出现 `D:\GT_workplan\` = `__pycache__` 跨 checkout 残留**（仓库从 GT_workplan 复制而来，pyc 的 `co_filename` 仍指旧路径，pytest 显示 `???` 行）→ 清 `__pycache__` + `.pytest_cache` 即恢复；**清完仍红的是真 bug，不得当"别的 checkout 问题"忽略**（曾据此误判 8 个失败）
- **🔴 AI section prompt 过短会诱导自造披露内容**：`_SECTION_PROMPTS` 里 18~19 字的笼统 prompt（如「请撰写存货附注「分类说明」披露文字。」）等于放任模型自由发挥 → 每条须 ≥20 字且写明源模板/15 号文口径 + 「不得虚构」约束，并用参数化测试守住（范式：`test_f2_ai_generate.py::test_disclosure_section_supported_and_has_prompt`）。新增 section 必须同时登记 `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` + 前端 `F2AiSection` 联合类型 + Tab 内 `AI_TARGETS`，四处缺一即空转
- **🔴 披露页多区块导入导出范式（F2 已落地，其它循环照抄）**：`_f2_disclosure_import_export.py` = 一张 `_Block` 表驱动三形态（`rows` 数组 / `override` 按类别名匹配的覆盖 map / `dr` 三来源列），**一区块一 sheet + 文本域集中「文本说明」sheet**，分发接在既有循环三路由里（沿用 F2-1 模式，不新建 router）。披露 item 全部读写 **`remark`**（`conclusion` 为 null）。两条硬约束：①**行标签重复的表只能按 rowKey 匹配**（数据资源 21 行三段里「1.期初余额」等同名，按标签匹配会静默覆盖 → 首列放「行标识(勿改)」）；②**override/dr 是整表覆盖**（清空某行=撤销覆盖），但整表全空须跳过写库防"拿空模板只导文本"误清。后端镜像前端常量必须用**读 `.ts` 源码的正则契约测试**逐条守（防双真源漂移）
- **🔴 同一批次不得重复提交相同 item_id**：重复会让后端**整批拒绝**、该批全部数据丢失（不是只丢那一条）。**已全量收口**：共享 `useChecklistPersistence` 用 `Set` 天然去重；legacy `useXFormData.debouncedSave` 是单 item 保存无风险；真正暴露点是 `saveBatch(items)` 调用方传重复 id（联动回写「先写整表 JSON、再写汇总字段」最易触发）→ **36 份同形状 `saveBatch` 已统一加按 itemId 去重（后写覆盖先写）**，脚本 `fix_save_batch_dedup.py --check` + CI job `disclosure-sync-hardening`。其它形状（`ChecklistResponse[]` / `{itemId,value}`）语义不同未动
- **🔴 `_xxxMounted` 一次性防护已全平台清除**（10 处：D3×2/D5/D6/D7/E1/L1×2/L3×2，F2 早前已修）：防护消耗时机取决于「数据是否已加载」→ 切走再切回时吞掉第一次真实编辑（浏览器实测）。Vue `watch` 默认 `immediate:false` 本不需要。脚本 `fix_disclosure_mounted_guard.py --check` + 守卫 `disclosureAutoSyncCoverage.spec.ts`（含自检替身）+ CI job
- **🔴 改后端 `.json`/`.sql` 配置不触发 `--reload`**（`wp_code_overrides.json`/`prefill_formula_mapping` 等模块级 `load()` 只加载一次）→ 须改一个 `.py` 触发重载或手动重启

## 披露链路脚手架（2026-07-30 新建，做任何循环的披露→附注对接都先用）

- **开工第一步跑诊断**：`python backend/scripts/diagnose/diagnose_disclosure_sheet_vs_template.py --cycle G4`（只读）→ 一次产出①源 xlsx 披露 sheet 的小节切分 + 推测表头（含两行表头）②模板 JSON 该章节的表名/列数/`group`·`flat` 表态/guidance/headers 含 HTML ③比对提示。参数 `--list-cycles` / `--section-listed|soe`（章节号歧义时指定）/ `--account` / `--out`
- **契约测试用 helper**：`composables/__tests__/_disclosureSubtableContract.helper.ts` 的 `runDisclosureSubtableContract({cycle, variants})`，一次跑 5 条 Property（子表名逐字一致 / 章节号存在 / `group`·`flat` 必表态 / 标签纯文本 / 标签列头对齐 `headers[0]`），各循环接入 ~20 行；`columnsPending` 是逃逸阀（强制写理由 + 已补齐必须移出）。自检 spec 用 K1 真实数据反验 helper
- **🔴 `note_template_variant_matrix.json` 按科目名索引、不含 wp_code**：结构是 `accounts[] = {account_key, section_title, variants:{listed_standalone, soe_standalone, …}}` → 查章节号只能用科目名匹配，「债权投资」vs「其他债权投资」这类会歧义，须人工确认
- **源 xlsx 路径规律**：`基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/**/{CODE} {科目名}.xlsx`，每循环恰好 1 个，共 349 个
- **模板欠账普遍存在**：G4「五、14」13 张表实测**全部 `columns=0` + 全部无 guidance + 裸 `续：` 表名 + headers 被压扁**（「期末重要的债权投资」模板 2 列 vs 源 xlsx 6 列）→ 补同步链路前先修模板，与 `disclosure-columns-coverage-rollout` 工作重叠
- **K1 同步载荷 columns 也全未表态**（`flat:`/`group:` 各 0 次），两级表头靠模板 `_column_groups` + 后端前缀推断兜住，与 F2 问题镜像

## 关键引用

- spec 状态 → `.kiro/specs/INDEX.md`
- 领域术语 → `glossary.md`（inclusion:always）
- 底稿内容结构权威来源 → `基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/`
- 附注章节号权威源 → `backend/data/note_template_variant_matrix.json`
- 附注 section↔wp 映射真源 → `backend/data/note_workpaper_sync_registry.json`
- 报表科目映射真源 → `report_config` DB 表（非 `formula_presets_seed.json`）
