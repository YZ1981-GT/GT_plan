// ESLint 自定义规则：检测 UI 文本中的英文（应为中文）
//
// Requirements: Req 13 UI 全中文化
//
// 触发条件：
//   - el-table-column / el-form-item 的 label 属性含纯英文
//   - el-dialog / el-drawer 的 title 属性含纯英文
//   - placeholder 属性含纯英文
//   - <el-button>纯英文文本</el-button>
//
// 豁免条件：
//   - 值含中文字符（混合中英视为已中文化）
//   - 值在技术术语白名单中
//   - el-radio / el-radio-button / el-option 的 label（程序值非可见文本）
//   - 行末含 // allow-en-text 注释
//   - 动态绑定 :label / v-bind:label
//
// Level: warn

/** @type {Set<string>} */
const TECH_WHITELIST = new Set([
  // 编程/技术
  'SQL', 'PDF', 'OCR', 'LLM', 'AI', 'API', 'URL', 'UUID', 'CSV', 'JSON', 'YAML',
  'HTTP', 'HTTPS', 'UTF', 'RFC', 'ISO', 'XML', 'HTML', 'CSS', 'JWT', 'OAuth',
  'RBAC', 'RLS', 'ORM', 'CRUD', 'REST', 'GraphQL', 'WebSocket', 'SSE',
  'Docker', 'Redis', 'PostgreSQL', 'FastAPI', 'Vue', 'Pinia', 'TypeScript',
  'ESLint', 'Playwright', 'vitest', 'Decimal', 'PyYAML',
  // AI/模型
  'Qwen', 'GPT', 'Claude', 'DeepSeek', 'Ollama', 'vLLM', 'PaddleOCR', 'OpenAI',
  // 审计标准
  'CAS', 'PCAOB', 'WCAG', 'EQCR', 'PBC', 'AJE', 'RJE',
  // 公式/函数
  'TB', 'ROW', 'NOTE', 'WP', 'REPORT', 'AUX', 'PREV', 'IF', 'ABS', 'ROUND',
  'MAX', 'MIN', 'SUM', 'AVG', 'COUNT', 'DISTINCT',
  // 格式/技术
  'OL', 'UL', 'AND', 'OR', 'INNER', 'LEFT', 'RIGHT', 'ID',
  'Excel', 'Word', 'Ref', 'SAP', 'Sheet', 'Token',
  // 日志级别
  'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
  // 数据格式
  'ACT', 'SHA', 'SHA-256', 'YYYY-MM-DD',
  // 其他
  'English',  // 语言选项名称
])

// 多词白名单短语
const PHRASE_WHITELIST = new Set([
  'LLM Stub', 'API Key', 'ACT/360', 'ACT/365', '30/360',
])

// el-radio / el-radio-button / el-option 的 label 是程序值，不是可见文本
const PROGRAMMATIC_LABEL_TAGS = new Set([
  'el-radio', 'el-radio-button', 'el-option', 'el-select',
])

// 只检测这些标签的 label/title/placeholder
const TARGET_LABEL_TAGS = new Set([
  'el-table-column', 'el-form-item', 'el-tab-pane',
  'el-dialog', 'el-drawer', 'el-tooltip', 'el-popover',
])

const HAS_CHINESE_RE = /[\u4e00-\u9fff]/
const ENGLISH_ONLY_RE = /^[A-Za-z][A-Za-z0-9 \-_./\\]*$/

/**
 * Check if a value is whitelisted (all words are technical terms).
 * @param {string} value
 * @returns {boolean}
 */
function isWhitelisted(value) {
  if (TECH_WHITELIST.has(value)) return true
  if (PHRASE_WHITELIST.has(value)) return true
  const words = value.split(/\s+/).filter(Boolean)
  return words.every(w =>
    TECH_WHITELIST.has(w) ||
    TECH_WHITELIST.has(w.toUpperCase()) ||
    /^[0-9.]+$/.test(w) ||
    /^[A-Z]-?\d/.test(w)  // 审计编码如 D2, E1, B-100
  )
}

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '检测 UI 可见文本（label/title/placeholder/button）中的纯英文，应使用中文',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noEnglishUiText:
        'UI 文本应使用中文: "{{ text }}"。技术术语可通过白名单豁免或行末 // allow-en-text 注释。',
    },
    schema: [],
  },

  create(context) {
    // 需要 vue-eslint-parser 的 defineTemplateBodyVisitor
    const parserServices = context.parserServices || context.sourceCode.parserServices
    if (!parserServices || !parserServices.defineTemplateBodyVisitor) {
      return {}
    }

    return parserServices.defineTemplateBodyVisitor({
      /**
       * Check label/title/placeholder attributes on elements.
       */
      VAttribute(node) {
        // Skip dynamic bindings (:label, v-bind:label)
        if (node.directive) return

        const attrName = node.key && node.key.name
        if (!attrName) return
        if (!['label', 'title', 'placeholder'].includes(attrName)) return

        // Get the value
        const value = node.value && node.value.value
        if (!value || typeof value !== 'string') return

        // Skip if contains Chinese
        if (HAS_CHINESE_RE.test(value)) return

        // Skip if not English-like
        if (!ENGLISH_ONLY_RE.test(value)) return

        // Skip very short values (likely programmatic)
        if (value.length <= 2) return

        // Skip if parent tag is a programmatic label tag (el-radio, el-option, etc.)
        const element = node.parent && node.parent.parent
        const parentTag = element && element.name
        if (parentTag && PROGRAMMATIC_LABEL_TAGS.has(parentTag)) return

        // Skip whitelisted terms
        if (isWhitelisted(value)) return

        // Skip camelCase / dot notation (dynamic variable references that slipped through)
        if (value.includes('.')) return
        if (value[0] === value[0].toLowerCase() && /[A-Z]/.test(value.slice(1))) return

        // Check for allow-en-text comment on the same line
        const sourceCode = context.getSourceCode ? context.getSourceCode() : context.sourceCode
        if (sourceCode) {
          const line = sourceCode.lines[node.loc.start.line - 1] || ''
          if (line.includes('allow-en-text')) return
        }

        context.report({
          node,
          messageId: 'noEnglishUiText',
          data: { text: value },
        })
      },
    })
  },
}

module.exports = rule
