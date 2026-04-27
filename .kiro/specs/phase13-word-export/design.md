# Phase 13: 审计报告·报表·附注生成与导出 - 设计文档

---

## 1. 架构概览

### 1.1 双方案架构

```
方案B（优先）：模板填充 + ONLYOFFICE 在线编辑
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ 致同标准Word模板  │ →   │ WordTemplateFiller│ →   │ ONLYOFFICE编辑   │
│ （格式已调好）    │     │ （填充数据到占位符）│     │ （用户微调确认）  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                          ↓
方案A（降级）：python-docx 从零生成                    直接下载 .docx
┌──────────────────┐     ┌──────────────────┐
│ GTWordEngine      │ →   │ 各文档Exporter   │
│ （致同排版引擎）  │     │ （审计报告/报表/附注）│
└──────────────────┘     └──────────────────┘
```

### 1.2 服务层结构

```
┌─────────────────────────────────────────────────────────────┐
│                        API层                                 │
│  export.py（增强）                                           │
│  POST /projects/{id}/exports/*/generate                      │
│  POST /projects/{id}/exports/{task_id}/confirm               │
│  POST /projects/{id}/exports/full-package                    │
│  GET  /projects/{id}/jobs/{job_id}                           │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     服务层                                    │
│  ┌──────────────────┐  ┌──────────────────────────────┐     │
│  │ GTWordEngine      │  │ WordTemplateFiller            │     │
│  │ （方案A：从零生成）│  │ （方案B：模板填充）           │     │
│  └────────┬─────────┘  └──────────┬───────────────────┘     │
│           │                       │                          │
│  ┌────────▼─────────┐  ┌─────────▼──────────────────┐      │
│  │AuditReportWord   │  │ fill_audit_report()         │      │
│  │Exporter          │  │ fill_financial_reports()     │      │
│  │FinancialReport   │  │ fill_disclosure_notes()      │      │
│  │WordExporter      │  └────────────────────────────┘      │
│  │NoteWordExporter  │                                       │
│  │（增强版）        │                                       │
│  └──────────────────┘   ExportTaskService / ExportJobService │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 设计收敛原则

| 原则 | 说明 |
|------|------|
| 模板优先 | 本期主交付路径为方案B（模板填充 + ONLYOFFICE 编辑），方案A仅保留降级导出基线 |
| 单一真相源 | `reports/` 目录下已确认版本是最终交付物；模板、自定义模板快照、报表快照仅作为输入与镜像 |
| 长任务 job 化 | 全套导出、批量渲染、上年解析、LLM 预填统一走 `job_id`，支持页面刷新恢复与失败重试 |
| 单向数据流 | `trial_balance`、`audit_report`、`disclosure_note` 等源数据只流向快照和文档，不反向改写 |
| 模板快照优先 | 附注 `custom` 模板优先读取项目级 `custom_template_snapshot`，切换模板不得覆盖已确认用户修改 |

---

## 2. 方案A：GTWordEngine 统一导出引擎

### 2.1 核心类设计

```python
class GTWordEngine:
    """致同标准 Word 导出引擎 — 统一排版规范"""

    def __init__(self):
        self.doc = Document()
        self._setup_page()
        self._setup_styles()

    def _setup_page(self):
        """页面设置：左3/右3.18/上3.2/下2.54 cm，页眉页脚1.3cm"""

    def _setup_styles(self):
        """注册自定义样式：GT标题1-3/GT正文/GT表格标题/GT表格数据
           中文：仿宋_GB2312 小四(12pt)
           英文/数字：Arial Narrow"""

    def setup_header_footer(self, firm_name, project_name):
        """页眉：事务所名称(左) + 项目名称(右)
           页脚：第 X 页 共 Y 页（居中）
           实现：OxmlElement 插入 PAGE/NUMPAGES 域代码"""

    def add_heading(self, text, level=1):
        """多级标题：一、（一）、1. 自动编号
           左缩进 -2 字符，首行不缩进"""

    def add_paragraph(self, text, style='GT正文', after_table=False):
        """正文段落：段前0行 段后0.9行 单倍行距
           after_table=True时：段前0.5行"""

    def add_table(self, headers, rows, total_row=None):
        """三线表：
           - 上下边框 1 磅，标题行下边框 1/2 磅，无左右边框
           - 标题列左对齐，数据列右对齐，垂直居中
           - 标题行+合计行加粗
           - 数字 Arial Narrow + 千分位 + 负数括号 (1,234.56)
           - 单行数据不加合计行"""

    def process_color_text(self, paragraph):
        """三色文本处理（附注专用）：
           - 蓝色 run → 删除
           - 红色 run → 转黑色
           - 黑色 run → 保留"""

    def format_number(self, value, decimals=2):
        """数字格式化：千分位 + 负数括号
           12345.67 → '12,345.67'
           -1234.56 → '(1,234.56)'
           None/0 → '-'"""

    def add_page_break(self):
        """插入分页符"""

    def save(self, output) -> BytesIO:
        """保存为 BytesIO 或文件路径"""
```

### 2.2 审计报告导出器

```python
class AuditReportWordExporter(GTWordEngine):
    """审计报告 Word 导出 — 致同标准 7 段式"""

    async def export(self, db, project_id, year) -> BytesIO:
        """
        1. 从 audit_report 表读取 7 个段落
        2. 占位符替换：{entity_name}/{report_date}/{audit_period}
        3. 三色文本处理
        4. 段落格式：
           - 审计意见段：黑体标题 + 正文仿宋
           - KAM：每个独立子标题 + 表格（事项描述/审计应对）
           - 管理层/审计师责任：含 5 项编号列表
           - 签章段：右对齐，事务所名+CPA+日期，间距加大
        """
```

### 2.3 财务报表导出器

```python
class FinancialReportWordExporter(GTWordEngine):
    """四张报表 Word 导出"""

    async def export(self, db, project_id, year, report_types=None) -> BytesIO:
        """
        默认导出全部 4 张报表到一个 Word 文件，每张分页。

        BS 资产负债表：
        - 标题居中："{entity_name} 资产负债表"
        - 副标题："{year}年12月31日  单位：元"
        - 三线表：项目 | 附注 | 期末余额 | 年初余额
        - indent_level 控制左缩进（0=顶级 1=明细 2=子明细）
        - 合计行：加粗 + 上边框
        - 资产/负债/权益三段之间空一行

        IS 利润表：
        - 三线表：项目 | 附注 | 本期金额 | 上期金额

        CFS 现金流量表：
        - 三段：经营/投资/筹资活动，每段有小计行

        EQ 权益变动表：
        - 宽表：列=实收资本/资本公积/盈余公积/未分配利润/合计
        - 行=期初余额/本年增减变动/期末余额

        通用规则：
        - 数字千分位，负数括号
        - 附注列显示"五、1"格式
        - 每张报表后分页符
        """
```

### 2.4 附注导出器增强

```python
class NoteWordExporter(GTWordEngine):
    """附注 Word 导出 — 继承 GTWordEngine 统一排版"""

    async def export(self, db, project_id, year, sections=None) -> BytesIO:
        """
        增强点：
        1. 三色文本处理（核心）：遍历 text_content 颜色标记
        2. 多级标题编号：一、（一）、1.
        3. 三线表格式（复用 GTWordEngine.add_table）
        4. 会计政策段落：首行缩进 2 字符
        5. 选择性导出：sections 参数 + 跳过"不适用"章节
        6. 附注目录：章节编号+标题+页码（OxmlElement 域代码）
        7. 页眉：致同会计师事务所 | {entity_name} 财务报表附注
        """
```

---

## 3. 方案B：Word 模板填充 + ONLYOFFICE 编辑

### 3.1 核心思路

```
致同标准 Word 模板（格式已调好）
        ↓
python-docx 填充数据到占位符/书签
        ↓
保存到 storage/projects/{id}/reports/
        ↓
用户通过 ONLYOFFICE 在线编辑确认
        ↓
直接下载 = 最终交付物（格式零损失）
```

### 3.2 模板文件清单

| 模板文件 | 存储位置 | 占位符/书签 |
|---------|---------|------------|
| 审计报告模板.docx | backend/data/word_templates/ | {entity_name}/{report_date}/{audit_period} 等 |
| 资产负债表模板.docx | 同上 | 数据区域书签标记 |
| 利润表模板.docx | 同上 | 同上 |
| 现金流量表模板.docx | 同上 | 同上 |
| 权益变动表模板.docx | 同上 | 同上 |
| 附注模板_国企版.docx | 同上 | 章节结构+表格格式+占位符 |
| 附注模板_上市版.docx | 同上 | 同上 |
| 项目级自定义附注模板.docx | storage/projects/{id}/templates/ | 来源于 `custom_template_snapshot` 或集团参照锁定版本 |

### 3.3 填充服务设计

```python
class WordTemplateFiller:
    """Word 模板填充服务 — 方案B核心"""

    async def fill_audit_report(self, db, project_id, year) -> Path:
        """打开审计报告模板 → 替换占位符 → 保存到项目目录
           从 audit_report 表读取 7 个段落
           python-docx 遍历 paragraphs，替换 {xxx} 占位符
           不动格式，只改文本内容"""

    async def fill_financial_reports(self, db, project_id, year) -> list[Path]:
        """打开报表模板 → 填充数据到表格单元格 → 保存
           从 financial_report 表读取行数据
           python-docx 定位表格书签 → 逐行填入数字
           数字格式化：千分位 + 负数括号"""

    async def fill_disclosure_notes(self, db, project_id, year) -> Path:
        """打开附注模板 → 填充表格数据+叙述文本 → 三色处理 → 保存
           模板解析顺序：custom_template_snapshot > 项目 templates/ > 系统模板 `soe/listed`
           表格区域：定位书签 → 填入数字
           叙述区域：替换占位符 → 填入会计政策文本
           三色处理：删除蓝色段落 + 红色转黑色
           裁剪处理：跳过 note_section_instances 中"不适用"章节"""

    async def fill_full_package(self, db, project_id, year) -> Path:
        """全套导出：审计报告+4张报表+附注 → ZIP打包"""
```

### 3.4 WOPI 集成

```
填充后的 Word 文件复用底稿的 WOPI 机制：
1. 文件保存到 storage/projects/{id}/reports/{filename}.docx
2. 创建 ExportTask 记录（file_path, status=generated）并登记版本v1
3. 前端用 ONLYOFFICE iframe 打开编辑
4. 用户微调措辞、补充内容、调整格式，状态进入 editing
5. 保存 = WOPI put_file → 版本递增到 export_task_versions
6. 用户点击确认后状态变为 confirmed，才允许全套打包/集团参照
7. 下载 = 直接下载当前 confirmed 或最新 editing 版本 .docx
8. 状态流转：draft → generating → generated → editing → confirmed → signed
```

### 3.5 ExportTask 状态与后台任务模型

```python
class ExportTaskService:
    """导出状态机与版本管理"""

    async def create_task(self, db, project_id, doc_type, template_type, user_id) -> dict:
        """创建 export_task + export_task_versions 基线记录"""

    async def confirm_task(self, db, export_task_id, user_id) -> dict:
        """
        人工确认后的唯一生效入口：
        1. 校验当前版本存在且文件可下载
        2. 更新 status='confirmed'
        3. 记录 confirmed_by / confirmed_at
        4. 仅 confirmed 版本允许 full_package、template_reference、signed
        """

class ExportJobService:
    """统一管理全套导出、重算、解析、LLM预填等长任务"""

    async def create_job(self, db, project_id, job_type, payload, user_id) -> dict:
        """创建 export_jobs + export_job_items，返回 job_id"""

    async def retry_job(self, db, job_id) -> dict:
        """仅重试失败项，保留已完成文件和原始审计轨迹"""
```

| 对象 | 状态 | 允许转移 | 阻断条件 |
|------|------|---------|---------|
| `export_task.status` | `draft` → `generating` → `generated` → `editing` → `confirmed` → `signed` | `confirmed` 可 reopen 回 `editing` 并生成新版本 | `draft/editing/generated` 不可用于 ZIP 打包、集团参照、签发 |
| `snapshot_status` | `missing` / `fresh` / `stale` / `refreshing` | `stale` 经重算进入 `refreshing`，成功后回到 `fresh` | `stale` 时需显式选择沿用旧快照或重算 |
| `job_status` | `queued` → `running` → `succeeded` / `partial_failed` / `failed` / `cancelled` | `partial_failed` / `failed` 可经 retry 回到 `running` | 前端需展示失败项并支持恢复 |

---

## 4. API 设计

```yaml
POST /api/projects/{id}/exports/audit-report/generate
  - 生成审计报告草稿并创建 ExportTask
  - 返回: { export_task_id, status, editor_url }

POST /api/projects/{id}/exports/financial-reports/generate
  - 生成报表文档并绑定最新快照
  - body: { report_types: ["BS", "IS", "CFS", "EQ"], snapshot_strategy: "reuse"|"refresh" }
  - 返回: [{ export_task_id, report_type, status, editor_url }]

POST /api/projects/{id}/exports/disclosure-notes/generate
  - 生成附注草稿
  - body: { template_type: "soe"|"listed"|"custom", sections?: [] }
  - 返回: { export_task_id, status, editor_url }

POST /api/projects/{id}/exports/{export_task_id}/confirm
  - 人工确认当前导出版本
  - 返回: { status, confirmed_at }

GET /api/projects/{id}/exports/history
  - 返回: [{ id, doc_type, file_path, status, created_at, confirmed_at }]

POST /api/projects/{id}/exports/full-package
  - 发起全套导出与 ZIP 打包
  - body: { export_task_ids[] }
  - 返回: { job_id, status }

GET /api/projects/{id}/jobs/{job_id}
  - 获取后台任务状态
  - 返回: { status, progress_total, progress_done, failed_count, items[] }

POST /api/projects/{id}/jobs/{job_id}/retry
  - 重试失败项
  - 返回: { job_id, retried_count }

GET /api/projects/{id}/template-reference/available
  - 列出可参照项目

POST /api/projects/{id}/template-reference/copy
  - body: { source_project_id, doc_types: ["audit_report", "notes"] }
  - 返回: { copied_files[], diff_markers[] }

POST /api/projects/{id}/prior-year/upload
  - 上传上年报告/附注并触发解析
  - body: FormData(file, doc_type, year)
  - 返回: { document_id, job_id }

POST /api/projects/{id}/prior-year/prefill-report
  - 发起审计报告 LLM 预填
  - 返回: { job_id, status }

POST /api/projects/{id}/prior-year/prefill-notes
  - 发起附注 LLM 预填
  - 返回: { job_id, status }
```

---

## 5. 关键技术难点

### 5.1 python-docx 页码实现

```python
# python-docx 不原生支持页码，需要 XML 操作
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def add_page_number(paragraph):
    """插入 '第 X 页 共 Y 页' 页码"""
    run = paragraph.add_run("第 ")
    # PAGE 域代码
    fld_char_begin = OxmlElement('w:fldChar')
    fld_char_begin.set(qn('w:fldCharType'), 'begin')
    run._r.append(fld_char_begin)
    instr_text = OxmlElement('w:instrText')
    instr_text.text = " PAGE "
    run._r.append(instr_text)
    fld_char_end = OxmlElement('w:fldChar')
    fld_char_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fld_char_end)
    run2 = paragraph.add_run(" 页 共 ")
    # NUMPAGES 域代码（同上模式）
    ...
```

### 5.2 三线表边框实现

```python
def set_table_borders(table):
    """三线表：上下1磅，标题行下1/2磅，无左右"""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    borders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'bottom']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '8')  # 1磅 = 8 half-points
        borders.append(border)
    # 标题行下边框 1/2 磅
    # 通过行级别 tcBorders 设置
```

### 5.3 仿宋_GB2312 字体兼容

```
问题：仿宋_GB2312 在非 Windows 系统上不存在
解决：
1. python-docx 设置 rFonts eastAsia="仿宋_GB2312"
2. 同时设置 fallback：rFonts ascii="FangSong" hAnsi="FangSong"
3. Docker 环境需安装中文字体包（fonts-wqy-zenhei）
4. 或在 Dockerfile 中 COPY 仿宋_GB2312.ttf 到 /usr/share/fonts/
```


---

## 4. 审计报告正文名称联动处理

### 4.1 占位符体系

审计报告正文中涉及大量需要联动替换的名称和表述：

```
占位符清单（从 project.wizard_state.basic_info 读取）：

| 占位符 | 来源 | 联动规则 |
|--------|------|---------|
| {entity_name} | client_name | 修改后全文替换所有出现位置 |
| {entity_short_name} | 用户手动填入 | 默认=全称加引号，如"XX公司" |
| {report_scope} | report_scope字段 | consolidated→"合并及母公司财务报表"，standalone→"财务报表" |
| {audit_period} | audit_period_start/end | "2025年1月1日至2025年12月31日" |
| {audit_year} | audit_year | "2025" |
| {signing_partner} | 从project_assignments取签字合伙人 | |
| {report_date} | 用户填入 | 默认=审计期间结束日后30天 |
| {firm_name} | 系统配置 | "致同会计师事务所（特殊普通合伙）" |
| {cpa_name_1} | 用户填入 | 签字注册会计师1 |
| {cpa_name_2} | 用户填入 | 签字注册会计师2 |

联动替换逻辑：
- 用户在"基本信息"中修改 entity_name → 触发全文扫描替换
- 正文中"XX有限公司"等硬编码文本也需被替换（模糊匹配旧名称）
- 替换后高亮标记已替换位置（黄色背景），供用户确认
```

### 4.2 报表口径自动切换

```python
# 根据 report_scope 自动替换正文表述
SCOPE_REPLACEMENTS = {
    "consolidated": {
        "财务报表": "合并及母公司财务报表",
        "资产负债表": "合并及母公司资产负债表",
        "利润表": "合并及母公司利润表",
        "现金流量表": "合并及母公司现金流量表",
        "所有者权益变动表": "合并及母公司所有者权益变动表",
        "财务报表附注": "合并及母公司财务报表附注",
    },
    "standalone": {
        # 单体报表不需要替换，保持原文
    }
}
```

---

## 5. 报表数据拉取与快照机制

### 5.1 数据拉取链路

```
trial_balance (试算表)
    ↓ report_engine.generate_all_reports()
    ↓ 公式计算：TB()/SUM_TB()/ROW()
financial_report (报表行数据)
    ↓ 保存快照
report_snapshot (数据快照表)
    ↓ 导出时从快照读取
Word 文件
```

### 5.2 快照策略

```python
class ReportSnapshotService:
    async def create_snapshot(self, db, project_id, year) -> dict:
        """
        1. 调用 report_engine.generate_all_reports() 重新计算
        2. 计算 trial_balance 数据哈希（用于检测过期）
        3. 将4张报表行数据序列化为 JSONB 存入 report_snapshot
        4. 返回 snapshot_id
        
        过期检测：
        - 导出时比对当前 trial_balance 哈希 vs 快照哈希
        - 不一致→提示"报表数据已变更，是否重新生成？"
        - 用户可选择：用旧快照导出 / 重新生成快照
        """

    async def get_latest_snapshot(self, db, project_id, year, report_type):
        """获取最新快照，如不存在则自动创建"""
```

---

## 6. 集团模板参照机制

### 6.1 参照流程

```
母公司项目（已完成报告编辑）
    ↓ 子企业点击"参照母公司"
复制母公司 reports/ 下的已确认文档到子企业 templates/
    ↓ 自动替换
替换占位符：{entity_name}→子企业名称，{entity_short_name}→子企业简称
    ↓ 差异标记
黄色高亮：单位名称替换位置
蓝色高亮：金额数据占位符（需从子企业试算表重新拉取）
绿色高亮：会计政策可能需要调整的段落
    ↓ 子企业编辑
用户逐处确认/修改高亮位置
    ↓ 填充子企业数据
报表数据从子企业 trial_balance 拉取填充
附注表格数据从子企业 disclosure_note 拉取填充
```

### 6.2 参照服务设计

```python
class TemplateReferenceService:
    async def reference_from_parent(self, db, source_project_id, 
                                     target_project_id, doc_types) -> dict:
        """
        从母公司项目参照模板到子企业项目
        
        参数：
        - source_project_id: 母公司项目ID
        - target_project_id: 子企业项目ID  
        - doc_types: ['audit_report', 'notes', 'all']
        
        步骤：
        1. 验证母公司项目存在且有已确认文档
        2. 复制文档到子企业 templates/ 目录
        3. 读取子企业 basic_info，替换占位符
        4. 标记差异位置（返回 diff_markers 列表）
        5. 记录参照关系到 template_reference 表
        
        返回：
        {
            "copied_files": ["audit_report.docx", "notes.docx"],
            "diff_markers": [
                {"file": "notes.docx", "location": "第五章第3节", 
                 "type": "policy_diff", "reason": "子企业可能有不同折旧政策"}
            ],
            "reference_id": "uuid"
        }
        """

    async def list_referenceable_projects(self, db, project_id) -> list:
        """
        列出可参照的项目（同集团的母公司/兄弟企业）
        通过 parent_project_id 关系链查找
        """
```

---

## 7. 上年报告 LLM 智能复用

### 7.1 上年文档解析

```python
class PriorYearDocumentService:
    async def upload_and_parse(self, db, project_id, year, 
                                file, doc_type) -> dict:
        """
        上传上年报告/附注并解析
        
        Word 文件解析（python-docx）：
        - 审计报告：识别7段式结构，提取各段文本
        - 附注：识别章节目录→按章节拆分→表格数据提取→叙述文本提取
        
        PDF 文件解析（MinerU GPU 加速 + OCR 兜底）：
        - 文字层直接提取
        - 扫描版 OCR
        - 表格识别（MinerU 表格检测）
        
        解析结果存储：
        - 原始文件 → storage/projects/{id}/prior_year/
        - 解析结果 → prior_year_document 表 parsed_data JSONB
        
        parsed_data 结构（审计报告）：
        {
            "paragraphs": [
                {"type": "opinion", "text": "..."},
                {"type": "basis", "text": "..."},
                {"type": "kam", "items": [{"title": "...", "description": "...", "response": "..."}]},
                {"type": "other_info", "text": "..."},
                {"type": "management_responsibility", "text": "..."},
                {"type": "auditor_responsibility", "text": "..."},
                {"type": "signature", "text": "..."}
            ]
        }
        
        parsed_data 结构（附注）：
        {
            "sections": [
                {
                    "code": "五、1",
                    "title": "货币资金",
                    "tables": [{"headers": [...], "rows": [...]}],
                    "narrative": "本公司货币资金主要包括...",
                    "prior_closing": 1200000,
                    "prior_opening": 1100000
                }
            ]
        }
        """
```

### 7.2 LLM 智能预填审计报告

```python
class ReportLLMService:
    async def prefill_audit_report(self, db, project_id, year) -> dict:
        """
        根据上年报告 + 当期数据生成当期报告草稿
        
        处理逻辑（按段落类型分别处理）：
        
        1. 审计意见段：
           - 默认沿用上年意见类型（标准无保留/保留/否定/无法表示）
           - 替换单位名称、审计期间、报表口径
           - 如果当期有重大调整（AJE金额>重要性水平）→ LLM 提示可能需要修改意见类型
        
        2. 形成基础段：
           - 沿用上年模板
           - 替换占位符
        
        3. 关键审计事项（KAM）：
           - 上年 KAM 列表作为参考
           - LLM 分析当期数据：哪些科目变动大/有重大调整/有特殊风险
           - 建议保留/删除/新增 KAM 项
           - 每个 KAM 的"审计应对"段落根据当期实际执行程序更新
        
        4. 其他信息段/管理层责任段/审计师责任段：
           - 基本沿用上年（标准化段落）
           - 替换占位符
        
        5. 签章段：
           - 更新签字合伙人、日期
        
        Prompt 模板：
        [system] 你是致同会计师事务所的审计报告编写专家。
        根据上年审计报告和当期审计数据，生成当期审计报告草稿。
        保留上年的措辞风格和结构，仅更新数据引用和必要变更。
        对于需要人工判断的变更点，用 [需确认: 原因] 标记。
        
        [user] 
        上年报告：{prior_year_paragraphs}
        当期变动摘要：{current_year_changes}
        当期重大调整：{significant_adjustments}
        当期重要性水平：{materiality}
        
        返回：
        {
            "paragraphs": [...],  # 当期报告各段草稿
            "changes_from_prior": [  # 与上年的差异清单
                {"paragraph": "opinion", "change": "意见类型未变", "needs_review": false},
                {"paragraph": "kam", "change": "建议新增KAM：商誉减值", "needs_review": true}
            ],
            "confidence": "high"
        }
        """
```

### 7.3 LLM 智能预填附注

```python
class NoteLLMService:
    async def prefill_disclosure_notes(self, db, project_id, year) -> dict:
        """
        根据上年附注 + 当期数据生成当期附注草稿
        
        按章节类型分别处理：
        
        类型1：纯表格章节（如货币资金、应收账款明细）
        - 上年期末 → 当期期初（直接复制）
        - 当期期末 → 从 trial_balance / disclosure_note 拉取
        - 变动额 = 期末 - 期初（自动计算）
        - 不需要 LLM，纯数据填充
        
        类型2：表格+变动说明（如固定资产变动表）
        - 表格部分同类型1
        - 变动说明 → LLM 生成：
          输入：科目期初/期末/变动额 + 调整分录明细 + 上年变动说明
          输出：当期变动说明（200字内，引用具体数据）
          Prompt：参照上年说明的措辞风格，更新数据引用
        
        类型3：纯叙述章节（如会计政策、税项说明）
        - 默认沿用上年文本
        - LLM 检查：是否有新准则变更需要更新
          输入：上年会计政策文本 + 当年新准则清单（从知识库加载）
          输出：需要更新的段落 + 更新建议
        - 无变更 → 直接复制上年文本
        - 有变更 → 标记 [需确认: 新准则XXX可能影响此政策]
        
        类型4：关联方/或有事项/承诺等特殊章节
        - 上年文本作为参考
        - LLM 提示：这些章节通常每年变化较大，建议人工重写
        - 提供上年文本供参考，不自动生成
        
        返回：
        {
            "sections": [
                {
                    "code": "五、1",
                    "title": "货币资金",
                    "fill_type": "table_only",
                    "tables": [...],  # 已填充数据的表格
                    "narrative": null,
                    "needs_review": false
                },
                {
                    "code": "五、10",
                    "title": "固定资产",
                    "fill_type": "table_and_narrative",
                    "tables": [...],
                    "narrative": "本期固定资产增加主要系...",
                    "narrative_source": "llm",
                    "needs_review": true,
                    "review_reason": "变动说明由AI生成，请核实数据引用"
                },
                {
                    "code": "三、1",
                    "title": "会计政策",
                    "fill_type": "narrative_only",
                    "narrative": "（沿用上年）...",
                    "changes_detected": ["新收入准则解释第X号可能影响收入确认政策"],
                    "needs_review": true
                }
            ],
            "stats": {
                "total_sections": 40,
                "auto_filled": 25,
                "llm_generated": 10,
                "manual_required": 5
            }
        }
        """
```

---

## 8. 附注章节编辑处理

### 8.1 章节编辑模型

```
每个附注章节的编辑区由以下 block 组成（支持交替排列）：

┌─────────────────────────────────────────┐
│ Block 1: 叙述文本（TipTap 富文本编辑器）  │
│ "本公司货币资金主要包括库存现金、银行..."  │
├─────────────────────────────────────────┤
│ Block 2: 表格（el-table 可编辑）          │
│ ┌────────┬────────┬────────┬────────┐  │
│ │ 项目    │ 期末余额 │ 期初余额 │ 变动   │  │
│ ├────────┼────────┼────────┼────────┤  │
│ │ 库存现金 │ auto   │ auto   │ =期末-期初│ │
│ │ 银行存款 │ auto   │ manual │ =期末-期初│ │
│ │ 合计    │ =SUM   │ =SUM   │ =SUM   │  │
│ └────────┴────────┴────────┴────────┘  │
├─────────────────────────────────────────┤
│ Block 3: 叙述文本                        │
│ "本期银行存款增加主要系..."               │
├─────────────────────────────────────────┤
│ Block 4: 表格（账龄分析表）               │
│ ...                                      │
└─────────────────────────────────────────┘

单元格三种模式：
- auto（蓝色背景）：从 trial_balance 自动取数，刷新时更新
- manual（白色背景）：用户手动输入，刷新时不覆盖
- locked（灰色背景）：公式计算结果，不可编辑（如合计行、变动列）
```

### 8.2 附注数据来源优先级

```
每个附注表格单元格的数据来源按以下优先级：

1. 用户手动输入（manual模式）→ 最高优先，永不被覆盖
2. 底稿 parsed_data（如果底稿已完成）→ 底稿是第一手审计证据
3. trial_balance 审定数 → 试算表是汇总数据
4. 上年附注期末值 → 作为当期期初值
5. LLM 生成 → 叙述性文本的草稿

刷新逻辑：
- 点击"刷新数据" → 只更新 auto 模式单元格
- manual 模式单元格保持不变
- locked 模式单元格重新计算公式
- 刷新后显示变更摘要弹窗（旧值→新值）
```

### 8.3 附注叙述文本编辑

```
叙述文本编辑器（TipTap）功能：
1. 基础格式：加粗/斜体/下划线/列表/缩进
2. 数据标签：插入 {{amount:1001:closing}} 标签 → 渲染为实际金额
   - 点击标签 → 跳转到试算表对应行
   - 数据变更时标签自动更新
3. AI 辅助：
   - "AI 生成变动说明" 按钮 → 调用 NoteLLMService
   - "AI 润色" 按钮 → 优化措辞但保留数据引用
   - AI 生成内容用虚线边框标记，需用户确认
4. 上年参照：
   - 侧边栏显示上年同章节文本（只读）
   - 可一键复制上年文本到编辑器
   - 复制后自动标记需要更新的数据引用（黄色高亮）
```

---

## 9. API 设计补充

### 9.1 集团参照 API

```yaml
GET /api/projects/{id}/template-reference/available
  - 列出可参照的项目（同集团母公司/兄弟企业）
  - 返回: [{ project_id, client_name, relationship, has_confirmed_report }]

POST /api/projects/{id}/template-reference/copy
  - 从母公司参照模板
  - body: { source_project_id, doc_types: ["audit_report", "notes"] }
  - 返回: { copied_files[], diff_markers[] }
```

### 9.2 上年文档 API

```yaml
POST /api/projects/{id}/prior-year/upload
  - 上传上年报告/附注
  - body: FormData(file, doc_type, year)
  - 返回: { document_id, job_id }

GET /api/projects/{id}/prior-year/{doc_type}
  - 获取上年文档解析结果
  - 返回: { parsed_data }

POST /api/projects/{id}/prior-year/prefill-report
  - LLM 智能预填审计报告
  - 返回: { job_id, status }

POST /api/projects/{id}/prior-year/prefill-notes
  - LLM 智能预填附注
  - 返回: { job_id, status }
```

### 9.3 报表快照 API

```yaml
POST /api/projects/{id}/report-snapshot/create
  - 创建报表数据快照
  - 返回: { snapshot_id, is_stale: false }

GET /api/projects/{id}/report-snapshot/latest
  - 获取最新快照（含过期检测）
  - 返回: { snapshot_id, data, is_stale, stale_reason }
```
