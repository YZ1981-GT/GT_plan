/**
 * 建议分配表组件与裁剪页接线守卫（源码级，零 mount）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 18
 * 被测: `../GtDelegationSuggestionTable.vue` + `views/ProcedureTrimming.vue` 的接线
 * _Requirements: 11.1, 11.6, 11.8_
 *
 * ## 本文件防的三类缺陷（全部在本轮落地时真实踩到）
 *
 * | # | 缺陷 | 表现 | 四层检查 |
 * |---|---|---|---|
 * | 1 | 拿 `wp_id` 填 `wp_index_ids` | 后端 `_resolve_targets` 用 `ProcedureRowTask.wp_index_id.in_(...)` ⇒ **静默匹配不到任何目标**，UI 显示「0 张待应用」而非报错 | 全绿 |
 * | 2 | 负载未知补 0 | 0 被算法与看板同时读成「这个人很空闲」⇒ 工作全堆给数据缺失的那个人 | 全绿 |
 * | 3 | 组件自己发请求 | 绕开既有 preview → apply 两阶段与 `request_id` 幂等 = 第二套写入路径 | 全绿 |
 *
 * 本轮另外真实踩到并已修的四个**只有挂载才暴露**的接线缺陷（故本文件有对应判据）：
 * 模板绑 `suggestMembers` 而声明是 `suggestionMembers`、模板调 `generateSuggestion`
 * 而声明是 `openSuggestionPanel`、宿主传 `:result` 而组件 prop 是 `suggestion`、
 * 以及**重复 import 同一批符号**（重复顶层声明会让 Vite transform 直接失败，
 * `get_diagnostics` 查不出）。这四个 Volar / vitest / `get_diagnostics` 全绿。
 *
 * ## 判据一律落结构、且先 stripComments
 *
 * 组件与宿主的注释里**刻意保留**了 `wp_id` / `ROLE_PRIORITY` / `preview` / `apply`
 * 等字样以记录「为何不那样做」。任何「全文不含 X」的判据若不剥注释就会**误红**
 * —— 那是守卫缺陷不是代码缺陷。
 *
 * helper（`repoRoot` / `read` / `fnBody` / `stripComments`）照抄
 * `views/__tests__/trimDecisionWiring.spec.ts`（Task 13 已用变异检验验证过承重性）。
 * 刻意不抽公共模块：守卫 helper 一旦共享，改它就会同时改变多个守卫的判据面。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ═══════════════════════════════════════════════════════════════════════════
// helper 五件套（照抄 trimDecisionWiring.spec.ts）
// ═══════════════════════════════════════════════════════════════════════════

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')
const P_COMP = path.join(FE, 'components', 'workpaper', 'delegation', 'GtDelegationSuggestionTable.vue')
const P_TRIM = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_SENIORITY = path.join(FE, 'components', 'workpaper', 'composables', 'delegationSeniority.ts')
const P_COMMON_API = path.join(FE, 'services', 'commonApi.ts')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 截具名函数体（花括号配对）。
 *
 * 🔴 两条踩过的坑，勿"简化"回去：
 *
 * 1. **不能用「声明后第一个 `{`」定位** —— 那个 `{` 可能是参数的内联类型字面量
 *    （`function f(p: { k: string })`）或内联返回类型注解（`): Promise<{ a: X }> {`），
 *    截出来的"函数体"其实是那段类型，后续断言全落在无关文本上。
 * 2. **更不能用「块内含 return/const/if 等语句特征」筛选**（平台既有守卫的旧写法）
 *    —— 本轮实测被它咬到：`function removeRow(i) { rows.value.splice(i, 1);
 *    emitChange() }` 的函数体**只有表达式语句、一个关键字都没有** ⇒ 该筛选跳过
 *    真正的函数体，一路命中下一个无关块（实测命中了 `loadBoard` computed 的体），
 *    断言随即在错误文本上求值并**假红**。这正是「守卫红了也不能直接信」的实例：
 *    先分清 ANCHOR-MISS（脚本缺陷）与 RED（代码缺陷）。
 *
 * 正解 = 先按圆括号配对跳过**参数列表**，再按 `<>` / `{}` / `[]` 深度跳过**返回
 * 类型注解**，取第一个各深度均为 0 的 `{` 作函数体起点。与块内有无关键字无关。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let i = src.indexOf('(', m.index + m[0].length)
  if (i < 0) return ''
  // ① 跳过参数列表（圆括号配对）
  let paren = 0
  for (; i < src.length; i += 1) {
    if (src[i] === '(') paren += 1
    else if (src[i] === ')') {
      paren -= 1
      if (paren === 0) { i += 1; break }
    }
  }
  if (paren !== 0) return ''
  // ② 跳过返回类型注解：取各深度均为 0 的第一个 `{`
  let angle = 0
  let bracket = 0
  let brace = 0
  let start = -1
  for (; i < src.length; i += 1) {
    const c = src[i]
    if (c === '<') angle += 1
    else if (c === '>') { if (angle > 0) angle -= 1 }
    else if (c === '[') bracket += 1
    else if (c === ']') { if (bracket > 0) bracket -= 1 }
    else if (c === '{') {
      if (angle === 0 && bracket === 0 && brace === 0) { start = i; break }
      brace += 1
    } else if (c === '}') { if (brace > 0) brace -= 1 }
  }
  if (start < 0) return ''
  // ③ 函数体花括号配对
  let depth = 0
  for (let j = start; j < src.length; j += 1) {
    if (src[j] === '{') depth += 1
    else if (src[j] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(start, j + 1)
    }
  }
  return ''
}

/**
 * 截 `const {name} = computed(...)` 的整个实参区（圆括号配对）。
 *
 * 🔴 必须容忍**显式类型实参**：`computed<DelegationApplyGroup[]>(...)` /
 * `computed<Record<string, any>>(...)` 都是本仓库真实写法，而朴素正则
 * `computed\s*\(` 对它们**零命中** ⇒ 判据以「未找到 computed」的形态**假红**
 * （本轮实测踩到 3 条）。故先按 `<>` 深度跳过类型实参再定位 `(`。
 *
 * 不复用 `fnBody`：computed 有花括号体与**表达式体**两形态，后者第一个 `{` 是
 * 对象字面量而非函数体；圆括号配对对两形态都成立。
 */
function computedArg(src: string, name: string): string {
  const decl = new RegExp(`const\\s+${name}\\s*=\\s*computed\\b`)
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let i = m.index + m[0].length
  while (i < src.length && /\s/.test(src[i])) i += 1
  if (src[i] === '<') {
    let angle = 0
    for (; i < src.length; i += 1) {
      if (src[i] === '<') angle += 1
      else if (src[i] === '>') {
        angle -= 1
        if (angle === 0) { i += 1; break }
      }
    }
  }
  const open = src.indexOf('(', i)
  if (open < 0) return ''
  let depth = 0
  for (let j = open; j < src.length; j += 1) {
    if (src[j] === '(') depth += 1
    else if (src[j] === ')') {
      depth -= 1
      if (depth === 0) return src.slice(open, j + 1)
    }
  }
  return ''
}

function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

/** SFC 三段切分（`</template>` 取 `<script setup` 之前的**最后一个**）。 */
function sfcSegments(clean: string): { template: string; script: string } {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(tplStart, '未找到 <template>').toBeGreaterThanOrEqual(0)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(tplStart)
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  return { template: clean.slice(tplStart, tplEnd), script: clean.slice(scStart, scEnd) }
}

const COMP_RAW = read(P_COMP)
const COMP = stripComments(COMP_RAW)
const COMP_SEG = sfcSegments(COMP)
const TRIM = stripComments(read(P_TRIM))
const TRIM_SEG = sfcSegments(TRIM)

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检（防判据空转 / 误红）
// ═══════════════════════════════════════════════════════════════════════════

describe('helper 自检', () => {
  it('stripComments 剥注释、保留字符串字面量', () => {
    const s = stripComments(`const a = 'wp_index_id' // 注释里写 wp_id\n/* 块里写 wp_id */`)
    expect(s).toContain("'wp_index_id'")
    expect(s).not.toContain('注释里写')
    expect(s).not.toContain('块里写')
  })

  it('stripComments 不把 accept="image/*" 当块注释起点', () => {
    expect(stripComments(`<input accept="image/*" />\nconst x = 1`)).toContain('const x = 1')
  })

  it('fnBody 跳过内联返回类型注解', () => {
    const fx = 'async function f(): Promise<{\n a: X\n}> {\n  const y = 1\n  return y\n}'
    expect(fnBody(fx, /async\s+function\s+f\b/)).toContain('const y = 1')
  })

  // 🔴 本轮实测踩到的守卫缺陷 1：`fnBody` 原按「块内含 return/const/let/await/if/for/throw」
  //    筛函数体。但**只含表达式语句**的函数体（`emitApply` 只有一行 `emit(...)`、
  //    `removeRow` 只有 `splice` + `emitChange()`）不含任何这类关键字 ⇒ 被跳过，
  //    helper 继续往下找，最终把**另一个无关函数**的体返回。表现是断言在无关文本上
  //    求值：`removeRow 未真的删行: expected '{ const increments = new Map…'`（那是
  //    `loadBoard` 的体）。这种失败极易被误读成「代码没实现」而去改正确的代码。
  it('fnBody 能截到只含表达式语句的函数体（不被"含语句关键字"筛掉）', () => {
    const fx = 'function emitApply() {\n  emit("apply", groups.value)\n}'
    const body = fnBody(fx, /function\s+emitApply\b/)
    expect(body, '只含表达式语句的函数体被跳过了').toContain('emit("apply"')
  })

  it('fnBody 对紧邻的两个函数不串体（截到的是第一个的体）', () => {
    const fx = [
      'function a() {',
      '  doA()',
      '}',
      'function b() {',
      '  const zzz = 1',
      '}',
    ].join('\n')
    const body = fnBody(fx, /function\s+a\b/)
    expect(body).toContain('doA()')
    expect(body, 'fnBody 串到了下一个函数的体').not.toContain('zzz')
  })

  // 🔴 本轮实测踩到的守卫缺陷 2：`computedArg` 原正则要求 `computed\s*\(`，
  //    匹配不到**带泛型实参**的 `computed<DelegationMember[]>(...)` ⇒ 返回空串，
  //    而空串对 `toMatch` 恒不命中 ⇒ 判据以「未找到」的形态假红。宿主的
  //    `suggestionMembers` / 组件的 `applyGroups` 都是这个写法。
  it('computedArg 支持带泛型实参的 computed<T>(...)', () => {
    const fx = 'const x = computed<Foo[]>(() => bar.map(f))'
    expect(computedArg(fx, 'x'), 'computed<T>( 形态未被匹配').toContain('bar.map(f)')
  })

  it('computedArg 对不带泛型的 computed(...) 同样成立（两形态都要覆盖）', () => {
    const fx = 'const y = computed(() => baz())'
    expect(computedArg(fx, 'y')).toContain('baz()')
  })

  it('扫描面非空：组件与宿主两段都切到了', () => {
    expect(COMP_SEG.template.length, '组件模板段过短').toBeGreaterThan(2000)
    expect(COMP_SEG.script.length, '组件脚本段过短').toBeGreaterThan(3000)
    expect(TRIM_SEG.template.length, '宿主模板段过短').toBeGreaterThan(10000)
    expect(TRIM_SEG.script.length, '宿主脚本段过短').toBeGreaterThan(20000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：wp_index_ids 不得由 wp_id 派生（本文件最贵的一条）
// ═══════════════════════════════════════════════════════════════════════════
//
// `getProcedures` 只下发 `wp_id`（= `working_paper.id`），而底稿粒度 selector 要
// `wp_index.id`。两者不同表：拿 wp_id 填 wp_index_ids 后端匹配不到任何目标，且
// **不报错** —— 表现为「建议表生成了但应用后 0 变更」，最难归因的一类。
describe('判据 A: 底稿粒度目标的 wpIndexId 取自 wp_index_id，不由 wp_id 派生', () => {
  const body = fnBody(TRIM_SEG.script, /async\s+function\s+buildSuggestionTargets\b/)

  it('扫描面非空：截到 buildSuggestionTargets 函数体', () => {
    expect(body, '未截到 buildSuggestionTargets 函数体').not.toBe('')
    expect(body.length, '函数体过短，疑似截错').toBeGreaterThan(400)
  })

  it('取数走 listWorkpapersPaged（不是 getProcedures）', () => {
    expect(body, '未调用 listWorkpapersPaged').toContain('listWorkpapersPaged')
    expect(
      /getProcedures\s*\(/.test(body),
      'buildSuggestionTargets 里调了 getProcedures（它只下发 wp_id，无 wp_index_id）',
    ).toBe(false)
  })

  it('wpIndexId 的赋值表达式真的读 wp_index_id', () => {
    // 结构判据：wpIndexId 的右值里必须出现 wp_index_id
    const m = body.match(/wpIndexId\s*=\s*([^\n]+)/)
    expect(m, '未找到 wpIndexId 的赋值语句').not.toBeNull()
    expect(m![1], `wpIndexId 右值未读 wp_index_id，实际为: ${m![1]}`).toContain('wp_index_id')
  })

  it('函数体内不出现 wp_id（剥注释后）—— 防「改回 wp_id」与「两者混用」', () => {
    // `wp_index_id` 含子串 `_id` 但不含 `wp_id`；用负向后顾排除 wp_index_id 的干扰
    const bad = body.match(/(?<!wp_index)\bwp_id\b/g) ?? []
    expect(bad.length, `函数体内出现 ${bad.length} 处裸 wp_id`).toBe(0)
  })

  it('反向自检：把 wp_index_id 换成 wp_id 后同一判据必须命中', () => {
    const fake = body.replace(/wp_index_id/g, 'wp_id')
    expect(fake, '替身构造失败').not.toBe(body)
    const m = fake.match(/wpIndexId\s*=\s*([^\n]+)/)
    expect(m).not.toBeNull()
    expect(
      m![1].includes('wp_index_id'),
      '替身仍被判为读 wp_index_id ⇒ 判据无承重',
    ).toBe(false)
    expect((fake.match(/(?<!wp_index)\bwp_id\b/g) ?? []).length, '替身未被裸 wp_id 判据命中')
      .toBeGreaterThan(0)
  })

  it('selector 语义已登记为 workpaper 粒度（应用分组按 wp_index_ids）', () => {
    const groups = computedArg(COMP_SEG.script, 'applyGroups')
    expect(groups, '未找到 applyGroups computed').not.toBe('')
    // 🔴 键名必须是后端契约的 **snake_case** `wp_index_ids`（`DelegationSelector`
    //    是直接 POST 给后端的载荷形态）。此处曾误写 camelCase `wpIndexIds` 断言 ——
    //    那会把正确实现打红，属守卫缺陷。改为按契约键名断言，并钉死 kind。
    expect(groups, 'applyGroups 未产出 wp_index_ids（后端 selector 契约键名）')
      .toContain('wp_index_ids')
    expect(groups, "selector.kind 未声明为 'workpaper'").toMatch(/kind:\s*'workpaper'/)
    expect(groups, 'applyGroups 未按 assigneeStaffId 分组').toContain('assigneeStaffId')
    // 反向：camelCase 形态不得出现（出现即说明有人按前端习惯改了键名 → 后端收不到）
    expect(
      /wpIndexIds/.test(groups),
      'applyGroups 用了 camelCase wpIndexIds ⇒ 后端 selector 收不到该键',
    ).toBe(false)
  })

  it('组件的 selector 键名与 commonApi 的 DelegationSelector 契约逐名一致', () => {
    // 交叉锁死：一侧改名另一侧未跟进即红（现状前端只用 cycle 粒度，workpaper 粒度
    // 是本任务第一次真正使用，最容易出现「键名自拟」）
    const api = stripComments(read(P_COMMON_API))
    const at = api.indexOf('export interface DelegationSelector')
    expect(at, 'commonApi 未声明 DelegationSelector').toBeGreaterThanOrEqual(0)
    const open = api.indexOf('{', at)
    const close = api.indexOf('}', open)
    const decl = api.slice(open, close)
    expect(decl, 'DelegationSelector 契约无 wp_index_ids').toContain('wp_index_ids')
    expect(decl, "DelegationSelector 契约无 'workpaper' 粒度").toContain('workpaper')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：负载未知显示「负载未知」，绝不补 0
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 B: 负载未知不补 0', () => {
  const board = computedArg(COMP_SEG.script, 'loadBoard')

  it('扫描面非空：截到 loadBoard computed', () => {
    expect(board, '未找到 loadBoard computed').not.toBe('')
    expect(board.length).toBeGreaterThan(200)
  })

  it('before 为 null 时 after 亦为 null（不拿 0 当基线凑绝对值）', () => {
    expect(
      /before\s*===\s*null\s*\?\s*null\s*:/.test(board),
      'loadBoard 未按「before === null ⇒ after = null」构造',
    ).toBe(true)
  })

  it('currentLoad 不被 ?? 0 / || 0 兜底（那正是「未知变 0」的形态）', () => {
    expect(
      /currentLoad\s*(\?\?|\|\|)\s*0/.test(COMP_SEG.script),
      '组件把 currentLoad 兜底成 0',
    ).toBe(false)
    expect(
      /currentLoad\s*(\?\?|\|\|)\s*0/.test(TRIM_SEG.script),
      '宿主把 currentLoad 兜底成 0',
    ).toBe(false)
  })

  it('模板真的渲染「负载未知」文案（不只是算出 null 却显示空白）', () => {
    expect(COMP_SEG.template, '组件模板未渲染「负载未知」').toContain('负载未知')
  })

  it('宿主传给算法的 currentLoad 来自三态 memberLoadOf（null = 未知）', () => {
    const arg = computedArg(TRIM_SEG.script, 'suggestionMembers')
    expect(arg, '未找到 suggestionMembers computed').not.toBe('')
    expect(arg, 'currentLoad 未取 memberLoadOf').toMatch(/currentLoad:\s*memberLoadOf\(/)
  })

  it('反向自检：把 after 改成 before ?? 0 + 增量后判据必须命中', () => {
    const fake = board.replace(/before\s*===\s*null\s*\?\s*null\s*:/, '')
    expect(fake, '替身构造失败').not.toBe(board)
    expect(
      /before\s*===\s*null\s*\?\s*null\s*:/.test(fake),
      '替身仍被判为正确 ⇒ 判据无承重',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：组件只读 + emit，无任何请求/写入
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 C: 组件自身不发请求、不写库', () => {
  it('不 import http / services / axios', () => {
    expect(/from\s+['"]@\/utils\/http['"]/.test(COMP_SEG.script), '组件 import 了 http').toBe(false)
    expect(/from\s+['"]@\/services\//.test(COMP_SEG.script), '组件 import 了 services').toBe(false)
    expect(/from\s+['"]axios['"]/.test(COMP_SEG.script), '组件 import 了 axios').toBe(false)
  })

  it('无 http 动词调用（.get( / .post( / .put( / .delete(）', () => {
    for (const verb of ['get', 'post', 'put', 'delete', 'patch']) {
      const re = new RegExp(`\\bhttp\\s*\\.\\s*${verb}\\s*\\(`)
      expect(re.test(COMP_SEG.script), `组件内有 http.${verb}( 调用`).toBe(false)
    }
  })

  it('不调用既有委派写入函数（preview / apply 归宿主与 Task 19）', () => {
    expect(
      /previewProcedureDelegation\s*\(/.test(COMP_SEG.script),
      '组件直接调 previewProcedureDelegation',
    ).toBe(false)
    expect(
      /applyProcedureDelegation\s*\(/.test(COMP_SEG.script),
      '组件直接调 applyProcedureDelegation',
    ).toBe(false)
    expect(
      /canonicalTrimApply\s*\(/.test(COMP_SEG.script),
      '组件直接调 canonicalTrimApply',
    ).toBe(false)
  })

  it('应用动作只 emit，不自行执行', () => {
    const body = fnBody(COMP_SEG.script, /function\s+emitApply\b/)
    expect(body, '未找到 emitApply 函数体').not.toBe('')
    expect(body, 'emitApply 未 emit').toContain("emit('apply'")
    expect(/await\s/.test(body), 'emitApply 里有 await ⇒ 疑似自行发请求').toBe(false)
  })

  it('反向自检：注入 http.post 后同一判据必须命中', () => {
    const fake = `${COMP_SEG.script}\nasync function x() { await http.post('/a', {}) }`
    expect(/\bhttp\s*\.\s*post\s*\(/.test(fake), '判据对替身未命中 ⇒ 无承重').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：宿主接线（props / emits 名字必须对得上 —— 只有挂载才暴露的一类）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 D: 宿主与组件的 props / emits 逐名对齐', () => {
  function declaredNames(block: string): string[] {
    // 从 `defineProps<{ a: X; b: Y }>()` 的类型字面量里抽键名
    const out: string[] = []
    for (const m of block.matchAll(/^\s*(\w+)\s*[?]?\s*:/gm)) out.push(m[1])
    return out
  }

  const propsBlock = (() => {
    const at = COMP_SEG.script.indexOf('defineProps')
    expect(at, '未找到 defineProps').toBeGreaterThanOrEqual(0)
    const open = COMP_SEG.script.indexOf('{', at)
    const close = COMP_SEG.script.indexOf('}>', open)
    return COMP_SEG.script.slice(open + 1, close)
  })()

  const emitsBlock = (() => {
    const at = COMP_SEG.script.indexOf('defineEmits')
    expect(at, '未找到 defineEmits').toBeGreaterThanOrEqual(0)
    const open = COMP_SEG.script.indexOf('{', at)
    const close = COMP_SEG.script.indexOf('}>', open)
    return COMP_SEG.script.slice(open + 1, close)
  })()

  const hostTag = (() => {
    const at = TRIM_SEG.template.indexOf('<GtDelegationSuggestionTable')
    expect(at, '宿主模板未使用 GtDelegationSuggestionTable').toBeGreaterThanOrEqual(0)
    const close = TRIM_SEG.template.indexOf('/>', at)
    expect(close, '组件标签未闭合').toBeGreaterThan(at)
    return TRIM_SEG.template.slice(at, close + 2)
  })()

  it('扫描面非空：props / emits / 宿主标签都抽到了', () => {
    expect(declaredNames(propsBlock).length, 'props 键抽不到').toBeGreaterThanOrEqual(2)
    expect(emitsBlock, 'emits 块为空').not.toBe('')
    expect(hostTag.length, '宿主标签过短').toBeGreaterThan(80)
  })

  it('组件声明的每个 prop，宿主都真的传了（防「传了不存在的 prop」静默失效）', () => {
    for (const name of declaredNames(propsBlock)) {
      expect(hostTag, `宿主未传 prop :${name}`).toContain(`:${name}=`)
    }
  })

  it('宿主传的每个 prop，组件都声明了', () => {
    const declared = new Set(declaredNames(propsBlock))
    for (const m of hostTag.matchAll(/:(\w[\w-]*)=/g)) {
      const attr = m[1]
      if (attr === 'key') continue
      expect(declared.has(attr), `宿主传了组件未声明的 prop :${attr}`).toBe(true)
    }
  })

  it('组件声明的每个 emit，宿主都有监听（否则该出口是死输出）', () => {
    const emitNames = [...emitsBlock.matchAll(/\(e:\s*'(\w+)'/g)].map((m) => m[1])
    expect(emitNames.length, 'emit 名抽不到').toBeGreaterThanOrEqual(2)
    for (const e of emitNames) {
      expect(hostTag, `宿主未监听 @${e}`).toContain(`@${e}=`)
    }
  })

  it('宿主模板里的建议面板标识符都在 script 有声明（防 ReferenceError）', () => {
    for (const id of [
      'suggestPanel', 'suggestionMembers', 'onSuggestionRowsChange',
      'onSuggestionApplyRequest', 'openSuggestionPanel',
    ]) {
      expect(TRIM_SEG.template, `模板未使用 ${id}`).toContain(id)
      const declared = new RegExp(
        `(const|let|function|async\\s+function)\\s+${id}\\b`,
      ).test(TRIM_SEG.script)
      expect(declared, `${id} 在模板被使用但 script 无声明（运行即 ReferenceError）`).toBe(true)
    }
  })

  it('建议面板有面板外的入口（否则永远打不开）', () => {
    // 面板自身的 dialog 起点：入口按钮必须在它之前
    const panelAt = TRIM_SEG.template.indexOf('v-model="suggestPanel.visible"')
    expect(panelAt, '未找到建议面板 dialog').toBeGreaterThan(0)
    const before = TRIM_SEG.template.slice(0, panelAt)
    expect(
      before.includes('openSuggestionPanel'),
      '建议面板之外没有任何 openSuggestionPanel 入口 ⇒ 面板不可达',
    ).toBe(true)
  })

  it('取数失败可见：suggestPanel.error 真的被模板渲染（不是死字段）', () => {
    expect(
      TRIM_SEG.template,
      'suggestPanel.error 未渲染 ⇒ 取数失败与「无建议」不可区分（fail-open）',
    ).toContain('suggestPanel.error')
  })

  it('无重复顶层 import（重复顶层声明会让 Vite transform 直接失败）', () => {
    for (const sym of [
      'suggestDelegation', 'roleSeniority', 'GtDelegationSuggestionTable', 'listWorkpapersPaged',
    ]) {
      const decls = (TRIM_SEG.script.match(
        new RegExp(`^import\\s+(\\{[^}]*\\b${sym}\\b[^}]*\\}|${sym})\\s+from`, 'gm'),
      ) ?? []).length
      expect(decls, `${sym} 被 import ${decls} 次（>1 即重复顶层声明）`).toBeLessThanOrEqual(1)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 E：SOD 与资历折算不得被绕开
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 E: SOD 硬约束与资历折算口径', () => {
  it('复核人候选排除本行执行人（SOD 第一道）', () => {
    const body = fnBody(COMP_SEG.script, /function\s+reviewerOptions\b/)
    expect(body, '未找到 reviewerOptions 函数体').not.toBe('')
    expect(
      /staffId\s*!==\s*row\.assigneeStaffId/.test(body),
      'reviewerOptions 未排除执行人本人（SOD 被绕开）',
    ).toBe(true)
  })

  it('改执行人后与其同名的复核人被清空（防落库前才被后端拒）', () => {
    const body = fnBody(COMP_SEG.script, /function\s+onAssigneeChange\b/)
    expect(body, '未找到 onAssigneeChange 函数体').not.toBe('')
    expect(
      /reviewerStaffId\s*===\s*row\.assigneeStaffId/.test(body),
      'onAssigneeChange 未检测复核人与新执行人同一人',
    ).toBe(true)
    expect(body, '未清空 reviewerStaffId').toMatch(/reviewerStaffId\s*=\s*null/)
  })

  it('宿主用 roleSeniority 折算资历，不挪用 ROLE_PRIORITY', () => {
    const arg = computedArg(TRIM_SEG.script, 'suggestionMembers')
    expect(arg, 'seniority 未走 roleSeniority').toMatch(/seniority:\s*roleSeniority\(/)
    expect(
      arg.includes('ROLE_PRIORITY'),
      'suggestionMembers 里挪用了 ROLE_PRIORITY（方向与键集都不对）',
    ).toBe(false)
  })

  it('资历折算模块存在且不引用 ROLE_PRIORITY（剥注释后）', () => {
    const sen = stripComments(read(P_SENIORITY))
    expect(sen, '未找到 roleSeniority 导出').toContain('export function roleSeniority')
    expect(
      sen.includes('ROLE_PRIORITY'),
      'delegationSeniority.ts 在代码中引用了 ROLE_PRIORITY',
    ).toBe(false)
  })

  it('降级模式下不判资历（拿不可信风险值判等于假装做了风险匹配）', () => {
    const body = fnBody(COMP_SEG.script, /function\s+rowIssue\b/)
    expect(body, '未找到 rowIssue 函数体').not.toBe('')
    expect(
      /!\s*props\.suggestion\.degraded/.test(body),
      'rowIssue 未按 degraded 短路资历判定',
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 F：算法结论如实暴露（warnings / unassignedTargets / degraded 独立区块）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 F: 算法的判据缺口必须独立成块展示，不得只塞 tooltip', () => {
  it('degraded 显著标注「未做风险匹配」', () => {
    expect(COMP_SEG.template, '未渲染 degraded 分支').toContain('degraded')
    expect(COMP_SEG.template, '未标注「未做风险匹配」').toContain('未做风险匹配')
  })

  it('warnings 独立区块（逐条列出，不是拼成一句塞 tooltip）', () => {
    expect(COMP_SEG.template, '未渲染 warnings').toContain('warnings')
    expect(
      /v-for="[^"]*\bin\s+suggestion\.warnings/.test(COMP_SEG.template),
      'warnings 未逐条 v-for 渲染',
    ).toBe(true)
  })

  it('unassignedTargets 独立区块并展示 reason', () => {
    expect(COMP_SEG.template, '未渲染 unassignedTargets').toContain('unassignedTargets')
    expect(COMP_SEG.template, '未展示未分配原因 reason').toMatch(/prop="reason"|row\.reason/)
  })

  /**
   * 🔴 判据必须落「渲染条件真的由数据驱动」而非「字符是否出现」。
   *
   * 本条是变异检验 M6 首轮 **GREEN**（守卫缺陷）后补的：M6 把
   * `v-if="suggestion.unassignedTargets.length > 0"` 改成 `v-if="false"`，
   * 区块从此永不渲染 —— 但 `unassignedTargets` 这个字符串在同区块的标题行与
   * `:data` 行仍然在，故上面那条 `toContain('unassignedTargets')` 照样通过。
   *
   * 「H 风险无人覆盖」是必须上报项目负责人的事实（要加派资深人员或升级复核层级），
   * 被静默咽掉时 UI 与「本来就没有未分配项」完全无法区分。故这里断言**条件表达式
   * 本身**绑在 `suggestion.unassignedTargets` 上，且不是常量。
   */
  it('未分配区块的渲染条件由数据驱动，不是常量（防 v-if="false" 静默咽掉）', () => {
    const conds = [...COMP_SEG.template.matchAll(/v-if="([^"]*)"/g)].map((m) => m[1])
    expect(conds.length, '模板里没有任何 v-if ⇒ 扫描面失效').toBeGreaterThan(0)

    const driven = conds.filter((c) => /suggestion\.unassignedTargets\b/.test(c))
    expect(
      driven.length,
      '未分配区块的 v-if 未绑定 suggestion.unassignedTargets（疑似被改成常量或写死）',
    ).toBeGreaterThanOrEqual(1)
    // 条件里必须真的比较长度，而不是 `v-if="true"` 之类恒真式
    expect(
      driven.some((c) => /\.length\s*>\s*0/.test(c)),
      '未分配区块的 v-if 未按 length > 0 判定',
    ).toBe(true)

    // 反向自检：替身把该条件换成常量后，同一判据必须不再命中
    const fake = COMP_SEG.template.replace(
      /v-if="suggestion\.unassignedTargets\.length > 0"/,
      'v-if="false"',
    )
    expect(fake, '替身构造失败（未替换到未分配区块的 v-if）').not.toBe(COMP_SEG.template)
    const fakeDriven = [...fake.matchAll(/v-if="([^"]*)"/g)]
      .map((m) => m[1])
      .filter((c) => /suggestion\.unassignedTargets\b/.test(c))
    expect(
      fakeDriven.length,
      '替身仍被判为数据驱动 ⇒ 该判据无承重（M6 会继续 GREEN）',
    ).toBe(0)
  })

  it('逐行 rationale 可见（审计师据此判断是否接受）', () => {
    expect(COMP_SEG.template, '未渲染 rationale').toContain('rationaleOf')
    const body = fnBody(COMP_SEG.script, /function\s+rationaleOf\b/)
    expect(body, '未找到 rationaleOf 函数体').not.toBe('')
    expect(body, 'rationaleOf 未使用算法给的 rationale').toContain('row.rationale')
  })

  it('逐行可移除（R11.6）', () => {
    expect(COMP_SEG.template, '未提供移除入口').toContain('removeRow')
    const body = fnBody(COMP_SEG.script, /function\s+removeRow\b/)
    expect(body, '未找到 removeRow 函数体').not.toBe('')
    expect(body, 'removeRow 未真的删行').toMatch(/splice\(/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 G：Task 13 成果零回归（本任务是加法式，不得动既有建议态链）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 G: Task 13/15/16 既有成果原样保留', () => {
  it('suggestionOf / clearRowSuggestion / loadTrimContext 调用点未被削减', () => {
    expect((TRIM.match(/suggestionOf\s*\(/g) ?? []).length, 'suggestionOf 调用点少于 3')
      .toBeGreaterThanOrEqual(3)
    expect((TRIM.match(/clearRowSuggestion\s*\(/g) ?? []).length, 'clearRowSuggestion 少于 2')
      .toBeGreaterThanOrEqual(2)
    expect((TRIM.match(/loadTrimContext\s*\(/g) ?? []).length, 'loadTrimContext 调用点少于 5')
      .toBeGreaterThanOrEqual(5)
  })

  it('suggest_trim 分支仍写 _suggest = true（建议态产生路径未被破坏）', () => {
    expect((TRIM.match(/_suggest\s*=\s*true/g) ?? []).length, '_suggest = true 赋值点消失')
      .toBeGreaterThanOrEqual(1)
  })

  it('概览侧建议态统计与导出理由码列仍在', () => {
    expect((TRIM.match(/suggestConfirmed/g) ?? []).length, 'suggestConfirmed 出现次数下降')
      .toBeGreaterThanOrEqual(6)
    expect(TRIM, '导出「理由码」列消失').toContain('理由码')
  })

  it('单执行人委派流程（Task 15/16）未被替换', () => {
    expect(TRIM_SEG.script, 'runDelegatePreview 消失').toContain('runDelegatePreview')
    expect(TRIM_SEG.script, 'runDelegateApply 消失').toContain('runDelegateApply')
    expect(TRIM_SEG.script, 'memberLoadOf 消失（Task 16 负载单一真源）').toContain('memberLoadOf')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 H：UI 铁律
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 H: UI 铁律', () => {
  it('模板属性内无中文引号/特殊 Unicode（会让 Vite 编译崩且 get_diagnostics 查不出）', () => {
    for (const [i, line] of COMP_RAW.split('\n').entries()) {
      // 只查属性区（含 = 且带引号的行）
      if (!/=\s*"/.test(line)) continue
      for (const ch of ['\u201c', '\u201d', '\u2018', '\u2019']) {
        expect(
          line.includes(ch),
          `第 ${i + 1} 行模板属性含中文引号 ${JSON.stringify(ch)}: ${line.trim().slice(0, 90)}`,
        ).toBe(false)
      }
    }
  })

  it('负载/资历/权重是计数与系数，禁套金额组件', () => {
    expect(COMP_SEG.script.includes('WpAmountInput'), '组件用了 WpAmountInput（金额专用）').toBe(false)
    expect(COMP_SEG.template.includes('WpAmountInput'), '模板用了 WpAmountInput').toBe(false)
    expect(COMP_SEG.script.includes('fmtAmount'), '组件用了 fmtAmount（金额专用）').toBe(false)
  })

  it('13px 字号', () => {
    expect(COMP_RAW, '未设置 13px 字号').toContain('13px')
  })

  it('状态列用中文彩色 tag，无裸英文状态词', () => {
    expect(COMP_SEG.template, '未用 el-tag').toContain('el-tag')
    // 风险等级必须有中文标签函数，不直接渲染 H/M/L
    const body = fnBody(COMP_SEG.script, /function\s+riskLabel\b/)
    expect(body, '未找到 riskLabel').not.toBe('')
    expect(body, 'riskLabel 未给出中文').toMatch(/高风险|中风险|低风险/)
  })

  it('执行人/复核人用 el-select 点选（交互点选优先）', () => {
    expect((COMP_SEG.template.match(/<el-select/g) ?? []).length, 'el-select 少于 2 个')
      .toBeGreaterThanOrEqual(2)
  })

  it('长文 rationale 用 el-tooltip 承载', () => {
    expect(COMP_SEG.template, 'rationale 未配 tooltip').toContain('el-tooltip')
  })
})
