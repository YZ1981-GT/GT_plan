<!--
  GtAuditFlowGraph.vue — 审计逻辑流程图（阶段泳道横向）

  当后端 audit-flow-graph API 有数据时用服务端数据，
  否则从 programs prop 按阶段分组生成本地 fallback 图。
  4 阶段横向泳道：计划 → 执行 → 完成 → 复核归档。
  每个程序节点显示序号+简称+关联底稿 chip。
-->

<template>
  <div class="gt-audit-flow" v-show="expanded">
    <div v-if="stages.length" class="gt-audit-flow__stages">
      <div
        v-for="(stage, si) in stages"
        :key="si"
        class="gt-audit-flow__stage"
      >
        <!-- 阶段头 -->
        <div class="gt-audit-flow__stage-header" :style="{ borderColor: stageColors[si] }">
          <span class="gt-audit-flow__stage-icon">{{ stageIcons[si] }}</span>
          <span class="gt-audit-flow__stage-name">{{ stage.name }}</span>
          <span class="gt-audit-flow__stage-count">{{ stage.items.length }}项</span>
        </div>
        <!-- 程序节点横向排列 -->
        <div class="gt-audit-flow__items">
          <div
            v-for="item in stage.items"
            :key="item.program_no"
            class="gt-audit-flow__item"
            :class="`gt-audit-flow__item--${item.status}`"
            @click="scrollToProgram(item.program_no)"
            :title="item.full_desc"
          >
            <span class="gt-audit-flow__item-no">{{ item.program_no }}</span>
            <span class="gt-audit-flow__item-text">{{ item.short_desc }}</span>
            <div v-if="item.refs.length" class="gt-audit-flow__item-refs">
              <GtIndexChip
                v-for="(ref, ri) in item.refs"
                :key="ri"
                :value="ref"
                :validate="true"
              />
            </div>
          </div>
        </div>
      </div>
      <!-- 阶段间连接箭头 -->
      <div class="gt-audit-flow__arrows">
        <span v-for="i in stages.length - 1" :key="i" class="gt-audit-flow__arrow">→</span>
      </div>
    </div>
    <div v-else class="gt-audit-flow__empty">
      <el-empty description="暂无审计逻辑图数据" :image-size="50" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  expanded: boolean
  programs?: Array<{ program_no: number; program_desc: string; linked_workpapers?: string; status: string }>
}>()

const emit = defineEmits<{
  'scroll-to-program': [programNo: number]
}>()

interface StageData {
  name: string
  items: Array<{ program_no: number; short_desc: string; full_desc: string; status: string; refs: string[] }>
}

const stageColors = ['#4b2d77', '#0094B3', '#28A745', '#FFC23D']
const stageIcons = ['📋', '🔍', '✅', '🔒']

const STAGE_RANGES: Array<{ name: string; range: [number, number] }> = [
  { name: '计划与风险评估', range: [1, 3] },
  { name: '执行审计程序', range: [4, 5] },
  { name: '完成阶段', range: [6, 14] },
  { name: '复核与归档', range: [15, 99] },
]

const stages = ref<StageData[]>([])

function parseLinkedRefs(value: string): string[] {
  if (!value) return []
  const parts = value.split(/[/,;、，；\n]/).map(s => s.trim()).filter(Boolean)
  const out: string[] = []
  for (const token of parts) {
    const m = token.match(/^([A-Z]\d+)-(\d+)\s*(?:到|至|~|～|-)\s*(?:([A-Z]\d+)-)?(\d+)$/i)
    if (m) {
      const base1 = (m[1] || '').toUpperCase()
      const start = Number(m[2])
      const base2 = (m[3] || base1).toUpperCase()
      const end = Number(m[4])
      if (base1 === base2 && Number.isFinite(start) && Number.isFinite(end) && end >= start && end - start <= 50) {
        for (let i = start; i <= end; i += 1) out.push(`${base1}-${i}`)
        continue
      }
    }
    out.push(token)
  }
  return out.filter((v, i) => out.indexOf(v) === i)
}

function buildStages() {
  const progs = props.programs || []
  if (!progs.length) { stages.value = []; return }

  stages.value = STAGE_RANGES.map(s => {
    const items = progs
      .filter(p => p.program_no >= s.range[0] && p.program_no <= s.range[1])
      .map(p => ({
        program_no: p.program_no,
        short_desc: (p.program_desc || '').replace(/ — .*$/, '').slice(0, 14),
        full_desc: p.program_desc || '',
        status: p.status || 'pending',
        refs: parseLinkedRefs(p.linked_workpapers || ''),
      }))
    return { name: s.name, items }
  }).filter(s => s.items.length > 0)
}

function scrollToProgram(no: number) {
  emit('scroll-to-program', no)
}

async function tryLoadFromApi() {
  try {
    const data = await api.get<any>(`/api/workpapers/${props.wpId}/audit-flow-graph`)
    if (data?.procedures?.length) {
      // 服务端有数据则不用本地 fallback（未来可扩展）
    }
  } catch { /* 静默 */ }
  buildStages()
}

onMounted(() => { if (props.expanded) tryLoadFromApi() })
watch(() => props.expanded, v => { if (v) buildStages() })
watch(() => props.programs, () => { if (props.expanded) buildStages() }, { deep: true })
</script>

<style scoped>
.gt-audit-flow {
  margin-bottom: 12px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 8px;
}

.gt-audit-flow__stages {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  overflow-x: auto;
  position: relative;
}

.gt-audit-flow__stage {
  flex: 1;
  min-width: 180px;
  background: var(--gt-bg-default, #fff);
  border-radius: 8px;
  border: 1px solid var(--gt-color-border, #e5e5ea);
  overflow: hidden;
}

.gt-audit-flow__stage-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: var(--gt-bg-subtle, #f5f7fa);
  border-bottom: 2px solid;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-audit-flow__stage-icon { font-size: 14px; }
.gt-audit-flow__stage-name { flex: 1; }
.gt-audit-flow__stage-count {
  font-size: 11px;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 400;
}

.gt-audit-flow__items {
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
}

.gt-audit-flow__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
  flex-wrap: wrap;
}
.gt-audit-flow__item:hover { background: var(--gt-color-primary-bg, #f4f0fa); }

.gt-audit-flow__item--completed { color: #28A745; }
.gt-audit-flow__item--in_progress { color: #d48806; }
.gt-audit-flow__item--pending { color: var(--gt-color-text-regular, #606266); }
.gt-audit-flow__item--not_applicable { color: #999; text-decoration: line-through; }

.gt-audit-flow__item-no {
  font-weight: 700;
  min-width: 18px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-audit-flow__item-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-audit-flow__item-refs {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
}

.gt-audit-flow__arrows {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-around;
  pointer-events: none;
  transform: translateY(-50%);
  z-index: 0;
  opacity: 0;
}
.gt-audit-flow__arrow {
  font-size: 20px;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-audit-flow__empty { text-align: center; padding: 16px; }
</style>
