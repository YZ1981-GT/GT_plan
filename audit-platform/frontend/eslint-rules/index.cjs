// ESLint 自定义规则插件入口
// Plugin name: gt-audit
//
// 注册方式：在 .eslintrc.cjs 中通过 plugins + rules 引入
// 或在 eslint.config.js flat config 中通过 plugins 对象引入

const noAmountWithoutDecimal = require('./no-amount-without-decimal.cjs')
const elFormMustHaveRules = require('./el-form-must-have-rules.cjs')
const noDeleteWithoutConfirm = require('./no-delete-without-confirm.cjs')
const mustWatchRouteOrContext = require('./must-watch-route-or-context.cjs')
const noBareAmountCell = require('./no-bare-amount-cell.cjs')
const noStatusStringLiteral = require('./no-status-string-literal.cjs')
const noEnglishUiText = require('./no-english-ui-text.cjs')
// 既有规则
const noAmountArithmetic = require('./no-amount-arithmetic.cjs')
const noAmountToFixed = require('./no-amount-toFixed.cjs')
const noAmountUnitInScript = require('./no-amount-unit-in-script.cjs')
const noDialogWithoutAppend = require('./no-dialog-without-append.cjs')
// Feature: platform-global-hardening — Wp_Kit 等价手写结构检测
const noAdhocWpStructure = require('./no-adhoc-wp-structure.cjs')
// Feature: platform-global-hardening — 底稿禁止直接调用取数 URL
const noDirectAuditFetch = require('./no-direct-audit-fetch.cjs')

/** @type {import('eslint').ESLint.Plugin} */
const plugin = {
  meta: {
    name: 'eslint-plugin-gt-audit',
    version: '1.0.0',
  },
  rules: {
    // V3 新增 7 条规则
    'no-amount-without-decimal': noAmountWithoutDecimal,
    'el-form-must-have-rules': elFormMustHaveRules,
    'no-delete-without-confirm': noDeleteWithoutConfirm,
    'must-watch-route-or-context': mustWatchRouteOrContext,
    'no-bare-amount-cell': noBareAmountCell,
    'no-status-string-literal': noStatusStringLiteral,
    'no-english-ui-text': noEnglishUiText,
    // 既有规则
    'no-amount-arithmetic': noAmountArithmetic,
    'no-amount-toFixed': noAmountToFixed,
    'no-amount-unit-in-script': noAmountUnitInScript,
    'no-dialog-without-append': noDialogWithoutAppend,
    // Feature: platform-global-hardening — Wp_Kit 等价手写结构检测
    'no-adhoc-wp-structure': noAdhocWpStructure,
    // Feature: platform-global-hardening — 底稿禁止直接调用取数 URL
    'no-direct-audit-fetch': noDirectAuditFetch,
  },
}

module.exports = plugin
