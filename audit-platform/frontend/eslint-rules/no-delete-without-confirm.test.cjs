// 简单逻辑验证 ESLint 规则 no-delete-without-confirm
//
// 运行方式：node eslint-rules/no-delete-without-confirm.test.cjs
// 不依赖 RuleTester：直接构造最小 sourceCode mock，验证 hasConfirmInWindow 逻辑。

const rule = require('./no-delete-without-confirm.cjs')

function createCtx(filename, lines) {
  const reports = []
  return {
    _reports: reports,
    getFilename: () => filename,
    getSourceCode: () => ({
      lines,
      getText: (node) => node._text || 'api.delete',
    }),
    report: (d) => reports.push(d),
  }
}

function makeNode(line, calleeText = 'api.delete', parent = null) {
  return {
    type: 'CallExpression',
    loc: { start: { line }, end: { line } },
    callee: {
      type: 'MemberExpression',
      computed: false,
      property: { type: 'Identifier', name: 'delete' },
      object: { type: 'Identifier', name: calleeText.split('.')[0] },
      _text: calleeText,
    },
    parent,
  }
}

/** 构造一个嵌套在 ArrowFunctionExpression 内的 api.delete 节点 */
function makeNodeInFn(callLine, fnStartLine, calleeText = 'api.delete') {
  const fn = {
    type: 'ArrowFunctionExpression',
    loc: { start: { line: fnStartLine }, end: { line: callLine + 5 } },
    parent: null,
  }
  return makeNode(callLine, calleeText, fn)
}

function run(name, fn) {
  try {
    fn()
    console.log('✓', name)
  } catch (err) {
    console.error('✗', name, err.message)
    process.exitCode = 1
  }
}

run('case 1: api.delete 前 3 行有 confirmDelete → 不报', () => {
  const ctx = createCtx('src/views/X.vue', [
    'async function onDel(row) {',
    '  await confirmDelete(row.name)',
    '  try {',
    '    await api.delete(`/api/x/${row.id}`)',
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNode(4))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 reports, got ${ctx._reports.length}`)
  }
})

run('case 2: api.delete 前 3 行无 confirm → 报', () => {
  const ctx = createCtx('src/views/X.vue', [
    'async function onDel(row) {',
    '  loading.value = true',
    '  try {',
    '    await api.delete(`/api/x/${row.id}`)',
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNode(4))
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 report, got ${ctx._reports.length}`)
  }
  if (ctx._reports[0].messageId !== 'noDeleteWithoutConfirm') {
    throw new Error('wrong messageId')
  }
})

run('case 3: ElMessageBox.confirm 在前 3 行 → 不报', () => {
  const ctx = createCtx('src/components/X.vue', [
    'try {',
    '  await ElMessageBox.confirm("确定删除？", "提示")',
    '  await api.delete("/api/x")',
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNode(3))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0, got ${ctx._reports.length}`)
  }
})

run('case 4: confirmDangerous 也算 confirm → 不报', () => {
  const ctx = createCtx('src/components/X.vue', [
    'await confirmDangerous("...", "title")',
    'try {',
    '  await api.delete("/api/x")',
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNode(3))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0, got ${ctx._reports.length}`)
  }
})

run('case 5: 文件级豁免（services/consolidationApi.ts）→ 不报', () => {
  const ctx = createCtx('/path/src/services/consolidationApi.ts', [
    'export async function delScope(id) {',
    '  return api.delete(`/api/scope/${id}`)',
  ])
  const listeners = rule.create(ctx)
  if (Object.keys(listeners).length !== 0) {
    // 应直接返回空 listeners
    throw new Error('exempt file should return empty listeners')
  }
})

run('case 6: 文件级豁免（composables/useEditingLock.ts）→ 不报', () => {
  const ctx = createCtx('/path/src/composables/useEditingLock.ts', [
    'await api.delete(`/api/lock/${id}`)',
  ])
  const listeners = rule.create(ctx)
  if (Object.keys(listeners).length !== 0) {
    throw new Error('exempt file should return empty listeners')
  }
})

run('case 6b: 任意 services/*.ts 都豁免（commonApi/auditPlatformApi 等）', () => {
  const ctx = createCtx('/path/src/services/auditPlatformApi.ts', [
    'export const deleteX = (id) => api.delete(`/api/x/${id}`)',
  ])
  const listeners = rule.create(ctx)
  if (Object.keys(listeners).length !== 0) {
    throw new Error('all services/*.ts should be exempt')
  }
})

run('case 7: Set.prototype.delete 不被误报', () => {
  const ctx = createCtx('src/utils/X.ts', [
    'const s = new Set()',
    's.delete(item)',
  ])
  const listeners = rule.create(ctx)
  // s 不在 COMMON 集合，不应触发
  const node = {
    type: 'CallExpression',
    loc: { start: { line: 2 }, end: { line: 2 } },
    callee: {
      type: 'MemberExpression',
      computed: false,
      property: { type: 'Identifier', name: 'delete' },
      object: { type: 'Identifier', name: 's' },
      _text: 's.delete',
    },
  }
  listeners.CallExpression(node)
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 (Set.delete should not match), got ${ctx._reports.length}`)
  }
})

run('case 8: httpApi.delete 也被识别', () => {
  const ctx = createCtx('src/views/X.vue', [
    'try {',
    '  await httpApi.delete("/api/x")',
  ])
  const listeners = rule.create(ctx)
  const node = {
    type: 'CallExpression',
    loc: { start: { line: 2 }, end: { line: 2 } },
    callee: {
      type: 'MemberExpression',
      computed: false,
      property: { type: 'Identifier', name: 'delete' },
      object: { type: 'Identifier', name: 'httpApi' },
      _text: 'httpApi.delete',
    },
  }
  listeners.CallExpression(node)
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1, got ${ctx._reports.length}`)
  }
})

run('case 9: 9 行外的 confirm 不算（窗口边界 8 行，无 enclosing fn）', () => {
  const ctx = createCtx('/path/src/views/X.vue', [
    'await confirmDelete()',  // line 1
    'doSomething()',           // 2
    'doSomething()',           // 3
    'doSomething()',           // 4
    'doSomething()',           // 5
    'doSomething()',           // 6
    'doSomething()',           // 7
    'doSomething()',           // 8
    'doSomething()',           // 9
    'await api.delete("/api/x")', // 10
  ])
  const listeners = rule.create(ctx)
  // 不传 parent → 没有 enclosing function，回退到 8 行窗口
  listeners.CallExpression(makeNode(10))
  if (ctx._reports.length !== 1) {
    throw new Error(`expected 1 (confirm out of 8-line window), got ${ctx._reports.length}`)
  }
})

run('case 9b: try/catch 包裹 confirm 模式（4-5 行间距）→ 不报', () => {
  const ctx = createCtx('/path/src/views/X.vue', [
    'const handleDelete = async (row) => {',  // 1
    '  try {',                                 // 2
    '    await confirmDelete(row.name)',       // 3
    '  } catch {',                             // 4
    '    return',                              // 5
    '  }',                                     // 6
    '  try {',                                 // 7
    '    await api.delete(`/api/x/${row.id}`)', // 8
    '  } catch (e) {',                         // 9
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNodeInFn(8, 1))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 (try/catch confirm pattern, fn-scoped), got ${ctx._reports.length}`)
  }
})

run('case 9c: 多行 ElMessageBox.confirm({...}) + api.delete 跨 15+ 行 → 不报（同函数内）', () => {
  const ctx = createCtx('/path/src/views/X.vue', [
    'async function onDelete(row) {',          // 1
    '  try {',                                 // 2
    '    await ElMessageBox.confirm(',         // 3
    '      "确定删除？",',                     // 4
    '      "提示",',                           // 5
    '      {',                                 // 6
    '        confirmButtonText: "删除",',      // 7
    '        cancelButtonText: "取消",',       // 8
    '        type: "warning",',                // 9
    '      },',                                // 10
    '    )',                                   // 11
    '  } catch {',                             // 12
    '    return',                              // 13
    '  }',                                     // 14
    '  try {',                                 // 15
    '    await api.delete(`/api/x/${row.id}`)', // 16
    '  } catch (e) {',                         // 17
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNodeInFn(16, 1))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 (multi-line confirm in same fn), got ${ctx._reports.length}`)
  }
})

run('case 10: 同一行 confirm 也算', () => {
  const ctx = createCtx('src/components/X.vue', [
    'try { await ElMessageBox.confirm("?"); await api.delete("/api/x") } catch {}',
  ])
  const listeners = rule.create(ctx)
  listeners.CallExpression(makeNode(1))
  if (ctx._reports.length !== 0) {
    throw new Error(`expected 0 (same line confirm counts), got ${ctx._reports.length}`)
  }
})

console.log('\nno-delete-without-confirm 单元测试全部通过 ✓')
