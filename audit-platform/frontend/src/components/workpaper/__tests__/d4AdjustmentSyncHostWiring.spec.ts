/**
 * D4-4 调整分录汇总接桥 + 宿主登记 + 表格列完整性守卫。
 *
 * spec: d4-4-adjustment-summary-bidirectional-writeback · Task 13 / 13b
 * Requirements: 5.1/5.2（走统一 sync bridge 而非 legacy 单向）, 5.3/5.4（两处名单同批改）,
 *               5.6（flushHtml 先 flush 待存）, 2.5/5.7（UI 十列与模板/契约一致）
 *
 * 参照 `d4AdjudicationSyncHostWiring.spec.ts`（D4-1，同为 core 目录审定/调整类表）。
 *
 * 断言面：
 *  1. `D4TabAdjustment.vue` 消费 `useD4SyncMode`（禁自建/直连底层桥、禁裸 GtOnlyOfficeSheet）。
 *  2. sheetKey 走**具名常量** `D4_4_SHEET_KEY = 'd44-managed'`（内联字面量会让跨语言守卫失明）。
 *  3. `flushHtml` 内 `flushPendingSave()` **先于** `readStoreProjection`（debounce 2000ms，
 *     顺序反了会把用户最后一次编辑丢在 timer 里 ⇒ OO 侧看到旧值）。
 *  4. 挂载 `WorkpaperSyncEditorHost` 且包在 `.oo-container` 里（iframe 无内在高度）。
 *  5. 宿主 `isD4DedicatedSyncSheet` 含 `'D4-4'`，**且** `D4_LEGACY_OO_BLOCKED_SHEETS`
 *     **不含** `'D4-4'`（两处缺一即坏，见 Task 12）。
 *  6. 表格业务列恰 10 个且顺序与模板 A~J 一致（Task 13b）。
 *
 * 🔴 全部源码断言都先 `stripComments` —— 否则注释里写的反例/说明会被当成真实现
 *    （这是本仓库反复踩过的「文本匹配被注释骗过」，正反两向都出现过）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
const ADJ_PATH = resolve(_dir, '..', 'd4', 'core', 'D4TabAdjustment.vue')
const HOST_PATH = resolve(_dir, '..', 'GtD4OperatingRevenue.vue')
const CONST_PATH = resolve(_dir, '..', 'composables', 'd4Constants.ts')
const COMPOSABLE_PATH = resolve(_dir, '..', 'composables', 'useD4Adjustment.ts')

/** 后端 provider 的 `SHEET_KEY_D44` —— 两侧必须逐字相等。 */
const D4_4_SHEET_KEY = 'd44-managed'

/** 模板 A~J 十列对应的 UI 列标题（顺序即模板列序）。 */
const EXPECTED_COLUMN_LABELS = [
  '摘要',       // A description
  '分类',       // B category
  '报表项目',   // C reportItem
  '会计科目',   // D accountName
  '附注项目',   // E noteItem
  '补充说明',   // F placeholder  ← Task 13b 新增
  '借方',       // G debitAmount
  '贷方',       // H creditAmount
  '索引号',     // I indexRef
  '备注',       // J remark       ← Task 13b 新增
]

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}
/** 抽取 `useD4SyncMode({...})` 的调用体（括号配平，禁用 split 提前截断）。 */
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
/** 抽取某个具名数组/Set 字面量的内容（括号配平）。 */
function extractListAfter(src: string, marker: string): string {
  const start = src.indexOf(marker)
  if (start < 0) return ''
  const lb = src.indexOf('[', start)
  if (lb < 0) return ''
  const rb = src.indexOf(']', lb)
  return rb < 0 ? '' : src.slice(lb + 1, rb)
}

const adjSrc = existsSync(ADJ_PATH) ? stripComments(read(ADJ_PATH)) : ''
const hostSrc = existsSync(HOST_PATH) ? stripComments(read(HOST_PATH)) : ''
const constSrc = existsSync(CONST_PATH) ? stripComments(read(CONST_PATH)) : ''
const composableSrc = existsSync(COMPOSABLE_PATH) ? stripComments(read(COMPOSABLE_PATH)) : ''
const bridgeArgs = extractBridgeCallArgs(adjSrc)

// ── 自检（防恒真）：源码必须真读到了 ─────────────────────────────────────────
describe('守卫自检：四个源文件都真读到了', () => {
  it('文件存在且非空', () => {
    expect(existsSync(ADJ_PATH)).toBe(true)
    expect(adjSrc.length).toBeGreaterThan(1000)
    expect(hostSrc.length).toBeGreaterThan(1000)
    expect(constSrc.length).toBeGreaterThan(100)
    expect(composableSrc.length).toBeGreaterThan(500)
  })

  it('stripComments 真的剥掉了注释（否则下面的"不得出现"类断言会被注释骗过）', () => {
    // 🔴 样本串必须与保留内容**无共同字符**：首版用了单字母 `a`/`b`/`c`，而保留下来的
    //    `code` 里就含 `c` ⇒ 断言自撞打红。判据本身写错了，不是 stripComments 有问题。
    const sample = stripComments('/* BLOCKMARK */ KEEPME // LINEMARK\n<!-- HTMLMARK -->')
    expect(sample).not.toContain('BLOCKMARK')
    expect(sample).not.toContain('LINEMARK')
    expect(sample).not.toContain('HTMLMARK')
    expect(sample).toContain('KEEPME')
  })
})

// ── 1/2/3：接桥形态 ────────────────────────────────────────────────────────
describe('D4-4 必须消费平台 sync bridge（Req 5.1/5.2）', () => {
  it('调用共享 composable useD4SyncMode（禁自建 / 禁直连底层桥）', () => {
    expect(bridgeArgs.length).toBeGreaterThan(0)
    expect(adjSrc).not.toContain('useWorkpaperSyncBridge(')
    expect(adjSrc).not.toContain('ContentMutationService')
  })

  it('禁裸 GtOnlyOfficeSheet（那是 legacy 单向通道）', () => {
    expect(adjSrc).not.toContain('GtOnlyOfficeSheet')
  })

  it('sheetKey 走具名常量而非内联字面量', () => {
    expect(adjSrc).toContain(`const D4_4_SHEET_KEY = '${D4_4_SHEET_KEY}'`)
    // 调用体里必须用常量名传入
    expect(bridgeArgs).toContain('sheetKey: D4_4_SHEET_KEY')
    // 调用体里不得再出现内联字面量（会让跨语言守卫失明）
    expect(bridgeArgs).not.toContain(`'${D4_4_SHEET_KEY}'`)
  })

  it('flushHtml 内 flushPendingSave 先于 readStoreProjection（Req 5.6）', () => {
    const iFlush = bridgeArgs.indexOf('flushPendingSave')
    const iRead = bridgeArgs.indexOf('readStoreProjection')
    expect(iFlush).toBeGreaterThan(-1)
    expect(iRead).toBeGreaterThan(-1)
    expect(iFlush).toBeLessThan(iRead)
  })

  it('useD4Adjustment 真的导出了 flushPendingSave（否则上一条断言在测一个 undefined）', () => {
    expect(composableSrc).toContain('flushPendingSave')
    // debounce 仍是 2000ms —— 若被改小，flush 的必要性论证要重估
    expect(composableSrc).toContain('2000')
  })

  it('消费 composable 的 syncStateTag（fail-visible 统一实现，不在组件内重复文案）', () => {
    expect(adjSrc).toContain('syncStateTag')
  })
})

// ── 4：host 挂点 ──────────────────────────────────────────────────────────
describe('在线编辑挂 WorkpaperSyncEditorHost 且有确定高度容器', () => {
  it('挂载了 host 组件', () => {
    expect(adjSrc).toContain('WorkpaperSyncEditorHost')
    expect(adjSrc).toContain(':bridge="syncBridge"')
    expect(adjSrc).toContain(':descriptor="syncOoDescriptor"')
  })

  it('包在 .oo-container 里，且 CSS 给了确定高度（iframe 无内在高度）', () => {
    expect(adjSrc).toContain('class="oo-container"')
    expect(adjSrc).toMatch(/\.oo-container\s*\{[^}]*height/)
  })

  it('表格视图与在线编辑互斥渲染', () => {
    expect(adjSrc).toContain(`editorMode !== '在线编辑'`)
    expect(adjSrc).toContain(`editorMode === '在线编辑'`)
  })
})

// ── 5：两处名单必须同批（Task 12）──────────────────────────────────────────
describe('宿主登记与 legacy 禁入名单必须同批改（Req 5.3/5.4）', () => {
  it("isD4DedicatedSyncSheet 含 'D4-4'", () => {
    const list = extractListAfter(hostSrc, 'const isD4DedicatedSyncSheet')
    expect(list.length).toBeGreaterThan(0)
    expect(list).toContain("'D4-4'")
  })

  it("D4_LEGACY_OO_BLOCKED_SHEETS 不再含 'D4-4'（已接桥）", () => {
    const m = constSrc.match(/D4_LEGACY_OO_BLOCKED_SHEETS[^=]*=\s*new Set\(\[([^\]]*)\]/)
    expect(m).not.toBeNull()
    const members = m![1]
    expect(members).not.toContain("'D4-4'")
  })

  it("D4-5 仍在禁入名单（不得连带摘除）", () => {
    const m = constSrc.match(/D4_LEGACY_OO_BLOCKED_SHEETS[^=]*=\s*new Set\(\[([^\]]*)\]/)
    expect(m![1]).toContain("'D4-5'")
  })

  it('D4-4 已完成状态迁移：进 dedicated 且出 legacy 名单', () => {
    // 🔴 首版我写的是「两处不得有交集」——**那是我臆想的规则，实际设计不成立**：
    //    `D4-5` 刻意同时在两处（d4Constants.ts 注释明说它是「历史冗余项，已接子组件桥
    //    `d45-managed`，故实际不可能命中 legacy 分支」）。发明一条不存在的基准会把
    //    有意设计判成缺陷。本条收窄为只断言 D4-4 的迁移完成，D4-5 走下面的显式豁免。
    const dedicated = extractListAfter(hostSrc, 'const isD4DedicatedSyncSheet')
    const m = constSrc.match(/D4_LEGACY_OO_BLOCKED_SHEETS[^=]*=\s*new Set\(\[([^\]]*)\]/)
    expect(dedicated).toContain("'D4-4'")
    expect(m![1]).not.toContain("'D4-4'")
  })

  it('已知双重登记豁免：D4-5 —— 且反向断言它真的符合豁免条件', () => {
    // 豁免不能只写理由文本（那是加一行就变绿的后门），必须断言「它声称的条件真的成立」：
    // D4-5 之所以可以同时在两处，是因为它**已经接了子组件桥** `d45-managed`。
    const dedicated = extractListAfter(hostSrc, 'const isD4DedicatedSyncSheet')
    const m = constSrc.match(/D4_LEGACY_OO_BLOCKED_SHEETS[^=]*=\s*new Set\(\[([^\]]*)\]/)
    const blocked = (m?.[1] ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    const overlap = blocked.filter((code) => dedicated.includes(code))

    // 当前唯一允许的重叠项
    expect(overlap).toEqual(["'D4-5'"])

    // 反向断言：D4-5 真的已接桥（否则这条豁免就是在掩盖一个真缺陷）
    const policyPath = resolve(_dir, '..', 'd4', 'policy', 'D4TabPolicyCheck.vue')
    expect(existsSync(policyPath)).toBe(true)
    const policySrc = stripComments(read(policyPath))
    expect(policySrc).toContain('useD4SyncMode')
    expect(policySrc).toContain('d45-managed')
  })
})

// ── 6：表格十列（Task 13b）────────────────────────────────────────────────
describe('表格业务列必须与模板 A~J 十列一致（Req 2.5/5.7）', () => {
  /** 取模板里 el-table 内的业务列 label（排除 selection 与空 label 的操作列）。 */
  function businessColumnLabels(src: string): string[] {
    const labels: string[] = []
    const re = /<el-table-column\b([^>]*)>/g
    let m: RegExpExecArray | null
    while ((m = re.exec(src)) !== null) {
      const attrs = m[1]
      if (/type="selection"/.test(attrs)) continue
      const lm = attrs.match(/label="([^"]*)"/)
      if (!lm || lm[1] === '') continue
      labels.push(lm[1])
    }
    return labels
  }

  const labels = businessColumnLabels(adjSrc)

  it('恰 10 个业务列', () => {
    expect(labels).toHaveLength(EXPECTED_COLUMN_LABELS.length)
  })

  it('顺序与模板列序逐项一致', () => {
    expect(labels).toEqual(EXPECTED_COLUMN_LABELS)
  })

  it('补充说明(F) 与 备注(J) 两列真的绑到了字段而不只是占位属性', () => {
    // 🔴 同名陷阱：本文件有多处 `placeholder="…"` 是 el-input 的占位文本属性，
    //    与 `D4AdjustmentRow.placeholder` 字段无关。判据必须锚定 updateCell 的字段名参数。
    expect(adjSrc).toContain(`updateCell(row.rowId, 'placeholder', v)`)
    expect(adjSrc).toContain(`updateCell(row.rowId, 'remark', v)`)
    expect(adjSrc).toContain(':model-value="row.placeholder"')
    expect(adjSrc).toContain(':model-value="row.remark"')
  })

  it('十列全部有 updateCell 写入路径（列数-字段数对账，防将来加字段忘补 UI）', () => {
    const fields = [
      'description', 'category', 'reportItem', 'accountName', 'noteItem',
      'placeholder', 'debitAmount', 'creditAmount', 'indexRef', 'remark',
    ]
    expect(fields).toHaveLength(EXPECTED_COLUMN_LABELS.length)
    for (const f of fields) {
      expect(adjSrc).toContain(`updateCell(row.rowId, '${f}'`)
    }
  })

  it('变异反证：列标题抽取器对缺列样本会打红（证明非恒真）', () => {
    const mutated = adjSrc.replace(/<el-table-column label="备注"[\s\S]*?<\/el-table-column>/, '')
    const mutatedLabels = businessColumnLabels(mutated)
    expect(mutatedLabels).not.toEqual(EXPECTED_COLUMN_LABELS)
    expect(mutatedLabels).toHaveLength(EXPECTED_COLUMN_LABELS.length - 1)
  })
})
