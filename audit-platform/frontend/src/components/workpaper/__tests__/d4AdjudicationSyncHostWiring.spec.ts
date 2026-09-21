/**
 * D4-1 审定表接桥 + 宿主登记守卫（Task 10）—— 参照 d4InspectionSyncHostWiring.spec.ts。
 *
 * spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 10
 * Requirements: 5.1（双向链路走统一 sync bridge 而非 legacy 单向）, 2.4（模式切换不发布 TB）
 *
 * 2026-09-21 治本改造后更新：D4-1 的接桥不再直接调 `useWorkpaperSyncBridge`，而是
 * 通过共享 composable `useD4SyncMode`（见 `d4/composables/useD4SyncMode.ts`）——
 * entryId/capability/健康门禁/switchMode/fail-visible tag 的**实现细节**已内聚到该
 * composable 内部（并由 `useD4SyncMode.spec.ts` 单独守卫），组件源码里不再重复出现
 * 这些字面量。本守卫因此改为断言：
 *  1. D4TabAdjudication.vue 消费 `useD4SyncMode`（禁自建/直连底层桥）。
 *  2. sheetKey 走具名常量（不得内联字面量，防跨语言/跨组件漂移）。
 *  3. flushHtml 内 flushPendingSave 先于 readStoreProjection（防投影旧值）。
 *  4. 宿主 GtD4OperatingRevenue.vue 的 isD4DedicatedSyncSheet 含 'D4-1'。
 *  5. 消费 composable 导出的 syncStateTag（fail-visible 由 useD4SyncMode 统一实现，
 *     不在本组件内重复 danger tag 文案——重复即技术债，交叉验证见 useD4SyncMode.spec.ts）。
 *  6. 模式切换器（editorMode，双向绑定 composable computed）不出现在
 *     publishAdjudicated 调用体内；确认审定按钮独立绑定 publishAdjudicated
 *     （Req 2.4：切模式不发布 TB —— 组件里已没有自己的 switchMode，
 *     该函数认不到 publishAdjudicated 这个符号，天然不可能调用它）。
 *  7. 挂载 WorkpaperSyncEditorHost，不得再挂裸 GtOnlyOfficeSheet。
 *
 * 反向自检（变异守卫）：若 'D4-1' 从 dedicated 列表移除、或 sheetKey 变成内联字面量、
 * 或 publishAdjudicated 被拖进切换逻辑，则相应断言转红。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const ADJ_PATH = resolve(_dir, '..', 'd4', 'core', 'D4TabAdjudication.vue')
const HOST_PATH = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')

const D4_1_SHEET_KEY = 'd41-managed'

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}
/** 抽取 useD4SyncMode({...}) 的调用体（括号配平）。 */
function extractBridgeCallArgs(src: string): string {
  const marker = 'useD4SyncMode('
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

const adjSrc = existsSync(ADJ_PATH) ? stripComments(read(ADJ_PATH)) : ''
const hostSrc = existsSync(HOST_PATH) ? stripComments(read(HOST_PATH)) : ''
const bridgeArgs = extractBridgeCallArgs(adjSrc)

// ── D4TabAdjudication 接桥守卫 ──────────────────────────────────────────────
describe('D4-1 审定表必须消费平台 sync bridge（Req 5.1）', () => {
  it('D4TabAdjudication.vue 存在', () => {
    expect(existsSync(ADJ_PATH)).toBe(true)
  })

  it('调用了共享 composable useD4SyncMode（禁自建同步 composable / 禁直连底层桥）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    // 直连底层桥或 spec 草案臆想的服务名，组件层不得再直接引用
    expect(adjSrc).not.toContain('useWorkpaperSyncBridge(')
    expect(adjSrc).not.toContain('ContentMutationService')
  })

  it('sheetKey 走具名常量（不得内联字面量，防跨语言/跨组件漂移）', () => {
    expect(adjSrc).toContain(`= '${D4_1_SHEET_KEY}'`)
    expect(bridgeArgs).toMatch(/sheetKey:\s*D4_1_SHEET_KEY\b/)
    // 桥参数里不得再出现裸字面量 sheetKey（应始终引用常量）
    expect(bridgeArgs).not.toMatch(new RegExp(`sheetKey:\\s*['"]${D4_1_SHEET_KEY}['"]`))
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
describe('D4-1 同步失败必须 fail-visible（消费共享 composable 的中文 danger tag）', () => {
  it('消费 composable 导出的 syncStateTag（不自行重复 danger 文案 —— 那是技术债，实现细节交 useD4SyncMode.spec.ts 守）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    expect(adjSrc).toMatch(/syncStateTag/)
    // 组件模板必须渲染该 tag（否则失败态对用户不可见）
    expect(adjSrc).toMatch(/syncStateTag\.type/)
    expect(adjSrc).toMatch(/syncStateTag\.text/)
  })

  it('不得绕过共享 composable 自行 markSynced 静默吞错', () => {
    expect(adjSrc).not.toContain('markSynced')
  })
})

// ── 模式切换不发布 TB（Req 2.4）──────────────────────────────────────────
describe('模式切换不触发 TB 发布（Req 2.4 / AC-2.4）', () => {
  it('组件内已没有自建 switchMode（切换逻辑收敛进 useD4SyncMode，天然认不到 publishAdjudicated）', () => {
    // 治本改造后组件不再自己定义 switchMode；若将来漂移回自建切换逻辑，本断言会先转红，
    // 提示需要同步检查它是否又混进了 publishAdjudicated（Req 2.4 的真正判据见下一条）。
    expect(adjSrc).not.toMatch(/function\s+switchMode\s*\(/)
  })

  it('editorMode（切换器 v-model，绑定 composable 返回值）所在声明处不直连 publishAdjudicated', () => {
    const declIdx = adjSrc.indexOf('editorMode')
    expect(declIdx).toBeGreaterThanOrEqual(0)
    // useD4SyncMode(...) 整个调用体内不得出现 publishAdjudicated（发布门与切换器物理隔离）
    expect(bridgeArgs).not.toContain('publishAdjudicated')
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
    const stub = "const b = useD4SyncMode({ sheetKey: D4_1_SHEET_KEY, flushHtml: async () => {} })"
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })

  it('stripComments 剥掉注释里的反例', () => {
    const stub = 'const x = 1 // <GtOnlyOfficeSheet />\n/* ContentMutationService publishAdjudicated */'
    const out = stripComments(stub)
    expect(out).not.toContain('GtOnlyOfficeSheet')
    expect(out).not.toContain('ContentMutationService')
    expect(out).not.toContain('publishAdjudicated')
  })
})
