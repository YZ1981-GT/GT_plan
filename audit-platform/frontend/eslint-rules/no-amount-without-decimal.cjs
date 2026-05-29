// ESLint 自定义规则：检测金额变量使用 Number()/parseFloat() 而非 Decimal
//
// Requirements: Req 2 金额 Decimal 化
//
// 触发条件：检测 `Number(...)` / `parseFloat(...)` 在金额关键字
// （amount/balance/debit/credit）变量上的使用
//
// Level: warn
// Status: 骨架（TODO: 实现检测逻辑）

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        '禁止对金额相关变量使用 Number()/parseFloat()，应使用 Decimal 类型',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      noAmountWithoutDecimal:
        '避免对金额变量「{{ name }}」使用 {{ func }}()。请使用 Decimal 类型处理金额。',
    },
    schema: [],
  },

  create(context) {
    // TODO: 实现检测逻辑
    // - 检测 Number(...) / parseFloat(...) 调用
    // - 判断参数是否为金额相关变量名（amount/balance/debit/credit）
    // - 排除非金额场景（index/count/page 等）
    return {}
  },
}

module.exports = rule
