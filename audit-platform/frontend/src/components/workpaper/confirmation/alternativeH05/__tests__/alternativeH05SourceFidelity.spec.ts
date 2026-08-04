/**
 * alternativeH05SourceFidelity.spec.ts — H0-5 替代程序源模板保真度守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 4.1~4.7；Property 12, 13
 *
 * 分工：与源 xlsx 的**逐字比对**由后端守卫
 * `backend/tests/test_h0_source_template_facts.py`（`test_h0_5_sample_fields_and_guidance`
 * / `test_h0_5_check_record_area_is_blank`）直读 openpyxl 裁决（前端读不了 xlsx）。
 * 本文件负责：
 *   ① 与该后端守卫的**交叉锁死**（读 .py 源码抽出标签/提示文字比对，改一侧另一侧必红）；
 *   ② 组件不得内联字面量（区块编号/标签/提示只许来自 h05SourceFidelity）；
 *   ③ 四区块 title 与 alternativeBlockManifest 逐字一致；
 *   ④ 自由记录区与源外增强标注确有渲染点。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  H05_CHECK_RECORD_FREE_KEY,
  H05_CHECK_RECORD_FREE_LABEL,
  H05_CHECK_RECORD_FREE_PLACEHOLDER,
  H05_GUIDANCE_GROUPS,
  H05_GUIDANCE_TITLE,
  H05_HEADER_TIP,
  H05_SAMPLING_FIELDS,
  H05_SAMPLING_METHOD_OPTIONS,
  H05_SECTION_TITLES,
  H05_SOURCE_EXTRA_BADGE,
  H05_SOURCE_EXTRA_REASON,
  h05SectionTitle,
} from '../h05SourceFidelity'
import { BLOCK_COLUMN_CONFIGS_H05 } from '../blockColumnConfigsH05'
import { ALTERNATIVE_BLOCK_MANIFEST } from '../../coordination/alternativeBlockManifest'

/** 仓库根定位（向上找哨兵**文件**，不写死回退级数） */
function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    // 🔴 哨兵必须是具体文件：`audit-platform/backend/app/routers` 目录也存在（历史遗留空目录），
    //    只判目录会在 audit-platform 层提前停下 → ENOENT（该陷阱已在 sendListSpec.spec.ts 实证）。
    if (fs.existsSync(path.join(dir, 'backend', 'tests', 'test_h0_source_template_facts.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from}）`)
}
const REPO_ROOT = findRepoRoot(__dirname)

const BACKEND_GUARD = fs.readFileSync(
  path.join(REPO_ROOT, 'backend', 'tests', 'test_h0_source_template_facts.py'),
  'utf-8',
)

const COMPONENT_PATH = path.join(__dirname, '..', 'GtConfirmationAlternativeH05.vue')
const COMPONENT_SRC = fs.readFileSync(COMPONENT_PATH, 'utf-8')

/** 去注释（HTML 注释 + JS 行/块注释），防「注释里写的反例被数成真实代码」 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, '$1')
}
const COMPONENT_CODE = stripComments(COMPONENT_SRC)

// ─── Property 12：6 个抽样字段与源模板交叉锁死 ───────────────────────────────

describe('Property 12: 抽样 6 字段与源模板逐字（跨后端守卫锁死）', () => {
  it('6 个字段齐备且 field 唯一', () => {
    expect(H05_SAMPLING_FIELDS).toHaveLength(6)
    const fields = H05_SAMPLING_FIELDS.map((f) => f.field)
    expect(new Set(fields).size).toBe(6)
  })

  it('标签与锚点与后端守卫抽出的 (anchor, label) 对逐条一致', () => {
    // 后端守卫里的形态：("A7", "测试范围"), ("A8", "抽样总体"), ... ("I9", "抽样过程"),
    const block = BACKEND_GUARD.slice(BACKEND_GUARD.indexOf('def test_h0_5_sample_fields_and_guidance'))
    const listStart = block.indexOf('for anchor, label in [')
    expect(listStart).toBeGreaterThan(0) // 正则失效自检
    const listEnd = block.indexOf(']:', listStart)
    const listBody = block.slice(listStart, listEnd)
    const pairs = [...listBody.matchAll(/\("([A-Z]+\d+)",\s*"([^"]+)"\)/g)].map((m) => [m[1], m[2]])
    expect(pairs).toHaveLength(6)

    const frontPairs = H05_SAMPLING_FIELDS.map((f) => [f.labelRef, f.label])
    // 后端顺序 A7/A8/A9/I7/I8/I9，前端按阅读顺序左右交错 → 用集合比对
    expect(new Set(frontPairs.map((p) => p.join('|')))).toEqual(
      new Set(pairs.map((p) => p.join('|'))),
    )
  })

  it('「确定的抽样样本量」不得退化为「样本量」（I8 源模板全称）', () => {
    const sampleSize = H05_SAMPLING_FIELDS.find((f) => f.field === 'sample_size')!
    expect(sampleSize.label).toBe('确定的抽样样本量')
    expect(sampleSize.labelRef).toBe('I8')
    expect(sampleSize.hint).toContain('样本计算器')
  })

  it('🔴 测试范围占位是借方发生额单侧，不得含 F0-5 的「贷方发生额」措辞', () => {
    const testScope = H05_SAMPLING_FIELDS.find((f) => f.field === 'test_scope')!
    expect(testScope.placeholder).toContain('借方发生额')
    expect(testScope.placeholder).not.toContain('贷方发生额')
    // 组件内也不得残留旧占位
    expect(COMPONENT_CODE).not.toContain('贷方发生额所有凭证')
  })

  it('抽样方法四选项逐字（含「（非统计抽样适用）」后缀不得被拆成 label/value 两值）', () => {
    expect(H05_SAMPLING_METHOD_OPTIONS).toEqual([
      '随机选样',
      '系统选样',
      '货币单元抽样',
      '随意选样（非统计抽样适用）',
    ])
    // 旧实现把 value 写成「随意选样」而 label 写「随意选样（非统计抽样适用）」→ 存库值与源模板不符
    expect(COMPONENT_CODE).not.toMatch(/value="随意选样"/)
  })

  it('每个字段都有占位与占位锚点，且占位非空', () => {
    for (const f of H05_SAMPLING_FIELDS) {
      expect(f.placeholder.length, f.field).toBeGreaterThan(0)
      expect(f.placeholderRef, f.field).toMatch(/^[A-Z]+\d+$/)
    }
  })
})

// ─── Property 12（续）：编制说明 3 条与后端守卫锁死 ──────────────────────────

describe('Property 12: 编制说明与源模板逐字', () => {
  it('「1、函证替代程序」3 条与后端守卫断言的 tips 逐字一致', () => {
    const block = BACKEND_GUARD.slice(BACKEND_GUARD.indexOf('def test_h0_5_sample_fields_and_guidance'))
    const start = block.indexOf('assert tips == [')
    expect(start).toBeGreaterThan(0) // 正则失效自检
    const body = block.slice(start, block.indexOf(']', start))
    const tips = [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1])
    expect(tips).toHaveLength(3)

    const group = H05_GUIDANCE_GROUPS.find((g) => g.anchor === 'A29')!
    expect(group.items.map((i) => i.text)).toEqual(tips)
  })

  it('「2、概述」两条含源模板原文（含前导空白的续行原样登记）', () => {
    const group = H05_GUIDANCE_GROUPS.find((g) => g.anchor === 'A34')!
    expect(group.items).toHaveLength(2)
    expect(group.items[0].sourceText).toBe('2、概述：（1）程序的测试情况、结果；')
    expect(group.items[1].sourceText).toMatch(/^ {2,}（2）/)
    expect(group.items[1].text).toBe(
      '（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。',
    )
  })

  it('顶部提示条取自编制说明第 ③ 条（不另写一份）', () => {
    expect(H05_HEADER_TIP).toBe(
      '③对回函可能性不高的、余额重大的，发函同时执行替代程序。',
    )
    expect(H05_GUIDANCE_TITLE).toBe('编制说明')
  })
})

// ─── Property 13：区块编号与源模板一致 + 源外增强标注 ─────────────────────────

describe('Property 13: 四段编号与源模板一致', () => {
  it('一/二/三/四 = 样本选取 / 检查过程记录 / 审计说明 / 审计结论', () => {
    expect(H05_SECTION_TITLES.map((s) => s.title)).toEqual([
      '一、样本选取标准与规模',
      '二、检查过程记录',
      '三、审计说明',
      '四、审计结论',
    ])
    expect(H05_SECTION_TITLES.map((s) => s.anchor)).toEqual(['A6', 'A10', 'A20', 'A23'])
    expect(h05SectionTitle('check_record')).toBe('二、检查过程记录')
  })

  it('组件不得残留改造前的错位编号', () => {
    for (const stale of [
      '二、余额汇总与检查比例',
      '三、检查过程记录',
      '四、审计说明与结论',
    ]) {
      expect(COMPONENT_CODE, stale).not.toContain(stale)
    }
  })

  it('组件不得内联区块标题字面量（只许引用 sectionTitles）', () => {
    for (const title of H05_SECTION_TITLES.map((s) => s.title)) {
      expect(COMPONENT_CODE, title).not.toContain(title)
    }
    expect(COMPONENT_CODE).toContain('sectionTitles.check_record')
  })

  it('反向自检：未去注释的原始源码确实含被禁字样（否则上条断言空转）', () => {
    // 组件注释里写明了源模板四段编号，故原始源码必然含这些字样；
    // 若某天注释被清掉，本条会提醒把自检基准换掉。
    expect(COMPONENT_SRC).toContain('二、检查过程记录')
  })

  it('审计说明与审计结论是两个独立区块（各自有 data-testid）', () => {
    expect(COMPONENT_SRC).toContain('data-testid="h05-section-audit-note"')
    expect(COMPONENT_SRC).toContain('data-testid="h05-section-conclusion"')
    expect(COMPONENT_SRC).toContain('data-testid="h05-section-sampling"')
    expect(COMPONENT_SRC).toContain('data-testid="h05-section-check-record"')
  })
})

describe('Property 13: 自由记录区与源外增强标注', () => {
  it('自由记录区常量与渲染点齐备', () => {
    expect(H05_CHECK_RECORD_FREE_KEY).toBe('H0-5-check-record-free')
    expect(H05_CHECK_RECORD_FREE_LABEL.length).toBeGreaterThan(0)
    expect(H05_CHECK_RECORD_FREE_PLACEHOLDER).toContain('空白自由记录区')
    expect(COMPONENT_SRC).toContain('data-testid="h05-check-record-free"')
    expect(COMPONENT_CODE).toContain('checkRecordFree')
  })

  it('自由记录区落在 AlternativeCompany.check_record_free（随 buildPayload 持久化）', () => {
    expect(COMPONENT_CODE).toContain('check_record_free')
    const typesSrc = fs.readFileSync(
      path.join(__dirname, '..', '..', 'alternativeD05', 'alternativeD05Types.ts'),
      'utf-8',
    )
    expect(typesSrc).toContain('check_record_free?: string')
  })

  it('源外增强标注文字含依据说明并有渲染点', () => {
    expect(H05_SOURCE_EXTRA_BADGE).toContain('平台增强')
    expect(H05_SOURCE_EXTRA_REASON).toContain('空白自由记录区')
    expect(H05_SOURCE_EXTRA_REASON).toContain('sourceExtra')
    expect(COMPONENT_SRC).toContain('data-testid="h05-source-extra-notice"')
  })

  it('后端守卫确实断言了该区为空白（本标注的事实基础）', () => {
    expect(BACKEND_GUARD).toContain('def test_h0_5_check_record_area_is_blank')
    expect(BACKEND_GUARD).toContain('二、检查过程记录：')
  })
})

// ─── Property 13：四区块 title 与 manifest 逐字一致 ───────────────────────────

describe('Property 13: 四区块 title 与 alternativeBlockManifest 对齐', () => {
  it('BLOCK_COLUMN_CONFIGS_H05 的 title 与 manifest.H05 逐字一致', () => {
    const manifest = ALTERNATIVE_BLOCK_MANIFEST.H05
    expect(manifest).toHaveLength(4)
    for (const spec of manifest) {
      const cfg = BLOCK_COLUMN_CONFIGS_H05[spec.block]
      expect(cfg, spec.block).toBeTruthy()
      expect(cfg.title, spec.block).toBe(spec.title)
    }
  })

  it('manifest.H05 四区块全部登记为源外增强且带依据', () => {
    for (const spec of ALTERNATIVE_BLOCK_MANIFEST.H05) {
      expect(spec.sourceExtra, spec.block).toBe(true)
      expect((spec.sourceExtraReason || '').length, spec.block).toBeGreaterThan(10)
    }
  })

  it('反向自检：改造前的 title 形态（「1、期后验收/权属证据检查」）不得复活', () => {
    const titles = Object.values(BLOCK_COLUMN_CONFIGS_H05).map((c) => c.title)
    for (const t of titles) {
      expect(t, t).not.toMatch(/^\d、/)
    }
  })
})
