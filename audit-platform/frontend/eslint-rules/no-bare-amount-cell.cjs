// ESLint 自定义规则：检测表格金额列未使用 GtAmountCell 组件
//
// Requirements: V3 Req 8.1 金额列格式化
//
// 触发条件：
//   1) <el-table-column> 含 align="right" 属性
//   2) prop 命中金额关键字（amount/balance/debit/credit/tax/cost/price/...）
//      或 label 含中文金额关键字（金额/余额/借方/贷方/税金/成本/价格/合计/...）
//   3) 子树未含 <GtAmountCell> / <gt-amount-cell> / <g-t-amount-cell>
//      也未含 formatAmount / displayAmount / amountFormatter 等格式化调用
//
// Level: warn（baseline 模式：只减不增；接入时以 baseline=109 为起点）
//
// 注：本规则用 vue-eslint-parser defineTemplateBodyVisitor 走模板 AST，
//     不能直接 return { VElement(...) }（vue 文件默认 visitor 不走模板）。

// 金额关键字（与 _scan_bare_amount_cells.mjs 保持一致）
const AMOUNT_PROP_RE =
  /(amount|balance|debit|credit|tax|cost|price|principal|interest|payable|receivable|salary|fund|equity|capital|fee|charge|discount|profit|loss|revenue|expense|income|net_asset|netasset)/i
const AMOUNT_LABEL_RE =
  /(金额|余额|借方|贷方|税金|税额|成本|价格|合计|小计|总计|总额|本金|利息|应付|应收|薪资|工资|股本|权益|费用|费率|折扣|损益|利润|亏损|收入|支出|资产|负债|净资产|股东|未分配|盈余)/

const GT_AMOUNT_TAG_RE = /^(GtAmountCell|gt-amount-cell|g-t-amount-cell)$/
const FORMAT_HELPER_RE = /(formatAmount|displayAmount|amountFormatter|toCurrency|formatCurrency)/

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '金额相关的 el-table-column（align=right + prop/label 命中金额关键字）应使用 <GtAmountCell> 组件，确保 displayPrefs 全局一致',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noBareAmountCell:
        '<el-table-column prop="{{ prop }}" align="right"> 检测到金额列但未使用 <GtAmountCell>，建议接入以保证 displayPrefs 全局一致',
    },
    schema: [],
  },

  create(context) {
    function getTagName(node) {
      if (!node || node.type !== 'VElement') return null
      return node.rawName || node.name || null
    }

    function isElTableColumn(node) {
      const name = getTagName(node)
      return name === 'el-table-column' || name === 'ElTableColumn'
    }

    /**
     * 取静态属性值：name="value" / :name="'value'"（仅常量字符串字面量）
     */
    function readStaticAttr(node, name) {
      const attrs = (node.startTag && node.startTag.attributes) || []
      for (const attr of attrs) {
        if (!attr || attr.type !== 'VAttribute') continue
        // 静态：name="value"
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
        // 动态 :name="'foo'"（取常量字符串）
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
     * 递归子树检查：是否含 GtAmountCell 组件 或 格式化辅助函数调用
     */
    function subtreeHasGtAmountOrFormatter(node) {
      if (!node) return false
      if (node.type === 'VElement') {
        const tag = getTagName(node)
        if (tag && GT_AMOUNT_TAG_RE.test(tag)) return true
      }
      // VExpressionContainer 内含 formatAmount(...) 等调用：查源文本
      if (node.type === 'VExpressionContainer' && node.expression) {
        const src = context.getSourceCode().getText(node)
        if (FORMAT_HELPER_RE.test(src)) return true
      }
      const children = node.children || []
      for (const child of children) {
        if (subtreeHasGtAmountOrFormatter(child)) return true
      }
      return false
    }

    if (
      !context.parserServices ||
      typeof context.parserServices.defineTemplateBodyVisitor !== 'function'
    ) {
      return {}
    }

    return context.parserServices.defineTemplateBodyVisitor({
      VElement(node) {
        if (!isElTableColumn(node)) return

        const align = readStaticAttr(node, 'align')
        if (align !== 'right') return

        const prop = readStaticAttr(node, 'prop')
        const label = readStaticAttr(node, 'label')

        const propHit = prop && AMOUNT_PROP_RE.test(prop)
        const labelHit = label && AMOUNT_LABEL_RE.test(label)
        if (!propHit && !labelHit) return

        if (subtreeHasGtAmountOrFormatter(node)) return

        context.report({
          node: node.startTag,
          messageId: 'noBareAmountCell',
          data: { prop: prop || label || '(未指定 prop)' },
        })
      },
    })
  },
}

module.exports = rule
