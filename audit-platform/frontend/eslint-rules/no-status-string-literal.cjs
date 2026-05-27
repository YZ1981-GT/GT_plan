// ESLint 自定义规则：检测 .vue 文件中状态字符串字面量硬编码
//
// Requirements: Req 8.4 状态枚举统一
//
// 触发条件：检测 `.vue` 文件 <script> 中 Literal 节点值为已知状态字符串
// （'draft' / 'pending_review' / 'archived' 等 statusEnum 值）
// 出现在比较表达式（=== / !==）或对象键值映射中。
//
// 排除：
// - import 语句中的字符串
// - 类型声明中的字符串
// - statusEnum.ts 自身
// - 对象属性键（作为映射定义时允许）
// - const 声明右侧的字面量赋值（如 const X = 'draft'）
//
// Level: warn（baseline 模式：只减不增）

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '禁止在 .vue 文件中硬编码状态字符串字面量，应使用 statusEnum 常量替代硬编码。',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noStatusStringLiteral:
        '检测到状态字符串字面量「{{ value }}」，请使用 statusEnum 常量替代硬编码。',
    },
    schema: [],
  },

  create(context) {
    const filename = context.getFilename ? context.getFilename() : (context.filename || '')

    // 仅检测 .vue 文件
    if (!filename.endsWith('.vue')) return {}

    // 排除 statusEnum.ts 自身（不应该在 .vue 中但以防万一）
    if (filename.includes('statusEnum')) return {}

    // 已知状态字符串列表（来自 statusEnum.ts 中的所有值）
    const STATUS_STRINGS = new Set([
      // WP_STATUS
      'draft', 'edit_complete', 'pending_review', 'under_review',
      'review_passed', 'rejected', 'archived',
      // WP_REVIEW_STATUS
      'pending', 'reviewing', 'approved',
      // REPORT_STATUS
      'eqcr_approved', 'final',
      // ADJUSTMENT_STATUS (draft/pending_review/approved/rejected already above)
      // PROJECT_STATUS
      'created', 'planning', 'execution', 'completion', 'reporting',
      // ISSUE_STATUS
      'open', 'in_progress', 'resolved', 'closed',
      // WORKHOUR_STATUS
      'tracking',
      // TEMPLATE_STATUS
      'published', 'deprecated',
      // PDF/EXPORT_TASK_STATUS
      'queued', 'processing', 'completed', 'failed',
      // PROCEDURE_EXECUTION_STATUS
      'reviewed', 'not_applicable', 'skip',
      // Additional common ones
      'not_started', 'in_fix', 'pending_recheck',
      'draft_complete', 'revision_required',
      'review_level1_passed', 'review_level2_passed',
    ])

    // Short common words that are too generic to flag
    // (they appear in many non-status contexts)
    const GENERIC_SKIP = new Set([
      'open', 'closed', 'pending', 'completed', 'failed',
      'approved', 'rejected', 'final', 'created',
      'processing', 'queued', 'resolved', 'published',
      'tracking', 'skip',
    ])

    /**
     * Check if a node is inside an import declaration
     */
    function isInImport(node) {
      let cur = node.parent
      while (cur) {
        if (cur.type === 'ImportDeclaration') return true
        cur = cur.parent
      }
      return false
    }

    /**
     * Check if a node is inside a type annotation / interface / type alias
     */
    function isInTypeContext(node) {
      let cur = node.parent
      while (cur) {
        if (
          cur.type === 'TSTypeAnnotation' ||
          cur.type === 'TSInterfaceDeclaration' ||
          cur.type === 'TSTypeAliasDeclaration' ||
          cur.type === 'TSLiteralType'
        ) return true
        cur = cur.parent
      }
      return false
    }

    /**
     * Check if a literal is used as an object property key
     * e.g. { 'draft': '草稿' } — the key 'draft' is allowed
     */
    function isObjectPropertyKey(node) {
      return (
        node.parent &&
        node.parent.type === 'Property' &&
        node.parent.key === node
      )
    }

    /**
     * Check if a literal is in a const/let/var declaration initializer
     * e.g. const STATUS = 'draft' — this is defining a constant
     */
    function isConstantDefinition(node) {
      return (
        node.parent &&
        node.parent.type === 'VariableDeclarator' &&
        node.parent.init === node
      )
    }

    /**
     * Check if a literal is in a switch case test
     * e.g. case 'draft': — this is a comparison pattern
     */
    function isSwitchCaseTest(node) {
      return (
        node.parent &&
        node.parent.type === 'SwitchCase' &&
        node.parent.test === node
      )
    }

    /**
     * Check if a literal is in a comparison expression (=== / !==)
     */
    function isInComparison(node) {
      return (
        node.parent &&
        node.parent.type === 'BinaryExpression' &&
        (node.parent.operator === '===' || node.parent.operator === '!==' ||
         node.parent.operator === '==' || node.parent.operator === '!=')
      )
    }

    /**
     * Check if a literal is in an array expression (e.g. ['draft', 'pending'])
     */
    function isInArray(node) {
      return node.parent && node.parent.type === 'ArrayExpression'
    }

    /**
     * Check if a node is inside a mapping function (function with Record/map/switch pattern)
     * These are legitimate patterns for status→label/color mapping
     */
    function isInMappingFunction(node) {
      let cur = node.parent
      while (cur) {
        // Object expression used as a map (e.g. { draft: '草稿', ... }[status])
        if (cur.type === 'ObjectExpression') return true
        // Stop at function boundary
        if (
          cur.type === 'FunctionDeclaration' ||
          cur.type === 'FunctionExpression' ||
          cur.type === 'ArrowFunctionExpression'
        ) break
        cur = cur.parent
      }
      return false
    }

    /**
     * Main check: report status string literals used in comparisons
     * (the most problematic patterns for maintenance)
     */
    function checkLiteral(node) {
      if (typeof node.value !== 'string') return
      if (!STATUS_STRINGS.has(node.value)) return

      // Skip generic words unless in direct comparison context
      if (GENERIC_SKIP.has(node.value)) {
        if (!isInComparison(node)) return
      }

      // Exclusions
      if (isInImport(node)) return
      if (isInTypeContext(node)) return
      if (isObjectPropertyKey(node)) return
      if (isConstantDefinition(node)) return
      if (isInMappingFunction(node)) return

      // Switch cases in script are legitimate mapping patterns (statusLabel functions)
      if (isSwitchCaseTest(node)) return

      // Only flag: direct comparisons (=== / !==) in template or script
      if (!isInComparison(node)) return

      context.report({
        node,
        messageId: 'noStatusStringLiteral',
        data: { value: node.value },
      })
    }

    // For .vue files, we need to handle both script and template
    // Script-level Literal nodes are visited directly
    // Template-level needs defineTemplateBodyVisitor

    const scriptVisitor = {
      Literal: checkLiteral,
    }

    // If vue-eslint-parser is available, also check template expressions
    if (
      context.parserServices &&
      typeof context.parserServices.defineTemplateBodyVisitor === 'function'
    ) {
      return context.parserServices.defineTemplateBodyVisitor(
        {
          // Template expressions (e.g. v-if="status === 'draft'")
          'VExpressionContainer Literal': checkLiteral,
        },
        // Script visitor (second argument)
        scriptVisitor,
      )
    }

    return scriptVisitor
  },
}

module.exports = rule
