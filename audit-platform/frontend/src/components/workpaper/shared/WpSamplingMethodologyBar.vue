<!--
  WpSamplingMethodologyBar — 底稿正文上的抽样方法学只读条（sampling-compliance-closure R6.2）

  为什么需要它：抽样方法学此前只存在于 `workpaper_extraction_log` 与抽凭弹窗里，
  而**复核与归档看的是底稿正文**。42 个宿主连 `filled` 载荷里的 methodology 都丢掉了，
  底稿上看不出"这批样本是怎么抽出来的"。

  形态遵循平台铁律：紧凑单行 bar（不用空洞 el-card）、13px、金额走 displayPrefs.fmtAmount。
  `methodology` 无内容时整条不渲染（Property 17）。
-->
<template>
  <div v-if="visible" class="wp-sampling-methodology-bar">
    <span class="msb-title">抽样方法学</span>

    <el-tag size="small" type="primary" effect="plain">
      {{ methodLabel }}
    </el-tag>

    <span v-if="accountText" class="msb-item">
      <span class="msb-label">科目</span>{{ accountText }}
    </span>

    <span class="msb-item">
      <span class="msb-label">样本量</span>{{ sampleSize }}
      <span v-if="suggestedText" class="msb-sub">（系统建议 {{ suggestedText }}）</span>
    </span>

    <span v-if="intervalText" class="msb-item">
      <span class="msb-label">抽样间隔</span>{{ intervalText }}
    </span>

    <span v-if="tolerableText" class="msb-item">
      <span class="msb-label">可容忍错报</span>{{ tolerableText }}
    </span>

    <span v-if="confidenceText" class="msb-item">
      <span class="msb-label">置信度</span>{{ confidenceText }}
    </span>

    <el-tooltip
      v-if="seedText"
      content="随机种子：与账套版本一并决定抽样可否复算"
      placement="top"
    >
      <span class="msb-item msb-item--mono">
        <span class="msb-label">种子</span>{{ seedText }}
      </span>
    </el-tooltip>

    <el-tooltip v-if="batchText" :content="`抽凭批次 ${methodology!.batchId}`" placement="top">
      <span class="msb-item msb-item--mono">
        <span class="msb-label">批次</span>{{ batchText }}
      </span>
    </el-tooltip>

    <el-tooltip
      v-if="datasetText"
      :content="`抽样框账套版本 ${methodology!.datasetId}；该版本被替换后，以相同种子重跑不会得到相同样本`"
      placement="top"
    >
      <span class="msb-item msb-item--mono">
        <span class="msb-label">账套版本</span>{{ datasetText }}
      </span>
    </el-tooltip>

    <el-tag v-else size="small" type="info" effect="plain" class="msb-warn">
      未绑定账套版本
    </el-tag>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import {
  hasMethodologyContent,
  samplingMethodLabel,
  type SamplingMethodologySnapshot,
} from '../composables/shared/samplingFillTarget'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  methodology: SamplingMethodologySnapshot | null | undefined
}>()

// 🔴 fmtAmount 是 store 成员，不是 '@/stores/displayPrefs' 的模块级导出。
// 必须在 setup 顶层取 store（写进函数体会静默失效），否则整页崩成
// 「does not provide an export named 'fmtAmount'」。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const visible = computed(() => hasMethodologyContent(props.methodology))

const methodLabel = computed(() => samplingMethodLabel(props.methodology?.samplingMethod))

const accountText = computed(() => (props.methodology?.accountCodes ?? []).join('、'))

const sampleSize = computed(() => Number(props.methodology?.sampleSize) || 0)

const suggestedText = computed(() => {
  const v = props.methodology?.suggestedSampleSize
  return v === null || v === undefined || v === '' ? '' : String(v)
})

function fmtMoney(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return displayPrefs.fmtAmount(n)
}

const intervalText = computed(() => fmtMoney(props.methodology?.samplingInterval))
const tolerableText = computed(() => fmtMoney(props.methodology?.tolerableMisstatement))

const confidenceText = computed(() => {
  const v = props.methodology?.confidenceLevel
  if (v === null || v === undefined) return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  // 0.95 → 95%；已是百分数形式（95）时原样加 %
  return n <= 1 ? `${(n * 100).toFixed(0)}%` : `${n}%`
})

const seedText = computed(() => {
  const v = props.methodology?.randomSeed
  return v === null || v === undefined || v === '' ? '' : String(v)
})

const batchText = computed(() => {
  const v = props.methodology?.batchId
  return v ? String(v).slice(0, 8) : ''
})

const datasetText = computed(() => {
  const v = props.methodology?.datasetId
  return v ? String(v).slice(0, 8) : ''
})
</script>

<style scoped>
.wp-sampling-methodology-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 6px 10px;
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.6;
  background: var(--el-fill-color-lighter);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 3px;
  color: var(--el-text-color-regular);
}

.msb-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.msb-item {
  white-space: nowrap;
}

.msb-item--mono {
  font-variant-numeric: tabular-nums;
  cursor: help;
}

.msb-label {
  margin-right: 4px;
  color: var(--el-text-color-secondary);
}

.msb-sub {
  color: var(--el-text-color-secondary);
}

.msb-warn {
  margin-left: auto;
}
</style>
