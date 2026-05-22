// ESLint 自定义规则：检测金额相关变量的直接算术运算
//
// Requirements: F1.5, F1.6
//
// 规则逻辑：
// - 对金额相关变量名（*amount*/*balance*/*total*/*sum*/*debit*/*credit*）
//   使用直接 +/-/*// 运算符时发出 warning
// - 开发者可通过 // eslint-disable-next-line 豁免
// - 级别设为 warn（高误报风险，初期收集误报后再升级）

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '禁止对金额相关变量直接使用算术运算符，应使用 useDecimalCalc composable',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noAmountArithmetic:
        '避免对金额变量「{{ name }}」直接使用算术运算符。请使用 useDecimalCalc() 的 add/sub/mul/div/sum 方法。',
    },
    schema: [],
  },

  create(context) {
    // 金额相关变量名模式（不区分大小写）
    const AMOUNT_PATTERN = /amount|balance|total|sum|debit|credit/i

    function isAmountName(name) {
      return AMOUNT_PATTERN.test(name)
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

    return {
      BinaryExpression(node) {
        // Only check arithmetic operators
        if (!['+', '-', '*', '/'].includes(node.operator)) return

        const leftName = getIdentifierName(node.left)
        const rightName = getIdentifierName(node.right)

        if (leftName && isAmountName(leftName)) {
          context.report({
            node,
            messageId: 'noAmountArithmetic',
            data: { name: leftName },
          })
        } else if (rightName && isAmountName(rightName)) {
          context.report({
            node,
            messageId: 'noAmountArithmetic',
            data: { name: rightName },
          })
        }
      },

      AssignmentExpression(node) {
        // Check +=, -=, *=, /= on amount variables
        if (!['+=', '-=', '*=', '/='].includes(node.operator)) return

        const leftName = getIdentifierName(node.left)
        if (leftName && isAmountName(leftName)) {
          context.report({
            node,
            messageId: 'noAmountArithmetic',
            data: { name: leftName },
          })
        }
      },
    }
  },
}

module.exports = rule
