/**
 * Property 15：受管 sheet 集合**从 provider 派生** + `capability`/`sheetKey` 走 Ref。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Task 22 · Property 15
 *
 * ═══ 这条 Property 在防什么 ═══
 *
 * 三个宿主原来把受管 sheet 写死成一张：
 *   `const D5_MANAGED_SHEET_KEY = 'd52-managed'` + `currentSheet === 'D5-2'`
 * 而 provider 侧受管区已扩到 **D5 3 张 / D6 7 张 / D7 6 张**。写死的后果是两个：
 *   ① 其余受管 sheet 在前端进不了在线编辑通道（声明层扩了、UI 不认）；
 *   ② 更隐蔽 —— `flushHtml` 回传的 `sheetKey` 也是那个字面量，而桥内是
 *      `flushed.sheetKey ?? sheetKey()`（**flushed 优先**）⇒ 无论用户在哪张受管 sheet，
 *      编辑都会 materialize 进 `d52-managed`。受管集合一旦 >1 张这就是**写错受管区**。
 *
 * ═══ 下发通道的裁决（原 tasks.md 把这条列为「卡设计裁决」）═══
 *
 * 结论：**不加端点、不改 render-config、不扩 155-entry 的共享 manifest**，
 * 新建专用生成产物 `workpaperSyncManagedSheets.generated.ts`，取数链三段全是既有真源：
 *   `DELIVERED_PER_ENTRY_CONTRACTS` → contract_id → `contract_path_for` → 契约
 *   → `sheets[].{sheet_key, excel_name}`
 * 🔴 该链**不依赖 adapter 是否注册**（登记行里 `adapter_registered` 是独立字段，
 *    三家当前均为 False）——「契约已交付」与「adapter 已注册」是两个分母。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  WORKPAPER_SYNC_MANAGED_SHEETS,
  managedSheetsForEntry,
} from '../workpaperSyncManagedSheets.generated'
import { resolveD5SheetCode } from '../../composables/useD5SheetRouting'
import { resolveD6SheetCode } from '../../composables/useD6SheetRouting'
import { resolveD7SheetCode } from '../../composables/useD7SheetRouting'

const WORKPAPER_ROOT = resolve(__dirname, '../..')
const src = (rel: string) => readFileSync(resolve(WORKPAPER_ROOT, rel), 'utf-8')

/**
 * 剔掉注释后的源码 —— 判「代码是否真做了 X」**必须**先剔注释。
 *
 * 🔴 两个方向都会被骗（本文件首跑就撞了第一个）：
 *   · **假阳**：注释里写「改造前是 `const D5_MANAGED_SHEET_KEY = 'd52-managed'`」这类
 *     对照说明，会被「仍有写死常量」判据命中；
 *   · **假阴**：docstring 里声称「已接 X」而代码没接，会被「已接」判据命中。
 * 本项目已把这条记成纪律（同族教训：鉴权基线守卫用文本匹配，6 处摘掉依赖后 3 处仍全绿）。
 *
 * 局限如实登记：这是正则剔注释，不是 AST。它不处理「字符串字面量里含 `//`」这种情形；
 * 本文件的判据对象（常量声明 / `computed(` / `sheetKey:` 键名）都不在该盲区内。
 */
function codeOnly(text: string): string {
  return text
    .replace(/<!--[\s\S]*?-->/g, '') // Vue 模板注释
    .replace(/\/\*[\s\S]*?\*\//g, '') // 块注释（含 docstring）
    .replace(/(^|[^:])\/\/.*$/gm, '$1') // 行注释（`://` 不误伤 URL）
}

/** 三家宿主：entry_id / 宿主文件 / 该循环的页签码归一函数 / 现算受管张数下限。 */
const HOSTS = [
  {
    label: 'D5',
    entryId: 'xlsx/gt-d5-receivables-financing',
    file: 'GtD5ReceivablesFinancing.vue',
    resolveCode: resolveD5SheetCode,
    legacySingleKey: 'd52-managed',
  },
  {
    label: 'D6',
    entryId: 'xlsx/gt-d6-contract-assets',
    file: 'GtD6ContractAssets.vue',
    resolveCode: resolveD6SheetCode,
    legacySingleKey: 'd62-managed',
  },
  {
    label: 'D7',
    entryId: 'xlsx/gt-d7-contract-liabilities',
    file: 'GtD7ContractLiabilities.vue',
    resolveCode: resolveD7SheetCode,
    legacySingleKey: 'd72-managed',
  },
] as const

// ═══════════════════════════════════════════════════════════════════════════
// 一、生成产物本身可用（下发通道成立）
// **Validates: Requirements 8.1（Property 15）**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 15 ①：受管清单生成产物', () => {
  it('产物非空且每条都带 contractId / managedSheets（空分母即判据失效）', () => {
    expect(WORKPAPER_SYNC_MANAGED_SHEETS.length).toBeGreaterThan(0)
    for (const e of WORKPAPER_SYNC_MANAGED_SHEETS) {
      expect(e.entryId, 'entryId 为空').toBeTruthy()
      expect(e.contractId, `${e.entryId} contractId 为空`).toBeTruthy()
      expect(e.managedSheets.length, `${e.entryId} 无受管 sheet`).toBeGreaterThan(0)
      for (const s of e.managedSheets) {
        expect(s.sheetKey, `${e.entryId} sheetKey 为空`).toBeTruthy()
        expect(s.excelName, `${e.entryId}/${s.sheetKey} excelName 为空`).toBeTruthy()
      }
    }
  })

  it('🔴 受管清单与 adapter 注册状态是两个分母（三家 adapterRegistered=false 仍有清单）', () => {
    // 这条是裁决的核心：若受管清单被 adapter 注册状态门控，三家现在就拿不到清单，
    // Property 15 也就无法在 adapter 注册前交付。
    for (const { entryId } of HOSTS) {
      const e = WORKPAPER_SYNC_MANAGED_SHEETS.find((x) => x.entryId === entryId)
      expect(e, `${entryId} 不在受管清单产物里`).toBeDefined()
      expect(e!.adapterRegistered, `${entryId} adapterRegistered 现状变了（登记前提需复核）`).toBe(false)
      expect(e!.managedSheets.length, `${entryId} 因 adapter 未注册而拿不到清单 ⇒ 两分母被混成一个门`).toBeGreaterThan(0)
    }
  })

  it('未登记 entry 返回空数组（fail-closed 为「无受管 sheet」而非抛错）', () => {
    expect(managedSheetsForEntry('xlsx/does-not-exist')).toEqual([])
    expect(managedSheetsForEntry('')).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 二、三家受管集合真的 > 1 张，且页签码可解析
// **Validates: Requirements 8.1**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 15 ②：三家受管集合从 provider 派生', () => {
  it.each(HOSTS)('$label 受管 sheet 多于一张（改造前只认一张）', ({ entryId, legacySingleKey }) => {
    const sheets = managedSheetsForEntry(entryId)
    expect(sheets.length, `${entryId} 受管张数应 >1，实得 ${sheets.length}`).toBeGreaterThan(1)
    // 原来那张仍在集合内（不是把它换掉，是把集合补全）。
    expect(sheets.map((s) => s.sheetKey)).toContain(legacySingleKey)
  })

  it.each(HOSTS)('$label 每张受管 sheet 的 excelName 都能被本循环归一函数解析成页签码', ({
    entryId,
    resolveCode,
    label,
  }) => {
    const sheets = managedSheetsForEntry(entryId)
    const codes = sheets.map((s) => resolveCode(s.excelName))
    for (const [i, code] of codes.entries()) {
      expect(code, `${label}/${sheets[i].sheetKey}（${sheets[i].excelName}）归一不出页签码`).toBeTruthy()
    }
    // 🔴 页签码必须互不相同 —— 撞码会让 Map 里后者顶掉前者、悄悄丢一张受管 sheet。
    expect(new Set(codes).size, `${label} 页签码有重复：${codes.join(',')}`).toBe(codes.length)
  })

  it('🔴 excelName 不可用字符串推演代替（d51-managed 的真实名无 `-1` 后缀）', () => {
    // 裁决 G3 的具体反例：按 `d51-managed` 推演成 `审定表D5-1` 会 sheet 找不到，
    // 真实名是 `审定表D5`。本条把这个反例钉死，防有人把产物换成拼字符串。
    const d5 = managedSheetsForEntry('xlsx/gt-d5-receivables-financing')
    const adj = d5.find((s) => s.sheetKey === 'd51-managed')
    expect(adj, 'd51-managed 不在 D5 受管清单里').toBeDefined()
    expect(adj!.excelName).toBe('审定表D5')
    expect(adj!.excelName).not.toBe('审定表D5-1')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 三、宿主接线（源码级）：不得留写死的单张受管键
// **Validates: Requirements 8.1**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 15 ③：宿主接线', () => {
  it.each(HOSTS)('$label 宿主从生成产物取受管集合', ({ file }) => {
    const code = codeOnly(src(file))
    expect(code, '未 import 受管清单产物').toContain(
      "import { managedSheetsForEntry } from './sync/workpaperSyncManagedSheets.generated'",
    )
    expect(code, '未调用 managedSheetsForEntry').toContain('managedSheetsForEntry(')
  })

  it.each(HOSTS)('🔴 $label 宿主不再写死单张受管键常量', ({ file, label, legacySingleKey }) => {
    // 🔴 必须剔注释：文件里有「改造前是 const D*_MANAGED_SHEET_KEY = '...'」这类对照说明，
    //    不剔会把注释判成代码（本判据首跑就是这样假阳的）。
    const code = codeOnly(src(file))
    expect(
      code.includes(`const D${label[1]}_MANAGED_SHEET_KEY`),
      `${label} 仍有写死的 D*_MANAGED_SHEET_KEY 常量`,
    ).toBe(false)
    // 字面量本身也不该再出现在宿主**代码**里（它现在只应来自生成产物）。
    expect(code.includes(`'${legacySingleKey}'`), `${label} 仍内联 ${legacySingleKey} 字面量`).toBe(
      false,
    )
  })

  it.each(HOSTS)('🔴 $label 的 syncSheetKey 是 computed 而非一次性 ref', ({ file, label }) => {
    const code = codeOnly(src(file))
    expect(code, `${label} syncSheetKey 仍是 ref(...) ⇒ 切 sheet 后指向旧受管区`).not.toMatch(
      /const syncSheetKey = ref\(/,
    )
    expect(code, `${label} syncSheetKey 未改成 computed`).toMatch(/const syncSheetKey = computed\(/)
  })

  it.each(HOSTS)(
    '🔴 $label 的 flushHtml 回传当前 sheet 的键（桥内 flushed 优先，写死会写错受管区）',
    ({ file, label }) => {
      const code = codeOnly(src(file))
      expect(code, `${label} flushHtml 未回传 syncSheetKey.value`).toContain(
        'sheetKey: syncSheetKey.value',
      )
    },
  )

  it.each(HOSTS)('$label 的 isD*DetailSheet 由受管集合判定，不再比单张页签码', ({ file, label }) => {
    const code = codeOnly(src(file))
    const n = label[1]
    expect(
      code,
      `${label} isD${n}DetailSheet 仍写死比较单张页签码`,
    ).not.toMatch(new RegExp(`isD${n}DetailSheet = computed\\(\\(\\) => currentSheet\\.value === `))
    expect(code).toMatch(new RegExp(`D${n}_MANAGED_SHEET_BY_CODE\\.has\\(currentSheet\\.value\\)`))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 四、桥的 capability 支持 Ref，且读取收口在单一入口
// **Validates: Requirements 8.1**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 15 ④：桥的 capability 读 Ref', () => {
  const BRIDGE = 'sync/useWorkpaperSyncBridge.ts'

  it('options.capability 类型接受值 / Ref / ComputedRef（向后兼容）', () => {
    const code = src(BRIDGE)
    expect(code).toMatch(/readonly capability:\s*\n?\s*\|?\s*WorkpaperSyncCapability/)
    expect(code).toContain('Ref<WorkpaperSyncCapability>')
    expect(code).toContain('ComputedRef<WorkpaperSyncCapability>')
  })

  it('🔴 capability 读取收口在 capabilityOf()（一处忘了 unref 会静默拒绝 OO）', () => {
    // 这里**故意不剔注释**：要按「capabilityOf() 内 / 外」切片，剔注释会打乱下标。
    // 切片本身已把 capabilityOf() 的 docstring 划进 helper 段，等效排除。
    const code = src(BRIDGE)
    // 除 capabilityOf() 自身（含其 docstring 举例）外，不得再有 options.capability 读取。
    const helperStart = code.indexOf('function capabilityOf()')
    expect(helperStart, 'capabilityOf() 不存在').toBeGreaterThan(-1)
    const docStart = code.lastIndexOf('/**', helperStart)
    const helperEnd = code.indexOf('\n  }', helperStart)
    const helper = code.slice(docStart, helperEnd)
    const outside = code.slice(0, docStart) + code.slice(helperEnd)
    // 声明处（options 接口）不算读取 —— 它是 `readonly capability:` 而非 `options.capability`。
    expect(
      outside.includes('options.capability'),
      'capabilityOf() 之外仍有 options.capability 读取 ⇒ 未收口',
    ).toBe(false)
    expect(helper).toContain('unref(options.capability)')
  })

  it('sheetKey 入参类型接受 ComputedRef（宿主现在传的就是 computed）', () => {
    const code = src(BRIDGE)
    expect(code).toMatch(/readonly sheetKey\?:\s*Ref<string>\s*\|\s*ComputedRef<string>/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 五、变异自检：判据有牙齿
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 15 变异自检', () => {
  it('🔴 若某宿主退回写死单张，③ 组的两条判据必红（形态自检）', () => {
    // 用真实宿主源码构造变异体（不改盘上文件），复算同一判定。
    const mutated = codeOnly(src('GtD5ReceivablesFinancing.vue'))
      .replace(/const syncSheetKey = computed\(/, 'const syncSheetKey = ref(')
      .replace(/sheetKey: syncSheetKey\.value/, "sheetKey: 'd52-managed'")
    expect(mutated).toMatch(/const syncSheetKey = ref\(/) // ③ 的 ref 判据会红
    expect(mutated.includes('sheetKey: syncSheetKey.value')).toBe(false) // flushHtml 判据会红
  })

  it('🔴 受管张数判据不是恒真：若清单被截成一张，② 组必红', () => {
    const sheets = managedSheetsForEntry('xlsx/gt-d5-receivables-financing')
    expect(sheets.length).toBeGreaterThan(1)
    const truncated = sheets.slice(0, 1)
    expect(truncated.length > 1, '截成一张后仍判 >1 ⇒ 判据无鉴别力').toBe(false)
  })
})
