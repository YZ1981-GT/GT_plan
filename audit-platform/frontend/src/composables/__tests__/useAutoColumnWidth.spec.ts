/**
 * useAutoColumnWidth.spec.ts — 列宽内容自适应测算
 *
 * 背景：element-plus 的 `table-layout="auto"` 因上游 issue #19737（OPEN）
 * 在「fixed 列 + width」组合下渲染错位，且 el-table-v2 架构上不支持它，
 * 故列宽自适应走内容测量路线。本测试锁住测量逻辑的关键性质。
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'
import { useAutoColumnWidth } from '../useAutoColumnWidth'

/** 与平台一致的金额格式：千分符 + 两位小数 */
const fmtAmount = (v: any): string => {
  const n = Number(v) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

describe('useAutoColumnWidth — 内容越长列越宽', () => {
  it('长内容列宽度大于短内容列', () => {
    const rows = ref([
      { short: 1, long: 123456789.12 },
      { short: 2, long: 987654321.99 },
    ])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [
        { field: 'short', header: 'A' },
        { field: 'long', header: 'B' },
      ],
      formatter: fmtAmount,
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    expect(colWidth('long')).toBeGreaterThan(colWidth('short'))
  })

  it('空列收窄到 minWidth，不占多余空间', () => {
    const rows = ref([{ empty: 0 }, { empty: 0 }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'empty', header: 'x' }],
      formatter: () => '-',
      defaultMinWidth: 56,
      defaultMaxWidth: 180,
    })
    expect(colWidth('empty')).toBe(56)
  })

  it('表头比数据长时，宽度由表头决定（表头不被截断）', () => {
    const rows = ref([{ f: 1 }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: '这是一个很长的中文表头名称' }],
      formatter: () => '1',
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    // 13 个中文字 * 8px * 1.7 + 16 padding ≈ 193
    expect(colWidth('f')).toBeGreaterThan(150)
  })

  it('超长内容被 maxWidth 截住（其余交给 CSS 折行）', () => {
    const rows = ref([{ f: '这是一段非常非常非常长的文本内容会超过最大列宽限制' }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: 'f', type: 'text', maxWidth: 200 }],
      formatter: fmtAmount,
    })
    expect(colWidth('f')).toBe(200)
  })
})

describe('useAutoColumnWidth — text 列型', () => {
  it('text 列空值不会被数值 formatter 变成 0.00', () => {
    const rows = ref([{ name: null }, { name: undefined }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'name', header: 'n', type: 'text' }],
      formatter: fmtAmount, // 若误用于 text 列会产出 "0.00"（4+ 字符宽）
      defaultMinWidth: 20,
      defaultMaxWidth: 999,
    })
    // 只剩表头宽度（单字符），远小于 "0.00" 的宽度
    expect(colWidth('name')).toBeLessThan(40)
  })

  it('CJK 文本比同字数 ASCII 更宽', () => {
    const rows = ref([{ cjk: '中文内容示例', ascii: 'abcdef' }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [
        { field: 'cjk', header: 'a', type: 'text' },
        { field: 'ascii', header: 'b', type: 'text' },
      ],
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    expect(colWidth('cjk')).toBeGreaterThan(colWidth('ascii'))
  })

  it('boolean 值按「是/-」测宽，不产出 true/false', () => {
    const rows = ref([{ flag: true }, { flag: false }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'flag', header: 'f', type: 'text' }],
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    // "是" 一个 CJK 字 ≈ 6.2*1.7 + 16 ≈ 26.5；"false" 会是 5*6.2+16=47
    expect(colWidth('flag')).toBeLessThan(40)
  })
})

describe('useAutoColumnWidth — 列级 formatter 优先', () => {
  it('列级 formatter 覆盖全局 formatter', () => {
    const rows = ref([{ f: 1 }])
    const { colWidth: narrow } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: 'f' }],
      formatter: () => '1',
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    const { colWidth: wide } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: 'f', formatter: () => '1234567890' }],
      formatter: () => '1',
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    expect(wide('f')).toBeGreaterThan(narrow('f'))
  })
})

describe('useAutoColumnWidth — 容器撑满', () => {
  it('总宽不足容器时放大到恰好铺满（消除右侧留白）', () => {
    const rows = ref([{ a: 1, b: 2 }])
    const { totalWidth } = useAutoColumnWidth({
      rows,
      columns: [
        { field: 'a', header: 'a' },
        { field: 'b', header: 'b' },
      ],
      formatter: fmtAmount,
      containerWidth: 1000,
    })
    expect(totalWidth.value).toBe(1000)
  })

  it('noGrow 列不参与放大，宽度保持原值', () => {
    const rows = ref([{ seq: 1, name: '客户' }])
    const { colWidth, totalWidth } = useAutoColumnWidth({
      rows,
      columns: [
        { field: 'seq', header: '序号', minWidth: 60, maxWidth: 60, noGrow: true },
        { field: 'name', header: '名称', type: 'text' },
      ],
      containerWidth: 800,
    })
    expect(colWidth('seq')).toBe(60)
    expect(totalWidth.value).toBe(800)
  })

  it('总宽已超容器时不缩窄（走横向滚动，由 CSS 折行兜住）', () => {
    const rows = ref([{ a: 123456789012345 }])
    const { totalWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'a', header: 'a', maxWidth: 500 }],
      formatter: fmtAmount,
      containerWidth: 100,
    })
    expect(totalWidth.value).toBeGreaterThan(100)
  })

  it('不传 containerWidth 时不做任何放大（既有调用方行为不变）', () => {
    const rows = ref([{ a: 1 }])
    const opts = {
      rows,
      columns: [{ field: 'a', header: 'a' }],
      formatter: fmtAmount,
      defaultMinWidth: 56,
      defaultMaxWidth: 180,
    }
    const { colWidth } = useAutoColumnWidth(opts)
    const { colWidth: withContainer } = useAutoColumnWidth({ ...opts, containerWidth: 0 })
    expect(colWidth('a')).toBe(withContainer('a'))
  })
})

describe('useAutoColumnWidth — 响应式', () => {
  it('数据变化后宽度重算', () => {
    const rows = ref<Record<string, any>[]>([{ f: 1 }])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: 'f', type: 'text' }],
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    const before = colWidth('f')
    rows.value = [{ f: '一段明显更长的文本内容' }]
    expect(colWidth('f')).toBeGreaterThan(before)
  })

  it('列定义传 computed 时能随之变化（账龄段等动态列）', () => {
    const rows = ref([{ a: 'x', b: 'yyyyyyyyyy' }])
    const useB = ref(false)
    const cols = computed(() =>
      useB.value
        ? [{ field: 'b', header: 'b', type: 'text' as const }]
        : [{ field: 'a', header: 'a', type: 'text' as const }],
    )
    const { totalWidth } = useAutoColumnWidth({
      rows,
      columns: cols,
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    const before = totalWidth.value
    useB.value = true
    expect(totalWidth.value).toBeGreaterThan(before)
  })
})

describe('useAutoColumnWidth — 大数据集性能护栏', () => {
  it('只扫描 sampleLimit 行，超出部分不影响宽度', () => {
    const rows = ref([
      ...Array.from({ length: 10 }, () => ({ f: 'short' })),
      { f: '这一行非常长但排在采样窗口之外不应影响列宽计算结果' },
    ])
    const { colWidth } = useAutoColumnWidth({
      rows,
      columns: [{ field: 'f', header: 'f', type: 'text' }],
      sampleLimit: 10,
      defaultMinWidth: 10,
      defaultMaxWidth: 999,
    })
    // 'short' = 5 ASCII * 6.2 + 16 = 47
    expect(colWidth('f')).toBeLessThan(60)
  })
})
