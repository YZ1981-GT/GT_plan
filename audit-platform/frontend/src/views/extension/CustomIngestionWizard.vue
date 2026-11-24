<script setup lang="ts">
/**
 * 自定义模板摄取向导（Task 12）—— 三入口 + F-SHELL 门控。
 * candidate 仅静态预览；ACTIVE 后才注册 host facts。
 *
 * 2026-11-24 增：逐 amount region 确认 —— preflight 后从报告读金额列候选，
 * 用户逐列裁决 measureKind / unit（amount）/ ratioScale（ratio），组装
 * manifest.regions 交给 putUnitAuthority；不再手写 regions JSON。
 */
import { computed, ref } from 'vue'
import {
  buildRegionsFromDecisions,
  entrySuccessMessage,
  useCustomIngestionWizard,
  REGION_ALLOWED_KINDS,
  type IngestionEntryKind,
  type PreflightRegionCandidate,
  type RegionDecision,
} from '@/composables/useCustomIngestionWizard'

const wizard = useCustomIngestionWizard()
const entries: { kind: IngestionEntryKind; title: string; desc: string }[] = [
  {
    kind: 'batch_blank',
    title: '批量空白底稿',
    desc: '不上传文件，仅建立批量编制入口；成功 ≠ 发布',
  },
  {
    kind: 'metadata_only',
    title: '仅元数据',
    desc: '登记模板说明，不进入正式摄取 / publication',
  },
  {
    kind: 'ingest_excel',
    title: '摄取 Excel',
    desc: 'multipart 进入隔离区；需 preflight / 审批 / finalize 后才 ACTIVE',
  },
]

/** 逐 region 确认区状态 */
const regionCandidates = ref<PreflightRegionCandidate[]>([])
const regionDecisions = ref<Record<string, RegionDecision>>({})
const regionLoading = ref(false)
const regionError = ref<string | null>(null)
const regionSubmitted = ref(false)

/** 每个 kind 是否还需要更细的选择（amount → unit；ratio → ratioScale）。 */
const KIND_LABELS: Record<string, string> = {
  amount: '金额',
  quantity: '数量',
  count: '计数',
  ratio: '比例',
  exchange_rate: '汇率',
  unit_price: '单价',
  text: '文本',
}

const regionRows = computed(() =>
  regionCandidates.value.map((c) => ({
    ...c,
    decision: regionDecisions.value[c.stableId] ?? null,
  })),
)

const regionDecisionsComplete = computed(
  () => regionCandidates.value.length > 0
    && regionCandidates.value.every((c) => {
      const d = regionDecisions.value[c.stableId]
      if (!d) return false
      if (d.measureKind === 'amount') return !!d.unit
      if (d.measureKind === 'ratio') return !!d.ratioScale
      return true
    }),
)

async function onLoadRegions() {
  regionLoading.value = true
  regionError.value = null
  try {
    const cands = await wizard.loadRegionCandidates()
    regionCandidates.value = cands
    // 默认裁决：amount（最常见的金额列）；用户可逐行改。
    const defaults: Record<string, RegionDecision> = {}
    for (const c of cands) {
      defaults[c.stableId] = { stableId: c.stableId, measureKind: 'amount', unit: 'yuan' }
    }
    regionDecisions.value = defaults
  } finally {
    regionLoading.value = false
  }
}

function setKind(stableId: string, kind: RegionDecision['measureKind']) {
  const prev = regionDecisions.value[stableId]
  regionDecisions.value = {
    ...regionDecisions.value,
    [stableId]: { stableId, measureKind: kind, unit: undefined, ratioScale: undefined },
  }
  void prev
}

function setUnit(stableId: string, unit: 'yuan' | 'qian' | 'wan') {
  const prev = regionDecisions.value[stableId]
  if (!prev) return
  const divisors: Record<string, 1 | 1000 | 10000> = { yuan: 1, qian: 1000, wan: 10000 }
  regionDecisions.value = {
    ...regionDecisions.value,
    [stableId]: { ...prev, unit, divisor: divisors[unit] },
  }
}

function setScale(stableId: string, scale: 'fraction' | 'percent_points') {
  const prev = regionDecisions.value[stableId]
  if (!prev) return
  regionDecisions.value = {
    ...regionDecisions.value,
    [stableId]: { ...prev, ratioScale: scale },
  }
}

/** 组装 manifest 并预览（不直接提交 —— 提交仍走 putUnitAuthority 的既有链）。 */
const builtManifest = computed(() => {
  const decisions = Object.values(regionDecisions.value)
  if (!decisions.length) return null
  const { regions, errors } = buildRegionsFromDecisions(decisions)
  if (errors.length) {
    return { regions, errors }
  }
  return { regions, errors: [] }
})

const statusText = computed(() => {
  const s = wizard.state.value
  if (!wizard.fshell.ok) return 'F-SHELL 门控未通过'
  if (s.phase === 'active') return '已 ACTIVE（可注册 host facts）'
  if (s.phase === 'candidate_preview') return '候选静态预览（禁止生产 OO/WOPI）'
  if (s.phase === 'blocked') return '已阻断'
  if (s.entry) return entrySuccessMessage(s.entry)
  return '请选择入口'
})

function onSelect(kind: IngestionEntryKind) {
  wizard.selectEntry(kind)
  if (kind === 'ingest_excel') {
    wizard.markCandidatePreview()
  }
}
</script>

<template>
  <div class="gt-custom-ingestion-wizard" data-testid="custom-ingestion-wizard">
    <header class="gt-custom-ingestion-wizard__head">
      <h2>自定义模板摄取</h2>
      <p class="gt-custom-ingestion-wizard__status" data-testid="ingestion-status">{{ statusText }}</p>
    </header>

    <div v-if="!wizard.fshell.ok" class="gt-custom-ingestion-wizard__blocked" role="alert">
      <strong>无法启动向导</strong>
      <p>{{ wizard.state.value.blockers[0]?.messageZh }}</p>
    </div>

    <ul v-else class="gt-custom-ingestion-wizard__entries">
      <li v-for="e in entries" :key="e.kind">
        <button
          type="button"
          class="gt-custom-ingestion-wizard__entry"
          :data-testid="`entry-${e.kind}`"
          :aria-pressed="wizard.state.value.entry === e.kind"
          @click="onSelect(e.kind)"
        >
          <strong>{{ e.title }}</strong>
          <span>{{ e.desc }}</span>
        </button>
      </li>
    </ul>

    <section
      v-if="wizard.state.value.phase === 'candidate_preview'"
      class="gt-custom-ingestion-wizard__preview"
      data-testid="static-preview-banner"
    >
      当前为<strong>静态预览</strong>：不生成生产 OnlyOffice / WOPI 配置。
      hostFactsRegistered={{ wizard.state.value.hostFactsRegistered }}
    </section>

    <ul v-if="wizard.state.value.blockers.length" class="gt-custom-ingestion-wizard__blockers">
      <li v-for="b in wizard.state.value.blockers" :key="b.code">
        {{ b.messageZh }}
        <span v-if="b.recoverable">（可恢复）</span>
      </li>
    </ul>

    <!-- 逐 amount region 确认（preflight 后） -->
    <section
      v-if="wizard.state.value.phase === 'preflight'"
      class="gt-custom-ingestion-wizard__regions"
      data-testid="region-confirm-section"
    >
      <h3>金额列确认</h3>
      <p class="gt-custom-ingestion-wizard__region-hint">
        以下是预检报告识别出的数值列候选。请逐列确认它的语义（金额 / 数量 / 比例…）；
        金额列还需选择单位（元 / 千元 / 万元）。扫描器只给候选，不猜单位。
      </p>
      <el-button
        size="small"
        :loading="regionLoading"
        data-testid="region-load"
        @click="onLoadRegions"
      >
        读取金额列候选
      </el-button>

      <div v-if="regionCandidates.length" class="gt-custom-ingestion-wizard__region-list">
        <div
          v-for="row in regionRows"
          :key="row.stableId"
          class="gt-custom-ingestion-wizard__region-row"
          :data-testid="`region-row-${row.stableId}`"
        >
          <span class="gt-custom-ingestion-wizard__region-col">
            <strong>{{ row.sheetName }}</strong>
            {{ row.columnLetter }} 列
            <span v-if="row.header" class="gt-custom-ingestion-wizard__region-header">「{{ row.header }}」</span>
            <span class="gt-custom-ingestion-wizard__region-cells">{{ row.numericCells }} 个数值</span>
          </span>
          <select
            :value="row.decision?.measureKind ?? 'amount'"
            :data-testid="`region-kind-${row.stableId}`"
            :aria-label="`${row.sheetName} ${row.columnLetter} 列语义`"
            @change="setKind(row.stableId, ($event.target as HTMLSelectElement).value as RegionDecision['measureKind'])"
          >
            <option v-for="k in REGION_ALLOWED_KINDS" :key="k" :value="k">{{ KIND_LABELS[k] }}</option>
          </select>
          <select
            v-if="row.decision?.measureKind === 'amount'"
            :value="row.decision?.unit ?? 'yuan'"
            :data-testid="`region-unit-${row.stableId}`"
            :aria-label="`${row.sheetName} ${row.columnLetter} 列单位`"
            @change="setUnit(row.stableId, ($event.target as HTMLSelectElement).value as 'yuan' | 'qian' | 'wan')"
          >
            <option value="yuan">元</option>
            <option value="qian">千元</option>
            <option value="wan">万元</option>
          </select>
          <select
            v-if="row.decision?.measureKind === 'ratio'"
            :value="row.decision?.ratioScale ?? ''"
            :data-testid="`region-scale-${row.stableId}`"
            :aria-label="`${row.sheetName} ${row.columnLetter} 列比例刻度`"
            @change="setScale(row.stableId, ($event.target as HTMLSelectElement).value as 'fraction' | 'percent_points')"
          >
            <option value="" disabled>请选择</option>
            <option value="fraction">小数（0.2 = 20%）</option>
            <option value="percent_points">百分点（20 = 20%）</option>
          </select>
        </div>
      </div>
      <p v-else-if="!regionLoading" class="gt-custom-ingestion-wizard__region-empty">
        预检报告没有数值列候选（可能是纯文本模板）—— 无需确认金额列。
      </p>

      <p
        v-if="builtManifest && builtManifest.errors.length"
        class="gt-custom-ingestion-wizard__region-error"
        data-testid="region-errors"
        role="alert"
      >
        {{ builtManifest.errors.join('；') }}
      </p>
      <p
        v-else-if="builtManifest"
        class="gt-custom-ingestion-wizard__region-ok"
        data-testid="region-summary"
      >
        已确认 {{ builtManifest.regions.length }} 个金额列，可在下一步「确认单位」中提交。
      </p>
    </section>
  </div>
</template>

<style scoped>
.gt-custom-ingestion-wizard {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px;
}
.gt-custom-ingestion-wizard__head h2 {
  margin: 0 0 8px;
  font-size: 1.25rem;
}
.gt-custom-ingestion-wizard__status {
  color: var(--el-text-color-secondary, #666);
  margin: 0 0 16px;
}
.gt-custom-ingestion-wizard__entries {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 12px;
}
.gt-custom-ingestion-wizard__entry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.gt-custom-ingestion-wizard__entry[aria-pressed='true'] {
  border-color: var(--el-color-primary, #4b2d77);
}
.gt-custom-ingestion-wizard__preview {
  margin-top: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.gt-custom-ingestion-wizard__blocked {
  padding: 12px;
  background: #fef0f0;
  color: #c45656;
  border-radius: 6px;
}
.gt-custom-ingestion-wizard__blockers {
  margin-top: 12px;
  color: #c45656;
}
</style>
