<template>
  <el-collapse
    v-if="hasContent"
    v-model="active"
    class="llm-reasoning-panel"
  >
    <el-collapse-item :name="paneName">
      <template #title>
        <span class="reasoning-title">
          🔍 推理依据
          <el-tag
            v-if="confidenceLabel"
            size="small"
            :type="confidenceTagType"
            effect="plain"
            style="margin-left: 8px"
          >置信度 {{ confidenceLabel }}</el-tag>
          <span v-if="referenceCount" class="meta">· 引用 {{ referenceCount }} 项</span>
          <span v-if="dataSourceCount" class="meta">· 数据 {{ dataSourceCount }} 处</span>
        </span>
      </template>

      <div v-if="reasoning" class="reasoning-section">
        <div class="section-label">推理过程</div>
        <div class="reasoning-text">{{ reasoning }}</div>
      </div>

      <div v-if="references && references.length" class="reasoning-section">
        <div class="section-label">引用来源（准则 / 案例）</div>
        <ul class="reference-list">
          <li v-for="(ref, idx) in references" :key="idx">
            <el-tag size="small" type="warning" effect="plain">{{ ref.type || 'REF' }}</el-tag>
            <span class="ref-code">{{ ref.code }}</span>
            <span v-if="ref.section" class="ref-section">— {{ ref.section }}</span>
          </li>
        </ul>
      </div>

      <div v-if="dataSources && dataSources.length" class="reasoning-section">
        <div class="section-label">数据来源</div>
        <div class="datasource-tags">
          <el-tag
            v-for="(d, idx) in dataSources"
            :key="idx"
            size="small"
            type="info"
            effect="plain"
            style="margin: 2px 4px 2px 0"
          >{{ d }}</el-tag>
        </div>
      </div>

      <div v-if="confidence !== undefined && confidence !== null" class="reasoning-section">
        <div class="section-label">置信度</div>
        <el-progress
          :percentage="confidencePercent"
          :stroke-width="10"
          :color="confidenceColor"
          style="max-width: 320px"
        />
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface ReferenceItem {
  type?: string
  code?: string
  section?: string
}

interface Props {
  reasoning?: string | null
  references?: ReferenceItem[] | null
  dataSources?: string[] | null
  confidence?: number | null
  /** el-collapse-item name；多 dialog 共用时可避免冲突 */
  paneName?: string
  /** 默认折叠（false）/ 展开（true） */
  defaultOpen?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  reasoning: null,
  references: () => [],
  dataSources: () => [],
  confidence: 0,
  paneName: 'llm-reasoning',
  defaultOpen: false,
})

const active = ref<string[]>(props.defaultOpen ? [props.paneName] : [])

const hasContent = computed(() => {
  return Boolean(
    props.reasoning ||
      (props.references && props.references.length) ||
      (props.dataSources && props.dataSources.length) ||
      (typeof props.confidence === 'number' && props.confidence > 0),
  )
})

const referenceCount = computed(() => props.references?.length || 0)
const dataSourceCount = computed(() => props.dataSources?.length || 0)

const confidencePercent = computed(() => {
  const c = typeof props.confidence === 'number' ? props.confidence : 0
  return Math.round(Math.max(0, Math.min(1, c)) * 100)
})

const confidenceLabel = computed(() => {
  if (typeof props.confidence !== 'number' || props.confidence <= 0) return ''
  return `${confidencePercent.value}%`
})

const confidenceTagType = computed<'success' | 'warning' | 'info'>(() => {
  const c = typeof props.confidence === 'number' ? props.confidence : 0
  if (c >= 0.8) return 'success'
  if (c >= 0.5) return 'warning'
  return 'info'
})

const confidenceColor = computed(() => {
  const c = typeof props.confidence === 'number' ? props.confidence : 0
  if (c >= 0.8) return '#67C23A'
  if (c >= 0.5) return '#E6A23C'
  return '#909399'
})
</script>

<style scoped>
.llm-reasoning-panel {
  margin: 12px 0 4px;
  border-top: 1px dashed var(--el-border-color-lighter, #e4e7ed);
}

.reasoning-title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.meta {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
}

.reasoning-section {
  margin: 8px 0 12px;
}

.section-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  font-weight: 500;
}

.reasoning-text {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  background-color: var(--el-fill-color-lighter, #f5f7fa);
  padding: 8px 12px;
  border-radius: 4px;
}

.reference-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.reference-list li {
  padding: 4px 0;
  font-size: 13px;
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.ref-code {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ref-section {
  color: var(--el-text-color-secondary);
}

.datasource-tags {
  display: flex;
  flex-wrap: wrap;
}
</style>
