import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC = resolve(__dirname, '../../..')
const read = (path: string) => readFileSync(resolve(SRC, path), 'utf8')

describe('底稿提交复核唯一入口', () => {
  it('编辑器只调用专用 submit-review，并处理 can_submit=false', () => {
    const source = read('composables/useEditorSave.ts')
    expect(source).toContain('P_wp.submitReview(')
    expect(source).toContain('result?.can_submit === false')
    expect(source).not.toContain("status: 'pending_review'")
  })

  it('两个批量 UI 都调用 working-papers/batch-submit', () => {
    const list = read('views/WorkpaperList.vue')
    const panel = read('components/workpaper/BatchOperationsPanel.vue')
    expect(list).toContain('/working-papers/batch-submit')
    expect(panel).toContain('/working-papers/batch-submit')
    expect(panel).not.toContain('/workpapers/batch-submit')
  })
})
