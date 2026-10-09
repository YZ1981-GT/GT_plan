/**
 * L2 e2e 选格安全性守卫 —— 「行身份派生源字段不得被测试改写」
 *
 * 背景（2026-09-28 真栈实证的一串因果）：
 *   1. `useD4Adjudication.ts` 的 D4-1 派生行身份是 `xsheet-${section}-${labelKey(label)}`
 *      —— **行身份由业务字段 `label` 派生**。
 *   2. L2 验收 e2e（`d4-l2-oo-to-html-all` / `d4-l2-fast-batch`）会挑一个"安全格"写入标记值
 *      （`L2MARK-...`）再 forcesave，而其 `SKIP_KEYS` 当时**不含 `label`**。
 *   3. 于是测试改了 label ⇒ 行身份漂移 ⇒ xlsx 里多出一条 store 侧不存在的**孤儿行**。
 *   4. 此后所有 materialize 抛 `roundtrip_projection_mismatch`
 *      （「staged representation 反读出未提交的受管字段 …（共 338 个）」）⇒ **整个
 *      `xlsx/gt-d4-operating-revenue` entry 的在线编辑被打挂**，且污染写进 representation
 *      **不会自愈**，必须 `d43_rematerialize_dual_sheet.py --apply --force` 从权威模板重建。
 *
 * 所以这不是"测试留了脏数据"的卫生问题，而是**测试能把生产 entry 打挂**的问题。
 * 本守卫把不变量机器化：**凡被用作行身份派生源的字段，必须出现在两个 e2e 的 `SKIP_KEYS` 里**。
 * 判据从源码现算派生源（而非写死 `['label']`），这样将来新增别的派生源也会被抓。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const FE_ROOT = resolve(__dirname, '..', '..', '..', '..', '..')
const ADJUDICATION = resolve(__dirname, '..', 'useD4Adjudication.ts')
const L2_SPECS = [
  resolve(FE_ROOT, 'e2e', 'd4-l2-oo-to-html-all.spec.ts'),
  resolve(FE_ROOT, 'e2e', 'd4-l2-fast-batch.spec.ts'),
]

function read(p: string): string {
  return readFileSync(p, 'utf-8')
}

/**
 * 剥掉 `//` 行注释与 `/* *\/` 块注释后的代码。
 *
 * 必需：本守卫要断言「代码里不再有某个分支」，而解释该分支为何被移除的**注释里恰好引用了
 * 它的原文**。不剥注释的话断言会命中自己的注释而假红（本文件首版即如此）。
 * 这是仓库铁律「grep 命中后必须判注释/代码」的同型。
 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((ln) => !ln.trim().startsWith('//'))
    .map((ln) => ln.replace(/(?<![:'"`/])\/\/(?!\/).*$/, ''))
    .join('\n')
}

/** 从源码提取「赋给 rowKey/rowId 的模板串」里引用的业务字段名（= 身份派生源）。 */
function identitySourceFields(src: string): string[] {
  const out = new Set<string>()
  const assign = /(rowKey|rowId)\s*[:=]\s*`([^`]{0,200})`/g
  for (const m of src.matchAll(assign)) {
    for (const expr of m[2].matchAll(/\$\{([^}]+)\}/g)) {
      // `labelKey(label)` → 取括号内的字段名；裸 `${label}` → 直接取
      const inner = expr[1]
      const called = inner.match(/^\s*\w+\(\s*([A-Za-z_][\w.]*)\s*\)\s*$/)
      const raw = (called ? called[1] : inner).trim()
      // 只保留看起来是行字段的标识符（排除 section/常量/表达式/函数调用残留）
      const leaf = raw.split('.').pop() || ''
      if (/^[a-z][A-Za-z0-9_]*$/.test(leaf) && !['section', 'i', 'idx', 'n', 'prefix'].includes(leaf)) {
        out.add(leaf)
      }
    }
  }
  return [...out].sort()
}

/** 解析某个 e2e spec 的 SKIP_KEYS 集合。 */
function skipKeys(src: string): string[] {
  const m = src.match(/SKIP_KEYS\s*=\s*new Set\(\[([\s\S]*?)\]\)/)
  if (!m) return []
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]).sort()
}

describe('L2 e2e 不得改写行身份派生源字段', () => {
  const adjSrc = read(ADJUDICATION)

  it('守卫自检（防恒真）：能从 useD4Adjudication 提取到派生源字段', () => {
    // D4-1 派生行：`xsheet-${section}-${labelKey(label)}`
    expect(adjSrc).toMatch(/rowKey\s*=\s*`xsheet-\$\{section\}-\$\{labelKey\(label\)\}`/)
    const fields = identitySourceFields(adjSrc)
    expect(fields.length).toBeGreaterThan(0)
    expect(fields).toContain('label')
  })

  it('守卫自检（防恒真）：能解析出两个 e2e 的 SKIP_KEYS 且非空', () => {
    for (const p of L2_SPECS) {
      const keys = skipKeys(read(p))
      expect(keys.length, `${p} 的 SKIP_KEYS 解析为空`).toBeGreaterThan(3)
    }
  })

  it.each(L2_SPECS.map((p) => [p.split(/[\\/]/).pop() as string, p]))(
    '%s 的 SKIP_KEYS 覆盖全部行身份派生源',
    (_name, specPath) => {
      const required = identitySourceFields(adjSrc)
      const keys = skipKeys(read(specPath))
      const missing = required.filter((f) => !keys.includes(f.toLowerCase()))
      expect(
        missing,
        `SKIP_KEYS 缺少行身份派生源 ${JSON.stringify(missing)} —— 测试改这些列会造出孤儿行，` +
          '使整个 entry 的 materialize 抛 roundtrip_projection_mismatch',
      ).toEqual([])
    },
  )

  it.each(L2_SPECS.map((p) => [p.split(/[\\/]/).pop() as string, p]))(
    '%s 的 SKIP_KEYS 含 label（本次事故的直接触发列）',
    (_name, specPath) => {
      expect(skipKeys(read(specPath))).toContain('label')
    },
  )

  it('all 版不再在 amount 分支单独判 group_label（已并入 SKIP_KEYS，消除两分支口径不一致）', () => {
    const src = read(L2_SPECS[0])
    expect(skipKeys(src)).toContain('group_label')
    // 🔴 必须对**剥注释后**的代码断言：解释该分支为何移除的注释里引用了它的原文
    expect(stripComments(src)).not.toMatch(/colKey === 'group_label'/)
  })

  it('all 版有测试后还原（不还原会把 L2MARK 永久留在真实业务数据里）', () => {
    const code = stripComments(read(L2_SPECS[0]))
    expect(code).toMatch(/L2_NO_RESTORE/)
    expect(code).toMatch(/restored/)
    // 还原必须真的写回 oldValue 并再 forcesave 一次，不能只记个标志
    expect(code).toMatch(/typeIntoOoCell\(page,\s*String\(locate\.target\),\s*String\(oldValue\)\)/)
    expect(code).toMatch(/wp-sync-host-forcesave/)
  })
})
