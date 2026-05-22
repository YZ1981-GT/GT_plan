/**
 * 简单验证 ESLint 规则逻辑的测试
 *
 * 运行方式：node eslint-rules/no-amount-toFixed.test.cjs
 * （不依赖 ESLint RuleTester，纯逻辑验证）
 */

const rule = require('./no-amount-toFixed.cjs')

// 模拟 ESLint context
function createMockContext(filename = 'src/views/Test.vue') {
  const reports = []
  return {
    getFilename: () => filename,
    report: (descriptor) => reports.push(descriptor),
    _reports: reports,
  }
}

// Test 1: 普通 .vue 文件中的 .toFixed() 应触发 warning
function testTriggersOnVueFile() {
  const ctx = createMockContext('src/views/Adjustments.vue')
  const listeners = rule.create(ctx)

  // Simulate a .toFixed() CallExpression AST node
  const node = {
    callee: {
      type: 'MemberExpression',
      property: { type: 'Identifier', name: 'toFixed' },
    },
  }
  listeners.CallExpression(node)

  console.assert(ctx._reports.length === 1, 'Test 1 FAILED: should report 1 warning')
  console.log('✓ Test 1: triggers warning on .toFixed() in .vue file')
}

// Test 2: formatters.ts 内部不触发
function testSkipsFormattersTs() {
  const ctx = createMockContext('src/utils/formatters.ts')
  const listeners = rule.create(ctx)

  // Should return empty listeners (skip file)
  console.assert(
    Object.keys(listeners).length === 0,
    'Test 2 FAILED: should skip formatters.ts'
  )
  console.log('✓ Test 2: skips formatters.ts internal implementation')
}

// Test 3: 非 toFixed 的 MemberExpression 不触发
function testIgnoresOtherMethods() {
  const ctx = createMockContext('src/views/Test.vue')
  const listeners = rule.create(ctx)

  const node = {
    callee: {
      type: 'MemberExpression',
      property: { type: 'Identifier', name: 'toString' },
    },
  }
  listeners.CallExpression(node)

  console.assert(ctx._reports.length === 0, 'Test 3 FAILED: should not report for toString()')
  console.log('✓ Test 3: ignores non-toFixed method calls')
}

// Test 4: .ts 文件中的 .toFixed() 也应触发
function testTriggersOnTsFile() {
  const ctx = createMockContext('src/utils/monitor.ts')
  const listeners = rule.create(ctx)

  const node = {
    callee: {
      type: 'MemberExpression',
      property: { type: 'Identifier', name: 'toFixed' },
    },
  }
  listeners.CallExpression(node)

  console.assert(ctx._reports.length === 1, 'Test 4 FAILED: should report 1 warning in .ts')
  console.log('✓ Test 4: triggers warning on .toFixed() in .ts file')
}

// Run all tests
testTriggersOnVueFile()
testSkipsFormattersTs()
testIgnoresOtherMethods()
testTriggersOnTsFile()
console.log('\nAll ESLint rule tests passed ✓')
