/**
 * 共享回填函数接入守卫（spec voucher-identity-writeback-and-audit-phase 任务 10~13，需求 4.7、6.5，design §4）
 *
 * 扫全部抽凭引擎宿主（模板里挂 `<GtVoucherSamplingEngine`）与挂凭导入宿主（调 `pullSamplesForWorkpaper`）。
 * 宿主连同它 import 的本地组合式函数（两层：截止测试宿主经 useI2Cutoff / useI6Cutoff 包装 useCycleCutoff；
 * 共享回填模块 shared/voucherCheckFill.ts 本身不算 —— 它定义了 useVoucherCheckFill / withRowMeta，算进来会让只 import
 * 它的类型的宿主被误判为已接入），须同时满足：
 * - 调 `useVoucherCheckFill`（回填、挂凭导入、撤销都走共享函数，ADR-VK-07 / 08）；
 * - 不再调 `expandMultiAccountVouchers`（展开只按后端配对结果，`prepareSamples`）；
 * - 解析 / 保存经 `withRowMeta` 透传行元数据 `_gt`（需求 4.1）；
 * - 表格有阶段 / 来源标签列（`VoucherRowMetaCell` 或 `VoucherRowMetaTag`，需求 4.8；表格在宿主直接 import 的
 *   本地子组件里也算，如 D2 的矩阵 / 卡片视图；抽凭共享组件目录 voucher-sampling/ 不算）；
 * - 引擎标签上不传 `phase`（阶段取项目当前阶段，需求 6.2 / 6.5），接了 `@undo-request`（撤销按批次删行）。
 * 不满足的宿主必须在冻结清单 `FROZEN` 里；清单只许删（接入一个删一个，已接入的还在清单里同样打红），交付时为空。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

function findRepoRoot(): string {
  const SENTINEL = join('backend', 'app', 'routers', 'voucher_sampling.py')
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(join(dir, SENTINEL))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error('未找到仓库根（哨兵 backend/app/routers/voucher_sampling.py）')
}

const SRC = join(findRepoRoot(), 'audit-platform', 'frontend', 'src')
const read = (p: string) => readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
const rel = (p: string) => relative(SRC, p).replace(/\\/g, '/')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '__tests__') continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(vue|ts)$/.test(name) && !/\.spec\.ts$/.test(name) && !name.endsWith('.d.ts')) out.push(p)
  }
  return out
}

/**
 * 宿主模板里引擎的标签名：组件名本身，或 import / defineAsyncComponent 起的别名（各带短横线写法）。
 * G3-4 期后收回以别名 `SamplingEngine` 异步引入，只认 `<GtVoucherSamplingEngine` 会漏扫。
 */
export function engineTagNames(text: string): string[] {
  const names = new Set<string>(['GtVoucherSamplingEngine'])
  const src = String.raw`['"][^'"]*GtVoucherSamplingEngine(?:\.vue)?['"]`
  for (const m of text.matchAll(new RegExp(String.raw`import\s+(\w+)\s+from\s+` + src, 'g'))) names.add(m[1])
  for (const m of text.matchAll(new RegExp(
    String.raw`(?:const|let)\s+(\w+)\s*=\s*defineAsyncComponent\(\s*(?:\(\)\s*=>\s*)?import\(\s*` + src, 'g',
  ))) names.add(m[1])
  const kebab = [...names].map(n => n.replace(/(?<!^)([A-Z])/g, '-$1').toLowerCase())
  return [...names, ...kebab]
}

/** 宿主模板里每个引擎标签的属性串 */
export function engineTagAttrs(text: string): string[] {
  const out: string[] = []
  for (const name of engineTagNames(text)) {
    for (const m of text.matchAll(new RegExp(`<${name}(?![\\w-])([\\s\\S]*?)\\/?>`, 'g'))) out.push(m[1])
  }
  return out
}
/** 相对路径与 `@/`（= src/）别名导入的整条语句（导入子句里不跨引号 / 分号，免得从上一条非本地导入一路吞过来） */
const LOCAL_IMPORT = /import\s+([^'";]*?)\s+from\s+'((?:\.{1,2}|@)\/[^']+)'/g

/** 只导入类型（`import type {…}`，或说明符全带 `type`）：编译后擦除，不执行 */
function isTypeOnly(clause: string): boolean {
  if (/^type\s/.test(clause.trim())) return true
  const braces = /^\{([\s\S]*)\}$/.exec(clause.trim())
  if (!braces) return false
  const specs = braces[1].split(',').map(s => s.trim()).filter(Boolean)
  return specs.length > 0 && specs.every(s => /^type\s/.test(s))
}

/** 本地值导入的路径（类型导入不算：组合式函数链只跟会执行的模块） */
export function valueImportPaths(text: string): string[] {
  return [...text.matchAll(LOCAL_IMPORT)].filter(m => !isTypeOnly(m[1])).map(m => m[2])
}

/** 动态引入的本地 .vue（`defineAsyncComponent(() => import('./X.vue'))`；K8-6 / K8-7 的分段表格这样引入） */
const DYNAMIC_VUE_IMPORT = /\bimport\(\s*'((?:\.{1,2}|@)\/[^']+\.vue)'\s*\)/g
export function dynamicVueImportPaths(text: string): string[] {
  return [...text.matchAll(DYNAMIC_VUE_IMPORT)].map(m => m[1])
}

/** 宿主直接 import 的本地文件（一层）：.ts 是组合式函数（通常在这一层接入），.vue 是表格子组件 */
function localImports(file: string, text: string, ext: '.ts' | '.vue'): string[] {
  const out: string[] = []
  const paths = ext === '.vue' ? [...valueImportPaths(text), ...dynamicVueImportPaths(text)] : valueImportPaths(text)
  for (const path of paths) {
    const base = path.startsWith('@/') ? join(SRC, path.slice(2)) : resolve(dirname(file), path)
    const cands = ext === '.ts' ? [base, `${base}.ts`, join(base, 'index.ts')] : [base]
    for (const cand of cands) {
      try {
        if (statSync(cand).isFile() && cand.endsWith(ext)) {
          out.push(cand)
          break
        }
      } catch { /* 不存在 */ }
    }
  }
  // 抽凭共享组件（引擎、标签列组件本身）不算宿主的表格子组件
  return ext === '.vue' ? out.filter(p => !rel(p).startsWith('components/workpaper/voucher-sampling/')) : out
}

/** 一个宿主未满足的接入要求（空 = 已接入）；childTexts：宿主直接 import 的本地表格子组件 */
export function adoptionProblems(hostText: string, chainTexts: string[], childTexts: string[] = []): string[] {
  const chain = [hostText, ...chainTexts]
  const problems: string[] = []
  if (!chain.some(t => /\buseVoucherCheckFill\s*[<(]/.test(t))) problems.push('未接入 useVoucherCheckFill')
  // 调用可带类型参数（withRowMeta<Row>(...)）
  if (chain.some(t => /\bexpandMultiAccountVouchers\s*[<(]/.test(t))) problems.push('仍调用 expandMultiAccountVouchers')
  if (!chain.some(t => /\bwithRowMeta\s*[<(]/.test(t))) problems.push('解析 / 保存未经 withRowMeta 透传行元数据')
  if (![hostText, ...childTexts].some(t => /<VoucherRowMeta(Cell|Tag)\b/.test(t))) problems.push('表格缺阶段 / 来源标签列')
  for (const attrs of engineTagAttrs(hostText)) {
    if (/(^|\s)(:|v-bind:)?phase\s*=/.test(attrs)) problems.push('给引擎传 phase（阶段取项目当前阶段）')
    if (!/@undo-request\s*=/.test(attrs)) problems.push('引擎未接 @undo-request（撤销按批次删行）')
  }
  return problems
}

const SHARED_FILL = 'components/workpaper/composables/shared/voucherCheckFill.ts'

/** 宿主 import 的本地组合式函数两层（不含共享回填模块本身） */
export function localComposableChain(file: string, text: string): string[] {
  const notShared = (p: string) => rel(p) !== SHARED_FILL
  const first = localImports(file, text, '.ts').filter(notShared)
  const second = first.flatMap(p => localImports(p, read(p), '.ts')).filter(notShared)
  return [...new Set([...first, ...second])]
}

function scanHosts(): Map<string, string[]> {
  const verdicts = new Map<string, string[]>()
  for (const file of walk(SRC)) {
    const text = read(file)
    const isEngineHost = file.endsWith('.vue') && engineTagAttrs(text).length > 0
    const isAttachHost = /\bpullSamplesForWorkpaper\s*\(/.test(text) && !/export async function pullSamplesForWorkpaper/.test(text)
    if (!isEngineHost && !isAttachHost) continue
    verdicts.set(rel(file), adoptionProblems(
      text, localComposableChain(file, text).map(read), localImports(file, text, '.vue').map(read),
    ))
  }
  return verdicts
}

/**
 * 冻结清单：尚未接入共享回填函数的宿主（只许删，交付时为空）。
 * 任务 10 接入 D、E 循环；11 F、G；12 H、I；13 J、K、M、N —— 已清空，不许再加。
 */
const FROZEN: readonly string[] = []

/**
 * 全仓零挂载的引擎宿主（死代码）：不接入，但每次核验仍无人挂载 —— 一旦被 import / 在模板里用到就必须接入并删去此项。
 * F2ValuationTestSheet 不删：F 循环冻结 slice（workpaper_sync_f_cycle_manifest_slice.json）与后端路由基线快照仍引用其文件。
 */
const UNMOUNTED: Readonly<Record<string, string>> = {
  'components/workpaper/f2/valuation/F2ValuationTestSheet.vue': 'F2-38/39/40 计价测试通用组件的旧版，各 tab 已改用 F2ValuationDateSheet / MonthlySheet',
}

/** 别处引用了它（import 路径或模板标签，含自动注册的全局组件写法） */
function mountedBy(target: string): string[] {
  const base = target.split('/').pop()!.replace(/\.vue$/, '')
  const kebab = base.replace(/(?<!^)([A-Z])/g, '-$1').toLowerCase()
  const pattern = new RegExp(`/${base}(?:\\.vue)?['"]|<${base}[\\s/>]|<${kebab}[\\s/>]`)
  return walk(SRC).map(rel).filter(f => f !== target && !f.endsWith('components.d.ts') && pattern.test(read(join(SRC, f))))
}

describe('共享回填函数接入守卫', () => {
  const verdicts = scanHosts()
  const failing = [...verdicts].filter(([, p]) => p.length > 0)

  it('扫到全部宿主（78 个引擎宿主，挂凭导入宿主都在其中）', () => {
    expect(verdicts.size).toBeGreaterThanOrEqual(78)
  })

  it('不在冻结清单里的宿主都已接入', () => {
    const fresh = failing.filter(([f]) => !FROZEN.includes(f) && !(f in UNMOUNTED)).map(([f, p]) => `${f}: ${p.join('；')}`)
    expect(fresh, `以下宿主未接入共享回填函数（接入它，不要往冻结清单里加）：\n${fresh.join('\n')}`).toEqual([])
  })

  it('冻结清单没有已接入或已不存在的条目（只许删）', () => {
    const failingSet = new Set(failing.map(([f]) => f))
    const stale = FROZEN.filter(f => !failingSet.has(f))
    expect(stale, `以下宿主已接入（或已不是宿主），请从冻结清单删去：\n${stale.join('\n')}`).toEqual([])
  })

  it('冻结清单为空（任务 13 起全部宿主已接入）', () => {
    expect(FROZEN).toEqual([])
  })

  it('「未挂载」登记的宿主确实无人挂载，且仍未接入（接入了就删去此项）', () => {
    const failingSet = new Set(failing.map(([f]) => f))
    for (const f of Object.keys(UNMOUNTED)) {
      expect(verdicts.has(f), `${f} 已不是宿主或已删除，请从「未挂载」删去`).toBe(true)
      expect(failingSet.has(f), `${f} 已接入，请从「未挂载」删去`).toBe(true)
      expect(mountedBy(f), `${f} 被挂载了，必须接入共享回填函数`).toEqual([])
    }
  })

  it('挂载判据自检：认 import 路径、PascalCase 与短横线标签', () => {
    // 用一个真实被挂载的宿主（G5-12 由 G5 主组件 import）验证判据不是恒空
    expect(mountedBy('components/workpaper/g5-long-term-receivable/voucher/G5TabVoucherCheck.vue').length).toBeGreaterThan(0)
  })

  it('表格子组件也认 defineAsyncComponent 动态引入的（K8-6 / K8-7 分段表格）', () => {
    const text = "const T = defineAsyncComponent(() => import('./K8CutoffS2VTable.vue'))\n"
      + "const E = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))\n"
      + "const C = defineAsyncComponent(() => import('./useX'))"
    expect(dynamicVueImportPaths(text)).toEqual(['./K8CutoffS2VTable.vue', '../../voucher-sampling/GtVoucherSamplingEngine.vue'])
    const children = localImports(join(SRC, 'components/workpaper/k8/cutoff/K8TabCutoffS2V.vue'),
      read(join(SRC, 'components/workpaper/k8/cutoff/K8TabCutoffS2V.vue')), '.vue').map(rel)
    expect(children).toContain('components/workpaper/k8/cutoff/K8CutoffS2VTable.vue')
    // 抽凭共享组件（引擎本身）不算宿主的表格子组件
    expect(children.some(c => c.includes('voucher-sampling/'))).toBe(false)
  })

  it('组合式函数链只跟值导入：类型导入（import type / 说明符全带 type）不算', () => {
    const text = [
      "import type { A } from './a'",
      "import { type B } from './b'",
      "import { c, type D } from './c'",
      "import E from '@/e'",
      "import { ref } from 'vue'",
      "import {\n  f,\n  g,\n} from '../fg'",
      "import type {\n  H,\n} from '../h'",
    ].join('\n')
    expect(valueImportPaths(text)).toEqual(['./c', '@/e', '../fg'])
  })

  it('组合式函数链：跟两层（截止测试宿主经 useI2Cutoff 到 useCycleCutoff）、认 `@/` 别名（G6），不含共享回填模块本身', () => {
    const chainOf = (f: string) => localComposableChain(join(SRC, f), read(join(SRC, f))).map(rel)
    const cutoff = chainOf('components/workpaper/i2/cutoff/I2TabCutoffForward.vue')
    expect(cutoff).toContain('components/workpaper/composables/useCycleCutoff.ts')
    expect(chainOf('components/workpaper/g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue'))
      .toContain('composables/useG6EclVoucherCheck.ts')
    // I2-8 宿主与它的组合式函数都 import 了 shared/voucherCheckFill（combineRowClass、类型）：共享模块定义了
    // useVoucherCheckFill / withRowMeta，算进链里会让只 import 它的类型的宿主被判为已接入
    const material = chainOf('components/workpaper/i2/inspection/I2TabMaterialCheck.vue')
    expect(material).toContain('components/workpaper/composables/useI2MaterialCheck.ts')
    expect(material).not.toContain(SHARED_FILL)
    expect(cutoff).not.toContain(SHARED_FILL)
  })

  it('判据能打红：缺共享函数 / 仍展开 / 传 phase / 没接撤销 / 没透传元数据 / 没标签列', () => {
    const adopted = `<script setup>useVoucherCheckFill({}); withRowMeta(a, b)</script>
      <GtVoucherSamplingEngine :project-id="p" @filled="f" @undo-request="u" />
      <VoucherRowMetaCell :row="row" />`
    expect(adoptionProblems(adopted, [])).toEqual([])
    expect(adoptionProblems(adopted.replace('useVoucherCheckFill', 'useOther'), [])).toContain('未接入 useVoucherCheckFill')
    expect(adoptionProblems(adopted, ['expandMultiAccountVouchers(samples)'])).toContain('仍调用 expandMultiAccountVouchers')
    expect(adoptionProblems(adopted.replace(':project-id', 'phase="final" :project-id'), [])).toContain('给引擎传 phase（阶段取项目当前阶段）')
    expect(adoptionProblems(adopted.replace(':project-id', ':phase="p" :project-id'), [])).toContain('给引擎传 phase（阶段取项目当前阶段）')
    expect(adoptionProblems(adopted.replace(' @undo-request="u"', ''), [])).toContain('引擎未接 @undo-request（撤销按批次删行）')
    expect(adoptionProblems(adopted.replace('withRowMeta(a, b)', ''), [])).toContain('解析 / 保存未经 withRowMeta 透传行元数据')
    expect(adoptionProblems(adopted.replace('withRowMeta(a, b)', 'withRowMeta<Row>(a, b)'), [])).toEqual([])
    expect(adoptionProblems(adopted, ['expandMultiAccountVouchers<S>(samples)'])).toContain('仍调用 expandMultiAccountVouchers')
    expect(adoptionProblems(adopted.replace('<VoucherRowMetaCell :row="row" />', ''), [])).toContain('表格缺阶段 / 来源标签列')
    // 组合式函数里接入也算（宿主只用它返回的处理函数）
    expect(adoptionProblems(adopted.replace('useVoucherCheckFill({}); withRowMeta(a, b)', ''),
      ['useVoucherCheckFill<Row>({}); withRowMeta(row, raw)'])).toEqual([])
    // 表格在宿主的子组件里（D2 矩阵 / 卡片视图）：标签列在子组件模板里也算
    const noColumn = adopted.replace('<VoucherRowMetaCell :row="row" />', '<MatrixView :rows="rows" />')
    expect(adoptionProblems(noColumn, [], ['<el-table-column label="来源"><VoucherRowMetaCell :row="row" /></el-table-column>'])).toEqual([])
    expect(adoptionProblems(noColumn, [], ['<el-table :data="rows" />'])).toContain('表格缺阶段 / 来源标签列')
    // 以别名引入的引擎（G3-4：defineAsyncComponent 起名 SamplingEngine）同样算宿主、同样查 phase / 撤销
    const aliased = `<script setup>const SamplingEngine = defineAsyncComponent(() => import('../voucher-sampling/GtVoucherSamplingEngine.vue'))
      useVoucherCheckFill({}); withRowMeta(a, b)</script>
      <SamplingEngine phase="final" @filled="f" /><VoucherRowMetaCell :row="row" />`
    expect(engineTagAttrs(aliased)).toHaveLength(1)
    expect(adoptionProblems(aliased, [])).toEqual(['给引擎传 phase（阶段取项目当前阶段）', '引擎未接 @undo-request（撤销按批次删行）'])
    expect(engineTagAttrs("import X from './GtVoucherSamplingEngine.vue'\n<x :a=\"1\" />")).toHaveLength(1)
    // 只在注释里提到引擎的不算宿主
    expect(engineTagAttrs('<!-- 集成 GtVoucherSamplingEngine 行级抽凭 -->')).toEqual([])
  })
})
