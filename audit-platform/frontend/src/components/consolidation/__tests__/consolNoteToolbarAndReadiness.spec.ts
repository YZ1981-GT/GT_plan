/**
 * 批 5：附注工具栏四组分派 + ConsolReadinessBar 挂载守卫。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '../../..')
const read = (relative: string) => readFileSync(resolve(root, relative), 'utf8')

describe('ConsolNoteTab 工具栏四组 + 主按钮分派', () => {
  const note = read('components/consolidation/ConsolNoteTab.vue')

  it('工具栏按四组分隔（分组 1 编辑查看 / 分组 2 计算更新 / 分组 3 复核 / 分组 4 数据准备）', () => {
    // 四组之间有分隔符
    const sepCount = (note.match(/class="gt-note-sep"/g) || []).length
    expect(sepCount).toBeGreaterThanOrEqual(3)
    // 分组注释
    expect(note).toContain('分组 1：编辑与查看')
    expect(note).toContain('分组 2：计算更新')
    expect(note).toContain('分组 3：复核')
    expect(note).toContain('分组 4：数据准备')
  })

  it('主按钮按 source_mode 分派：formula 直接填入、detail_mapping/subtree_aggregate 直接汇总、mixed/空 下拉', () => {
    expect(note).toContain('noteSourceMode')
    // formula 模式显示「ƒx 按公式填入」
    expect(note).toContain("v-else-if=\"noteSourceMode === 'formula'\"")
    // detail_mapping/subtree_aggregate 显示「🔄 重新汇总」
    expect(note).toContain('v-else content="重新汇总')
    // mixed/空 显示下拉
    expect(note).toContain("v-if=\"noteSourceMode === 'mixed' || !noteSourceMode\"")
    expect(note).toContain('consol-note-update-main')
  })

  it('noteSourceMode computed 优先读 V243 投影字段，兼容旧 _last_write_source', () => {
    expect(note).toContain('record.source_mode || record._source_mode')
    expect(note).toContain("source === 'detail_mapping' || source === 'subtree_aggregate' || source === 'formula'")
  })
})

describe('ConsolidationIndex ReadinessBar 挂载', () => {
  const index = read('views/ConsolidationIndex.vue')

  it('ReadinessBar 组件已挂载并绑定 projectId/year', () => {
    expect(index).toContain('ConsolReadinessBar')
    expect(index).toContain('consolReadinessBarRef')
    expect(index).toContain(':project-id="projectId"')
    expect(index).toContain(':year="effectiveConsolYear()"')
    expect(index).toContain('consol-readiness-bar')
  })

  it('readiness API 路径已注册', () => {
    const paths = read('services/apiPaths/report.ts')
    expect(paths).toContain('/api/consolidation/readiness/')
    expect(paths).toContain('readiness:')
  })
})
