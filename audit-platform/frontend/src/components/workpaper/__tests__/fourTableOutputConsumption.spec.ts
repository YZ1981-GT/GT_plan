/**
 * 平台守卫：render 策略输出的**四表取数键**必须有前端消费点（Property 11）。
 *
 * spec: `.kiro/specs/n345-four-table-extraction-alignment/` R9.1
 *
 * 为什么需要
 * ----------
 * 「后端输出了但前端不读」是本平台反复出现的静默缺陷形态，编译与测试全绿：
 * - N3：`useN3FormData.selfLoad` 曾 `await api.get(...)` **把响应整个丢弃**
 *   → `trial_balance` / `formula_direction` / `n3_metadata` 三键零消费。
 * - N4：`N4TabAdjudication.vue` 的 seed 分支是**空 if 块**（只有注释）
 *   → `tb_values` 到了 composable 但从未进未审数。
 * - N5：后端两处 `get_active_filter` 签名错 → 输出恒 0/None，前端链路虽通却拿不到数。
 * - H1：`tb_source_codes` 输出后前端 grep 0 命中（memory 记为 dead output）。
 *
 * 本守卫从**后端策略源码**抽出四表键名，再在前端源码里找消费点，
 * 缺失即红（可登记豁免，但必须写理由）。
 *
 * 另断言共享件 `useLmnTbReconcile` 有真实消费方（Property 12）——
 * 它 78 行、专为 L/M/N 审定表设计，却长期 0 引用。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// 本文件位于 audit-platform/frontend/src/components/workpaper/__tests__/
const WORKPAPER_DIR = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(__dirname, '../../../../../..')
const STRATEGY_DIR = path.join(
  REPO_ROOT,
  'backend/app/routers/wp_render_strategies',
)

/** 被检查的循环 → 策略文件名 */
const CYCLES: Record<string, string> = {
  N1: '_n1_deferred_tax_assets.py',
  N3: '_n3_deferred_tax_liabilities.py',
  N4: '_n4_taxes_and_surcharges.py',
  N5: '_n5_income_tax_expense.py',
}

/** 四表取数相关键名（出现在 render 返回值里即需前端消费） */
const FOUR_TABLE_KEYS = [
  'trial_balance',
  'trial_balance_liability',
  'tb_values',
  'adjudication_prefill',
  'liability_prefill',
  'tb_source_codes',
]

/**
 * 豁免清单 —— **每条必须写理由**。
 * key 形如 `N3::formula_direction`。
 */
const EXEMPT: Readonly<Record<string, string>> = {}

function readFileSafe(p: string): string {
  try {
    return fs.readFileSync(p, 'utf-8')
  } catch {
    return ''
  }
}

/** 递归收集前端源码（.ts / .vue） */
function collectFrontendSources(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue
      collectFrontendSources(full, acc)
    } else if (/\.(ts|vue)$/.test(entry.name)) {
      acc.push(full)
    }
  }
  return acc
}

const FRONTEND_SOURCES = collectFrontendSources(WORKPAPER_DIR)
const FRONTEND_BLOB = FRONTEND_SOURCES.map((f) => readFileSafe(f)).join('\n')

/** 从策略源码抽出 render 返回的四表键（只认 `"key":` 形态的字典键） */
function emittedKeys(pySource: string): string[] {
  return FOUR_TABLE_KEYS.filter((k) =>
    new RegExp(`"${k}"\\s*:`).test(pySource),
  )
}

describe('四表取数输出消费性（Property 11）', () => {
  it('自检：策略文件存在且能抽出键名', () => {
    for (const [cycle, file] of Object.entries(CYCLES)) {
      const src = readFileSafe(path.join(STRATEGY_DIR, file))
      expect(src.length, `${cycle} 策略文件读不到：${file}`).toBeGreaterThan(500)
      expect(
        emittedKeys(src).length,
        `${cycle} 未抽出任何四表键 → 正则或返回结构变了`,
      ).toBeGreaterThan(0)
    }
  })

  it('自检：前端源码集合非空', () => {
    expect(FRONTEND_SOURCES.length).toBeGreaterThan(500)
    expect(FRONTEND_BLOB).toContain('useLmnTbReconcile')
  })

  it('每个四表键都有前端消费点（否则等于没做）', () => {
    const missing: string[] = []
    for (const [cycle, file] of Object.entries(CYCLES)) {
      const src = readFileSafe(path.join(STRATEGY_DIR, file))
      for (const key of emittedKeys(src)) {
        if (EXEMPT[`${cycle}::${key}`]) continue
        // 前端可能写 snake_case（读 html_data）或 camelCase（归一后的 ref）
        const camel = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
        if (FRONTEND_BLOB.includes(key) || FRONTEND_BLOB.includes(camel)) continue
        missing.push(`${cycle}::${key}`)
      }
    }
    expect(
      missing,
      `以下 render 输出键在前端零消费（dead output）：${missing.join(', ')}。`
        + '请接入或从 render 移除；确有理由保留则登记 EXEMPT 并写明原因。',
    ).toEqual([])
  })

  it('反向自检：不存在的键必然被判缺失（防断言空转）', () => {
    const bogus = '__definitely_not_a_real_key__'
    expect(FRONTEND_BLOB.includes(bogus)).toBe(false)
  })

  it('豁免清单每条都有理由', () => {
    for (const [k, reason] of Object.entries(EXEMPT)) {
      expect(String(reason).trim().length, `${k} 豁免缺理由`).toBeGreaterThan(10)
    }
  })
})

describe('useLmnTbReconcile 消费方（Property 12）', () => {
  const consumers = FRONTEND_SOURCES.filter(
    (f) =>
      !f.endsWith('useLmnTbReconcile.ts')
      && /\buseLmnTbReconcile\b/.test(readFileSafe(f)),
  )

  it('共享 TB 核对件必须有 ≥3 个消费方（N3/N4/N5 审定表）', () => {
    const names = consumers.map((f) => path.basename(f))
    expect(
      consumers.length,
      `useLmnTbReconcile 消费方不足（现 ${consumers.length}：${names.join(', ')}）。`
        + '该共享件 78 行、专为 L/M/N 审定表设计，曾长期 0 引用 —— 不要再让它闲置。',
    ).toBeGreaterThanOrEqual(3)
  })

  it('N3 / N4 / N5 审定表各自接入', () => {
    const names = consumers.map((f) => path.basename(f))
    for (const expected of [
      'N3TabAdjudication.vue',
      'N4TabAdjudication.vue',
      'N5TabAdjudication.vue',
    ]) {
      expect(names, `${expected} 未接入 TB 核对`).toContain(expected)
    }
  })
})

describe('N3 无披露 inert 残留（Property 13）', () => {
  const host = readFileSafe(path.join(WORKPAPER_DIR, 'GtN3DeferredTaxLiabilities.vue'))

  it('自检：宿主文件可读', () => {
    expect(host.length).toBeGreaterThan(1000)
  })

  it('sheet 分发与 isHtmlSheet 不得把「附注」判为 HTML 专属 sheet', () => {
    // 剥注释后再断言（宿主里有大段解释「为什么不认附注」的注释）
    const stripped = host
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
    expect(
      /return\s*'附注'/.test(stripped),
      'currentSheet 不应返回 \'附注\'（N3 源模板无披露 sheet，披露与 N1 共节）',
    ).toBe(false)
    expect(
      /===\s*'附注'/.test(stripped),
      'isHtmlSheet 不应把 \'附注\' 判为专属 sheet（否则渲染空白 Tab）',
    ).toBe(false)
  })

  it('自检：剥注释前宿主确实含解释性「附注」字样（证明剥注释有效）', () => {
    expect(host).toContain('附注')
  })
})
