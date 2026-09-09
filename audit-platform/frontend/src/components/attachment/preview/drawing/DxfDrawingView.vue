<template>
  <div class="gt-dxf-view" data-testid="dxf-drawing-view">
    <svg
      :viewBox="viewBox"
      class="gt-dxf-view__svg"
      xmlns="http://www.w3.org/2000/svg"
    >
      <DxfEntityNode
        v-for="(entity, index) in model.entities"
        :key="index"
        :entity="entity"
      />
    </svg>
    <p v-if="model.truncated" data-testid="dxf-truncated">已截断：{{ model.truncateReason }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, type PropType, type VNodeChild } from 'vue'
import type { DxfEntity, DxfRenderModel } from './dxfModel'

const props = defineProps<{ model: DxfRenderModel }>()

const TAU = Math.PI * 2
const EPSILON = 1e-9
const pad = 10

const viewBox = computed(() => {
  const bounds = props.model.bounds
  const width = Math.max(1, bounds.maxX - bounds.minX)
  const height = Math.max(1, bounds.maxY - bounds.minY)
  return `${bounds.minX - pad} ${-bounds.maxY - pad} ${width + pad * 2} ${height + pad * 2}`
})

function svgNumber(value: number): string {
  const normalized = Math.abs(value) < 1e-12 ? 0 : value
  return String(Math.round(normalized * 1e12) / 1e12)
}

function flip(y: number): number {
  return -y
}

function positiveSweep(start: number, end: number): number {
  const raw = end - start
  const normalized = ((raw % TAU) + TAU) % TAU
  return normalized < EPSILON && Math.abs(raw) > EPSILON ? TAU : normalized
}

function arcPath(cx: number, cy: number, radius: number, start: number, end: number): string {
  const sweep = positiveSweep(start, end)
  const startX = cx + radius * Math.cos(start)
  const startY = flip(cy + radius * Math.sin(start))
  if (sweep >= TAU - EPSILON) {
    const middle = start + Math.PI
    const middleX = cx + radius * Math.cos(middle)
    const middleY = flip(cy + radius * Math.sin(middle))
    return `M ${svgNumber(startX)} ${svgNumber(startY)} A ${svgNumber(radius)} ${svgNumber(radius)} 0 0 0 ${svgNumber(middleX)} ${svgNumber(middleY)} A ${svgNumber(radius)} ${svgNumber(radius)} 0 0 0 ${svgNumber(startX)} ${svgNumber(startY)}`
  }
  const endX = cx + radius * Math.cos(end)
  const endY = flip(cy + radius * Math.sin(end))
  const largeArc = sweep > Math.PI ? 1 : 0
  // CAD 为 Y 向上且角度逆时针；坐标翻转到 SVG 后 sweep 必须为 0。
  return `M ${svgNumber(startX)} ${svgNumber(startY)} A ${svgNumber(radius)} ${svgNumber(radius)} 0 ${largeArc} 0 ${svgNumber(endX)} ${svgNumber(endY)}`
}

function ellipsePoint(entity: Extract<DxfEntity, { type: 'ELLIPSE' }>, parameter: number) {
  const cos = Math.cos(parameter)
  const sin = Math.sin(parameter)
  return {
    x: entity.cx + entity.mx * cos - entity.ratio * entity.my * sin,
    y: entity.cy + entity.my * cos + entity.ratio * entity.mx * sin,
  }
}

function ellipseGeometry(entity: Extract<DxfEntity, { type: 'ELLIPSE' }>) {
  const rx = Math.hypot(entity.mx, entity.my)
  const ry = rx * Math.abs(entity.ratio)
  const sweep = positiveSweep(entity.start, entity.end)
  const full = sweep < EPSILON || sweep >= TAU - EPSILON
  const rotation = (-Math.atan2(entity.my, entity.mx) * 180) / Math.PI
  return { rx, ry, sweep, full, rotation }
}

function ellipseArcPath(entity: Extract<DxfEntity, { type: 'ELLIPSE' }>): string {
  const geometry = ellipseGeometry(entity)
  const start = ellipsePoint(entity, entity.start)
  const end = ellipsePoint(entity, entity.end)
  const largeArc = geometry.sweep > Math.PI ? 1 : 0
  return `M ${svgNumber(start.x)} ${svgNumber(flip(start.y))} A ${svgNumber(geometry.rx)} ${svgNumber(geometry.ry)} ${svgNumber(geometry.rotation)} ${largeArc} 0 ${svgNumber(end.x)} ${svgNumber(flip(end.y))}`
}

function insertTransform(entity: Extract<DxfEntity, { type: 'INSERT' }>): string {
  // F * T * R * S * B * F：把 CAD 变换共轭到已翻转 Y 的 SVG 坐标系。
  return [
    `translate(${svgNumber(entity.x)} ${svgNumber(flip(entity.y))})`,
    `rotate(${svgNumber(-entity.rotation)})`,
    `scale(${svgNumber(entity.sx)} ${svgNumber(entity.sy)})`,
    `translate(${svgNumber(-entity.baseX)} ${svgNumber(entity.baseY)})`,
  ].join(' ')
}

const commonStroke = { stroke: 'currentColor', fill: 'none', 'vector-effect': 'non-scaling-stroke' }

function renderEntity(entity: DxfEntity): VNodeChild {
  if (entity.type === 'LINE') {
    return h('line', {
      'data-dxf-type': 'LINE',
      x1: entity.x1,
      y1: flip(entity.y1),
      x2: entity.x2,
      y2: flip(entity.y2),
      ...commonStroke,
    })
  }
  if (entity.type === 'CIRCLE') {
    return h('circle', {
      'data-dxf-type': 'CIRCLE',
      cx: entity.cx,
      cy: flip(entity.cy),
      r: entity.r,
      ...commonStroke,
    })
  }
  if (entity.type === 'ARC') {
    return h('path', {
      'data-dxf-type': 'ARC',
      d: arcPath(entity.cx, entity.cy, entity.r, entity.start, entity.end),
      ...commonStroke,
    })
  }
  if (entity.type === 'POINT') {
    return h('circle', {
      'data-dxf-type': 'POINT',
      cx: entity.x,
      cy: flip(entity.y),
      r: 1,
      fill: 'currentColor',
    })
  }
  if (entity.type === 'LWPOLYLINE') {
    const points = entity.points.map((point) => `${svgNumber(point.x)},${svgNumber(flip(point.y))}`).join(' ')
    return entity.closed
      ? h('polygon', { 'data-dxf-type': 'LWPOLYLINE', points, ...commonStroke })
      : h('polyline', { 'data-dxf-type': 'LWPOLYLINE', points, ...commonStroke })
  }
  if (entity.type === 'TEXT') {
    return h('text', {
      'data-dxf-type': 'TEXT',
      x: entity.x,
      y: flip(entity.y),
      'font-size': entity.height,
    }, entity.text)
  }
  if (entity.type === 'MTEXT') {
    return h('text', {
      'data-dxf-type': 'MTEXT',
      x: entity.x,
      y: flip(entity.y),
      'font-size': entity.height,
    }, entity.text)
  }
  if (entity.type === 'ELLIPSE') {
    const geometry = ellipseGeometry(entity)
    if (geometry.full) {
      return h('ellipse', {
        'data-dxf-type': 'ELLIPSE',
        cx: entity.cx,
        cy: flip(entity.cy),
        rx: geometry.rx,
        ry: geometry.ry,
        transform: `rotate(${svgNumber(geometry.rotation)} ${svgNumber(entity.cx)} ${svgNumber(flip(entity.cy))})`,
        ...commonStroke,
      })
    }
    return h('path', {
      'data-dxf-type': 'ELLIPSE',
      d: ellipseArcPath(entity),
      ...commonStroke,
    })
  }
  if (entity.type === 'INSERT') {
    return h('g', {
      'data-dxf-type': 'INSERT',
      'data-block-name': entity.name,
      transform: insertTransform(entity),
    }, entity.children.map((child, index) => h(DxfEntityNode, { key: index, entity: child })))
  }
  const exhaustive: never = entity
  return exhaustive
}

const DxfEntityNode = defineComponent({
  name: 'DxfEntityNode',
  props: {
    entity: { type: Object as PropType<DxfEntity>, required: true },
  },
  setup(nodeProps) {
    return () => renderEntity(nodeProps.entity)
  },
})
</script>

<style scoped>
.gt-dxf-view__svg { width: 100%; min-height: 280px; background: #fafafa; }
</style>
