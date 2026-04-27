# Phase 13: 致同标准 Word 导出引擎 - 设计文档

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
│  POST /projects/{id}/export/audit-report-word                │
│  POST /projects/{id}/export/financial-reports-word            │
│  POST /projects/{id}/export/disclosure-notes-word             │
│  POST /projects/{id}/export/full-package                     │
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
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

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
2. 创建 ExportTask 记录（file_path, status=draft）
3. 前端用 ONLYOFFICE iframe 打开编辑
4. 用户微调措辞、补充内容、调整格式
5. 保存 = WOPI put_file → 版本递增
6. 下载 = 直接下载当前版本 .docx
7. 状态流转：draft → confirmed → signed
```

---

## 4. API 设计

```yaml
# 方案A：从零生成
POST /api/projects/{id}/export/audit-report-word
  返回: .docx 文件流

POST /api/projects/{id}/export/financial-reports-word
  query: { report_types: "BS,IS,CFS,EQ" }
  返回: .docx 文件流

POST /api/projects/{id}/export/disclosure-notes-word
  body: { sections: ["五、1", "五、2"], template_type: "soe"|"listed" }
  返回: .docx 文件流

# 方案B：模板填充
POST /api/projects/{id}/export/fill-audit-report
  返回: { file_path, editor_url }

POST /api/projects/{id}/export/fill-financial-reports
  返回: [{ report_type, file_path, editor_url }]

POST /api/projects/{id}/export/fill-disclosure-notes
  body: { template_type: "soe"|"listed" }
  返回: { file_path, editor_url }

# 通用
POST /api/projects/{id}/export/full-package
  返回: .zip 文件流

GET /api/projects/{id}/export/history
  返回: [{ id, type, file_path, status, created_at }]
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
