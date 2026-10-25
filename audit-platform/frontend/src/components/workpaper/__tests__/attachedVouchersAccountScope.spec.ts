/**
 * 挂凭回拉（路径 B）守卫 —— spec `voucher-sampling-account-scope-and-attach-closure` 阶段 1。
 *
 * 🔴 路径 B 与路径 A 的科目关联机制不同：
 *
 *   路径 A（抽凭引擎）在**查询阶段**按科目筛，样本行天然是该科目的分录。
 *   路径 B（序时账挂凭）回拉时取**整张凭证的全部分录**，再由前端按底稿科目前缀挑出
 *   「本科目那条」。两处缺陷：
 *
 *   ① `if (picked.length === 0) picked = lines`
 *      筛不到本底稿科目就**回退取全部分录** ⇒ 用户挂错底稿时，整张凭证所有科目的
 *      分录都被灌进底稿，且无任何提示（静默错误数据）。
 *
 *   ② `sampled_vouchers.account_code`（用户挂凭时所在行的科目 = 挂凭意图）
 *      只用于兜底显示，**不参与筛选** ⇒ 用户明确在「1002 银行存款」那行挂的，
 *      这个意图被丢弃，改用底稿硬编码前缀。
 *
 * 正确优先级（spec R3.1）：① 底稿科目前缀 → ② 挂凭意图 → ③ 判「挂错底稿」不产样本。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const COMPOSABLES = path.resolve(__dirname, '../composables')
const ATTACHED = path.join(COMPOSABLES, 'useAttachedVouchers.ts')

/** 剔注释（同 samplingAccountCodeSource 的理由：说明性注释含被禁形态） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
    .replace(/([^:])\/\/[^\n'"`]*$/gm, '$1')
}

const RAW = fs.readFileSync(ATTACHED, 'utf-8')
const SRC = stripComments(RAW)

/** 取 pullSamplesForWorkpaper 的函数体（按花括号配对，避免溢出到下一个函数） */
function pullSamplesBody(src: string): string {
  const start = src.indexOf('export async function pullSamplesForWorkpaper')
  if (start < 0) return ''
  let depth = 0
  let i = src.indexOf('{', start)
  const from = i
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(from, i + 1)
    }
  }
  return src.slice(from)
}

const BODY = pullSamplesBody(SRC)

describe('useAttachedVouchers 扫描面自检', () => {
  it('能取到 pullSamplesForWorkpaper 函数体（否则全部断言空转）', () => {
    expect(BODY.length, '截不到函数体 ⇒ 判据失效').toBeGreaterThan(200)
    expect(BODY).toContain('listAttachedVouchers')
  })

  it('剔注释器自检：注释里的被禁形态被剔、代码保留', () => {
    const sample = [
      '// 🔴 缺陷①：if (picked.length === 0) picked = lines',
      'const picked = lines.filter(x => x)',
    ].join('\n')
    const out = stripComments(sample)
    expect(out).not.toContain('缺陷①')
    expect(out, '剔过度 ⇒ 主断言空转').toContain('lines.filter')
  })
})

// ─── 1.4 禁「筛空回退取全部」──────────────────────────────────────────────

describe('路径 B：不得在筛空时回退取全部分录（spec R6.5 / R3.4）', () => {
  it('🔴 不得出现 `picked.length === 0` 后把 lines 整体赋给 picked', () => {
    // 形态：picked.length === 0 ... picked = lines（允许中间有空白/换行，但不跨语句块）
    const bad = /picked\.length\s*===\s*0\s*\)?\s*picked\s*=\s*lines\s*[;\n]/.test(BODY)
    expect(
      bad,
      '检测到「筛空回退取全部」：用户挂错底稿时会把整张凭证所有科目的分录灌进底稿，' +
        '且无提示。正确做法见 spec R3.1 三级优先级：底稿前缀 → 挂凭意图 → 判挂错底稿（不产样本）。',
    ).toBe(false)
  })

  it('🔴 反向自检：判据能抓到该形态（否则上一条是假绿）', () => {
    const sample = 'let picked = lines.filter(f)\n    if (picked.length === 0) picked = lines\n'
    expect(/picked\.length\s*===\s*0\s*\)?\s*picked\s*=\s*lines\s*[;\n]/.test(sample)).toBe(true)
  })

  it('挂凭意图（rec.account_code）必须参与筛选，而非仅兜底显示', () => {
    // 判据：account_code 出现在 filter/匹配上下文，而不只是出现在 makeSample 的实参里
    const usedInFilter =
      /lineMatchesAccounts\([^)]*rec\.account_code/.test(BODY) ||
      /filter\([^)]*rec\.account_code/.test(BODY) ||
      /rec\.account_code[^\n]*filter/.test(BODY) ||
      /intentPrefixes|attachIntent|intentCodes/.test(BODY)
    expect(
      usedInFilter,
      'rec.account_code（用户挂凭时所在行的科目=挂凭意图）未参与筛选。' +
        '用户明确在某科目行挂的凭证，该意图不应被丢弃（spec R3.1 第 ② 级）。',
    ).toBe(true)
  })

  it('必须产出「挂错底稿」清单（misattached）供 UI 提示', () => {
    expect(
      /misattached/.test(SRC),
      '缺 misattached 返回项：三级筛选全空时应把凭证计入该清单并汇总提示，' +
        '而不是静默丢弃或灌入错科目（spec R3.4 / R3.5）。',
    ).toBe(true)
  })

  it('穿透失败（lines 为空）与业务错挂必须可区分', () => {
    // 技术失败仍保留占位样本；业务错挂进 misattached
    expect(
      /lines\.length\s*===\s*0|!lines\.length/.test(BODY),
      '未显式区分 lines 为空（穿透失败，保留占位样本）与三级筛选全空（业务错挂）' +
        '⇒ 两类问题在提示上不可分（spec R3.6）。',
    ).toBe(true)
  })
})

// ─── 1.3 accountPrefixes 禁数组字面量 ─────────────────────────────────────

describe('路径 B：accountPrefixes 实参不得为数组字面量（spec R6.4 / R4.1）', () => {
  /** 递归收集 .vue / .ts（排除测试文件自身） */
  function collect(dir: string): string[] {
    const out: string[] = []
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) {
        if (e.name === '__tests__' || e.name === 'node_modules') continue
        out.push(...collect(p))
      } else if (e.name.endsWith('.vue') || e.name.endsWith('.ts')) out.push(p)
    }
    return out
  }

  const WP_ROOT = path.resolve(__dirname, '..')
  const CALLERS = collect(WP_ROOT)
    .map((f) => ({
      file: path.relative(WP_ROOT, f).replace(/\\/g, '/'),
      src: stripComments(fs.readFileSync(f, 'utf-8')),
    }))
    .filter((f) => f.src.includes('pullSamplesForWorkpaper') && !f.file.includes('useAttachedVouchers'))

  it('扫描面非空（现算应有 1 个消费端 E1TabLargeCheck）', () => {
    expect(CALLERS.length, '扫不到 pullSamplesForWorkpaper 的调用方').toBeGreaterThan(0)
  })

  it('🔴 调用方传的 accountPrefixes 不得是内联数组字面量', () => {
    const offenders: string[] = []
    for (const c of CALLERS) {
      // 形态一：pullSamplesForWorkpaper(a, b, c, ['1001','1002'])
      if (/pullSamplesForWorkpaper\([^)]*\[\s*['"]\d/.test(c.src)) {
        offenders.push(`${c.file}（实参内联数组）`)
      }
      // 形态二：const X = ['1001','1002'] 然后传 X
      const constArr = c.src.match(/(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*\[\s*['"]\d[^\]]*\]/g)
      if (constArr) {
        for (const decl of constArr) {
          const name = decl.match(/(?:const|let)\s+(\w+)/)![1]
          if (new RegExp(`pullSamplesForWorkpaper\\([^)]*\\b${name}\\b`, 's').test(c.src)) {
            offenders.push(`${c.file}（${name} = 数字数组字面量）`)
          }
        }
      }
    }
    expect(
      offenders,
      'accountPrefixes 必须与路径 A 的科目码同源（对应 *AccountScope.ts），' +
        '否则两条路径会对「本底稿是什么科目」给出不同答案：\n  ' + offenders.join('\n  '),
    ).toEqual([])
  })

  it('🔴 反向自检：能抓到两种字面量形态', () => {
    const bad1 = "await pullSamplesForWorkpaper(pid, y, wp, ['1001','1002'])"
    expect(/pullSamplesForWorkpaper\([^)]*\[\s*['"]\d/.test(bad1)).toBe(true)
    const bad2 = "const MF = ['1001','1002']\nawait pullSamplesForWorkpaper(pid, y, wp, MF)"
    const name = bad2.match(/(?:const|let)\s+(\w+)/)![1]
    expect(new RegExp(`pullSamplesForWorkpaper\\([^)]*\\b${name}\\b`, 's').test(bad2)).toBe(true)
  })
})
