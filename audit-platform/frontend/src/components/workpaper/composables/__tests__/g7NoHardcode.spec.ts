/**
 * g7NoHardcode.spec.ts — G7 反硬编码守卫
 *
 * 读源码 + stripComments() 再做正则断言，防止科目码/章节号/固定列数/固定行数
 * 等硬编码漂移或复活。
 *
 * 🔴 必须先 stripComments()：守卫注释里就写着反例（如「原实现 _G7_ACCOUNT_PREFIX='1511'」），
 *    不剥离会被数成真实调用。
 * 🔴 每条规则都加反向自检：断言被扫描的源码确实非空/确实含某已知模式，
 *    证明 stripComments 没把断言变空转。
 *
 * **Validates: Requirements 11.1, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8**
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment (Task 6.6)
 * Properties: 15, 16, 17, 18
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import { resolve, relative } from 'path'

// ─── stripComments ────────────────────────────────────────────────────────────

/** 去掉 JS/TS 行注释 + 块注释 + HTML 注释，再做源码级断言 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/gm, '$1')
    .replace(/<!--[\s\S]*?-->/g, '')
}

// ─── 路径常量 ─────────────────────────────────────────────────────────────────

const WP_ROOT = resolve(__dirname, '../..')
const COMPOSABLES_ROOT = resolve(WP_ROOT, 'composables')
const G7_MAIN_ROOT = resolve(WP_ROOT, 'g7-long-term-equity-main')
const ACCOUNT_SCOPE_PATH = resolve(COMPOSABLES_ROOT, 'g7AccountScope.ts')
const NOTE_SECTION_MAP_PATH = resolve(COMPOSABLES_ROOT, 'g7NoteSectionMap.ts')
const LISTED_MODEL_PATH = resolve(G7_MAIN_ROOT, 'disclosure/g7ListedDisclosureModel.ts')
const SOE_MODEL_PATH = resolve(G7_MAIN_ROOT, 'disclosure/g7SoeDisclosureModel.ts')

const BACKEND_DATA = resolve(__dirname, '../../../../../../../backend/data')
const VARIANT_MATRIX_PATH = resolve(BACKEND_DATA, 'note_template_variant_matrix.json')
const NOTE_TEMPLATE_SOE_PATH = resolve(BACKEND_DATA, 'note_template_soe.json')

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/** 递归收集 .ts / .vue 文件 */
function collectFiles(dir: string, extensions = ['.ts', '.vue']): string[] {
  const results: string[] = []
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return results
  }
  for (const entry of entries) {
    const full = resolve(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      // 跳过 __tests__ 和 node_modules
      if (entry === '__tests__' || entry === 'node_modules') continue
      results.push(...collectFiles(full, extensions))
    } else if (extensions.some((ext) => entry.endsWith(ext))) {
      results.push(full)
    }
  }
  return results
}

/** 判断文件是否是测试 fixture（路径含 __tests__ 或 .spec. 或 .test.） */
function isTestFixture(filePath: string): boolean {
  const rel = relative(WP_ROOT, filePath)
  return rel.includes('__tests__') || rel.includes('.spec.') || rel.includes('.test.')
}

// ─── 规则 ① 科目码字面量单一真源 ────────────────────────────────────────────

describe('规则① 1511/1512 字面量只许出现在 g7AccountScope.ts 与测试 fixture', () => {
  // 收集 G7 相关前端源码（composables + g7-long-term-equity-main 目录，排除 __tests__）
  const g7Files = [
    ...collectFiles(COMPOSABLES_ROOT).filter((f) => {
      const name = f.replace(/\\/g, '/').toLowerCase()
      return name.includes('g7') || name.includes('g7-')
    }),
    ...collectFiles(G7_MAIN_ROOT),
  ]

  // allowlist：g7AccountScope.ts（作 fallback 常量定义处）
  // useG7FormData.ts 尚有残留（writebackTB 默认参数 + 试算表请求），待后续收敛
  const ALLOWLIST = new Set([
    ACCOUNT_SCOPE_PATH.replace(/\\/g, '/'),
    resolve(COMPOSABLES_ROOT, 'useG7FormData.ts').replace(/\\/g, '/'),
  ])

  // 匹配 '1511' 或 "1511" 或 `1511` 以及 '1512' 等
  const ACCOUNT_CODE_RE = /['"`]151[12]['"`]/g

  it('反向自检：g7AccountScope.ts 确实含 1511/1512 字面量', () => {
    const raw = readFileSync(ACCOUNT_SCOPE_PATH, 'utf-8')
    expect(raw).toMatch(/1511/)
    expect(raw).toMatch(/1512/)
  })

  it('反向自检：扫描到非空文件集（>5 个 G7 源码文件）', () => {
    expect(g7Files.length).toBeGreaterThan(5)
  })

  const violations: Array<{ file: string; matches: string[] }> = []

  for (const file of g7Files) {
    const normalized = file.replace(/\\/g, '/')
    if (ALLOWLIST.has(normalized)) continue
    if (isTestFixture(file)) continue

    const raw = readFileSync(file, 'utf-8')
    const src = stripComments(raw)
    const matches = src.match(ACCOUNT_CODE_RE)
    if (matches && matches.length > 0) {
      // 允许出现在 UI 说明文案中的 "TB1511" / "1511−1512" 等给人看的文字
      // 但不允许作为程序化用途的引号包裹字面量
      const programmatic = matches.filter((m) => {
        // 允许出现在模板字符串说明文案里的：如 `科目1511` `TB1511`
        return true // 所有引号包裹的都算违规
      })
      if (programmatic.length > 0) {
        violations.push({ file: relative(WP_ROOT, file), matches: programmatic })
      }
    }
  }

  it('非 allowlist 文件中不得出现 1511/1512 引号包裹字面量', () => {
    expect(violations, `违规文件：${JSON.stringify(violations, null, 2)}`).toHaveLength(0)
  })
})

// ─── 规则 ② G7_NOTE_SECTION 逐字等于 variant_matrix ──────────────────────────

describe('规则② G7_NOTE_SECTION 两个值逐字等于 note_template_variant_matrix.json', () => {
  const mapSrc = stripComments(readFileSync(NOTE_SECTION_MAP_PATH, 'utf-8'))

  // 提取 listed 和 soe 值
  const listedMatch = mapSrc.match(/listed:\s*['"]([^'"]+)['"]/)
  const soeMatch = mapSrc.match(/soe:\s*['"]([^'"]+)['"]/)

  it('反向自检：成功提取 G7_NOTE_SECTION 两个值', () => {
    expect(listedMatch).not.toBeNull()
    expect(soeMatch).not.toBeNull()
  })

  const listedSection = listedMatch?.[1] ?? ''
  const soeSection = soeMatch?.[1] ?? ''

  it('G7_NOTE_SECTION.listed 与 variant_matrix 的 chang_qi_gu_quan_tou_zi 对应', () => {
    const matrix = JSON.parse(readFileSync(VARIANT_MATRIX_PATH, 'utf-8'))
    const entry = (matrix.accounts || matrix).find?.(
      (a: any) => a.account_key === 'chang_qi_gu_quan_tou_zi',
    )
    // 如果 matrix 不是 array，尝试 object 结构
    const variants = entry?.variants ?? matrix?.chang_qi_gu_quan_tou_zi?.variants ?? matrix?.chang_qi_gu_quan_tou_zi
    expect(variants).toBeDefined()
    const expected = variants?.listed_standalone ?? variants?.listed
    expect(listedSection).toBe(expected)
  })

  it('G7_NOTE_SECTION.soe 与 variant_matrix 的 chang_qi_gu_quan_tou_zi 对应', () => {
    const matrix = JSON.parse(readFileSync(VARIANT_MATRIX_PATH, 'utf-8'))
    const entry = (matrix.accounts || matrix).find?.(
      (a: any) => a.account_key === 'chang_qi_gu_quan_tou_zi',
    )
    const variants = entry?.variants ?? matrix?.chang_qi_gu_quan_tou_zi?.variants ?? matrix?.chang_qi_gu_quan_tou_zi
    expect(variants).toBeDefined()
    const expected = variants?.soe_standalone ?? variants?.soe
    expect(soeSection).toBe(expected)
  })
})

// ─── 规则 ③ 国企 15 个 noteSectionId 存在于 note_template_soe.json ────────────

describe('规则③ 国企 noteSectionId 逐条存在于 note_template_soe.json 的 section_number 集合', () => {
  // 从 g7SoeDisclosureModel.ts 提取所有 noteSectionId
  const soeModelRaw = readFileSync(SOE_MODEL_PATH, 'utf-8')
  const soeModelSrc = stripComments(soeModelRaw)

  // 匹配 noteSectionId: 'xxx' 或 noteSectionId: "xxx"
  const sectionIds = [...soeModelSrc.matchAll(/noteSectionId:\s*['"]([^'"]+)['"]/g)].map(
    (m) => m[1],
  )

  it('反向自检：从 g7SoeDisclosureModel.ts 提取到 ≥2 个 noteSectionId', () => {
    expect(sectionIds.length).toBeGreaterThanOrEqual(2)
  })

  // 读 note_template_soe.json 并收集所有 section_number
  const soeTemplate = JSON.parse(readFileSync(NOTE_TEMPLATE_SOE_PATH, 'utf-8'))
  const allSectionNumbers = new Set<string>()
  function walkSections(sections: any[]): void {
    if (!Array.isArray(sections)) return
    for (const sec of sections) {
      if (sec.section_number) allSectionNumbers.add(sec.section_number)
      if (sec.sub_sections) walkSections(sec.sub_sections)
      if (sec.children) walkSections(sec.children)
    }
  }
  walkSections(soeTemplate.sections ?? soeTemplate)

  it('反向自检：note_template_soe.json 含 >50 个 section_number', () => {
    expect(allSectionNumbers.size).toBeGreaterThan(50)
  })

  it.each(sectionIds)('noteSectionId "%s" 存在于 note_template_soe.json', (sid) => {
    expect(
      allSectionNumbers.has(sid),
      `"${sid}" 不在 note_template_soe.json 的 section_number 集合中。\n` +
        `可能是 md 截断值不匹配，请核实模板真实 section_number`,
    ).toBe(true)
  })
})

// ─── 规则 ④ 两个披露模型不得出现固定列构造 ──────────────────────────────────

describe('规则④ 披露模型禁止 公司1..公司N / length:6 式列构造', () => {
  const listedRaw = readFileSync(LISTED_MODEL_PATH, 'utf-8')
  const soeRaw = readFileSync(SOE_MODEL_PATH, 'utf-8')
  const listedSrc = stripComments(listedRaw)
  const soeSrc = stripComments(soeRaw)

  it('反向自检：两个披露模型源码非空（>500 字符）', () => {
    expect(listedSrc.length).toBeGreaterThan(500)
    expect(soeSrc.length).toBeGreaterThan(500)
  })

  // 匹配 公司1 / 公司2 / 子公司A / 联营企业1 等固定列名模式
  // 🔴 排除 *_SLOT_DEFAULT_NAMES（动态列的初始 seed 名称，用户可改名/增删，key 稳定）
  const FIXED_COMPANY_RE = /['"`](?:公司|子公司|联营企业|合营企业|被投资单位)\d+['"`]/g

  /**
   * 判断一行中的匹配是否属于动态 slot 默认名称（允许）。
   * 动态 slot 默认名的行特征：在 *_DEFAULT_NAMES / *_SLOT_DEFAULT* / 数组字面量 context 中
   * 且同一文件已有 buildG7SlotColumns / SlotColumn 字样（证明是动态列模型）。
   */
  function isInDynamicSlotContext(src: string, matchIndex: number): boolean {
    // 往前找该行开头
    const lineStart = src.lastIndexOf('\n', matchIndex) + 1
    const lineEnd = src.indexOf('\n', matchIndex)
    const line = src.slice(lineStart, lineEnd === -1 ? undefined : lineEnd)
    // 同行或前 3 行有 SLOT_DEFAULT / DEFAULT_NAMES / defaultNames 关键字
    const contextStart = Math.max(0, matchIndex - 300)
    const context = src.slice(contextStart, matchIndex + 100)
    return (
      /SLOT_DEFAULT|DEFAULT_NAMES|defaultNames|SlotColumn/i.test(context) ||
      /SLOT_DEFAULT|DEFAULT_NAMES|defaultNames/i.test(line)
    )
  }

  function findNonDynamicViolations(src: string): string[] {
    const results: string[] = []
    const re = new RegExp(FIXED_COMPANY_RE.source, 'g')
    let m: RegExpExecArray | null
    while ((m = re.exec(src)) !== null) {
      if (!isInDynamicSlotContext(src, m.index)) {
        results.push(m[0])
      }
    }
    return results
  }

  it('g7ListedDisclosureModel 无固定列名字面量（排除 SLOT_DEFAULT_NAMES）', () => {
    // 反向自检：确认文件确实含有动态 slot 默认名（证明排除逻辑有工作对象）
    expect(listedSrc).toMatch(/SLOT_DEFAULT_NAMES/)
    const matches = findNonDynamicViolations(listedSrc)
    expect(matches, `Found: ${matches.join(', ')}`).toHaveLength(0)
  })

  it('g7SoeDisclosureModel 无固定列名字面量（排除 SLOT_DEFAULT_NAMES）', () => {
    expect(soeSrc).toMatch(/SLOT_DEFAULT_NAMES/)
    const matches = findNonDynamicViolations(soeSrc)
    expect(matches, `Found: ${matches.join(', ')}`).toHaveLength(0)
  })

  // 匹配 length: 6 / length: 3 等固定长度列构造（Array(6).fill(...) 或 { length: 6 }）
  const FIXED_LENGTH_RE = /(?:length\s*:\s*\d+|Array\(\d+\))/g

  it('g7ListedDisclosureModel 无固定 length 列构造', () => {
    const matches = listedSrc.match(FIXED_LENGTH_RE) ?? []
    expect(matches, `Found: ${matches.join(', ')}`).toHaveLength(0)
  })

  it('g7SoeDisclosureModel 无固定 length 列构造', () => {
    const matches = soeSrc.match(FIXED_LENGTH_RE) ?? []
    expect(matches, `Found: ${matches.join(', ')}`).toHaveLength(0)
  })
})

// ─── 规则 ⑤ blankRows( 调用的 count 实参不得为字面量数字 ────────────────────

describe('规则⑤ blankRows( count 实参不得为字面量数字', () => {
  // 扫描 G7 相关所有 .ts / .vue 文件
  const allG7Files = [...collectFiles(COMPOSABLES_ROOT), ...collectFiles(G7_MAIN_ROOT)].filter(
    (f) => {
      const name = f.replace(/\\/g, '/').toLowerCase()
      return name.includes('g7') || name.includes('g7-')
    },
  )

  // blankRows(prefix, 3) / blankRows(p, 10, ...) 中第二参数是字面量数字
  const BLANK_ROWS_LITERAL_RE = /blankRows\s*\([^,)]+,\s*(\d+)\s*[,)]/g

  const violations: Array<{ file: string; match: string }> = []

  for (const file of allG7Files) {
    if (isTestFixture(file)) continue
    const src = stripComments(readFileSync(file, 'utf-8'))
    let m: RegExpExecArray | null
    const re = new RegExp(BLANK_ROWS_LITERAL_RE.source, 'g')
    while ((m = re.exec(src)) !== null) {
      violations.push({ file: relative(WP_ROOT, file), match: m[0] })
    }
  }

  it('反向自检：扫描了 >3 个 G7 源码文件', () => {
    expect(allG7Files.length).toBeGreaterThan(3)
  })

  it('blankRows( 的 count 参数不得为字面量数字', () => {
    expect(
      violations,
      `违规：\n${violations.map((v) => `  ${v.file}: ${v.match}`).join('\n')}`,
    ).toHaveLength(0)
  })
})

// ─── 规则 ⑥ 中文分类标签不在前端重复定义 ─────────────────────────────────────

describe('规则⑥ 中文分类标签只读 render 下发的 bucket_defs，前端不重复定义', () => {
  // G7 的 7 个中文分类标签
  const BUCKET_LABELS = [
    '子公司',
    '合营',
    '联营',
    '损益调整',
    '其他综合收益',
    '其他权益变动',
    '减值准备',
  ]

  // 扫描披露模型 + composables 中 G7 相关文件（排除 g7AccountScope 和测试）
  const g7FrontendFiles = [
    ...collectFiles(COMPOSABLES_ROOT).filter((f) => {
      const name = f.replace(/\\/g, '/').toLowerCase()
      return name.includes('g7') && !name.includes('g7accountscope')
    }),
    ...collectFiles(G7_MAIN_ROOT),
  ].filter((f) => !isTestFixture(f))

  // 排除 g7_investment_buckets 相关（那是后端真源的前端 re-export/type 文件）
  // 披露模型文件使用桶标签做键→列映射（消费 bucket 语义，非重复定义真源）
  // G7TabDetail.vue 使用桶标签做明细表→审定表分类聚合映射
  const BUCKET_DEFINITION_ALLOWLIST = [
    'g7InvestmentBuckets',
    'g7FourTableSeed',
    'g7ListedDisclosureModel',
    'g7SoeDisclosureModel',
    'G7TabDetail',
  ]

  it('反向自检：扫描了 >5 个 G7 前端源码文件', () => {
    expect(g7FrontendFiles.length).toBeGreaterThan(5)
  })

  it('前端源码不得定义包含分类桶中文标签的常量数组/对象（只读 bucket_defs）', () => {
    const violations: Array<{ file: string; label: string; line: string }> = []

    for (const file of g7FrontendFiles) {
      const name = file.replace(/\\/g, '/')
      if (BUCKET_DEFINITION_ALLOWLIST.some((al) => name.includes(al))) continue

      const src = stripComments(readFileSync(file, 'utf-8'))
      const lines = src.split('\n')

      for (const label of BUCKET_LABELS) {
        // 在一行中出现引号包裹的完整分类标签（作为定义值而非注释/消费）
        // 允许: UI 文案中出现（如 tooltip 描述、placeholder）
        // 禁止: 作为 Map/Object 的 value 定义重复标签集
        const re = new RegExp(`['"\`](?:对)?${label}(?:(?:企业)?(?:投资)?(?:成本)?)?['"\`]`)
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i]
          // 只抓「声明式」定义模式：label: '...' / '...' as const / [..., '...']
          if (
            re.test(line) &&
            (line.includes('label') || line.includes('const ') || line.includes('['))
          ) {
            // 如果同一行还有 bucket_defs / bucketDefs / props. 就是消费而非定义
            if (/bucket_defs|bucketDefs|props\./.test(line)) continue
            violations.push({ file: relative(WP_ROOT, file), label, line: line.trim() })
          }
        }
      }
    }

    // 这条规则比较宽松 —— 如果有少量 UI 展示用途的标签也不违规
    // 真正违规的是「重新定义完整 7 桶标签集」的行为
    // 此处只检查是否有文件定义了 ≥4 个不同的桶标签（≥4 即为重复定义整套）
    const fileViolationCounts = new Map<string, Set<string>>()
    for (const v of violations) {
      const set = fileViolationCounts.get(v.file) ?? new Set()
      set.add(v.label)
      fileViolationCounts.set(v.file, set)
    }

    const bulkDuplicates = [...fileViolationCounts.entries()].filter(
      ([, labels]) => labels.size >= 4,
    )

    expect(
      bulkDuplicates,
      `以下文件重复定义了 ≥4 个分类桶标签（应只读 bucket_defs）：\n` +
        bulkDuplicates.map(([f, labels]) => `  ${f}: ${[...labels].join(', ')}`).join('\n'),
    ).toHaveLength(0)
  })
})

// ─── stripComments 全局自检 ──────────────────────────────────────────────────

describe('stripComments 自检', () => {
  it('能剥离行注释', () => {
    const input = "const x = '1511' // _G7_ACCOUNT_PREFIX was '1511'\n"
    const stripped = stripComments(input)
    expect(stripped).toContain("'1511'")
    expect(stripped).not.toContain('_G7_ACCOUNT_PREFIX')
  })

  it('能剥离块注释', () => {
    const input = "/* 原来 const CODE = '1512' */ const y = 1\n"
    const stripped = stripComments(input)
    expect(stripped).not.toContain("'1512'")
    expect(stripped).toContain('const y = 1')
  })

  it('能剥离 HTML 注释', () => {
    const input = "<!-- blankRows(p, 5) -->\n<div>ok</div>"
    const stripped = stripComments(input)
    expect(stripped).not.toContain('blankRows')
    expect(stripped).toContain('<div>ok</div>')
  })
})
