/**
 * 总体完整性核对 — 接线守卫（源码级）
 *
 * spec: voucher-sampling-reconcile-balance-source
 * Task 9
 *
 * 覆盖：
 * - composable conclusionBlockedSource 映射
 * - 引擎 confirmBlockedReason 按来源分文案
 * - 预览弹窗声明就地放行 props 与渲染块
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'

function findRepoRoot(): string {
  let dir = process.cwd()
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(dir, '.kiro', 'steering', 'memory.md'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根')
}

const REPO_ROOT = findRepoRoot()

function read(rel: string): string {
  return readFileSync(join(REPO_ROOT, rel), 'utf-8').replace(/\r\n/g, '\n')
}

const COMPOSABLE_SRC = read(
  'audit-platform/frontend/src/components/workpaper/composables/useVoucherSampling.ts',
)
const ENGINE_SRC = read(
  'audit-platform/frontend/src/components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue',
)
const PREVIEW_SRC = read(
  'audit-platform/frontend/src/components/workpaper/voucher-sampling/SamplingPreviewDialog.vue',
)

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

// ─── composable: conclusionBlockedSource ────────────────────────────────────

describe('conclusionBlockedSource 存在且映射正确', () => {
  const src = stripComments(COMPOSABLE_SRC)

  it('声明为 computed', () => {
    expect(src).toMatch(/const conclusionBlockedSource\s*=\s*computed/)
  })

  it('返回 reconcile 来源', () => {
    expect(src).toContain("return 'reconcile'")
  })

  it('在 return 列表中导出', () => {
    expect(src).toContain('conclusionBlockedSource')
    // 确认在 return { ... } 中
    const returnBlock = src.slice(src.lastIndexOf('return {'))
    expect(returnBlock).toContain('conclusionBlockedSource')
  })

  it('依赖 reconcileBlockedReason（与门控同链）', () => {
    // conclusionBlockedSource 的 computed 体内引用 reconcileBlockedReason
    const start = src.indexOf('const conclusionBlockedSource')
    const body = src.slice(start, start + 800)
    expect(body).toContain('reconcileBlockedReason')
  })
})

// ─── 引擎: confirmBlockedReason 按来源分文案 ────────────────────────────────

describe('引擎 confirmBlockedReason 按来源区分文案', () => {
  const src = stripComments(ENGINE_SRC)

  it('解构 conclusionBlockedSource', () => {
    expect(src).toContain('conclusionBlockedSource')
  })

  it('reconcile 来源不要求关闭预览', () => {
    // 找 confirmBlockedReason computed 体
    const match = src.match(/const confirmBlockedReason\s*=\s*computed[\s\S]{0,1500}?\n\}\)/)
    expect(match).not.toBeNull()
    const body = match![0]
    // reconcile 来源的文案不含「关闭本预览」
    expect(body).toContain("source === 'reconcile'")
    // reconcile 分支的文案
    // reconcile 分支到第一个 return 结束
    const branchStart = body.indexOf("source === 'reconcile'")
    const branchReturn = body.indexOf('return `', branchStart)
    const branchEnd = body.indexOf('\n', branchReturn)
    const reconcileBranch = body.slice(branchStart, branchEnd)
    expect(reconcileBranch).toContain('本窗口下方')
    expect(reconcileBranch).not.toContain('关闭本预览')
  })

  it('非 reconcile 来源仍要求关闭预览', () => {
    const match = src.match(/const confirmBlockedReason\s*=\s*computed[\s\S]{0,1500}?\n\}\)/)
    const body = match![0]
    // 默认分支（非 reconcile）仍含「关闭本预览」
    expect(body).toContain('关闭本预览')
  })
})

// ─── 引擎: 传参给预览弹窗 ──────────────────────────────────────────────────

describe('引擎向预览传核对 props', () => {
  it('传入 reconcile-issue', () => {
    expect(ENGINE_SRC).toContain(':reconcile-issue="reconcileIssue"')
  })

  it('传入 reconcile-override-reason', () => {
    expect(ENGINE_SRC).toContain(':reconcile-override-reason="reconcileOverrideReason"')
  })

  it('传入 reconcile-presets', () => {
    expect(ENGINE_SRC).toContain(':reconcile-presets="activeReconcilePresets"')
  })

  it('监听 update:reconcile-override-reason', () => {
    expect(ENGINE_SRC).toContain('@update:reconcile-override-reason=')
  })
})

// ─── 预览弹窗就地放行：行为由挂载测试覆盖 ────────────────────────────────────
// voucher-sampling/__tests__/SamplingPreviewDialog.reconcile.spec.ts（显示 / 预置理由 /
// 预览内填写 ≥10 字后确认填充变为可用）。此处只保留它测不到的一条：放行块有自己的样式
// —— scoped 样式不跨组件，引擎里的同名样式管不到预览弹窗。

describe('预览弹窗放行块样式不是孤儿', () => {
  it('放行块用到的类在预览弹窗自己的 <style scoped> 里都有定义', () => {
    const style = PREVIEW_SRC.slice(PREVIEW_SRC.indexOf('<style scoped>'))
    for (const cls of ['reconcile-override-inline', 'reconcile-override-head', 'reconcile-override-text', 'reconcile-presets', 'reconcile-override-foot']) {
      expect(PREVIEW_SRC, `模板未使用 ${cls}`).toContain(`class="${cls}"`)
      expect(style, `预览弹窗缺少 .${cls} 样式`).toMatch(new RegExp(`\\.${cls}\\s*\\{`))
    }
  })
})

// ─── 引擎: 核对逻辑改用新模块 ───────────────────────────────────────────────

describe('引擎核对逻辑改用新模块', () => {
  it('import resolvePopulationReconcile（别名 resolveReconcile）', () => {
    expect(ENGINE_SRC).toContain('resolvePopulationReconcile as resolveReconcile')
  })

  it('import describeReconcileIssue', () => {
    expect(ENGINE_SRC).toContain('describeReconcileIssue')
  })

  it('import reconcilePresetsFor', () => {
    expect(ENGINE_SRC).toContain('reconcilePresetsFor')
  })

  it('旧单值核对函数 reconcilePopulation 已从引擎移除（不再导入、不再调用）', () => {
    expect(ENGINE_SRC).not.toMatch(/import\s*\{[^}]*\breconcilePopulation\b[^}]*\}\s*from/)
    expect(ENGINE_SRC).not.toMatch(/\breconcilePopulation\s*\(/)
    // 仍保留的同模块导入（防止上面的断言因整行被删而空转）
    expect(ENGINE_SRC).toMatch(/import\s*\{\s*buildSamplingMemo\s*\}\s*from '\.\.\/composables\/useSamplingAlgorithms'/)
  })

  it('不再有 effectiveBookAmount computed', () => {
    expect(ENGINE_SRC).not.toContain('effectiveBookAmount')
  })

  it('预置理由改为动态 activeReconcilePresets', () => {
    expect(ENGINE_SRC).toContain('activeReconcilePresets')
    expect(ENGINE_SRC).not.toMatch(/const RECONCILE_PRESETS\s*=\s*\[/)
  })
})

// ─── 扫描面自检 ──────────────────────────────────────────────────────────────

describe('扫描面自检', () => {
  it('三个被扫文件都存在且非空', () => {
    expect(COMPOSABLE_SRC.length).toBeGreaterThan(1000)
    expect(ENGINE_SRC.length).toBeGreaterThan(1000)
    expect(PREVIEW_SRC.length).toBeGreaterThan(1000)
  })
})
