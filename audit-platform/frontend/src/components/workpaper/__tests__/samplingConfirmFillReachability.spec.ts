/**
 * samplingConfirmFillReachability.spec.ts — 「确认填充」门控可达性守卫
 *
 * 背景（2026-08-04 浏览器实测）：R18.7 结论确认门禁本身是审计逻辑正确的
 * （已推断出总体结论但未经审计师确认时不得定稿回填），但它的**呈现方式**让用户
 * 无从下手：审计师勾完样本点「确认填充」，只弹一条 warning、预览弹窗照旧开着，
 * 而提示里指向的「错报推断与总体结论」区在弹窗背后（带遮罩）既看不到也点不到 ——
 * 四张登记表全 0 行、无任何可操作出口。这是「链条上游合格、整条链仍是死的」的变种。
 *
 * 三条不变式（全部读源码，因为它们是模板级/时序级事实，纯函数测不到）：
 * - P1 门控**前置**为 disabled + tooltip，而不是点了才拦
 * - P2 门控真被命中时**必须关闭预览弹窗**，否则提示是死信
 * - P3 关闭之后**必须有重开通路**，否则用户只能「重抽」（换种子、打断批次留痕）
 *
 * 每条都配反向自检：把源码替换成修复前的写法时判定必须为违规。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数；哨兵不能是目录） ────────

function findRepoRoot(): string {
  let dir = process.cwd()
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(dir, '.kiro', 'steering', 'memory.md'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根（哨兵 .kiro/steering/memory.md）')
}

const REPO_ROOT = findRepoRoot()
const ENGINE_DIR = join(
  REPO_ROOT, 'audit-platform', 'frontend', 'src',
  'components', 'workpaper', 'voucher-sampling',
)
const ENGINE = join(ENGINE_DIR, 'GtVoucherSamplingEngine.vue')
const PREVIEW = join(ENGINE_DIR, 'SamplingPreviewDialog.vue')

function read(p: string): string {
  return readFileSync(p, 'utf-8')
}

const engineSrc = read(ENGINE)
const previewSrc = read(PREVIEW)

/** 按花括号配对截取函数体（避开参数里的内联类型字面量：先用圆括号配对跳过参数列表） */
function functionBody(src: string, name: string): string {
  const decl = new RegExp(
    `(?:function\\s+${name}\\s*\\(|(?:const|let|var)\\s+${name}\\s*=\\s*(?:async\\s*)?\\()`,
  )
  const m = decl.exec(src)
  if (!m) throw new Error(`未找到函数 ${name}（守卫正则失效或函数已改名）`)
  let paren = 1
  let i = m.index + m[0].length
  for (; i < src.length && paren > 0; i++) {
    if (src[i] === '(') paren++
    else if (src[i] === ')') paren--
  }
  const open = src.indexOf('{', i)
  if (open < 0) throw new Error(`未找到 ${name} 的函数体`)
  let depth = 0
  for (let k = open; k < src.length; k++) {
    if (src[k] === '{') depth++
    else if (src[k] === '}') {
      depth--
      if (depth === 0) return src.slice(open, k + 1)
    }
  }
  throw new Error(`${name} 的函数体括号不配对`)
}

// ─── 判定纯函数（供反向自检拿替身源码复现修复前行为） ────────────────────────

/** P1：预览弹窗的确认按钮已按门控原因 disabled，且 tooltip 展示原因 */
function previewGatesConfirmUpfront(src: string): boolean {
  const hasProp = /confirmBlockedReason\??\s*:/.test(src)
  const hasDisabled = /:disabled="isConfirmBlocked"/.test(src)
  const hasTooltip =
    /<el-tooltip[\s\S]{0,240}:disabled="!isConfirmBlocked"[\s\S]{0,240}:content="confirmBlockedReason/.test(src)
  return hasProp && hasDisabled && hasTooltip
}

/** P1b：弹窗自身也兜住（旧调用点不传 prop 时不能照旧 emit） */
function previewConfirmHasFallbackGuard(src: string): boolean {
  const body = functionBody(src, 'handleConfirm')
  return /isConfirmBlocked\.value/.test(body) && /return/.test(body)
}

/** P2：引擎的门控分支必须先关预览再提示 */
function engineClosesPreviewOnBlock(src: string): boolean {
  const body = functionBody(src, 'handleConfirmFill')
  const iClose = body.indexOf('previewVisible.value = false')
  const iWarn = body.search(/ElMessage\.warning/)
  if (iClose < 0 || iWarn < 0) return false
  return iClose < iWarn
}

/** P3：存在重开预览的通路（按钮 + 处理器），且它不走重抽 */
function engineHasReopenPath(src: string): boolean {
  const hasBtn = /data-testid="reopen-sampling-preview"/.test(src)
  if (!hasBtn) return false
  const body = functionBody(src, 'handleReopenPreview')
  // 必须直接把预览打开，且**不得**调用重抽（重抽会换种子、打断批次留痕）
  return /previewVisible\.value = true/.test(body) && !/\bresample\b/.test(body)
}

// ─── Property 22：确认填充门控必须前置为 disabled ────────────────────────────

describe('Property 22：结论确认门禁前置为 disabled + tooltip', () => {
  it('预览弹窗声明 confirmBlockedReason 并据它 disabled + tooltip 说明原因', () => {
    expect(previewGatesConfirmUpfront(previewSrc)).toBe(true)
  })

  it('弹窗内 handleConfirm 自带兜底门控（旧调用点不传 prop 时也不 emit）', () => {
    expect(previewConfirmHasFallbackGuard(previewSrc)).toBe(true)
  })

  it('缺省 confirmBlockedReason 为 null（未传 prop 的调用点行为逐字等价）', () => {
    expect(/confirmBlockedReason:\s*null/.test(previewSrc)).toBe(true)
  })

  it('反向自检：删掉 disabled 绑定后判定必须为违规', () => {
    const mutated = previewSrc.replace(':disabled="isConfirmBlocked"', '')
    expect(previewGatesConfirmUpfront(mutated)).toBe(false)
  })

  it('反向自检：handleConfirm 去掉兜底门控后判定必须为违规', () => {
    const mutated = previewSrc.replace(
      /function handleConfirm\(\)[\s\S]*?\n\}/,
      'function handleConfirm() {\n  emit(\'confirm\')\n}',
    )
    expect(previewConfirmHasFallbackGuard(mutated)).toBe(false)
  })
})

// ─── Property 23：门控命中必须关闭预览（否则提示是死信） ─────────────────────

describe('Property 23：门控命中先关预览再提示', () => {
  it('handleConfirmFill 的门控分支先 previewVisible=false 再 ElMessage.warning', () => {
    expect(engineClosesPreviewOnBlock(engineSrc)).toBe(true)
  })

  it('门控提示指向具体动作（区名 + 确认按钮 + 回来的入口）', () => {
    const reason = engineSrc.match(/confirmBlockedReason\s*=\s*computed[\s\S]{0,700}?\n\}\)/)
    expect(reason).not.toBeNull()
    const text = reason![0]
    expect(text).toContain('错报推断与总体结论')
    expect(text).toContain('确认采用此结论')
    expect(text).toContain('继续填充')
  })

  it('提示里的区名与模板里的实际标题逐字一致（防文案漂移成指不到的区）', () => {
    const titles = [...engineSrc.matchAll(/class="misstatement-title">([^<]+)</g)].map(
      (m) => m[1].trim(),
    )
    expect(titles.length).toBeGreaterThan(0)
    expect(titles).toContain('错报推断与总体结论')
  })

  it('反向自检：还原成「只 warning 不关弹窗」后判定必须为违规', () => {
    const mutated = engineSrc.replace(
      /if \(confirmBlockedReason\.value\) \{[\s\S]*?\n  \}/,
      'if (confirmBlockedReason.value) {\n    ElMessage.warning(confirmBlockedReason.value)\n    return\n  }',
    )
    expect(engineClosesPreviewOnBlock(mutated)).toBe(false)
  })
})

// ─── Property 24：关闭后必须能重开（不靠重抽） ───────────────────────────────

describe('Property 24：预览有重开通路，不必重抽', () => {
  it('操作栏有「继续填充」按钮 + handleReopenPreview 直接打开预览', () => {
    expect(engineHasReopenPath(engineSrc)).toBe(true)
  })

  it('重开按钮仅在「有样本且预览已关」时出现（避免与预览并存）', () => {
    expect(engineSrc).toMatch(
      /v-if="sampledVouchers\.length > 0 && !previewVisible"[\s\S]{0,240}reopen-sampling-preview/,
    )
  })

  it('重开不改动样本集合与种子（源码级：处理器体内不得写 sampledVouchers/seed）', () => {
    const body = functionBody(engineSrc, 'handleReopenPreview')
    expect(body).not.toMatch(/sampledVouchers\.value\s*=/)
    expect(body).not.toMatch(/seedUsed\.value\s*=/)
  })

  it('反向自检：去掉重开按钮后判定必须为违规', () => {
    const mutated = engineSrc.replace('data-testid="reopen-sampling-preview"', '')
    expect(engineHasReopenPath(mutated)).toBe(false)
  })

  it('反向自检：重开处理器改为走重抽后判定必须为违规', () => {
    const mutated = engineSrc.replace(
      /function handleReopenPreview\(\)[\s\S]*?\n\}/,
      'function handleReopenPreview() {\n  resample()\n  previewVisible.value = true\n}',
    )
    expect(engineHasReopenPath(mutated)).toBe(false)
  })
})

// ─── 扫描面自检 ──────────────────────────────────────────────────────────────

describe('扫描面自检', () => {
  it('两个被扫文件都存在且非空（防路径写错导致守卫空转）', () => {
    expect(engineSrc.length).toBeGreaterThan(2000)
    expect(previewSrc.length).toBeGreaterThan(2000)
  })

  it('functionBody 对不存在的函数必须抛错（防解析失效变成静默通过）', () => {
    expect(() => functionBody(engineSrc, 'thisFunctionDoesNotExist')).toThrow()
  })
})
