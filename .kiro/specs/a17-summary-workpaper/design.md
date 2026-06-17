# A17 重大事项概要底稿 — 设计文档

## 架构总览

A17 系列 14 个底稿按 4 种模式处理：

| 模式 | 底稿 | componentType | 格式 |
|------|------|---------------|------|
| 弹窗(OnlyOffice) | A17-3/3-1/4/6 | WpPopupDocxEditor | 信函型，自由格式 |
| 核对表(HTML) | A17-5-1~5-5 | checklist-table | 判断型，适用/执行 |
| 签署(HTML) | A17-7/7A | independence-signing | 判断型，逐条确认+签字 |
| **专用组件(HTML)** | A17-1, A17-2-1 | a17-summary / kam-workpaper | 报告型，章节导航+联动 |

### 底稿格式选型原则
| 底稿类型 | 编辑格式 | 交付格式 | 理由 |
|----------|----------|----------|------|
| 判断型（适用/执行/签署） | HTML 组件 | 数据存 DB，按需导出 | 交互频繁，需跳转联动 |
| 报告型（概要/KAM/沟通函） | HTML 结构化编辑 | 导出 Word | 章节多需导航，联动其他模块 |
| 信函型（律师函/问询函） | OnlyOffice/弹窗 | docx 直编 | 自由格式，每次内容不同 |

## 组件设计

### GtA17Summary.vue（A17-1 重大事项概要汇总）

**设计原则**：编辑时结构化 HTML，交付时生成 Word（与 DisclosureEditor 同一思路）

**布局**：左侧目录 + 右侧章节编辑区

```
┌─────────────┬────────────────────────────────────────┐
│ 目录导航     │ 章节编辑区                              │
│             │ ┌──────────────────────────────────┐   │
│ ▸ 一、约定范围│ │ 📋 提示栏（折叠）                   │   │
│ ▸ 二、独立性  │ │ "本章应描述审计业务约定的范围..."    │   │
│ ▸ 三、计划更新│ │ （灰色底，不导出）                   │   │
│ ▸ 四、前任   │ ├──────────────────────────────────┤   │
│ ▸ 五、重大判断│ │ 一、审计业务约定范围及执行情况      │   │
│ ▸ 六、错报风险│ │                                  │   │
│ ▸ 七、舞弊   │ │ [从项目信息拉取] [AI 生成] [引用]  │   │
│ ▸ 八、KAM   │ │                                  │   │
│ ▸ 九、持续经营│ │ 正文编辑区（textarea）             │   │
│ ▸ 十、沟通   │ │ （用户填写，导出到 Word）           │   │
│ ▸ 十一、其他 │ │                                  │   │
│             │ │ 状态: ● 已填写  来源：项目信息表    │   │
└─────────────┴────────────────────────────────────────┘
              │ 工具栏: [导出 Word] [检查完整性]       │
```

**数据模型**：复用 `checklist_responses` 表
- item_id: `A17-1-ch01`~`A17-1-ch11`（11 个章节）
- conclusion: `done`/`pending`/`na`（章节完成状态）
- remark: 章节正文内容（纯文本+换行）
- wp_ref: 数据来源引用（如 `B40,A15`）

### GtKamWorkpaper.vue（A17-2-1 关键审计事项）

**布局**：卡片式 KAM 列表 + 详情编辑

```
┌────────────────────────────────────────────────────┐
│ 关键审计事项 (KAM)                    [+新增] [导出]│
├────────────────────────────────────────────────────┤
│ KAM 1: 商誉减值  ● 已完成                          │
│ KAM 2: 收入确认  ◐ 编辑中                          │
│ KAM 3: ...                                         │
├────────────────────────────────────────────────────┤
│ 编辑: KAM 2 — 收入确认                             │
│ ┌──────────────────────────────────────────────┐   │
│ │ 基本情况：                                    │   │
│ │ [textarea]                                   │   │
│ │                                              │   │
│ │ 认定原因：                                    │   │
│ │ [textarea]                                   │   │
│ │                                              │   │
│ │ 审计应对：                                    │   │
│ │ [textarea]                                   │   │
│ │                                              │   │
│ │ 引用底稿: D4(收入), B50(风险)                 │   │
│ │ [AI 生成初稿] [同步到审计报告]                 │   │
│ └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

**数据模型**：`checklist_responses` 表
- item_id: `KAM-001`~`KAM-NNN`（动态，每个 KAM 一条）
- conclusion: KAM 标题/风险领域名
- remark: JSON 字符串 `{"situation":"...","reason":"...","response":"...","refs":"D4,B50"}`
- wp_ref: 引用底稿编码

### LLM 生成服务

**后端**：`backend/app/services/a17_llm_service.py`

```python
class A17LLMService:
    async def generate_chapter(self, project_id, year, chapter_id, context_data):
        """为 A17-1 某章节生成初稿"""
        # 1. 从知识库检索同行业范例
        # 2. 组装 prompt（项目信息+关联底稿摘要+范例）
        # 3. 调 llm_client.chat_completion()
        # 4. 返回生成文本（用户可编辑后采纳）

    async def generate_kam_draft(self, project_id, year, risk_area, audit_procedures):
        """为 KAM 生成描述初稿"""
        # 1. 检索知识库中同行业/同风险的 KAM 案例
        # 2. 传入风险描述+审计程序+案例
        # 3. 按 3 要素格式输出
```

**Prompt 模板**：`backend/data/wp_llm_prompts/a17/`
- `chapter_template.txt`：各章节通用 prompt
- `kam_draft_template.txt`：KAM 描述生成 prompt
- `chapter_context_{chapter_id}.txt`：各章节专用上下文指引

### Word 导出

**A17-1 导出**：
1. 复制模板 `A17-1 重大事项概要汇总.docx`
2. 按目录结构定位各章节段落
3. 用 checklist_responses 中保存的正文填充对应章节
4. 未填写章节保留模板原文或标记"待完善"
5. 蓝色提示删除、红色替换

**A17-2-1 导出**：
1. 复制模板
2. KAM 列表动态生成表格行
3. 每个 KAM 的 3 要素填入对应列
4. 蓝色提示删除

## 技术方案

### 后端新增
- `a17_llm_service.py`：LLM 章节/KAM 生成
- `a17_summary_service.py`：章节数据聚合（从各关联模块取数）
- `a17_word_exporter.py`：Word 导出
- prompt 文件 `backend/data/wp_llm_prompts/a17/`

### 前端新增
- `GtA17Summary.vue`：A17-1 章节导航编辑器
- `GtKamWorkpaper.vue`：A17-2-1 KAM 结构化编辑器
- htmlRendererRegistry 注册 `a17-summary` + `kam-workpaper`

### _WP_CODE_OVERRIDE 新增
```python
"A17-1": "a17-summary",
"A17-2-1": "kam-workpaper",
"A17-5-1": "checklist-table",
"A17-5-2": "checklist-table",
"A17-5-3": "checklist-table",
"A17-5-4": "checklist-table",
"A17-5-5": "checklist-table",
```
