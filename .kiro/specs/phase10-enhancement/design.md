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
