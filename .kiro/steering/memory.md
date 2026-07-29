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
- **可编辑金额** 用 `composables/wpAmountInput.ts` 的 formatter/parser（**EP `el-input-number` 忽略 `:formatter`**，要千分符必须用 `el-input`）；**绝不套用**利率/汇率/比例/笔数/年度/月份。
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
- **🔴 增强打磨禁止自造披露内容**：附注/披露表增强必先看源模板，禁按"常识"造表（D5 曾自造"金融资产风险敞口"）
- **模板预填优先于 AI 生成**：有固定骨架的章节用 CHAPTER_TEMPLATE + 变量替换，AI 仅用于复杂章节
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
- **Active spec = 0**（470 个已归档至 `_archive/`，见 `.kiro/specs/INDEX.md`）
- **分支** `work/2026-05-30-wp-specs`；**最高迁移 V133**（以 `migration_status` 实测为准）
- **工作树干净**，HEAD 已推送 origin

### 已知遗留（低优先，无 spec）

- 附注三灰度开关默认关（`DISCLOSURE_NOTE_FORMULA_ENABLED` / `RAG_ENABLED` / `CONSOL_NOTES_V2_ENABLED`）待项目 opt-in；RAG 须先补知识库索引
- `report_note_linkage.json` 仅 1 条 seed → stale 分级的 `report` 定向分支空转；补映射须逐节人工核对源模板（禁批量臆造）
- 11 张空 `note_*` 表 + 2 张备份表待清理（破坏性，须显式确认）
- 6000 VU 容量压测待专用环境（工具链已就绪）
- 大文件技术债：`g7_consol_linkage_service` 2267 行 / `G7TabAdjudication` 1200+ 行 / `event_handlers` / Top-5 巨型 Vue

## 踩坑铁律

> **完整清单（后端/前端/OnlyOffice 各 30+ 条）见 `#conventions`**。最高频三条：

- **🔴 禁用 PowerShell `Set-Content`/`Get-Content` 操作 .vue/.md**（破坏 UTF-8 中文 + 加 BOM）→ 只用 `str_replace`/`fs_write`；批量改用 Python 显式 `encoding='utf-8'`
- **🔴 崩溃类 bug 以 Vite transform 为权威**：`curl.exe http://localhost:3030/src/.../X.vue` 看 200/500。`get_diagnostics`(Volar) 查不出 SFC 结构损坏/import 解析失败/未声明 binding/`export` in script-setup；HMR 长开页面会累积旧态，判真实状态必全新导航
- **🔴 改后端 `.json`/`.sql` 配置不触发 `--reload`**（`wp_code_overrides.json`/`prefill_formula_mapping` 等模块级 `load()` 只加载一次）→ 须改一个 `.py` 触发重载或手动重启

## 关键引用

- spec 状态 → `.kiro/specs/INDEX.md`
- 领域术语 → `glossary.md`（inclusion:always）
- 底稿内容结构权威来源 → `基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/`
- 附注章节号权威源 → `backend/data/note_template_variant_matrix.json`
- 附注 section↔wp 映射真源 → `backend/data/note_workpaper_sync_registry.json`
- 报表科目映射真源 → `report_config` DB 表（非 `formula_presets_seed.json`）
