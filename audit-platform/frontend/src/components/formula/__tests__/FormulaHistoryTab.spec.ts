/**
 * FormulaHistoryTab 测试（需求 13.3，ADR-FHIC-10）
 *
 * 验证：
 * - 删除 specAReady 常量
 * - 只对 rollbackable=true 显示回滚按钮
 * - 回滚请求不带 target_formula
 * - 按状态码判成功
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC = resolve(__dirname, '..', 'FormulaHistoryTab.vue')

describe('FormulaHistoryTab — specAReady 已删除', () => {
  const src = readFileSync(SRC, 'utf-8')

  it('不再有 specAReady 引用', () => {
    expect(src).not.toContain('specAReady')
  })

  it('不再有 spec A 阶段3 提示的 el-alert', () => {
    // 原来有一段「公式变更哈希链（spec A 阶段3）尚未完成」的 el-alert
    expect(src).not.toContain('spec A 阶段3')
    expect(src).not.toContain('哈希链 formula.changed 留痕')
  })
})

describe('FormulaHistoryTab — rollbackable 门控', () => {
  const src = readFileSync(SRC, 'utf-8')

  it('HistoryEntry 接口含 rollbackable 字段', () => {
    expect(src).toMatch(/rollbackable\??\s*:\s*boolean/)
  })

  it('canRollback 按服务端 rollbackable 判定', () => {
    const m = src.match(/function canRollback[\s\S]*?\n}/)
    expect(m, '未找到 canRollback').toBeTruthy()
    expect(m![0]).toContain('rollbackable')
    // 不再检查 entry.action 或 entry.old_formula
    expect(m![0]).not.toContain("entry.action === 'update'")
    expect(m![0]).not.toContain('entry.old_formula')
  })

  it('回滚按钮仍受 canRollback 门控', () => {
    const template = src.match(/<template>([\s\S]*?)\n<\/template>/)?.[1] ?? ''
    expect(template).toMatch(/v-if="canRollback\(entry\)"/)
  })
})

describe('FormulaHistoryTab — 回滚请求体', () => {
  const src = readFileSync(SRC, 'utf-8')

  it('回滚请求不传 target_formula（ADR-FHIC-10）', () => {
    // api.post 调用内的请求体对象不应包含 target_formula 键
    // 找从 api.post 到下一个 }) 的整段
    const postIdx = src.indexOf("api.post(formulaAuditLog.rollback")
    expect(postIdx, '未找到 api.post 回滚调用').toBeGreaterThan(-1)
    const postSegment = src.substring(postIdx, postIdx + 300)
    expect(postSegment).not.toMatch(/\btarget_formula\b/)
    expect(postSegment).toContain('source_log_id')
  })

  it('回滚请求不使用 validateStatus: s < 600 模式', () => {
    const m = src.match(/async function onRollback[\s\S]*?\n}/)?.[0] ?? ''
    expect(m).not.toContain('validateStatus')
  })

  it('回滚失败按状态码 428/409 显示中文提示', () => {
    const m = src.match(/async function onRollback[\s\S]*?\n}/)?.[0] ?? ''
    expect(m).toContain('428')
    expect(m).toContain('409')
  })
})

describe('FormulaHistoryTab — 历史加载', () => {
  const src = readFileSync(SRC, 'utf-8')

  it('loadHistory 不使用 validateStatus: s < 600', () => {
    const m = src.match(/async function loadHistory[\s\S]*?\n}/)?.[0] ?? ''
    expect(m).not.toContain('validateStatus')
    expect(m).not.toContain('s < 600')
  })
})
