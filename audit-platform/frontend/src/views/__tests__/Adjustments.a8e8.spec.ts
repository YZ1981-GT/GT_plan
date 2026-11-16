import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(process.cwd(), 'src')
const read = (relative: string) => readFileSync(resolve(root, relative), 'utf8')

const page = () => read('views/Adjustments.vue')
const table = () => read('components/adjustment/AdjustmentHallTable.vue')

function pageContracts(source: string) {
  return {
    contextEpoch: source.includes('const contextEpoch = ref(0)')
      && source.includes('resourceContextKey')
      && source.includes('generation !== contextEpoch.value'),
    resourceError: source.includes('resourceFailures.length')
      && source.includes('lastSuccessAt')
      && source.includes('retryResource(item.key)'),
    serverPaging: /page_size:\s*adjPageSize/.test(source)
      && source.includes('focus_entry_group_id: parsedRouteTarget.value.focus'),
    deepLink: source.includes('parseAdjustmentRouteTarget')
      && source.includes('applyRouteTargets')
      && source.includes('focusEntry(target.focus'),
    responsiveFocus: source.includes('gt-adj-tabs-row')
      && source.includes('flex-wrap')
      && source.includes('gt-adj-paste-zone:focus-visible'),
  }
}

describe('调整大厅 A8 / E8 运行契约', () => {
  it('保留上下文代际、错误重试、服务端分页和深链入口', () => {
    expect(Object.values(pageContracts(page()))).toEqual([true, true, true, true, true])
  })

  it('反向变异自检：分页和代际门被删时判据会变红', () => {
    const source = page()
    const withoutPaging = source.replace(/page_size:\s*adjPageSize/, 'page_size: 10000')
    const withoutEpoch = source.replace(/generation !== contextEpoch\.value/g, 'false')
    expect(pageContracts(withoutPaging).serverPaging).toBe(false)
    expect(pageContracts(withoutEpoch).contextEpoch).toBe(false)
  })

  it('窄屏/键盘契约：可点击来源和协作状态使用原生按钮并保留焦点样式', () => {
    const source = table()
    expect(source).toContain('class="gt-adj-inline-action gt-adj-inline-action--success"')
    expect(source).toContain('class="gt-adj-inline-action gt-adj-inline-action--primary"')
    expect(source).toContain('aria-label="查看进行中的协作补充"')
    expect(source).toContain('.gt-adj-inline-action:focus-visible')
    expect(source).not.toMatch(/<el-tag[^>]*@click/)
  })

  it('窄屏布局契约：筛选行、状态行、批量栏和明细脚注允许换行', () => {
    const source = table()
    const pageSource = page()
    expect(pageSource).toContain('.gt-adj-tabs-row')
    expect(pageSource).toContain('.gt-adj-status-row')
    expect(pageSource).toContain('.gt-adj-batch-actions')
    expect(source).toContain('.gt-adj-status-cell { display: flex; flex-wrap: wrap;')
    expect(source).toContain('.gt-adj-expand-footer { display: flex; flex-wrap: wrap;')
  })
})
