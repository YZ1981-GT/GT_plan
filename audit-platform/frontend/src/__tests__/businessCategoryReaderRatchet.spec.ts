/**
 * 前端直接读 `business_category` 的位置只许减少（spec trim-generation-plan-followup-optimizations R4.5）。
 *
 * 项目分类 / 场景的唯一解释在后端 `project_classification`（随项目详情、向导基本信息、D4 project_context 下发），
 * 前端判定读它的 `tags` / `category_group`（见 `@/types/projectClassification`、`@/utils/ipoProjectUtils`）。
 * 迁移期仍直接读分类列的旧读者（展示、首字母 / 子串等私有判断）冻结在基线里：新增读者或某文件读得更多即打红；
 * 读者减少须同步下调基线（不留虚高额度）。计数口径见 `_helpers/businessCategoryReaders.ts`。
 */
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { FRONTEND_SRC } from './_helpers/frontendSourceScan'
import { countFileReaders, countScriptReaders, scanBusinessCategoryReaders } from './_helpers/businessCategoryReaders'

const BASELINE = JSON.parse(
  readFileSync(resolve(__dirname, 'businessCategoryReaderRatchet.baseline.json'), 'utf-8'),
).readers as Record<string, number>

describe('business_category 直接读者棘轮（R4.5）', () => {
  it('只许减少：不新增读者、读者减少即下调基线', () => {
    const current = scanBusinessCategoryReaders()
    const grown = Object.entries(current)
      .filter(([file, n]) => n > (BASELINE[file] ?? 0))
      .map(([file, n]) => `${file} ${BASELINE[file] ?? 0}→${n}`)
    const shrunk = Object.entries(BASELINE)
      .filter(([file, n]) => (current[file] ?? 0) < n)
      .map(([file, n]) => `${file} ${n}→${current[file] ?? 0}`)
    expect(
      grown,
      `新增 / 增多了直接读 business_category 的代码（应读后端 project_classification）：\n${JSON.stringify(current, null, 2)}`,
    ).toEqual([])
    expect(shrunk, `直接读者减少了，请把基线同步下调：\n${JSON.stringify(current, null, 2)}`).toEqual([])
  })

  it('基线是现状快照：文件都存在、非空（空基线 = 扫描口径失效或已清零，应改成禁止任何直接读者）', () => {
    expect(Object.keys(BASELINE).length).toBeGreaterThan(0)
    const missing = Object.keys(BASELINE).filter((file) => !existsSync(resolve(FRONTEND_SRC, file)))
    expect(missing).toEqual([])
  })

  it('反向自检：读属性 / 下标 / 字符串 / 模板算，注释 / 类型字段 / 对象键 / 赋值不算', () => {
    const script = [
      '/** 说明里的 business_category 不算 */',
      'interface P { business_category: string | null }',
      'type K = "business_category"',
      'function f(p: P, row: Record<string, string>) {',
      '  // 注释里的 business_category 不算',
      '  const a = p.business_category',
      '  p.business_category = "C"',
      '  row["business_category"] = "A"',
      '  const b = row["business_category"]',
      '  const payload = { business_category: a, "business_category": b }',
      '  const prefix = (p.business_category || "").charAt(0)',
      '  return `${prefix} business_category ${a}`',
      '}',
    ].join('\n')
    // 读：p.business_category ×2、row["business_category"] 读取 ×1、模板字面量 ×1
    expect(countScriptReaders(script)).toBe(4)

    const vue = [
      '<template>',
      '  <!-- 模板注释里的 business_category 不算 -->',
      '  <span>{{ project.business_category }}</span>',
      '</template>',
      `<script setup lang="ts">\n${script}\n</script>`,
      '<style scoped>.business_category { color: red }</style>',
    ].join('\n')
    expect(countFileReaders('X.vue', vue)).toBe(5)
    expect(countFileReaders('x.ts', '// business_category\nexport const n = 1\n')).toBe(0)
  })
})
