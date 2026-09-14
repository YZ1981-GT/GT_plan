/**
 * 行级合并 fail-closed 提示：必须说出**为什么**，且原因字段必须真被消费。
 *
 * 后端 `row_scope_unresolved_reasons` 是本轮 additive 新增的（Requirement 11.3）。
 * 🔴 additive 字段最典型的失败形态是「加了没人用」—— 后端多返一个键、前端照旧只
 * 显示表名，判据全绿而审计师还是不知道该找谁改什么。故本文件除了测纯函数，还要
 * 钉死三个既有消费方**真的读了那个键**。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
 *       Requirements 11.3 / Property 40
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { rowScopeFailureMessage } from '../shared/rowScopeFailure'

const ROOT = resolve(__dirname, '../../../../..')

/** 三个消费方（相对 `src/`）。新增消费方也要进这份清单。 */
const CONSUMERS = [
  'src/components/workpaper/e1/E1TabDisclosure.vue',
  'src/components/workpaper/d1/D1TabDisclosure.vue',
  'src/components/workpaper/composables/useRestrictedAssetsSync.ts',
]

function src(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8')
}

describe('rowScopeFailureMessage', () => {
  it('无失败时返回 null（调用方据此不弹提示）', () => {
    expect(rowScopeFailureMessage('外币货币性项目', [], {})).toBeNull()
    expect(rowScopeFailureMessage('外币货币性项目', undefined, undefined)).toBeNull()
    expect(rowScopeFailureMessage('外币货币性项目', null, null)).toBeNull()
  })

  it('有原因时把原因原样带出（不是只报表名）', () => {
    const msg = rowScopeFailureMessage(
      '外币货币性项目',
      ['其他应付款'],
      { 其他应付款: '其他应付款（章节 五、42，段 BS-050）：附注模板该表缺少段首行标记' },
    )
    expect(msg).toContain('附注模板该表缺少段首行标记')
    expect(msg).toContain('五、42')
    expect(msg).toContain('外币货币性项目')
  })

  it('后端没给原因时兜底文案要显式（空串等于静默）', () => {
    const msg = rowScopeFailureMessage('受限资产', ['某表'], {})
    expect(msg).toBeTruthy()
    expect(msg).toContain('某表')
    expect(msg).toContain('段边界解析失败')
  })

  it('多表失败时逐表列出原因', () => {
    const msg = rowScopeFailureMessage('受限资产', ['A', 'B'], {
      A: 'A：准则未填',
      B: 'B：表名不一致',
    })
    expect(msg).toContain('准则未填')
    expect(msg).toContain('表名不一致')
  })

  it('非字符串表名被忽略（防 `String(null)` 造出假表名）', () => {
    const msg = rowScopeFailureMessage('X', [null as any, undefined as any, ''], {})
    expect(msg).toBeNull()
  })
})

describe('消费方接线（防 additive 死字段）', () => {
  it.each(CONSUMERS)('%s 读取 row_scope_unresolved_reasons', (rel) => {
    const text = src(rel)
    expect(text, `${rel} 没读原因字段 —— 后端多返的键成了死代码`).toContain(
      'row_scope_unresolved_reasons',
    )
  })

  it.each(CONSUMERS)('%s 走共享文案函数（禁各写一份）', (rel) => {
    expect(src(rel)).toContain('rowScopeFailureMessage')
  })

  it.each(CONSUMERS)('%s 不再自行拼「段边界解析失败」文案', (rel) => {
    const text = src(rel)
    // 文案单一真源在 `shared/rowScopeFailure.ts`；消费方里出现该字面量说明又抄了一份
    expect(text, `${rel} 仍自拼文案 → 与共享真源分叉`).not.toContain(
      '段边界解析失败）：',
    )
  })

  it('共享文案函数只有一份实现', () => {
    const helper = src('src/components/workpaper/composables/shared/rowScopeFailure.ts')
    expect(helper).toContain('export function rowScopeFailureMessage')
    // 兜底分支必须存在（后端加新错误码时前端不至于显示空白）
    expect(helper).toContain('fallbackReason')
  })
})
