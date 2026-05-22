// ESLint 自定义规则：禁止在 .vue / .ts 文件中直接调用 .toFixed() 用于金额格式化
//
// Requirements: 8.4, 8.5
//
// 规则逻辑：
// - 对所有 .toFixed() 调用发出 warning
// - 开发者可通过 // eslint-disable-next-line gt-audit/no-amount-toFixed 豁免非金额用途
// - formatters.ts 内部实现不受此规则影响（通过文件名检测排除）
//
// 使用方式（当项目引入 ESLint 后）：
//   在 eslint.config.js 中引入此规则，配置 files: ['*.vue', '*.ts']
//   并 ignores: ['formatters.ts']

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '禁止直接调用 .toFixed() 格式化金额，应使用 fmtAmountUnit / displayPrefs.fmt()',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      avoidToFixed:
        '避免直接使用 .toFixed() 格式化金额。请使用 fmtAmountUnit() 或 displayPrefs.fmt()。' +
        '如果此处为非金额用途（百分比/文件大小/耗时等），请添加 // eslint-disable-next-line gt-audit/no-amount-toFixed',
    },
    schema: [],
  },

  create(context) {
    // Skip formatters.ts internal implementation
    const filename = context.getFilename ? context.getFilename() : context.filename || ''
    if (filename.includes('formatters.ts') || filename.includes('formatters.js')) {
      return {}
    }

    return {
      // Detect .toFixed(...) call expressions
      // AST pattern: CallExpression with callee being MemberExpression
      // where property.name === 'toFixed'
      CallExpression(node) {
        if (
          node.callee &&
          node.callee.type === 'MemberExpression' &&
          node.callee.property &&
          node.callee.property.type === 'Identifier' &&
          node.callee.property.name === 'toFixed'
        ) {
          context.report({
            node,
            messageId: 'avoidToFixed',
          })
        }
      },
    }
  },
}

module.exports = rule
