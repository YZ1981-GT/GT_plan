// 简单逻辑验证 ESLint 规则 must-watch-route-or-context
//
// 运行方式：node eslint-rules/must-watch-route-or-context.test.cjs
//
// 用 espree 直接解析 JS 字符串构造 AST（无 vue 模板需要），
// 模拟 <script setup> 体顶层结构。

const espree = require('espree')
const rule = require('./must-watch-route-or-context.cjs')

function parse(code) {
  return espree.parse(code, {
    ecmaVersion: 'latest',
    sourceType: 'module',
    loc: true,
    range: true,
  })
}

function setParents(node, parent) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return
  Object.defineProperty(node, 'parent', { value: parent, configurable: true, writable: true, enumerable: false })
  for (const key of Object.keys(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range' || key === 'start' || key === 'end') continue
    const child = node[key]
    if (Array.isArray(child)) {
      for (const c of child) setParents(c, node)
    } else if (child && typeof child === 'object' && typeof child.type === 'string') {
      setParents(child, node)
    }
  }
}

function createCtx() {
  const reports = []
  return {
    _reports: reports,
    report: (d) => reports.push(d),
    getFilename: () => 'test.vue',
    getSourceCode: () => ({ lines: [] }),
  }
}

function runRule(code) {
  const ast = parse(code)
  setParents(ast, null)
  const ctx = createCtx()
  const listeners = rule.create(ctx)
  if (typeof listeners.Program === 'function') {
    listeners.Program(ast)
  }
  return ctx._reports
}

function expect(reports, n) {
  if (reports.length !== n) {
    throw new Error('expected ' + n + ', got ' + reports.length)
  }
}

function run(name, fn) {
  try {
    fn()
    console.log('OK ', name)
  } catch (err) {
    console.error('FAIL', name, err.message)
    process.exitCode = 1
  }
}

// ─── 应触发（onMounted 含 year fetch + 无任何守卫） ─────────────

run('case 1: onMounted 内 fetchData 含 year，无 watch/onContextChange → 触发', () => {
  const code = `
    import { onMounted } from 'vue'
    const route = useRoute()
    const year = computed(() => Number(route.query.year) || 2025)
    onMounted(async () => {
      await fetchData(projectId.value, year.value)
    })
  `
  const reports = runRule(code)
  expect(reports, 1)
  if (reports[0].messageId !== 'mustWatchRouteOrContext') throw new Error('wrong messageId')
})

run('case 2: onMounted 内 api.getMateriality + route.query.year 引用 → 触发', () => {
  const code = `
    onMounted(async () => {
      await api.getMateriality(projectId.value, route.query.year)
    })
  `
  expect(runRule(code), 1)
})

run('case 3: onMounted 内 store.fetch + currentYear → 触发', () => {
  const code = `
    onMounted(async () => {
      await projectStore.fetchSomething({ year: currentYear.value })
    })
  `
  expect(runRule(code), 1)
})

// ─── 不应触发（已有守卫） ──────────────────────────────────────

run('case 4: 同文件存在 onContextChange 调用 → 不触发', () => {
  const code = `
    const { onContextChange } = useAuditContext()
    onMounted(async () => {
      await fetchData(year.value)
    })
    onContextChange(() => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 5: useAuditContext().onContextChange(...) 链式调用 → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchData(year.value)
    })
    useAuditContext().onContextChange(() => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 6: watch(() => route.query.year, ...) → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchData(year.value)
    })
    watch(() => route.query.year, () => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 7: watch(() => route.query, ...) 整体监听 → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchData(year.value)
    })
    watch(() => route.query, () => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 8: watch(year, ...) 直接 ref → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchData(year.value)
    })
    watch(year, () => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 9: watch([projectId, () => route.query.year], ...) 数组形式 → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchData(year.value)
    })
    watch([projectId, () => route.query.year], () => fetchData(year.value))
  `
  expect(runRule(code), 0)
})

run('case 10: watch(selectedYear, ...) → 不触发', () => {
  const code = `
    const selectedYear = ref(2025)
    onMounted(async () => {
      await loadAll(selectedYear.value)
    })
    watch(selectedYear, loadAll)
  `
  expect(runRule(code), 0)
})

// ─── 边界 / 不应触发（无 year 或无 fetch） ──────────────────────

run('case 11: onMounted 内无 fetch 调用 → 不触发', () => {
  const code = `
    onMounted(() => {
      console.log('mounted', year.value)
    })
  `
  expect(runRule(code), 0)
})

run('case 12: onMounted 内 fetch 但无 year 引用 → 不触发', () => {
  const code = `
    onMounted(async () => {
      await fetchUserList()
    })
  `
  expect(runRule(code), 0)
})

run('case 13: 无 onMounted → 不触发', () => {
  const code = `
    const year = computed(() => 2025)
    const x = api.fetch()
  `
  expect(runRule(code), 0)
})

// ─── 多 onMounted / 嵌套调用 ────────────────────────────────────

run('case 14: 两个 onMounted 一个 year + 文件存在 onContextChange → 不报', () => {
  const code = `
    onMounted(() => fetchData(year.value))
    onMounted(() => fetchOther())
    onContextChange(() => {})
  `
  expect(runRule(code), 0)
})

run('case 15: onMounted 内 Promise.all([fetchA(), fetchB(year)]) → 触发', () => {
  const code = `
    onMounted(async () => {
      await Promise.all([fetchA(), fetchB(year.value)])
    })
  `
  expect(runRule(code), 1)
})

run('case 16: project.year 命名（MemberExpression .year）也算 year ref', () => {
  const code = `
    onMounted(async () => {
      await fetchData(project.year)
    })
  `
  expect(runRule(code), 1)
})

console.log('')
console.log('must-watch-route-or-context 单元测试全部通过')
