/**
 * samplingMethodologyTraceability.spec.ts
 *
 * 钉死「抽样方法学 bar 的批次号 / 抽样框版本两列真能取到值」这条链路
 * （sampling-compliance-closure R6.2，Task 24 浏览器实测挖出的缺陷）。
 *
 * **缺陷形态（改造前，浏览器实测复现）**：`GtVoucherSamplingEngine` 构造 `filled`
 * 载荷的 `methodology` 对象时只填 9 个字段，**没有 batchId / datasetId** ——
 * 而共享类型 `SamplingMethodologySnapshot` 声明了两者、`buildMethodologySummary`
 * 渲染两者、`WpSamplingMethodologyBar.vue` 也渲染两者。于是这两列**结构上恒为空**：
 * 实测 D3 底稿在一个 `dataset_id` 已绑定的批次上仍显示「未绑定账套版本」。
 * 同族第二处：抽样备忘导出把 `batchId` 读成 `methodologySnapshot.batch_id`，
 * 而后端 `build_methodology_snapshot` 是纯方法学函数、快照里压根没有该键。
 *
 * 判据一律是**源码级形态**而非「字段名出现过」——「出现过」挡不住把它写成
 * 恒 null 的表达式（平台已记同族教训：`toContain('a.b.length')` 抓不住删掉判断）。
 *
 * Validates: Requirements 6.2, 6.3
 * Properties: Property 17
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ─── REPO_ROOT：双哨兵具体文件向上查找（禁写死回退级数）────────────────────
const SENTINELS = [
  'audit-platform/frontend/package.json',
  'backend/app/services/ledger_sampling_service.py',
]

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    if (SENTINELS.every((s) => fs.existsSync(path.join(dir, ...s.split('/'))))) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('REPO_ROOT 未找到（哨兵文件缺失）')
}

const REPO_ROOT = findRepoRoot()
const FE = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper')

function read(rel: string): string {
  const p = path.join(FE, rel)
  const src = fs.readFileSync(p, 'utf-8')
  expect(src.length, `${rel} 应非空（路径漂移会让本文件全部断言空转）`).toBeGreaterThan(500)
  return src
}

const ENGINE = read(path.join('voucher-sampling', 'GtVoucherSamplingEngine.vue'))
const COMPOSABLE = read(path.join('composables', 'useVoucherSampling.ts'))
const SHARED = read(path.join('composables', 'shared', 'samplingFillTarget.ts'))
const BAR = read(path.join('shared', 'WpSamplingMethodologyBar.vue'))

/** 剥 JS 行注释与块注释（本文件自己的说明文字里会出现被禁形态） */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let inStr: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (inStr) {
      if (c === '\\') {
        out += c + (n ?? '')
        i += 2
        continue
      }
      if (c === inStr) inStr = null
      out += c
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      inStr = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += c
    i += 1
  }
  return out
}

const ENGINE_CODE = stripComments(ENGINE)
const COMPOSABLE_CODE = stripComments(COMPOSABLE)

/** 花括号配对截取 `const <name>: <T> = { ... }` 的对象字面量体 */
function objectLiteralBody(src: string, declRe: RegExp): string {
  const m = declRe.exec(src)
  if (!m) return ''
  let i = src.indexOf('{', m.index)
  if (i < 0) return ''
  let depth = 0
  const start = i
  while (i < src.length) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(start, i + 1)
    }
    i += 1
  }
  return ''
}

describe('抽样方法学可追溯性（R6.2）', () => {
  describe('stripComments 自检', () => {
    it('确实剥掉注释、且不误伤字符串字面量', () => {
      expect(stripComments('const a = 1 // batchId: null')).not.toContain('batchId')
      expect(stripComments("const a = '// batchId'")).toContain('batchId')
      expect(stripComments('/* batchId */ const a = 1')).not.toContain('batchId')
    })

    it('原始源码里确实含说明性注释（证明剥注释非空操作）', () => {
      expect(ENGINE.length).toBeGreaterThan(ENGINE_CODE.length)
    })
  })

  describe('Property 17：filled 载荷的 methodology 必须携带批次号与抽样框版本', () => {
    const body = objectLiteralBody(
      ENGINE_CODE,
      /const\s+methodology\s*:\s*SamplingFilledMethodology\s*=/,
    )

    it('能截到 methodology 对象字面量（防正则失效导致断言空转）', () => {
      expect(body.length).toBeGreaterThan(200)
      // 锚定：既有字段仍在，证明截到的是正确的那个对象
      expect(body).toMatch(/samplingMethod\s*:/)
      expect(body).toMatch(/randomSeed\s*:/)
    })

    it('batchId 取自 filledBatchId（不得为字面 null，也不得读后端方法学快照）', () => {
      expect(body).toMatch(/batchId\s*:\s*filledBatchId\.value/)
      // 反向：这两种写法都会让该列恒空 —— 前者是"声明了但没接"，
      // 后者是改造前的真实缺陷（后端 build_methodology_snapshot 无 batch_id 键）
      expect(body).not.toMatch(/batchId\s*:\s*null\s*[,}]/)
      expect(body).not.toMatch(/batchId\s*:[^,}]*methodologySnapshot/)
    })

    it('datasetId 取自 datasetId ref（不得为字面 null）', () => {
      expect(body).toMatch(/datasetId\s*:\s*datasetId\.value/)
      expect(body).not.toMatch(/datasetId\s*:\s*null\s*[,}]/)
    })

    it('SamplingFilledMethodology 接口声明了两个字段', () => {
      const iface = objectLiteralBody(
        ENGINE_CODE,
        /export\s+interface\s+SamplingFilledMethodology\s*/,
      )
      expect(iface.length).toBeGreaterThan(150)
      expect(iface).toMatch(/\bbatchId\b/)
      expect(iface).toMatch(/\bdatasetId\b/)
    })

    it('引擎已从 composable 解构 filledBatchId', () => {
      // 解构块在 `const {` ... `} = useVoucherSampling(` 之间
      const m = /const\s*\{([\s\S]*?)\}\s*=\s*useVoucherSampling\s*\(/.exec(ENGINE_CODE)
      expect(m, '未找到 useVoucherSampling 解构块').not.toBeNull()
      expect(m![1]).toMatch(/\bfilledBatchId\b/)
      expect(m![1]).toMatch(/\bdatasetId\b/)
    })
  })

  describe('Property 17：composable 必须从 cutoff-fill 响应取回 batch_id', () => {
    it('声明并导出 filledBatchId', () => {
      expect(COMPOSABLE_CODE).toMatch(/const\s+filledBatchId\s*=\s*ref</)
      const ret = COMPOSABLE_CODE.lastIndexOf('return {')
      expect(ret).toBeGreaterThan(0)
      expect(COMPOSABLE_CODE.slice(ret)).toMatch(/\bfilledBatchId\b/)
    })

    it('confirmFill 捕获 cutoff-fill 响应而非丢弃', () => {
      // 改造前是裸 `await http.post(...)`（响应被丢弃）→ 批次号无从得知
      expect(COMPOSABLE_CODE).toMatch(/const\s+fillRes\s*=\s*await\s+http\.post\(/)
    })

    it('按信封形态读取（res.data.data），不得直接读 res.data.batch_id', () => {
      // `@/utils/http` 返回 AxiosResponse，payload 在 res.data.data；
      // 直接读 res.data.batch_id 恒 undefined（平台已记同族踩坑）
      expect(COMPOSABLE_CODE).toMatch(/fillRes\??\.data[\s\S]{0,40}?\?\.\s*data/)
      expect(COMPOSABLE_CODE).toMatch(/filledBatchId\.value\s*=/)
    })

    it('新抽样时清空 filledBatchId（不得把上一批次号贴到新样本上）', () => {
      // triggerSampling 的重置分支：与 loadedFromBatch 一并清空
      const idx = COMPOSABLE_CODE.indexOf('loadedFromBatch.value = null')
      expect(idx).toBeGreaterThan(0)
      const window = COMPOSABLE_CODE.slice(idx, idx + 300)
      expect(window).toMatch(/filledBatchId\.value\s*=\s*null/)
    })
  })

  describe('Property 17：备忘导出的批次号不得读后端方法学快照', () => {
    it('batchId 走 filledBatchId / loadedFromBatch 回落', () => {
      const idx = ENGINE_CODE.indexOf('buildSamplingMemo(')
      expect(idx).toBeGreaterThan(0)
      const window = ENGINE_CODE.slice(idx, idx + 1200)
      expect(window).toMatch(/batchId\s*:\s*filledBatchId\.value/)
      expect(window).not.toMatch(/batchId\s*:[^,}]*methodologySnapshot/)
    })
  })

  describe('source_wp_code 溯源：wpCode 必须回落 WorkpaperRuntimeContext', () => {
    it('引擎在 setup 顶层 inject 运行时上下文（不得写进函数体）', () => {
      const m = /const\s+workpaperRuntime\s*=\s*inject\(\s*WorkpaperRuntimeContextKey\s*,\s*null\s*\)/.exec(
        ENGINE_CODE,
      )
      expect(m, '未找到 inject(WorkpaperRuntimeContextKey, null)').not.toBeNull()
      // setup 顶层判据：该行不得有缩进（写进函数体会静默拿不到，平台已记该踩坑）
      const lineStart = ENGINE_CODE.lastIndexOf('\n', m!.index) + 1
      expect(
        ENGINE_CODE.slice(lineStart, m!.index),
        'inject 必须在 setup 顶层（该行不得缩进）',
      ).toBe('')
    })

    it('effectiveWpCode = prop 优先 → runtime 回落', () => {
      expect(ENGINE_CODE).toMatch(
        /const\s+effectiveWpCode\s*=\s*computed\(\s*\(\)\s*=>\s*props\.wpCode\s*\|\|\s*workpaperRuntime\?\.wpCode\?\.value\s*\|\|\s*''\s*,?\s*\)/,
      )
    })

    it('传给 composable 的是 getter 而非静态快照', () => {
      // 静态 `wpCode: props.wpCode` 会把 runtime 尚未就位时的空串固化下来
      const m = /useVoucherSampling\(\{([\s\S]*?)\n\}\)/.exec(ENGINE_CODE)
      expect(m, '未找到 useVoucherSampling 入参').not.toBeNull()
      expect(m![1]).toMatch(/wpCode\s*:\s*\(\)\s*=>\s*effectiveWpCode\.value/)
      expect(m![1]).not.toMatch(/wpCode\s*:\s*props\.wpCode\s*,/)
    })

    it('复核 section 前缀与 source_wp_code 同一真源（不得两处分叉）', () => {
      expect(ENGINE_CODE).toMatch(
        /samplingSectionPrefix\s*=\s*computed\([\s\S]{0,160}?effectiveWpCode\.value/,
      )
      expect(ENGINE_CODE).not.toMatch(
        /samplingSectionPrefix\s*=\s*computed\([\s\S]{0,80}?props\.wpCode/,
      )
    })

    it('composable 延迟求值（string / ref / getter 三形态都认）', () => {
      expect(COMPOSABLE_CODE).toMatch(/function\s+resolveWpCode\s*\(\)\s*:\s*string/)
      // a13 推送处必须走 resolveWpCode，不得读解构出的静态值
      const idx = COMPOSABLE_CODE.indexOf("'a13:push-misstatement'")
      expect(idx).toBeGreaterThan(0)
      const window = COMPOSABLE_CODE.slice(idx, idx + 500)
      expect(window).toMatch(/wpCode\s*:\s*resolveWpCode\(\)/)
      expect(window).not.toMatch(/options\.wpCode\s*\?\?/)
    })

    it('resolveWpCode 用 unref 且该符号已 import（漏 import 时 diagnostics 查不出）', () => {
      const body = /function\s+resolveWpCode[\s\S]*?\n  \}/.exec(COMPOSABLE_CODE)
      expect(body).not.toBeNull()
      expect(body![0]).toMatch(/\bunref\(/)
      const imp = /^import\s*\{([^}]*)\}\s*from\s*'vue'/m.exec(COMPOSABLE_CODE)
      expect(imp, "未找到 vue import").not.toBeNull()
      expect(imp![1]).toMatch(/\bunref\b/)
    })

    it('WorkpaperRuntimeContext 确实声明了 wpCode（跨文件交叉锁死）', () => {
      const scaffold = fs.readFileSync(
        path.join(FE, 'composables', 'useWorkpaperScaffold.ts'),
        'utf-8',
      )
      const m = /interface WorkpaperRuntimeContext\s*\{([\s\S]*?)\n\}/.exec(scaffold)
      expect(m, '未截到 WorkpaperRuntimeContext').not.toBeNull()
      expect(m![1]).toMatch(/\bwpCode\s*:\s*Ref<string>/)
      // 该 key 必须被 provide（否则 inject 恒 null = 又一个死 fallback）
      expect(scaffold).toMatch(/provide\(\s*WorkpaperRuntimeContextKey\s*,/)
    })
  })

  describe('R2.7 回读态可见性：评价卡片不得被样本数门控藏起来', () => {
    it('卡片渲染门控含 misstatementResult（0 样本回读时也要显示）', () => {
      // 缺陷形态：`v-if="sampledVouchers.length > 0"` —— 回读既有批次评价时会话内
      // 没有样本 ⇒ 整块藏起来，「打开底稿就能看到上一批次结论」不成立
      expect(ENGINE).toMatch(
        /v-if="sampledVouchers\.length > 0 \|\| misstatementResult"[\s\S]{0,120}?misstatement-card/,
      )
      expect(ENGINE).not.toMatch(
        /v-if="sampledVouchers\.length > 0"\s*\n\s*shadow="never"\s*\n\s*class="misstatement-card"/,
      )
    })

    it('回读态下「重新推断」与「记入 A13」必须禁用（否则会写错留痕）', () => {
      expect(ENGINE_CODE).toMatch(
        /const\s+hasSessionSamples\s*=\s*computed\(\s*\(\)\s*=>\s*sampledVouchers\.value\.length\s*>\s*0\s*\)/,
      )
      // 重新推断：禁用条件含 !hasSessionSamples
      expect(ENGINE).toMatch(/:disabled="props\.readonly \|\| !hasSessionSamples"/)
      // A13 推送：canPushProjected 里必须有该判据
      const m = /const\s+canPushProjected\s*=\s*computed\(\(\)\s*=>\s*\{([\s\S]*?)\n\}\)/.exec(
        ENGINE_CODE,
      )
      expect(m, '未截到 canPushProjected').not.toBeNull()
      expect(m![1]).toMatch(/!hasSessionSamples\.value/)
    })

    it('两个禁用原因都给出可读理由（tooltip 不得为空）', () => {
      expect(ENGINE_CODE).toMatch(/const\s+reInferDisabledReason\s*=\s*computed/)
      const m = /const\s+pushProjectedDisabledReason\s*=\s*computed\(\(\)\s*=>\s*\{([\s\S]*?)\n\}\)/.exec(
        ENGINE_CODE,
      )
      expect(m).not.toBeNull()
      expect(m![1]).toMatch(/hasSessionSamples/)
      // 理由必须提到「本会话未执行抽样」这一根因，而不是笼统的「不可用」
      expect(m![1]).toMatch(/本会话未执行抽样/)
    })

    it('描述构造确实依赖会话内样本数与本次 seed（这是上一条门控的理由）', () => {
      const m = /function\s+buildProjectedMisstatementDescription[\s\S]*?\n  \}/.exec(
        COMPOSABLE_CODE,
      )
      expect(m).not.toBeNull()
      expect(m![0]).toMatch(/sampledVouchers\.value\.length/)
      expect(m![0]).toMatch(/seedUsed\.value/)
    })
  })

  describe('A13 留痕自洽：描述里的批次号必须与样本量/种子同属一个事件', () => {
    it('描述不得直接读 loadedFromBatch（已抽未回填时那是上一批次）', () => {
      const m = /function\s+buildProjectedMisstatementDescription[\s\S]*?\n  \}/.exec(
        COMPOSABLE_CODE,
      )
      expect(m).not.toBeNull()
      expect(m![0]).toMatch(/批次:\$\{resolveDescriptionBatchId\(\)\}/)
      // 缺陷形态：批次直接取回读值 → 与本会话的样本量/种子不是同一批
      expect(m![0]).not.toMatch(/批次:\$\{loadedFromBatch\.value\?\.batchId/)
    })

    it('resolveDescriptionBatchId 三态：本次回填 > 未回填 > 回读', () => {
      const m = /function\s+resolveDescriptionBatchId\(\)\s*:\s*string\s*\{([\s\S]*?)\n  \}/.exec(
        COMPOSABLE_CODE,
      )
      expect(m, '未截到 resolveDescriptionBatchId').not.toBeNull()
      const body = m![1]
      // 1) 本会话已回填 → 用它
      expect(body).toMatch(/if\s*\(filledBatchId\.value\)\s*return\s+filledBatchId\.value/)
      // 2) 已抽样但未回填 → 如实写「未回填」，不得冒充别的批次
      expect(body).toMatch(/sampledVouchers\.value\.length\s*>\s*0/)
      expect(body).toMatch(/'未回填'/)
      // 3) 会话内无样本（纯回读态）→ 回读批次与该评价同源，可用
      expect(body).toMatch(/loadedFromBatch\.value\?\.batchId/)
      // 顺序判据：未回填分支必须在回读分支之前，否则仍会取到上一批次
      expect(body.indexOf("'未回填'")).toBeLessThan(body.indexOf('loadedFromBatch'))
    })
  })

  describe('链路完备性：序列化不得白名单过滤掉新字段', () => {
    it('serializeMethodology 整体 stringify（加字段自动流通）', () => {
      const code = stripComments(SHARED)
      const m = /export function serializeMethodology[\s\S]*?\n\}/.exec(code)
      expect(m).not.toBeNull()
      expect(m![0]).toMatch(/JSON\.stringify\(\s*m\s*\)/)
      // 反向：若改成逐字段挑选，新增字段会被静默丢弃
      expect(m![0]).not.toMatch(/samplingMethod\s*:/)
    })

    it('bar 组件确实渲染这两列（否则修 composable 也看不到）', () => {
      expect(BAR).toMatch(/\bbatchId\b/)
      expect(BAR).toMatch(/\bdatasetId\b/)
    })

    it('buildMethodologySummary 也渲染这两列（导出/摘要口径一致）', () => {
      const code = stripComments(SHARED)
      const m = /export function buildMethodologySummary[\s\S]*?\n\}/.exec(code)
      expect(m).not.toBeNull()
      expect(m![0]).toMatch(/m\.batchId/)
      expect(m![0]).toMatch(/m\.datasetId/)
    })
  })
})
