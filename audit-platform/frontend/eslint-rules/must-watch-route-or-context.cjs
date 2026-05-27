// ESLint 自定义规则：检测 onMounted 内 fetch year-related 数据但缺
// watch(route.query.year) / useAuditContext().onContextChange 守卫
//
// Requirements: V3 Req 5 路由参数变化响应
//
// 触发条件：
//   1) 同一 onMounted 回调 body 内同时出现：
//        - 数据获取调用：函数名命中 /^(fetch|load|get|refresh|reload|init|sync|query|list)/i
//          或 `api.X` / `httpApi.X` / `xxxApi.X` 形式
//          或 `xxxStore.fetch|load|init|refresh|reload|sync` 形式
//        - year 引用：标识符 `year` / `selectedYear` / `currentYear` / `routeYear` 等
//          或 MemberExpression 末段为 `.year`（如 `route.query.year` / `projectStore.year`）
//   2) 整个文件内**未**同时存在以下任一守卫：
//        - watch(年度引用 / `() => route.query.year` / `() => route.query` / 数组形式 / `year.value`, ...)
//        - 任意位置调用 `onContextChange(...)`（无论是 `useAuditContext().onContextChange()`
//          还是 `const { onContextChange } = useAuditContext()` 后顶层调用）
//
// 命中后给出 warning 提示，引导开发者补 watch 或 useAuditContext.onContextChange。
//
// Level: warn（baseline 模式：只减不增）
//
// 注：本规则只读取 <script setup> AST（vue-eslint-parser 默认 visitor 即可），
// 不需要 defineTemplateBodyVisitor。

const FETCH_NAME_RE = /^(fetch|load|refresh|reload|init|sync|query|list|get)/i
const API_OBJ_RE = /^(api|httpApi|http|axios|request)$/
const API_OBJ_SUFFIX_RE = /Api$/        // workpaperApi / consolidationApi …
const STORE_OBJ_SUFFIX_RE = /Store$/    // projectStore / dictStore …
const STORE_FETCH_RE = /^(fetch|load|init|refresh|reload|sync|update|ensure)/i

const YEAR_IDENT_RE = /^(year|currentYear|selectedYear|routeYear|fiscalYear|targetYear|reportYear|auditYear)$/

/** 返回 true 表示这个 CallExpression 看起来是数据获取/加载/初始化调用 */
function callIsFetchLike(node) {
  if (!node || node.type !== 'CallExpression') return false
  const callee = node.callee
  if (!callee) return false
  // foo() — Identifier callee
  if (callee.type === 'Identifier') {
    return FETCH_NAME_RE.test(callee.name)
  }
  // obj.method() — MemberExpression callee
  if (callee.type === 'MemberExpression' && !callee.computed) {
    const prop = callee.property
    if (!prop || prop.type !== 'Identifier') return false
    // 命中常见 fetch/load/get/init 方法名
    if (FETCH_NAME_RE.test(prop.name)) return true
    const obj = callee.object
    if (!obj) return false
    // api.X / httpApi.X / axios.X / xxxApi.X
    if (obj.type === 'Identifier') {
      if (API_OBJ_RE.test(obj.name) || API_OBJ_SUFFIX_RE.test(obj.name)) return true
      // xxxStore.fetch|load|init|...
      if (STORE_OBJ_SUFFIX_RE.test(obj.name) && STORE_FETCH_RE.test(prop.name)) return true
    }
  }
  return false
}

/** 返回 true 表示节点本身就是 year 引用（identifier 或 MemberExpression 末段为 .year） */
function isYearReferenceNode(node) {
  if (!node) return false
  if (node.type === 'Identifier') {
    return YEAR_IDENT_RE.test(node.name)
  }
  if (node.type === 'MemberExpression' && !node.computed) {
    const prop = node.property
    if (prop && prop.type === 'Identifier' && prop.name === 'year') return true
  }
  return false
}

/** 自定义递归 walker（不依赖 estree-walker），跳过 parent/loc/range */
function walk(node, visit) {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return
  visit(node)
  for (const key of Object.keys(node)) {
    if (key === 'parent' || key === 'loc' || key === 'range' || key === 'start' || key === 'end') continue
    const child = node[key]
    if (Array.isArray(child)) {
      for (const c of child) {
        if (c && typeof c === 'object' && typeof c.type === 'string') walk(c, visit)
      }
    } else if (child && typeof child === 'object' && typeof child.type === 'string') {
      walk(child, visit)
    }
  }
}

function isOnMountedCall(node) {
  if (!node || node.type !== 'CallExpression') return false
  if (!node.callee || node.callee.type !== 'Identifier' || node.callee.name !== 'onMounted') return false
  if (!node.arguments || node.arguments.length < 1) return false
  const first = node.arguments[0]
  return first && (first.type === 'ArrowFunctionExpression' || first.type === 'FunctionExpression')
}

/** 取 onMounted 回调的函数体节点（BlockStatement 或表达式） */
function getOnMountedBody(node) {
  return node.arguments[0].body
}

/** 判定 watch 第一参数是否是 year-shape */
function watchFirstArgIsYearShape(arg) {
  if (!arg) return false
  // watch(year, ...)
  if (isYearReferenceNode(arg)) return true
  // watch(() => year, ...) / watch(() => year.value, ...) / watch(() => route.query.year, ...) / watch(() => route.query, ...)
  if (arg.type === 'ArrowFunctionExpression' || arg.type === 'FunctionExpression') {
    let body = arg.body
    if (body && body.type === 'BlockStatement') {
      // 单 return 形式：() => { return X }
      const stmts = body.body || []
      if (stmts.length === 1 && stmts[0].type === 'ReturnStatement') {
        body = stmts[0].argument
      } else {
        return false
      }
    }
    if (!body) return false
    if (isYearReferenceNode(body)) return true
    // route.query  /  xxx.query（覆盖所有路由 query 监听）
    if (body.type === 'MemberExpression' && !body.computed && body.property?.type === 'Identifier' && body.property.name === 'query') {
      return true
    }
    // year.value / currentYear.value
    if (body.type === 'MemberExpression' && body.object && isYearReferenceNode(body.object)) return true
    return false
  }
  // 数组形式：watch([year, () => route.query.year, ...], ...)
  if (arg.type === 'ArrayExpression') {
    return (arg.elements || []).some((el) => el && watchFirstArgIsYearShape(el))
  }
  return false
}

function isWatchCall(node) {
  if (!node || node.type !== 'CallExpression') return false
  if (!node.callee || node.callee.type !== 'Identifier') return false
  if (node.callee.name !== 'watch' && node.callee.name !== 'watchEffect') return false
  if (!node.arguments || node.arguments.length < 1) return false
  return true
}

function isOnContextChangeCall(node) {
  if (!node || node.type !== 'CallExpression') return false
  const callee = node.callee
  if (!callee) return false
  // onContextChange(...)
  if (callee.type === 'Identifier' && callee.name === 'onContextChange') return true
  // ctx.onContextChange(...) / useAuditContext().onContextChange(...)
  if (
    callee.type === 'MemberExpression' &&
    !callee.computed &&
    callee.property &&
    callee.property.type === 'Identifier' &&
    callee.property.name === 'onContextChange'
  ) {
    return true
  }
  return false
}

/** @type {import('eslint').Rule.RuleModule} */
const rule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'onMounted 内含 year 相关数据获取时，文件须同时存在 watch(route.query/year) 或 useAuditContext().onContextChange',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      mustWatchRouteOrContext:
        'onMounted 内含 year 相关数据获取，但未检测到 watch(route.query) 或 useAuditContext().onContextChange，年度切换时数据不会刷新。',
    },
    schema: [],
  },

  create(context) {
    return {
      Program(programNode) {
        const offenders = []  // onMounted CallExpression nodes that need a guard
        let hasGuard = false  // 任一 watch year-shape 或 onContextChange 调用

        walk(programNode, (n) => {
          // 1) 检测 onMounted body 内是否同时出现 fetch + year
          if (isOnMountedCall(n)) {
            const body = getOnMountedBody(n)
            if (body) {
              let hasFetch = false
              let hasYear = false
              walk(body, (m) => {
                if (!hasFetch && callIsFetchLike(m)) hasFetch = true
                if (!hasYear && isYearReferenceNode(m)) hasYear = true
              })
              if (hasFetch && hasYear) offenders.push(n)
            }
          }
          // 2) 任意 watch(year-shape) 视为已加守卫
          if (isWatchCall(n) && watchFirstArgIsYearShape(n.arguments[0])) {
            hasGuard = true
          }
          // 3) 任意 onContextChange(...) 视为已加守卫
          if (isOnContextChangeCall(n)) {
            hasGuard = true
          }
        })

        if (hasGuard) return
        for (const offender of offenders) {
          context.report({
            node: offender.callee,
            messageId: 'mustWatchRouteOrContext',
          })
        }
      },
    }
  },
}

module.exports = rule
// 导出内部函数以便单测
module.exports._internal = {
  callIsFetchLike,
  isYearReferenceNode,
  isOnMountedCall,
  isWatchCall,
  isOnContextChangeCall,
  watchFirstArgIsYearShape,
  walk,
}
