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

  // 引擎表里只有本次抽出的样本（都是项目当前阶段）；「年审阶段预审行只读」改在宿主底稿行上做
  // （shared/voucherCheckFill 的 rowClass / guardPersist，voucher-identity-writeback-and-audit-phase 任务 9）
  //
  // 只读真源是 `isReadonly`（prop 与底稿运行时上下文取或）：78 个宿主都不传 readonly prop，
  // 归档 / 编辑锁 / 复核身份 / 后台合并的只读只在 WorkpaperRuntimeContext.readonly 上
  // （spec voucher-workflow-linkage-lineage-closure R4.1）。只认 props.readonly 等于这些场景照样能改。
  const IS_READONLY = /const isReadonly = computed\(\(\) => !!props\.readonly \|\| !!workpaperRuntime\?\.readonly\?\.value\)/
  const CAN_EDIT_ROW = /function canEditRow\(_?row: SampledVoucher\): boolean \{\s*return !isReadonly\.value\s*\}/

  /** 模板里包含 anchor 的那个开始标签（el-* 与子组件都算；属性值里的 `=>` 不截断） */
  function tagContaining(src: string, anchor: string): string {
    const tmpl = src.slice(src.indexOf('<template>'), src.lastIndexOf('</template>'))
    const tags = tmpl.match(/<[A-Za-z][\w-]*(?:[^>"]|"[^"]*")*>/g) || []
    return tags.find(t => t.includes(anchor)) || ''
  }

  const GATED_CONTROLS = [
    'v-model="reconcileOverrideReason"',
    'v-model="bookAmountInput"',
    'v-model="reconcileThresholdPct"',
    '@click="handleConfirmConclusion"',
    '@click="handleInferMisstatement"',
    '@click="handleOpenConfig"',
  ]

  it('只读真源合并 prop 与底稿运行时只读', () => {
    expect(ENGINE).toMatch(IS_READONLY)
    // inject 在 setup 顶层（写进函数体会静默拿不到）
    expect(ENGINE).toMatch(/\nconst workpaperRuntime = inject\(WorkpaperRuntimeContextKey, null\)/)
  })

  it('行可编辑判定合并只读态（canEditRow）', () => {
    expect(ENGINE).toMatch(CAN_EDIT_ROW)
  })

  it('模板一律走 canEditRow，不再直接用 isRowEditable', () => {
    const tmpl = ENGINE.slice(ENGINE.indexOf('<template>'), ENGINE.lastIndexOf('</template>'))
    expect(tmpl).not.toContain('isRowEditable(')
    expect((tmpl.match(/canEditRow\(row\)/g) || []).length).toBeGreaterThan(5)
  })

  it('关键录入与操作入口按 isReadonly 禁用（逐个控件看自己的 disabled）', () => {
    for (const anchor of GATED_CONTROLS) {
      const tag = tagContaining(ENGINE, anchor)
      expect(tag, `模板里未找到 ${anchor}`).not.toBe('')
      expect(tag, `${anchor} 未按 isReadonly 禁用`).toMatch(/:disabled="isReadonly(?:\s*\|\||")/)
    }
    // 模板不再直接读 props.readonly（只读一律走 isReadonly，否则运行时只读漏掉）
    const tmpl = ENGINE.slice(ENGINE.indexOf('<template>'), ENGINE.lastIndexOf('</template>'))
    expect(tmpl).not.toMatch(/props\.readonly/)
  })

  it('预览弹窗、撤销与确认回填同读 isReadonly', () => {
    expect(tagContaining(ENGINE, ':confirming="confirming"')).toMatch(/:readonly="isReadonly"/)
    expect(ENGINE).toMatch(/useEngineUndo\(\{[\s\S]{0,200}readonly: isReadonly/)
    expect(ENGINE).toMatch(/async function handleConfirmFill\(\) \{\s*if \(confirming\.value \|\| isReadonly\.value\) return/)
    // 单飞要真的置位：回填前置 true、结束（成功或失败）后复位；只有早退没有置位等于没挡
    expect(ENGINE).toMatch(/confirming\.value = true\s*\n\s*const result = await confirmFill\(\)\.finally\(\(\) => \{ confirming\.value = false \}\)/)
  })

  it('记入错报汇总（A13 推送）是写操作：只读时不能推，并说明原因', () => {
    const push = /const canPushProjected = computed\(\(\) => \{([\s\S]*?)\n\}\)/.exec(ENGINE)
    expect(push, '未截到 canPushProjected').not.toBeNull()
    expect(push![1]).toMatch(/^\s*if \(isReadonly\.value\) return false\n/)
    const reason = /const pushProjectedDisabledReason = computed\(\(\) => \{([\s\S]*?)\n\}\)/.exec(ENGINE)
    expect(reason, '未截到 pushProjectedDisabledReason').not.toBeNull()
    expect(reason![1]).toMatch(/^\s*if \(isReadonly\.value\) return '底稿只读，不能记入错报汇总'\n/)
  })

  it('反向自检：canEditRow 若丢掉 readonly 判定即打红', () => {
    const mutated = ENGINE.replace(/(function canEditRow\(_?row: SampledVoucher\): boolean \{\s*)return !isReadonly\.value/, '$1return true')
    expect(mutated).not.toBe(ENGINE)
    expect(mutated).not.toMatch(CAN_EDIT_ROW)
  })

  it('反向自检：isReadonly 只认 prop（丢掉运行时只读）即打红', () => {
    const mutated = ENGINE.replace(' || !!workpaperRuntime?.readonly?.value)', ')')
    expect(mutated).not.toBe(ENGINE)
    expect(mutated).not.toMatch(IS_READONLY)
  })

  it('反向自检：任一入口丢掉 disabled 即打红', () => {
    const mutated = ENGINE.replace(':disabled="isReadonly" @click="handleOpenConfig"', '@click="handleOpenConfig"')
    expect(mutated).not.toBe(ENGINE)
    expect(tagContaining(mutated, '@click="handleOpenConfig"')).not.toMatch(/:disabled="isReadonly(?:\s*\|\||")/)
  })
})
