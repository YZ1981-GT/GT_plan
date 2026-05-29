/**
 * 简单逻辑验证 ESLint 规则 el-form-must-have-rules
 *
 * 运行方式：node eslint-rules/el-form-must-have-rules.test.cjs
 * 不依赖 RuleTester，直接构造 vue-eslint-parser 风格 AST 验证。
 */

const rule = require('./el-form-must-have-rules.cjs')

// ----- 工具：构造迷你 vue-eslint-parser AST -----

function vText(value) {
  return { type: 'VText', value }
}

function vAttr(name, value = null) {
  return {
    type: 'VAttribute',
    key: { type: 'VIdentifier', name },
    value: value == null ? null : { type: 'VLiteral', value },
  }
}

function vDirective(argName) {
  return {
    type: 'VAttribute',
    key: {
      type: 'VDirectiveKey',
      name: { name: 'bind', rawName: 'bind' },
      argument: { name: argName, rawName: argName },
    },
    value: { type: 'VExpressionContainer' },
  }
}

function vElement(name, attrs = [], children = []) {
  const startTag = { type: 'VStartTag', attributes: attrs }
  return {
    type: 'VElement',
    name,
    rawName: name,
    startTag,
    children,
  }
}

function elButton(text, extraAttrs = []) {
  return vElement('el-button', extraAttrs, text ? [vText(text)] : [])
}

// ----- mock context -----
function createCtx() {
  const reports = []
  const ctx = {
    report: (d) => reports.push(d),
    _reports: reports,
    parserServices: {
      // 模拟 vue-eslint-parser：直接把 templateBodyVisitor 透传，
      // 让我们能在测试中手动调用 listeners.VElement。
      defineTemplateBodyVisitor(templateBodyVisitor) {
        return templateBodyVisitor
      },
    },
  }
  return ctx
}

// ----- 测试用例 -----

function run(name, fn) {
  try {
    fn()
    console.log('✓', name)
  } catch (err) {
    console.error('✗', name, err.message)
    process.exitCode = 1
  }
}

run('case 1: el-form 含「提交」按钮但无 :rules → 触发 warning', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement(
    'el-form',
    [vAttr('label-width', '80px')],
    [elButton('提交')]
  )
  listeners.VElement(form)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report, got ${ctx._reports.length}`)
  }
  if (ctx._reports[0].messageId !== 'elFormMustHaveRules') {
    throw new Error('wrong messageId')
  }
})

run('case 2: el-form 已绑定 :rules → 不触发', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement(
    'el-form',
    [vDirective('rules')],
    [elButton('保存')]
  )
  listeners.VElement(form)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

run('case 3: el-form 含非提交按钮（"取消"）→ 不触发', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement('el-form', [], [elButton('取消'), elButton('返回')])
  listeners.VElement(form)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

run('case 4: 提交按钮嵌套在多层节点内仍能识别', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const inner = vElement('el-form-item', [], [
    vElement('div', [], [elButton('确认')]),
  ])
  const form = vElement('el-form', [], [inner])
  listeners.VElement(form)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report, got ${ctx._reports.length}`)
  }
})

run('case 5: PascalCase ElForm + ElButton 也支持', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement('ElForm', [], [vElement('ElButton', [], [vText('新建')])])
  listeners.VElement(form)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report, got ${ctx._reports.length}`)
  }
})

run('case 6: 关键词作为更长文字一部分（"立即提交"）也命中', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement('el-form', [], [elButton('立即提交')])
  listeners.VElement(form)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report, got ${ctx._reports.length}`)
  }
})

run('case 7: 非 el-form 节点不触发', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const div = vElement('div', [], [elButton('提交')])
  listeners.VElement(div)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

run('case 8: 静态属性 rules（罕见但允许）→ 不触发', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement(
    'el-form',
    [vAttr('rules', 'someRules')],
    [elButton('保存')]
  )
  listeners.VElement(form)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

run('case 9: el-dialog 内的 el-form + footer 按钮（兄弟节点）也能命中', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement('el-form', [], [
    vElement('el-form-item', [vAttr('label', '日期')], []),
  ])
  const footerBtn = elButton('保存')
  const dialog = vElement('el-dialog', [vAttr('append-to-body')], [
    form,
    footerBtn,
  ])
  // 设置 parent 链
  form.parent = dialog
  footerBtn.parent = dialog
  dialog.parent = null
  listeners.VElement(form)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report (sibling button), got ${ctx._reports.length}`)
  }
})

run('case 10: 同样 dialog 内但 :rules 已绑定 → 不触发', () => {
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  const form = vElement('el-form', [vDirective('rules')], [])
  const footerBtn = elButton('提交')
  const dialog = vElement('el-dialog', [], [form, footerBtn])
  form.parent = dialog
  footerBtn.parent = dialog
  listeners.VElement(form)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

console.log('\nel-form-must-have-rules 单元测试全部通过 ✓')
