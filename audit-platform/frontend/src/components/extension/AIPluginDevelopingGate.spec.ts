import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const list = readFileSync(resolve(process.cwd(), 'src/components/extension/PluginList.vue'), 'utf-8')
const page = readFileSync(resolve(process.cwd(), 'src/views/extension/AIPluginManagement.vue'), 'utf-8')

describe('AI 插件开发中门禁', () => {
  it('预设 stub 的启用、执行和配置入口全部禁用', () => {
    expect(list).toContain(':disabled="isStub(row.plugin_id)"')
    expect(list).toContain('该插件正在开发中')
    expect(page).toContain('当前不保存生产配置')
    expect(page).toContain('不能启用、执行或保存生产配置')
  })

  it('八个预设插件逐项登记，不用模糊前缀放行', () => {
    const match = page.match(/const STUB_PLUGIN_IDS = \[([\s\S]*?)\]/)
    expect(match).not.toBeNull()
    const ids = match![1].match(/'[^']+'/g) ?? []
    expect(ids).toHaveLength(8)
  })
})
