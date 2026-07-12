// Feature: platform-global-hardening
// ESLint 自定义规则：检测可用 Wp_Kit 组件的等价手写结构
//
// Requirements: Req 4.6 — WHERE 某处存在可用的 Wp_Kit 组件，
// THE ESLint 规则 SHALL 禁止手写等价结构，并在检出时报错。
//
// 检测特征（保守策略，低误报）：
//   1) 手写 <el-input type="textarea" :autosize> 在底稿结论/意见区域
//      → 建议使用 <WpOpinionCard>
//   2) 手写 <el-dropdown> 含"导入"或"导出"文案
//      → 建议使用 <WpImportExport>
//   3) 直接使用 toLocaleString 渲染金额
//      → 建议使用 <WpAmountCell>
//
// Level: warn（灰度策略，初期不阻断）

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '检测可用 Wp_Kit 组件的等价手写结构（autosize textarea 结论区 / 含「导入/导出」文案的 el-dropdown / 直接 toLocaleString 渲染金额），建议使用对应 Wp_Kit 组件',
      category: 'Best Practices',
      recommended: false,
    },
    messages: {
      useWpOpinionCard:
        '检测到手写 autosize textarea（结论/意见区），建议使用 <WpOpinionCard> 组件以统一交互规范',
      useWpImportExport:
        '检测到手写 el-dropdown 含"导入/导出"文案，建议使用 <WpImportExport> 组件以统一导入导出交互',
      useWpAmountCell:
        '检测到直接使用 toLocaleString 渲染金额，建议使用 <WpAmountCell> 组件以保证 displayPrefs 全局一致',
    },
    schema: [],
  },

  create(context) {
    // ── 辅助函数 ──────────────────────────────────────────────

    function getTagName(node) {
      if (!node || node.type !== 'VElement') return null
      return node.rawName || node.name || null
    }

    /**
     * 取静态属性值（含动态常量绑定）
     */
    function readStaticAttr(node, name) {
      const attrs = (node.startTag && node.startTag.attributes) || []
      for (const attr of attrs) {
        if (!attr || attr.type !== 'VAttribute') continue
        // 静态: name="value"
        if (
          !attr.directive &&
          attr.key &&
          attr.key.type === 'VIdentifier' &&
          attr.key.name === name &&
          attr.value &&
          typeof attr.value.value === 'string'
        ) {
          return attr.value.value
        }
        // 动态 :name="'value'"（仅常量字符串字面量）
        if (
          attr.directive &&
          attr.key &&
          attr.key.type === 'VDirectiveKey' &&
          attr.key.name &&
          (attr.key.name.name === 'bind' || attr.key.name.rawName === 'bind') &&
          attr.key.argument &&
          (attr.key.argument.rawName === name || attr.key.argument.name === name) &&
          attr.value &&
          attr.value.expression &&
          attr.value.expression.type === 'Literal' &&
          typeof attr.value.expression.value === 'string'
        ) {
          return attr.value.expression.value
        }
      }
      return null
    }

    /**
     * 检查节点是否有某个属性（不区分动态/静态），仅检查存在性
     */
    function hasAttr(node, name) {
      const attrs = (node.startTag && node.startTag.attributes) || []
      for (const attr of attrs) {
        if (!attr || attr.type !== 'VAttribute') continue
        // 静态属性
        if (
          !attr.directive &&
          attr.key &&
          attr.key.type === 'VIdentifier' &&
          attr.key.name === name
        ) {
          return true
        }
        // 动态绑定 :name / v-bind:name
        if (
          attr.directive &&
          attr.key &&
          attr.key.type === 'VDirectiveKey' &&
          attr.key.name &&
          (attr.key.name.name === 'bind' || attr.key.name.rawName === 'bind') &&
          attr.key.argument &&
          (attr.key.argument.rawName === name || attr.key.argument.name === name)
        ) {
          return true
        }
      }
      return false
    }

    /**
     * 递归提取子树中所有文本内容（VText + VExpressionContainer 的源文本）
     */
    function extractTextContent(node) {
      if (!node) return ''
      let text = ''
      if (node.type === 'VText') {
        text += node.value || ''
      }
      if (node.type === 'VExpressionContainer' && node.expression) {
        text += context.getSourceCode().getText(node)
      }
      if (node.type === 'VLiteral') {
        text += node.value || ''
      }
      const children = node.children || []
      for (const child of children) {
        text += extractTextContent(child)
      }
      return text
    }

    // ── 检测文件路径 ──────────────────────────────────────────

    const filename = context.getFilename()
    // 仅对底稿相关 Vue 文件生效（workpaper/ 目录下），减少误报
    const isWorkpaperFile = /[/\\]workpaper[/\\]/i.test(filename)

    // ── 模板 visitor ──────────────────────────────────────────

    if (
      !context.parserServices ||
      typeof context.parserServices.defineTemplateBodyVisitor !== 'function'
    ) {
      return {}
    }

    return context.parserServices.defineTemplateBodyVisitor(
      {
        // ─── 检测1: autosize textarea 结论区 → WpOpinionCard ───
        VElement(node) {
          const tag = getTagName(node)

          // 检测1: el-input type="textarea" + autosize → WpOpinionCard
          if (tag === 'el-input' || tag === 'ElInput') {
            const typeAttr = readStaticAttr(node, 'type')
            if (typeAttr === 'textarea' && hasAttr(node, 'autosize')) {
              // 保守策略：仅在底稿文件中报告
              if (isWorkpaperFile) {
                context.report({
                  node: node.startTag,
                  messageId: 'useWpOpinionCard',
                })
              }
            }
          }

          // 检测2: el-dropdown 含"导入/导出"文案 → WpImportExport
          if (tag === 'el-dropdown' || tag === 'ElDropdown') {
            const textContent = extractTextContent(node)
            // 中文"导入"或"导出"在同一个 dropdown 中出现
            const has导入 = textContent.includes('导入')
            const has导出 = textContent.includes('导出')
            if (has导入 && has导出) {
              // 保守：仅当同时含"导入"和"导出"两词时报告
              if (isWorkpaperFile) {
                context.report({
                  node: node.startTag,
                  messageId: 'useWpImportExport',
                })
              }
            }
          }
        },

        // ─── 检测3: toLocaleString 渲染金额 → WpAmountCell ───
        // 在模板表达式中检测 .toLocaleString() 调用
        "VExpressionContainer CallExpression[callee.property.name='toLocaleString']"(
          node,
        ) {
          if (!isWorkpaperFile) return
          context.report({
            node,
            messageId: 'useWpAmountCell',
          })
        },
      },
      // script visitor（可选，用于捕获 script 中的 toLocaleString 用于渲染）
      {},
    )
  },
}

module.exports = rule
