"""
基于 workpaper_template_analysis.json 生成人工可读的 markdown 文档
按 16 循环分章节，每循环列：
  - 模板 xlsx 列表（按编码排序）
  - 每个 xlsx 的 sheet 表格（sheet 名 / 类别 / 行列 / 公式数 / 推荐渲染 / reason）
  - 循环级统计

用法：
  python backend/scripts/generate_template_analysis_md.py
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

INPUT_JSON = Path(r'D:\GT_plan\.kiro\specs\workpaper-html-renderer\workpaper_template_analysis.json')
OUTPUT_MD = Path(r'D:\GT_plan\.kiro\specs\workpaper-html-renderer\workpaper_template_analysis.md')


def main():
    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    md = []
    md.append('# 底稿模板逐 sheet 分析与处理建议')
    md.append('')
    md.append(f'> **数据源**：`backend/wp_templates/` 全量 xlsx 模板扫描')
    md.append(f'> **生成时间**：{data["meta"]["generated_at"][:19]}')
    md.append(f'> **覆盖范围**：{data["meta"]["total_xlsx"]} 个 xlsx 模板 × {data["meta"]["total_sheets"]} 个 sheet')
    md.append(f'> **生成脚本**：`backend/scripts/analyze_wp_templates.py`（含 60+ 条归类规则）+ `backend/scripts/generate_template_analysis_md.py`')
    md.append(f'> **JSON 数据**：`workpaper_template_analysis.json`（机器读，design 阶段消费）')
    md.append('')
    md.append('## 全局统计')
    md.append('')
    md.append('### 归类分布')
    md.append('')
    md.append('| 类别 | 数量 | 占比 |')
    md.append('|------|------|------|')
    total = data['meta']['total_sheets']
    for cls, cnt in sorted(data['class_summary'].items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        md.append(f'| {cls} | {cnt} | {pct:.1f}% |')
    md.append('')
    md.append('### 渲染策略分布')
    md.append('')
    md.append('| 渲染策略 | 数量 | 占比 |')
    md.append('|---------|------|------|')
    for r, cnt in sorted(data['render_summary'].items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        md.append(f'| {r} | {cnt} | {pct:.1f}% |')
    md.append('')

    # 全局健康度
    pending = data['class_summary'].get('_pending', 0)
    classified = total - pending
    classify_rate = classified / total * 100
    md.append('### 自动归类健康度')
    md.append('')
    md.append(f'- 已自动归类：**{classified} sheet（{classify_rate:.1f}%）**')
    md.append(f'- 待人工归类：**{pending} sheet（{100-classify_rate:.1f}%）** — {"✅ 达标（>95%）" if classify_rate >= 95 else "❌ 未达标（<95% 不进 implementation）"}')
    md.append('')

    # 按循环输出
    md.append('## 按循环逐一分析')
    md.append('')

    # 循环顺序按字母 + S + _reference
    cycle_order = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S', '_reference']

    for cycle_key in cycle_order:
        if cycle_key not in data['cycles']:
            continue
        cycle_data = data['cycles'][cycle_key]
        templates = cycle_data['templates']
        if not templates:
            continue

        # 循环统计
        all_sheets = []
        for tpl in templates:
            all_sheets.extend(tpl.get('sheets', []))
        cycle_class_count = Counter(s['class'] for s in all_sheets)
        cycle_render_count = Counter(s['render'] for s in all_sheets)

        md.append(f'### {cycle_key} {cycle_data["cycle_name"]}（{len(templates)} 个 xlsx / {len(all_sheets)} 个 sheet）')
        md.append('')
        md.append(f'**类别分布**：')
        md.append('')
        md.append('| 类别 | 数量 |')
        md.append('|------|------|')
        for cls, cnt in cycle_class_count.most_common():
            md.append(f'| {cls} | {cnt} |')
        md.append('')

        # 每个 xlsx 的 sheet 表
        md.append(f'#### {cycle_key} 模板逐表分析')
        md.append('')
        for tpl in templates:
            md.append(f'##### `{tpl["filename"]}`')
            md.append('')
            sheets = tpl.get('sheets', [])
            if not sheets:
                if tpl.get('error'):
                    md.append(f'⚠️ 解析失败：{tpl["error"]}')
                else:
                    md.append('（空 xlsx）')
                md.append('')
                continue
            md.append('| sheet 名 | 类别 | 行×列 | 合并 | 公式 | 长文本 | 推荐渲染 | reason |')
            md.append('|----------|------|------|------|------|--------|---------|--------|')
            for sh in sheets:
                f = sh['features']
                # 转义管道
                name_safe = sh['name'].replace('|', '\\|')
                reason_safe = sh['reason'].replace('|', '\\|')
                md.append(f'| {name_safe} | {sh["class"]} | {f["max_row"]}×{f["max_col"]} | {f["merged_count"]} | {f["formula_cells"]} | {f["long_text_cells"]} | {sh["render"]} | {reason_safe} |')
            md.append('')

    # 待人工归类清单
    md.append('## 待人工归类 sheet 清单')
    md.append('')
    pending_sheets = data.get('pending_sheets', [])
    md.append(f'共 **{len(pending_sheets)}** 个 sheet 未匹配自动归类规则，需 design 阶段人工归类（参考特征推断 + 落 PG `workpaper_sheet_classification` 表）。')
    md.append('')
    if pending_sheets:
        md.append('| 循环 | 模板 | sheet 名 | 行×列 | 公式 | 长文本 | 建议方向 |')
        md.append('|------|------|---------|------|------|--------|---------|')
        for p in pending_sheets:
            f = p['features']
            # 自动建议方向（启发式）
            if f['formula_cells'] >= 10:
                hint = '建议 F 数据表'
            elif f['formula_cells'] >= 3 and ('计算' in p['sheet'] or '测算' in p['sheet']):
                hint = '建议 G 测算'
            elif f['long_text_cells'] >= 3:
                hint = '建议 D 段落型表单'
            elif f['merged_count'] / max(f['max_row'], 1) > 0.3:
                hint = '建议 C 嵌套表'
            else:
                hint = '建议 D 表格型表单'
            tpl_safe = p['template'][:35].replace('|', '\\|')
            sheet_safe = p['sheet'][:30].replace('|', '\\|')
            md.append(f'| {p["cycle"]} | {tpl_safe} | {sheet_safe} | {f["max_row"]}×{f["max_col"]} | {f["formula_cells"]} | {f["long_text_cells"]} | {hint} |')
        md.append('')

    md.append('---')
    md.append('')
    md.append('## design 阶段使用本文档的方式')
    md.append('')
    md.append('1. 每个底稿模板 xlsx 作为 schema 单元（参见 4.3.1 方案 C 还原约束）')
    md.append('2. 每个 sheet 的"类别"决定渲染组件选择（A 中控台 / B 表单 / C 嵌套表 / D 表单 / E stepper / F-G Univer / H 静态 / I 跳过）')
    md.append('3. 每个 sheet 的"特征"决定 schema 字段映射（行列 → 表单字段数 / 合并 → rowspan/colspan / 公式 → 保留 xlsx 公式不写值）')
    md.append('4. 待人工归类 92 sheet 走 design 阶段第 1 周专项处理')
    md.append('5. JSON 文件作为 implementation 阶段的归类映射数据源（落 PG `workpaper_sheet_classification` 表）')

    # 写文件
    OUTPUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(f'[OK] Generated: {OUTPUT_MD}')
    print(f'  Lines: {len(md)}')


if __name__ == '__main__':
    main()
