# Phase 13: 审计报告·报表·附注生成与导出 - 需求文档

> 不只是"导出 Word"，而是审计报告正文编辑、报表数据拉取、附注章节编辑、集团模板参照、上年报告 LLM 智能复用的完整业务闭环。

---

## 1. 背景与目标

### 1.1 现状

| 文档类型 | 当前能力 | 缺失 |
|---------|---------|------|
| 审计报告 | audit_report_service 模板加载+占位符填充+段落编辑 | 无 Word 导出；正文中单位名称/简称/报表口径等需人工逐处修改；无上年报告参照 |
| 财务报表 | report_engine 公式驱动生成4张报表 | 无 Word 导出；报表数据从 trial_balance 拉取后无持久化快照；缩进/合计行格式缺失 |
| 附注 | disclosure_engine 生成+note_word_exporter 基础导出 | 缺三线表/页眉页脚/三色处理/千分位；附注章节编辑无上年数据对比；无集团模板参照；无 LLM 辅助生成会计政策 |

### 1.2 核心目标

| 目标 | 量化指标 |
|------|---------|
| 格式精确度 | 与致同标准 Word 模板 100% 一致 |
| 导出速度 | 单文档 <10秒，全套 <30秒 |
| 编辑效率 | 集团子企业参照母公司模板，附注编辑时间 -50% |
| 智能复用 | 上传上年报告后，LLM 自动预填当期 70%+ 内容 |
| 数据准确 | 报表数据从 trial_balance 实时拉取，与试算表零差异 |

### 1.3 双方案策略

| | 方案A: python-docx 从零生成 | 方案B: Word 模板填充+ONLYOFFICE 编辑 |
|---|---|---|
| 格式精确度 | 难以 100% 还原 | 100%（模板自带格式） |
| 开发工作量 | 大 | 小（只写填充逻辑） |
| 用户可编辑 | 导出后用本地 Word 改 | 在线直接编辑 |
| ONLYOFFICE 依赖 | 不依赖 | 依赖（降级用方案A） |

**决策：方案B 优先，方案A 作为降级备选。**

---

## 2. 需求清单

### 2.1 P0 — 基础引擎+数据拉取

| 序号 | 需求 | 用户故事 | 验收标准 |
|------|------|---------|---------|
| P0-1 | 统一 Word 导出引擎 | 作为系统，所有导出文档必须遵循致同排版规范 | 页面设置+样式+三线表+页眉页脚+三色文本处理+千分位 |
| P0-2 | 审计报告正文编辑与名称处理 | 作为审计员，我编辑报告正文时，修改单位全称后简称/报表口径等应自动联动替换 | 占位符联动：修改{entity_name}后，正文中所有"XX公司"自动替换；{entity_short_name}联动；{report_scope}根据单体/合并自动切换"财务报表"/"合并及母公司财务报表" |
| P0-3 | 报表数据拉取与快照 | 作为审计员，报表数据必须从试算表实时拉取，且导出时保存数据快照 | 从 trial_balance→report_engine 公式计算→生成 financial_report 行数据→保存到 report_snapshot 表（project_id+year+report_type+generated_at+data JSONB）；后续导出从快照读取，不重复计算 |
| P0-4 | 报表 Word 导出 | 作为审计员，我需要导出符合致同标准的四张报表 Word | BS/IS/CFS/EQ 三线表+缩进层级+千分位+负数括号+附注编号列+分页 |
| P0-5 | 附注 Word 导出增强 | 作为审计员，附注导出必须处理三色文本和多级标题 | 继承 GTWordEngine+三色处理+多级标题编号+选择性导出+裁剪状态跳过 |

### 2.2 P1 — 模板体系+集团参照

| 序号 | 需求 | 用户故事 | 验收标准 |
|------|------|---------|---------|
| P1-1 | Word 模板准备 | 作为系统，需要预置致同标准模板 | 7套模板文件（审计报告+4张报表+附注国企版/上市版），格式已调好，占位符/书签标记 |
| P1-2 | 模板填充服务 | 作为审计员，点击"生成"后系统自动填充数据到模板 | 打开模板→替换占位符→填充表格数据→三色处理→保存到项目目录 |
| P1-3 | WOPI 在线编辑集成 | 作为审计员，生成后我想在线微调措辞再下载 | 填充后的 Word 注册到 WOPI，ONLYOFFICE 打开编辑，保存版本递增 |
| P1-4 | 集团模板参照 | 作为项目经理，集团母公司的报告模板修改好后，子企业应能一键参照 | 母公司项目的已确认报告/附注作为模板源→子企业"参照母公司"按钮→复制模板+替换单位名称/数据→子企业只需微调差异部分 |
| P1-5 | 集团模板差异标记 | 作为审计员，参照母公司模板后我想知道哪些地方需要修改 | 参照复制后自动标记：①单位名称占位符（黄色高亮）②金额数据占位符（蓝色高亮）③会计政策差异段落（如子企业有特殊政策需补充） |
| P1-6 | 前端导出交互 | 作为审计员，导出流程应该简单直观 | "生成Word"→"在线编辑"→"下载"三步；状态标签：草稿/已确认/已签发 |

### 2.3 P2 — 上年报告智能复用

| 序号 | 需求 | 用户故事 | 验收标准 |
|------|------|---------|---------|
| P2-1 | 上年审计报告上传解析 | 作为审计员，我上传上年审计报告 Word/PDF，系统自动解析结构 | python-docx 解析 Word 段落结构→识别7段式→提取各段文本→存储为 prior_year_report（project_id+year+paragraphs JSONB） |
| P2-2 | 上年附注上传解析 | 作为审计员，我上传上年附注 Word/PDF，系统自动解析章节和表格 | 解析附注目录→按章节拆分→表格数据提取→叙述文本提取→存储为 prior_year_notes（project_id+year+sections JSONB） |
| P2-3 | LLM 智能预填审计报告 | 作为审计员，系统根据上年报告+当期数据自动生成当期报告草稿 | LLM 输入：上年报告各段+当期 trial_balance 变动+当期 adjustments→输出：当期报告草稿（保留上年措辞风格，更新数据引用，标记需人工确认的变更点） |
| P2-4 | LLM 智能预填附注 | 作为审计员，系统根据上年附注+当期数据自动生成当期附注草稿 | 按章节处理：①表格章节→上年期末=当期期初，当期数据从 trial_balance/disclosure_note 拉取 ②叙述章节→LLM 对比上年文本+当期数据变动，生成当期文本（标记变更点） ③会计政策章节→默认沿用上年，LLM 检查是否有新准则变更需更新 |
| P2-5 | 附注章节逐章编辑 | 作为审计员，我需要逐章节编辑附注内容（表格+叙述混排） | 每个章节独立编辑区：表格区（el-table 可编辑+公式联动）+叙述区（TipTap 富文本）；单元格三种模式：auto（从试算表取数）/manual（手动输入）/locked（锁定不可改） |
| P2-6 | 附注变动分析自动生成 | 作为审计员，附注中"本期变动原因说明"应由 AI 自动草拟 | LLM 输入：科目期初/期末/变动额+调整分录明细+上年同期→输出：变动原因说明（200字内，引用具体数据） |
| P2-7 | 全套一键导出 | 作为审计员，我想一键导出审计报告+报表+附注完整套 | 审计报告+4张报表+附注打包为 ZIP，文件名按致同规范命名 |
| P2-8 | 导出历史与版本管理 | 作为项目经理，我想查看导出历史和版本变更 | 版本列表+下载+删除+状态标签（草稿/已确认/已签发）+版本间差异摘要 |

---

## 3. 文件存储路径规范

```
storage/projects/{project_id}/
├── reports/                          # 导出文档目录
│   ├── audit_report_{year}.docx      # 审计报告（可在线编辑）
│   ├── bs_{year}.docx                # 资产负债表
│   ├── is_{year}.docx                # 利润表
│   ├── cfs_{year}.docx               # 现金流量表
│   ├── eq_{year}.docx                # 权益变动表
│   ├── notes_{year}.docx             # 附注（完整版）
│   ├── full_package_{year}.zip       # 全套打包
│   └── .versions/                    # 版本快照（最近10版）
│       ├── audit_report_{year}_v1.docx
│       └── audit_report_{year}_v2.docx
├── prior_year/                       # 上年参考文档
│   ├── audit_report_{year-1}.docx    # 上年审计报告（用户上传）
│   ├── notes_{year-1}.docx           # 上年附注（用户上传）
│   └── parsed/                       # 解析后的结构化数据
│       ├── report_parsed.json        # 上年报告解析结果
│       └── notes_parsed.json         # 上年附注解析结果
└── templates/                        # 项目级模板（从集团参照或自定义）
    ├── audit_report_template.docx
    └── notes_template.docx
```

**集团参照路径**：子企业参照母公司时，从母公司项目的 `reports/` 目录复制已确认文档到子企业的 `templates/` 目录，替换占位符后作为子企业的模板。

---

## 4. 致同标准排版规范

### 3.1 页面设置
- 页边距：左 3cm、右 3.18cm、上 3.2cm、下 2.54cm
- 页眉 1.3cm、页脚 1.3cm

### 3.2 字体字号
- 中文（含页眉页脚）：仿宋_GB2312、小四（12pt）
- 数字和英文：Arial Narrow
- 表格金额过大时：最小 9pt

### 3.3 三色文本规则（附注专用）
- 黑色：正式披露内容（保留）
- 蓝色：编写者指引（导出时删除）
- 红色：披露格式提示（导出时转黑色）

### 3.4 文字排版
- 标题行：左缩进 -2 字符，首行不缩进，居左
- 段落间距：段前 0 行、段后 0.9 行，单倍行距
- 表格下一行：段前 0.5 行

### 3.5 三线表格式
- 上下边框 1 磅，标题行下边框 1/2 磅，无左右边框
- 标题列左对齐，数据列右对齐，垂直居中
- 标题行+合计行加粗
- 数字千分位格式（#,##0.00），负数用括号

### 3.6 页眉页脚
- 页眉左：事务所名称 | 页眉右：项目名称
- 页脚居中："第 X 页 共 Y 页"（python-docx OxmlElement 域代码）

---

## 5. 非功能需求

| 指标 | 目标值 |
|------|--------|
| 单文档导出 | <10秒 |
| 全套导出（报告+报表+附注） | <30秒 |
| 导出文件大小 | <5MB（单文档） |
| 并发导出 | 10人同时导出不阻塞 |

---

## 6. 数据模型新增

### 6.1 报表数据快照表

```sql
CREATE TABLE report_snapshot (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    year INTEGER,
    report_type VARCHAR(10),           -- BS/IS/CFS/EQ
    generated_at TIMESTAMP,
    data JSONB,                        -- 报表行数据快照
    source_trial_balance_hash VARCHAR(64), -- 试算表数据哈希（检测是否过期）
    created_by UUID REFERENCES users(id)
);
```

### 6.2 上年文档解析表

```sql
CREATE TABLE prior_year_document (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    year INTEGER,                      -- 上年年度
    doc_type VARCHAR(20),              -- 'audit_report' | 'disclosure_notes'
    original_file_path TEXT,           -- 上传的原始文件路径
    parsed_data JSONB,                 -- 解析后的结构化数据
    parsed_at TIMESTAMP,
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.3 集团模板参照记录表

```sql
CREATE TABLE template_reference (
    id UUID PRIMARY KEY,
    source_project_id UUID REFERENCES projects(id),  -- 母公司项目
    target_project_id UUID REFERENCES projects(id),  -- 子企业项目
    doc_type VARCHAR(20),              -- 'audit_report' | 'notes' | 'all'
    referenced_at TIMESTAMP,
    referenced_by UUID REFERENCES users(id),
    customizations JSONB               -- 子企业的差异化修改记录
);
```

---

## 7. 范围边界

| 功能 | 原因 | 后续版本 |
|------|------|---------|
| PDF 导出优化 | 当前 WeasyPrint 方案可用 | 按需优化 |
| Excel 报表导出 | 已有 openpyxl 导出 | 不重复建设 |
| 批量项目导出 | 单项目优先 | 远期规划 |
