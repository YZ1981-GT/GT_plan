/**
 * 附注编辑器「🔄 恢复模板结构」按当前表取模板（spec note-pull-header-formula-closure，批 6 浏览器实测发现）。
 *
 * 原先请求不带表信息、后端恒返回章节第一张表：在【测试】甲 五、5「组合计提项目：应收中央企业客户」上点恢复，表被换成
 * 「按账龄披露」的 3 列 12 行，2 分钟定时自动保存随即写库。现行：先确认，再带当前表的表名与序号请求（后端按它们找
 * 模板里的同一张表，找不到 404，见 backend/tests/test_note_template_structure.py）；恢复本身的列身份 / 行对应见
 * composables/__tests__/useNoteTableStructure.test.ts。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const editorSource = readFileSync(resolve(__dirname, '../DisclosureEditor.vue'), 'utf8')

function functionBody(source: string, signature: string): string {
  const start = source.indexOf(signature)
  expect(start, `找不到 ${signature}`).toBeGreaterThan(-1)
  return source.slice(start, source.indexOf('\n}\n', start))
}

describe('onRestoreTemplateStructure', () => {
  const body = functionBody(editorSource, 'async function onRestoreTemplateStructure()')

  it('带当前表的表名与序号请求模板结构', () => {
    expect(body).toContain('const { table, index } = structureEditState.value')
    expect(body).toMatch(/if \(tableName\) params\.table_name = tableName/)
    expect(body).toMatch(/if \(index != null\) params\.table_index = index/)
    expect(body).toMatch(/api\.get\(P\.disclosureNotes\.templateStructure\(projectId\.value, year\.value, section\), \{ params, _silent: true \} as any\)/)
  })

  it('模板里没有这张表（404）给出说明，不叠全局提示', () => {
    const catchAt = body.lastIndexOf('} catch (e: any) {')
    const handler = body.slice(catchAt)
    expect(handler).toMatch(/if \(e\?\.response\?\.status === 404\) \{\s+ElMessage\.warning\(`模板里没有/)
    expect(handler.indexOf('status === 404')).toBeLessThan(handler.indexOf("handleApiError(e, '恢复模板结构')"))
  })

  it('先二次确认再请求（恢复会去掉模板里没有的行，定时自动保存会写库）', () => {
    const confirmAt = body.indexOf('ElMessageBox.confirm(')
    expect(confirmAt).toBeGreaterThan(-1)
    expect(confirmAt).toBeLessThan(body.indexOf('api.get('))
    expect(body).toMatch(/\} catch \{ return \}/)
  })
})

describe('定时自动保存只存不打断（浏览器实测：填完一格，计时器保存后跳到下一章节 / 收起编辑态）', () => {
  it('计时器回调走 saveCurrentNote({ auto: true })，手工保存走 onSave → saveCurrentNote({ auto: false })', () => {
    const start = editorSource.indexOf('const autoSave = useWorkpaperAutoSave(')
    const timerCallback = editorSource.slice(start, editorSource.indexOf('}, 120_000', start))
    expect(timerCallback).toContain('await saveCurrentNote({ auto: true })')
    expect(timerCallback).not.toMatch(/\bonSave\(/)
    expect(editorSource).toContain('function onSave() { return saveCurrentNote({ auto: false }) }')
  })

  it('自动保存不退出编辑、不跳章；保存后清结构撤销记录', () => {
    const save = functionBody(editorSource, 'async function saveCurrentNote({ auto }: { auto: boolean })')
    expect(save).toContain('await _rawSave({ keepEditing: auto })')
    expect(save).toContain('if (!auto && autoAdvance.value) {')
    expect(save.indexOf('noteTableStructure.clearHistory()')).toBeGreaterThan(save.indexOf('await _rawSave('))
  })
})
