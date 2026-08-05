<template>
  <el-alert
    v-if="visible"
    :type="unavailable ? 'error' : 'warning'"
    :closable="false"
    show-icon
    class="drift-alert"
  >
    <template #title>
      <span v-if="unavailable">报表差异检测不可用，本版本不可确认</span>
      <span v-else>
        报表有 {{ diffs.length }} 处数字与按试算表重算的结果不一致，本版本不可确认
      </span>
      <el-tag v-if="!unavailable" size="small" :type="attributionTag" class="drift-alert__tag">
        {{ attributionText }}
      </el-tag>
    </template>

    <div v-if="unavailable" class="drift-alert__body">
      <p class="drift-alert__reason">{{ unavailable }}</p>
      <p class="drift-alert__hint">
        单元格映射配置损坏时无法判定报表是否被改动。为避免把改过的数字确认下来，已阻断本版本；
        请修复映射配置后重新生成报表。
      </p>
    </div>

    <div v-else class="drift-alert__body">
      <el-table :data="diffs" size="small" border class="drift-alert__table">
        <el-table-column prop="row_name" label="报表行" min-width="150" />
        <el-table-column label="位置" min-width="150">
          <template #default="{ row }">{{ row.sheet }}!{{ row.coord }}</template>
        </el-table-column>
        <el-table-column label="期间" width="70">
          <template #default="{ row }">{{ periodLabel(row.period) }}</template>
        </el-table-column>
        <el-table-column label="文件值" min-width="130" align="right">
          <template #default="{ row }">{{ amount(row.file_value) }}</template>
        </el-table-column>
        <el-table-column label="按试算表重算" min-width="130" align="right">
          <template #default="{ row }">{{ amount(row.expected_value) }}</template>
        </el-table-column>
        <el-table-column label="差额" min-width="130" align="right">
          <template #default="{ row }">{{ amount(row.diff) }}</template>
        </el-table-column>
        <el-table-column label="本次编辑引入" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.pre_existing === true" size="small" type="info">编辑前已存在</el-tag>
            <el-tag v-else-if="row.pre_existing === false" size="small" type="danger">是</el-tag>
            <span v-else class="drift-alert__unknown">无基线可比</span>
          </template>
        </el-table-column>
      </el-table>

      <p v-if="preExistingHint" class="drift-alert__hint">{{ preExistingHint }}</p>
      <p v-if="staleHint" class="drift-alert__hint">{{ staleHint }}</p>

      <div class="drift-alert__causes">
        <p class="drift-alert__causes-title">请先确认原因，再决定处置：</p>
        <ol>
          <li>
            <b>上游数据已变更</b>：试算表或调整分录在报表生成后有改动 → 重新生成报表即可。
          </li>
          <li>
            <b>确有手工改动</b>：财务报表数字只能由试算表与调整分录（AJE/RJE）派生 →
            请通过调整分录修正后重新生成，<b>不要直接改 xlsx</b>。
          </li>
          <li>
            <b>单元格映射与模板布局不一致</b>：属配置问题，请联系系统管理员核对
            Cell_Mapping 坐标。
          </li>
        </ol>
      </div>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
/**
 * 报表 xlsx 手工改动差异告警（需求 10.3）。
 *
 * 只呈现事实（哪一行、哪个格、两侧数值、差额）+ 三种可能原因，
 * **不断言「有人改了数字」** —— 真实库实测存在「映射坐标与模板布局不一致」
 * 导致刚生成的报表也报差异的情形，在审计平台里误指控比不告警更坏。
 */
import { computed } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { DeliverableDriftReport, DeliverableDriftDiff } from '@/services/deliverableApi'
import {
  driftAttributionLabel,
  driftAttributionTag,
  driftDiffs,
  driftPeriodLabel,
  shouldShowDriftAlert,
} from './deliverableLineageLabels'

const props = defineProps<{
  /** 最新版本的 drift_report；null / undefined = 未检测或未配映射 */
  report?: DeliverableDriftReport | null
}>()

// 🔴 fmtAmount 是 store 成员，不是模块级导出（memory 平台铁律）。
const displayPrefs = useDisplayPrefsStore()

const unavailable = computed<string | null>(() => props.report?.unavailable ?? null)

const diffs = computed<DeliverableDriftDiff[]>(
  () => driftDiffs(props.report) as unknown as DeliverableDriftDiff[],
)

/** 与后端 should_block_confirm 同口径：`{"diffs": []}` 表示已比对且一致 ⇒ 不告警。 */
const visible = computed(() => shouldShowDriftAlert(props.report))

const attributionText = computed(() => driftAttributionLabel(props.report?.attribution))
const attributionTag = computed(() => driftAttributionTag(props.report?.attribution))

const staleHint = computed(() =>
  props.report?.stale
    ? '该版本绑定的试算表快照已过期（上游数据在生成后发生变更），很可能只需重新生成报表。'
    : '',
)

const preExistingHint = computed(() => {
  if (props.report?.attribution !== 'pre_existing') return ''
  const n = props.report?.pre_existing_count
  return `其中 ${n ?? diffs.value.length} 处在被编辑的上一版就已存在（本次编辑并未改动这些单元格），更可能是单元格映射与模板布局不一致。`
})

function periodLabel(v: string) {
  return driftPeriodLabel(v)
}

function amount(v: string | null | undefined) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return displayPrefs.fmtAmount(n)
}
</script>

<style scoped>
.drift-alert {
  margin-bottom: 12px;
}

.drift-alert__tag {
  margin-left: 8px;
}

.drift-alert__body {
  margin-top: 8px;
  font-size: 13px;
}

.drift-alert__table {
  margin-bottom: 8px;
}

.drift-alert__reason {
  margin: 0 0 6px;
  font-family: var(--el-font-family-monospace, monospace);
}

.drift-alert__hint {
  margin: 0 0 6px;
  color: var(--el-text-color-regular);
}

.drift-alert__causes {
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  padding: 8px 10px;
}

.drift-alert__causes-title {
  margin: 0 0 4px;
  font-weight: 600;
}

.drift-alert__causes ol {
  margin: 0;
  padding-left: 20px;
}

.drift-alert__causes li {
  margin-bottom: 3px;
  line-height: 1.6;
}

.drift-alert__unknown {
  color: var(--el-text-color-placeholder);
}
</style>
