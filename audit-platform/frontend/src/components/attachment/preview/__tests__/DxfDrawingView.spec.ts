import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DxfDrawingView from '../drawing/DxfDrawingView.vue'
import type { DxfEntity, DxfRenderModel } from '../drawing/dxfModel'

function model(entities: DxfEntity[], bounds = { minX: -20, minY: -20, maxX: 200, maxY: 100 }): DxfRenderModel {
  return { entities, bounds, truncated: false }
}

describe('DxfDrawingView', () => {
  it('按弧度渲染跨 0 与大 ARC，并在 Y 翻转后使用正确 sweep', () => {
    const wrapper = mount(DxfDrawingView, {
      props: {
        model: model([
          { type: 'ARC', cx: 0, cy: 0, r: 10, start: (350 * Math.PI) / 180, end: (10 * Math.PI) / 180 },
          { type: 'ARC', cx: 30, cy: 0, r: 10, start: (10 * Math.PI) / 180, end: (300 * Math.PI) / 180 },
        ]),
      },
    })

    const arcs = wrapper.findAll('path[data-dxf-type="ARC"]')
    expect(arcs).toHaveLength(2)
    expect(arcs[0].attributes('d')).toContain('A 10 10 0 0 0')
    expect(arcs[1].attributes('d')).toContain('A 10 10 0 1 0')
    expect(arcs[0].attributes('d')).toMatch(/^M 9\.848077530122 1\.736481776669/)
    expect(arcs[0].attributes('d')).toMatch(/9\.848077530122 -1\.736481776669$/)
  })

  it('完整 ELLIPSE 使用 ellipse，部分椭圆弧使用 path 且保留旋转轴', () => {
    const wrapper = mount(DxfDrawingView, {
      props: {
        model: model([
          { type: 'ELLIPSE', cx: 10, cy: 20, mx: 4, my: 3, ratio: 0.5, start: 0, end: Math.PI * 2 },
          { type: 'ELLIPSE', cx: 40, cy: 20, mx: 8, my: 0, ratio: 0.25, start: 0, end: Math.PI * 1.5 },
        ]),
      },
    })

    const full = wrapper.get('ellipse[data-dxf-type="ELLIPSE"]')
    expect(full.attributes()).toMatchObject({ cx: '10', cy: '-20', rx: '5', ry: '2.5' })
    expect(full.attributes('transform')).toBe('rotate(-36.869897645844 10 -20)')

    const partial = wrapper.get('path[data-dxf-type="ELLIPSE"]')
    expect(partial.attributes('d')).toContain('A 8 2 0 1 0')
    expect(partial.attributes('d')).toMatch(/^M 48 -20/)
  })

  it('以递归 g 保留 INSERT children，并应用 base point、平移、缩放与旋转', () => {
    const nested: DxfEntity = {
      type: 'INSERT',
      name: 'OUTER',
      x: 100,
      y: 50,
      sx: 2,
      sy: 3,
      rotation: 90,
      baseX: 5,
      baseY: 6,
      children: [
        {
          type: 'INSERT',
          name: 'INNER',
          x: 8,
          y: 9,
          sx: 0.5,
          sy: 0.25,
          rotation: 30,
          baseX: 1,
          baseY: 2,
          children: [{ type: 'LINE', x1: 1, y1: 2, x2: 4, y2: 2 }],
        },
      ],
    }
    const wrapper = mount(DxfDrawingView, { props: { model: model([nested]) } })

    const groups = wrapper.findAll('g[data-dxf-type="INSERT"]')
    expect(groups).toHaveLength(2)
    expect(groups[0].attributes('transform')).toBe('translate(100 -50) rotate(-90) scale(2 3) translate(-5 6)')
    expect(groups[1].attributes('transform')).toBe('translate(8 -9) rotate(-30) scale(0.5 0.25) translate(-1 2)')
    const child = groups[1].get('line[data-dxf-type="LINE"]')
    expect(child.attributes()).toMatchObject({
      x1: '1', y1: '-2', x2: '4', y2: '-2', 'vector-effect': 'non-scaling-stroke',
    })
  })

  it('closed polyline 真正输出 polygon，并覆盖 union 的每个渲染分支', () => {
    const entities: DxfEntity[] = [
      { type: 'LINE', x1: 0, y1: 0, x2: 1, y2: 1 },
      { type: 'CIRCLE', cx: 2, cy: 2, r: 1 },
      { type: 'ARC', cx: 4, cy: 4, r: 1, start: 0, end: Math.PI },
      { type: 'POINT', x: 5, y: 5 },
      { type: 'LWPOLYLINE', points: [{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 2 }], closed: true },
      { type: 'TEXT', x: 6, y: 6, text: 'text', height: 1 },
      { type: 'MTEXT', x: 7, y: 7, text: 'mtext', height: 1 },
      { type: 'ELLIPSE', cx: 8, cy: 8, mx: 2, my: 0, ratio: 0.5, start: 0, end: Math.PI * 2 },
      { type: 'INSERT', name: 'EMPTY', x: 0, y: 0, sx: 1, sy: 1, rotation: 0, baseX: 0, baseY: 0, children: [] },
    ]
    const wrapper = mount(DxfDrawingView, { props: { model: model(entities) } })

    for (const type of ['LINE', 'CIRCLE', 'ARC', 'POINT', 'LWPOLYLINE', 'TEXT', 'MTEXT', 'ELLIPSE', 'INSERT']) {
      expect(wrapper.find(`[data-dxf-type="${type}"]`).exists(), type).toBe(true)
    }
    const closed = wrapper.get('polygon[data-dxf-type="LWPOLYLINE"]')
    expect(closed.attributes('points')).toBe('0,0 2,0 2,-2')
    expect(wrapper.find('polyline[data-dxf-type="LWPOLYLINE"]').exists()).toBe(false)
  })

  it('把 INSERT 循环或深度限制显式呈现为截断提示', () => {
    const wrapper = mount(DxfDrawingView, {
      props: {
        model: {
          entities: [{
            type: 'INSERT', name: 'LOOP', x: 0, y: 0, sx: 1, sy: 1,
            rotation: 0, baseX: 0, baseY: 0, children: [],
          }],
          bounds: { minX: 0, minY: 0, maxX: 1, maxY: 1 },
          truncated: true,
          truncateReason: 'insertCycle:LOOP',
        },
      },
    })

    expect(wrapper.get('[data-testid="dxf-truncated"]').text()).toContain('insertCycle:LOOP')
    expect(wrapper.get('g[data-dxf-type="INSERT"]').attributes('data-block-name')).toBe('LOOP')
  })
})
