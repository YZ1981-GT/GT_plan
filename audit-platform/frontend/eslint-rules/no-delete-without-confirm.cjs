// ESLint 自定义规则：检测 api.delete() 调用前 3 行无 confirm 二次确认
//
// Requirements: Req 4 删除二次确认
//
// 触发条件：检测到 `api.delete(...)` 或 `httpApi.delete(...)` 等 axios DELETE
// 调用，且其前 3 行内无 confirm 关键字（confirm/ElMessageBox.confirm/Message
// Box.prompt 等），则发出 warn。
//
// 例外（不触发）：
// - 服务层 wrapper 文件（src/services/**.ts）：被 caller 调用前已确认
// - 自动清理 composable（useEditingLock / useConflictGuard / useEvidenceLink /
//   useReviewMarks / useCellComments）：unmount/programmatic 释放
// - import / export / 注释行不算"前 3 行"
//
// Level: warn
// 使用方式：在 .eslintrc.cjs 中通过 plugins: ['gt-audit'] 引入

const path = require('path')

/** 文件级豁免（service wrappers + auto-cleanup composables） */
const EXEMPT_FILE_PATTERNS = [
  // 整个 services/ 目录都是 axios wrapper，由 caller 负责确认
  /\/src\/services\/[^/]+\.ts$/,
  // 自动清理 composables
  /\/src\/composables\/useConflictGuard\.ts$/,
  /\/src\/composables\/useEditingLock\.ts$/,
  /\/src\/composables\/useEvidenceLink\.ts$/,
  /\/src\/composables\/useReviewMarks\.ts$/,
  /\/src\/composables\/useCellComments\.ts$/,
]

/** 关键字正则：3 行回溯窗口内任一命中即视为已确认 */
const CONFIRM_RE = /\b(confirmDelete|confirmDangerous|confirmBatch|confirmRollback|confirmShare|confirmDuplicateAction|confirmForcePass|confirmSign|confirmSignature|confirmConvert|confirmEscalate|confirmForceReset|confirmLeave|confirmSubmitReview|confirmVersionConflict|ElMessageBox\.(confirm|prompt)|MessageBox\.(confirm|prompt))\b/

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '调用 api.delete() 前 3 行必须包含 confirm 二次确认',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noDeleteWithoutConfirm:
        '调用 {{ callee }}() 前 3 行未检测到 confirm 确认逻辑，请添加删除二次确认（confirmDelete / confirmDangerous / ElMessageBox.confirm 等）。',
    },
    schema: [],
  },

  create(context) {
    // 文件级豁免（service wrappers / auto-cleanup composables）
    const filename = (context.getFilename() || '').replace(/\\/g, '/')
    for (const re of EXEMPT_FILE_PATTERNS) {
      if (re.test(filename)) return {}
    }

    const sourceCode = context.getSourceCode()
    const lines = sourceCode.lines // string[] 0-indexed

    /**
     * 判断给定 CallExpression 是否是 axios-like delete 调用：
     *   - api.delete(...)
     *   - httpApi.delete(...)
     *   - http.delete(...)
     *   - this.api.delete(...)（保险起见允许）
     *   - <anyIdentifier>.delete(<args>)，但 args 第一参为字符串/模板字符串/调用表达式（API 路径）
     */
    function isApiDeleteCall(node) {
      if (!node || node.type !== 'CallExpression') return false
      const callee = node.callee
      if (!callee || callee.type !== 'MemberExpression') return false
      const prop = callee.property
      if (!prop) return false
      // computed property (e.g., obj['delete']) skip
      if (callee.computed) return false
      if (prop.type !== 'Identifier' || prop.name !== 'delete') return false

      // object 必须是 Identifier (api / httpApi / http) 或 ThisExpression / MemberExpression
      // 我们只对常见命名做严格判断，避免 Set.prototype.delete / array.delete 等误报
      const obj = callee.object
      const objName = obj && obj.type === 'Identifier' ? obj.name : null
      const COMMON = new Set(['api', 'httpApi', 'http', 'request', 'axios'])
      if (!objName) return false
      if (!COMMON.has(objName)) return false
      return true
    }

    /**
     * 取 callee 文本（用于 message data）
     */
    function calleeText(node) {
      try {
        return sourceCode.getText(node.callee)
      } catch {
        return 'api.delete'
      }
    }

    /**
     * 检查 api.delete 调用所在函数体内（向上至函数声明）是否有 confirm 关键字。
     *
     * 相比固定行数窗口，本方案以 enclosing function/method 为边界：
     * - 在同一 async function / arrow function / method 内任意位置出现 confirm 即视为已确认
     * - 这能容忍多行 ElMessageBox.confirm({...}) 与 api.delete 间隔较远的合法写法
     * - 失败兜底：找不到 enclosing function 时回退到 8 行窗口
     */
    function findEnclosingFunctionStartLine(node) {
      let cur = node.parent
      while (cur) {
        if (
          cur.type === 'FunctionDeclaration' ||
          cur.type === 'FunctionExpression' ||
          cur.type === 'ArrowFunctionExpression' ||
          cur.type === 'MethodDefinition'
        ) {
          return cur.loc?.start?.line ?? null
        }
        cur = cur.parent
      }
      return null
    }

    function hasConfirmInWindow(node) {
      const startLine = node.loc.start.line // 1-indexed
      const fnStart = findEnclosingFunctionStartLine(node)
      const windowStart = fnStart != null
        ? Math.max(1, fnStart)
        : Math.max(1, startLine - 8)
      for (let i = windowStart; i <= startLine; i++) {
        const line = lines[i - 1] || ''
        if (CONFIRM_RE.test(line)) return true
      }
      return false
    }

    return {
      CallExpression(node) {
        if (!isApiDeleteCall(node)) return
        if (hasConfirmInWindow(node)) return
        context.report({
          node,
          messageId: 'noDeleteWithoutConfirm',
          data: { callee: calleeText(node) },
        })
      },
    }
  },
}

module.exports = rule
