// ESLint 自定义规则：检测 <el-form> 含提交按钮但缺 :rules 属性
//
// Requirements: Req 3 表单校验
//
// 触发条件：检测 `<el-form>` 内含提交类按钮（按钮文字含
// 提交/保存/创建/签字/新建/新增/确认/发送 等关键词）但未绑定
// `:rules` / `v-bind:rules`。检出后给开发者一个明确的中文提示，
// 提醒补齐表单校验规则，避免空值或非法输入直接落库。
//
// Level: warn（baseline 模式：只减不增）
// 使用方式：在 .eslintrc.cjs 中通过 plugins: ['gt-audit'] 引入

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '含提交按钮的 <el-form> 必须绑定 :rules 属性进行表单校验',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      elFormMustHaveRules:
        'el-form 包含提交类按钮（{{ buttonText }}）但未绑定 :rules，提交时无法拦截空值或非法输入。请补充表单校验规则。',
    },
    schema: [],
  },

  create(context) {
    // 提交类按钮关键词（命中其一即视为提交按钮）
    const SUBMIT_KEYWORD = /(提交|保存|创建|签字|新建|新增|确认|发送)/

    /**
     * 取 VElement 的标签名（兼容大小写写法 el-form / ElForm）
     */
    function getTagName(node) {
      if (!node || node.type !== 'VElement') return null
      return node.rawName || node.name || null
    }

    /**
     * 判断 VElement 是否为指定标签（同时匹配 kebab-case 与 PascalCase）
     */
    function isTag(node, kebab, pascal) {
      const name = getTagName(node)
      if (!name) return false
      return name === kebab || name === pascal
    }

    /**
     * 判断 el-form 是否绑定了 :rules / v-bind:rules
     */
    function hasRulesBinding(formNode) {
      const attrs =
        (formNode.startTag && formNode.startTag.attributes) || []
      return attrs.some((attr) => {
        if (!attr || attr.type !== 'VAttribute') return false
        // 静态属性 rules="..." 也算（虽然罕见，但开发者可能误写）
        if (attr.key && attr.key.type === 'VIdentifier') {
          return attr.key.name === 'rules'
        }
        // v-bind:rules / :rules 简写
        if (attr.key && attr.key.type === 'VDirectiveKey') {
          const dirName =
            attr.key.name && (attr.key.name.name || attr.key.name.rawName)
          if (dirName !== 'bind') return false
          const arg = attr.key.argument
          if (!arg) return false
          const argName = arg.rawName || arg.name
          return argName === 'rules'
        }
        return false
      })
    }

    /**
     * 从 el-button 节点提取按钮可见文字（VText 子节点 + label 属性兜底）
     */
    function extractButtonText(buttonNode) {
      const parts = []
      // 1) 子节点中的 VText
      const children = buttonNode.children || []
      for (const child of children) {
        if (child && child.type === 'VText' && typeof child.value === 'string') {
          parts.push(child.value)
        }
      }
      // 2) label="..." 静态属性兜底
      const attrs =
        (buttonNode.startTag && buttonNode.startTag.attributes) || []
      for (const attr of attrs) {
        if (
          attr &&
          attr.type === 'VAttribute' &&
          attr.key &&
          attr.key.type === 'VIdentifier' &&
          attr.key.name === 'label' &&
          attr.value &&
          typeof attr.value.value === 'string'
        ) {
          parts.push(attr.value.value)
        }
      }
      return parts.join(' ').trim()
    }

    /**
     * 递归查找 el-form 子树中第一个命中关键词的提交按钮
     * 返回该按钮的可见文字；若无则返回 null
     */
    function findSubmitButtonText(node) {
      if (!node) return null
      // 命中 el-button 直接判断
      if (isTag(node, 'el-button', 'ElButton')) {
        const text = extractButtonText(node)
        if (text && SUBMIT_KEYWORD.test(text)) {
          return text
        }
      }
      // 递归子节点
      const children = node.children || []
      for (const child of children) {
        if (!child) continue
        // 只递归 VElement 节点；VText/VExpressionContainer 不含按钮
        if (child.type !== 'VElement') continue
        const found = findSubmitButtonText(child)
        if (found) return found
      }
      return null
    }

    /**
     * 在 el-form 子树中找不到提交按钮时，回退到「同 dialog 内
     * 的兄弟节点」：Element Plus 常见写法是把按钮放在
     * <el-dialog> 的 #footer slot 中，作为 el-form 的兄弟节点。
     * 我们在最近的 el-dialog 祖先（若有）中递归查找，但
     * 跳过本 el-form 子树以避免重复遍历。
     */
    function findSiblingSubmitButton(formNode) {
      let cur = formNode.parent
      while (cur) {
        if (cur.type !== 'VElement') {
          cur = cur.parent
          continue
        }
        // 仅在 dialog / drawer 容器中扩大查找范围（避免对裸
        // 表单页面误报：那种页面整页都是按钮，会带来很多 FP）
        if (
          isTag(cur, 'el-dialog', 'ElDialog') ||
          isTag(cur, 'el-drawer', 'ElDrawer')
        ) {
          return findSubmitButtonExcluding(cur, formNode)
        }
        cur = cur.parent
      }
      return null
    }

    function findSubmitButtonExcluding(node, exclude) {
      if (!node || node === exclude) return null
      if (isTag(node, 'el-button', 'ElButton')) {
        const text = extractButtonText(node)
        if (text && SUBMIT_KEYWORD.test(text)) return text
      }
      const children = node.children || []
      for (const child of children) {
        if (!child || child.type !== 'VElement') continue
        if (child === exclude) continue
        const found = findSubmitButtonExcluding(child, exclude)
        if (found) return found
      }
      return null
    }

    // 仅 vue-eslint-parser 解析的 .vue 文件中，parserServices.defineTemplateBodyVisitor
    // 可用；其它情况（普通 .js / .ts）直接返回空 listeners。
    if (
      !context.parserServices ||
      typeof context.parserServices.defineTemplateBodyVisitor !== 'function'
    ) {
      return {}
    }

    return context.parserServices.defineTemplateBodyVisitor({
      VElement(node) {
        if (!isTag(node, 'el-form', 'ElForm')) return
        // 已绑定 :rules → 跳过
        if (hasRulesBinding(node)) return
        // 查找提交类按钮（先 el-form 子树，再 dialog 兄弟节点）
        const submitText =
          findSubmitButtonText(node) || findSiblingSubmitButton(node)
        if (!submitText) return
        context.report({
          node: node.startTag,
          messageId: 'elFormMustHaveRules',
          data: { buttonText: submitText },
        })
      },
    })
  },
}

module.exports = rule
