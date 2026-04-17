# Phase 10 — 技术设计

## 1. 底稿下载与导入

### 1a 下载流程
```
用户勾选底稿 → POST /api/projects/{id}/workpapers/download-pack
  body: { wp_ids: [uuid], include_prefill: true }
  → 后端：
    1. 遍历 wp_ids，对每个底稿调用 PrefillService.prefill_workpaper()
    2. 用 zipfile 打包为 ZIP（目录结构：{cycle}/{wp_code}_{wp_name}.xlsx）
    3. StreamingResponse 返回 ZIP 文件
```

### 1b 导入流程
```
用户上传 Excel → POST /api/projects/{id}/workpapers/{wp_id}/upload
  → 后端：
    1. 检查 file_version（请求头 X-WP-Version vs 数据库 file_version）
    2. 版本一致 → 直接覆盖文件，递增 file_version
    3. 版本不一致 → 返回 409 Conflict + 两个版本的 diff 摘要
    4. 覆盖后触发 ParseService.parse_workpaper() + WORKPAPER_SAVED 事件
```

## 2. 连续审计

### 数据模型
```
projects 表已有 parent_project_id（合并层级），连续审计用新字段：
  prior_year_project_id: UUID FK → projects.id（上年项目）

adjustments 表新增字段：
  is_continuous: BOOLEAN DEFAULT false（标记为连续审计结转分录）

连续审计创建流程：
  POST /api/projects/{id}/create-next-year
    → 复制 basic_info（client_name/company_code/template_type 等）
    → 复制 account_mapping（科目映射）
    → 复制 project_assignments（团队委派）
    → 设置 prior_year_project_id = 当前项目 ID
    → 上年 trial_balance.audited_* → 当年 trial_balance.opening_*
    → 上年 disclosure_note 期末 → 当年 disclosure_note 上期
    → 上年 adjustments(is_continuous=true) → 当年 adjustments
    → 上年 unadjusted_misstatements → 当年 carry_forward
```

## 3. 服务器存储

### 分区结构
```
storage/
├── projects/{project_id}/{year}/
│   ├── workpapers/          底稿文件
│   └── attachments/         附件
├── users/{user_id}/
│   └── private/             私人库（上限 1GB）
├── archives/                归档压缩包
└── temp/                    临时文件（定期清理）
```

### 私人库容量管理
```python
class PrivateStorageService:
    MAX_SIZE_BYTES = 1 * 1024 * 1024 * 1024  # 1GB
    WARN_THRESHOLD = 0.9  # 90%

    async def check_quota(self, user_id) -> dict:
        path = STORAGE_ROOT / "users" / str(user_id) / "private"
        used = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return {
            "used": used,
            "limit": self.MAX_SIZE_BYTES,
            "usage_pct": used / self.MAX_SIZE_BYTES,
            "warning": used / self.MAX_SIZE_BYTES >= self.WARN_THRESHOLD,
        }
```

## 4. 复核记录对话系统

### 数据模型
```
review_conversations 表（新增）
├── id: UUID PK
├── project_id: UUID FK
├── initiator_id: UUID FK → users.id（发起人）
├── target_id: UUID FK → users.id（被指定人）
├── related_object_type: VARCHAR（workpaper/disclosure_note/audit_report）
├── related_object_id: UUID
├── cell_ref: VARCHAR（可选，精确到单元格，如 "E9-1!B15"）
├── status: VARCHAR（open/in_progress/closed）
├── title: VARCHAR
├── created_at, closed_at

review_messages 表（新增）
├── id: UUID PK
├── conversation_id: UUID FK
├── sender_id: UUID FK → users.id
├── content: TEXT
├── message_type: VARCHAR（text/image/file）
├── attachment_path: VARCHAR（可选）
├── created_at
```

### 对话流程
```
发起人复核底稿 → 发现问题 → 创建复核记录
  → 选择指定人员 → POST /api/review-conversations
  → 被指定人收到 SSE 推送通知
  → 双方在对话窗口中交互（POST /api/review-conversations/{id}/messages）
  → 发起人点击"结束" → PUT /api/review-conversations/{id}/close
  → 对话记录可导出 Word（POST /api/review-conversations/{id}/export）
  → 看板显示进行中的对话数
```

## 5. LLM 对话填充底稿

### 架构
```
底稿编辑页面（WorkpaperEditor.vue）
├── ONLYOFFICE iframe（底稿内容）
├── LLM 对话侧边栏（ChatPanel）
│   ├── 上下文：当前底稿的 parsed_data + 四表数据 + 知识库
│   ├── 指令："帮我填写审定表" → LLM 生成内容 → 用户确认 → 写入底稿
│   ├── 指令："分析变动原因" → LLM 生成分析 → 填入审计说明区域
│   └── 指令："搜索知识库" → RAG 检索 → 返回相关文档片段
└── 联动：选中单元格 → 对话窗口显示该单元格上下文 → AI 回复填入

后端 API：
  POST /api/workpapers/{wp_id}/ai/chat
    body: { message, context: { selected_cell?, account_code? } }
    → SSE 流式返回 AI 回复
    → 回复中包含 fill_suggestion: { cell_ref, value } 供前端填入
```

## 6. 报告复核溯源

### 溯源链
```
报告复核页面 → 点击附注科目（如"五、9 固定资产"）
  → 后端查询：
    1. disclosure_note 中该科目的表格数据
    2. note_wp_mapping 找到关联底稿（E9-1 固定资产审定表）
    3. working_paper.parsed_data 中的审定数和审计说明
    4. tb_ledger 中该科目的大额交易明细
  → 前端展示溯源面板：
    ├── 附注数据（期末/期初/变动）
    ├── 底稿审定数（未审/调整/审定）
    ├── 审计说明（底稿中的文字说明）
    ├── 主要明细变动（Top10 大额交易）
    └── 复核意见输入框
```

## 7. 工时打卡与足迹

### 数据模型
```
check_ins 表（新增）
├── id: UUID PK
├── staff_id: UUID FK
├── check_time: TIMESTAMPTZ
├── latitude: NUMERIC(10,7)
├── longitude: NUMERIC(10,7)
├── location_name: VARCHAR（逆地理编码）
├── check_type: VARCHAR（morning/evening）
├── created_at

足迹生成（每半年 cron 任务）：
  → 查询 check_ins + project_assignments + work_hours
  → LLM 生成工作总结
  → 保存为 staff_members.resume_data 的一部分
  → 推送通知给成员和合伙人
```

## 8. 吐槽与求助专栏

### 数据模型
```
forum_posts 表（新增）
├── id: UUID PK
├── author_id: UUID FK → users.id
├── is_anonymous: BOOLEAN
├── category: VARCHAR（vent/help/share）
├── title: VARCHAR
├── content: TEXT
├── like_count: INT DEFAULT 0
├── is_deleted, created_at

forum_comments 表（新增）
├── id: UUID PK
├── post_id: UUID FK
├── author_id: UUID FK
├── content: TEXT
├── is_deleted, created_at
```

## 9. 辅助余额表明细汇总

### 匹配逻辑
```
GET /api/projects/{id}/ledger/aux-summary
  → 按 account_code 汇总 tb_aux_balance 的 closing_balance
  → 与 tb_balance 的 closing_balance 逐科目比对
  → 返回：
    [{
      account_code, account_name,
      tb_balance: 1000000,        // 科目余额表
      aux_summary: 1000000,       // 辅助汇总
      diff: 0,                    // 差异
      is_matched: true,           // 是否一致
      aux_details: [              // 辅助明细（不一致时展开）
        { aux_name: "客户A", balance: 500000 },
        { aux_name: "客户B", balance: 500000 },
      ]
    }]
```


## 10. 过程记录与人机协同标注（补充设计，对应需求 4）

### 底稿编辑记录
```
WOPI PutFile 触发时：
  → 记录到 logs 表：
    action_type: "workpaper_edit"
    object_type: "working_paper"
    object_id: wp_id
    new_value: { file_version, edited_by, edited_at, change_summary }
  → change_summary 由 ParseService 对比前后 parsed_data 生成
```

### 人机协同标注
```
AI 生成内容时：
  → 写入 ai_content 表（Phase 4 已定义）
  → content_type: data_fill / analytical_review / note_draft
  → confirmation_status: pending → accepted / modified / rejected
  → 前端显示 AI 标签（紫色背景 + "AI 辅助-待确认"）
  → 人工确认后标签变为"已确认"
```

## 11. 抽样程序增强（补充设计，对应需求 6）

### 截止性测试
```
POST /api/projects/{id}/sampling/cutoff-test
  body: { account_codes: ["6001"], days_before: 5, days_after: 5, amount_threshold: 10000 }
  → 查询 tb_ledger WHERE voucher_date BETWEEN (period_end - days_before) AND (period_end + days_after)
    AND account_code IN account_codes AND (debit_amount > threshold OR credit_amount > threshold)
  → 返回交易列表 + 自动填入截止性测试底稿模板
```

### 账龄分析
```
POST /api/projects/{id}/sampling/aging-analysis
  body: {
    account_code: "1122",
    aging_brackets: [
      { label: "1年以内", min_days: 0, max_days: 365 },
      { label: "1-2年", min_days: 366, max_days: 730 },
      { label: "2-3年", min_days: 731, max_days: 1095 },
      { label: "3年以上", min_days: 1096, max_days: null }
    ],
    base_date: "2025-12-31"  // 账龄计算基准日（默认审计期末）
  }
  → 先进先出（FIFO）账龄计算逻辑：
    1. 从 tb_aux_ledger 按辅助维度（客户/供应商）分组
    2. 每个辅助维度内，按 voucher_date 正序排列所有借方发生（形成应收）
    3. 按 voucher_date 正序排列所有贷方发生（回款核销）
    4. 贷方金额按先进先出原则依次核销最早的借方余额
    5. 未核销的借方余额按其原始 voucher_date 计算账龄天数 = base_date - voucher_date
    6. 按用户自定义的 aging_brackets 区间分组汇总
  → 兜底方案：用户可直接上传已有账龄分析 Excel（跳过 FIFO 计算）
  → 返回：
    [{
      aux_name: "客户A",
      total_balance: 500000,
      brackets: [
        { label: "1年以内", amount: 300000 },
        { label: "1-2年", amount: 150000 },
        { label: "2-3年", amount: 50000 },
        { label: "3年以上", amount: 0 }
      ]
    }]
  → 自动填入账龄分析底稿
```

### 月度明细
```
POST /api/projects/{id}/sampling/monthly-detail
  body: { account_code: "6001", year: 2025 }
  → 查询 tb_ledger GROUP BY accounting_period
  → 按月汇总借方/贷方/余额
  → 返回 12 个月的明细数据 + 自动填入底稿
```

## 12. 合并报表增强（补充设计，对应需求 7）

### 7a 合并锁定同步
```
projects 表新增字段：
  consol_lock: BOOLEAN DEFAULT false
  consol_lock_by: UUID FK → projects.id（锁定发起的合并项目）
  consol_lock_at: TIMESTAMPTZ

锁定流程：
  合并项目开始汇总 → PUT /api/consolidation/{parent_id}/lock
    → 遍历所有子公司项目，设置 consol_lock=true, consol_lock_by=parent_id
    → 锁定期间子公司的 trial_balance/adjustments API 返回 423 Locked
  合并完成 → PUT /api/consolidation/{parent_id}/unlock
    → 遍历所有子公司项目，设置 consol_lock=false
```

### 7b 外部单位报表导入
```
POST /api/consolidation/{project_id}/import-external
  body: multipart/form-data（Excel 报表 + Word 附注）
  → Excel 解析：提取四张报表行次数据，写入 consol_trial 的独立列
  → Word 附注：调用 history_note_parser 解析章节结构
  → LLM 辅助映射到合并附注模版
```

### 7c 独立模块入口
```
前端路由：
  /standalone/consolidation → 仅合并模块（导入各单位报表 → 合并）
  /standalone/report-review → 仅报告复核（上传报告+报表+附注 → 复核）
  /standalone/report-format → 仅报告排版（上传内容 → 排版导出）

后端：复用现有 API，不需要 project_id 时用临时项目
  → 临时项目：auto_created=true，project_type="standalone"
  → 生命周期：30天无操作自动清理（定时任务扫描 updated_at < now()-30d AND auto_created=true）
  → 用户可将临时项目转为正式项目（PUT /api/projects/{id}/promote）
```

## 13. LLM 底稿复核提示词（补充设计，对应需求 8a）

```
复核流程：
  POST /api/workpapers/{wp_id}/ai/review
    → 加载底稿 parsed_data
    → 根据 audit_cycle 从 TSJ/ 加载对应提示词（如 E 循环 → 货币资金提示词.md）
    → 构建 system prompt：提示词内容 + 底稿数据 + 试算表数据
    → 调用 llm_client.chat_completion()
    → 解析 LLM 回复为结构化 findings：
      [{
        finding_type: "data_discrepancy" | "logic_contradiction" | "completeness_gap",
        severity: "high" | "medium" | "low",
        description: "...",
        cell_reference: "E9-1!B15",
        suggestion: "..."
      }]
    → 写入 wp_qc_result 表
```

## 14. 私人库 RAG 对话（补充设计，对应需求 12b）

```
上传文档 → 向量化索引：
  POST /api/users/{id}/private-storage/upload
    → 保存文件到 storage/users/{id}/private/
    → 调用 UnifiedOCRService 提取文本（Word/PDF/图片）
    → 文本分块（chunk_size=500, overlap=50）
    → 调用 embedding API 生成向量
    → 存入 ChromaDB collection: private_{user_id}

RAG 对话：
  POST /api/users/{id}/private-storage/chat
    body: { message }
    → ChromaDB 检索 top-5 相关文档片段
    → 构建 prompt：用户消息 + 检索到的文档片段
    → 调用 llm_client.chat_completion(stream=True)
    → SSE 流式返回，回复中标注引用来源

私人库→知识库共享：
  POST /api/users/{id}/private-storage/share
    body: { file_ids: [uuid], target_library: "notes" }
    → 复制文件到 knowledge_service 对应分类目录
    → 创建知识库文档记录
    → 返回共享结果
```

## 15. 权限精细化（补充设计，对应需求 14）

```
删除权限检查中间件：
  在 DELETE 请求处理前检查：
    1. 获取目标对象的 created_by
    2. 当前用户 == created_by → 允许
    3. 当前用户角色 == manager 且 目标在同一项目 → 允许
    4. 当前用户角色 == partner 或 admin → 允许
    5. 否则 → 403 Forbidden

  实现方式：在各路由的 DELETE 端点中添加权限检查
  或：创建通用 check_delete_permission(user, object) 函数
```

## 16. 存储统计看板（补充设计，对应需求 3a.5）

```
GET /api/admin/storage-stats
  → 遍历 storage/ 目录，按项目/用户/年度统计占用
  → 返回：
    {
      total_size: 52GB,
      by_project: [{ project_id, name, size, wp_count }],
      by_user: [{ user_id, name, private_size }],
      by_year: [{ year, size }],
    }
  → 前端 ECharts 饼图/柱状图展示
```

## 跨 Phase 兼容性说明

| 冲突点 | 涉及 Phase | 解决方案 |
|--------|-----------|---------|
| 底稿导入 vs WOPI PutFile | 1b vs 10 | 共存：WOPI 用于在线编辑，Phase 10 用于离线回传 |
| 连续审计 vs 项目向导 | 9 vs 10 | 新增 create-next-year API，不修改现有向导 |
| 合并锁定 vs 合并试算表 | 9 vs 10 | 新增 consol_lock 字段，锁定期间返回 423 |
| 复核对话 vs 三级复核 | 3 vs 10 | 共存：review_records 正式复核，review_conversations 实时对话 |
| 私人库 vs 知识库 | 9 vs 10 | 不同存储路径（users/ vs knowledge/），可互相共享 |


## 17. 单元格级复核批注（需求 15）

### 数据模型
```
cell_annotations 表（新增）
├── id: UUID PK
├── project_id: UUID FK
├── object_type: VARCHAR（workpaper/disclosure_note/financial_report）
├── object_id: UUID
├── cell_ref: VARCHAR（如 "E9-1!B15" 或 "五、9.row3.col2"）
├── content: TEXT
├── priority: VARCHAR（high/medium/low）
├── status: VARCHAR（pending/replied/resolved）
├── author_id: UUID FK → users.id
├── mentioned_user_ids: JSONB（@提及的人员）
├── linked_annotation_id: UUID FK → cell_annotations.id（穿透关联的批注）
├── conversation_id: UUID FK → review_conversations.id（升级为对话时关联）
├── is_deleted, created_at, updated_at
```

### 穿透关联逻辑
```
附注单元格批注 → 通过 note_wp_mapping 找到关联底稿 → 自动创建 linked_annotation
底稿单元格批注 → 通过 note_wp_mapping 反向找到附注 → 自动创建 linked_annotation
```

## 18. 合并数据快照（需求 16）

### 数据模型
```
consol_snapshots 表（新增）
├── id: UUID PK
├── project_id: UUID FK（合并项目）
├── year: INT
├── snapshot_data: JSONB（各单体 trial_balance + 抵消分录 + 合并调整的完整快照）
├── trigger_reason: VARCHAR（manual/auto_on_generate/auto_on_lock）
├── diff_summary: JSONB（与上一次快照的差异摘要）
├── created_by: UUID FK
├── created_at
```

## 19. 底稿智能推荐（需求 17）

```
POST /api/projects/{id}/ai/recommend-workpapers
  → 输入：项目的 materiality + industry + prior_year_findings
  → LLM 分析风险等级，推荐底稿优先级
  → 返回：[{ wp_code, wp_name, risk_level, recommendation, reason }]
  → 与 procedure_instances 联动：高风险自动标记 status=execute
```

## 20. 年度差异分析报告（需求 19）

```
POST /api/projects/{id}/ai/annual-diff-report
  body: { save_to: "project" | "private" }  // 保存位置选项
  → 查询当年 trial_balance vs 上年（prior_year_project_id）
  → 计算全科目变动额/变动率
  → 筛选重大变动（>20% 或 >materiality）
  → LLM 逐科目生成分析说明
  → save_to == "project" → 保存为底稿（wp_index + working_paper）
  → save_to == "private" → 保存到私人库（PrivateStorageService）
  → 返回 Word 下载链接
```

## 21. 附件智能分类（需求 20）

```
POST /api/projects/{id}/attachments/upload
  → 保存文件
  → OCR 提取文本（UnifiedOCRService）
  → LLM 分类：{ type: "invoice", confidence: 0.95, suggested_wp_code: "D1-5" }
  → 自动创建 attachment_working_paper 关联
  → 返回分类结果供用户确认/修改
```

## 22. 报告排版模板（需求 21）

```
report_format_templates 表（新增）
├── id: UUID PK
├── template_name: VARCHAR（致同标准版/简化版/国企版/上市版）
├── template_type: VARCHAR（audit_report/management_letter/confirmation）
├── config: JSONB（字体/页边距/页眉页脚/水印/Logo路径）
├── version: INT
├── is_default: BOOLEAN
├── is_deleted, created_at, updated_at

排版预览：
  GET /api/report-format/preview?template_id=xxx&content=...
  → 后端用 python-docx 按模板配置渲染 → 转 HTML → 返回给前端 iframe
```


## 23. 知识库上下文感知（补充设计，对应需求 18）

```
LLM 对话上下文自动注入：
  POST /api/workpapers/{wp_id}/ai/chat
    → 后端自动构建上下文：
      1. 从 wp_index 获取 audit_cycle + wp_code
      2. 从 trial_balance 获取该科目的未审/调整/审定数
      3. 从 knowledge_retriever 按科目关键词检索知识库 top-5 文档片段
      4. 从 TSJ/ 加载对应审计循环的提示词
      5. 组装 system prompt = 提示词 + 科目数据 + 知识库片段
    → 用户消息作为 user prompt
    → llm_client.chat_completion(stream=True)

知识库检索排序：
  1. 同科目同行业的历史底稿（最高优先）
  2. 同科目不同行业的底稿
  3. 审计准则/法规文档
  4. 通用审计经验文档

"@知识库"触发：
  前端检测用户输入 "@知识库" 或 "@kb" 前缀
    → 弹出知识库搜索面板（复用 KnowledgeSearchPanel）
    → 选中文档后自动注入对话上下文
```

## 24. 复核对话权限补充

```
PUT /api/review-conversations/{id}/close
  → 权限校验：只有 initiator_id == current_user.id 才能关闭
  → 其他人调用返回 403 "只有发起人可以结束对话"
```

## 跨 Phase 兼容性说明（补充）

| 冲突点 | 涉及 Phase | 解决方案 |
|--------|-----------|---------|
| 单元格批注 vs ONLYOFFICE 批注插件 | 1b vs 10 | 共存：ONLYOFFICE 内部批注用于编辑时标注，系统级批注用于跨模块穿透 |
| 合并快照 vs consol_trial | 2 vs 10 | 快照存入独立 consol_snapshots 表，不修改 consol_trial |
| 底稿推荐 vs 程序裁剪 | 9 vs 10 | 推荐结果写入 procedure_instances.status，与裁剪共用 |
| 年度差异报告 vs 未审/已审对比 | 9 vs 10 | 不同维度：Phase 9 单张报表对比，Phase 10 全科目跨年差异 |
| 附件分类 vs 单据OCR | 4 vs 10 | 互补：Phase 4 结构化提取，Phase 10 类型分类+底稿关联 |
| 排版模板 vs PDF导出 | 1c vs 10 | Phase 10 新增模板管理层，导出引擎复用 Phase 1c |

## 25. 联动链路完整性设计（关键）

### 25a 底稿导入 → 试算表自动同步
```
底稿导入（Task 1.2）→ ParseService 解析审定数 → WORKPAPER_SAVED 事件
  → 事件处理器：
    1. 从 parsed_data 提取审定数（account_code → audited_amount）
    2. 与 trial_balance 当前审定数比对
    3. 差异时自动调用 tb_sync（POST /api/trial-balance/{project_id}/{year}/sync-from-workpaper）
    4. 触发 TRIAL_BALANCE_UPDATED → 报表重算 → 附注刷新
  → 全自动，无需人工干预

  前提：data/wp_parse_rules.json 定义每种底稿模板的解析规则：
    {
      "E9-1": {  // 固定资产审定表
        "account_code": "1601",
        "audited_cell": "F25",      // 审定数单元格
        "adjustment_cell": "E25",   // 调整数单元格
        "opening_cell": "C25",      // 期初数单元格
        "unadjusted_cell": "D25"    // 未审数单元格
      },
      ...
    }
  → 先覆盖核心 30 个审定表（E 循环），其余用 LLM 辅助识别单元格位置
```

### 25b 调整分录 → 底稿审定表反向联动
```
调整分录变更 → ADJUSTMENT_CREATED/UPDATED/DELETED 事件
  → 事件处理器：
    1. 标记关联科目底稿 prefill_stale=true（已有）
    2. 新增：自动汇总该科目所有 AJE/RJE 金额
    3. 通过 note_wp_mapping 找到对应底稿的审定表
    4. 用 openpyxl 更新底稿中"调整数"列的值
    5. 触发 WORKPAPER_SAVED → 级联更新
  → 或：底稿中用 AJE() 公式实时取数（ONLYOFFICE 自定义函数已支持）
```

### 25c 合并锁定中间件
```
新增 consol_lock_middleware.py：
  在 trial_balance/adjustments/misstatements 路由的 POST/PUT/DELETE 前检查：
    1. 从 request 获取 project_id
    2. 查询 projects.consol_lock
    3. consol_lock=true → 返回 423 Locked + { locked_by, locked_at, message }
    4. consol_lock=false → 放行
  → 实现为 FastAPI Depends 依赖注入，不用中间件（更精确控制哪些路由需要）
```

### 25d 连续审计底稿期初数结转
```
create-next-year API 中：
  → 遍历上年 working_paper 记录
  → 对每个底稿：
    1. 复制文件到当年目录
    2. 用 openpyxl 打开新底稿
    3. 从上年 parsed_data 提取审定数
    4. 写入新底稿的"期初数"列（根据模板映射规则）
    5. 清空"本期数"/"调整数"列
    6. 保存并创建新 working_paper 记录
```

### 25e 复核对话 deep link
```
review_conversations 表已有 related_object_type + related_object_id
新增字段：cell_ref VARCHAR（可选，精确到单元格）

前端通知点击：
  → router.push 到对应页面：
    workpaper → /projects/{id}/workpapers/{wp_id}/edit?highlight=cell_ref
    disclosure_note → /projects/{id}/disclosure-notes?section=note_id&cell=cell_ref
    audit_report → /projects/{id}/audit-report?paragraph=section_number
```

### 25f note_wp_mapping 自动初始化
```
项目底稿生成时（workpaper_generator.py）：
  → 根据模板集中的底稿编号规则，自动生成 note_wp_mapping：
    E9-1 固定资产审定表 → 附注"五、9 固定资产"
    E10-1 无形资产审定表 → 附注"五、10 无形资产"
    ...
  → 映射规则存储在 data/note_wp_mapping_rules.json
  → 先覆盖核心 30 个审定表，其余用 LLM 辅助匹配（根据底稿名称+科目编码推断）
  → 用户可在前端手动调整映射关系
```

### 25g 抽样结果 → 底稿填充映射
```
sampling_config 表新增字段：
  target_wp_id: UUID FK → working_paper.id（目标底稿）
  target_cell_range: VARCHAR（如 "B5:F50"，填入区域）

抽样完成后：
  → 从 sampling_records 提取选中样本
  → 用 openpyxl 写入 target_wp_id 的 target_cell_range
  → 触发 WORKPAPER_SAVED 事件
```

### 25h 附件分类 → 底稿匹配规则
```
LLM 分类后匹配底稿：
  1. 从附件 OCR 文本提取关键词（科目名称/编号/客户名称）
  2. 在 wp_index 中按 audit_cycle + account_code 模糊匹配
  3. 匹配到多个底稿时返回候选列表供用户选择
  4. 匹配规则：
     - 发票/合同 → 匹配收入/成本循环底稿（D 循环）
     - 银行对账单 → 匹配货币资金底稿（E1）
     - 函证回函 → 匹配对应科目的函证底稿
     - 会议纪要 → 匹配审计总结底稿（A 循环）
```

### 25i 合并解锁后自动刷新
```
PUT /api/consolidation/{parent_id}/unlock
  → 遍历所有子公司项目，设置 consol_lock=false
  → 自动触发合并试算表重算（调用 consol_trial 汇总 API）
  → 与上次快照对比，生成差异摘要
  → 前端显示"解锁完成，N 个科目有变动"提示
```

### 25j 连续审计额外结转项
```
create-next-year API 中额外结转：
  → 复制 note_wp_mapping（附注-底稿映射关系）
  → 复制 procedure_instances + procedure_trim_schemes（程序裁剪方案）
  → 复制 note_section_instances + note_trim_schemes（附注章节裁剪方案）
  → 复制 sampling_config（抽样配置，清空抽样记录）
  → 以上均设置 project_id = 新项目 ID
```

### 25k 知识库文档自动打标签
```
知识库上传时：
  POST /api/knowledge/{library}/upload
    → 保存文件 + OCR 提取文本
    → LLM 自动打标签：
      { industry: "制造业", account_codes: ["1601","1602"], doc_type: "审计底稿" }
    → 标签存入知识库文档元数据（knowledge_service 的 metadata JSONB）
    → 检索时按标签匹配排序
```

### 25l 截止性测试/月度明细统一底稿填充
```
截止性测试和月度明细复用 §25g 的 target_wp_id + target_cell_range 机制：
  → cutoff-test API 新增 target_wp_id 参数（可选）
  → monthly-detail API 新增 target_wp_id 参数（可选）
  → 有 target_wp_id 时自动用 openpyxl 填入底稿
  → 无 target_wp_id 时只返回数据（前端展示）
```

### 25m 批量下载预填性能优化
```
POST /api/projects/{id}/workpapers/download-pack
  → 底稿数量 > 10 时改为异步模式：
    1. 创建下载任务（download_tasks 表或内存队列）
    2. 返回 task_id，前端轮询进度
    3. 后端用 asyncio.gather 并发预填（最大并发 5）
    4. 全部完成后打包 ZIP，返回下载链接
  → 底稿数量 ≤ 10 时同步模式（直接 StreamingResponse）
```

### 25n 溯源复核意见统一写入
```
溯源页面添加复核意见时：
  → 写入 cell_annotations 表（与批注系统统一）
  → object_type = "disclosure_note"
  → object_id = note_id
  → cell_ref = section_number（如 "五、9"）
  → 自动通过 note_wp_mapping 创建 linked_annotation 到底稿
  → 复核意见同时可升级为 review_conversation（点击"发起对话"）
```

### 25o LLM 复核 findings 与人工复核统一视图
```
review_messages 表新增字段：
  finding_id: UUID FK → wp_qc_result.id（可选，关联 LLM 复核发现）

统一 findings 查询：
  GET /api/projects/{id}/findings-summary
    → 合并两个来源：
      1. wp_qc_result（LLM 自动复核发现）
      2. cell_annotations WHERE priority='high'（人工复核批注）
    → 按科目/底稿/严重度分组
    → 前端统一 findings 看板
```
