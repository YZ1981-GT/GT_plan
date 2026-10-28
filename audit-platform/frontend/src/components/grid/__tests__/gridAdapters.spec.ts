/**
 * spec excel-style-table-editing R2.2 / R9 / R10.3 / R5.3：适配组件在表格外透传、单向绑定修复、
 * expose 转发、页面自激活编辑器兼容、卸载时提交、下拉格选定即提交。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import WpAmountInput from '@/components/workpaper/shared/WpAmountInput.vue'
import {
  activeInput, cell, click, clipboardEvent, dblclick, kernelOf, key, mountGrid, mousedown, settle, settleFrames, sink,
  typeInSink, unmountAll,
} from './gridHarness'

afterEach(() => unmountAll())

describe('表格外透传（R2.2）与单向绑定修复（R9）', () => {
  it('只绑 :model-value + @change 的 el-input 能打字，change 带上打的字', async () => {
    const onChange = vi.fn()
    const w = await mountGrid(`<div><el-input id="x" :model-value="v" @change="onChange" /></div>`, () => ({ v: 'abc' }), { onChange } as never)
    const input = w.element.querySelector('input') as HTMLInputElement
    input.focus()
    input.value = 'abcd'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    expect(input.value).toBe('abcd') // 原生 el-input 这里会被改回 abc（design §1.3）
    input.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange.mock.calls[0][0]).toBe('abcd')
  })

  it('只绑 :model-value + @blur 读 e.target.value 的写法读到打的字', async () => {
    const onBlur = vi.fn()
    const w = await mountGrid(`<div><el-input :model-value="v" @blur="(e) => onBlur(e.target.value)" /></div>`, () => ({ v: '原' }), { onBlur } as never)
    const input = w.element.querySelector('input') as HTMLInputElement
    input.focus()
    input.value = '新值'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    input.blur()
    await settle()
    expect(onBlur).toHaveBeenCalledWith('新值')
  })

  it('v-model 照常即时更新；表头插槽里的输入框不按单元格处理', async () => {
    const w = await mountGrid(`
      <div>
        <el-input id="free" v-model="v" />
        <el-table :data="rows">
          <el-table-column label="名称"><template #header><el-input id="hdr" v-model="q" /></template>
            <template #default="{ row }">{{ row.name }}</template></el-table-column>
        </el-table>
      </div>`, () => ({ v: 'a', q: '', rows: [{ name: '甲' }] }))
    const free = w.element.querySelector('#free') as HTMLInputElement
    free.value = 'ab'
    free.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    expect((w.vm as unknown as { v: string }).v).toBe('ab')
    expect(w.element.querySelector('#hdr')).not.toBeNull()
  })

  it('expose 转发：表格外 ref.focus() 聚焦原生输入框', async () => {
    const w = await mountGrid(`<div><el-input ref="inp" v-model="v" /></div>`, () => ({ v: '' }))
    ;(w.vm.$refs.inp as { focus: () => void }).focus()
    await settle()
    expect(document.activeElement?.tagName).toBe('INPUT')
  })
})

describe('页面自激活的编辑器（design §7）', () => {
  it('点了才渲染的编辑器：挂载在刚点过的格里就直接打开', async () => {
    const w = await mountGrid(`
      <el-table :data="rows" @cell-click="(row) => row.editing = true">
        <el-table-column label="名称"><template #default="{ row }">
          <el-input v-if="row.editing" v-model="row.name" />
          <span v-else>{{ row.name }}</span>
        </template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲', editing: false }] }))
    click(cell(w, 0, 0))
    await settle()
    expect(activeInput(w).value).toBe('甲')
  })

  it('带 autofocus 的编辑器挂载即打开；显示态下 focus() 等同打开', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }"><el-input ref="inp" v-model="row.name" /></template></el-table-column>
        <el-table-column label="数"><template #default="{ row }"><el-input-number v-if="row.show" v-model="row.n" autofocus /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲', n: 1, show: false }] }))
    const vm = w.vm as unknown as { rows: Array<{ show: boolean }> }
    vm.rows[0].show = true
    await settle()
    expect(cell(w, 0, 1).hasAttribute('data-gt-editing')).toBe(true)
    key(activeInput(w), 'Escape')
    await settle()
    const ref = (w.vm.$refs.inp as unknown as { focus: () => void })
    ref.focus()
    await settle()
    expect(cell(w, 0, 0).hasAttribute('data-gt-editing')).toBe(true)
  })

  it('编辑中上方删行（按下标复用格子）：打的字提交给原来那一行，不落到下一行', async () => {
    const onChange = vi.fn()
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }"><el-input :model-value="row.name" @change="(v) => onChange(row.name, v)" /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲' }, { name: '乙' }] }), { onChange } as never)
    click(cell(w, 0, 0))
    key(sink(w), 'F2')
    await settle()
    const input = activeInput(w)
    input.value = '甲改'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    ;(w.vm as unknown as { rows: unknown[] }).rows.splice(0, 1)
    await settle()
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('甲', '甲改')
  })

  it('格里已有编辑器、点击后整行重挂（换了 row-key）：不自动打开', async () => {
    let seq = 0
    const w = await mountGrid(`
      <el-table :data="rows" row-key="k" @cell-click="reload">
        <el-table-column label="名称"><template #default="{ row }"><el-input v-model="row.name" /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ k: 'a0', name: '甲' }] }), {
      reload(this: { rows: Array<{ k: string; name: string }> }) { seq += 1; this.rows = this.rows.map((r) => ({ ...r, k: `a${seq}` })) },
    } as never)
    click(cell(w, 0, 0))
    await settleFrames()
    expect(cell(w, 0, 0).hasAttribute('data-gt-active')).toBe(true) // 行换了新元素，选区按坐标重贴
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('格里已有编辑器、点击后同一格里编辑器重挂（换了 key）：不自动打开', async () => {
    const w = await mountGrid(`
      <el-table :data="rows" @cell-click="(row) => row.v++">
        <el-table-column label="名称"><template #default="{ row }"><el-input :key="row.v" v-model="row.name" /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ v: 0, name: '甲' }] }))
    click(cell(w, 0, 0))
    await settle()
    expect((w.vm as unknown as { rows: Array<{ v: number }> }).rows[0].v).toBe(1)
    expect(cell(w, 0, 0).hasAttribute('data-gt-active')).toBe(true)
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('焦点离开表格：先提交（change 在 blur 之前）', async () => {
    const order: string[] = []
    const w = await mountGrid(`
      <div><input id="outside" />
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }">
          <el-input :model-value="row.name" @change="(v) => { order.push('change:' + v); row.name = v }" @blur="order.push('blur')" />
        </template></el-table-column>
      </el-table></div>`, () => ({ rows: [{ name: '甲' }], order }))
    click(cell(w, 0, 0))
    typeInSink(sink(w), '乙')
    await settle()
    ;(w.element.querySelector('#outside') as HTMLInputElement).focus()
    await settle()
    expect(order).toEqual(['change:乙', 'blur'])
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('快速连敲：编辑器挂好之前敲的字不丢', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }"><el-input v-model="row.name" /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲' }] }))
    click(cell(w, 0, 0))
    typeInSink(sink(w), 'a')
    typeInSink(sink(w), 'b')
    typeInSink(sink(w), 'c')
    await settle()
    expect(activeInput(w).value).toBe('abc')
  })

  it('单元格里弹出层（气泡）中的输入框按普通控件处理', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }">
          <el-popover :visible="true" :teleported="false">
            <template #reference><el-button>改</el-button></template>
            <el-input id="pop" v-model="row.name" />
          </el-popover>
        </template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲' }] }))
    expect(w.element.querySelector('input#pop')).not.toBeNull()
  })
})

describe('宿主在 focus 里换显示值（浏览器实测：底稿金额格 WpAmountInput）', () => {
  const AMT = `
    <el-table :data="rows">
      <el-table-column label="金额"><template #default="{ row }"><wp-amount-input v-model="row.amt" @change="onChange" /></template></el-table-column>
    </el-table>`

  it('双击打开不被当成「这一格换了行」收起；编辑框是去千分符的编辑态；不改直接回车不发 change、不记撤销', async () => {
    const onChange = vi.fn()
    const w = await mountGrid(AMT, () => ({ rows: [{ amt: 1234.5 }] }), { onChange } as never, { WpAmountInput })
    const td = cell(w, 0, 0)
    expect(td.textContent?.trim()).toBe('1,234.50')
    click(td)
    dblclick(td)
    await settle()
    expect(td.hasAttribute('data-gt-editing')).toBe(true)
    expect(activeInput(w).value).toBe('1234.5')
    key(activeInput(w), 'Enter')
    await settle()
    expect(td.hasAttribute('data-gt-editing')).toBe(false)
    expect(onChange).not.toHaveBeenCalled()
    expect(kernelOf(w).canUndo()).toBe(false)
    expect(td.textContent?.trim()).toBe('1,234.50')
  })

  it('双击后改值回车：宿主失焦归一写回、可撤销；再双击打字后 Esc 还原不写', async () => {
    const onChange = vi.fn()
    const w = await mountGrid(AMT, () => ({ rows: [{ amt: 1234.5 }] }), { onChange } as never, { WpAmountInput })
    const data = (w.vm as unknown as { rows: Array<{ amt: number }> }).rows
    const td = cell(w, 0, 0)
    click(td)
    dblclick(td)
    await settle()
    const input = activeInput(w)
    input.value = '2000'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    key(input, 'Enter')
    await settle()
    expect(data[0].amt).toBe(2000)
    expect(onChange).toHaveBeenCalledWith(2000)
    expect(td.textContent?.trim()).toBe('2,000.00')
    expect(kernelOf(w).canUndo()).toBe(true)
    dblclick(td)
    await settle()
    const again = activeInput(w)
    again.value = '9'
    again.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    key(again, 'Escape')
    await settle()
    expect(data[0].amt).toBe(2000)
    expect(td.textContent?.trim()).toBe('2,000.00')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('只认 change 的宿主在 focus 里换显示值：先敲的字不被宿主的编辑态覆盖，回车照常提交', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="金额"><template #default="{ row }">
          <el-input :model-value="row.f ? String(row.v) : row.v.toFixed(2)" @focus="row.f = true" @blur="row.f = false" @change="(v) => { row.v = Number(v) }" />
        </template></el-table-column>
      </el-table>`, () => ({ rows: [{ v: 1234.5, f: false }] }))
    const data = (w.vm as unknown as { rows: Array<{ v: number }> }).rows
    const td = cell(w, 0, 0)
    expect(td.textContent?.trim()).toBe('1234.50')
    click(td)
    typeInSink(sink(w), '7')
    await settle()
    expect(td.hasAttribute('data-gt-editing')).toBe(true)
    expect(activeInput(w).value).toBe('7')
    key(activeInput(w), 'Enter')
    await settle()
    expect(data[0].v).toBe(7)
    expect(td.textContent?.trim()).toBe('7.00')
  })

  it('宿主写回时规整了值（50 → 50.00）：粘贴、编辑都能撤销 / 重做，不误报「已被其他操作修改」', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="期初"><template #default="{ row }"><wp-amount-input v-model="row.a" /></template></el-table-column>
        <el-table-column label="增加"><template #default="{ row }"><wp-amount-input v-model="row.b" /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ a: 100, b: 0 }] }), {}, { WpAmountInput })
    const data = (w.vm as unknown as { rows: Array<{ a: number; b: number }> }).rows
    click(cell(w, 0, 0))
    sink(w).dispatchEvent(clipboardEvent('paste', { 'text/plain': '50\t25' }).ev)
    await settle()
    expect([data[0].a, data[0].b]).toEqual([50, 25])
    expect(cell(w, 0, 0).textContent?.trim()).toBe('50.00')
    key(sink(w), 'z', { ctrlKey: true })
    await settle()
    expect([data[0].a, data[0].b]).toEqual([100, 0])
    key(sink(w), 'y', { ctrlKey: true })
    await settle()
    expect([data[0].a, data[0].b]).toEqual([50, 25])
    typeInSink(sink(w), '7')
    await settle()
    key(activeInput(w), 'Enter')
    await settle()
    expect(data[0].a).toBe(7)
    key(sink(w), 'z', { ctrlKey: true })
    await settle()
    expect(data[0].a).toBe(50)
    expect(document.querySelector('.el-message--warning')).toBeNull()
  })

  it('撤销写回的旧值也被宿主规整（存量小写 → 写入即转大写）：之后仍能重做', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="代码"><template #default="{ row }">
          <el-input :model-value="row.code" @change="(v) => { row.code = String(v).toUpperCase() }" />
        </template></el-table-column>
      </el-table>`, () => ({ rows: [{ code: 'x1' }] }))
    const data = (w.vm as unknown as { rows: Array<{ code: string }> }).rows
    click(cell(w, 0, 0))
    typeInSink(sink(w), 'ab')
    await settle()
    key(activeInput(w), 'Enter')
    await settle()
    expect(data[0].code).toBe('AB')
    key(sink(w), 'z', { ctrlKey: true })
    await settle()
    expect(data[0].code).toBe('X1')
    key(sink(w), 'y', { ctrlKey: true })
    await settle()
    expect(data[0].code).toBe('AB')
    expect(document.querySelector('.el-message--warning')).toBeNull()
  })

  it('0 值格直接打字：首字不丢（宿主 focus 把 0 显示成空）', async () => {
    const w = await mountGrid(AMT, () => ({ rows: [{ amt: 0 }] }), { onChange: () => undefined } as never, { WpAmountInput })
    const td = cell(w, 0, 0)
    expect(td.textContent?.trim()).toBe('0.00')
    click(td)
    typeInSink(sink(w), '5')
    await settle()
    expect(activeInput(w).value).toBe('5')
  })
})

describe('禁用格（R7）', () => {
  it('粘贴跳过禁用格并计数', async () => {
    const w = await mountGrid(`
      <el-table :data="rows">
        <el-table-column label="名称"><template #default="{ row }"><el-input v-model="row.name" disabled /></template></el-table-column>
      </el-table>`, () => ({ rows: [{ name: '甲' }] }))
    click(cell(w, 0, 0))
    const res = await kernelOf(w).applyMatrix([['乙']])
    expect(res).toMatchObject({ written: 0, skipped: 1, failed: 0 })
    expect((w.vm as unknown as { rows: Array<{ name: string }> }).rows[0].name).toBe('甲')
    expect(cell(w, 0, 0).querySelector('.gt-cell-display--readonly')).not.toBeNull()
  })
})

describe('下拉 / 勾选格（R4.7）', () => {
  const SELECT = `
    <el-table :data="rows">
      <el-table-column label="结论"><template #default="{ row }">
        <el-select :model-value="row.v" @change="(v) => { row.v = v; onChange(v) }">
          <el-option label="相符" value="ok" /><el-option label="不符" value="bad" />
        </el-select>
      </template></el-table-column>
      <el-table-column label="已核对"><template #default="{ row }"><el-checkbox v-model="row.done" /></template></el-table-column>
    </el-table>`

  it('下拉格显示选项名称；双击展开，选定即提交并收起', async () => {
    const onChange = vi.fn()
    const w = await mountGrid(SELECT, () => ({ rows: [{ v: 'ok', done: false }] }), { onChange } as never)
    expect(cell(w, 0, 0).textContent).toContain('相符')
    mousedown(cell(w, 0, 0))
    dblclick(cell(w, 0, 0))
    await settle()
    expect(cell(w, 0, 0).hasAttribute('data-gt-editing')).toBe(true)
    const select = cell(w, 0, 0).querySelector('.el-select') as Element
    expect(select).not.toBeNull()
    // 选中「不符」：Element 的选项点击在 jsdom 下走同一条 emit 路径
    const options = Array.from(document.querySelectorAll('.el-select-dropdown__item')) as HTMLElement[]
    options.find((o) => o.textContent?.includes('不符'))!.click()
    await settle()
    expect(onChange).toHaveBeenCalledWith('bad')
    expect(cell(w, 0, 0).hasAttribute('data-gt-editing')).toBe(false)
    expect(cell(w, 0, 0).textContent).toContain('不符')
  })

  it('勾选格显示控件本身；空格切换；粘贴「是」', async () => {
    const w = await mountGrid(SELECT, () => ({ rows: [{ v: 'ok', done: false }] }))
    const data = (w.vm as unknown as { rows: Array<{ done: boolean }> }).rows
    expect(cell(w, 0, 1).querySelector('.el-checkbox')).not.toBeNull()
    mousedown(cell(w, 0, 1).querySelector('.cell')!)
    await nextTick()
    key(sink(w), ' ')
    await settle()
    expect(data[0].done).toBe(true)
  })
})
