/**
 * h0SummaryLowerZone.spec.ts — H0-1 下区固定文字真源守卫（前端侧）
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 2.6~2.10；Property 7
 *
 * 分工：与源 xlsx 的**逐字比对**由后端守卫
 * `backend/tests/test_h0_source_template_facts.py` 直读 openpyxl 裁决
 * （前端读不了 xlsx）；本文件负责常量内部一致性、跨格合并完整性、笔误登记、
 * 持久化 key 形态与 AI section 齐备性。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  H0_AI_SECTIONS,
  H0_AUDIT_NOTE_KEY_PREFIX,
  H0_AUDIT_NOTE_SECTIONS,
  H0_CONCLUSION_KEY,
  H0_LOWER_ZONE_BLOCKS,
  H0_LOWER_ZONE_TEXTS,
  H0_REFERENCE_CONCLUSIONS,
  H0_SAMPLE_KEY_PREFIX,
  H0_SAMPLE_SELECTION_FIELDS,
  getH0TextsForBlock,
  h0AuditNoteItemId,
  h0SampleItemId,
} from '../h0SummaryLowerZone'

/** 仓库根定位（向上找含 backend/ 的目录，不写死回退级数） */
function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    // 🔴 哨兵必须是具体文件：`audit-platform/backend/app/routers` 目录也存在（历史遗留空目录），
    //    只判目录会在 audit-platform 层提前停下 → ENOENT。
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'routers', 'wp_render_strategies', '_h0_confirmation_ai.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from}）`)
}
const REPO_ROOT = findRepoRoot(__dirname)

// ─── 四块锚点与标题 ──────────────────────────────────────────────────────────

describe('四块锚点与标题', () => {
  it('四块锚点逐字（C28 / J28 / S28 / C39）', () => {
    expect(H0_LOWER_ZONE_BLOCKS.matrix.anchor).toBe('C28')
    expect(H0_LOWER_ZONE_BLOCKS.sample_selection.anchor).toBe('J28')
    expect(H0_LOWER_ZONE_BLOCKS.audit_note.anchor).toBe('S28')
    expect(H0_LOWER_ZONE_BLOCKS.conclusion.anchor).toBe('C39')
  })

  it('标题按「一、二、三、四」连续编号（修正源模板笔误）', () => {
    expect(H0_LOWER_ZONE_BLOCKS.matrix.title).toBe('一、函证情况')
    expect(H0_LOWER_ZONE_BLOCKS.sample_selection.title).toBe('二、样本选择')
    expect(H0_LOWER_ZONE_BLOCKS.audit_note.title).toBe('三、审计说明')
    expect(H0_LOWER_ZONE_BLOCKS.conclusion.title).toBe('四、审计结论')
  })

  it('源模板 S28 编号笔误已登记原文（防被「顺手修正」后与 xlsx 比对打红）', () => {
    // 🔴 源模板 S28 原文是「二、审计说明」，与 J28 的「二、样本选择」撞号
    expect(H0_LOWER_ZONE_BLOCKS.audit_note.sourceText).toBe('二、审计说明')
    expect(H0_LOWER_ZONE_BLOCKS.audit_note.sourceText).not.toBe(
      H0_LOWER_ZONE_BLOCKS.audit_note.title,
    )
  })
})

// ─── 二、样本选择 6 字段 ─────────────────────────────────────────────────────

describe('二、样本选择（6 字段）', () => {
  it('恰好 6 个字段，标签与锚点逐字', () => {
    expect(H0_SAMPLE_SELECTION_FIELDS.map((f) => [f.label, f.anchor])).toEqual([
      ['测试总体', 'J29'],
      ['特定样本', 'J30'],
      ['抽样总体', 'J31'],
      ['确定的抽样样本量', 'J32'],
      ['抽样方法', 'J34'],
      ['抽样过程', 'J35'],
    ])
  })

  it('标签不带尾冒号（源模板带「：」，常量去掉由 UI 加）', () => {
    for (const f of H0_SAMPLE_SELECTION_FIELDS) {
      expect(f.label.endsWith('：')).toBe(false)
      expect(f.label.endsWith(':')).toBe(false)
    }
  })

  it('每个字段都有 placeholder（源模板示例文字）', () => {
    for (const f of H0_SAMPLE_SELECTION_FIELDS) {
      expect(f.placeholder.trim().length).toBeGreaterThan(4)
    }
  })

  it('跨格合并的 placeholder 锚点用 + 连接且是完整句（无半句话）', () => {
    const sampleSize = H0_SAMPLE_SELECTION_FIELDS.find((f) => f.key === 'sample_size')!
    expect(sampleSize.placeholderAnchor).toBe('K32+K33')
    // K32 尾「共XX个供应商；」+ K33「（如果使用了样本计算器…）」两格拼成整句
    expect(sampleSize.placeholder).toContain('分别抽取XX个')
    expect(sampleSize.placeholder).toContain('样本量计算过程见<XX>底稿')

    const process = H0_SAMPLE_SELECTION_FIELDS.find((f) => f.key === 'sampling_process')!
    expect(process.placeholderAnchor).toBe('K35+K36+K37')
    expect(process.placeholder).toContain('使用IDEA')
    expect(process.placeholder).toContain('抽样工具中的样本选择过程和结果见<XX>底稿')
  })

  it('抽样过程示例保留源模板残留措辞「预付账款/应付票据」（F0 模板复制痕迹，源模板事实）', () => {
    const process = H0_SAMPLE_SELECTION_FIELDS.find((f) => f.key === 'sampling_process')!
    expect(process.placeholder).toContain('预付账款')
    expect(process.placeholder).toContain('应付票据')
  })

  it('字段 key 唯一且持久化 itemId 形态稳定', () => {
    const keys = H0_SAMPLE_SELECTION_FIELDS.map((f) => f.key)
    expect(new Set(keys).size).toBe(keys.length)
    expect(h0SampleItemId('population')).toBe('H0-1-lower-sample-population')
    expect(H0_SAMPLE_KEY_PREFIX).toBe('H0-1-lower-sample-')
  })
})

// ─── 三、审计说明 5 小节 ─────────────────────────────────────────────────────

describe('三、审计说明（5 小节）', () => {
  it('恰好 5 个小节，标题与锚点逐字（含「N、」序号）', () => {
    expect(H0_AUDIT_NOTE_SECTIONS.map((s) => [s.title, s.anchor])).toEqual([
      ['1、对询证函保持的控制的说明', 'S29'],
      ['2、对误差的分析', 'W29'],
      ['3、对以传真或电子邮件形式收到的回函的可靠性的考虑（H0-6）', 'S33'],
      ['4、针对不符事项的程序', 'S34'],
      ['5、针对未回函的替代程序', 'S37'],
    ])
  })

  it('第 2 小节的误差构成条件由 W30+W31 合并为整句（否则界面出现半句话）', () => {
    const s = H0_AUDIT_NOTE_SECTIONS.find((x) => x.key === 'error_analysis')!
    expect(s.hintAnchor).toBe('W30+W31')
    // W30 结尾是「…账户余额人民币」，W31 开头是「（）万元，…」
    expect(s.hint).toContain('界定误差构成条件')
    expect(s.hint).toContain('账户余额人民币（）万元')
    expect(s.hint!.endsWith('］')).toBe(true)
  })

  it('第 4 小节挂 S35 的未函证其他信息提示', () => {
    const s = H0_AUDIT_NOTE_SECTIONS.find((x) => x.key === 'mismatch')!
    expect(s.hintAnchor).toBe('S35')
    expect(s.hint).toContain('未函证的其他信息')
  })

  it('第 3 小节标题内引 H0-6（可靠性验证底稿）', () => {
    const s = H0_AUDIT_NOTE_SECTIONS.find((x) => x.key === 'reliability')!
    expect(s.title).toContain('（H0-6）')
  })

  it('小节 key 唯一、AI section 唯一且带 h0_ 前缀', () => {
    const keys = H0_AUDIT_NOTE_SECTIONS.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
    expect(new Set(H0_AI_SECTIONS).size).toBe(H0_AI_SECTIONS.length)
    // 与 H0 专属 AI 端点 `_h0_confirmation_ai.py` 的 kebab-case 命名一致
    for (const id of H0_AI_SECTIONS) {
      expect(id).toMatch(/^summary-[a-z-]+$/)
    }
  })

  it('AI section 全部已在后端 `_h0_confirmation_ai.py` 的 _SUPPORTED_SECTIONS 登记', () => {
    // 「有 AI 按钮」≠「AI 能用」：未登记的 section 会被端点 400 拒绝且被 catch 吞掉
    const py = fs.readFileSync(
      path.join(REPO_ROOT, 'backend', 'app', 'routers', 'wp_render_strategies', '_h0_confirmation_ai.py'),
      'utf-8',
    )
    const m = /_SUPPORTED_SECTIONS\s*=\s*\{([\s\S]*?)\}/.exec(py)
    expect(m, '未解析出 _SUPPORTED_SECTIONS').toBeTruthy()
    const registered = new Set([...m![1].matchAll(/"([^"]+)"/g)].map((x) => x[1]))
    expect(registered.size).toBeGreaterThan(2)
    for (const id of [...H0_AI_SECTIONS, 'summary-conclusion']) {
      expect(registered.has(id), `section "${id}" 未在后端登记`).toBe(true)
    }
  })

  it('后端每条 H0-1 下区 prompt ≥40 字且含「不得虚构」约束', () => {
    const py = fs.readFileSync(
      path.join(REPO_ROOT, 'backend', 'app', 'routers', 'wp_render_strategies', '_h0_confirmation_ai.py'),
      'utf-8',
    )
    for (const id of [...H0_AI_SECTIONS, 'summary-conclusion']) {
      const idx = py.indexOf(`"${id}": (`)
      expect(idx, `prompt "${id}" 未定义`).toBeGreaterThan(-1)
      const block = py.slice(idx, py.indexOf('),', idx))
      expect(block.length, `prompt "${id}" 过短（会诱导自造内容）`).toBeGreaterThan(40)
      expect(block, `prompt "${id}" 缺「不得虚构」约束`).toContain('_NO_FABRICATION')
    }
  })

  it('持久化 itemId 形态稳定', () => {
    expect(H0_AUDIT_NOTE_KEY_PREFIX).toBe('H0-1-lower-audit-note-')
    expect(h0AuditNoteItemId('control')).toBe('H0-1-lower-audit-note-control')
    expect(H0_CONCLUSION_KEY).toBe('H0-1-lower-conclusion')
  })
})

// ─── 四、审计结论 参考结论 ───────────────────────────────────────────────────

describe('四、审计结论（参考结论 A/B/C）', () => {
  it('三条参考结论逐字（源模板 A66:B68）', () => {
    expect(H0_REFERENCE_CONCLUSIONS.map((r) => r.code)).toEqual(['A', 'B', 'C'])
    expect(H0_REFERENCE_CONCLUSIONS[0].text).toBe('未见异常。')
    expect(H0_REFERENCE_CONCLUSIONS[1].text).toBe(
      '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    )
    expect(H0_REFERENCE_CONCLUSIONS[2].text).toBe(
      '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
    )
  })

  it('锚点跨两格（序号格 + 文字格）', () => {
    for (const r of H0_REFERENCE_CONCLUSIONS) {
      expect(r.anchor).toMatch(/^A\d+\+B\d+$/)
    }
  })
})

// ─── 只读方法论上下文（编制说明） ────────────────────────────────────────────

describe('编制说明（只读方法论上下文）', () => {
  it('全部为 readonly=true 且归入 guidance 块', () => {
    const g = getH0TextsForBlock('guidance')
    expect(g.length).toBeGreaterThanOrEqual(5)
    for (const t of g) {
      expect(t.readonly).toBe(true)
      expect(t.block).toBe('guidance')
    }
  })

  it('准则 1312 第十条六项齐备（逐条）', () => {
    const t = H0_LOWER_ZONE_TEXTS.find((x) => x.key === 'sample_selection_standard')!
    expect(t.text).toContain('《中国注册会计师审计准则第1312号——函证》第十条')
    for (const item of ['（一）金额较大的项目', '（二）账龄较长的项目', '（三）交易频繁但期末余额较小的项目',
      '（四）重大关联方交易', '（五）重大或异常的交易', '（六）可能存在争议以及产生重大舞弊或错误的交易']) {
      expect(t.text).toContain(item)
    }
  })

  it('准则六项的全角缩进空格逐字保留（源模板 A49~A53）', () => {
    const t = H0_LOWER_ZONE_TEXTS.find((x) => x.key === 'sample_selection_standard')!
    expect(t.text).toContain('\u3000\u3000（二）账龄较长的项目')
  })

  it('函证注意事项八条齐备（①~⑧）', () => {
    const t = H0_LOWER_ZONE_TEXTS.find((x) => x.key === 'confirmation_cautions')!
    for (const mark of ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']) {
      expect(t.text).toContain(mark)
    }
    expect(t.text).toContain('⑧未回函的全部执行替代程序。')
  })

  it('文字 key 唯一、锚点非空、无 markdown 粗体标记', () => {
    const keys = H0_LOWER_ZONE_TEXTS.map((t) => t.key)
    expect(new Set(keys).size).toBe(keys.length)
    for (const t of H0_LOWER_ZONE_TEXTS) {
      expect(t.anchor.trim().length).toBeGreaterThan(1)
      expect(t.text).not.toContain('**')
    }
  })

  it('多格合并的文字锚点用 + 连接', () => {
    for (const t of H0_LOWER_ZONE_TEXTS) {
      const parts = t.anchor.split('+')
      if (parts.length > 1) {
        for (const p of parts) expect(p).toMatch(/^[A-Z]+\d+$/)
      }
    }
  })
})
