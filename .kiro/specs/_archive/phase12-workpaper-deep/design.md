# Phase 12: 底稿深度开发 - 设计文档

---

## 1. 核心设计理念

### 1.1 人机协同原则

```
AI不替代审计判断，AI是审计助理的"副驾驶"
├── AI草拟 → 人工审阅确认 → AI根据反馈优化 → 人工最终定稿
├── 所有AI生成内容必须有明确标记（ai_content字段）
├── 未经人工确认的AI内容 → QC规则QC-02阻断提交复核
└── AI建议可一键采纳或一键忽略，不强制
```

### 1.2 五阶段工作流

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 底稿生成（全自动）                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ 模板复制  │ →  │ 表头填充  │ →  │ 公式预填  │              │
│  │ (自动)    │    │ (自动)    │    │ (自动)    │              │
│  └──────────┘    └──────────┘    └──────────┘              │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: 数据核对（人机协同）                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ AI标记   │ →  │ 人工核对  │ →  │ 确认/调整 │              │
│  │ 异常值   │    │ 逐行确认  │    │ 修正数据  │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│  异常值：审定数与试算表差异>0.01元、变动率>30%、AJE>重要性    │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: 审计说明（人机协同★核心创新）                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ AI草拟   │ →  │ 人工编辑  │ →  │ AI优化   │              │
│  │ 说明草稿 │    │ 修改补充  │    │ 润色定稿  │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│  数据采集：试算表+调整分录+科目映射+TSJ要点+抽样结果          │
├─────────────────────────────────────────────────────────────┤
│  Phase 4: 自检提交（自动+人工）                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ QC自检   │ →  │ 人工修复  │ →  │ 提交复核  │              │
│  │ (18条)   │    │ 阻断项    │    │ (门禁检查)│              │
│  └──────────┘    └──────────┘    └──────────┘              │
│  QC-02门禁：检查ai_content中status=pending的项              │
├─────────────────────────────────────────────────────────────┤
│  Phase 5: 复核（人机协同）                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ AI预审   │ →  │ 复核人    │ →  │ 通过/退回 │              │
│  │ 标记问题 │    │ 人工判断  │    │ (附原因)  │              │
│  └──────────┘    └──────────┘    └──────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 设计收敛原则

| 原则 | 说明 |
|------|------|
| MVP优先 | 本期上线承诺限定为P0 + P1-1/P1-2/P1-4/P1-6/P1-7，增强项在核心闭环稳定后插入 |
| 单一真相源 | 底稿工作簿是审计说明、审定数、结论的最终归档载体，`parsed_data` 仅作为缓存和检索镜像 |
| 长任务job化 | 批量刷新、批量生成、批量提交复核、打包下载统一走后台任务模型，前端依赖 `job_id` 恢复进度 |
| 全链路可追溯 | AI生成必须记录 `prompt_version`、`model`、`generation_id`、`confirmed_by`，支持回放与审计 |

---

## 2. 角色化功能设计

### 2.1 审计助理 — 编制工具集

```
┌──────────────────────────────────────────────────┐
│ 底稿列表（仅自己负责的循环）                      │
│ 底稿编辑（在线为主，离线接口预留）                │
│ 预填充刷新（过期提示）                           │
│ ┌────────────────────────────────────────┐     │
│ │ ★ 审计说明AI生成面板                    │     │
│ │ - 数据采集：TB+Adjustments+Mapping+TSJ│     │
│ │ - SSE流式输出草稿                      │     │
│ │ - TipTap编辑器修改（支持数据标签）     │     │
│ │ - 采纳/重新生成/手动编写               │     │
│ └────────────────────────────────────────┘     │
│ AI对话助手（上下文注入底稿数据）                  │
│ QC自检（一键检查，未通过项跳转定位）              │
│ 提交复核（门禁检查）                              │
│ 查看复核意见 + 回复                              │
│ 附件上传关联（证据链可视化）                      │
└──────────────────────────────────────────────────┘
```

### 2.2 项目经理 — 管控面板 + 复核工作台

```
┌──────────────────────────────────────────────────┐
│ 全部底稿列表（所有循环）+ 批量操作模式            │
│ ┌────────────────────────────────────────┐     │
│ │ 进度总览面板                            │     │
│ │ - 进度矩阵（循环×状态）                 │     │
│ │ - 关键指标（完成率/待复核/逾期/stale） │     │
│ │ - 甘特图（编制周期可视化）              │     │
│ │ - 人员负荷（识别负荷不均）              │     │
│ └────────────────────────────────────────┘     │
│ ┌────────────────────────────────────────┐     │
│ │ ★ 复核工作台                            │     │
│ │ 左栏：待复核队列（首次/退回重提交）     │     │
│ │ 中栏：只读预览（关键数据标红）          │     │
│ │ 右栏：AI预审结果 + 复核意见 + 操作      │     │
│ │ 快捷键：Ctrl+Enter通过，Ctrl+Shift+Enter退回│  │
│ └────────────────────────────────────────┘     │
│ 数据一致性监控（底稿vs试算表vs附注）              │
│ 批量操作（分配/刷新/生成说明/下载，job跟踪）      │
└──────────────────────────────────────────────────┘
```

### 2.3 合伙人 — 风险聚焦 + 签字前检查

```
┌──────────────────────────────────────────────────┐
│ 风险底稿聚焦视图（仅高风险）                      │
│   筛选规则：金额>重要性、有AJE/RJE、QC阻断       │
│             被退回过、prefill_stale              │
│ ┌────────────────────────────────────────┐     │
│ │ 签字前底稿专项检查清单                  │     │
│ │ ☐ 所有底稿复核状态=level2_passed        │     │
│ │ ☐ 所有底稿QC自检通过                    │     │
│ │ ☐ 所有底稿审计说明非空                  │     │
│ │ ☐ 底稿审定数与试算表一致                │     │
│ │ ☐ 关键底稿附件关联≥1                    │     │
│ │ 未通过项列出明细，点击跳转              │     │
│ └────────────────────────────────────────┘     │
│ 底稿质量趋势图表（ECharts）                      │
│ 底稿只读浏览 + 标记已阅                          │
└──────────────────────────────────────────────────┘
```

### 2.4 质控人员 — 独立抽查 + 合规检查

```
┌──────────────────────────────────────────────────┐
│ 全部底稿列表（独立于项目团队）                   │
│ QC规则执行结果总览                               │
│ ┌────────────────────────────────────────┐     │
│ │ 独立抽查工作台                          │     │
│ │ - 智能抽样：风险分层+循环均匀+编制人覆盖│     │
│ │ - 抽查清单：检查项逐项确认              │     │
│ │ - 抽查报告：结构化草稿（HTML/Markdown）  │     │
│ └────────────────────────────────────────┘     │
│ 合规性检查（格式+内容+时间）                     │
└──────────────────────────────────────────────────┘
```

---

## 3. 系统架构

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层                                │
│  WorkpaperList  WorkpaperEditor  WorkpaperWorkbench       │
│  ReviewWorkstation  ProjectProgressBoard  PartnerDashboard  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                      API层                                   │
│  working_paper.py  wp_explanation.py  wp_batch.py            │
│  wopi.py  wp_review.py  wp_ai.py  qc.py                      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     服务层                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │wp_explanation│ │wp_ai_service│ │wp_chat_service│           │
│  │_service.py  │ │             │ │（上下文增强）│            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │prefill_engine│ │wopi_service │ │qc_engine    │            │
│  │（解析增强）  │ │（只读+计时）│ │（18条规则） │            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐      │
│  │wp_guidance   │ │wp_template_ │ │wp_offline_       │      │
│  │_service     │ │migration    │ │pack_service      │      │
│  └─────────────┘ └─────────────┘ └──────────────────┘      │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     数据层                                   │
│  working_paper  trial_balance  adjustments  wp_edit_sessions │
│  procedure_instances（新增wp_id FK）  attachment_wp关联表    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据模型变更

> 注：MVP阶段优先落地 `wp_explanation_service`、`wp_ai_service`、`qc_engine`、`wopi_service` 与后台任务编排；推荐反馈、抽查工作台与其他增强服务按后续阶段插入。

底稿工作簿是最终归档载体，`parsed_data` 仅作为缓存和检索镜像，供列表、工作台与QC快速读取。

```sql
-- WorkingPaper表新增结构化字段
ALTER TABLE working_papers ADD COLUMN workflow_status VARCHAR(30) DEFAULT 'draft';
ALTER TABLE working_papers ADD COLUMN explanation_status VARCHAR(30) DEFAULT 'not_started';
ALTER TABLE working_papers ADD COLUMN consistency_status VARCHAR(30) DEFAULT 'unknown';
ALTER TABLE working_papers ADD COLUMN last_parsed_sync_at TIMESTAMP;
ALTER TABLE working_papers ADD COLUMN prefill_stale_reason VARCHAR(50);
ALTER TABLE working_papers ADD COLUMN partner_reviewed_at TIMESTAMP;
ALTER TABLE working_papers ADD COLUMN partner_reviewed_by UUID REFERENCES users(id);

-- parsed_data JSONB结构扩展（缓存镜像，不作为最终归档权威源）
{
    "audited_amount": 12000,
    "conclusion": "...",
    "audit_explanation": "...",        -- 工作簿说明正文的缓存镜像
    "procedure_status": {...},
    "attachment_refs": [...],
    "formula_cells": [...],
    "ai_content": {
        "latest_generation_id": "uuid",
        "latest_status": "confirmed",  -- ai_drafted/user_edited/confirmed/sync_failed
        "last_confirmed_at": "2025-03-15T11:00:00",
        "review_suggestions": [...]
    }
}

-- 新增表：AI生成历史（完整留痕）
CREATE TABLE wp_ai_generations (
    id UUID PRIMARY KEY,
    wp_id UUID REFERENCES working_papers(id),
    prompt_version VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    input_hash VARCHAR(64),
    output_text TEXT,
    output_structured JSONB,
    status VARCHAR(30),                -- drafted/confirmed/rejected
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    confirmed_by UUID REFERENCES users(id),
    confirmed_at TIMESTAMP
);

-- 新增表：批量/长任务编排
CREATE TABLE background_jobs (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    job_type VARCHAR(50) NOT NULL,     -- prefill/generate_explanation/submit_review/download_pack
    status VARCHAR(30) NOT NULL,       -- queued/running/partial_failed/succeeded/failed/cancelled
    payload JSONB,
    progress_total INTEGER DEFAULT 0,
    progress_done INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    initiated_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE background_job_items (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES background_jobs(id),
    wp_id UUID REFERENCES working_papers(id),
    status VARCHAR(30) NOT NULL,
    error_message TEXT,
    finished_at TIMESTAMP
);

-- 新增索引：用于统计查询
CREATE INDEX idx_wp_ai_generations_wp ON wp_ai_generations(wp_id, created_at DESC);
CREATE INDEX idx_background_jobs_project ON background_jobs(project_id, created_at DESC);
CREATE INDEX idx_background_job_items_job ON background_job_items(job_id, status);
CREATE INDEX idx_wp_feedback_project ON wp_recommendation_feedback(project_id);
CREATE INDEX idx_wp_feedback_action ON wp_recommendation_feedback(action, action_at);
CREATE INDEX idx_wp_feedback_type ON wp_recommendation_feedback(project_type, industry);
```

### 3.3 状态机定义

| 对象 | 状态 | 允许转移 | 阻断条件 |
|------|------|---------|---------|
| `workflow_status` | `draft` → `in_progress` → `self_checked` → `submitted_for_review` → `review_passed` / `review_returned` → `partner_checked` → `archived` | 退回后可重新进入 `in_progress` | QC阻断、说明未同步、数据不一致时不可提交复核 |
| `explanation_status` | `not_started` → `ai_drafted` → `user_edited` → `confirmed` → `written_back` → `synced` | 写回失败进入 `sync_failed`，修复后重新写回 | `sync_failed` 或 `not_started` 时不可提交复核 |
| `prefill` 新鲜度 | `fresh` / `stale_by_tb` / `stale_by_adjustment` / `stale_by_template` / `refreshing` | `stale_*` 经刷新进入 `refreshing`，成功后回到 `fresh` | stale 超24小时触发警告 |
| `job_status` | `queued` → `running` → `succeeded` / `partial_failed` / `failed` / `cancelled` | `partial_failed` / `failed` 可经 retry 回到 `running` | `failed` 前端需展示失败项并允许恢复 |

---

## 4. 核心服务设计

### 4.1 审计说明生成服务

```python
class WpExplanationService:
    """审计说明智能生成 — 人机协同模式"""

    async def generate_draft(self, db, project_id, year, wp_id) -> dict:
        """
        只生成草稿，不直接覆盖工作簿正文。

        数据采集（token预算分配，总上下文≤6000 tokens）：
        1. 试算表数据（~200 tokens）：审定数/未审数/AJE/RJE/变动率/上年同期
        2. 调整分录明细（~300 tokens）：最多5条，金额+摘要
        3. 科目特征（~100 tokens）：循环/关联底稿/附注章节
        4. TSJ审计要点（~500 tokens）：截取前500字
        5. 抽样结果（~200 tokens）：样本量/异常数/结论
        6. 预留输出空间（~2000 tokens）

        返回：
        {
            "generation_id": "uuid",
            "prompt_version": "wp_expl_v3",
            "draft_text": "完整审计说明文本",
            "structured": { objective, procedures, findings, conclusion },
            "data_sources": ["trial_balance", "adjustments", ...],
            "confidence": "high/medium/low",
            "suggestions": ["建议补充抽样结果"]
        }
        """

    async def confirm_draft(self, db, wp_id, generation_id, final_text, user_id) -> dict:
        """
        人工确认后的唯一生效入口：
        1. 将final_text写回底稿工作簿指定区域
        2. 写回成功后刷新 parsed_data.audit_explanation
        3. 更新 explanation_status='written_back' -> 'synced'
        4. 记录 confirmed_by / confirmed_at / last_parsed_sync_at
        """

    async def refine_draft(self, db, wp_id, generation_id, user_edits, feedback) -> dict:
        """基于用户修改优化草稿，但不绕过 confirm_draft 直接生效"""

    async def batch_generate(self, db, project_id, year, wp_ids) -> dict:
        """创建后台任务，返回job_id，由 BackgroundJobService 推进"""
```

### 4.1.1 审计说明写回与同步机制

1. `generate_draft` 仅生成草稿并留痕，不直接覆盖工作簿正文。
2. 用户点击“采纳/确认”时统一走 `confirm_draft`，先写回底稿工作簿。
3. 写回成功后立即触发解析刷新，更新 `parsed_data.audit_explanation` 与 `last_parsed_sync_at`。
4. 如写回或解析失败，`explanation_status=sync_failed`，QC与提交复核全部阻断，前端提示重试。

### 4.2 AI预审服务

```python
class WpAiService:
    async def review_workpaper_content(self, db, wp_id) -> dict:
        """
        AI预审检查：
        1. 数据一致性：底稿审定数 vs 试算表
        2. 说明完整性：字数、关键要素（程序/发现/结论）
        3. 结论合理性：与审定数是否匹配

        返回：{
            "issues": [
                {
                    "description": "审定数与试算表差异500元",
                    "severity": "warning/blocking",
                    "suggested_action": "核实差异原因"
                }
            ]
        }
        """
```

### 4.2.1 后台任务编排服务

```python
class BackgroundJobService:
    """统一管理批量刷新/生成/提交/下载等长任务"""

    async def create_job(self, db, project_id, job_type, wp_ids, payload, user_id) -> dict:
        """创建 background_jobs + background_job_items，返回 job_id"""

    async def run_job(self, db, job_id) -> None:
        """
        统一执行模型：
        - queued -> running
        - 按wp粒度记录成功/失败
        - 结束后置为 succeeded / partial_failed / failed
        """

    async def retry_job(self, db, job_id) -> dict:
        """仅重试失败项，保留原始审计轨迹"""

    async def get_job_stream(self, job_id):
        """SSE事件流：started/progress/item_failed/completed"""
```

### 4.3 QC引擎增强

```python
# 新增4条内容级规则

QC-15 审计说明完整性:
  - parsed_data.audit_explanation非空且≥50字
  - explanation_status必须为synced
  - 包含关键要素：执行程序描述+审计发现+审计结论

QC-16 数据引用一致性:
  - parsed_data.audited_amount vs trial_balance.audited_amount
  - 误差>0.01元即阻断

QC-17 附件证据充分性:
  - 重要性以上科目底稿至少关联1个附件
  - 从attachment_working_paper+materiality联合查询

QC-18 底稿间交叉引用完整性:
  - parsed_data.cross_refs中引用的底稿编号都存在
  - 被引用底稿状态不是draft
```

### 4.4 底稿推荐反馈服务

```python
class WpMappingFeedbackService:
    """底稿推荐反馈闭环 — 学习用户行为优化推荐"""

    async def record_recommendation(self, db, project_id, recommended_wp_ids) -> None:
        """记录本次推荐结果"""

    async def record_feedback(self, db, recommend_id, wp_id, action) -> None:
        """
        记录用户反馈：
        - action: 'accepted'/'skipped'/'manually_added'
        - accepted: 用户采纳了推荐
        - skipped: 用户跳过了推荐
        - manually_added: 用户手动添加了非推荐底稿（标记为遗漏）
        """

    async def get_recommend_stats(self, db, filters) -> dict:
        """
        推荐效果统计：
        - 按行业/企业规模/科目类别分组
        - 采纳率 = accepted / (accepted + skipped)
        - 遗漏率 = manually_added / total_generated
        """

    async def optimize_recommend_rules(self, db) -> None:
        """
        推荐规则自优化：
        - 采纳率<30%的规则降权
        - 遗漏率>20%的科目补充到推荐规则
        - 按项目类型（年审/专项/IPO）差异化权重
        """
```

### 4.5 底稿编制智能引导服务

```python
class WpGuidanceService:
    """底稿编制智能引导 — 根据底稿类型显示不同引导"""

    async def get_guidance(self, db, wp_id) -> dict:
        """
        根据wp_code判断底稿类型，返回对应引导：
        
        审定表（如D1-1）：
        - 引导：未审数→检查调整→确认审定数→写结论
        - TSJ要点：从tsj_prompt_service加载
        
        明细表（如D1-2）：
        - 引导：逐行核对→标记差异→记录发现
        - 程序检查清单：从wp_manual_service加载
        
        分析表（如D1-3）：
        - 引导：计算变动率→识别异常→解释原因
        - 分析指标：同比/环比/行业对比
        
        通用引导：
        - 表头完整性检查
        - 交叉引用完整性检查
        - 附件关联提醒
        """

    async def check_procedure_progress(self, db, wp_id) -> dict:
        """
        检查关联审计程序执行状态：
        - 从procedure_instances查询关联程序
        - 返回程序完成度（已执行/未执行/跳过）
        - 提示未执行程序对应的底稿区域
        """
```

### 4.6 数据提取可视化服务

```python
class WpVisualizationService:
    """数据提取可视化 — 公式高亮、来源追溯、差异对比"""

    async def get_formula_cells(self, wp_id) -> list:
        """
        获取所有公式单元格（从parsed_data缓存读取，不实时解析Excel）：
        - 预填充时 prefill_engine 已扫描并缓存公式到 parsed_data.formula_cells
        - 直接从 working_paper.parsed_data['formula_cells'] 读取
        - 返回单元格位置、公式内容、当前值、数据来源
        - 如果缓存为空，触发一次 prefill_engine.scan_formulas() 刷新缓存
        """

    async def get_cell_data_source(self, wp_id, cell_ref) -> dict:
        """
        获取单元格数据来源：
        - =TB('1001','期末余额') → 试算表科目1001期末余额
        - =AJE('1001') → 调整分录表AJE合计
        - 返回：来源表、来源行、字段名、原始值
        """

    async def compare_refresh_diff(self, wp_id, before_data, after_data) -> list:
        """
        对比刷新前后的差异：
        - 遍历所有公式单元格
        - 检测值变化的单元格
        - 返回：单元格位置、旧值、新值、变动率
        """

    async def generate_diff_summary(self, wp_id) -> dict:
        """
        生成差异摘要弹窗数据：
        - 变更单元格数量
        - 最大变动金额
        - 最大变动率
        - 建议关注项（变动率>30%标红）
        """
```

### 4.7 底稿对话上下文增强服务

```python
class WpChatContextService:
    """底稿对话上下文注入 — 增强wp_chat_service"""

    def build_enhanced_context(self, project_id, wp_id) -> dict:
        """
        构建增强上下文：
        
        1. 当前底稿数据：
           - parsed_data：审定数/未审数/AJE/RJE/结论/说明
           - wp_status：file_status + review_status
        
        2. 关联科目数据：
           - trial_balance本科目行（未审/审定/AJE/RJE/变动）
           - adjustments本科目明细（分录号/摘要/金额/类型）
        
        3. 审计程序状态：
           - 关联procedure_instances执行状态
           - 程序执行记录
        
        4. QC结果：
           - 当前底稿QC检查结果
           - 未通过项列表
        
        5. 复核意见：
           - 当前未回复的复核意见
           - 历史意见记录
        
        6. TSJ审计要点：
           - 按科目名从tsj_prompt_service加载
           - 审计要点+检查清单
        
        返回结构化上下文，供LLM对话使用
        """

    def extract_suggestion(self, llm_response) -> dict:
        """
        从LLM回复中提取数值建议：
        - 识别"建议调整为xxx"模式
        - 返回：cell_ref + suggested_value + reason
        - 前端可一键应用
        """
```

### 4.8 ONLYOFFICE插件部署验证

```python
class OnlyofficePluginService:
    """ONLYOFFICE插件部署验证与增强"""

    async def verify_plugin_deployment(self) -> dict:
        """
        验证插件部署状态：
        1. 检查容器内插件目录存在性
           - /var/www/onlyoffice/documentserver/sdkjs-plugins/audit-formula
           - /var/www/onlyoffice/documentserver/sdkjs-plugins/audit-review
        2. 验证config.json格式正确
        3. 测试XHR调用/api/formula/execute可达
        4. 返回部署状态报告
        """

    async def enhance_audit_formula_plugin(self) -> None:
        """
        audit-formula插件增强：
        1. 新增EXPLAIN()函数：调用/wp-ai/generate-explanation
        2. 新增REFRESH()函数：触发当前底稿预填充刷新
        3. 错误提示本地化：从#REF!改为中文提示
           - "科目编码不存在"
           - "试算表数据未找到"
           - "请先导入科目余额表"
        """

    async def enhance_audit_review_plugin(self) -> None:
        """
        audit-review插件增强：
        1. 复核批注与系统ReviewRecord同步
        2. 批注状态实时更新（open/replied/resolved）
        3. 支持@提及通知
        """
```

### 4.9 证据链可视化服务

```python
class AttachmentEvidenceChainService:
    """证据链可视化服务 — 附件与底稿关联可视化"""

    async def get_wp_attachments(self, wp_id) -> list:
        """
        获取底稿关联附件列表：
        1. 从attachment_working_paper表查询关联附件
        2. 返回：attachment_id, filename, upload_time, uploader, evidence_type
        3. evidence_type: '原始凭证'|'分析说明'|'沟通记录'|'其他'
        """

    async def quick_attach(self, wp_id, attachment_ids) -> dict:
        """
        快速关联附件：
        1. 批量插入attachment_working_paper记录
        2. 设置evidence_type默认为'原始凭证'
        3. 返回成功数量
        """

    async def generate_evidence_graph(self, wp_id) -> dict:
        """
        生成证据图谱：
        1. 查询当前底稿关联的所有附件
        2. 查询这些附件还关联了哪些其他底稿
        3. 构建关系图：底稿<->附件<->底稿
        4. 返回节点和边数据（ECharts格式）
        """

    async def get_attachment_timeline(self, wp_id) -> list:
        """
        获取附件时间线：
        1. 按上传时间排序关联附件
        2. 标注附件与底稿编制阶段的关系
        3. 返回时间线数据（Timeline组件格式）
        """
```

### 4.10 可用性降级服务

```python
class AvailabilityFallbackService:
    """可用性降级服务 — 处理异常场景的降级逻辑"""

    async def handle_llm_failure(self, wp_id) -> dict:
        """
        AI生成失败降级：
        1. 检测vLLM服务状态（超时/错误）
        2. 设置全局降级标志（Redis: llm_fallback=true）
        3. 前端显示"AI服务暂不可用"提示
        4. 提供手动编写模式（TipTap编辑器正常工作）
        5. 重试机制：每30秒检测一次服务恢复，恢复后清除降级标志
        """

    async def handle_batch_interrupt(self, job_id) -> dict:
        """
        批量操作中断处理：
        1. 已完成项保留在 `background_job_items` 中为 succeeded
        2. 未完成项统一标记为 failed 或 cancelled
        3. 前端基于 `job_id` 恢复展示进度、失败项和错误原因
        4. 用户点击重试时仅重放失败项，保留原始审计轨迹
        5. 页面刷新后可通过 `GET /jobs/{job_id}` 继续查看状态
        """

    async def handle_network_recovery(self, user_id) -> dict:
        """
        网络中断恢复（后端部分）：
        1. 提供 POST /api/sync-pending-data 端点接收前端暂存数据
        2. 冲突检测：比对服务端版本号 vs 客户端版本号
        3. 冲突时返回 conflict 列表，由前端提示用户选择
        4. 无冲突时直接合并保存
        
        前端部分（IndexedDB，不在此服务中）：
        - 本地暂存未同步数据（<10MB限制）
        - navigator.onLine 检测网络状态
        - 恢复后自动调用 sync-pending-data API
        """

    async def handle_lock_conflict(self, wp_id, user_id) -> dict:
        """
        底稿锁定冲突：
        1. WOPI检测到锁被其他用户持有
        2. 返回ReadOnly=True + ReadOnlyReason="其他用户正在编辑"
        3. 前端显示冲突提示，提供两个选项：
           - "只读浏览"：打开只读模式（<2秒）
           - "稍后提醒"：设置定时器（30秒后提醒）
        4. 定时器检测锁释放后，自动通知用户
        """
```

---

## 5. API设计

### 5.1 审计说明API

```yaml
POST /api/projects/{id}/wp-ai/{wp_id}/generate-explanation
  - 生成审计说明草稿
  - 返回: { generation_id, prompt_version, draft_text, data_sources, confidence, suggestions }

POST /api/projects/{id}/wp-ai/{wp_id}/confirm-explanation
  - 人工确认并写回底稿工作簿
  - body: { generation_id, final_text }
  - 返回: { explanation_status, last_parsed_sync_at }

POST /api/projects/{id}/wp-ai/{wp_id}/refine-explanation
  - 根据用户反馈优化草稿
  - body: { generation_id, user_edits, feedback }

POST /api/projects/{id}/wp-ai/{wp_id}/review-content
  - AI审阅底稿内容
  - 返回: { issues: [{ description, severity, suggested_action }] }
```

### 5.2 批量操作与后台任务API

```yaml
POST /api/projects/{id}/working-papers/assign/batch
  - 批量分配编制人/复核人
  - body: { wp_ids[], assignee_id, role }
  - 返回: { job_id, status }

POST /api/projects/{id}/working-papers/prefill/batch
  - 批量刷新预填充
  - body: { wp_ids[] }
  - 返回: { job_id, status }

POST /api/projects/{id}/wp-ai/batch-explanation
  - 批量生成审计说明
  - body: { wp_ids[] }
  - 返回: { job_id, status }

POST /api/projects/{id}/working-papers/submit-review/batch
  - 批量提交复核（带QC门禁检查）
  - body: { wp_ids[] }
  - 返回: { job_id, status }

POST /api/projects/{id}/working-papers/download-pack
  - 批量下载ZIP
  - body: { wp_ids[] }
  - 返回: { job_id, status }

GET /api/projects/{id}/jobs/{job_id}
  - 获取后台任务状态
  - 返回: { status, progress_total, progress_done, failed_count, items[] }

GET /api/projects/{id}/jobs/{job_id}/events
  - SSE订阅后台任务事件流

POST /api/projects/{id}/jobs/{job_id}/retry
  - 重试失败项
  - 返回: { job_id, retried_count }
```

### 5.3 合伙人API

```yaml
POST /api/projects/{id}/partner/workpaper-readiness
  - 签字前底稿专项检查
  - 返回: { 
      all_review_passed, all_qc_passed, all_has_explanation,
      no_prefill_stale, key_wp_has_attachment, failed_items[]
    }

GET /api/projects/{id}/partner/risk-workpapers
  - 风险底稿列表
  - query: { materiality_threshold, include_aje, include_rejected }
```

### 5.4 推荐反馈API

```yaml
POST /api/projects/{id}/wp-mapping/recommend-feedback
  - 记录推荐采纳/跳过/手动添加反馈
  - body: { recommend_id, wp_id, action: 'accepted'|'skipped'|'manually_added' }

GET /api/wp-mapping/recommend-stats
  - 推荐效果统计
  - query: { project_type, industry, date_range }
  - 返回: { adoption_rate, omission_rate, by_category[] }
```

### 5.5 智能引导API

```yaml
GET /api/projects/{id}/working-papers/{wp_id}/guidance
  - 获取底稿编制引导
  - 返回: { 
      wp_type: 'audited'|'detail'|'analysis',
      steps: [],
      tsj_points: [],
      procedure_progress: {}
    }

GET /api/projects/{id}/working-papers/{wp_id}/procedure-check
  - 检查关联审计程序执行状态
  - 返回: { procedures[], completed_count, total_count }
```

### 5.6 数据可视化API

```yaml
GET /api/projects/{id}/working-papers/{wp_id}/formula-cells
  - 获取公式单元格列表
  - 返回: [{ cell_ref, formula, current_value }]

GET /api/projects/{id}/working-papers/{wp_id}/cell-data-source
  - 获取单元格数据来源
  - query: { cell_ref }
  - 返回: { source_table, source_row, field_name, original_value }

POST /api/projects/{id}/working-papers/{wp_id}/compare-refresh
  - 对比刷新前后差异
  - body: { before_snapshot, after_snapshot }
  - 返回: { changes: [{ cell_ref, old_value, new_value, change_rate }] }
```

### 5.7 ONLYOFFICE插件API

```yaml
GET /api/system/onlyoffice-plugin-status
  - 检查ONLYOFFICE插件部署状态
  - 返回: { audit_formula_deployed, audit_review_deployed, errors[] }

POST /api/system/onlyoffice-plugin-verify
  - 验证插件配置并测试调用
  - 返回: { verified, details: {} }
```

### 5.8 证据链可视化API

```yaml
GET /api/projects/{id}/working-papers/{wp_id}/attachments
  - 获取底稿关联附件列表
  - 返回: [{ attachment_id, filename, upload_time, uploader, evidence_type }]

POST /api/projects/{id}/working-papers/{wp_id}/attachments/quick-attach
  - 快速关联附件
  - body: { attachment_ids[] }
  - 返回: { success_count, failed_count }

GET /api/projects/{id}/working-papers/{wp_id}/evidence-graph
  - 生成证据图谱
  - 返回: { nodes: [], edges: [] } (ECharts格式)

GET /api/projects/{id}/working-papers/{wp_id}/attachment-timeline
  - 获取附件时间线
  - 返回: { events: [] } (Timeline组件格式)
```

---

## 6. 关键算法与机制

### 6.1 数据一致性校验

| 校验项 | 逻辑 | 级别 |
|--------|------|------|
| 审定数一致性 | 底稿 vs 试算表，误差>0.01元 | 阻断 |
| AJE合计一致性 | 底稿 vs adjustments表 | 阻断 |
| RJE合计一致性 | 底稿 vs adjustments表 | 阻断 |
| 交叉引用有效性 | 被引用底稿状态≠draft | 阻断 |
| 说明字数 | <50字警告，<20字阻断 | 警告/阻断 |
| 附件充分性 | 重要性以上科目附件数≥1 | 阻断 |
| 数据新鲜度 | prefill_stale=true超24小时 | 警告 |

### 6.2 LLM调用约定

| 参数 | 设置 |
|------|------|
| 模型 | Qwen3.5-27B-NVFP4（本地vLLM） |
| enable_thinking | false |
| temperature | 0.3 |
| max_tokens | 2000 |
| 超时 | 30s（单次），批量时每底稿独立 |
| 失败降级 | 显示"AI服务暂不可用"，不阻断 |

### 6.3 监控告警响应流程

| 告警级别 | 响应时间 | 处理流程 | 通知对象 |
|---------|---------|---------|---------|
| P0（阻断） | 5分钟内 | 立即通知→开发负责人→30分钟内修复或降级→事后复盘 | 开发负责人+项目经理 |
| P1（警告） | 30分钟内 | 通知负责人→评估影响→4小时内处理或降级 | 开发负责人 |
| P2（提示） | 2小时内 | 记录日志→周会复盘→排期优化 | 技术团队 |

**告警指标定义**：
- 错误率 > 5% 持续10分钟 → P0
- 响应时间 > 5秒 持续5分钟 → P0
- LLM服务不可用 → P0
- 数据库连接池耗尽 → P0
- 批量操作失败率 > 10% → P1
- 缓存命中率 < 80% → P2
- 队列积压 > 1000 → P1

### 6.4 WOPI只读模式

```python
# check_file_info增加只读判断
if current_user != lock_holder:
    return {
        "UserCanWrite": False,
        "ReadOnly": True,
        "ReadOnlyReason": "其他用户正在编辑"
    }
if current_user.role == "reviewer":
    return {
        "UserCanWrite": False,
        "ReadOnly": True,
        "ReadOnlyReason": "复核模式"
    }
```

---

## 7. 前端组件清单

| 组件名 | 用途 | 角色 |
|--------|------|------|
| WorkpaperList | 底稿列表+批量操作模式 | 全部 |
| WorkpaperEditor | 在线编辑+过期提示 | 审计助理 |
| WorkpaperWorkbench | 三栏工作台+审计说明面板 | 审计助理 |
| ReviewWorkstation | 复核工作台+AI预审 | 项目经理 |
| ProjectProgressBoard | 进度总览+矩阵+甘特图 | 项目经理 |
| DataConsistencyMonitor | 数据一致性监控 | 项目经理 |
| PartnerDashboard | 风险视图+签字前检查 | 合伙人 |
| QCDashboard | 抽查工作台+合规检查 | 质控 |

---

## 8. 与四表系统衔接

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  tb_balance   │     │  tb_ledger   │     │  adjustments │
│  (科目余额表) │     │  (序时账)     │     │  (调整分录)   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                    trial_balance (试算表)                  │
└──────────────────────┬───────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐ ┌─────────┐ ┌──────────────┐
   │ 底稿预填充  │ │ 报表生成 │ │ 附注生成      │
   └─────┬──────┘ └─────────┘ └──────────────┘
         │
         ▼
   ┌──────────────────────────────────────────┐
   │           working_paper (底稿)            │
   │  事件级联：                                │
   │  DATA_IMPORTED → 标记 stale               │
   │  ADJUSTMENT_CHANGED → 标记关联科目 stale   │
   │  WORKPAPER_SAVED → 比对审定数一致性        │
   └──────────────────────────────────────────┘
```
