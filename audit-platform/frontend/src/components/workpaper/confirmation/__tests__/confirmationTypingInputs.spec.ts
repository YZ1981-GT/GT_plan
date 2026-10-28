/**
 * 替代程序公司名 / 函证索引号、A12-1 律师事务所等文本框能打字（spec attachment-confirmation-evidence-loop 浏览器走查实测）
 *
 * el-input 每次输入后把原生值还原成 modelValue；只绑 `:model-value` + `@change`、不回写的框，打的字立即消失、
 * 失焦也拿不到新值（全前端同类写法由 workpaper/__tests__/controlledInputCommitRatchet.spec.ts 冻结）。
 * 这两处挡住了本 spec 的功能：替代程序公司对不上函证（逐笔判定按公司名 / 索引号对应）、A12-1 填不了律师事务所就登记不了函证中心。
 * 🔴 VTU 的 setValue 在 input 后同步补发 change，读到的是还没被还原的值 ⇒ 测这类框只发 input 事件。
 */
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import ElementPlus from 'element-plus'
import AlternativeD05Master from '../alternativeD05/AlternativeD05Master.vue'

const TAG = /<el-input(?![-\w])(?:[^>"']|"[^"]*"|'[^']*')*?\/?>/g
const WRITES_BACK = /v-model\b|@update:model-value|@update:modelValue|@input\b|v-on:input/
const commitOnly = (src: string) =>
  [...src.matchAll(TAG)].filter(([tag]) => tag.includes(':model-value') && tag.includes('@change') && !WRITES_BACK.test(tag)).length

describe('文本框能打字', () => {
  it('替代程序公司名：只发 input 事件就回到宿主（不靠失焦 change）', async () => {
    const w = mount(AlternativeD05Master, {
      props: {
        companies: [{ _company_id: 'c1', seq: 1, entity_name: '', confirm_index: '' }],
        readonly: false, isDirty: false, hasAbnormal: () => false,
        getCompletionStatus: () => ({ completed: 0, total: 4, rate: 0 }), getCheckRatio: () => null,
      } as any,
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    const [name, index] = w.findAll('input')
    ;(name.element as HTMLInputElement).value = '甲公司'
    await name.trigger('input')
    ;(index.element as HTMLInputElement).value = 'D0-1-001'
    await index.trigger('input')
    await flushPromises()
    expect(w.emitted('update-field')).toEqual([['c1', 'entity_name', '甲公司'], ['c1', 'confirm_index', 'D0-1-001']])
  })

  it.each([
    ['alternativeD05/AlternativeD05Master.vue'],
    ['../GtA121LegalConfirmation.vue'],
  ])('%s 没有「只绑 :model-value + @change」的文本框', (rel) => {
    const src = readFileSync(resolve(__dirname, '..', rel), 'utf-8')
    expect(src.includes('<el-input')).toBe(true)
    expect(commitOnly(src)).toBe(0)
  })

  it('判据自检', () => {
    expect(commitOnly('<el-input :model-value="a" @change="(v) => save(v)" />')).toBe(1)
    expect(commitOnly('<el-input :model-value="a" @update:model-value="(v) => save(v)" />')).toBe(0)
  })
})
