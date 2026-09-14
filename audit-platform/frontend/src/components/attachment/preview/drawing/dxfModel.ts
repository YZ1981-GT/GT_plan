/**
 * DXF → typed render model（禁止 SVG string + v-html）
 */
import DxfParser from 'dxf-parser'
import { DRAWING_LIMITS } from './drawingLimits'

export { DRAWING_LIMITS } from './drawingLimits'

export type DxfEntity =
  | { type: 'LINE'; x1: number; y1: number; x2: number; y2: number }
  | { type: 'CIRCLE'; cx: number; cy: number; r: number }
  | { type: 'ARC'; cx: number; cy: number; r: number; start: number; end: number }
  | { type: 'POINT'; x: number; y: number }
  | { type: 'LWPOLYLINE'; points: Array<{ x: number; y: number }>; closed: boolean }
  | { type: 'TEXT'; x: number; y: number; text: string; height: number }
  | { type: 'MTEXT'; x: number; y: number; text: string; height: number }
  | {
      type: 'ELLIPSE'
      cx: number
      cy: number
      mx: number
      my: number
      ratio: number
      start: number
      end: number
    }
  | {
      type: 'INSERT'
      name: string
      x: number
      y: number
      sx: number
      sy: number
      rotation: number
      baseX: number
      baseY: number
      children: DxfEntity[]
    }

export interface DxfRenderModel {
  entities: DxfEntity[]
  bounds: { minX: number; minY: number; maxX: number; maxY: number }
  truncated: boolean
  truncateReason?: string
}

export type DxfParseResult =
  | { status: 'ok'; model: DxfRenderModel }
  | { status: 'limit'; message: string }
  | { status: 'parse_failed'; message: string }

type Matrix = { a: number; b: number; c: number; d: number; e: number; f: number }

const TAU = Math.PI * 2
const IDENTITY: Matrix = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }

function num(v: unknown, d = 0): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : d
}

function multiply(left: Matrix, right: Matrix): Matrix {
  return {
    a: left.a * right.a + left.c * right.b,
    b: left.b * right.a + left.d * right.b,
    c: left.a * right.c + left.c * right.d,
    d: left.b * right.c + left.d * right.d,
    e: left.a * right.e + left.c * right.f + left.e,
    f: left.b * right.e + left.d * right.f + left.f,
  }
}

function insertMatrix(entity: Extract<DxfEntity, { type: 'INSERT' }>): Matrix {
  const angle = (entity.rotation * Math.PI) / 180
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  return {
    a: cos * entity.sx,
    b: sin * entity.sx,
    c: -sin * entity.sy,
    d: cos * entity.sy,
    e: entity.x - cos * entity.sx * entity.baseX + sin * entity.sy * entity.baseY,
    f: entity.y - sin * entity.sx * entity.baseX - cos * entity.sy * entity.baseY,
  }
}

function point(matrix: Matrix, x: number, y: number): { x: number; y: number } {
  return {
    x: matrix.a * x + matrix.c * y + matrix.e,
    y: matrix.b * x + matrix.d * y + matrix.f,
  }
}

function calculateBounds(entities: DxfEntity[]): DxfRenderModel['bounds'] {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  const expand = (x: number, y: number) => {
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
  }
  const expandPoint = (matrix: Matrix, x: number, y: number) => {
    const p = point(matrix, x, y)
    expand(p.x, p.y)
  }
  const expandBox = (matrix: Matrix, left: number, bottom: number, right: number, top: number) => {
    expandPoint(matrix, left, bottom)
    expandPoint(matrix, left, top)
    expandPoint(matrix, right, bottom)
    expandPoint(matrix, right, top)
  }

  const walk = (list: DxfEntity[], matrix: Matrix) => {
    for (const entity of list) {
      if (entity.type === 'LINE') {
        expandPoint(matrix, entity.x1, entity.y1)
        expandPoint(matrix, entity.x2, entity.y2)
      } else if (entity.type === 'CIRCLE' || entity.type === 'ARC') {
        const center = point(matrix, entity.cx, entity.cy)
        // ARC 使用整圆的保守包围盒；任意 INSERT 非均匀缩放/旋转后仍不会裁剪。
        const extentX = entity.r * Math.hypot(matrix.a, matrix.c)
        const extentY = entity.r * Math.hypot(matrix.b, matrix.d)
        expand(center.x - extentX, center.y - extentY)
        expand(center.x + extentX, center.y + extentY)
      } else if (entity.type === 'POINT') {
        const center = point(matrix, entity.x, entity.y)
        const extentX = Math.hypot(matrix.a, matrix.c)
        const extentY = Math.hypot(matrix.b, matrix.d)
        expand(center.x - extentX, center.y - extentY)
        expand(center.x + extentX, center.y + extentY)
      } else if (entity.type === 'LWPOLYLINE') {
        for (const p of entity.points) expandPoint(matrix, p.x, p.y)
      } else if (entity.type === 'TEXT' || entity.type === 'MTEXT') {
        const height = Math.max(Math.abs(entity.height), 1)
        const width = Math.max(height, Array.from(entity.text).length * height * 1.2)
        // SVG text 的 y 是基线；采用保守 em 盒并随 INSERT 组合矩阵变换。
        expandBox(matrix, entity.x, entity.y - height * 1.2, entity.x + width, entity.y + height * 0.4)
      } else if (entity.type === 'ELLIPSE') {
        const center = point(matrix, entity.cx, entity.cy)
        const vx = -entity.my * entity.ratio
        const vy = entity.mx * entity.ratio
        const ux = matrix.a * entity.mx + matrix.c * entity.my
        const uy = matrix.b * entity.mx + matrix.d * entity.my
        const transformedVx = matrix.a * vx + matrix.c * vy
        const transformedVy = matrix.b * vx + matrix.d * vy
        // 部分椭圆弧也使用完整椭圆的安全包围盒，保证不裁剪。
        const extentX = Math.hypot(ux, transformedVx)
        const extentY = Math.hypot(uy, transformedVy)
        expand(center.x - extentX, center.y - extentY)
        expand(center.x + extentX, center.y + extentY)
      } else if (entity.type === 'INSERT') {
        walk(entity.children, multiply(matrix, insertMatrix(entity)))
      }
    }
  }

  walk(entities, IDENTITY)
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 1, maxY: 1 }
  return { minX, minY, maxX, maxY }
}

const DXF_STRUCTURE_TOKENS = new Set([
  'SECTION',
  'ENDSEC',
  'EOF',
  'TABLE',
  'ENDTAB',
  'BLOCK',
  'ENDBLK',
  'SEQEND',
])

function nextDxfLine(text: string, start: number): { value: string; next: number } | null {
  if (start >= text.length) return null
  let end = start
  while (end < text.length && text[end] !== '\n' && text[end] !== '\r') end += 1
  let next = end
  if (text[next] === '\r') next += 1
  if (text[next] === '\n') next += 1
  return { value: text.slice(start, end), next }
}

export function exceedsDxfEntityLimit(text: string, maxEntities: number): boolean {
  let offset = 0
  let section = ''
  let awaitingSectionName = false
  let entities = 0
  while (offset < text.length) {
    const codeLine = nextDxfLine(text, offset)
    if (!codeLine) break
    const valueLine = nextDxfLine(text, codeLine.next)
    if (!valueLine) break
    offset = valueLine.next
    const code = Number.parseInt(codeLine.value.trim(), 10)
    const value = valueLine.value.trim().toUpperCase()
    if (awaitingSectionName) {
      if (code === 2) section = value
      awaitingSectionName = false
      continue
    }
    if (code !== 0) continue
    if (value === 'SECTION') {
      awaitingSectionName = true
      continue
    }
    if (value === 'ENDSEC') {
      section = ''
      continue
    }
    if ((section === 'ENTITIES' || section === 'BLOCKS') && !DXF_STRUCTURE_TOKENS.has(value)) {
      entities += 1
      if (entities > maxEntities) return true
    }
  }
  return false
}

export function parseDxfBytes(input: ArrayBuffer): DxfParseResult {
  if (input.byteLength > DRAWING_LIMITS.maxInputBytes) {
    return { status: 'limit', message: 'dxf_input_limit' }
  }
  const text = new TextDecoder('utf-8', { fatal: false }).decode(input)
  if (exceedsDxfEntityLimit(text, DRAWING_LIMITS.maxEntities)) {
    return { status: 'limit', message: 'dxf_entity_prescan_limit' }
  }

  let dxf: any
  try {
    dxf = new DxfParser().parseSync(text)
  } catch (error) {
    return { status: 'parse_failed', message: error instanceof Error ? error.message : 'parse_failed' }
  }

  let nodeCount = 0
  let truncated = false
  let truncateReason: string | undefined
  const truncate = (reason: string) => {
    truncated = true
    truncateReason ||= reason
  }

  const build = (list: any[], depth: number, blockStack: string[]): DxfEntity[] => {
    const result: DxfEntity[] = []
    for (const source of list || []) {
      if (nodeCount >= DRAWING_LIMITS.maxEntities) {
        truncate('maxEntities')
        break
      }
      const type = String(source.type || '').toUpperCase()
      let entity: DxfEntity | undefined
      if (type === 'LINE') {
        entity = {
          type: 'LINE',
          x1: num(source.vertices?.[0]?.x ?? source.startPoint?.x ?? source.x),
          y1: num(source.vertices?.[0]?.y ?? source.startPoint?.y ?? source.y),
          x2: num(source.vertices?.[1]?.x ?? source.endPoint?.x),
          y2: num(source.vertices?.[1]?.y ?? source.endPoint?.y),
        }
      } else if (type === 'CIRCLE') {
        entity = {
          type: 'CIRCLE',
          cx: num(source.center?.x),
          cy: num(source.center?.y),
          r: Math.abs(num(source.radius)),
        }
      } else if (type === 'ARC') {
        entity = {
          type: 'ARC',
          cx: num(source.center?.x),
          cy: num(source.center?.y),
          r: Math.abs(num(source.radius)),
          start: num(source.startAngle),
          end: num(source.endAngle),
        }
      } else if (type === 'POINT') {
        entity = {
          type: 'POINT',
          x: num(source.position?.x ?? source.x),
          y: num(source.position?.y ?? source.y),
        }
      } else if (type === 'LWPOLYLINE' || type === 'POLYLINE') {
        entity = {
          type: 'LWPOLYLINE',
          points: (source.vertices || []).map((vertex: any) => ({ x: num(vertex.x), y: num(vertex.y) })),
          closed: !!source.shape || !!source.closed,
        }
      } else if (type === 'TEXT') {
        entity = {
          type: 'TEXT',
          x: num(source.startPoint?.x ?? source.position?.x),
          y: num(source.startPoint?.y ?? source.position?.y),
          text: String(source.text || ''),
          height: num(source.textHeight || source.height, 1),
        }
      } else if (type === 'MTEXT') {
        entity = {
          type: 'MTEXT',
          x: num(source.position?.x),
          y: num(source.position?.y),
          text: String(source.text || '').replace(/\\[A-Za-z][^;]*;/g, ''),
          height: num(source.height, 1),
        }
      } else if (type === 'ELLIPSE') {
        entity = {
          type: 'ELLIPSE',
          cx: num(source.center?.x),
          cy: num(source.center?.y),
          mx: num(source.majorAxisEndPoint?.x),
          my: num(source.majorAxisEndPoint?.y),
          ratio: Math.abs(num(source.axisRatio, 1)),
          start: num(source.startAngle),
          end: num(source.endAngle, TAU),
        }
      } else if (type === 'INSERT') {
        const name = String(source.name || '')
        const block = dxf?.blocks?.[name]
        const base = block?.position ?? block?.basePoint
        const insert: Extract<DxfEntity, { type: 'INSERT' }> = {
          type: 'INSERT',
          name,
          x: num(source.position?.x),
          y: num(source.position?.y),
          sx: num(source.xScale, 1),
          sy: num(source.yScale, 1),
          rotation: num(source.rotation),
          baseX: num(base?.x),
          baseY: num(base?.y),
          children: [],
        }
        entity = insert
        nodeCount += 1
        result.push(insert)
        if (blockStack.includes(name)) {
          truncate(`insertCycle:${name}`)
        } else if (depth >= DRAWING_LIMITS.maxInsertDepth) {
          truncate('maxInsertDepth')
        } else if (block?.entities) {
          insert.children = build(block.entities, depth + 1, [...blockStack, name])
        }
        continue
      }

      if (entity) {
        nodeCount += 1
        result.push(entity)
      }
    }
    return result
  }

  const entities = build(dxf?.entities || [], 0, [])
  return {
    status: 'ok',
    model: {
      entities,
      bounds: calculateBounds(entities),
      truncated,
      truncateReason,
    },
  }
}
