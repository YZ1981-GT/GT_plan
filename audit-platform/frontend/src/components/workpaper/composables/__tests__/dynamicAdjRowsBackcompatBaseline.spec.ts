/**
 * P10 零回归基线：共享件 `serializeRows` 的**既有行为**与消费方边界快照。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 3
 * Requirements 4.3 · Property 10
 *
 * ═══ 这条判据钉的是什么 ═══
 *
 * 任务 8 要给 `serializeRows` 增加「把 `valueFields` 一并落进行对象」的能力（新签名
 * `serializeRows(rows, { readField })`）。需求 4.3 要求：**不改动 D1/J1 等未使用
 * per-field 金额模型的消费方的行为**。
 *
 * D1（`useD1DetailCategory`）自带另一套 `serializeRows`、零引用本共享件，所以真正需要
 * 锁死的是两件事：
 *   ① 共享件 `serializeRows` 在**不传 readField**（＝旧调用方式）时，输出与今天逐字节相同
 *      —— 这是「向后兼容」最直接的判据。K2/D4 之外没有第三个消费方，若新增能力污染了
 *      默认路径，本快照必红。
 *   ② `shared/dynamicAdjudicationRows` 的**运行时**消费方边界恰为 { useD4Adjudication,
 *      useK2Adjudication }。新增第三个 import 方 = 有人把共享层改动带到了预期之外的地方，
 *      必须显式确认（改这条断言）而不是悄悄扩散。
 *
 * 用**替身 spec `XX-9`**（与任何真实循环无关）驱动，与既有 `dynamicAdjudicationRows.spec.ts`
 * 同款——它是「非参与消费方」的干净代理：既不带 D4 的 6 金额、也不带 K2 的字段集。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { serializeRows, type DynamicAdjRow, type DynamicRowsSpec } from '../shared/dynamicAdjudicationRows'

const SPEC: DynamicRowsSpec = {
  prefix: 'XX-9',
  legacyRows: [],
  valueFields: ['unadj', 'aje', 'rje'],
}

/** 替身行：既有 serializeRows 只落 rowId/label/source/accountCode 四键。 */
const ROWS: DynamicAdjRow[] = [
  { rowId: 'r-1', label: '甲类', source: 'manual', accountCode: '1122' },
  { rowId: 'r-2', label: '乙类', source: 'tb', accountCode: '1123' },
  { rowId: 'r-3', label: '丙类（无科目码）', source: 'manual' },
]

describe('P10 共享件 serializeRows 向后兼容基线', () => {
  it('不传 readField 时输出为既有四键形态（逐字节冻结）', () => {
    const out = serializeRows(ROWS)
    // 🔴 冻结当前实现的确切字符串。任务 8 加 valueFields 能力后，
    //    「不传 readField」这条路径的输出必须一字不差 —— 变了就是污染了默认行为。
    const expected = JSON.stringify([
      { rowId: 'r-1', label: '甲类', source: 'manual', accountCode: '1122' },
      { rowId: 'r-2', label: '乙类', source: 'tb', accountCode: '1123' },
      { rowId: 'r-3', label: '丙类（无科目码）', source: 'manual' },
    ])
    expect(out).toBe(expected)
  })

  it('不传 readField 时不落任何 valueFields 键（派生列读时推导）', () => {
    const parsed = JSON.parse(serializeRows(ROWS)) as Array<Record<string, unknown>>
    for (const row of parsed) {
      for (const f of SPEC.valueFields) {
        expect(row).not.toHaveProperty(f)
      }
    }
  })
})

describe('P10 共享件运行时消费方边界', () => {
  it('运行时消费方恰为 useD4Adjudication / useK2Adjudication', () => {
    // 扫 composables 目录下**运行时** import（值 import，非 `import type`）本共享件的文件。
    const dir = resolve(__dirname, '..')
    const files = [
      'useD4Adjudication.ts',
      'useK2Adjudication.ts',
      'd4AdjudicationRows.ts',
      'k2AdjudicationRows.ts',
    ]
    const valueImporters: string[] = []
    for (const f of files) {
      const src = readFileSync(resolve(dir, f), 'utf-8')
      // 匹配 `from './shared/dynamicAdjudicationRows'` 且**不是** `import type { ... } from`
      const importsShared = /from\s+['"]\.\/shared\/dynamicAdjudicationRows['"]/.test(src)
      if (!importsShared) continue
      const typeOnly = /import\s+type\s+\{[^}]*\}\s+from\s+['"]\.\/shared\/dynamicAdjudicationRows['"]/.test(src)
      const hasValueImport = /(^|\n)\s*import\s+\{[^}]*\}\s+from\s+['"]\.\/shared\/dynamicAdjudicationRows['"]/.test(src)
      if (hasValueImport && !typeOnly) valueImporters.push(f)
      else if (importsShared && !typeOnly && !hasValueImport) {
        // 混合 import（既有 type 又有值），也算运行时消费方
        valueImporters.push(f)
      }
    }
    // d4/k2AdjudicationRows.ts 只 import type ⇒ 不算运行时消费方。
    expect(valueImporters.sort()).toEqual(['useD4Adjudication.ts', 'useK2Adjudication.ts'])
  })
})
