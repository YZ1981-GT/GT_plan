import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = resolve(HERE, '../../../..')
const FILE = resolve(FRONTEND_ROOT, 'src/views/TrialBalance.vue')
const SOURCE = readFileSync(FILE, 'utf-8')
const { descriptor, errors } = parse(SOURCE, { filename: FILE })
const TEMPLATE = descriptor.template?.content ?? ''
const SCRIPT = descriptor.scriptSetup?.content ?? ''

function functionBody(source: string, name: string): string {
  const signature = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`)
  const found = signature.exec(source)
  if (!found) return ''
  const open = source.indexOf('{', found.index)
  let depth = 0
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1
    if (source[i] === '}') {
      depth -= 1
      if (depth === 0) return source.slice(found.index, i + 1)
    }
  }
  return ''
}

describe('TrialBalance TB 重分类自动持久化接线', () => {
  it('SFC 可解析且测试读取了真实模板与脚本', () => {
    expect(errors).toEqual([])
    expect(TEMPLATE.length).toBeGreaterThan(10_000)
    expect(SCRIPT.length).toBeGreaterThan(20_000)
  })

  it('借贷两格只允许普通可编辑行，并统一调用业务提交入口', () => {
    expect(TEMPLATE.match(/:editable="canEdit && !row\.is_total && !row\.is_category"/g)).toHaveLength(2)
    expect(TEMPLATE.match(/@change="onTbSummaryRclChange\(row, 'rcl_(?:dr|cr)'\)"/g)).toHaveLength(2)
    expect(TEMPLATE).not.toMatch(/v-model="row\.rcl_(?:dr|cr)"[^>]+@change="recalcTbSummaryAudited\(\)"/)
  })

  it('提交入口先挡无权与汇总行，再标记格、重算并排入保存', () => {
    const body = functionBody(SCRIPT, 'onTbSummaryRclChange')
    expect(body).toContain('!canEdit.value || row.is_total || row.is_category')
    expect(body).toContain('markManualRcl(row, field)')
    expect(body).toContain('recalcTbSummaryAudited()')
    expect(body).toContain('tbSummaryPersistence.queue()')
  })

  it('加载委托控制器合并并 prime 版本，显式保存只走同一 CAS 队列', () => {
    const merge = functionBody(SCRIPT, '_mergeSavedTbSummary')
    const save = functionBody(SCRIPT, 'saveTbSummary')
    expect(merge).toContain('await tbSummaryPersistence.hydrate(context)')
    expect(merge).toContain('recalcTbSummaryAudited()')
    expect(save).toContain('await tbSummaryPersistence.flush(true)')
    expect(save).toContain("ElMessage.success('试算平衡表已保存')")
    expect(save).not.toContain('api.put(')
    expect(save).not.toContain('validateStatus')
  })

  it('Ctrl+S 先提交格内编辑并等待同一显式保存，卸载时停止控制器', () => {
    const shortcut = functionBody(SCRIPT, 'onShortcutSave')
    const keydown = functionBody(SCRIPT, 'onKeydown')
    expect(keydown).toContain("e.key.toLowerCase() === 's'")
    expect(keydown).toContain('commitAllGridEdits()')
    expect(keydown).toContain('void onShortcutSave()')
    expect(shortcut).toContain('await saveTbSummary()')
    expect(SCRIPT).toContain('tbSummaryPersistence.dispose()')
  })

  it('刷新与路由切换先经保存/确认门，年度或项目变化后重载当前汇总表', () => {
    const load = functionBody(SCRIPT, 'loadTbSummary')
    const reload = functionBody(SCRIPT, 'reloadTrialBalanceContext')
    expect(load).toContain("if (!await tbSummaryNavigation.settle('刷新')) return")
    expect(load.indexOf('tbSummaryNavigation.settle')).toBeLessThan(load.indexOf('const loadContext'))
    expect(SCRIPT).toContain('useTbSummaryNavigationGuard(tbSummaryPersistence)')
    expect(reload).toContain("if (tbViewMode.value === 'summary') await loadTbSummary()")
  })

  it('工具栏显示等待、保存中和失败状态，不逐格弹成功消息', () => {
    expect(TEMPLATE).toContain('等待自动保存…')
    expect(TEMPLATE).toContain('自动保存中…')
    expect(TEMPLATE).toContain('{{ tbSummarySaveError }}')
    const commit = functionBody(SCRIPT, 'onTbSummaryRclChange')
    expect(commit).not.toContain('ElMessage.success')
  })
})
