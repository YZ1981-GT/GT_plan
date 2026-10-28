/**
 * 批量创建自定义底稿回执 → 计数、明细与提示（spec procedure-chain-hardening-and-java-contracts R11.5）。
 *
 * 原先后端不看表头填充结果、前端只看 failed 计数 ⇒ 表头没填上也报「已创建 N 个」成功。
 * 跨语言：明细字段名直接读后端 `create_custom_workpaper_batch` 的返回体（改一侧另一侧必红）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { summarizeBatchCreate } from '../customWpBatchParse'

function backendRouter(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const p = path.join(dir, 'backend', 'app', 'routers', 'wp_template.py')
    if (fs.existsSync(p)) return fs.readFileSync(p, 'utf-8')
    dir = path.dirname(dir)
  }
  throw new Error('找不到 backend/app/routers/wp_template.py')
}

describe('summarizeBatchCreate', () => {
  it('全部创建且表头都填上：成功提示', () => {
    expect(summarizeBatchCreate({ created: 2, skipped: 1, failed: 0, failed_items: [], header_failures: [] }))
      .toEqual({
        counts: { created: 2, skipped: 1, failed: 0 },
        items: [],
        level: 'success',
        message: '已创建 2 个，跳过 1 个',
      })
  })

  it('表头没填上：警告，明细写明「已创建，表头未填上」与原因', () => {
    const s = summarizeBatchCreate({
      created: 2,
      failed: 0,
      header_failures: [{ wp_code: 'X2', reason: '打开底稿文件失败' }],
    })
    expect(s.level).toBe('warning')
    expect(s.message).toBe('已创建 2 个，1 个表头未填上（见下方明细）')
    expect(s.items).toEqual([{ wp_code: 'X2', reason: '已创建，表头未填上：打开底稿文件失败' }])
  })

  it('失败与表头没填上并存：两类都进明细，失败在前', () => {
    const s = summarizeBatchCreate({
      created: 1,
      failed: 1,
      failed_items: [{ wp_code: 'X1', reason: '编号已存在' }],
      header_failures: [{ wp_code: 'X3', reason: '保存底稿文件失败' }],
    })
    expect(s.message).toBe('已创建 1 个，1 个失败，1 个表头未填上（见下方明细）')
    expect(s.items.map((i) => i.wp_code)).toEqual(['X1', 'X3'])
    expect(summarizeBatchCreate(undefined).counts).toEqual({ created: 0, skipped: 0, failed: 0 })
  })

  it('接线：批量创建弹窗的计数、明细与提示都取自 summarizeBatchCreate', () => {
    const dialog = fs
      .readFileSync(path.join(__dirname, '..', 'GtCustomWpBatchDialog.vue'), 'utf-8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '')
    expect(dialog).toMatch(/const summary = summarizeBatchCreate\(res\)/)
    expect(dialog).toMatch(/result\.value = summary\.counts/)
    expect(dialog).toMatch(/failedItems\.value = summary\.items/)
    expect(dialog).toMatch(/ElMessage\[summary\.level\]\(summary\.message\)/)
  })

  it('跨语言：后端批量创建的返回体带 header_failures（{wp_code, reason}）', () => {
    const src = backendRouter()
    const body = src.split('async def create_custom_workpaper_batch(')[1] ?? ''
    expect(body).toMatch(/"header_failures":\s*header_failures/)
    expect(body).toMatch(/\{"wp_code":\s*c\["wp_code"\],\s*"reason":\s*c\["header_issue"\]\}/)
  })
})
