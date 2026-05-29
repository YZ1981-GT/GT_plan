"""Property 10: 中文化覆盖不变量 — 静态扫描白名单外英文=0

∀ vue_file F in src/**/*.vue, ∀ static label/title/placeholder attr A:
  A.value ∉ TECH_WHITELIST ∧ A.value is pure English ⇒ FAIL

验证：所有 .vue 文件中的静态 UI 文本（label/title/placeholder）
在排除技术术语白名单后，不应包含纯英文文本。

**Validates: Requirements 13.10**

文件：backend/tests/test_property_10_chinese_coverage.py
"""

import re
import pathlib
import json

import pytest

# ─── 技术术语白名单 ───────────────────────────────────────────────────
TECH_WHITELIST = {
    # 编程/技术
    'SQL', 'PDF', 'OCR', 'LLM', 'AI', 'API', 'URL', 'UUID', 'CSV', 'JSON', 'YAML',
    'HTTP', 'HTTPS', 'UTF', 'RFC', 'ISO', 'XML', 'HTML', 'CSS', 'JWT', 'OAuth',
    'RBAC', 'RLS', 'ORM', 'CRUD', 'REST', 'GraphQL', 'WebSocket', 'SSE',
    'Docker', 'Redis', 'PostgreSQL', 'FastAPI', 'Vue', 'Pinia', 'TypeScript',
    'ESLint', 'Playwright', 'vitest', 'Decimal', 'PyYAML',
    # AI/模型
    'Qwen', 'GPT', 'Claude', 'DeepSeek', 'Ollama', 'vLLM', 'PaddleOCR', 'OpenAI',
    # 审计标准
    'CAS', 'PCAOB', 'WCAG', 'EQCR', 'PBC', 'AJE', 'RJE',
    # 公式/函数
    'TB', 'ROW', 'NOTE', 'WP', 'REPORT', 'AUX', 'PREV', 'IF', 'ABS', 'ROUND',
    'MAX', 'MIN', 'SUM', 'AVG', 'COUNT', 'DISTINCT',
    # 格式/技术
    'OL', 'UL', 'AND', 'OR', 'INNER', 'LEFT', 'RIGHT', 'ID',
    'Excel', 'Word', 'Ref', 'SAP', 'Sheet', 'Token',
    # 日志级别
    'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
    # 数据格式
    'ACT', 'SHA', 'SHA-256', 'YYYY-MM-DD',
    # 其他
    'English', 'LLM Stub', 'API Key',
}

HAS_CHINESE = re.compile(r'[\u4e00-\u9fff]')
ENGLISH_ONLY = re.compile(r'^[A-Za-z][A-Za-z0-9 \-_./\\]*$')

# el-radio / el-radio-button / el-option 的 label 是程序值
PROGRAMMATIC_TAG_RE = re.compile(r'<el-(?:radio|radio-button|option)\b')


def is_whitelisted(value: str) -> bool:
    """Check if value is in technical whitelist."""
    if value in TECH_WHITELIST:
        return True
    words = value.split()
    return all(
        w in TECH_WHITELIST or w.upper() in TECH_WHITELIST or re.match(r'^[0-9.]+$', w)
        for w in words
    )


def find_english_ui_text(src_root: pathlib.Path) -> list[dict]:
    """Scan all .vue files for English UI text that should be Chinese."""
    vue_files = sorted(src_root.rglob('*.vue'))
    hits = []

    for filepath in vue_files:
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        lines = content.split('\n')

        for m in re.finditer(r'(?<!:)(?:label|title|placeholder)="([^"]+)"', content):
            start = m.start()
            if start > 0 and content[start - 1] == ':':
                continue

            val = m.group(1)

            if HAS_CHINESE.search(val):
                continue
            if not ENGLISH_ONLY.match(val):
                continue
            if len(val) <= 2:
                continue
            if '.' in val or (val[0].islower() and any(c.isupper() for c in val[1:])):
                continue
            if is_whitelisted(val):
                continue

            line_num = content[:start].count('\n') + 1
            line_content = lines[line_num - 1] if line_num <= len(lines) else ''

            if 'allow-en-text' in line_content:
                continue
            if re.search(r'(?::|v-bind:)(?:label|title|placeholder)\s*=\s*"' + re.escape(val) + '"', line_content):
                continue
            if PROGRAMMATIC_TAG_RE.search(line_content):
                continue

            hits.append({
                'file': str(filepath.relative_to(src_root)),
                'line': line_num,
                'value': val,
            })

    return hits


def _resolve_src_root() -> pathlib.Path:
    """Resolve the frontend src root from multiple possible locations."""
    candidates = [
        pathlib.Path(__file__).resolve().parent.parent.parent / 'audit-platform' / 'frontend' / 'src',
        pathlib.Path('audit-platform/frontend/src'),
        pathlib.Path('../audit-platform/frontend/src'),
    ]
    for c in candidates:
        if c.exists():
            return c
    pytest.skip('Frontend src directory not found')


class TestProperty10ChineseCoverage:
    """Property 10: 中文化覆盖不变量。"""

    def test_no_english_ui_text_outside_whitelist(self):
        """白名单外英文 UI 文本数量 = 0。

        **Validates: Requirements 13.10**
        """
        src_root = _resolve_src_root()
        hits = find_english_ui_text(src_root)

        if hits:
            details = '\n'.join(
                f"  {h['file']}:{h['line']}: \"{h['value']}\""
                for h in hits[:20]
            )
            pytest.fail(
                f"发现 {len(hits)} 处白名单外英文 UI 文本（应为 0）:\n{details}"
            )

    def test_baseline_guard(self):
        """Baseline 守门：确保 baselines.json 中 no-english-ui-label-vue-files = 0。

        **Validates: Requirements 13.10**
        """
        baselines_candidates = [
            pathlib.Path(__file__).resolve().parent.parent.parent / '.github' / 'workflows' / 'baselines.json',
            pathlib.Path('.github/workflows/baselines.json'),
        ]
        baselines_path = None
        for c in baselines_candidates:
            if c.exists():
                baselines_path = c
                break

        if baselines_path is None:
            pytest.skip('baselines.json not found')

        data = json.loads(baselines_path.read_text(encoding='utf-8'))
        v3_rules = data.get('_v3_eslint_rules', {})
        baseline = v3_rules.get('no-english-ui-label-vue-files', '<TBD>')

        assert baseline == 0, (
            f"baselines.json no-english-ui-label-vue-files = {baseline}，应为 0"
        )
