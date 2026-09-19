/**
 * materialityAutoFetch.spec.ts — 函证差异调节表（X0-4）重要性水平自动取数守卫
 *
 * 立项依据（2026-08-06 浏览器实测，项目 `2aa00f57`）：
 * `materiality` 表有 `performance_materiality = 26104487`、
 * `GET /api/projects/{id}/materiality?year=2025` 返回 200 且字段完整，
 * 而 F0-4 界面「实际执行重要性」显示 **未配置** ——
 * `useDiffReconcileData` 的 materiality 配置只从底稿自身载荷
 * (`htmlData.materiality_config`) 读取，全文没有任何取数调用。
 *
 * 三个连带后果（全是静默的）：
 *   1. `isOverMateriality` 恒 false → 差异行永不标红
 *   2. 「推送 N 笔超重要性差异至 A13」按钮永久禁用（N 恒为 0）
 *   3. `source === 'auto'` 这个 tag 分支不可达（全平台无一处写入该值）
 *
 * 而 UI 文案早已写明「默认从 B15 重要性水平底稿自动获取」→ 承诺长期未兑现。
 *
 * 受益面 = D0-4 / E0-4 / F0-4 / G0-4 / H0-4 / K0-4 / L0-4 七个函证枢纽共用该组件。
 *
 * 本守卫钉死四件事：
 *   P1 取数纯函数三态语义（有效值 / 无有效阈值 / 端点失败 fail-open）
 *   P2 手工优先不变式（auto 值不得覆盖手填值与载荷已有值）
 *   P3 接线存在性（宿主必须真传 projectId，否则能力退化成零消费方）
 *   P4 声明顺序（缓存变量必须早于首次初始化调用，防 setup 期 TDZ）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'

// ─── 仓库根定位（双哨兵向上查找，禁写死回退级数） ────────────────────────────

function repoRoot(): string {
  let dir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(resolve(dir, 'backend/app/main.py'))
      readFileSync(resolve(dir, 'audit-platform/frontend/package.json'))
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('repoRoot not found — 双哨兵均未命中')
}

const ROOT = repoRoot()
const DIR = 'audit-platform/frontend/src/components/workpaper/confirmation/diffReconcile'

function readSource(rel: string): string {
  return readFileSync(resolve(ROOT, `${DIR}/${rel}`), 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 剥注释 —— 本文件与被测源码的说明注释里都含被禁字样（如「只从底稿自身载荷读」），
 * 不剥会让负向断言被自己的解释文字打红（memory 已记同款铁律，本轮第 N 次）。
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

// ─── api mock（必须在 import 被测模块之前声明） ──────────────────────────────

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: unknown[]) => mockGet(...args) },
}))

const { fetchMaterialityConfig, hasUsablePm } = await import('../fetchMaterialityConfig')

// ─── P1: 取数纯函数三态 ──────────────────────────────────────────────────────

describe('P1 fetchMaterialityConfig 三态语义', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('端点返回有效 PM → 返回配置对象且 source=auto', async () => {
    mockGet.mockResolvedValue({ performance_materiality: 26104487 })
    const cfg = await fetchMaterialityConfig('p1', 2025)
    expect(cfg).toEqual({
      performance_materiality: 26104487,
      is_overridden: false,
      source: 'auto',
    })
  })

  it('字符串数值也接受（后端 numeric 可能序列化成字符串）', async () => {
    mockGet.mockResolvedValue({ performance_materiality: '26104487.00' })
    const cfg = await fetchMaterialityConfig('p1', 2025)
    expect(cfg?.performance_materiality).toBe(26104487)
  })

  it('PM 为 0 / 负数 / null / 缺失 → 返回 null（不是有效阈值）', async () => {
    for (const pm of [0, -1, null, undefined]) {
      mockGet.mockResolvedValue({ performance_materiality: pm })
      expect(await fetchMaterialityConfig('p1', 2025)).toBeNull()
    }
  })

  it('端点抛错（404 未编制 / 网络失败）→ fail-open 返回 null 而不抛', async () => {
    mockGet.mockRejectedValue(new Error('404'))
    await expect(fetchMaterialityConfig('p1', 2025)).resolves.toBeNull()
  })

  it('projectId 缺失 → 不发请求直接返回 null', async () => {
    expect(await fetchMaterialityConfig(undefined, 2025)).toBeNull()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('year 缺省时不带 query（由后端取当前年度）', async () => {
    mockGet.mockResolvedValue({ performance_materiality: 100 })
    await fetchMaterialityConfig('p1', undefined)
    expect(String(mockGet.mock.calls[0][0])).not.toContain('year=')
  })

  it('year 提供时带上 query 参数', async () => {
    mockGet.mockResolvedValue({ performance_materiality: 100 })
    await fetchMaterialityConfig('p1', 2025)
    expect(String(mockGet.mock.calls[0][0])).toContain('year=2025')
  })
})

// ─── P2: hasUsablePm 与 isOverMateriality 同口径 ─────────────────────────────

describe('P2 hasUsablePm 判据与 isOverMateriality 一致', () => {
  it('有效正数 → true', () => {
    expect(hasUsablePm({ performance_materiality: 1 })).toBe(true)
  })

  it('0 / 负数 / null / undefined / NaN → false（与 pm <= 0 同口径）', () => {
    expect(hasUsablePm({ performance_materiality: 0 })).toBe(false)
    expect(hasUsablePm({ performance_materiality: -5 })).toBe(false)
    expect(hasUsablePm({})).toBe(false)
    expect(hasUsablePm(null)).toBe(false)
    expect(hasUsablePm({ performance_materiality: NaN })).toBe(false)
  })

  it('反向自检：isOverMateriality 的判据仍是 pm == null || pm <= 0', () => {
    // 两处口径必须一致，否则「hasUsablePm 说有效」而「isOverMateriality 说无效」
    const src = stripComments(readSource('composables/useDiffReconcileData.ts'))
    expect(src).toMatch(/pm\s*==\s*null\s*\|\|\s*pm\s*<=\s*0/)
  })
})

// ─── P3: 手工优先不变式（源码级） ────────────────────────────────────────────

describe('P3 手工优先不变式', () => {
  const src = stripComments(readSource('composables/useDiffReconcileData.ts'))

  it('套用 auto 值前必须检查 is_overridden（手动覆盖不得被冲掉）', () => {
    expect(src).toMatch(/is_overridden/)
    expect(src).toMatch(/if\s*\(\s*cur\.is_overridden/)
  })

  it('套用 auto 值前必须检查载荷已有 PM（hasUsablePm 短路）', () => {
    expect(src).toMatch(/hasUsablePm\s*\(\s*cur\s*\)/)
  })

  it('二次判定必须在 await 之后（取数期间用户可能已手填）', () => {
    const i = src.indexOf('await fetchMaterialityConfig')
    const j = src.indexOf('applyAutoMateriality()', i)
    expect(i).toBeGreaterThan(0)
    expect(j).toBeGreaterThan(i)
  })

  it('initFromHtmlData 末尾必须重新套用 auto 值（deep watch 会反复重置配置）', () => {
    // 不在这里回落，底稿保存/上游刷新后 auto 值会被静默冲掉（阈值时有时无）
    const body = src.slice(
      src.indexOf('function initFromHtmlData'),
      src.indexOf('function ensureRowId'),
    )
    expect(body).toContain('applyAutoMateriality()')
  })
})

// ─── P4: 接线存在性 + 声明顺序 ───────────────────────────────────────────────

describe('P4 接线存在性（防能力退化成零消费方）', () => {
  it('宿主必须真传 projectId —— 只写 composable 不传 prop 等于没接', () => {
    const host = stripComments(readSource('GtConfirmationDiffReconcile.vue'))
    const call = host.slice(
      host.indexOf('useDiffReconcileData({'),
      host.indexOf('})', host.indexOf('useDiffReconcileData({')),
    )
    expect(call).toContain('projectId: props.projectId')
    expect(call).toContain('year: props.year')
  })

  it('composable 必须声明 projectId / year 两个可选入参', () => {
    const src = stripComments(readSource('composables/useDiffReconcileData.ts'))
    expect(src).toMatch(/projectId\?:\s*string/)
    expect(src).toMatch(/year\?:\s*string\s*\|\s*number/)
  })

  it('缓存变量声明必须早于首次 initFromHtmlData 调用（防 setup 期 TDZ）', () => {
    // let 不像 function 那样提升；声明留在后半段会抛
    // ReferenceError 且 get_diagnostics / vitest 都查不出，只有浏览器暴露
    const lines = readSource('composables/useDiffReconcileData.ts').split('\n')
    const declLine = lines.findIndex((l) => /^\s*let\s+_autoConfig\b/.test(l))
    const callLine = lines.findIndex((l) => /^\s*initFromHtmlData\(props\.htmlData\(\)\)/.test(l))
    expect(declLine).toBeGreaterThan(-1)
    expect(callLine).toBeGreaterThan(-1)
    expect(declLine).toBeLessThan(callLine)
  })

  it('取数必须用 apiProxy 的 api（直接返回业务数据），不得用 utils/http', () => {
    // 本 spec Task 20.1 与 Task 33 两次踩过这个形态错配、方向还相反，
    // 四层验证全绿只有浏览器能发现
    const src = stripComments(readSource('composables/fetchMaterialityConfig.ts'))
    expect(src).toContain("from '@/services/apiProxy'")
    expect(src).not.toContain("@/utils/http")
    expect(src).not.toMatch(/const\s*\{\s*data\s*\}\s*=\s*await\s+api\.get/)
  })

  it('反向自检：剥注释没有把源码清空（否则上面全是空转）', () => {
    const src = stripComments(readSource('composables/useDiffReconcileData.ts'))
    expect(src.length).toBeGreaterThan(2000)
    expect(src).toContain('fetchMaterialityConfig')
  })
})
