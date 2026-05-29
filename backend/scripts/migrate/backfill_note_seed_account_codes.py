"""note_template seed 元数据回填工具（L-4 配套数据治理）

**目的**：补全 `note_template_listed.json` / `note_template_soe.json` 中
`tables[].rows[].account_codes` / `report_row_code` 字段，让 L-4 公式引擎
（=TB / =REPORT / =WP 三源自动提数）真实生效。

**使用方式**：
    cd backend
    python scripts/backfill_note_seed_account_codes.py

**当前实测覆盖率（2026-05-22 首次跑）**：
- note_template_listed.json：rows 2546 / 含 label 非 total 2144 / 命中 145 = 6.8%
- note_template_soe.json：rows 1761 / 含 label 非 total 1453 / 命中 64 = 4.4%

**为什么不是 80%**：seed 模板 row label 是真实业务行（如"重要的单项计提坏账
准备的应收款项"），不能机械匹配 wp_account_mapping 的 account_name（"应收账款"）。
要达到 ≥ 80% 需后续：
  ① 人工审计每一行的会计语义（约 2000 行）
  ② LLM 辅助标注（用 Qwen3.5 跑 batch 推理，单条 prompt 约 200 token）
  ③ 二次脚本：当模板 row 含 `account_codes` 后，行模式（"减：坏账准备"等）
     可被识别为数据行而非汇总行

**策略（保守不破坏既有结构）**：
1. 读 wp_account_mapping.json 建索引：
   - by_section: {note_section: [mapping]}（按 section 维度）
   - by_account_name: {normalized_name: [account_codes]}
2. 遍历每个 section.tables[].rows[]：
   - 若行有 label 且非 is_total：
     a. 优先按 label 完全匹配 wp_account_mapping[note_section].account_name
     b. 次按 label 在 account_name 中作子串包含（双向 in 检查 + 去除 "应收/应付/其他/减:" 等前缀）
     c. 命中则填 account_codes + report_row_code（如有）
3. 输出统计：每个 file 命中率
"""
import json
import re
from pathlib import Path

# 解析项目根（脚本位于 backend/scripts/）
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DATA_DIR = BACKEND_DIR / 'data'

# 加载映射
m = json.loads((DATA_DIR / 'wp_account_mapping.json').read_text(encoding='utf-8'))
mappings = m['mappings']

# 索引 1：by_section
by_section: dict[str, list] = {}
for mp in mappings:
    sec = mp.get('note_section')
    if sec:
        by_section.setdefault(sec, []).append(mp)

# 索引 2：by_account_name（normalized）
def normalize(s: str) -> str:
    if not s:
        return ''
    # 去掉常见前缀/标记
    s = s.strip()
    for prefix in ['减：', '减:', '加：', '加:', '其中：', '其中:', '：', ':']:
        s = s.replace(prefix, '')
    return s.strip()

by_account_name: dict[str, list] = {}
for mp in mappings:
    nm = normalize(mp.get('account_name', ''))
    if nm:
        by_account_name.setdefault(nm, []).append(mp)


def match_row_label(label: str, section_title: str | None) -> dict | None:
    """返回匹配的 mapping dict 或 None"""
    norm_label = normalize(label)
    if not norm_label:
        return None

    # 策略 1：先在 section 限定内做 label == account_name 完全匹配
    if section_title:
        # 反查 section title 对应的 note_section 编号
        # note_template_*.json 的 section_number 和 wp_account_mapping.note_section 都是 "五、1" 格式
        for mp in mappings:
            if mp.get('note_section') == section_title:
                if normalize(mp.get('account_name', '')) == norm_label:
                    return mp
        # 退化：section 内子串包含
        for mp in mappings:
            if mp.get('note_section') == section_title:
                a_name = normalize(mp.get('account_name', ''))
                if a_name and (norm_label == a_name or norm_label in a_name or a_name in norm_label):
                    return mp

    # 策略 2：跨 section 的 label == account_name 完全匹配
    if norm_label in by_account_name:
        candidates = by_account_name[norm_label]
        if len(candidates) == 1:
            return candidates[0]
        # 多个候选：选 is_primary=True 的
        for c in candidates:
            if c.get('is_primary'):
                return c
        return candidates[0]

    return None


def backfill(file_path: Path) -> dict:
    data = json.loads(file_path.read_text(encoding='utf-8'))
    sections = data.get('sections', [])
    stats = {'rows_total': 0, 'rows_with_label_non_total': 0, 'matched': 0, 'filled_account_codes': 0, 'filled_report_row_code': 0}

    for s in sections:
        section_number = s.get('section_number')  # "五、1" 等
        for t in (s.get('tables') or []):
            for r in (t.get('rows') or []):
                stats['rows_total'] += 1
                if r.get('is_total'):
                    continue
                label = r.get('label')
                if not label:
                    continue
                stats['rows_with_label_non_total'] += 1

                # 已有 account_codes 跳过
                if r.get('account_codes'):
                    continue

                mp = match_row_label(label, section_number)
                if mp:
                    stats['matched'] += 1
                    if mp.get('account_codes') and not r.get('account_codes'):
                        r['account_codes'] = list(mp['account_codes'])
                        stats['filled_account_codes'] += 1
                    if mp.get('report_row') and not r.get('report_row_code'):
                        r['report_row_code'] = mp['report_row']
                        stats['filled_report_row_code'] += 1

    # 写回（保留 indent=2 + ensure_ascii=False 与原文件风格一致）
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return stats


for fp in [DATA_DIR / 'note_template_listed.json', DATA_DIR / 'note_template_soe.json']:
    print(f'\n=== {fp.name} ===')
    s = backfill(fp)
    pct = 100 * s['filled_account_codes'] / max(s['rows_with_label_non_total'], 1)
    print(f'  rows: {s["rows_total"]} (含 label 非 total: {s["rows_with_label_non_total"]})')
    print(f'  matched: {s["matched"]}, filled account_codes: {s["filled_account_codes"]}, filled report_row: {s["filled_report_row_code"]}')
    print(f'  coverage: {pct:.1f}%')
