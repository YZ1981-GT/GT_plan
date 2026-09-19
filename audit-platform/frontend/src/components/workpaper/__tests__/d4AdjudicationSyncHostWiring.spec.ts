/**
 * D4-1 审定表接桥 + 宿主登记守卫（Task 10）—— 参照 d4InspectionSyncHostWiring.spec.ts。
 *
 * spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 10
 * Requirements: 5.1（双向链路走统一 sync bridge 而非 legacy 单向）, 2.4（模式切换不发布 TB）
 *
 * 判据落到源码结构（与 D4-15/16 检查表守卫同范式）：
 *  1. D4TabAdjudication.vue 用平台 useWorkpaperSyncBridge，接桥字面量
 *     entryId=`xlsx/gt-d4-operating-revenue`、sheetKey=`d41-managed`（两处均以字面量常量声明）。
 *  2. flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值 / 顺序守卫）。
 *  3. 宿主 GtD4OperatingRevenue.vue 的 isD4DedicatedSyncSheet 含 'D4-1'
 *     （否则宿主叠加 legacy 双切换器，真正的同步桥被埋）。
 *  4. fail-closed / fail-visible：同步失败以中文 danger tag 显式呈现，不静默 markSynced。
 *  5. 模式切换器（switchMode / editorMode）不调用 publishAdjudicated（Req 2.4：切模式不发布 TB）。
 *  6. 挂载 WorkpaperSyncEditorHost，不得再挂裸 GtOnlyOfficeSheet。
 *
 * 反向自检（变异守卫）：若 'D4-1' 从 dedicated 列表移除、或 entryId/sheetKey 字面量写错、
 * 或 publishAdjudicated 混进 switchMode，则相应断言转红。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const ADJ_PATH = resolve(_dir, '..', 'd4', 'core', 'D4TabAdjudication.vue')
const HOST_PATH = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')

const D4_1_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_1_SHEET_KEY = 'd41-managed'

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}
/** 抽取 useWorkpaperSyncBridge({...}) 的调用体（括号配平）。 */
function extractBridgeCallArgs(src: string): string {
  const marker = 'useWorkpaperSyncBridge('
  const start = src.indexOf(marker)
  if (start < 0) return ''
  let depth = 0
  for (let i = start + marker.length - 1; i < src.length; i++) {
    const ch = src[i]
    if (ch === '(') depth++
    else if (ch === ')') {
      depth--
      if (depth === 0) return src.slice(start + marker.length, i)
    }
  }
  return ''
}
/** 抽取具名函数体（括号配平），如 switchMode。 */
function extractFunctionBody(src: string, fnName: string): string {
  const marker = `function ${fnName}`
  const start = src.indexOf(marker)
  if (start < 0) return ''
  const lb = src.indexOf('{', start)
  if (lb < 0) return ''
  let depth = 0
  for (let i = lb; i < src.length; i++) {
    const ch = src[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return src.slice(lb, i + 1)
    }
  }
  return ''
}

const adjSrc = existsSync(ADJ_PATH) ? stripComments(read(ADJ_PATH)) : ''
const hostSrc = existsSync(HOST_PATH) ? stripComments(read(HOST_PATH)) : ''
const bridgeArgs = extractBridgeCallArgs(adjSrc)

// ── D4TabAdjudication 接桥守卫 ──────────────────────────────────────────────
describe('D4-1 审定表必须消费平台 sync bridge（Req 5.1）', () => {
  it('D4TabAdjudication.vue 存在', () => {
    expect(existsSync(ADJ_PATH)).toBe(true)
  })

  it('调用了平台 useWorkpaperSyncBridge（禁自建同步 composable）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    // spec 草案臆想的服务名，前端不得直接引用
    expect(adjSrc).not.toContain('ContentMutationService')
  })

  it('接桥 entryId 字面量 = xlsx/gt-d4-operating-revenue', () => {
    // 常量声明处字面量 + 桥参数引用该常量
    expect(adjSrc).toContain(`= '${D4_1_ENTRY}'`)
    expect(adjSrc).toContain(D4_1_ENTRY)
    expect(bridgeArgs).toMatch(/entryId:\s*ref\(\s*D4_1_ENTRY\s*\)/)
  })

  it('接桥 sheetKey 字面量 = d41-managed', () => {
    expect(adjSrc).toContain(`= '${D4_1_SHEET_KEY}'`)
    expect(bridgeArgs).toMatch(/sheetKey:\s*ref\(\s*D4_1_SHEET_KEY\s*\)/)
  })

  it('capability 现算：capabilityForEntry(父级 entry)，禁内联 bidirectional 字面量', () => {
    expect(adjSrc).toMatch(/capabilityForEntry\s*\(/)
    expect(bridgeArgs).not.toMatch(/capability:\s*['"]bidirectional['"]/)
  })

  it('flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）', () => {
    expect(bridgeArgs).toContain('flushHtml')
    expect(bridgeArgs).toMatch(/flushPendingSave\s*\(/)
    expect(bridgeArgs).toMatch(/readStoreProjection\s*\(/)
    const flushAt = bridgeArgs.indexOf('flushPendingSave')
    const readAt = bridgeArgs.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('flushHtml 回投 sheetKey 锁本表 managed 身份', () => {
    expect(bridgeArgs).toMatch(/sheetKey:\s*D4_1_SHEET_KEY/)
  })

  it('模板挂载 WorkpaperSyncEditorHost，不得再挂裸 GtOnlyOfficeSheet', () => {
    expect(adjSrc).toContain('<WorkpaperSyncEditorHost')
    expect(adjSrc).not.toMatch(/<GtOnlyOfficeSheet\b/)
    expect(adjSrc).not.toMatch(/import\s+GtOnlyOfficeSheet/)
  })
})

// ── fail-closed / fail-visible 守卫（Req 5.1 / AC-1.4）─────────────────────
describe('D4-1 同步失败必须 fail-visible（中文 danger tag，不静默）', () => {
  it('存在同步状态 tag 计算属性', () => {
    expect(adjSrc).toContain('syncStateTag')
  })

  it('错误态呈现中文 danger tag，不 markSynced 静默', () => {
    // 错误来源：state 含 error 或 lastError 非空
    expect(adjSrc).toMatch(/lastError/)
    expect(adjSrc).toMatch(/type:\s*'danger'/)
    expect(adjSrc).toContain('同步失败')
    // 绝不静默把失败当成功（markSynced 是反模式）
    expect(adjSrc).not.toContain('markSynced')
  })
})

// ── 模式切换不发布 TB（Req 2.4）──────────────────────────────────────────
describe('模式切换不触发 TB 发布（Req 2.4 / AC-2.4）', () => {
  const switchBody = extractFunctionBody(adjSrc, 'switchMode')

  it('switchMode 函数体存在', () => {
    expect(switchBody.length).toBeGreaterThan(0)
  })

  it('switchMode 只调用 switchToOnlyOffice/switchToHtml，不调用 publishAdjudicated', () => {
    expect(switchBody).toMatch(/switchTo(OnlyOffice|Html)\s*\(/)
    expect(switchBody).not.toContain('publishAdjudicated')
  })

  it('editorMode setter（切换器 v-model）不调用 publishAdjudicated', () => {
    // editorMode 的 set 走 switchMode，绝不直连发布门
    const setIdx = adjSrc.indexOf('const editorMode')
    expect(setIdx).toBeGreaterThanOrEqual(0)
    const editorModeBlock = adjSrc.slice(setIdx, setIdx + 400)
    expect(editorModeBlock).not.toContain('publishAdjudicated')
    expect(editorModeBlock).toContain('switchMode')
  })

  it('publishAdjudicated 仍由确认审定按钮独立触发（发布门未被切换器吞掉）', () => {
    // 确认审定按钮显式绑定 publishAdjudicated（P0-3d 发布门保留）
    expect(adjSrc).toMatch(/@click="publishAdjudicated"/)
  })
})

// ── 宿主登记守卫：D4-1 必须进 isD4DedicatedSyncSheet ────────────────────────
describe('宿主 GtD4OperatingRevenue 必须把 D4-1 登记为 dedicated sync sheet', () => {
  function extractDedicatedList(src: string): string {
    const marker = 'const isD4DedicatedSyncSheet'
    const start = src.indexOf(marker)
    if (start < 0) return ''
    const lb = src.indexOf('[', start)
    const rb = src.indexOf(']', lb)
    if (lb < 0 || rb < 0) return ''
    return src.slice(lb, rb + 1)
  }

  it('宿主文件存在且定义了 isD4DedicatedSyncSheet', () => {
    expect(existsSync(HOST_PATH)).toBe(true)
    expect(hostSrc).toContain('isD4DedicatedSyncSheet')
  })

  it("dedicated 列表含 'D4-1'（防宿主叠加 legacy 双切换器）", () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).toContain("'D4-1'")
  })

  it('自检：抽取器真在承重（列表里没有的 code 抓不到）', () => {
    const list = extractDedicatedList(hostSrc)
    expect(list).not.toContain("'D4-99'")
  })
})

// ── 反向自检：抽取器/剥注释真在承重（防恒真）────────────────────────────────
describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useWorkpaperSyncBridge({ entryId: ref(D4_1_ENTRY), flushHtml: async () => {} })"
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })

  it('extractFunctionBody 抓到函数体并配平括号', () => {
    const stub = 'async function switchMode(t){ if(x){ await y() } return }'
    const body = extractFunctionBody(stub, 'switchMode')
    expect(body).toContain('await y()')
    expect(extractFunctionBody(stub, 'nope')).toBe('')
  })

  it('stripComments 剥掉注释里的反例', () => {
    const stub = 'const x = 1 // <GtOnlyOfficeSheet />\n/* ContentMutationService publishAdjudicated */'
    const out = stripComments(stub)
    expect(out).not.toContain('GtOnlyOfficeSheet')
    expect(out).not.toContain('ContentMutationService')
    expect(out).not.toContain('publishAdjudicated')
  })
})
