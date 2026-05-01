"""解析附注模板Word文件，提取实际表格结构

输出每个章节的表格数量和表头信息，用于核对 note_template_soe/listed.json
"""
import sys
from docx import Document

def parse_note_docx(path: str):
    doc = Document(path)
    
    current_section = ""
    table_count = 0
    total_tables = 0
    
    # 遍历所有段落和表格
    for element in doc.element.body:
        tag = element.tag.split('}')[-1]
        
        if tag == 'p':
            # 段落 — 检查是否是章节标题
            from docx.oxml.ns import qn
            text = ''.join(node.text or '' for node in element.iter(qn('w:t')))
            text = text.strip()
            
            # 识别章节标题（如 "五、1 货币资金" 或 "(一) 货币资金"）
            if text and len(text) < 80:
                # 检查是否以编号开头
                for prefix in ['五、', '四、', '三、', '二、', '一、', '六、', '七、', '八、', '九、', '十、']:
                    if text.startswith(prefix):
                        if current_section and table_count > 0:
                            print(f"  → {table_count} 个表格")
                        current_section = text[:40]
                        table_count = 0
                        print(f"\n{current_section}")
                        break
                # 也检查 (一) (二) 等子标题
                if text.startswith('(') or text.startswith('（'):
                    if len(text) < 50:
                        print(f"    子节: {text}")
        
        elif tag == 'tbl':
            # 表格
            table_count += 1
            total_tables += 1
            
            # 提取表头（第一行）
            rows = element.findall('.//' + '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr')
            if rows:
                first_row = rows[0]
                cells = first_row.findall('.//' + '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc')
                headers = []
                for cell in cells:
                    cell_text = ''.join(node.text or '' for node in cell.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
                    headers.append(cell_text.strip())
                print(f"    表{table_count}: {len(rows)}行 表头={headers[:8]}")
    
    if current_section and table_count > 0:
        print(f"  → {table_count} 个表格")
    
    print(f"\n总计: {total_tables} 个表格")


if __name__ == "__main__":
    print("=" * 60)
    print("国企版合并附注模板")
    print("=" * 60)
    parse_note_docx("审计报告模板/国企版/合并/1.1-2025国企财务报表附注20260106.docx")
    
    print("\n\n")
    print("=" * 60)
    print("上市版合并附注模板")
    print("=" * 60)
    parse_note_docx("审计报告模板/上市版/合并_上市/3.2025年度上市公司财务报表附注模板-2026.01.15.docx")
