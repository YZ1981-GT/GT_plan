/**
 * 委派界面信息完整性与负载单一真源守卫
 *
 * Spec: .kiro/specs/procedure-trimming-and-delegation-intelligence/
 * Tasks: 15, 16
 * Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
 *
 * 守三件事：
 *
 * 1. **负载单一真源**：前端不得再自行聚合成员负载。改造前 `assigneeLoadMap` 按
 *    "底稿张数"自算一份（口径与后端"非终态任务数"不同，且仅在打开全项目概览
 *    抽屉后才有值 —— 而委派界面正是最需要它的地方）。
 *
 * 2. **"负载未知"与 0 必须可区分**：请求失败时显示 0 会误导为"这个人很空闲"。
 *
 * 3. **preview 计数读对层**：后端把计数放在嵌套的 `summary` 对象里。改造前前端读
 *    `preview.target_count ?? preview.targets` / `preview.conflict_count` /
 *    `preview.assigned_count` —— 三个字段名后端都不存在，故目标数与已分配恒显示
 *    「—」、冲突数恒显示 0，而这正是审计师判断本次委派影响面的唯一依据。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'

// ── 仓库根定位：双哨兵向上查找，禁写死回退级数 ──
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = resolve(dir, 'backend/app/services/procedure_delegation_service.py')
    const b = resolve(dir, 'audit-platform/frontend/src/views/ProcedureTrimming.vue')
    if (existsSync(a) && existsSync(b)) return dir
    dir = dirname(dir)
  }
  throw new Error('无法定位仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const VIEW = resolve(ROOT, 'audit-platform/frontend/src/views/ProcedureTrimming.vue')
const API = resolve(ROOT, 'audit-platform/frontend/src/services/commonApi.ts')
const PATHS = resolve(ROOT, 'audit-platform/frontend/src/services/apiPaths/workpaper.ts')
const SERVICE_PY = resolve(ROOT, 'backend/app/services/procedure_delegation_service.py')
const ROUTER_PY = resolve(ROOT, 'backend/app/routers/procedure_delegations.py')

const viewSrc = readFileSync(VIEW, 'utf-8')
const apiSrc = readFileSync(API, 'utf-8')
const pathsSrc = readFileSync(PATHS, 'utf-8')

/**
 * 剥注释（带字符串状态机）：判"源码里是否真的这么写"必须先剥注释，
 * 否则本文件与被测文件的说明性注释会被数成真实代码。
 * 分区处理：<style> 整段丢弃；模板区只剥 HTML 注释；<script> 区剥 JS 注释。
 * 不剥字符串字面量（URL 里的 // 与 accept="image/*" 都不能误判）。
 */
function stripComments(src: string): string {
  const noStyle = src.replace(/<style[\s\S]*?<\/style>/g, '')
  const noHtml = noStyle.replace(/<!--[\s\S]*?-->/g, '')
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < noHtml.length) {
    const c = noHtml[i]
    const n = noHtml[i + 1]
    if (quote) {
      if (c === '\\') { out += c + (n ?? ''); i += 2; continue }
      if (c === quote) quote = null
      out += c; i += 1; continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (c === '/' && n === '/') { while (i < noHtml.length && noHtml[i] !== '\n') i += 1; continue }
    if (c === '/' && n === '*') { i += 2; while (i < noHtml.length && !(noHtml[i] === '*' && noHtml[i + 1] === '/')) i += 1; i += 2; continue }
    out += c; i += 1
  }
  return out
}

const viewCode = stripComments(viewSrc)

describe('守卫自身有效性自检', () => {
  it('扫描面非空且剥注释生效', () => {
    expect(viewSrc.length).toBeGreaterThan(10000)
    // 原文含说明性注释里的反例字样，剥注释后应消失 —— 证明 stripComments 真起作用
    expect(viewSrc).toContain('底稿张数')
    expect(viewCode).not.toContain('底稿张数')
  })

  it('后端两个真源文件可读（跨前后端交叉锁死的前提）', () => {
    expect(existsSync(SERVICE_PY)).toBe(true)
    expect(existsSync(ROUTER_PY)).toBe(true)
  })
})

describe('Task 16 — 负载单一真源（Requirements 10.3, 10.4, 10.5）', () => {
  it('不存在前端自算负载的实现', () => {
    // 历史实现的符号名
    expect(viewCode).not.toMatch(/\bassigneeLoadMap\b/)
    expect(viewCode).not.toMatch(/\bassigneeLoadLoaded\b/)
  })

  it('不存在按底稿聚合负载的循环结构', () => {
    // 形如 map[p.assigned_to] = (map[p.assigned_to] || 0) + 1 的自算聚合
    expect(viewCode).not.toMatch(/\[\s*p\.assigned_to\s*\]\s*=\s*\(/)
    expect(viewCode).not.toMatch(/assigned_to\s*\]\s*\|\|\s*0\s*\)\s*\+\s*1/)
  })

  it('负载读自后端 member-loads 端点', () => {
    expect(viewCode).toContain('fetchDelegationMemberLoads')
    expect(apiSrc).toContain('export async function fetchDelegationMemberLoads')
    expect(pathsSrc).toContain('delegationMemberLoads')
  })

  it('端点路径与后端 router 注册逐字一致（跨前后端交叉锁死）', () => {
    const routerSrc = readFileSync(ROUTER_PY, 'utf-8')
    const m = pathsSrc.match(/delegationMemberLoads:\s*\(pid: string\)\s*=>\s*`([^`]+)`/)
    expect(m, 'apiPaths 未声明 delegationMemberLoads').toBeTruthy()
    // 把 ${pid} 还原成后端的 {pid} 占位再比对
    const feePath = m![1].replace('${pid}', '{pid}').replace('/api/projects', '')
    expect(routerSrc).toContain(`router.get("${feePath}")`)
  })

  it('负载在进入界面时即加载，不依赖打开其他抽屉', () => {
    // onMounted 块内必须调用负载加载
    const m = viewCode.match(/onMounted\(async \(\) => \{([\s\S]*?)\n\}\)/)
    expect(m, '未找到 onMounted 块').toBeTruthy()
    expect(m![1]).toContain('loadMemberLoads')
  })

  it('负载加载失败保持"未知"而非退化为 0', () => {
    const m = viewCode.match(/async function loadMemberLoads\(\)[\s\S]*?\n\}/)
    expect(m, '未找到 loadMemberLoads').toBeTruthy()
    // catch 分支必须把状态置 null（未知），不得置 {} 或 0
    expect(m![0]).toMatch(/catch\s*\{[\s\S]*?memberLoads\.value\s*=\s*null/)
  })
})

describe('Task 15/16 — 负载未知与 0 可区分（Requirement 10.6）', () => {
  it('存在三态取值函数且未知返回 null', () => {
    const m = viewCode.match(/function memberLoadOf\([\s\S]*?\n\}/)
    expect(m, '未找到 memberLoadOf').toBeTruthy()
    expect(m![0]).toMatch(/===\s*null\)\s*return null/)
  })

  it('展示文案对未知与 0 给出不同文本', () => {
    const m = viewCode.match(/function memberLoadLabel\([\s\S]*?\n\}/)
    expect(m, '未找到 memberLoadLabel').toBeTruthy()
    expect(m![0]).toContain('负载未知')
    // 未知分支必须先于数值分支（否则 0 会走进数值分支后无法区分）
    expect(m![0]).toMatch(/null\s*\?\s*'负载未知'/)
  })

  it('下拉标签走同一负载函数（与委派向导同源）', () => {
    const m = viewCode.match(/function assigneeOptionLabel\([\s\S]*?\n\}/)
    expect(m, '未找到 assigneeOptionLabel').toBeTruthy()
    expect(m![0]).toContain('memberLoadLabel')
  })
})

describe('Task 15 — preview 计数读对层（Requirements 10.1, 10.2）', () => {
  it('不再读后端不存在的顶层字段名', () => {
    for (const dead of ['target_count', 'conflict_count', 'assigned_count']) {
      expect(viewCode, `仍在读后端不存在的字段 ${dead}`).not.toContain(dead)
    }
  })

  it('计数取自嵌套 summary 的真实键', () => {
    const m = viewCode.match(/const previewSummary = computed[\s\S]*?\n\}\)/)
    expect(m, '未找到 previewSummary').toBeTruthy()
    expect(m![0]).toContain('preview?.summary')
    // 模板必须经 previewSummary 取值
    expect(viewCode).toMatch(/previewSummary\?\.targets/)
    expect(viewCode).toMatch(/previewSummary\?\.conflict/)
  })

  it('summary 键名与后端 preview 返回体逐字一致（跨前后端交叉锁死）', () => {
    const py = readFileSync(SERVICE_PY, 'utf-8')
    // 后端 summary 字典的键
    const block = py.match(/"summary":\s*\{([\s\S]*?)\n\s{12}\}/)
    expect(block, '后端 preview 的 summary 块未找到（判据失效）').toBeTruthy()
    const backendKeys = [...block![1].matchAll(/"(\w+)":/g)].map(x => x[1])
    expect(backendKeys.length).toBeGreaterThan(5)
    // 前端模板引用的 summary 键必须都在后端键集里
    const used = [...viewCode.matchAll(/previewSummary\?\.(\w+)/g)].map(x => x[1])
    expect(used.length).toBeGreaterThan(3)
    for (const k of used) {
      expect(backendKeys, `前端读的 summary.${k} 在后端不存在`).toContain(k)
    }
  })

  it('展示执行人当前负载（preview 已下发但改造前未展示）', () => {
    expect(viewCode).toContain('previewAssigneeLoad')
    expect(viewCode).toContain('membership_load')
    const py = readFileSync(SERVICE_PY, 'utf-8')
    expect(py).toContain('"active_task_count"')
    expect(viewCode).toContain('active_task_count')
  })

  it('展示受影响底稿清单（preview 已下发但改造前未展示）', () => {
    expect(viewCode).toContain('affectedWorkpapers')
    expect(viewCode).toContain('affected_workpapers')
    const m = viewCode.match(/const affectedWorkpapers = computed[\s\S]*?\n\}\)/)
    expect(m, '未找到 affectedWorkpapers').toBeTruthy()
    // 委派侧是 {wp_index_ids, wp_ids} 对象结构
    expect(m![0]).toContain('wp_ids')
    expect(m![0]).toContain('wp_index_ids')
  })

  it('不复用调整分录影响预览的同名字段渲染组件', () => {
    // affected_workpapers 在平台同名不同源：调整分录侧是 string[] / ImpactWorkpaper[]
    expect(viewCode).not.toContain('ImpactPreviewPanel')
    expect(viewCode).not.toContain('AdjustmentImpactPreview')
  })

  it('映射不到 wp_code 时如实提示而非显示空列表', () => {
    expect(viewSrc).toContain('编号待解析')
  })
})

describe('反向自检 — 复现旧行为必被打红', () => {
  it('旧的顶层字段读法会被本守卫拒绝', () => {
    const legacy = 'const x = preview.target_count ?? preview.targets ?? 0'
    const scan = (s: string) => ['target_count', 'conflict_count', 'assigned_count']
      .some(d => s.includes(d))
    expect(scan(legacy), '判据对旧写法必须命中').toBe(true)
    expect(scan(viewCode), '当前实现不应命中').toBe(false)
  })

  it('旧的前端自算负载写法会被本守卫拒绝', () => {
    const legacy = 'if (applicable && p.assigned_to) map[p.assigned_to] = (map[p.assigned_to] || 0) + 1'
    expect(/\[\s*p\.assigned_to\s*\]\s*=\s*\(/.test(legacy), '判据对旧写法必须命中').toBe(true)
    expect(/\[\s*p\.assigned_to\s*\]\s*=\s*\(/.test(viewCode), '当前实现不应命中').toBe(false)
  })

  it('把"负载未知"改成 0 会被本守卫拒绝', () => {
    const bad = "function memberLoadLabel(id: string): string { const n = memberLoadOf(id); return `在办${n ?? 0}项` }"
    expect(bad.includes('负载未知')).toBe(false)
    const m = viewCode.match(/function memberLoadLabel\([\s\S]*?\n\}/)
    expect(m![0].includes('负载未知')).toBe(true)
  })
})
