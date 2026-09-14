/**
 * 抽样引擎复核入口与只读态门控 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 10.1, 10.2, 10.3, 10.4, 11.2, 11.3
 * Properties: Property 25
 *
 * 背景（2026-08-05 实证 F17）：`GtVoucherSamplingEngine.vue`（1163 行）的
 * `GtReviewTrigger` / `openReviewDialog` 命中数**均为 0** —— 抽样是审计判断最集中的环节
 * （总体界定、样本量、随机种子、未检查样本处置、结论采纳），却没有一级复核留痕。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'review_dialog.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未找到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const ENGINE = fs
  .readFileSync(
    path.join(
      ROOT,
      'audit-platform/frontend/src/components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue',
    ),
    'utf-8',
  )
  .replace(/\r\n/g, '\n')
const REVIEW_PY = fs
  .readFileSync(path.join(ROOT, 'backend/app/routers/review_dialog.py'), 'utf-8')
  .replace(/\r\n/g, '\n')

/** 标签存在性判据必须带**标签名边界** —— `toContain('<Foo')` 会被 `<FooREMOVED` 骗过。 */
function hasTag(src: string, tag: string): boolean {
  return new RegExp(`<${tag}(?=[\\s/>])`).test(src)
}

// ─── Property 25：复核入口存在 ───────────────────────────────────────────────

describe('Property 25：抽样引擎有复核入口', () => {
  it('模板含 GtReviewTrigger（带标签名边界判据）', () => {
    expect(hasTag(ENGINE, 'GtReviewTrigger')).toBe(true)
  })

  it('两处复核入口：配置/总体界定 + 结论', () => {
    const count = (ENGINE.match(/<GtReviewTrigger(?=[\s/>])/g) || []).length
    expect(count, '应有配置区与结论区两处复核入口').toBe(2)
    expect(ENGINE).toContain('samplingConfigSectionId')
    expect(ENGINE).toContain('samplingConclusionSectionId')
  })

  it('GtReviewTrigger 已 import（不依赖全局自动注册）', () => {
    expect(ENGINE).toMatch(/import GtReviewTrigger from ['"][^'"]+GtReviewTrigger\.vue['"]/)
  })

  it('反向自检：标签名边界判据对改名必打红', () => {
    const mutated = ENGINE.replace(/<GtReviewTrigger/g, '<GtReviewTriggerREMOVED')
    expect(hasTag(mutated, 'GtReviewTrigger')).toBe(false)
    // 而弱判据仍会通过 —— 这正是本自检要钉死的差别
    expect(mutated).toContain('<GtReviewTrigger')
  })
})

// ─── R10.2：section_id 与后端 prompt 交叉锁死 ────────────────────────────────

describe('R10.2：section_id 已在后端登记专属 prompt', () => {
  const KEYS = ['sampling-config', 'sampling-conclusion']

  it('前端派生的无前缀 section_id 与后端登记键一致', () => {
    // 78 个宿主实测均未传 wp-code ⇒ 运行态 section_id 为无前缀形态
    expect(ENGINE).toMatch(/sampling-config/)
    expect(ENGINE).toMatch(/sampling-conclusion/)
    for (const k of KEYS) {
      expect(REVIEW_PY, `后端未登记 prompt: ${k}`).toContain(`"${k}"`)
    }
  })

  it('后端 prompt 登记在 _SAMPLING_REVIEW_PROMPTS 并并入 _SECTION_PROMPTS', () => {
    expect(REVIEW_PY).toContain('_SAMPLING_REVIEW_PROMPTS')
    expect(REVIEW_PY).toMatch(/_SECTION_PROMPTS[\s\S]{0,400}_SAMPLING_REVIEW_PROMPTS/)
  })

  it('每条 prompt ≥40 字且引用准则', () => {
    const block = REVIEW_PY.slice(
      REVIEW_PY.indexOf('_SAMPLING_REVIEW_PROMPTS'),
      REVIEW_PY.indexOf('_SECTION_PROMPTS'),
    )
    for (const k of KEYS) {
      const at = block.indexOf(`"${k}"`)
      expect(at, `prompt 块内缺 ${k}`).toBeGreaterThan(-1)
      const seg = block.slice(at, at + 700)
      const cn = (seg.match(/[\u4e00-\u9fa5]/g) || []).length
      expect(cn, `${k} 的 prompt 过短（${cn} 个汉字）`).toBeGreaterThan(40)
      expect(seg, `${k} 未引用准则`).toMatch(/CAS 1[23]\d\d/)
    }
  })

  it('prompt 带「不得虚构」约束（走 _NO_FABRICATION 拼接）', () => {
    const block = REVIEW_PY.slice(
      REVIEW_PY.indexOf('_SECTION_PROMPTS'),
      REVIEW_PY.indexOf('_SECTION_PROMPTS') + 900,
    )
    expect(block).toContain('_NO_FABRICATION')
  })

  it('带 wpCode 前缀的形态未登记（当前不可达），且代码里写明原因', () => {
    // 不登记是有意的：宿主不传 wp-code ⇒ 前缀分支不可达；未登记会回退通用 prompt 不报错
    expect(REVIEW_PY).toMatch(/78 个抽凭宿主/)
  })
})

// ─── R10.3：只读态门控 ──────────────────────────────────────────────────────

describe('R10.3：只读态禁用配置与回填入口', () => {
  it('引擎声明 readonly prop 且默认不传即可编辑（零回归）', () => {
    expect(ENGINE).toMatch(/readonly\?:\s*boolean/)
  })

  it('行可编辑判定合并只读态（canEditRow）', () => {
    expect(ENGINE).toMatch(/function canEditRow\(row: SampledVoucher\): boolean \{/)
    expect(ENGINE).toMatch(/return !props\.readonly && isRowEditable\(row\)/)
  })

  it('模板一律走 canEditRow，不再直接用 isRowEditable', () => {
    const tmpl = ENGINE.slice(ENGINE.indexOf('<template>'), ENGINE.lastIndexOf('</template>'))
    expect(tmpl).not.toContain('isRowEditable(')
    expect((tmpl.match(/canEditRow\(row\)/g) || []).length).toBeGreaterThan(5)
  })

  it('关键录入与操作入口按 readonly 禁用', () => {
    for (const anchor of [
      'reconcileOverrideReason',
      'bookAmountInput',
      'reconcileThresholdPct',
      'handleConfirmConclusion',
      'handleInferMisstatement',
    ]) {
      const at = ENGINE.indexOf(anchor)
      expect(at, `未找到 ${anchor}`).toBeGreaterThan(-1)
    }
    // props.readonly 至少覆盖 5 个入口 + canEditRow 内部 1 处
    expect((ENGINE.match(/props\.readonly/g) || []).length).toBeGreaterThanOrEqual(6)
  })

  it('反向自检：canEditRow 若丢掉 readonly 判定即打红', () => {
    const mutated = ENGINE.replace(
      'return !props.readonly && isRowEditable(row)',
      'return isRowEditable(row)',
    )
    expect(mutated).not.toMatch(/return !props\.readonly && isRowEditable\(row\)/)
  })
})
