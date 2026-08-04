/**
 * confirmationStubWiring.spec.ts — 函证共享组件 stub 实装守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 10.1~10.7；Property 25, 26
 *
 * 背景：四个共享 confirmation 组件里的跳转/删除处理器长期是 `console.log` stub，
 * 且注释与日志里写死 `'D0-1'` —— 而这些组件被 D0/E0/F0/G0/H0/K0/L0 七个枢纽共享，
 * 在 H0 上点「跳转汇总表」既不跳也不报错。
 *
 * 本守卫钉死：
 *   ① 四处不得残留 stub 形态（`TODO` + `console.log` 且无真实导航/删除调用）；
 *   ② 目标底稿编码必须按 `getCycleConfirmationMeta(wpCode).summaryCode` 派生，
 *      源码中不得出现 `'D0-1'` 字面量作跳转目标；
 *   ③ 复用平台既有 `navigateToCycleSheet`，不新造导航；
 *   ④ `navigateToCycleSheet` 必须用 `@/services/apiProxy`（`@/utils/http` 返回
 *      AxiosResponse，读 `res.wp_id` 恒 undefined）；
 *   ⑤ `handleJumpB50` 已由 e0-confirmation-completion 实装 —— 不得被本轮改动破坏。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { getCycleConfirmationMeta } from '../coordination/cycleConfirmationMeta'

const CONFIRM_DIR = path.join(__dirname, '..')

function read(rel: string): string {
  const p = path.join(CONFIRM_DIR, rel)
  const src = fs.readFileSync(p, 'utf-8')
  expect(src.length, `${rel} 读取为空（路径解析失败？）`).toBeGreaterThan(100)
  return src
}

/** 去注释（HTML 注释 + JS 行/块注释）。守卫说明里会写反例，不去注释必假红。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, '$1')
}

/** 截取一个具名函数的函数体（花括号配对，避免「固定字符窗口溢出到下一个函数」）。 */
function fnBody(src: string, name: string): string {
  const decl = src.indexOf(`function ${name}(`)
  expect(decl, `未找到 function ${name}(`).toBeGreaterThan(-1)
  const open = src.indexOf('{', decl)
  expect(open, `${name} 无函数体`).toBeGreaterThan(-1)
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  throw new Error(`${name} 花括号未配对`)
}

const FILES = {
  reliability: 'reliability/GtConfirmationReliability.vue',
  diffReconcile: 'diffReconcile/GtConfirmationDiffReconcile.vue',
  diffMaster: 'diffReconcile/DiffReconcileMaster.vue',
  fraudRisk: 'fraudRisk/GtConfirmationFraudRisk.vue',
  navigator: 'coordination/navigateToCycleSheet.ts',
} as const

const SRC = Object.fromEntries(
  Object.entries(FILES).map(([k, rel]) => [k, read(rel)]),
) as Record<keyof typeof FILES, string>

const CODE = Object.fromEntries(
  Object.entries(SRC).map(([k, s]) => [k, stripComments(s)]),
) as Record<keyof typeof FILES, string>

// ─── Property 25：四处 stub 已实装 ───────────────────────────────────────────

describe('Property 25: 四个 stub 已实装（不再是 console.log 占位）', () => {
  const cases: Array<{ file: keyof typeof FILES; fn: string; must: string[] }> = [
    { file: 'reliability', fn: 'handleJumpD01', must: ['navigateToCycleSheet', 'summaryCode'] },
    { file: 'diffReconcile', fn: 'handleJumpD01', must: ['navigateToCycleSheet', 'summaryCode'] },
    { file: 'diffReconcile', fn: 'handleDelete', must: ['deleteRows'] },
    { file: 'fraudRisk', fn: 'handleJumpRef', must: ['navigateToCycleSheet'] },
  ]

  for (const c of cases) {
    it(`${FILES[c.file]} :: ${c.fn} 有真实实现`, () => {
      const body = fnBody(CODE[c.file], c.fn)
      for (const token of c.must) {
        expect(body, `${c.fn} 应调用 ${token}`).toContain(token)
      }
      expect(body, `${c.fn} 仍残留 console.log 占位`).not.toContain('console.log')
    })
  }

  it('四处函数体内均无 TODO 残留', () => {
    for (const c of cases) {
      const body = fnBody(CODE[c.file], c.fn)
      expect(body, `${FILES[c.file]}::${c.fn}`).not.toMatch(/TODO/i)
    }
  })

  it('反向自检：未去注释的原始源码确实含 TODO/console.log（否则上两条断言空转）', () => {
    // 这些文件仍有别的 TODO（如 fraudRisk 的 Excel 导入导出），
    // 保证 stripComments 与 fnBody 的组合确实在做筛选而不是恒真。
    const anyTodo = Object.values(SRC).some((s) => /TODO/.test(s))
    expect(anyTodo).toBe(true)
  })
})

// ─── Property 26：目标编码按循环派生，禁 'D0-1' 字面量 ───────────────────────

describe('Property 26: 跳转目标按循环派生（禁写 D0-1 字面量）', () => {
  it('两处 handleJumpD01 函数体内不得出现 D0-1 字面量', () => {
    for (const file of ['reliability', 'diffReconcile'] as const) {
      const body = fnBody(CODE[file], 'handleJumpD01')
      expect(body, FILES[file]).not.toContain('D0-1')
      expect(body, FILES[file]).toContain('getCycleConfirmationMeta(props.wpCode)')
    }
  })

  it('fraudRisk handleJumpRef 取条目自身 source_ref，不写死任何循环编码', () => {
    const body = fnBody(CODE.fraudRisk, 'handleJumpRef')
    expect(body).not.toMatch(/['"][A-Z]0-\d/)
  })

  it('七枢纽 summaryCode 各不相同（证明「按循环派生」确有区分度）', () => {
    const codes = ['D0-7', 'E0-1', 'F0-4', 'G0-1', 'H0-6', 'K0-4', 'L0-1'].map(
      (wp) => getCycleConfirmationMeta(wp).summaryCode,
    )
    expect(new Set(codes).size).toBe(7)
    expect(getCycleConfirmationMeta('H0-6').summaryCode).toBe('H0-1')
    expect(getCycleConfirmationMeta('H0-4').summaryCode).toBe('H0-1')
  })

  it('复用平台既有 navigateToCycleSheet，未新造导航实现', () => {
    for (const file of ['reliability', 'diffReconcile', 'fraudRisk'] as const) {
      expect(CODE[file], FILES[file]).toContain(
        "from '../coordination/navigateToCycleSheet'",
      )
    }
  })

  it('router 在 setup 顶层取（useRouter 写进函数体会静默失效）', () => {
    for (const file of ['reliability', 'diffReconcile'] as const) {
      expect(CODE[file], FILES[file]).toMatch(/^const router = useRouter\(\)$/m)
    }
  })
})

// ─── navigateToCycleSheet 的 http 客户端形态 ─────────────────────────────────

describe('navigateToCycleSheet 必须用 apiProxy（http 默认导出返回 AxiosResponse）', () => {
  it('导入 @/services/apiProxy 的具名 api，而非 @/utils/http 默认导出', () => {
    expect(CODE.navigator).toContain("import { api } from '@/services/apiProxy'")
    expect(CODE.navigator).not.toMatch(/import\s+api\s+from\s+'@\/utils\/http'/)
  })

  it('读取 wp_id 的形态与 apiProxy 一致（直接取业务字段，不经 .data）', () => {
    expect(CODE.navigator).toContain('wp_id')
    expect(CODE.navigator).not.toContain('res.data?.wp_id')
  })
})

// ─── handleJumpB50 零回归 ────────────────────────────────────────────────────

describe('handleJumpB50 不得被本轮改动破坏（e0-confirmation-completion 已实装）', () => {
  it('仍走 workpapers?wp_code=B50 查询 + router.push', () => {
    const body = fnBody(CODE.fraudRisk, 'doJumpB50')
    expect(body).toContain("wp_code: 'B50'")
    expect(body).toContain('router.push')
    expect(body).not.toContain('console.log')
  })
})

// ─── 删除链路：选中态在子组件，必须随事件上报 ─────────────────────────────────

describe('差异核对删除链路完整（选中态在 Master，需随事件上报行 ID）', () => {
  it('DiffReconcileMaster 的 delete 事件携带 rowIds', () => {
    expect(CODE.diffMaster).toMatch(/\(e:\s*'delete',\s*rowIds:\s*string\[\]\)/)
    expect(CODE.diffMaster).toContain("emit('delete', [...selectedIds.value])")
  })

  it('删除后清空勾选（避免已删行 ID 残留在选中态）', () => {
    const body = fnBody(CODE.diffMaster, 'handleDeleteClick')
    expect(body).toContain('selectedIds.value = []')
    expect(body).toContain('clearSelection')
  })

  it('父组件 handleDelete 接收数组并对空选给出提示', () => {
    const body = fnBody(CODE.diffReconcile, 'handleDelete')
    expect(body).toContain('rowIds')
    expect(body).toContain('data.deleteRows(rowIds)')
    expect(body).toMatch(/ElMessage/)
  })
})
