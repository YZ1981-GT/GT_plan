/**
 * l0LowerZone.spec.ts — L0-1 下区文案守卫
 *
 * spec: l0-confirmation-source-alignment，Task 13
 *   Property 14（下区文案忠于源模板）
 *   Property 15（审计说明序号笔误已更正且留证）
 *   Property 16（下区键空间不与上区冲突）
 *
 * 🔴 源模板字面以 openpyxl 直读的后端守卫 `test_l0_source_template_facts.py` 为裁决者，
 * 本文件读它的常量做**跨前后端交叉锁死**（改一侧必打红）。
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  CONVERGENCE_TARGET,
  L0_ATTACHED_EVIDENCE_NOTE,
  L0_AUDIT_NOTE_DEFS,
  L0_CONCLUSION_FIELD,
  L0_LOWER_KEY_PREFIX,
  L0_LOWER_ZONE_FIELDS,
  L0_REFERENCE_CONCLUSIONS,
  L0_REFERENCE_CONCLUSION_TITLE,
  L0_SAMPLE_SELECTION_DEFS,
  L0_SECTION_TITLES,
  L0_SECTION_TITLE_BY_ID,
} from '../l0SummaryLowerZone'
import { L0_MATRIX_KEY_PREFIX } from '../l0MatrixDataSources'

function findRepoRoot(): string {
  const sentinels = [
    path.join('backend', 'app', 'services', 'four_table', 'l_cycle_specs.py'),
    path.join('backend', 'wp_templates', 'L', 'L0 债务循环函证.xlsx'),
  ]
  let dir = process.cwd()
  for (let i = 0; i < 12; i += 1) {
    if (sentinels.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到仓库根；cwd=${process.cwd()}`)
}

const REPO_ROOT = findRepoRoot()
const BACKEND_GUARD = path.join(REPO_ROOT, 'backend', 'tests', 'test_l0_source_template_facts.py')

// ─── Property 14：下区文案忠于源模板 ───────────────────────────────────────

describe('Property 14: 二、样本选择 6 项', () => {
  it('恰 6 项', () => {
    expect(L0_SAMPLE_SELECTION_DEFS).toHaveLength(6)
  })

  it('label 逐字取自源 J29/J30/J31/J32/J34/J35', () => {
    expect(L0_SAMPLE_SELECTION_DEFS.map((d) => d.label)).toEqual([
      '测试总体', '特定样本', '抽样总体', '确定的抽样样本量', '抽样方法', '抽样过程',
    ])
    expect(L0_SAMPLE_SELECTION_DEFS.map((d) => d.source_ref)).toEqual([
      'L0-1!J29', 'L0-1!J30', 'L0-1!J31', 'L0-1!J32', 'L0-1!J34', 'L0-1!J35',
    ])
  })

  it('field 序列逐字钉死（持久化键不得漂移，否则既有录入值失联）', () => {
    // 🔴 2026-08-05 变异检验补：把 `sample-6` 改名成 `sampleX` 时原守卫**未打红**
    //    —— 长度/label/source_ref 三条断言都不覆盖 field 名。持久化键漂移
    //    = 既有项目已录入的内容读不回来，属数据零丢失红线，必须逐字钉死。
    expect(L0_SAMPLE_SELECTION_DEFS.map((d) => d.field)).toEqual([
      'L0-1-lower-sample-1',
      'L0-1-lower-sample-2',
      'L0-1-lower-sample-3',
      'L0-1-lower-sample-4',
      'L0-1-lower-sample-5',
      'L0-1-lower-sample-6',
    ])
  })

  it('K33 括注是提示文本不是独立录入项（J33 源模板无标签）', () => {
    const sample4 = L0_SAMPLE_SELECTION_DEFS[3]
    expect(sample4.source_ref).toBe('L0-1!J32')
    expect(sample4.hint).toContain('样本计算器')
    // 不存在指向 J33 的独立项
    expect(L0_SAMPLE_SELECTION_DEFS.some((d) => d.source_ref === 'L0-1!J33')).toBe(false)
  })

  it('抽样过程合并 K35 + K36（源模板一句话拆两格）', () => {
    const sample6 = L0_SAMPLE_SELECTION_DEFS[5]
    expect(sample6.mergedFrom).toEqual(['L0-1!K35', 'L0-1!K36'])
    expect(sample6.placeholder).toContain('使用IDEA')
    expect(sample6.placeholder).toContain('抽样工具中的样本选择过程和结果见')
    // 🔴 只取 K35 会以逗号结尾（半句话）
    expect(sample6.placeholder.trimEnd().endsWith('，')).toBe(false)
  })

  it('反向自检：只取前格会得到以逗号结尾的半句话', () => {
    const headOnly = '使用IDEA（XX抽样工具）选取样本进行函证，长期应付款选择XX个供应商、金额XX的样本，'
    expect(headOnly.trimEnd().endsWith('，')).toBe(true)     // 复现缺陷形态
    expect(L0_SAMPLE_SELECTION_DEFS[5].placeholder).not.toBe(headOnly)
  })
})

describe('Property 14: 三、审计说明 5 段', () => {
  it('恰 5 段，label 带源模板序号 1~5', () => {
    expect(L0_AUDIT_NOTE_DEFS).toHaveLength(5)
    expect(L0_AUDIT_NOTE_DEFS.map((d) => d.label)).toEqual([
      '1、对询证函保持的控制的说明',
      '2、对误差的分析',
      '3、对以传真或电子邮件形式收到的回函的可靠性的考虑（L0-6）',
      '4、针对不符事项的程序',
      '5、针对未回函的替代程序',
    ])
  })

  it('source_ref 对应源 S29 / W29 / S33 / S34 / S36', () => {
    expect(L0_AUDIT_NOTE_DEFS.map((d) => d.source_ref)).toEqual([
      'L0-1!S29', 'L0-1!W29', 'L0-1!S33', 'L0-1!S34', 'L0-1!S36',
    ])
  })

  it('field 序列逐字钉死（同上，防持久化键漂移）', () => {
    expect(L0_AUDIT_NOTE_DEFS.map((d) => d.field)).toEqual([
      'L0-1-lower-audit-note-1',
      'L0-1-lower-audit-note-2',
      'L0-1-lower-audit-note-3',
      'L0-1-lower-audit-note-4',
      'L0-1-lower-audit-note-5',
    ])
  })

  it('误差界定条件合并 W30 + W31（前格无右方括号）', () => {
    const note2 = L0_AUDIT_NOTE_DEFS[1]
    expect(note2.mergedFrom).toEqual(['L0-1!W30', 'L0-1!W31'])
    expect(note2.hint).toContain('［')
    expect(note2.hint).toContain('］')      // 🔴 只取 W30 会缺这个
    expect(note2.hint).toContain('万元')
  })

  it('不符事项程序合并 S34 + S35（S35 是补充说明）', () => {
    const note4 = L0_AUDIT_NOTE_DEFS[3]
    expect(note4.mergedFrom).toEqual(['L0-1!S34', 'L0-1!S35'])
    expect(note4.hint).toContain('未函证的其他信息')
  })

  it('S33 的（L0-6）是正确索引号，不得被当笔误改掉', () => {
    expect(L0_AUDIT_NOTE_DEFS[2].label).toContain('（L0-6）')
    expect(L0_AUDIT_NOTE_DEFS[2].label).not.toContain('F0-6')
  })

  it('三处合并登记齐全（样本 1 处 + 说明 2 处）', () => {
    const merged = [...L0_SAMPLE_SELECTION_DEFS, ...L0_AUDIT_NOTE_DEFS]
      .filter((d) => d.mergedFrom)
    expect(merged).toHaveLength(3)
  })
})

// ─── Property 15：序号笔误已更正且留证 ─────────────────────────────────────

describe('Property 15: 审计说明序号笔误与参考结论', () => {
  it('审计说明展示「三、」而源模板字面是「二、」', () => {
    const s = L0_SECTION_TITLE_BY_ID.auditNote
    expect(s.display).toBe('三、审计说明')
    expect(s.sourceLiteral).toBe('二、审计说明')
    expect(s.source_ref).toBe('L0-1!S28')
    expect(s.typoNote).toBeTruthy()
    expect(s.typoNote).toContain('笔误')
  })

  it('其余三段无笔误（display === sourceLiteral）', () => {
    for (const s of L0_SECTION_TITLES) {
      if (s.id === 'auditNote') continue
      expect(s.display, `${s.id} 不应有笔误`).toBe(s.sourceLiteral)
      expect(s.typoNote).toBeUndefined()
    }
  })

  it('四段序号连续（一、二、三、四）', () => {
    expect(L0_SECTION_TITLES.map((s) => s.display[0])).toEqual(['一', '二', '三', '四'])
  })

  it('与后端笔误登记表交叉锁死', () => {
    const src = fs.readFileSync(BACKEND_GUARD, 'utf-8')
    expect(src).toContain('L0-1!S28')
    expect(src).toContain('二、审计说明')
    expect(src).toContain('三、审计说明')
  })

  it('参考结论 3 条 + 后附证据说明（只读展示）', () => {
    expect(L0_REFERENCE_CONCLUSIONS).toHaveLength(3)
    expect(L0_REFERENCE_CONCLUSIONS.map((c) => c.code)).toEqual(['A', 'B', 'C'])
    expect(L0_REFERENCE_CONCLUSIONS[0].text).toBe('未见异常。')
    expect(L0_REFERENCE_CONCLUSION_TITLE).toBe('参考结论：')
    expect(L0_ATTACHED_EVIDENCE_NOTE).toContain('询证函回函')
  })

  it('参考结论字面与后端守卫常量一致', () => {
    const src = fs.readFileSync(BACKEND_GUARD, 'utf-8')
    for (const c of L0_REFERENCE_CONCLUSIONS) {
      expect(src, `后端应含参考结论「${c.text}」`).toContain(c.text)
    }
    expect(src).toContain(L0_ATTACHED_EVIDENCE_NOTE)
  })
})

// ─── Property 16：键空间 ───────────────────────────────────────────────────

describe('Property 16: 下区键空间不与上区冲突', () => {
  it('全部下区键以 L0-1-lower 开头', () => {
    expect(L0_LOWER_KEY_PREFIX).toBe('L0-1-lower')
    for (const f of L0_LOWER_ZONE_FIELDS) {
      expect(f.startsWith(L0_LOWER_KEY_PREFIX), `键 ${f} 前缀不符`).toBe(true)
    }
  })

  it('键集恰 12 个（6 样本 + 5 说明 + 1 结论）且无重复', () => {
    expect(L0_LOWER_ZONE_FIELDS).toHaveLength(12)
    expect(new Set(L0_LOWER_ZONE_FIELDS).size).toBe(12)
  })

  it('结论键在集合内', () => {
    expect(L0_CONCLUSION_FIELD).toBe('L0-1-lower-conclusion')
    expect(L0_LOWER_ZONE_FIELDS).toContain(L0_CONCLUSION_FIELD)
  })

  it('下区键与矩阵手工覆盖键前缀不重叠', () => {
    expect(L0_LOWER_KEY_PREFIX).not.toBe(L0_MATRIX_KEY_PREFIX)
    for (const f of L0_LOWER_ZONE_FIELDS) {
      expect(f.startsWith(L0_MATRIX_KEY_PREFIX), `键 ${f} 侵入矩阵键空间`).toBe(false)
    }
  })

  it('键不含中文（持久化键一律 ASCII，避免编码问题）', () => {
    for (const f of L0_LOWER_ZONE_FIELDS) {
      expect(/[\u4e00-\u9fa5]/.test(f), `键 ${f} 含中文`).toBe(false)
    }
  })

  it('收敛锚点存在且与 G0 下区副本一致', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-lower-zone-convergence')
    const g0 = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components',
      'workpaper', 'g0-confirmation', 'g0SummaryLowerZone.ts')
    if (fs.existsSync(g0)) {
      expect(fs.readFileSync(g0, 'utf-8')).toContain(CONVERGENCE_TARGET)
    }
  })
})

// ─── 不预填示例文本 ────────────────────────────────────────────────────────

describe('源模板示例文本只作 placeholder，不预填', () => {
  it('每项都有 placeholder（源模板示例）', () => {
    for (const d of [...L0_SAMPLE_SELECTION_DEFS, ...L0_AUDIT_NOTE_DEFS]) {
      expect(d.placeholder.length, `${d.label} 缺 placeholder`).toBeGreaterThan(0)
    }
  })

  it('声明件不含 defaultValue/initialText 之类预填字段', () => {
    const src = fs.readFileSync(
      path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'confirmation', 'l0-confirmation', 'l0SummaryLowerZone.ts'),
      'utf-8',
    )
    expect(src).not.toContain('defaultValue')
    expect(src).not.toContain('initialText')
    expect(src).not.toContain('prefill')
  })
})
