# 归档模板目录

本目录存放归档包 PDF 生成所需的模板文件。

## 当前实现方案

由于 `python-docx` 未安装，当前采用 **HTML 模板 → LibreOffice headless 转 PDF** 方案。
HTML 模板内嵌在 `backend/app/services/archive_pdf_generators.py` 中。

## 模板文件（预留）

如果未来切换到 python-docx 方案，可在此目录放置：

- `project_cover.docx` — 项目封面模板（占位符：`{{client_name}}` / `{{project_name}}` / `{{period}}` / `{{opinion_type}}` / `{{report_number}}` / `{{sign_date}}` / `{{partner_name}}`）
- `signature_ledger.docx` — 签字流水模板（支持 N 级签字，预留 EQCR 扩展）

## 章节编号

| 前缀 | 文件名 | 来源 |
|------|--------|------|
| 00 | 00-项目封面.pdf | R1 需求 6 |
| 01 | 01-签字流水.pdf | R1 需求 6 |
| 02 | 02-EQCR备忘录.pdf | R5 需求 9（预留） |
| 03 | 03-质控抽查报告.pdf | R3 需求 4（预留） |
| 04 | 04-独立性声明/ | R1 需求 10（预留） |
| 10 | 10-底稿/ | 现有 |
| 20 | 20-报表/ | 现有 |
| 30 | 30-附注/ | 现有 |
| 40 | 40-附件/ | 现有 |
| 99 | 99-审计日志.jsonl | R1 需求 6 |
