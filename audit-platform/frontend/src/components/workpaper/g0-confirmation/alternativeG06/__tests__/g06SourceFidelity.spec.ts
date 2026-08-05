/**
 * g06SourceFidelity.spec.ts — G0-6 **段结构与段内字面**守卫
 *
 * spec: g0-confirmation-source-alignment，Task 14（Requirement 7.1 / 7.6 / 7.7）
 *
 * ─── 这份守卫补的是哪个洞 ────────────────────────────────────────────────────
 * `blockColumnConfigsG06.spec.ts`（35 例）只覆盖**区块列定义**，从不校验段标题/段号/
 * 点选项/录入位置 → Task 14 一度靠「列守卫全绿」被判完成，而实际整表段号串位：
 *   源外增强段「余额汇总与检查比例」占了源模板段号「二」
 *     → 「二、检查过程记录」被编成「三」
 *     → 「三、审计说明」+「四、审计结论」被挤成合并的「四、审计说明与结论」
 * 另有两处源模板录入位置完全缺失（`B7` 测试范围 5 点选项、`C15` 本期发生额抽样标准）。
 *
 * **教训（已写进 spec Notes）：区块列守卫全绿 ≠ 整表对齐。**
 *
 * ─── 裁决者链条（不连库、不读 xlsx）─────────────────────────────────────────
 *   源 xlsx ──openpyxl──▶ backend/tests/test_g0_source_template_facts.py
 *                          （`ALT_NUMBERED_SECTIONS` / `ALT_SCOPE_CELLS` /
 *                            `ALT_PREPARATION_NOTES` / `ALT_BLOCK_ANCHORS`）
 *                                  │ 交叉锁死
 *                                  ▼
 *                          g06SourceFidelity.ts（字面单一真源）
 *                                  │ 交叉锁死（源码级：组件必须消费它，不抄第二份中文）
 *                                  ▼
 *                          GtConfirmationAlternativeG06.vue
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  G06_BLOCK_HEADINGS,
  G06_EXTRA_SECTIONS,
  G06_HEADER_FIELDS,
  G06_OCCURRENCE_SAMPLING_OPTIONS,
  G06_OCCURRENCE_SAMPLING_SOURCE_TEXT,
  G06_PREPARATION_NOTES,
  G06_SECTIONS,
  G06_TEST_SCOPE_OPTIONS,
  G06_TEST_SCOPE_SOURCE_TEXT,
  G06_MASTER_LABELS,
  g06Section,
  parseG06ScopeSelections,
  serializeG06ScopeSelections,
} from '../g06SourceFidelity'
import {
  DEFAULT_ALTERNATIVE_MASTER_LABELS,
  resolveAlternativeMasterLabels,
} from '../../../confirmation/alternativeD05/alternativeMasterLabels'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
const SENTINELS = [
  join('backend', 'tests', 'test_g0_source_template_facts.py'),
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const BACKEND_SRC = readFileSync(
  join(REPO_ROOT, 'backend', 'tests', 'test_g0_source_template_facts.py'),
  'utf-8',
)
const ALT_DIR = join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
  'g0-confirmation',
  'alternativeG06',
)
const COMPONENT_SRC = readFileSync(join(ALT_DIR, 'GtConfirmationAlternativeG06.vue'), 'utf-8')

/** 去注释（块 + 行 + HTML）—— 组件注释里逐字写了旧段名，不剥必假红 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

const COMPONENT_CLEAN = stripComments(COMPONENT_SRC)

/**
 * 后端里的模块级字符串常量表（`NAME = "字面"`）。
 *
 * 🔴 后端元组的第二个元素**可能是常量引用而非字面量**（`("B7", ALT_TEST_SCOPE_TEXT)`）
 * → 只认引号的抽取器会静默返回 0 条（第一版就踩了这个）。故先建常量表再解引用。
 */
const BACKEND_STR_CONSTS: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(
    [...BACKEND_SRC.matchAll(/^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]*)"\s*$/gm)].map((m) => [m[1], m[2]]),
  ),
)

/** 从后端事实守卫抽 `(坐标, 文本)` 元组常量（值支持字面量或常量引用） */
function backendTuples(name: string): { coord: string; text: string }[] {
  const re = new RegExp(`${name}:\\s*tuple\\[tuple\\[str,\\s*str\\],\\s*\\.\\.\\.\\]\\s*=\\s*\\(([\\s\\S]*?)\\n\\)`)
  const m = BACKEND_SRC.match(re)
  if (!m) throw new Error(`未能在后端事实守卫里定位 ${name}（正则失效）`)
  const out: { coord: string; text: string }[] = []
  for (const mm of m[1].matchAll(/\("([A-Z]+\d+)",\s*(?:"([^"]*)"|([A-Z][A-Z0-9_]*))\)/g)) {
    const [, coord, literal, ident] = mm
    if (literal !== undefined) {
      out.push({ coord, text: literal })
      continue
    }
    const resolved = BACKEND_STR_CONSTS[ident]
    if (resolved === undefined) {
      throw new Error(`${name} 引用了未能解析的后端常量 ${ident}（抽取器需扩展）`)
    }
    out.push({ coord, text: resolved })
  }
  return out
}

/** 归一：源模板段标题带尾冒号（`三、审计说明：`），UI 不带 */
function normTitle(s: string): string {
  return s.replace(/[：:]\s*$/, '').trim()
}

// ════════════════════════════════════════════════════════════════════════════
describe('段号与段结构：源模板恰四个带序号的段，「二」是检查过程记录', () => {
  it('抽取非空自检：后端四个带序号段常量可解析', () => {
    const rows = backendTuples('ALT_NUMBERED_SECTIONS')
    expect(rows.length).toBeGreaterThan(0)
    expect(rows).toHaveLength(4)
  })

  it('真源四段（标题 + 锚点）与后端逐条一致，双侧无剩余', () => {
    const backend = backendTuples('ALT_NUMBERED_SECTIONS')
    expect(G06_SECTIONS).toHaveLength(backend.length)
    expect(G06_SECTIONS.map((s) => [s.anchor, normTitle(s.title)])).toEqual(
      backend.map((b) => [b.coord, normTitle(b.text)]),
    )
  })

  it('段号语义正确：一=样本选取 / 二=检查过程记录 / 三=审计说明 / 四=审计结论', () => {
    expect(g06Section('sampling').title).toBe('一、样本选取标准与规模')
    expect(g06Section('process').title).toBe('二、检查过程记录')
    expect(g06Section('audit_note').title).toBe('三、审计说明')
    expect(g06Section('conclusion').title).toBe('四、审计结论')
    expect(() => g06Section('nope')).toThrow(/未声明的段/)
  })

  it('源外增强段一律不带段号，且写明理由（防再次抢占源模板段号）', () => {
    expect(G06_EXTRA_SECTIONS.length).toBeGreaterThan(0)
    for (const s of G06_EXTRA_SECTIONS) {
      expect(s.title, `源外增强段 ${s.key} 不得带一/二/三/四段号`).not.toMatch(/^[一二三四五六七八九十]、/)
      expect(s.title).toContain('源外增强')
      expect(s.reason.trim().length, `${s.key} 的保留理由过短`).toBeGreaterThanOrEqual(30)
    }
  })

  it('组件段标题一律取自真源，不写死中文（改造前四处都是字面量）', () => {
    for (const key of ['sampling', 'process', 'audit_note', 'conclusion']) {
      expect(COMPONENT_CLEAN, `组件未消费 g06Section('${key}')`).toContain(`g06Section('${key}')`)
    }
    expect(COMPONENT_CLEAN).toContain('G06_EXTRA_SECTIONS[0].title')
  })

  it('反向自检：改造前的错误段名不得复活', () => {
    // 「二、余额汇总与检查比例」抢占段号 / 「三、检查过程记录」段号错 /
    // 「四、审计说明与结论」两段并一
    expect(COMPONENT_CLEAN).not.toContain('二、余额汇总')
    expect(COMPONENT_CLEAN).not.toContain('三、检查过程记录')
    expect(COMPONENT_CLEAN).not.toContain('审计说明与结论')
  })

  it('区块小标题与后端 `ALT_BLOCK_ANCHORS` 一致（1./2.（1）（2）/3.）', () => {
    const backend = new Map(backendTuples('ALT_BLOCK_ANCHORS').map((b) => [b.coord, b.text]))
    expect(backend.size).toBeGreaterThan(0)
    for (const [key, def] of Object.entries(G06_BLOCK_HEADINGS)) {
      expect(backend.get(def.anchor), `锚点 ${def.anchor}（${key}）不在后端清单里`).toBe(def.title)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('两组 5 点选项（源 B7 / C15）', () => {
  it('选项集合是源单元格原文的解析结果（防选项漂移）', () => {
    const parse = (t: string) => t.replace(/（）/g, '|').replace(/^\|+|\|+$/g, '').split('|')
    expect(parse(G06_TEST_SCOPE_SOURCE_TEXT)).toEqual([...G06_TEST_SCOPE_OPTIONS])
    expect(parse(G06_OCCURRENCE_SAMPLING_SOURCE_TEXT)).toEqual([...G06_OCCURRENCE_SAMPLING_OPTIONS])
  })

  it('源单元格原文与后端逐字一致（B7 / C15）', () => {
    const backend = new Map(backendTuples('ALT_SCOPE_CELLS').map((b) => [b.coord, b.text]))
    expect(backend.size).toBe(2)
    expect(backend.get('B7')).toBe(G06_TEST_SCOPE_SOURCE_TEXT)
    expect(backend.get('C15')).toBe(G06_OCCURRENCE_SAMPLING_SOURCE_TEXT)
  })

  it('🔴 两组只差最后一项：B7 末项「全部」/ C15 末项「其他」', () => {
    expect(G06_TEST_SCOPE_OPTIONS.slice(0, 4)).toEqual(G06_OCCURRENCE_SAMPLING_OPTIONS.slice(0, 4))
    expect(G06_TEST_SCOPE_OPTIONS[4]).toBe('全部')
    expect(G06_OCCURRENCE_SAMPLING_OPTIONS[4]).toBe('其他')
    expect(G06_TEST_SCOPE_OPTIONS).not.toEqual(G06_OCCURRENCE_SAMPLING_OPTIONS)
  })

  it('组件把两组都渲染成点选（`el-select multiple`），不再是自由 textarea', () => {
    expect(COMPONENT_CLEAN).toContain('G06_TEST_SCOPE_OPTIONS')
    expect(COMPONENT_CLEAN).toContain('G06_OCCURRENCE_SAMPLING_OPTIONS')
    expect(COMPONENT_CLEAN).toContain('onTestScopeChange')
    expect(COMPONENT_CLEAN).toContain('onOccurrenceScopeChange')
    // 「交互点选优先」铁律：这两处必须是多选 + allow-create（容纳存量自由文本）
    // 🔴 只数 `class="g06-scope-select"`（模板绑定），不要数裸类名 —— `<style>` 里的
    //    `.g06-scope-select` 选择器会让计数多 1（第一版就因此假红）。
    const scopeBindings = COMPONENT_CLEAN.match(/class="g06-scope-select"/g) ?? []
    expect(scopeBindings).toHaveLength(2)
    expect(COMPONENT_CLEAN).toContain('allow-create')
    const multiples = COMPONENT_CLEAN.match(/\bmultiple\b/g) ?? []
    expect(multiples.length).toBeGreaterThanOrEqual(2)
  })

  it('反向自检：`test_scope` 不得再绑成 textarea', () => {
    const m = COMPONENT_CLEAN.match(/test_scope[\s\S]{0,220}/)
    expect(m).toBeTruthy()
    expect(m![0]).not.toContain('type="textarea"')
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('多选值序列化：与旧自由文本同字段同形态（数据零丢失）', () => {
  it('parse / serialize 互为逆运算', () => {
    const values = ['大额', '关联方', '异常']
    expect(parseG06ScopeSelections(serializeG06ScopeSelections(values))).toEqual(values)
  })

  it('空值形态一致返回空（不产出 undefined/NaN 类脏值）', () => {
    for (const raw of [undefined, null, '', '   ']) {
      expect(parseG06ScopeSelections(raw)).toEqual([])
    }
    expect(serializeG06ScopeSelections([])).toBe('')
    expect(serializeG06ScopeSelections(undefined)).toBe('')
    expect(serializeG06ScopeSelections(['', '  '])).toBe('')
  })

  it('🔴 存量自由文本整段保留为一个自定义值（绝不丢弃）', () => {
    const legacy = '如应付账款借方发生额所有凭证共XX笔金额XX'
    expect(parseG06ScopeSelections(legacy)).toEqual([legacy])
    // 往返不改变内容
    expect(serializeG06ScopeSelections(parseG06ScopeSelections(legacy))).toBe(legacy)
  })

  it('容忍中英文逗号/分号分隔的存量值', () => {
    expect(parseG06ScopeSelections('大额,关联方，异常;全部；其他')).toEqual([
      '大额',
      '关联方',
      '异常',
      '全部',
      '其他',
    ])
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('表头字段与编制说明', () => {
  it('表头两字段与源 A5 / D5 一致，且组件已渲染', () => {
    expect(G06_HEADER_FIELDS.map((f) => [f.anchor, f.label])).toEqual([
      ['A5', '会计科目'],
      ['D5', '投资产品/名称'],
    ])
    expect(COMPONENT_CLEAN).toContain('会计科目')
    expect(COMPONENT_CLEAN).toContain('投资产品/名称')
  })

  it('编制说明三条要点与后端 B48:B50 逐字一致', () => {
    const backend = backendTuples('ALT_PREPARATION_NOTES')
    expect(backend).toHaveLength(3)
    expect(G06_PREPARATION_NOTES.map((n) => [n.anchor, n.text])).toEqual(
      backend.map((b) => [b.coord, b.text]),
    )
    // 正文在 B 列（只扫 A 列会整段漏掉）
    expect(G06_PREPARATION_NOTES.every((n) => n.anchor.startsWith('B'))).toBe(true)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('主表文案按循环（共享 AlternativeD05Master 的 D0-5 默认值零回归）', () => {
  it('默认文案与改造前逐字节相同 → 未传 labels 的六枢纽不受影响', () => {
    // 🔴 这组字面就是改造前 `AlternativeD05Master.vue` 里写死的值，改动即打红
    expect(DEFAULT_ALTERNATIVE_MASTER_LABELS).toEqual({
      addButton: '新增公司',
      importFromSummary: '从 D0-1 带入',
      entityColumn: '供应商/客户名称',
      entityPlaceholder: '单位名称',
      confirmIndexPlaceholder: 'D0-',
      ratioColumns: [
        { type: 'receipt', label: '收款比例' },
        { type: 'shipment', label: '出库比例' },
      ],
      emptyText: '暂无公司记录，请新增或从 D0-1 带入未回函公司',
    })
  })

  it('不传 / 传 null 都回落默认；部分覆盖只改声明项', () => {
    expect(resolveAlternativeMasterLabels(undefined)).toBe(DEFAULT_ALTERNATIVE_MASTER_LABELS)
    expect(resolveAlternativeMasterLabels(null)).toBe(DEFAULT_ALTERNATIVE_MASTER_LABELS)
    const partial = resolveAlternativeMasterLabels({ addButton: '新增X' })
    expect(partial.addButton).toBe('新增X')
    expect(partial.entityColumn).toBe(DEFAULT_ALTERNATIVE_MASTER_LABELS.entityColumn)
    expect(partial.ratioColumns).toBe(DEFAULT_ALTERNATIVE_MASTER_LABELS.ratioColumns)
  })

  it('🔴 G0 主表文案不得残留 D0-5 销售循环语义', () => {
    const merged = resolveAlternativeMasterLabels(G06_MASTER_LABELS)
    expect(merged.entityColumn).toBe('被投资单位名称')
    expect(merged.addButton).toBe('新增被投资单位')
    expect(merged.importFromSummary).toBe('从 G0-1 带入')
    expect(merged.confirmIndexPlaceholder).toBe('G0-')
    expect(merged.ratioColumns.map((c) => c.label)).toEqual(['股利检查比例', '持仓检查比例'])

    const joined = JSON.stringify(merged)
    for (const banned of ['供应商', '客户名称', 'D0-', '收款比例', '出库比例', '新增公司']) {
      expect(joined, `G0 主表文案仍含 D0-5 语义「${banned}」`).not.toContain(banned)
    }
  })

  it('比例列 type 仍是 receipt/shipment（master 的 getCheckRatio prop 签名不变）', () => {
    // G0 侧由 `getCheckRatioForMaster` 把 receipt→payment / shipment→inbound
    expect(G06_MASTER_LABELS.ratioColumns.map((c) => c.type)).toEqual(['receipt', 'shipment'])
    expect(COMPONENT_CLEAN).toContain('getCheckRatioForMaster')
    expect(COMPONENT_CLEAN).toMatch(/receipt'\s*\?\s*'payment'\s*:\s*'inbound'/)
  })

  it('组件确实把 labels 传给了主表（传不进去 = 静默失效）', () => {
    expect(COMPONENT_CLEAN).toContain(':labels="G06_MASTER_LABELS"')
    // prop 名必须是主表 defineProps 里真实存在的（动态抽取比对）
    const masterSrc = readFileSync(
      join(ALT_DIR, '..', '..', 'confirmation', 'alternativeD05', 'AlternativeD05Master.vue'),
      'utf-8',
    )
    expect(masterSrc).toMatch(/labels\?:\s*Partial<AlternativeMasterLabels>/)
  })

  it('🔴 主表行内编辑已接回写（改造前 update-field 无人监听 = 静默丢弃）', () => {
    expect(COMPONENT_CLEAN).toContain('@update-field="handleMasterUpdateField"')
    expect(COMPONENT_CLEAN).toContain('function handleMasterUpdateField')
    expect(COMPONENT_CLEAN).toContain('data.updateCompany(')
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('反向自检（防断言空转）', () => {
  it('stripComments 剥掉注释里的旧段名但保留模板字面', () => {
    const fixture = [
      '<!-- 改造前是「四、审计说明与结论」 -->',
      '/* 旧段号：三、检查过程记录 */',
      '// 二、余额汇总与检查比例',
      '<div>{{ g06Section(\'process\').title }}</div>',
    ].join('\n')
    const out = stripComments(fixture)
    expect(out).not.toContain('审计说明与结论')
    expect(out).not.toContain('三、检查过程记录')
    expect(out).not.toContain('二、余额汇总')
    expect(out).toContain("g06Section('process')")
    expect(stripComments('const u = "https://x.test/a"')).toContain('https://x.test/a')
  })

  it('两个源码文件确实被读到（非空 + 含锚点）', () => {
    expect(BACKEND_SRC).toContain('ALT_NUMBERED_SECTIONS')
    expect(COMPONENT_SRC.length).toBeGreaterThan(1000)
    expect(COMPONENT_CLEAN).toContain('g06SourceFidelity')
  })
})
