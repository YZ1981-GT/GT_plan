/**
 * B50 完成度纯函数守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 3
 * Property 24（B50 完成度三态与前后端同口径）/ Requirements 2.1–2.7
 *
 * 三组断言：
 * 1. 三态边界（含「导入了但一个都没评估」= partial 而非 not_started）
 * 2. 两侧归一化同口径（后端 `cells[*].rmm` / 前端 `cells[*].combinedRisk`）
 * 3. 🔴 与既有 `incompleteAccounts` 的口径差异钉死（防后续会话"统一"两者）
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  resolveB50Completeness,
  normalizeFromReader,
  normalizeFromMatrixRows,
  B50_COMPLETENESS_LABEL,
  B50_COMPLETENESS_TAG_TYPE,
  B50_COMPLETENESS_HINT,
  type B50NormalizedAccount,
} from '../b50Completeness'

// ── repoRoot：双哨兵具体文件向上查找（禁写死回退级数）─────────────────────
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'services', 'b50_risk_reader.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵：backend/app/services/b50_risk_reader.py + audit-platform/frontend/package.json）')
}

const ROOT = repoRoot()

function acc(account: string, hasAnyRmm: boolean): B50NormalizedAccount {
  return { account, hasAnyRmm }
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 三态边界
// ═══════════════════════════════════════════════════════════════════════════
describe('resolveB50Completeness 三态', () => {
  it('无科目 → not_started', () => {
    const r = resolveB50Completeness({ accounts: [] })
    expect(r.state).toBe('not_started')
    expect(r.importedCount).toBe(0)
    expect(r.assessedCount).toBe(0)
    expect(r.unassessedAccounts).toEqual([])
  })

  it('入参缺失/为 null 一律按 not_started（不抛错）', () => {
    expect(resolveB50Completeness(null).state).toBe('not_started')
    expect(resolveB50Completeness(undefined).state).toBe('not_started')
    expect(resolveB50Completeness({}).state).toBe('not_started')
    expect(resolveB50Completeness({ accounts: null }).state).toBe('not_started')
  })

  it('🔴 导入了但一个都没评估 → partial（不是 not_started）', () => {
    // 「未导入」与「导入了未评估」引导语不同：前者引导导入，后者引导逐科目评估。
    const r = resolveB50Completeness({ accounts: [acc('货币资金', false), acc('应收账款', false)] })
    expect(r.state).toBe('partial')
    expect(r.importedCount).toBe(2)
    expect(r.assessedCount).toBe(0)
    expect(r.unassessedAccounts).toEqual(['货币资金', '应收账款'])
  })

  it('部分评估 → partial，未评估清单准确且保持输入顺序', () => {
    const r = resolveB50Completeness({
      accounts: [acc('货币资金', true), acc('应收账款', false), acc('存货', true), acc('应付账款', false)],
    })
    expect(r.state).toBe('partial')
    expect(r.importedCount).toBe(4)
    expect(r.assessedCount).toBe(2)
    expect(r.unassessedAccounts).toEqual(['应收账款', '应付账款'])
  })

  it('全部评估 → completed，未评估清单为空', () => {
    const r = resolveB50Completeness({ accounts: [acc('货币资金', true), acc('存货', true)] })
    expect(r.state).toBe('completed')
    expect(r.assessedCount).toBe(2)
    expect(r.unassessedAccounts).toEqual([])
  })

  it('计数恒等式：importedCount === assessedCount + unassessedAccounts.length', () => {
    for (const accounts of [
      [],
      [acc('a', true)],
      [acc('a', false)],
      [acc('a', true), acc('b', false), acc('c', false)],
    ]) {
      const r = resolveB50Completeness({ accounts })
      expect(r.importedCount).toBe(r.assessedCount + r.unassessedAccounts.length)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 两侧归一化同口径
// ═══════════════════════════════════════════════════════════════════════════
describe('归一化：后端 reader 形态', () => {
  it('读 cells[*].rmm；至少一个合法等级即 hasAnyRmm', () => {
    const got = normalizeFromReader([
      { account: '货币资金', cells: { existence: { rmm: 'M', special: false } } },
      { account: '应收账款', cells: { existence: { rmm: null, special: true }, completeness: { rmm: 'H' } } },
      { account: '存货', cells: { existence: { rmm: null }, accuracy: { rmm: null } } },
      { account: '预付款项', cells: {} },
    ])
    expect(got).toEqual([
      { account: '货币资金', hasAnyRmm: true },
      { account: '应收账款', hasAnyRmm: true },
      { account: '存货', hasAnyRmm: false },
      { account: '预付款项', hasAnyRmm: false },
    ])
  })

  it('非法等级不算已评估（空串/0/未知字母）', () => {
    const got = normalizeFromReader([
      { account: 'a', cells: { existence: { rmm: '' } } },
      { account: 'b', cells: { existence: { rmm: 0 } } },
      { account: 'c', cells: { existence: { rmm: 'X' } } },
      { account: 'd', cells: { existence: { rmm: 'L' } } },
    ])
    expect(got.map(g => g.hasAnyRmm)).toEqual([false, false, false, true])
  })

  it('缺 account 的项被跳过；非数组入参返回空数组', () => {
    expect(normalizeFromReader([{ cells: { existence: { rmm: 'H' } } }])).toEqual([])
    expect(normalizeFromReader(null)).toEqual([])
    expect(normalizeFromReader(undefined)).toEqual([])
  })

  it('🔴 special 为真但 rmm 为空 ⇒ 仍算未评估（完成度只看 RMM）', () => {
    // 特别风险标记不代表已评估综合风险等级；裁剪的风险保护判据另读 has_special，
    // 与完成度是两件事。若这里把 special 也算进来，完成度会虚高。
    const got = normalizeFromReader([{ account: 'a', cells: { existence: { rmm: null, special: true } } }])
    expect(got[0].hasAnyRmm).toBe(false)
  })
})

describe('归一化：前端 matrix 形态', () => {
  it('读 cells[*].combinedRisk（字段名与后端不同）', () => {
    const got = normalizeFromMatrixRows([
      { name: '货币资金', cells: { existence: { combinedRisk: 'H' } } },
      { name: '存货', cells: { existence: { combinedRisk: null } } },
    ])
    expect(got).toEqual([
      { account: '货币资金', hasAnyRmm: true },
      { account: '存货', hasAnyRmm: false },
    ])
  })

  it('🔴 前端形态不得被后端归一化函数读出结果（字段名确实不同）', () => {
    // 这条断言的意义：若哪天有人把两个归一化函数合并成一个「兼容两种字段名」的版本，
    // 本断言会打红并提示——两侧字段名差异必须显式处理，不能靠 `rmm ?? combinedRisk`
    // 兜底（那会让"传错形态"以静默返回 false 的方式被掩盖）。
    const frontendShape = [{ name: '货币资金', cells: { existence: { combinedRisk: 'H' } } }]
    expect(normalizeFromReader(frontendShape as any)).toEqual([])
  })

  it('缺 name 的行被跳过；非数组返回空数组', () => {
    expect(normalizeFromMatrixRows([{ cells: { existence: { combinedRisk: 'H' } } }])).toEqual([])
    expect(normalizeFromMatrixRows(null)).toEqual([])
  })

  it('两侧等价数据经各自归一化后结果逐字相等（Property 24 同口径）', () => {
    const fromReader = normalizeFromReader([
      { account: '货币资金', cells: { existence: { rmm: 'M' } } },
      { account: '存货', cells: { existence: { rmm: null } } },
    ])
    const fromMatrix = normalizeFromMatrixRows([
      { name: '货币资金', cells: { existence: { combinedRisk: 'M' } } },
      { name: '存货', cells: { existence: { combinedRisk: null } } },
    ])
    expect(fromReader).toEqual(fromMatrix)
    expect(resolveB50Completeness({ accounts: fromReader })).toEqual(
      resolveB50Completeness({ accounts: fromMatrix }),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 🔴 与既有 incompleteAccounts 的口径差异钉死
// ═══════════════════════════════════════════════════════════════════════════
describe('与既有 incompleteAccounts 的口径差异', () => {
  const MATRIX = path.join(
    ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'composables', 'useB50RiskMatrix.ts',
  )

  it('既有 incompleteAccounts 仍是「任一认定为 null 即未填完」的严格口径', () => {
    const src = fs.readFileSync(MATRIX, 'utf-8')
    // 该实现形态若变化，本断言打红提醒复核两个口径是否仍然互补。
    expect(src).toMatch(/incompleteAccounts[\s\S]{0,400}?ASSERTIONS\.some\(\s*a\s*=>\s*row\.cells\[a\]\.combinedRisk\s*===\s*null\s*\)/)
  })

  it('🔴 同一份数据下两个口径结论不同（严格 vs 至少一个）', () => {
    // 只填了一个认定的科目：
    //   - 既有 incompleteAccounts 判它「未填完」（要六个认定全填）
    //   - 本模块判它「已评估」（裁剪只需 max_risk 可派生）
    // 两者同时成立，禁止统一。
    const rows = [{ name: '货币资金', cells: { existence: { combinedRisk: 'M' }, completeness: { combinedRisk: null } } }]

    // 重放既有严格口径
    const ASSERTIONS = ['existence', 'completeness', 'accuracy', 'cutoff', 'classification', 'presentation']
    const strictIncomplete = rows
      .filter(r => ASSERTIONS.some(a => (r.cells as any)[a]?.combinedRisk == null))
      .map(r => r.name)
    expect(strictIncomplete).toEqual(['货币资金'])

    // 本模块宽口径
    const r = resolveB50Completeness({ accounts: normalizeFromMatrixRows(rows) })
    expect(r.state).toBe('completed')
    expect(r.unassessedAccounts).toEqual([])
  })

  it('本模块源码不引用 incompleteAccounts / matrixStats（无双真源耦合）', () => {
    const src = fs.readFileSync(
      path.join(ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'composables', 'b50Completeness.ts'),
      'utf-8',
    )
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    expect(code).not.toContain('incompleteAccounts')
    expect(code).not.toContain('matrixStats')
    // 反向自检：剥注释确实生效（注释里提到过这两个名字）
    expect(src).toContain('incompleteAccounts')
  })

  it('纯函数无 Vue 依赖（源码不 import vue）', () => {
    const src = fs.readFileSync(
      path.join(ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'composables', 'b50Completeness.ts'),
      'utf-8',
    )
    expect(src).not.toMatch(/from\s+['"]vue['"]/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 展示常量（UI 全中文化 + 三态齐备）
// ═══════════════════════════════════════════════════════════════════════════
describe('展示常量', () => {
  const STATES = ['not_started', 'partial', 'completed'] as const

  it('三态标签/tag/引导语齐备且为中文', () => {
    for (const s of STATES) {
      expect(B50_COMPLETENESS_LABEL[s]).toMatch(/[\u4e00-\u9fa5]/)
      expect(B50_COMPLETENESS_HINT[s]).toMatch(/[\u4e00-\u9fa5]/)
      expect(B50_COMPLETENESS_TAG_TYPE[s]).toBeTruthy()
    }
    expect(Object.keys(B50_COMPLETENESS_LABEL).sort()).toEqual([...STATES].sort())
  })

  it('未开始用 info 不用 danger（待办不是错误）', () => {
    expect(B50_COMPLETENESS_TAG_TYPE.not_started).toBe('info')
    expect(B50_COMPLETENESS_TAG_TYPE.partial).toBe('warning')
    expect(B50_COMPLETENESS_TAG_TYPE.completed).toBe('success')
  })

  it('未开始的引导语指向既有导入入口（不新建导入能力）', () => {
    expect(B50_COMPLETENESS_HINT.not_started).toContain('试算表')
  })
})
