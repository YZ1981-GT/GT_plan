// ESLint 自定义规则：检测 <el-dialog> 标签必须包含 append-to-body 属性
//
// 背景：Element Plus 的 el-dialog 在嵌套使用时，如果不加 append-to-body，
// 弹窗会渲染在父组件 DOM 内部，导致 z-index 层级混乱和样式溢出问题。
// 项目 conventions 规定所有 el-dialog 必须加 append-to-body。
//
// Level: warn
// 使用方式：在 eslint.config.js 中引入此规则，配置 files: ['**/*.vue']

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description: '检测 <el-dialog> 标签必须包含 append-to-body 属性',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      missingAppendToBody:
        '<el-dialog> 必须添加 append-to-body 属性，避免嵌套弹窗 z-index 层级混乱。',
    },
    schema: [],
  },

  create(context) {
    // This rule works on Vue template AST nodes (vue-eslint-parser)
    return {
      // VElement is the AST node type for Vue template tags
      VElement(node) {
        // Match <el-dialog> or <ElDialog>
        const tagName = node.rawName || node.name
        if (tagName !== 'el-dialog' && tagName !== 'ElDialog') {
          return
        }

        // Check if append-to-body attribute exists
        const hasAppendToBody = node.startTag.attributes.some((attr) => {
          if (attr.type === 'VAttribute') {
            const attrName = attr.key.name
            // Handle both static attribute and v-bind shorthand
            if (attr.key.type === 'VDirectiveKey') {
              // :append-to-body or v-bind:append-to-body
              return (
                attr.key.argument &&
                attr.key.argument.rawName === 'append-to-body'
              )
            }
            return attrName === 'append-to-body'
          }
          return false
        })

        if (!hasAppendToBody) {
          context.report({
            node: node.startTag,
            messageId: 'missingAppendToBody',
          })
        }
      },
    }
  },
}

module.exports = rule
