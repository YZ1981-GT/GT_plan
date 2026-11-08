<template>
  <!-- 查询结果顶部信息条（AQF §8.1 QueryRunBanner；data-testid="aqb-result-scope" 由构建器宿主传入） -->
  <div
    v-if="hasContent"
    class="query-run-banner"
    :class="`query-run-banner--${freshnessStatus}`"
    :data-testid="scopeTestId"
  >
    <!-- 范围 -->
    <div v-if="scopeText" class="query-run-banner__scope">
      <span class="query-run-banner__label">范围：</span>{{ scopeText }}
    </div>

    <!-- 版本分量 -->
    <div v-if="components.length" class="query-run-banner__version">
      <span class="query-run-banner__label">数据版本：</span>
      <span
        v-for="comp in components"
        :key="comp.key"
        class="query-run-banner__comp"
        :title="basisLabel(comp.basis) + (comp.latest_update ? `，最近更新：${fmtBeijingTime(comp.latest_update)}` : '')"
      >
        {{ comp.label }}{{ comp.rows != null ? `（${fmtRows(comp.rows)}行）` : '' }}
        <span v-if="comp.weak" class="query-run-banner__weak">弱</span>
      </span>
    </div>

    <!-- 采集时间 -->
    <div v-if="capturedAt" class="query-run-banner__captured">
      <span class="query-run-banner__label">采集时间：</span>{{ fmtBeijingTime(capturedAt) }}
    </div>

    <!-- 时效状态 -->
    <div class="query-run-banner__freshness">
      <span v-if="freshnessStatus === 'current'" class="query-run-banner__status query-run-banner__status--current">
        ✓ {{ currentMessage(isWeak) }}
      </span>
      <span v-else-if="freshnessStatus === 'stale'" class="query-run-banner__status query-run-banner__status--stale">
        ⚠ 数据已过期：{{ staleReasonText }}
        <button class="query-run-banner__btn" @click="$emit('requery')">重新查询</button>
      </span>
      <span v-else-if="freshnessStatus === 'unknown'" class="query-run-banner__status query-run-banner__status--unknown">
        ? 无法判定时效
      </span>
      <span v-else-if="!runId" class="query-run-banner__status query-run-banner__status--unrecorded">
        本次查询未记录，无法判断是否过期
      </span>
    </div>

    <!-- 弱判据提示 -->
    <div v-if="isWeak && freshnessStatus !== 'stale'" class="query-run-banner__weak-note">
      部分来源仅按更新时间判断，未写更新时间的改动可能检测不到
    </div>

    <!-- 操作按钮 -->
    <div class="query-run-banner__actions">
      <button
        v-if="runId && freshnessStatus !== 'stale'"
        class="query-run-banner__btn"
        :disabled="checking"
        @click="$emit('check')"
      >
        {{ checking ? '检查中…' : '检查是否过期' }}
      </button>
      <button class="query-run-banner__btn" @click="$emit('open-drawer')">
        历史与证据
      </button>
    </div>

    <!-- 503 提示 -->
    <div v-if="unavailable" class="query-run-banner__unavailable">
      查询证据功能尚未启用
    </div>

    <!-- 翻页变化提示 -->
    <div v-if="pageChanged" class="query-run-banner__page-changed">
      ⚠ 数据已变化，本页与之前各页可能不一致
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  basisLabel, fmtBeijingTime, fmtRows, currentMessage, staleReason,
} from './queryRunFormat'
import type { VersionComponent, FreshnessResult, RunInfo } from './useQueryRunEvidence'

interface Props {
  runInfo?: RunInfo | null
  version?: { components?: ReadonlyArray<VersionComponent>; weak?: boolean } | null
  capturedAt?: string | null
  freshness?: FreshnessResult | null
  checking?: boolean
  scopeText?: string | null
  scopeTestId?: string
  unavailable?: boolean
  pageChanged?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  runInfo: null,
  version: null,
  capturedAt: null,
  freshness: null,
  checking: false,
  scopeText: null,
  scopeTestId: undefined,
  unavailable: false,
  pageChanged: false,
})

defineEmits<{
  check: []
  requery: []
  'open-drawer': []
}>()

const runId = computed(() => props.runInfo?.id)
const components = computed(() => props.version?.components ?? [])
const isWeak = computed(() => props.version?.weak ?? false)
const freshnessStatus = computed(() => props.freshness?.status ?? (props.runInfo && !props.runInfo?.id ? 'unrecorded' : null))
const staleReasonText = computed(() => staleReason(props.freshness?.changes ?? []))
const hasContent = computed(() =>
  props.scopeText || components.value.length > 0 || props.capturedAt || props.runInfo || props.freshness
    || props.unavailable || props.pageChanged
)
</script>

<style scoped>
.query-run-banner {
  padding: 6px 12px;
  border-radius: 4px;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  font-size: 12px;
  line-height: 1.6;
  color: #495057;
  margin-bottom: 8px;
}
.query-run-banner--stale { background: #fff3cd; border-color: #ffc107; }
.query-run-banner--unknown { background: #e2e3e5; border-color: #adb5bd; }
.query-run-banner__label { font-weight: 500; margin-right: 4px; }
.query-run-banner__comp { margin-right: 8px; }
.query-run-banner__weak { color: #868e96; font-size: 10px; margin-left: 2px; }
.query-run-banner__status--current { color: #198754; }
.query-run-banner__status--stale { color: #856404; }
.query-run-banner__status--unknown { color: #6c757d; }
.query-run-banner__status--unrecorded { color: #6c757d; font-style: italic; }
.query-run-banner__weak-note { color: #6c757d; font-size: 11px; margin-top: 2px; }
.query-run-banner__unavailable { color: #dc3545; font-size: 11px; }
.query-run-banner__page-changed { color: #856404; background: #fff3cd; padding: 2px 6px; border-radius: 3px; margin-top: 4px; }
.query-run-banner__actions { margin-top: 4px; display: flex; gap: 8px; }
.query-run-banner__btn {
  padding: 2px 8px; border-radius: 3px; border: 1px solid #dee2e6;
  background: #fff; cursor: pointer; font-size: 12px; color: #495057;
}
.query-run-banner__btn:hover:not(:disabled) { background: #e9ecef; }
.query-run-banner__btn:disabled { opacity: 0.5; cursor: default; }
.query-run-banner__scope, .query-run-banner__version, .query-run-banner__captured,
.query-run-banner__freshness { margin-bottom: 2px; }
</style>
