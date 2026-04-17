# Phase 9 — 技术设计

## 1. 项目向导步骤5 — 团队分配 + 人员库 + 工时管理

### 1.1 人员库（全局）

#### 数据模型
```
staff_members 表（新增）
├── id: UUID PK
├── user_id: UUID FK → users.id（可选，关联登录账号）
├── name: VARCHAR 姓名
├── employee_no: VARCHAR 工号（自动生成或手动填写）
├── department: VARCHAR 部门（如"审计二部"）
├── title: VARCHAR 职级（合伙人/总监/高级经理/经理/高级审计员/审计员/实习生）
├── partner_name: VARCHAR 所属合伙人姓名
├── partner_id: UUID FK → staff_members.id（可选，关联合伙人记录）
├── specialty: VARCHAR 专业领域
├── phone: VARCHAR
├── email: VARCHAR
├── join_date: DATE 入职日期
├── resume_data: JSONB 自动丰富的简历（行业经验、审计类型经验、项目数）
├── is_deleted, created_at, updated_at
```

#### 种子数据
从 `2025人员情况.xlsx` 导入（378 行审计二部人员，4 列）：
- 字段映射：姓名→name, 部门→department, 职级→title, 合伙人→partner_name
- 工号自动生成（部门缩写+序号，如 SJ2-001）

#### 后端 API
- `GET /api/staff` — 人员库列表（搜索、分页）
- `POST /api/staff` — 创建人员
- `PUT /api/staff/{id}` — 编辑人员
- `GET /api/staff/{id}/resume` — 获取自动生成的简历（从项目参与历史汇总）
- `GET /api/staff/{id}/projects` — 获取参与项目列表

### 1.2 团队委派

#### 数据模型
```
project_assignments 表（新增）
├── id: UUID PK
├── project_id: UUID FK → projects.id
├── staff_id: UUID FK → staff_members.id
├── role: VARCHAR（signing_partner/manager/auditor/qc）
├── assigned_cycles: JSONB（["B","C","D"]）
├── assigned_at: TIMESTAMPTZ
├── assigned_by: UUID FK → users.id
├── is_deleted, created_at
```

#### 前端组件
- `TeamAssignmentStep.vue`：
  - el-table 展示已委派成员
  - "添加成员"按钮 → el-dialog 从人员库搜索选择
  - 如果搜不到 → 弹出"快速创建人员"表单，保存后自动选中
  - 每行：角色下拉 + 审计循环多选
  - 保存到 wizard_state + project_assignments 表

### 1.3 工时管理

#### 数据模型
```
work_hours 表（新增或复用已有）
├── id: UUID PK
├── staff_id: UUID FK → staff_members.id
├── project_id: UUID FK → projects.id
├── work_date: DATE
├── hours: DECIMAL(4,1)
├── start_time: TIME（可选，用于时间段不重叠校验）
├── end_time: TIME（可选）
├── description: TEXT 工作内容
├── status: VARCHAR（draft/confirmed/approved）
├── ai_suggested: BOOLEAN 是否 LLM 预填
├── is_deleted, created_at
```

#### 后端 API
- `GET /api/staff/{id}/work-hours` — 个人工时列表（按日期范围）
- `POST /api/staff/{id}/work-hours` — 填报工时
- `PUT /api/work-hours/{id}` — 编辑工时
- `POST /api/work-hours/ai-suggest` — LLM 智能预填（根据项目参与情况生成建议）
- `GET /api/projects/{id}/work-hours` — 项目工时汇总（项目经理视角）

#### 工时校验规则（后端）
1. 每日总工时 ≤ 24h
2. 连续 3 天日均 > 12h → 返回 warning
3. 同一 staff_id 同一 work_date 的时间段不重叠

#### LLM 智能预填流程
```
用户打开工时填报 → 后端查询该用户当前参与的项目列表
→ 根据项目阶段（计划/执行/报告）和角色推断工时分配
→ 调用 LLM 生成建议（项目A 4h + 项目B 4h）
→ 返回预填数据 → 用户编辑确认 → 保存
```

### 数据流
```
人员库 → 团队委派（选人+分配角色+循环）→ 被委派人首页看到项目
→ 工时填报推送 → LLM 预填 → 用户确认 → 工时校验 → 保存
→ 项目经理查看团队工时汇总
→ 人员简历自动丰富（项目完成后更新 resume_data）
```

## 1c. 管理看板

### 前端组件
```
ManagementDashboard.vue
├── 顶部：关键指标卡片（4-6 个 StatCard）
├── 左侧：项目进度总览（ECharts 横向柱状图/进度条）
├── 右侧：人员负荷排行（ECharts 柱状图）
├── 中间：人员排期甘特图（ECharts 自定义系列/时间线）
└── 底部：工时热力图（ECharts heatmap，人员×日期）
```

### 技术选型
- **图表库**：ECharts 5.x + vue-echarts（`npm install echarts vue-echarts`）
- **GT 品牌主题**：注册自定义 ECharts 主题，主色 #4b2d77，辅助色 #0094B3/#FF5149/#F5A623
- **不用 Metabase**：看板需要高度定制化（GT 品牌规范+实时数据），Metabase 定制性不足

### 后端看板 API
```
GET /api/dashboard/overview          — 关键指标（在审项目数/本周工时/超期项目/待复核底稿）
GET /api/dashboard/project-progress  — 项目进度列表（项目名/阶段/完成率/截止日期）
GET /api/dashboard/staff-workload    — 人员负荷（人员名/当前项目数/本周工时/未来一周排期）
GET /api/dashboard/schedule          — 人员排期甘特图数据（人员×项目×时间段）
GET /api/dashboard/hours-heatmap     — 工时热力图数据（人员×日期×小时数）
```

### 委派辅助
在 TeamAssignmentStep.vue 的"添加成员"弹窗中：
- 搜索人员时，右侧显示该人员的当前负荷摘要（参与 N 个项目，本周已填 Xh）
- 未来一周排期预览（迷你甘特图或文字列表）
- 帮助委派人判断该成员是否有余力承接新项目

### 看板布局（响应式）
```
┌─────────────────────────────────────────────────┐
│  [在审项目 12]  [本周工时 480h]  [超期 2]  [待复核 15] │  ← StatCards
├────────────────────────┬────────────────────────┤
│  项目进度总览           │  人员负荷排行            │  ← 左右两栏
│  (横向进度条/柱状图)     │  (柱状图 Top10)         │
├────────────────────────┴────────────────────────┤
│  人员排期甘特图（人员×项目×时间线）                    │  ← 全宽
├─────────────────────────────────────────────────┤
│  工时热力图（人员×日期，颜色深浅表示工时）              │  ← 全宽
└─────────────────────────────────────────────────┘
```

## 2. 合并报表前端

### 组件结构
```
ConsolidationIndex.vue
├── el-tabs
│   ├── GroupStructure.vue     — 集团架构可视化（树形图）
│   ├── ConsolScope.vue        — 合并范围（子公司列表 CRUD）
│   ├── ConsolTrialBalance.vue — 合并试算表（跨项目自动汇总）
│   ├── InternalTrade.vue      — 内部交易抵消
│   ├── MinorityInterest.vue   — 少数股东权益
│   ├── ConsolNotes.vue        — 合并附注
│   └── ConsolReport.vue       — 合并报表（含口径切换）
```

### 2a. 集团架构可视化
```
GroupStructure.vue
├── ECharts 树形图（tree series）或 el-tree
│   ├── 最终控制方（顶层节点）
│   │   ├── 上级企业（中间节点）
│   │   │   ├── 本企业/合并项目（当前节点，高亮）
│   │   │   │   ├── 子公司A（叶子节点，显示项目状态）
│   │   │   │   ├── 子公司B
│   │   │   │   └── ...
│   │   │   └── 兄弟企业（如有）
│   │   └── ...
│   └── ...
├── 每个节点显示：企业名称、持股比例、合并级次、项目状态色标
└── 点击节点可跳转到对应项目
```

### 2b. 合并试算表数据流
```
子公司项目A.trial_balance ─┐
子公司项目B.trial_balance ─┼→ consol_trial API → 跨项目汇总 → 合并试算表
子公司项目C.trial_balance ─┘                      ↓
                                            + 抵消分录
                                            + 少数股东调整
                                              ↓
                                          合并报表
```

### 2c. 建项阶段集团关联
- BasicInfoStep.vue 选择"合并报表"时：
  - 展开集团架构面板（已有，三码体系）
  - 新增：自动搜索已有子公司项目（`GET /api/projects?client_name_like=xxx`）
  - 新增：批量创建子公司项目按钮
- 项目列表（MiddleProjectList.vue）：
  - 合并项目用树形展示（已有 ProjectTreeNode）
  - 每个节点显示 consol_level 标签

### 2d. 合并工作底稿
```
ConsolWorksheet.vue
├── 表头：科目编码 | 科目名称 | 子公司A | 子公司B | ... | 抵消借方 | 抵消贷方 | 合并数
├── 数据源：consol_trial API 返回的汇总数据 + 抵消分录
├── 导出 Excel 按钮
```

### 2e. 长投核对与商誉
```
后端：GET /api/consolidation/goodwill/{project_id}
├── 母公司长期股权投资金额（从母公司 trial_balance 取 1511 科目）
├── 子公司净资产（从子公司 trial_balance 取权益类合计）
├── 持股比例（从 consol_scope 取）
├── 差额 = 长投 - 净资产 × 持股比例 = 商誉
└── 高亮差异
```

### 2f. 合并勾稽校验
```
后端：GET /api/consolidation/validation/{project_id}
├── 校验1：合并总资产 = Σ子公司资产 - 内部往来抵消
├── 校验2：合并净利润 = 归属母公司净利润 + 少数股东损益
├── 校验3：合并所有者权益 = 母公司权益 + 少数股东权益
├── 校验4：合并资产 = 合并负债 + 合并权益
└── 返回 passed/failed + 差异金额
```

### 2g. 外币折算
```
ForexTranslation.vue
├── 境外子公司列表
├── 汇率设置（期末汇率、平均汇率、历史汇率）
├── 折算差异计算
├── 对接 /api/consolidation/forex API
```

### 2h. 组成部分审计师
```
ComponentAuditor.vue
├── 组成部分审计师列表（事务所名称、负责子公司、联系人）
├── 沟通函管理（发送/接收状态）
├── 工作底稿接收确认
├── 对接 /api/consolidation/component-auditor API
```

### API 对接（已有后端路由，prefix 统一为 /api/consolidation/）
| 前端组件 | 后端路由文件 | 实际 prefix | 风格 |
|---------|------------|------------|------|
| ConsolScope | consol_scope.py | /api/consolidation/scope | sync |
| ConsolTrialBalance | consol_trial.py | /api/consolidation/trial | sync |
| InternalTrade | internal_trade.py | /api/consolidation/internal-trade | sync |
| MinorityInterest | minority_interest.py | /api/consolidation/minority-interest | sync |
| ConsolNotes | consol_notes.py | /api/consolidation/notes | async |
| ConsolReport | consol_report.py | /api/consolidation/reports | async |
| 抵消分录 | consolidation.py | /api/consolidation/eliminations | sync |
| 组成部分审计 | component_auditor.py | /api/consolidation/component-auditor | sync |
| 商誉 | goodwill.py | /api/consolidation/goodwill | sync |
| 外币折算 | forex.py | /api/consolidation/forex | sync |

### 同步路由处理方案
8 个同步路由使用 `Depends(db)` 但实际是同步 ORM（`Session` + `db.query()`）。方案：通过 `Depends(sync_db)` 依赖注入使用同步会话，无需转异步。已有 `deps.py` 中的 `sync_db = get_sync_db` 别名。

### 前端 API 服务层
新增 `consolidationApi.ts`，封装上述 10 组 API 调用。

## 3. 查账页面完善

### 3.1 树形视图修复
- 问题：`treeBalance` computed 在某些数据结构下返回空数组
- 方案：默认扁平视图，树形为可选模式（已实现），修复 `getParentCode` 对纯数字编码的处理

### 3.2 辅助余额表树形
- 按 `account_code` 分组，同一科目下的辅助维度作为子节点
- 使用 el-table 的 `row-key` + `tree-props`

### 3.3 导入表头匹配
- 复用科目导入步骤的 preview API（`POST /api/projects/{id}/account-chart/preview`）
- 导入数据按钮跳转到科目导入步骤（已实现）

## 4. 协作功能前端

### 组件结构
```
CollaborationIndex.vue
├── el-tabs
│   ├── ProjectTimeline.vue  — 项目时间线
│   ├── WorkHours.vue        — 工时管理
│   ├── PBCChecklist.vue     — PBC 清单
│   └── Confirmations.vue    — 函证管理
```

### 后端路由（多数未注册到 main.py）
- 时间线、工时、PBC、函证：同步路由，属于"32个未注册的同步路由"之列
- 需先确认是否已注册到 main.py，未注册则添加
- 使用 `Depends(sync_db)` 依赖注入同步会话

## 5. 用户管理

### 前端
- 路由：`/settings/users` → `UserManagement.vue`
- 功能：用户列表（el-table）、创建/编辑弹窗（el-dialog）、角色分配
- API：`GET /api/users`、`POST /api/users`、`PUT /api/users/{id}`

### 后端
- 已有 `POST /api/users`（admin only）和 `GET /api/users/me`
- 需新增：`GET /api/users`（列表）、`PUT /api/users/{id}`（编辑）

## 6. 后续事项

### 前端
- 路由：`/projects/:projectId/subsequent-events` → `SubsequentEvents.vue`
- 功能：事项列表、分类（调整/非调整）、与审计报告关联

### 后端
- 新增路由：`/api/projects/{project_id}/subsequent-events`
- 新增服务：`SubsequentEventService`（CRUD + 分类 + 关联）
- ORM 模型：已有 `SubsequentEvent` 和 `SEChecklist` 在 `collaboration_models.py` 中（含 event_type/description/financial_impact/adjustment_required 等字段）

## 7-8. AI 模型配置 + 底稿汇总

### AI 模型配置
- 已有 `AIModelConfig.vue` + `aiModelApi.ts` + 后端 `/api/ai-models`
- 需完善：CRUD 弹窗对接、健康检查轮询、激活/停用操作

### 底稿汇总
- 已有 `WorkpaperSummary.vue` + 后端 `/api/workpaper-summary`
- 需完善：多企业列选择、科目树展开、Excel 导出

## 9. 审计底稿深度集成 — 方案 C 混合架构

### 架构总览
```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                          │
│  WorkpaperList.vue ──→ WorkpaperEditor.vue (ONLYOFFICE) │
│       ↕ API                    ↕ WOPI                   │
├─────────────────────────────────────────────────────────┤
│                    后端 (FastAPI)                        │
│  wp_index (索引) ←→ working_paper (元数据+状态)          │
│       ↕                        ↕                        │
│  模板文件夹 (600+ xlsx)    项目底稿目录 (复制的文件)       │
│       ↕                        ↕                        │
│  TemplateEngine (模板管理)  PrefillService (openpyxl预填) │
│                                ↕                        │
│                    FormulaEngine (取数公式)               │
│                    ↕           ↕           ↕             │
│              tb_balance   tb_ledger   trial_balance      │
├─────────────────────────────────────────────────────────┤
│              ONLYOFFICE Document Server                  │
│  ├── WOPI 协议（CheckFileInfo/GetFile/PutFile）          │
│  ├── audit-formula 插件（TB/WP/AUX/PREV/SUM_TB）        │
│  ├── audit-review 插件（复核批注）                        │
│  └── 多人协作（实时光标、修改同步）                        │
└─────────────────────────────────────────────────────────┘
```

### 9.1 模板初始化流程
```
1. 扫描模板文件夹
   ├── 递归遍历 致同通用审计程序及底稿模板（2025年修订）/
   ├── 解析文件名：E1-1至E1-11 货币资金- 审定表明细表.xlsx
   │   → 编号=E1-1, 名称=货币资金审定表明细表, 循环=E(货币资金)
   └── 写入 wp_template 表

2. 项目底稿生成
   ├── 用户选择模板集（或默认全量）
   ├── 后端 shutil.copy2 复制到 storage/projects/{id}/workpapers/
   ├── 创建 working_paper 记录（file_path, status=not_started）
   └── 关联 wp_index
```

### 9.2 多人协作方案
```
ONLYOFFICE 原生多人协作：
├── 同一文档最多 N 人同时编辑（ONLYOFFICE 默认支持）
├── 实时光标显示（每个用户不同颜色）
├── 修改冲突自动合并（ONLYOFFICE 内置 OT 算法）
├── 编辑锁：WOPI Lock/Unlock（已实现）
│   ├── 第一个打开的用户获取锁
│   ├── 后续用户以协作模式加入（不需要新锁）
│   └── 所有用户关闭后释放锁
└── 离线编辑回退：
    ├── 下载 → 本地编辑 → 上传
    ├── 上传时检测版本冲突（file_version 比对）
    └── 冲突时提示用户选择覆盖或合并
```

### 9.3 大数据量性能方案
```
文件存储层：
├── 底稿文件存 storage/ 本地磁盘（不存数据库 BLOB）
├── 数据库只存元数据（路径、大小、版本、状态）
├── 大文件（>10MB）：ONLYOFFICE 流式加载
└── 归档项目：底稿文件压缩为 .tar.gz 移到冷存储

并发控制层：
├── WOPI Lock 内存锁（已有，单实例）
├── 生产环境：Redis 分布式锁（key=wp:{id}:lock, TTL=30min）
├── 同一底稿最大并发编辑人数：5（ONLYOFFICE 配置）
└── 超限时返回只读模式

预填性能层：
├── 单个底稿预填：同步（openpyxl 写入 <1s）
├── 批量预填（项目初始化 600+ 底稿）：后台任务队列
│   ├── 用 asyncio.create_task 或 Celery
│   ├── 进度通过 SSE 推送到前端
│   └── 预填完成后通知用户
└── 索引树渲染：600+ 节点用 el-tree lazy 懒加载（按循环分组，展开时加载子节点）
```

### 9.4 数据预填与回写
```
预填（打开底稿前）：
├── 后端 PrefillService.prefill_workpaper(wp_id)
├── openpyxl 打开 Excel 文件
├── 根据底稿类型确定预填规则：
│   ├── 审定表（E1-1）：未审数=tb_balance.closing, 调整=adjustments, 审定数=trial_balance.audited
│   ├── 明细表：期初/期末/发生额 from tb_balance
│   └── 函证表：辅助余额 from tb_aux_balance
├── 写入指定单元格
└── 保存文件

回写（保存底稿后）：
├── WOPI PutFile 触发后端 hook
├── ParseService.parse_workpaper(wp_id)
├── openpyxl 读取关键单元格（审定数、差异、结论）
├── 写入 working_paper.parsed_data JSONB
├── 发布 WORKPAPER_SAVED 事件
└── 前端底稿列表显示关键数字摘要
```

### 9.5 四表与底稿事件驱动联动
```
完整数据链：
  四表(tb_balance) → 试算表(trial_balance) → 底稿(审定表) → 报表(financial_report)

事件流：
  DATA_IMPORTED / IMPORT_ROLLED_BACK
    → 标记所有底稿预填数据为"过期"（working_paper.prefill_stale = true）
    → 前端底稿列表显示⚠️刷新提示

  ADJUSTMENT_CREATED / ADJUSTMENT_UPDATED / ADJUSTMENT_DELETED
    → 触发 trial_balance 重算（已有）
    → 标记关联科目的底稿预填数据为"过期"

  TRIAL_BALANCE_UPDATED
    → 标记所有审定表底稿为"过期"
    → 触发报表重算（已有）

  WORKPAPER_SAVED（新增事件）
    → 解析底稿审定数 → 与 trial_balance 比对
    → 不一致时写入差异记录（wp_consistency_check）
    → 前端试算表和底稿列表都显示差异提示

底稿内创建调整分录：
  用户在底稿中标记需调整金额
    → ONLYOFFICE 插件提供"创建调整分录"按钮
    → 调用 POST /api/projects/{id}/adjustments（已有 API）
    → 触发 ADJUSTMENT_CREATED 事件
    → 级联更新试算表和报表
```


### 9.6 审计程序裁剪与委派

#### 数据模型
```
procedure_instances 表（新增）
├── id: UUID PK
├── project_id: UUID FK → projects.id
├── audit_cycle: VARCHAR（B/C/D/E/F/G/H/I/J/K/L/M/N）
├── source_template_id: UUID FK → wp_template.id（来源模板）
├── procedure_code: VARCHAR 程序编号（如 D-3.1）
├── procedure_name: VARCHAR 程序名称
├── parent_id: UUID FK → procedure_instances.id（层级结构，如大类→小步骤）
├── sort_order: INT 排序序号
├── status: VARCHAR（execute/skip/not_applicable）默认 execute
├── skip_reason: TEXT 跳过理由（status=skip 时必填）
├── is_custom: BOOLEAN 是否自定义新增（非模板预设）
├── assigned_to: UUID FK → staff_members.id（委派给谁）
├── assigned_at: TIMESTAMPTZ
├── execution_status: VARCHAR（not_started/in_progress/completed/reviewed）
├── wp_code: VARCHAR 关联底稿编号
├── wp_id: UUID FK → working_paper.id
├── is_deleted, created_at, updated_at
```

```
procedure_trim_schemes 表（新增，裁剪方案保存与复用）
├── id: UUID PK
├── project_id: UUID FK → projects.id（来源项目）
├── audit_cycle: VARCHAR
├── scheme_name: VARCHAR 方案名称（自动生成：项目名+科目+日期）
├── trim_data: JSONB 裁剪快照（procedure_code → {status, skip_reason, is_custom, procedure_name}）
├── created_by: UUID FK → users.id
├── is_deleted, created_at
```

#### 裁剪流程
```
1. 项目负责人进入底稿管理 → 选择审计循环（如 D 收入循环）
2. 后端加载该循环的全量预设程序（从 wp_template 或 procedure_instances 初始化）
   ├── 如果 procedure_instances 中已有该项目+循环的记录 → 直接加载
   └── 如果没有 → 从模板初始化（INSERT INTO procedure_instances SELECT ... FROM wp_template WHERE cycle=D）
3. 前端展示程序列表（树形结构，大类→步骤）
   ├── 每行：程序编号 | 程序名称 | 状态切换（执行✅/跳过⏭/不适用❌）| 裁剪理由 | 委派人
   ├── 跳过时弹出理由输入框（必填）
   └── 底部"新增自定义程序"按钮（插入到指定位置）
4. 保存裁剪结果 → 更新 procedure_instances
5. 自动保存为裁剪方案 → procedure_trim_schemes
```

#### 参照其他单位程序
```
前端交互：
  裁剪页面顶部"参照其他单位"按钮
    → el-dialog 弹窗：选择参照项目（下拉搜索）+ 选择审计循环
    → 后端 GET /api/projects/{ref_id}/procedures/{cycle}/trim-scheme
    → 返回该单位该循环的裁剪结果
    → 前端自动应用（覆盖当前裁剪状态）
    → 用户可二次编辑（增删改个别步骤）
    → 保存

后端逻辑：
  GET /api/projects/{project_id}/procedures/{cycle}/trim-scheme
    → 查询 procedure_instances WHERE project_id AND audit_cycle
    → 返回 [{procedure_code, procedure_name, status, skip_reason, is_custom}]
```

#### 批量裁剪（集团审计）
```
前端交互：
  合并项目的裁剪页面 → "批量应用到子公司"按钮
    → el-dialog：勾选目标子公司（el-checkbox-group，从 consol_scope 获取子公司列表）
    → 确认后后端批量操作

后端逻辑：
  POST /api/projects/{parent_id}/procedures/{cycle}/batch-apply
  body: { target_project_ids: [uuid1, uuid2, ...] }
    → 遍历每个目标项目：
      1. 清除该项目该循环的现有 procedure_instances（软删除）
      2. 从源项目复制 procedure_instances（INSERT INTO ... SELECT ... FROM）
      3. 保存裁剪方案
    → 返回 { applied_count, failed: [{project_id, reason}] }
```

#### 委派到人
```
裁剪完成后：
  前端：每个程序步骤右侧"委派"下拉 → 选择团队成员（从 project_assignments 获取该项目已委派成员）
  批量委派：勾选多个步骤 → "批量委派"按钮 → 选择成员
  保存：PUT /api/projects/{id}/procedures/assign
    → 更新 procedure_instances.assigned_to

成员视角：
  被委派成员打开项目 → 底稿管理页面
    → 只显示 assigned_to = 当前用户 且 status = 'execute' 的程序步骤
    → 每个步骤关联的底稿可直接打开编辑
    → 完成后标记 execution_status = completed
```

#### 后端 API
```
GET  /api/projects/{id}/procedures/{cycle}          — 获取该循环的程序列表（含裁剪状态）
POST /api/projects/{id}/procedures/{cycle}/init      — 从模板初始化程序实例
PUT  /api/projects/{id}/procedures/{cycle}/trim      — 保存裁剪结果（批量更新 status/skip_reason）
POST /api/projects/{id}/procedures/{cycle}/custom     — 新增自定义程序步骤
PUT  /api/projects/{id}/procedures/assign             — 批量委派（更新 assigned_to）
GET  /api/projects/{id}/procedures/{cycle}/trim-scheme — 获取裁剪方案（供参照）
POST /api/projects/{id}/procedures/{cycle}/apply-scheme — 应用参照方案
POST /api/projects/{parent_id}/procedures/{cycle}/batch-apply — 批量应用到子公司
GET  /api/projects/{id}/procedures/my-tasks           — 当前用户被委派的程序列表
```

#### 前端组件
```
ProcedureTrimming.vue（裁剪主页面）
├── 顶部：审计循环选择 el-tabs（B/C/D-N）
├── 工具栏：参照其他单位 | 批量应用到子公司 | 批量委派
├── 主体：el-table 树形展示程序列表
│   ├── 列：编号 | 名称 | 状态切换 | 裁剪理由 | 关联底稿 | 委派人 | 执行状态
│   ├── 状态切换：el-radio-group（执行/跳过/不适用）
│   ├── 跳过时展开理由输入（el-input）
│   └── 底部：+ 新增自定义程序
├── 参照弹窗：ReferenceSchemeDialog.vue
│   ├── 项目搜索下拉
│   ├── 循环选择
│   └── 预览裁剪结果 → 确认应用
└── 批量应用弹窗：BatchApplyDialog.vue
    ├── 子公司列表 checkbox
    └── 确认应用 → 进度提示

MyProcedureTasks.vue（成员视角 — 我的审计程序）
├── 按审计循环分组展示被委派的程序步骤
├── 每个步骤：程序名称 | 关联底稿（点击打开）| 执行状态切换
└── 完成进度条
```


### 9.7 未审报表→试算表→已审报表→附注→底稿 全链路联动

#### 完整数据链路图
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  四表原始数据  │────→│   试算表      │────→│  已审报表     │────→│   附注        │
│  tb_balance   │     │ trial_balance │     │ financial_   │     │ disclosure_  │
│  (未审数)     │     │ 未审+调整=审定 │     │ report       │     │ note         │
└──────────────┘     └──────┬───────┘     └──────────────┘     └──────────────┘
                            │                                          │
                            │ 双向校验                                  │ 金额一致
                            ↓                                          ↓
                     ┌──────────────┐                           ┌──────────────┐
                     │  底稿审定表   │←─────── 明细一致 ─────────→│  底稿明细表   │
                     │ working_paper │                           │ working_paper │
                     │ (审定数)      │                           │ (期末余额)    │
                     └──────────────┘                           └──────────────┘

事件级联链：
  DATA_IMPORTED → recalc_unadjusted → TRIAL_BALANCE_UPDATED
    → ReportEngine.regenerate → REPORTS_UPDATED
      → DisclosureEngine.on_reports_updated（附注刷新）
      → AuditReportService.on_reports_updated（审计报告刷新）
    → 标记底稿 prefill_stale=true

  ADJUSTMENT_CREATED/UPDATED/DELETED → recalc_adjustments + recalc_audited → TRIAL_BALANCE_UPDATED
    → （同上级联）

  WORKPAPER_SAVED → parse_workpaper → 与 trial_balance 比对 → 写入差异记录
```

#### 9.7.1 未审报表生成

```
数据模型决策：未审报表不单独存储 financial_report 记录，而是查询时动态计算。
理由：
  - 未审报表 = 试算表未审数列的公式计算结果，数据源始终是 trial_balance
  - 如果单独存储，每次四表导入都要同时重算两份报表，增加复杂度
  - 查询时动态计算性能可接受（<500 科目，公式计算 <2s）

实现方式：
  GET /api/reports/{project_id}/{year}/{type}?unadjusted=true
    → ReportFormulaParser(use_unadjusted=True)
    → 只取 trial_balance.unadjusted_debit / unadjusted_credit 列
    → 返回与已审报表相同的 ReportRow 结构
    → 前端对比视图同时请求两次（unadjusted=true + unadjusted=false）
```

#### 9.7.2 未审/已审对比视图

```
ReportView.vue 扩展：
├── 顶部新增：el-radio-group（已审报表 / 未审报表 / 对比视图）
├── 已审报表模式：现有逻辑不变
├── 未审报表模式：调用 getReport(projectId, year, type, { unadjusted: true })
├── 对比视图模式：
│   ├── 同时加载未审和已审数据
│   ├── el-table 列：行次 | 项目 | 未审金额 | 调整影响 | 已审金额
│   ├── 调整影响 = 已审 - 未审
│   └── 差异 ≠ 0 的行高亮（橙色背景）
```

#### 9.7.3 试算表穿透到底稿

```
TrialBalance.vue 扩展：
├── 新增列：底稿状态（✅一致 / ⚠️有差异 / —未关联）
│   ├── 后端 GET /api/trial-balance 返回每行增加 wp_consistency 字段
│   ├── wp_consistency: { wp_id, wp_code, status: 'consistent'|'inconsistent'|'not_linked', diff_amount }
│   └── 前端：状态图标 + tooltip 显示差异金额
├── 双击科目行 → 如果有关联底稿 → 跳转到 WorkpaperEditor（ONLYOFFICE 编辑）
│   ├── router.push({ name: 'WorkpaperEdit', params: { projectId, wpId: row.wp_id } })
│   └── 无关联底稿时提示"该科目未关联底稿"
```

#### 9.7.4 报表穿透到底稿

```
ReportView.vue 穿透弹窗扩展：
├── 现有：点击报表行次金额 → 弹窗显示科目列表
├── 扩展：每个科目行右侧增加"打开底稿"按钮
│   ├── 从 wp_consistency 数据获取 wp_id
│   └── 点击 → 新标签页打开 WorkpaperEditor
├── 报表行次旁增加附注编号链接
│   ├── 后端：report_config 中已有 note_ref 字段（附注编号）
│   └── 前端：行次旁显示 "附注X" 链接 → 点击跳转到 DisclosureEditor 对应章节
```

#### 9.7.5 附注数据来源标签

```
DisclosureEditor.vue 扩展：
├── 表格单元格中自动取数的值旁显示来源标签
│   ├── 小标签：📊 来自试算表 1001
│   ├── 点击标签 → 跳转到试算表页面并高亮该科目行
│   └── 后端：disclosure_note.table_data 中每个单元格增加 source 元数据
│       { value: 1000000, source: { type: 'trial_balance', account_code: '1001', column: 'audited_closing' } }
├── 校验结果侧边栏（已有 NoteValidationEngine）
│   ├── 增加"与报表一致性"校验结果
│   └── 增加"与底稿明细一致性"校验结果
```

#### 9.7.6 底稿审定数同步到试算表

```
用户在底稿中修改审定数 → 保存 → WOPI PutFile
  → ParseService 解析审定数
  → 与 trial_balance 比对
  → 不一致时：
    ├── 底稿列表显示 ⚠️ 差异提示
    ├── 试算表显示 ⚠️ 差异提示
    └── 用户可选择：
        a) 以底稿为准 → POST /api/trial-balance/sync-from-workpaper
           → 更新 trial_balance.audited_* → 触发 TRIAL_BALANCE_UPDATED → 级联更新报表+附注
        b) 以试算表为准 → 刷新底稿预填数据（覆盖底稿中的审定数）
        c) 暂不处理 → 保持差异状态，后续手动对齐
```

#### 9.7.7 全链路一致性校验服务

```python
class ConsistencyCheckService:
    """全链路一致性校验"""

    async def check_full_chain(self, project_id: UUID, year: int) -> FullChainConsistencyResult:
        """一次性校验全链路"""
        results = []

        # 1. 四表→试算表：未审数一致性
        results.append(await self._check_tb_vs_balance(project_id, year))

        # 2. 试算表→报表：审定数→报表行次
        results.append(await self._check_tb_vs_report(project_id, year))

        # 3. 报表→附注：行次金额与附注一致
        results.append(await self._check_report_vs_notes(project_id, year))

        # 4. 试算表→底稿：审定数与底稿审定表一致
        results.append(await self._check_tb_vs_workpaper(project_id, year))

        # 5. 附注→底稿：附注合计与底稿明细一致
        results.append(await self._check_notes_vs_workpaper(project_id, year))

        return FullChainConsistencyResult(
            project_id=project_id,
            year=year,
            checks=results,
            all_consistent=all(r.passed for r in results),
            checked_at=datetime.utcnow(),
        )

# Pydantic Schema
class ChainCheckResult(BaseModel):
    check_name: str          # "四表→试算表" / "试算表→报表" / ...
    passed: bool
    total_items: int         # 校验项总数
    passed_items: int        # 通过项数
    failed_items: list[ChainCheckFailure]  # 不通过的明细

class ChainCheckFailure(BaseModel):
    entity_type: str         # "account" / "report_row" / "note" / "workpaper"
    entity_id: str           # 科目编码 / 行次编号 / 附注ID / 底稿编号
    entity_name: str
    expected: Decimal
    actual: Decimal
    diff: Decimal
    jump_url: str            # 前端跳转路径
```

#### 9.7.8 后端 API

```
# 未审报表
GET /api/reports/{project_id}/{year}/{type}?unadjusted=true  — 未审报表数据

# 试算表底稿一致性
GET /api/trial-balance/{project_id}/{year}?include_wp_consistency=true  — 试算表含底稿一致性状态

# 底稿审定数同步
POST /api/trial-balance/{project_id}/{year}/sync-from-workpaper  — 以底稿审定数覆盖试算表
  body: { wp_id: UUID, account_codes: [str] }  — 可选指定科目，默认全部

# 全链路一致性校验
GET /api/projects/{project_id}/consistency-check?year=2024  — 全链路校验
POST /api/projects/{project_id}/consistency-check/run  — 手动触发校验

# 附注数据来源
GET /api/disclosure-notes/{project_id}/{note_id}/sources  — 附注单元格数据来源
```

#### 9.7.9 前端组件扩展

```
ConsistencyDashboard.vue（全链路一致性看板）
├── 5 个校验卡片（四表→试算表 / 试算表→报表 / 报表→附注 / 试算表→底稿 / 附注→底稿）
│   ├── 每个卡片：✅ 全部一致 / ⚠️ N 项不一致
│   ├── 点击展开不一致明细列表
│   └── 每条明细可点击跳转到具体位置
├── 顶部：整体状态（全部通过 / 有 N 项不一致）
├── 手动触发校验按钮
└── 路由：/projects/:id/consistency
```


### 9.8 附注与底稿深度联动 + 模版驱动 + 单体/合并附注联动

#### 9.8.1 附注提数优先级架构

```
附注单元格取数优先级：
  1. 手动编辑值（用户锁定，不被覆盖）
  2. 底稿 parsed_data（第一手审计证据）
  3. 试算表 audited_*（兜底数据源）

数据流：
  底稿(E9-1固定资产审定表)
    → PrefillService 预填 → 用户编辑 → WOPI PutFile
    → ParseService 解析 → parsed_data JSONB
    → DisclosureEngine 提数 → 附注"五、9 固定资产"表格

  试算表(trial_balance)
    → DisclosureEngine._get_tb_amount() → 附注表格（兜底）
```

#### 9.8.2 附注章节与底稿映射

```python
# disclosure_note 表扩展（或 note_template 中定义）
note_wp_mapping = {
    "五、1": {  # 货币资金
        "wp_code": "E1-1",
        "mapping_rules": [
            {"note_row": "库存现金", "wp_cell": "审定数.库存现金", "column": "closing"},
            {"note_row": "银行存款", "wp_cell": "审定数.银行存款", "column": "closing"},
            {"note_row": "其他货币资金", "wp_cell": "审定数.其他货币资金", "column": "closing"},
        ]
    },
    "五、9": {  # 固定资产（变动表）
        "wp_code": "E9-1",
        "mapping_rules": [
            {"note_row": "原值期初", "wp_cell": "原值.期初", "column": "opening"},
            {"note_row": "本期增加", "wp_cell": "原值.本期增加", "column": "movement"},
            {"note_row": "本期减少", "wp_cell": "原值.本期减少", "column": "movement"},
            {"note_row": "原值期末", "wp_cell": "原值.期末", "column": "closing"},
            # ... 累计折旧、账面价值同理
        ],
        "sub_columns": ["房屋建筑物", "机器设备", "运输工具", "电子设备"]  # 明细列
    },
    # ... 其他科目
}
```

#### 9.8.3 单元格编辑模式

```python
# disclosure_note.table_data 单元格结构扩展
{
    "headers": ["项目", "期末余额", "期初余额"],
    "rows": [
        {
            "label": "库存现金",
            "cells": [
                {
                    "value": 1500000.00,
                    "mode": "auto",          # auto=自动提数 / manual=手动编辑 / locked=锁定
                    "source": {
                        "type": "workpaper",  # workpaper / trial_balance / manual
                        "wp_code": "E1-1",
                        "wp_id": "uuid...",
                        "cell_ref": "审定数.库存现金",
                    },
                    "manual_value": null,     # 手动编辑时的值
                    "annotation": null,       # 审计批注
                    "last_synced_at": "2026-04-16T10:00:00",
                }
            ]
        }
    ]
}
```

#### 9.8.4 DisclosureEngine 提数逻辑扩展

```python
class DisclosureEngine:
    async def _build_table_data_v2(self, project_id, year, section, template):
        """增强版表格数据构建 — 优先从底稿提数"""
        mapping = self._get_wp_mapping(section.section_number)
        rows = []

        for tmpl_row in template.get("rows", []):
            cells = []
            for col_idx, header in enumerate(template["headers"][1:]):  # 跳过"项目"列
                cell = await self._resolve_cell_value(
                    project_id, year, section, tmpl_row, col_idx, mapping
                )
                cells.append(cell)
            rows.append({"label": tmpl_row["label"], "cells": cells, ...})

        return {"headers": template["headers"], "rows": rows}

    async def _resolve_cell_value(self, project_id, year, section, row, col_idx, mapping):
        """按优先级解析单元格值"""
        # 1. 检查是否有手动锁定值
        existing = await self._get_existing_cell(section.id, row["label"], col_idx)
        if existing and existing.get("mode") == "manual":
            return existing  # 手动值不覆盖

        # 2. 尝试从底稿 parsed_data 取数
        if mapping:
            wp_value = await self._get_from_workpaper(project_id, mapping, row["label"], col_idx)
            if wp_value is not None:
                return {
                    "value": wp_value,
                    "mode": "auto",
                    "source": {"type": "workpaper", "wp_code": mapping["wp_code"], ...}
                }

        # 3. 兜底：从试算表取数
        tb_value = await self._get_tb_amount(project_id, year, row.get("account_code"))
        return {
            "value": float(tb_value),
            "mode": "auto",
            "source": {"type": "trial_balance", "account_code": row.get("account_code")}
        }
```

#### 9.8.5 单体附注与合并附注联动

```
合并附注数据流：
  子公司A单体附注(disclosure_note) ─┐
  子公司B单体附注(disclosure_note) ─┼→ ConsolDisclosureService.aggregate_notes()
  子公司C单体附注(disclosure_note) ─┘     ↓
                                    汇总各子公司同科目数据
                                         ↓
                                    - 内部交易抵消调整
                                         ↓
                                    合并附注(consol_disclosure_note)
                                         ↓
                                    + 合并特有章节（合并范围/商誉/少数股东/内部交易/外币折算）

事件联动：
  子公司单体附注变更（NOTE_UPDATED 事件）
    → 查找该子公司所属的合并项目（parent_project_id）
    → 标记合并附注对应章节为 stale=true
    → 合并附注编辑页显示⚠️"子公司数据已更新，请刷新"

合并附注刷新：
  POST /api/consolidation/notes/{project_id}/{year}/refresh
    → 重新汇总各子公司单体附注
    → 重新计算内部交易抵消影响
    → 更新合并附注数据
    → 清除 stale 标记
```

#### 9.8.6 合并附注展开子公司明细

```
DisclosureEditor.vue（合并附注模式）扩展：
├── 表格行支持展开（el-table expand）
│   ├── 展开后显示各子公司的明细数据
│   │   ├── 子公司A：库存现金 500,000
│   │   ├── 子公司B：库存现金 800,000
│   │   ├── 内部抵消：0
│   │   └── 合并数：1,300,000
│   └── 帮助审计师理解合并数的构成
├── 后端 API：GET /api/consolidation/notes/{project_id}/{year}/{section}/breakdown
│   └── 返回各子公司的明细数据 + 抵消调整
```

#### 9.8.7 模版驱动附注生成

```
项目创建时：
  1. 用户选择模版类型（soe/listed）→ 存入 projects.template_type
  2. 附注生成时加载对应模版（note_template_soe.json / note_template_listed.json）
  3. 按模版结构初始化所有章节（disclosure_note 表）
  4. 自动提数填充表格数据（_build_table_data_v2）
  5. 叙述性章节预填模版文本（text_template）

模版差异：
  国企版特有：国有资本经营信息、国有资产保值增值
  上市版特有：每股收益、分部报告、股份支付、持续经营、公允价值
  共有但结构不同：固定资产（上市版要求更详细的分类披露）
```

#### 9.8.8 后端 API 扩展

```
# 附注提数刷新
POST /api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers  — 从底稿重新提数
POST /api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode    — 切换单元格自动/手动模式
  body: { row_label, col_index, mode: "auto"|"manual", manual_value? }

# 附注与底稿映射
GET  /api/disclosure-notes/{project_id}/wp-mapping                      — 获取附注-底稿映射关系
PUT  /api/disclosure-notes/{project_id}/wp-mapping                      — 更新映射关系

# 合并附注
POST /api/consolidation/notes/{project_id}/{year}/refresh               — 从子公司重新汇总
GET  /api/consolidation/notes/{project_id}/{year}/{section}/breakdown   — 子公司明细构成

# 附注导出
POST /api/disclosure-notes/{project_id}/{year}/export-word              — 导出 Word
  body: { sections?: string[], include_consol?: boolean }

# 新增事件类型
EventType.NOTE_UPDATED = "note.updated"  — 附注变更事件（触发合并附注刷新标记）
```

#### 9.8.9 前端组件扩展

```
DisclosureEditor.vue 扩展：
├── 单元格模式标识：蓝色背景=自动提数，白色=手动编辑
├── 右键菜单：切换自动/手动模式、查看数据来源、打开关联底稿、添加批注
├── 侧边栏：报表对应行次数据 + 校验结果 + 底稿关联状态
├── 顶部工具栏：从底稿刷新 | 导出 Word | 模版类型标签（国企版/上市版）
├── 合并附注模式：行展开显示子公司明细 + 刷新按钮 + stale 提示
└── 叙述性章节：富文本编辑器（Markdown 或 TipTap）
```


### 9.9 附注编辑体验 + 历史附注复用 + LLM 辅助

#### 9.9.1 编辑方案选型分析

```
方案对比：
  A. Excel/ONLYOFFICE 编辑附注
     ✗ 叙述文字排版差（Excel 不适合长文本）
     ✗ 章节结构难以维护（合并单元格混乱）
     ✗ 提数联动复杂（需要自定义函数）
     ✗ 导出 Word 需要二次转换

  B. Word/ONLYOFFICE 编辑附注
     ✗ 表格编辑体验差（Word 表格操作繁琐）
     ✗ 提数联动困难（Word 无公式引擎）
     ✗ 结构化数据提取困难

  C. 内置结构化 HTML 编辑器 ← 选定方案
     ✓ 表格用 el-table 可编辑（体验好，提数联动简单）
     ✓ 叙述文字用 TipTap 富文本（排版灵活）
     ✓ 数据存储为结构化 JSON（便于校验、提数、导出）
     ✓ 导出时用 python-docx 精确控制 Word 格式
     ✓ 实时预览 Word 效果
```

#### 9.9.2 附注章节数据结构

```python
# disclosure_note.content 结构（扩展现有 table_data + text_content）
{
    "section_number": "五、9",
    "section_title": "固定资产",
    "status": "retain",          # retain/skip/not_applicable（裁剪状态）
    "skip_reason": null,
    "blocks": [
        {
            "type": "text",
            "content": "<p>固定资产按成本进行初始计量...</p>",  # TipTap HTML
            "source": "template",   # template=模版预填 / history=历史附注 / manual=手动编辑 / llm=LLM生成
        },
        {
            "type": "table",
            "table_data": {
                "headers": ["项目", "房屋建筑物", "机器设备", "运输工具", "电子设备", "合计"],
                "rows": [
                    {
                        "label": "原值期初",
                        "cells": [
                            {"value": 5000000, "mode": "auto", "source": {"type": "workpaper", "wp_code": "E9-1"}},
                            {"value": 3000000, "mode": "auto", "source": {"type": "workpaper", "wp_code": "E9-1"}},
                            ...
                        ]
                    },
                    ...
                ]
            }
        },
        {
            "type": "text",
            "content": "<p>本期固定资产增加主要系购置生产设备所致。</p>",
            "source": "llm",  # LLM 自动生成的变动分析
        }
    ]
}
```

#### 9.9.3 附注章节裁剪

```
复用审计程序裁剪架构（procedure_instances 模式）：

note_section_instances 表（新增）
├── id: UUID PK
├── project_id: UUID FK → projects.id
├── template_type: VARCHAR（soe/listed）
├── section_number: VARCHAR（五、1 / 五、2 / ...）
├── section_title: VARCHAR
├── status: VARCHAR（retain/skip/not_applicable）默认 retain
├── skip_reason: TEXT
├── sort_order: INT
├── is_deleted, created_at, updated_at

note_trim_schemes 表（新增，裁剪方案保存）
├── id: UUID PK
├── project_id: UUID FK
├── template_type: VARCHAR
├── scheme_name: VARCHAR
├── trim_data: JSONB（section_number → {status, skip_reason}）
├── created_by: UUID FK
├── is_deleted, created_at

API：
  GET  /api/disclosure-notes/{project_id}/sections          — 获取章节列表（含裁剪状态）
  PUT  /api/disclosure-notes/{project_id}/sections/trim      — 保存裁剪结果
  GET  /api/disclosure-notes/{project_id}/sections/trim-scheme — 获取裁剪方案
  POST /api/disclosure-notes/{project_id}/sections/apply-scheme — 应用参照方案
  POST /api/disclosure-notes/{project_id}/sections/batch-apply  — 批量应用到子公司
```

#### 9.9.4 历史附注上传与解析

```
上传流程：
  用户上传历史附注（Word/PDF）
    → 后端接收文件
    → 文件类型判断
    ├── .docx → python-docx 解析
    │   ├── 遍历 paragraphs，按标题样式（Heading 1/2/3）识别章节边界
    │   ├── 遍历 tables，提取表格数据（行列结构+数值）
    │   ├── 分离叙述文字与表格
    │   └── 输出：[{section_title, text_blocks, tables}]
    │
    └── .pdf → MinerU 解析（GPU 加速）
        ├── 文字层 PDF → 直接提取文本
        ├── 扫描版/图片层 → OCR（PaddleOCR/Tesseract）
        ├── 混合 PDF → 智能策略（文字层优先+OCR补充）
        └── 输出：Markdown 格式文本

    → LLM 结构化处理（SSE 流式）
    ├── System Prompt：
    │   "你是审计附注解析专家。请将以下附注原文解析为结构化 JSON。
    │    识别每个章节（五、1 货币资金 等），提取表格数据和叙述文字。
    │    输出格式：[{section_number, section_title, tables: [{headers, rows}], text_blocks: [str]}]"
    ├── 分块处理（附注通常 50-100 页，按章节分块避免超 token 限制）
    └── 输出：结构化 JSON

    → 映射到当前模版
    ├── LLM 将历史章节与当前模版章节自动对应
    │   （如历史"五、（一）货币资金" → 模版"五、1 货币资金"）
    ├── 上年期末余额 → 当年期初/上期金额列
    └── 叙述文字 → 预填到对应章节

后端 API：
  POST /api/disclosure-notes/{project_id}/upload-history
    body: multipart/form-data（file + year）
    → SSE 流式返回解析进度
    → 最终返回 {parsed_sections, mapping_suggestions, unmapped_sections}
```

#### 9.9.5 LLM 辅助编辑

```
1. 会计政策生成：
   POST /api/disclosure-notes/{project_id}/ai/generate-policy
   body: { section_number, template_type, industry, history_text? }
   → LLM 根据模版+行业+历史生成标准会计政策文本
   → SSE 流式返回

2. 变动分析生成：
   POST /api/disclosure-notes/{project_id}/ai/generate-analysis
   body: { section_number, current_data, prior_data }
   → LLM 对比本期与上期数据，生成变动原因说明
   → "应收账款较上年增长 30%，主要系本期销售规模扩大所致"

3. 披露完整性检查：
   POST /api/disclosure-notes/{project_id}/ai/check-completeness
   → LLM 检查是否遗漏必要披露（关联方/或有事项/日后事项/分部信息）
   → 返回 [{missing_section, reason, suggestion}]

4. 表述规范性检查：
   POST /api/disclosure-notes/{project_id}/ai/check-expression
   body: { section_number, text_content }
   → LLM 检查用语准确性、逻辑通顺性
   → 返回 [{issue, location, suggestion}]

5. 智能续写：
   POST /api/disclosure-notes/{project_id}/ai/complete
   body: { section_number, current_text, cursor_position }
   → LLM 提供续写建议（3 个候选）
   → 前端类似 Copilot 灰色提示文字
```

#### 9.9.6 Word 导出引擎（python-docx）

```python
class NoteWordExporter:
    """附注 Word 导出 — 精确控制格式"""

    def export(self, project_id, year, sections, output_path):
        doc = Document()

        # 页面设置
        section = doc.sections[0]
        section.top_margin = Cm(3)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.2)

        # 标题
        doc.add_heading("财务报表附注", level=0)

        for note in sections:
            if note["status"] == "skip":
                continue

            # 章节标题（黑体加粗）
            h = doc.add_heading(f"{note['section_number']} {note['section_title']}", level=2)
            h.runs[0].font.name = '黑体'

            for block in note.get("blocks", []):
                if block["type"] == "text":
                    # 叙述文字（仿宋_GB2312）
                    self._add_rich_text(doc, block["content"])

                elif block["type"] == "table":
                    # 表格（三线表样式）
                    self._add_table(doc, block["table_data"])

        # 页脚页码
        self._add_page_numbers(doc)

        # 目录（在最前面插入）
        self._add_toc(doc)

        doc.save(output_path)

    def _add_table(self, doc, table_data):
        """三线表样式：表头下粗线+表尾粗线+中间细线"""
        headers = table_data["headers"]
        rows = table_data["rows"]
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))

        # 表头
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = h
            run = cell.paragraphs[0].runs[0]
            run.font.name = '仿宋_GB2312'
            run.bold = True

        # 数据行
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate([row["label"]] + [c.get("value", 0) for c in row.get("cells", [])]):
                cell = table.rows[r_idx + 1].cells[c_idx]
                cell.text = str(val) if val else ""
                # 数字右对齐
                if c_idx > 0:
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    run = cell.paragraphs[0].runs[0]
                    run.font.name = 'Arial Narrow'

        # 三线表边框
        self._set_three_line_border(table)
```

#### 9.9.7 前端组件

```
DisclosureEditor.vue 重构：
├── 左侧：章节目录树（el-tree，裁剪后只显示保留的章节）
│   ├── 每个节点：章节编号 + 标题 + 完成状态图标
│   ├── 右键菜单：裁剪/恢复、跳转到底稿、查看校验结果
│   └── 底部：裁剪管理按钮（打开裁剪面板）
│
├── 中间：编辑区（混排布局）
│   ├── 章节标题（不可编辑，从模版取）
│   ├── text block → TipTap 富文本编辑器
│   │   ├── 工具栏：加粗/斜体/列表/标题/撤销
│   │   ├── LLM 辅助按钮：生成/润色/续写
│   │   └── 来源标签：模版预填/历史附注/LLM生成/手动编辑
│   ├── table block → el-table 可编辑表格
│   │   ├── 双击单元格编辑
│   │   ├── 自动提数单元格蓝色背景 + 来源 tooltip
│   │   ├── 手动单元格白色背景
│   │   └── 右键：切换自动/手动、查看来源、打开底稿
│   └── 补充说明区 → TipTap（可选，用户自行添加）
│
├── 右侧：辅助面板（el-tabs）
│   ├── Tab 1：报表对照（对应报表行次金额，差异高亮）
│   ├── Tab 2：校验结果（NoteValidationEngine 结果）
│   ├── Tab 3：底稿关联（关联底稿列表，点击打开）
│   ├── Tab 4：历史对比（上年附注同章节内容）
│   └── Tab 5：Word 预览（实时渲染预览效果）
│
└── 顶部工具栏：
    ├── 模版类型标签（国企版/上市版）
    ├── 上传历史附注按钮
    ├── 从底稿刷新按钮
    ├── LLM 检查按钮（完整性+规范性）
    ├── 导出 Word 按钮
    └── 裁剪管理按钮

NoteTrimPanel.vue（附注裁剪面板，复用 ProcedureTrimming 模式）：
├── 全量章节列表（el-table）
├── 每行：章节编号 | 标题 | 状态切换（保留/跳过/不适用）| 理由
├── 参照其他单位 | 批量应用到子公司
└── 保存裁剪方案

HistoryNoteUpload.vue（历史附注上传弹窗）：
├── 文件上传（el-upload，支持 .docx / .pdf）
├── 年度选择
├── 解析进度（SSE 流式）
├── 解析结果预览（章节映射确认）
└── 确认应用（预填到当前附注）
```


## 1d. 看板体系增强

### 分层看板架构
```
┌─────────────────────────────────────────────────────────┐
│  全局看板（合伙人/管理层）                                 │
│  ManagementDashboard.vue                                │
│  ├── 关键指标卡片（在审项目/工时/超期/待复核）              │
│  ├── 项目风险预警（超期/重要性超限/底稿逾期）              │
│  ├── 审计质量指标（QC通过率/复核完成率/调整分录趋势）       │
│  ├── 集团审计总览（子公司进度对比）                        │
│  ├── 人员排期甘特图 + 工时热力图                          │
│  └── 年度对比趋势                                        │
├─────────────────────────────────────────────────────────┤
│  项目看板（项目经理）                                      │
│  ProjectDashboard.vue                                    │
│  ├── 项目进度环形图                                       │
│  ├── 底稿完成度矩阵（循环×状态热力图）                     │
│  ├── 团队工作量分布（饼图+柱状图）                         │
│  ├── 关键待办 Top10                                       │
│  ├── 数据一致性摘要（5项校验状态）                         │
│  └── 项目时间线（里程碑+实际进度）                         │
├─────────────────────────────────────────────────────────┤
│  个人看板（审计员）                                        │
│  PersonalDashboard.vue                                   │
│  ├── 我的待办（程序/底稿/复核意见）                        │
│  ├── 我的工时（日历视图+月汇总）                           │
│  ├── 我参与的项目（卡片列表）                              │
│  └── 通知中心                                             │
└─────────────────────────────────────────────────────────┘
```

### 后端 API 扩展
```
# 全局看板（已有 5 个 API，补充 3 个）
GET /api/dashboard/risk-alerts           — 风险预警（超期/重要性超限/底稿逾期）
GET /api/dashboard/quality-metrics       — 审计质量指标（QC通过率/复核完成率/调整趋势）
GET /api/dashboard/group-progress        — 集团审计子公司进度对比

# 项目看板（新增 4 个 API）
GET /api/projects/{id}/dashboard/overview     — 项目进度环形图数据
GET /api/projects/{id}/dashboard/wp-matrix    — 底稿完成度矩阵（循环×状态）
GET /api/projects/{id}/dashboard/team-load    — 团队工作量分布
GET /api/projects/{id}/dashboard/todo-top10   — 关键待办 Top10

# 个人看板（新增 2 个 API）
GET /api/my/dashboard                         — 个人看板汇总（待办/工时/项目）
GET /api/my/notifications                     — 通知列表（分页）
```

### GTChart.vue 通用图表组件
```vue
<template>
  <div class="gt-chart" :style="{ height: height + 'px' }">
    <div v-if="loading" class="gt-chart-loading">
      <el-skeleton :rows="3" animated />
    </div>
    <div v-else-if="isEmpty" class="gt-chart-empty">
      <el-empty description="暂无数据" :image-size="60" />
    </div>
    <v-chart v-else :option="mergedOption" autoresize />
  </div>
</template>

<!-- 自动注入 GT 品牌主题：
  主色 #4b2d77（紫）
  辅助色 #0094B3（水鸭蓝）/ #FF5149（珊瑚橙）/ #F5A623（琥珀黄）/ #28a745（绿）
  背景 #f8f6fb（浅紫灰）
  字体 PingFang SC / Microsoft YaHei
-->
```

### 看板数据缓存策略
```
Redis 缓存 key 规范：
  dashboard:global:overview         TTL=30s  （全局指标）
  dashboard:global:risk-alerts      TTL=60s  （风险预警）
  dashboard:project:{id}:overview   TTL=30s  （项目进度）
  dashboard:project:{id}:wp-matrix  TTL=60s  （底稿矩阵）
  dashboard:my:{user_id}            TTL=30s  （个人看板）

失效策略：
  - 底稿状态变更 → 失效 project:{id}:wp-matrix
  - 调整分录变更 → 失效 project:{id}:overview + global:overview
  - 工时填报 → 失效 global:overview + my:{user_id}
```


### 9.10 底稿交叉索引与完成度（补充设计，对应需求 9e）

```
交叉索引自动建立：
  WOPI PutFile → ParseService 解析底稿
    → 扫描所有 WP() 函数调用（正则匹配 =WP("xxx","yyy")）
    → 提取引用的底稿编号和单元格
    → 写入 wp_cross_ref 表（source_wp_id, target_wp_code, target_cell_ref）
    → 同时扫描 TB()/AUX() 函数建立底稿→科目的引用关系

引用关系图可视化：
  ECharts 力导向图（force layout）
    ├── 节点 = 底稿（按循环着色，大小按引用数）
    ├── 边 = WP() 引用关系（有向箭头）
    ├── 点击节点 → 打开底稿
    └── 高亮受影响路径（修改某底稿时，高亮所有引用它的底稿）

完成度统计：
  GET /api/projects/{id}/workpapers/progress
    → 按审计循环分组统计：
      { cycle: "E", total: 11, not_started: 3, in_progress: 2, prepared: 4, reviewed: 1, archived: 1 }
    → 项目整体完成率 = (prepared + reviewed + archived) / total

超期预警：
  GET /api/projects/{id}/workpapers/overdue?days=7
    → 查询 assigned_at + N天 < now() 且 status = not_started 的底稿
    → 返回 [{wp_code, wp_name, assigned_to, assigned_at, overdue_days}]
```

### 9.11 AI 辅助底稿编制（补充设计，对应需求 9f）

```
分析性复核底稿自动生成：
  POST /api/workpapers/{wp_id}/ai/analytical-review
    → 从 trial_balance 取当期+上期数据
    → 计算变动额和变动率
    → 调用 LLM（注入 TSJ/ 对应科目提示词作为 system prompt）
    → 生成结构化分析：
      {
        account_code: "1001",
        current_balance: 5000000,
        prior_balance: 3000000,
        change_amount: 2000000,
        change_rate: 0.667,
        is_significant: true,  // 变动率 > 20% 或变动额 > 重要性水平
        ai_analysis: "货币资金较上年增长 66.7%，主要系...",
        recommended_procedures: ["核实大额收款来源", "检查银行对账单"]
      }
    → 写入 working_paper.parsed_data.ai_review JSONB

函证对象自动提取：
  POST /api/workpapers/{wp_id}/ai/extract-confirmations
    → 从 tb_aux_balance 按科目（1122应收账款/2202应付账款）提取辅助维度
    → 按期末余额降序排列
    → 返回 [{aux_name, aux_code, closing_balance, opening_balance, contact_info?}]
    → 前端展示为函证候选列表，用户勾选后批量生成函证

审定表核对：
  POST /api/workpapers/{wp_id}/ai/check-consistency
    → 从 parsed_data 取底稿审定数
    → 从 financial_report 取报表行次金额
    → 逐科目比对
    → 返回 [{account_code, wp_amount, report_amount, diff, status}]
```

### 1.8 委派推送机制（补充设计，对应需求 1.8）

```
委派触发通知：
  POST /api/projects/{id}/assignments 保存委派
    → 遍历新增的 project_assignments
    → 对每个被委派人员：
      1. 写入 notifications 表（type=ASSIGNMENT_CREATED, recipient=staff.user_id）
      2. 如果 staff.user_id 存在（已关联登录账号）：
         → SSE 推送实时通知
         → 通知内容："您已被委派到项目 XXX，角色：审计员，负责循环：D/E"
      3. 通知中包含"开始填报工时"快捷链接 → 跳转到 WorkHoursPage

被委派人员首页：
  Dashboard.vue / PersonalDashboard.vue
    → GET /api/my/assignments 获取当前用户被委派的项目列表
    → 新委派项目卡片带"新"标签（assigned_at 在 7 天内）
    → 卡片底部显示"填报工时"快捷按钮
```
