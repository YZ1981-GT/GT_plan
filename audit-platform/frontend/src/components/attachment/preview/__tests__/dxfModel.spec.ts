import { describe, expect, it } from 'vitest'
import { exceedsDxfEntityLimit, parseDxfBytes } from '../drawing/dxfModel'
import { DRAWING_LIMITS } from '../drawing/drawingLimits'

function encode(lines: Array<string | number>): ArrayBuffer {
  return new TextEncoder().encode(`${lines.join('\n')}\n`).buffer
}

function pair(code: number, value: string | number): Array<string | number> {
  return [code, value]
}

describe('dxfModel scene graph', () => {
  it('所有 ENTITIES/BLOCKS 实体类型都参与预扫，unsupported flood 在 parser 前被拒绝', () => {
    const tinyUnsupported = '0\nSECTION\n2\nENTITIES\n0\nHATCH\n0\nHATCH\n0\nENDSEC\n0\nEOF\n'
    expect(exceedsDxfEntityLimit(tinyUnsupported, 1)).toBe(true)

    const body = '0\nHATCH\n'.repeat(DRAWING_LIMITS.maxEntities + 1)
    const input = new TextEncoder().encode(
      `0\nSECTION\n2\nENTITIES\n${body}0\nENDSEC\n0\nEOF\n`,
    ).buffer
    expect(parseDxfBytes(input)).toEqual({
      status: 'limit',
      message: 'dxf_entity_prescan_limit',
    })
  })

  it('保留 ARC 弧度、ELLIPSE start/end 与 closed polyline，并给椭圆弧安全 bounds', () => {
    const input = encode([
      ...pair(0, 'SECTION'), ...pair(2, 'ENTITIES'),
      ...pair(0, 'ARC'), ...pair(8, 0), ...pair(10, 0), ...pair(20, 0), ...pair(40, 2), ...pair(50, 350), ...pair(51, 10),
      ...pair(0, 'ELLIPSE'), ...pair(8, 0), ...pair(10, 10), ...pair(20, 20), ...pair(11, 5), ...pair(21, 0), ...pair(40, 0.5), ...pair(41, 0.5), ...pair(42, 2.5),
      ...pair(0, 'LWPOLYLINE'), ...pair(8, 0), ...pair(90, 3), ...pair(70, 1),
      ...pair(10, 0), ...pair(20, 0), ...pair(10, 1), ...pair(20, 0), ...pair(10, 1), ...pair(20, 1),
      ...pair(0, 'ENDSEC'), ...pair(0, 'EOF'),
    ])
    const result = parseDxfBytes(input)

    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    const arc = result.model.entities.find((entity) => entity.type === 'ARC')
    const ellipse = result.model.entities.find((entity) => entity.type === 'ELLIPSE')
    const polyline = result.model.entities.find((entity) => entity.type === 'LWPOLYLINE')
    expect(arc?.type === 'ARC' ? arc.start : 0).toBeCloseTo((350 * Math.PI) / 180)
    expect(arc?.type === 'ARC' ? arc.end : 0).toBeCloseTo((10 * Math.PI) / 180)
    expect(ellipse).toMatchObject({ type: 'ELLIPSE', start: 0.5, end: 2.5 })
    expect(polyline).toMatchObject({ type: 'LWPOLYLINE', closed: true })
    expect(result.model.bounds.minX).toBeLessThanOrEqual(5)
    expect(result.model.bounds.maxX).toBeGreaterThanOrEqual(15)
    expect(result.model.bounds.minY).toBeLessThanOrEqual(17.5)
    expect(result.model.bounds.maxY).toBeGreaterThanOrEqual(22.5)
  })

  it('INSERT 保留嵌套 children，应用 block base point 与组合变换计算 bounds', () => {
    const input = encode([
      ...pair(0, 'SECTION'), ...pair(2, 'BLOCKS'),
      ...pair(0, 'BLOCK'), ...pair(8, 0), ...pair(2, 'INNER'), ...pair(70, 0), ...pair(10, 2), ...pair(20, 3),
      ...pair(0, 'LINE'), ...pair(8, 0), ...pair(10, 2), ...pair(20, 3), ...pair(11, 3), ...pair(21, 3),
      ...pair(0, 'ENDBLK'),
      ...pair(0, 'BLOCK'), ...pair(8, 0), ...pair(2, 'OUTER'), ...pair(70, 0), ...pair(10, 5), ...pair(20, 5),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'INNER'), ...pair(10, 7), ...pair(20, 5), ...pair(41, 2), ...pair(42, 3), ...pair(50, 90),
      ...pair(0, 'ENDBLK'), ...pair(0, 'ENDSEC'),
      ...pair(0, 'SECTION'), ...pair(2, 'ENTITIES'),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'OUTER'), ...pair(10, 100), ...pair(20, 50),
      ...pair(0, 'ENDSEC'), ...pair(0, 'EOF'),
    ])
    const result = parseDxfBytes(input)

    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    const outer = result.model.entities[0]
    expect(outer).toMatchObject({ type: 'INSERT', name: 'OUTER', x: 100, y: 50, baseX: 5, baseY: 5 })
    if (outer?.type !== 'INSERT') return
    expect(outer.children).toHaveLength(1)
    const inner = outer.children[0]
    expect(inner).toMatchObject({ type: 'INSERT', name: 'INNER', sx: 2, sy: 3, rotation: 90, baseX: 2, baseY: 3 })
    expect(inner.type === 'INSERT' ? inner.children[0] : undefined).toMatchObject({ type: 'LINE', x1: 2, y1: 3, x2: 3, y2: 3 })
    expect(result.model.bounds.minX).toBeCloseTo(102)
    expect(result.model.bounds.maxX).toBeCloseTo(102)
    expect(result.model.bounds.minY).toBeCloseTo(50)
    expect(result.model.bounds.maxY).toBeCloseTo(52)
  })

  it('循环 INSERT 保留可见节点并标记 truncated，而不是无限展开或静默丢失', () => {
    const input = encode([
      ...pair(0, 'SECTION'), ...pair(2, 'BLOCKS'),
      ...pair(0, 'BLOCK'), ...pair(8, 0), ...pair(2, 'LOOP'), ...pair(70, 0), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'LOOP'), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'ENDBLK'), ...pair(0, 'ENDSEC'),
      ...pair(0, 'SECTION'), ...pair(2, 'ENTITIES'),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'LOOP'), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'ENDSEC'), ...pair(0, 'EOF'),
    ])
    const result = parseDxfBytes(input)

    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.model.truncated).toBe(true)
    expect(result.model.truncateReason).toBe('insertCycle:LOOP')
    const root = result.model.entities[0]
    expect(root?.type).toBe('INSERT')
    expect(root?.type === 'INSERT' ? root.children[0] : undefined).toMatchObject({ type: 'INSERT', name: 'LOOP', children: [] })
  })

  it('超过 INSERT 深度时保留已展开场景并标记 maxInsertDepth', () => {
    const blocks: Array<string | number> = [...pair(0, 'SECTION'), ...pair(2, 'BLOCKS')]
    for (let index = 0; index < 10; index += 1) {
      blocks.push(
        ...pair(0, 'BLOCK'), ...pair(8, 0), ...pair(2, `B${index}`), ...pair(70, 0), ...pair(10, 0), ...pair(20, 0),
      )
      if (index < 9) {
        blocks.push(...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, `B${index + 1}`), ...pair(10, 0), ...pair(20, 0))
      } else {
        blocks.push(...pair(0, 'LINE'), ...pair(8, 0), ...pair(10, 0), ...pair(20, 0), ...pair(11, 1), ...pair(21, 1))
      }
      blocks.push(...pair(0, 'ENDBLK'))
    }
    blocks.push(
      ...pair(0, 'ENDSEC'), ...pair(0, 'SECTION'), ...pair(2, 'ENTITIES'),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'B0'), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'ENDSEC'), ...pair(0, 'EOF'),
    )

    const result = parseDxfBytes(encode(blocks))
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.model.truncated).toBe(true)
    expect(result.model.truncateReason).toBe('maxInsertDepth')
    expect(result.model.entities[0]).toMatchObject({ type: 'INSERT', name: 'B0' })
  })

  it('bounds 覆盖放大 INSERT 内 POINT 半径与文本字形安全盒', () => {
    const input = encode([
      ...pair(0, 'SECTION'), ...pair(2, 'BLOCKS'),
      ...pair(0, 'BLOCK'), ...pair(8, 0), ...pair(2, 'PAINT'), ...pair(70, 0), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'POINT'), ...pair(8, 0), ...pair(10, 0), ...pair(20, 0),
      ...pair(0, 'TEXT'), ...pair(8, 0), ...pair(10, 10), ...pair(20, 0), ...pair(40, 2), ...pair(1, 'AB'),
      ...pair(0, 'ENDBLK'), ...pair(0, 'ENDSEC'),
      ...pair(0, 'SECTION'), ...pair(2, 'ENTITIES'),
      ...pair(0, 'INSERT'), ...pair(8, 0), ...pair(2, 'PAINT'), ...pair(10, 0), ...pair(20, 0), ...pair(41, 100), ...pair(42, 100),
      ...pair(0, 'ENDSEC'), ...pair(0, 'EOF'),
    ])
    const result = parseDxfBytes(input)

    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.model.bounds.minX).toBeCloseTo(-100)
    expect(result.model.bounds.maxX).toBeCloseTo(1480)
    expect(result.model.bounds.minY).toBeCloseTo(-240)
    expect(result.model.bounds.maxY).toBeCloseTo(100)
  })
})
