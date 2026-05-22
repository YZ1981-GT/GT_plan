// ESLint 自定义规则：禁止在 <script> 块中对金额变量做单位换算
//
// Requirements: F2.1, F2.2, F2.3, F2.4, F2.5, F2.6
//
// 规则逻辑：
// - 检测金额相关变量名（*amount*/*balance*/*total*/*sum*/*debit*/*credit*）
//   与 10000/1000 的乘除运算（单位换算）
// - 排除时间 ms→s 和百分比计算（变量名含 time/ms/percent/pct/rate/ratio）
// - 级别设为 warn
// - 当前 0 处违规，规则目的是防止新增违规

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '禁止在 <script> 块中对金额变量做 / 10000 或 * 10000 单位换算，应在模板层使用 displayPrefs',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noAmountUnitInScript:
        '避免在 <script> 中对金额变量「{{ name }}」做单位换算（{{ op }} {{ divisor }}）。' +
        '单位换算应在模板层通过 displayPrefs / fmtAmountUnit 处理。',
    },
    schema: [],
  },

  create(context) {
    // 金额相关变量名模式
    const AMOUNT_PATTERN = /amount|balance|total|sum|debit|credit/i
    // 排除模式（时间/百分比/比率）
    const EXCLUDE_PATTERN = /time|ms|percent|pct|rate|ratio|progress|duration|delay|timeout/i
    // 单位换算常量
    const UNIT_DIVISORS = [10000, 1000]

    function isAmountName(name) {
      if (!name) return false
      return AMOUNT_PATTERN.test(name) && !EXCLUDE_PATTERN.test(name)
    }

    function getIdentifierName(node) {
      if (!node) return null
      if (node.type === 'Identifier') return node.name
      if (node.type === 'MemberExpression' && node.property) {
        if (node.property.type === 'Identifier') return node.property.name
        if (node.property.type === 'Literal') return String(node.property.value)
      }
      return null
    }

    function isUnitDivisor(node) {
      if (node.type === 'Literal' && typeof node.value === 'number') {
        return UNIT_DIVISORS.includes(node.value)
      }
      return false
    }

    return {
      BinaryExpression(node) {
        // Only check / and * operators
        if (node.operator !== '/' && node.operator !== '*') return

        const leftName = getIdentifierName(node.left)
        const rightName = getIdentifierName(node.right)

        // Pattern: amountVar / 10000 or amountVar * 10000
        if (leftName && isAmountName(leftName) && isUnitDivisor(node.right)) {
          context.report({
            node,
            messageId: 'noAmountUnitInScript',
            data: {
              name: leftName,
              op: node.operator,
              divisor: String(node.right.value),
            },
          })
          return
        }

        // Pattern: 10000 * amountVar (less common but possible)
        if (rightName && isAmountName(rightName) && isUnitDivisor(node.left) && node.operator === '*') {
          context.report({
            node,
            messageId: 'noAmountUnitInScript',
            data: {
              name: rightName,
              op: node.operator,
              divisor: String(node.left.value),
            },
          })
        }
      },
    }
  },
}

module.exports = rule
