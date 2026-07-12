// Feature: platform-global-hardening
// ESLint 自定义规则：检测底稿内直接调用取数 URL 的裸请求
//
// Requirements: Req 5.7 — THE 底稿 SHALL 仅调用 AuditData_SDK 的语义方法，
// 禁止直接拼接取数 URL 或裸传取数参数。
//
// 检测特征（保守策略，低误报）：
//   - 字符串字面量或模板字面量参数中包含：
//     /trial-balance, /tb-balance, /ledger/entries, /aging-config
//   - 调用形式：http.get(...), api.get(...), http.post(...), api.post(...),
//     fetch(...), axios.get(...), axios.post(...)
//   - 仅在 workpaper/ 目录文件中生效
//
// Level: warn（灰度策略，初期不阻断）

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '检测底稿内直接调用取数 URL（trial-balance/tb-balance/ledger/entries/aging-config），建议使用 useAuditData SDK 的语义方法',
      category: 'Best Practices',
      recommended: false,
    },
    messages: {
      useAuditDataSdk:
        '底稿不应直接调用取数 URL，请使用 useAuditData SDK 的语义方法（getTbAmount/getAging/getLedgerEntries）',
    },
    schema: [],
  },

  create(context) {
    const filename = context.getFilename()
    // 仅对底稿相关文件生效（workpaper/ 目录下）
    const isWorkpaperFile = /[/\\]workpaper[/\\]/i.test(filename)
    if (!isWorkpaperFile) return {}

    // 检测的 URL 片段模式（保守，仅关注取数相关路径）
    const FORBIDDEN_PATTERNS = [
      /\/trial-balance/i,
      /\/tb-balance/i,
      /\/ledger\/entries/i,
      /\/aging-config/i,
    ]

    // 检测的调用目标方法名
    const FETCH_METHODS = new Set(['get', 'post', 'put', 'delete', 'patch'])

    /**
     * 检查字符串值是否匹配禁止的取数 URL 模式
     */
    function matchesForbiddenUrl(str) {
      if (!str || typeof str !== 'string') return false
      return FORBIDDEN_PATTERNS.some((re) => re.test(str))
    }

    /**
     * 检查调用表达式是否为 http.get / api.get / axios.get / fetch 等形式
     */
    function isHttpCallExpression(node) {
      if (!node || node.type !== 'CallExpression') return false
      const callee = node.callee

      // fetch('...')
      if (callee.type === 'Identifier' && callee.name === 'fetch') {
        return true
      }

      // http.get(...) / api.get(...) / axios.get(...) / request.get(...)
      if (
        callee.type === 'MemberExpression' &&
        callee.property &&
        callee.property.type === 'Identifier' &&
        FETCH_METHODS.has(callee.property.name)
      ) {
        const obj = callee.object
        if (obj.type === 'Identifier') {
          const name = obj.name.toLowerCase()
          if (
            name === 'http' ||
            name === 'api' ||
            name === 'axios' ||
            name === 'request'
          ) {
            return true
          }
        }
      }

      return false
    }

    /**
     * 从 CallExpression 的参数中提取字符串内容进行匹配
     */
    function checkCallArguments(node) {
      if (!node.arguments || node.arguments.length === 0) return

      const firstArg = node.arguments[0]

      // 字符串字面量: http.get('/api/projects/.../trial-balance')
      if (firstArg.type === 'Literal' && typeof firstArg.value === 'string') {
        if (matchesForbiddenUrl(firstArg.value)) {
          context.report({ node, messageId: 'useAuditDataSdk' })
        }
        return
      }

      // 模板字面量: http.get(`/api/projects/${id}/trial-balance`)
      if (firstArg.type === 'TemplateLiteral') {
        // 检查模板的静态部分
        const quasis = firstArg.quasis || []
        for (const quasi of quasis) {
          const raw = quasi.value && (quasi.value.cooked || quasi.value.raw)
          if (raw && matchesForbiddenUrl(raw)) {
            context.report({ node, messageId: 'useAuditDataSdk' })
            return
          }
        }
      }
    }

    return {
      CallExpression(node) {
        if (isHttpCallExpression(node)) {
          checkCallArguments(node)
        }
      },
    }
  },
}

module.exports = rule
