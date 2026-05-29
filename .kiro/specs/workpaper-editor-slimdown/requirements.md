# 底稿编辑器瘦身与跨模块联动 — 需求文档

> 起草日期：2026-05-28 | 修订：2026-05-29（基于 2602 sheet 完整分析数据）
> 触发场景：WorkpaperEditor.vue 2731 行 + 73 个 router + 100 个组件碎片化严重，跨模块联动断裂
> 状态：📝 requirements 阶段

---

## 一、问题背景

### 1.1 WorkpaperEditor.vue 膨胀

当前 WorkpaperEditor.vue 承载了所有循环的 dialog 触发逻辑：
- 23 个 dialog import（F/G/H/I/K/L/M/N 各循环专属弹窗）
- 12 个 trigger 按钮（v-if 正则匹配 wp_code）
- 11 个 isXCycle 守卫（useCycleType 解构）
- 每新增一个循环 dialog 需改 5 处代码（import + ref + trigger + dialog + wiring）

**目标**：2731 行 → ≤1200 行，新增循环 dialog 只改 1 行 JSON 配置。

### 1.2 跨模块联动断裂

| 联动路径 | 现状 | 问题 |
|---------|------|------|
| 底稿 → 报表 | report_line_mapping 存在但 HTML 渲染器未接入 | 保存后报表不刷新 |
| 底稿 → 附注 | wp_disclosure_sync router 存在但仅 Univer 路径触发 | C 类 HTML 编辑后附注不同步 |
| 底稿 → 附件 | workpaper_attachment 独立但无 HTML 组件入口 | 证据链断裂 |
| 底稿 → LLM | wp_ai 仅服务 Univer 路径 | HTML 类无 AI 辅助填写 |

### 1.3 后端碎片化

- router_registry/workpaper.py 包含 60+ 个 include_router
- 单端点级 router 文件 73 个，新人难以定位功能边界
- render_schema yaml 仅覆盖 55%（192/349 模板），缺口 168 个（A=40/B=27/C=15/D=9/E=3/F=9/S=65）

### 1.4 完整底稿分析数据（2602 sheet 全量归类）

基于 `workpaper_template_analysis.json`（349 模板 / 2602 sheet 100% 覆盖）：

| 渲染策略 | sheet 数 | 占比 | 对应组件 |
|---------|---------|------|---------|
| HTML 中控台 | 278 | 10.7% | GtAProgramConsole |
| HTML 表单（表格型检查） | 305 | 11.7% | GtDForm (table 子模式) |
| HTML 表单 | 292 | 11.2% | GtEControlTest |
| HTML 嵌套表（多级子表） | 166 | 6.4% | GtCNoteTable |
| HTML 表单（编制信息+索引导航） | 149 | 5.7% | GtBIndex |
| HTML 表单（专属子组件） | 109 | 4.2% | GtDForm (confirmation 子模式) |
| 静态展示 | 104 | 4.0% | GtHStaticDoc |
| HTML stepper | 29 | 1.1% | GtEControlTest (stepper) |
| HTML 表单（电子签） | 27 | 1.0% | GtDForm (review 子模式) |
| HTML 段落型 | 19 | 0.7% | GtDForm (paragraph 子模式) |
| HTML 是否问答型 | 9 | 0.3% | GtDForm (qa 子模式) |
| 保留 Univer | 706 | 27.1% | UniverContainer |
| 保留 Univer（测算） | 158 | 6.1% | UniverContainer |
| 跳过渲染 | 244 | 9.4% | (不渲染) |
| PENDING-待人工归类 | 7 | 0.3% | (需人工决策) |

**HTML 渲染总计：1487 sheet（57.1%）** — 全部需要正确的 render_schema yaml 驱动。，缺口 168 个（A=40/B=27/C=15/D=9/E=3/F=9/S=65）

### 1.4 完整底稿分析数据（2602 sheet 全量归类）

基于 `workpaper_template_analysis.json` 的完整分析结果：

| 渲染方式 | sheet 数 | 占比 | 说明 |
|---------|---------|------|------|
| HTML 渲染 | 1487 | 57.1% | 需 9 类 HTML 组件正确路由 |
| 保留 Univer | 864 | 33.2% | F/G 类数据表+测算（含公式） |
| 跳过渲染 | 244 | 9.4% | I-占位 sheet（表头/GT_Custom） |
| PENDING | 7 | 0.3% | 待人工归类 |

HTML 组件 → sheet 映射（前 10）：

| 组件类型 | 对应 class | sheet 数 |
|---------|-----------|---------|
| GtEControlTest | E-IT 控制测试 | 255 |
| GtDForm（表格型检查） | D-检查表 | 250 |
| GtCNoteTable | C-附注披露 | 166 |
| GtAProgramConsole | A-一般程序表 | 152 |
| GtBIndex | B-底稿目录 | 149 |
| GtHStaticDoc | H-辅助说明 | 104 |
| GtAProgramConsole | A-实质性程序 | 76 |
| GtDForm（专属子组件） | D-函证/盘点/访谈 | 109 |
| GtEControlTest（stepper） | E-评价控制偏差 | 29 |
| GtDForm（电子签） | D-复核记录 | 27 |

每循环 HTML/Univer 分布：

| 循环 | 模板数 | sheet 总数 | HTML | Univer | 跳过 |
|------|--------|-----------|------|--------|------|
| A | 65 | 607 | 233 | 324 | 46 |
| B | 49 | 262 | 227 | 11 | 21 |
| C | 36 | 164 | 125 | 8 | 31 |
| D | 17 | 155 | 92 | 56 | 7 |
| E | 5 | 56 | 39 | 17 | 0 |
| F | 15 | 151 | 74 | 62 | 15 |
| G | 15 | 197 | 113 | 84 | 0 |
| H | 11 | 187 | 111 | 74 | 2 |
| I | 6 | 86 | 41 | 39 | 6 |
| J | 3 | 38 | 23 | 9 | 6 |
| K | 14 | 152 | 90 | 54 | 8 |
| L | 9 | 100 | 62 | 34 | 4 |
| M | 10 | 102 | 54 | 37 | 11 |
| N | 5 | 59 | 29 | 25 | 5 |
| S | 86 | 267 | 167 | 18 | 82 |

---

## 二、用户故事与验收标准


### US-1：循环 Dialog 配置驱动化

**作为** 开发者，**我希望** 新增审计循环弹窗时只需在一个 JSON 配置文件中添加一行，**以便** 不再修改 WorkpaperEditor.vue 主体。

**验收标准**：
1. 新建 `audit-platform/frontend/src/config/cycleDialogRegistry.ts` 配置文件
2. 每条配置包含：`{ cycle, wpCodePattern, component, triggerLabel, triggerIcon, triggerType }`
3. 新建 `<CycleDialogSlot>` 组件，读取配置 + 按 wpDetail.wp_code 匹配渲染 trigger 按钮 + 挂载 dialog
4. WorkpaperEditor.vue 中 12 个 trigger div + 12 个 dialog 组件替换为单个 `<CycleDialogSlot>`
5. WorkpaperEditor.vue 行数减少 ≥600 行
6. 现有 15 个循环 dialog 功能不变（Playwright 回归验证）

### US-2：底稿 → 报表联动（HTML 渲染器接入）

**作为** 审计师，**我希望** 在 HTML 渲染器中保存底稿后，报表模块自动感知数据变化并标记 stale，**以便** 报表始终反映最新底稿数据。

**验收标准**：
1. GtWpRenderer 保存成功后 emit `save-success` → WorkpaperEditor 调用 `report_line_mapping.mark_stale(wp_code)`
2. 后端 `POST /api/workpapers/{id}/save` 成功后发 SSE `report.stale` 事件
3. ReportView 订阅 `report.stale` 事件后显示黄色横幅"底稿数据已更新，点击刷新"
4. 点击刷新后 report_snapshot 重新计算受影响行
5. 性能：stale 标记 <50ms，不阻塞保存主流程

### US-3：C 类底稿 → 附注自动同步（HTML 路径补全）

**作为** 审计师，**我希望** 在 GtCNoteTable 中编辑附注披露表后，disclosure_notes 模块自动同步最新数据，**以便** 附注生成始终使用底稿中的最新填写值。

**验收标准**：
1. GtCNoteTable 保存时自动调用 `POST /api/wp-disclosure-sync/{wp_id}/sync`
2. 同步范围：sub_table_data 中变化的字段 → disclosure_notes 对应 section 的 table_data
3. 同步后 disclosure_notes.is_stale = false
4. 冲突处理：如果 disclosure_notes 侧有手动编辑（last_modified > 底稿 last_save），弹窗提示用户选择"覆盖/保留/合并"
5. 同步日志写入 audit_trail

### US-4：底稿证据链 → 附件模块打通

**作为** 审计师，**我希望** 在 HTML 渲染器中直接上传/查看证据附件，**以便** 不需要跳转到独立附件页面。

**验收标准**：
1. GtAProgramConsole / GtEControlTest 的每行程序支持"📎 附件"按钮
2. 点击后弹出 AttachmentDropZone（已有组件）绑定到当前 wp_id + sheet_name + row_id
3. 已有附件显示数量 badge + hover 预览缩略图
4. 附件存储复用 `workpaper_attachment` 表 + `backend/storage/projects/{pid}/workpapers/` 路径
5. 上传后自动关联 evidence_index（证据链完整性）

### US-5：LLM 辅助填写接入 HTML 渲染器

**作为** 审计师，**我希望** 在 HTML 类底稿（D 类检查表/E 类控制测试）中使用 AI 辅助填写，**以便** 加速长文本段落的编写。

**验收标准**：
1. GtDFormParagraph / GtDFormQA / GtEControlTest 的文本输入区显示"🤖 AI 建议"按钮
2. 点击后调用 `POST /api/wp-ai/{wp_id}/suggest` 传入当前 context（sheet_name + field_name + 已填内容）
3. 返回建议文本，用户可"采纳/修改/忽略"
4. 采纳后自动填入 + 标记 `ai_assisted: true`（审计轨迹）
5. 当 `settings.WP_AI_SERVICE_ENABLED = false` 时按钮隐藏（feature flag）
6. 响应时间 <3s（LLM stub 模式 <200ms）


### US-6：router_registry 聚合治理

**作为** 开发者，**我希望** workpaper.py 中 60+ 个 include_router 按业务子域合并为 6 个聚合注册块，**以便** 新人能快速定位功能边界。

**验收标准**：
1. 合并为 6 个逻辑分组：`wp_template` / `wp_lifecycle` / `wp_review` / `wp_render` / `wp_data` / `wp_search`
2. 每个分组用一个 `APIRouter(prefix=..., tags=[...])` 聚合子端点
3. 所有端点 URL 不变（向后兼容）
4. 注册行从 60+ 减少到 ≤15
5. pytest 全量通过 + Playwright 冒烟无回归

### US-7：render_schema 全量覆盖

**作为** 系统，**我希望** 349 个模板 xlsx 全部有对应的 render_schema yaml（每个 yaml 精确描述该模板内所有 sheet 的渲染策略），**以便** HTML 渲染器对所有底稿都能正确路由而非回落 Univer。

**验收标准**：
1. 修复 `generate_wp_render_schema.py` 的去重 bug（`split("-")[0]` 导致同主 wp_code 多子模板只生成 1 个 yaml）
2. 改为按完整 wp_code（含子序号如 A1-11/A1-13/D2-1至D2-4）独立生成
3. 重跑后 `backend/data/wp_render_schema/` 下 yaml 数 ≥ 349
4. 每个 yaml 内的 sheets section 与对应 xlsx 的实际 sheet 名一一对应
5. 每个 sheet 的 componentType 与 `workpaper_template_analysis.json` 中的推荐渲染一致
6. 14 个手写 yaml 保留不覆盖（优先级高于 generated）
7. 新增 CI 脚本：`python -m pytest tests/test_render_schema_coverage.py` 断言覆盖率 = 100%
8. 前端 useWpClassification 对所有 wp_code 都能返回有效 componentType（不再 fallback Univer）
9. 7 个 PENDING sheet 人工归类后补入对应 yaml

---

## 三、正确性属性（PBT）

### P-1：配置驱动完备性

对于 cycleDialogRegistry 中的每条配置 C：
- C.wpCodePattern 是合法正则
- C.component 对应的 .vue 文件存在于 components/workpaper/
- 不存在两条配置的 wpCodePattern 对同一 wp_code 同时匹配（无歧义）

### P-2：报表 stale 传播正确性

对于任意底稿保存事件 S：
- 如果 S.wp_code 在 report_line_mapping 中有映射行 → 对应 report_snapshot 行标记 is_stale=true
- 如果 S.wp_code 不在映射中 → 不触发任何 stale 标记
- stale 标记是幂等的（重复保存不累积）

### P-3：附注同步一致性

对于 C 类底稿保存后的同步操作：
- disclosure_notes.table_data[section] 的值 ≡ 底稿 html_data[sheet].sub_table_data[section] 的值
- 同步后 disclosure_notes.is_stale = false
- 同步操作是原子的（部分失败则全部回滚）

### P-4：附件关联完整性

对于任意附件上传操作 U：
- workpaper_attachment 表存在记录 (wp_id, sheet_name, row_id, file_path)
- evidence_index 表存在对应关联记录
- 文件物理存在于 storage/projects/{pid}/workpapers/attachments/

### P-5：LLM 建议安全性

对于任意 AI suggest 请求：
- 当 WP_AI_SERVICE_ENABLED=false 时，端点返回 403
- 返回的建议文本长度 ≤ 2000 字符
- 建议文本不包含 PII（通过 sanitize 过滤）
- ai_assisted 标记正确写入 audit_trail

---

## 四、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | 底稿保存 + stale 标记 + 附注同步总耗时 <500ms |
| 兼容 | 所有现有端点 URL 不变，前端路由不变 |
| 测试 | 每个 US 至少 5 个 pytest + 对应 PBT |
| 回归 | WorkpaperEditor 瘦身后 Playwright 全量回归 |
| Feature Flag | LLM 功能受 WP_AI_SERVICE_ENABLED 控制 |
| 并发 | 6000 人同时在线不影响 stale 传播性能 |

---

## 五、不在范围

- 不动 F/G 类 Univer 渲染逻辑
- 不动 ProcedureTrimming 独立页面
- 不做模板版本升级迁移（P2+ 后置）
- 不做 WorkpaperList.vue 瘦身（独立 spec）
- 不做合并模块底稿渲染

---

## 六、用户体验增强（P2 迭代方向）

> 以下需求在 Sprint 1~3 完成后作为后续迭代方向，按成本/收益排序。

### US-8：底稿填写完成度可视化

**作为** 审计师，**我希望** 每个 HTML 类底稿顶部显示填写完成度指示器，底稿列表页也能看到完成度，**以便** 快速判断哪些底稿还需要填写。

**验收标准**：
1. 每个 HTML 类底稿顶部统一显示「填写完成度」环形进度（已填必填字段 / 总必填字段）
2. A 类：已决策程序数 / 总程序数
3. D 类：已回答问题数 / 总问题数
4. E 类：已完成步骤 / 总步骤
5. 底稿列表页每行显示完成度小圆环图标
6. 完成度计算基于 schema 中 `required_fields` 定义

### US-9：底稿间导航增强（跳转历史 + 返回面包屑）

**作为** 审计师，**我希望** 通过 GtIndexChip 跳转到其他底稿后能快速返回原位置，**以便** 不在多个底稿间迷失。

**验收标准**：
1. 跳转后目标底稿顶部显示「← 返回 D2A 第 3 行」面包屑
2. 复用已有 `initGlobalBackspace`（Backspace 键返回）
3. 跳转历史栈保留最近 5 条记录（sessionStorage）
4. 工具栏增加「最近访问」下拉菜单

### US-10：schema 缺失时智能提示

**作为** 审计师，**我希望** 打开一个 render_schema 尚未配置的底稿时看到友好提示而非无声 fallback，**以便** 知道为什么渲染效果不如预期。

**验收标准**：
1. 当 componentType 本应为 HTML 类但因 schema 缺失 fallback 到 Univer 时，顶部显示 info banner
2. banner 文案：「此底稿推荐使用 HTML 渲染器，当前因配置未就绪暂用表格模式」
3. schema 全覆盖后 banner 自动消失（无需手动关闭）
4. 仅对 A/B/C/D/E 类底稿显示（F/G 类 Univer 是设计保留，不提示）

### US-11：渲染模式手动切换

**作为** 审计师，**我希望** 对某些底稿可以手动切换 HTML ↔ Univer 渲染模式，**以便** 按个人习惯选择编辑方式。

**验收标准**：
1. 工具栏增加「切换渲染模式」按钮（仅 A/B/D/E 类显示）
2. 切换后记录到 `project_workpaper_sheet_override` 表（项目级偏好）
3. 下次打开同一底稿自动使用上次选择的模式
4. C 类（嵌套表）和 H 类（静态文档）不支持切换

### US-12：离线暂存 + 弱网恢复

**作为** 审计师，**我希望** 在客户现场网络不稳定时编辑的内容不会丢失，**以便** 不用担心断网导致工作白费。

**验收标准**：
1. HTML 类底稿 auto-save 失败时自动暂存到 localStorage
2. 底稿列表显示「本地有未同步修改」标记（橙色圆点）
3. 恢复网络后自动重试保存 + 冲突检测
4. 冲突时弹窗提示「本地版本 vs 服务器版本」选择
5. localStorage 暂存上限 50MB（超出时提示用户手动导出）

### US-13：首次使用引导

**作为** 新用户，**我希望** 第一次打开 HTML 渲染器时有简短引导，**以便** 快速了解核心操作。

**验收标准**：
1. 仅对 A 类程序表（最复杂）显示 3 步引导 tooltip
2. 步骤：「程序表中控台」→「点击展开查看详情」→「批量裁剪在这里」
3. localStorage 记录已看过，不重复显示
4. 引导可随时通过「?」按钮重新触发

### US-14：底稿模板导出 → 线下填写 → 导入回系统

**作为** 审计师，**我希望** 将底稿导出为带注意事项的 xlsx 模板交给客户/团队成员线下填写，填完后一键导入回系统并自动匹配，**以便** 支持离线协作场景（客户现场无网络、外部专家填写等）。

**验收标准**：
1. 底稿编辑器工具栏增加「📤 导出填写模板」按钮
2. 导出的 xlsx 包含：
   - **注意事项 sheet**（第 1 个 sheet）：填写说明（6~8 节）+ 联系人 + 截止日期 + 字段颜色语义说明
   - **底稿内容 sheet**（按原模板结构）：可填区域黄色底色 / 公式区域灰色锁定 / 必填区域绿色边框 / 禁改区域红色锁定
   - **隐藏 _meta_ sheet**：base64+gzip 压缩的 binding 元数据（字段映射 + schema_version + wp_id + sheet_name），用于导入时自动匹配
3. 导出时可选择导出范围（全部 sheet / 指定 sheet 子集）
4. 导入时系统自动：
   - 解析 _meta_ sheet 获取 binding 信息
   - 逐字段 diff 对比（值变化 / 新增行 / 删除行）
   - 显示 diff 预览表格（变化字段高亮，用户可逐条确认/忽略）
5. 冲突处理：如果系统侧有更新的编辑（last_modified > 导出时间），弹窗提示选择「覆盖/保留系统版本/合并」
6. 导入成功后写入审计日志（who/when/哪些字段被更新/来源=offline_import）
7. 支持可选 AES 加密（敏感底稿场景，导出时设密码，导入时输入密码解密）
8. 导出文件 30 天归档保留（`backend/storage/projects/{pid}/workpapers/offline_exports/`）

### US-15：HTML 底稿自动刷数 + 全链路可点跳转

**作为** 审计师，**我希望** HTML 底稿中的数值自动从 TB/审定表/报表取数填充，所有索引号都是可点击链接，**以便** 不需要手动抄数且能快速穿透到数据源头。

**验收标准**：
1. HTML 底稿中标记为 `source: TB/WP/REPORT` 的 cell 自动从后端取数填充（打开时 + 保存后刷新）
2. 取数来源显示 tooltip：hover 时显示「来自 D2-1!K15 审定数」
3. 取数失败时显示红色虚线框 + tooltip「数据源不可用：D2-1 尚未填写」
4. 所有 GtIndexChip 渲染的索引号均可点击跳转（已有能力，确保 100% 覆盖）
5. 跳转目标不存在时灰显 + tooltip 提示原因（被裁剪/未生成/跨项目）
6. 自动刷数性能：单底稿 ≤200ms（批量取数 API，不逐 cell 请求）

### US-16：程序表流程导航图（审计目标 → 风险 → 应对 → 底稿）

**作为** 审计师，**我希望** 在 A 类程序表和 B 类目录顶部看到可视化的流程导航图，展示「审计目标 → 识别风险 → 应对程序 → 关联底稿」的逻辑链路，**以便** 一目了然整个审计逻辑而非逐行阅读表格。

**验收标准**：
1. A 类程序表（GtAProgramConsole）顶部增加可折叠的「审计逻辑图」区域
2. 流程图展示 4 层结构：
   - 第 1 层：审计目标（5 项认定：存在/完整性/权利义务/准确性/列报）
   - 第 2 层：识别的风险（从 B 循环风险评估关联）
   - 第 3 层：应对程序（当前底稿的程序清单，按类别分组）
   - 第 4 层：关联底稿（每个程序对应的执行底稿，可点击跳转）
3. 流程图节点可点击：
   - 点击风险节点 → 跳转到风险评估底稿
   - 点击程序节点 → 表格滚动到对应行并高亮
   - 点击底稿节点 → 跳转到关联底稿编辑器
4. 节点颜色反映状态：绿色=已完成 / 黄色=进行中 / 灰色=待执行 / 红色=已裁剪
5. B 类目录（GtBIndex）顶部增加简化版「底稿架构图」：树形展示当前循环所有底稿的层级关系
6. 流程图默认折叠（节省空间），点击「🗺️ 审计逻辑图」按钮展开
7. 流程图使用轻量 SVG 渲染（不引入重型图表库），支持缩放和拖拽
