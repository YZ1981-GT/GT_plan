<!--
  G7 处置 / 后续计量「凭证抽查」区块（Task 5.1，共享）。

  G7-10/G7-11/G7-12 是测算表无凭证明细行 → 本区块提供独立的凭证抽查行，
  挂载抽凭引擎（account-code=1511 / phase=final），@filled 按 voucherNo 去重回填。
  自包含持久化（useG7SubFormData，storageKey 由父传入，各表独立）。
-->
<template>
  <el-card shadow="never" class="g7-voucher-sample" :data-testid="`g7-voucher-sample-${storageKey}`">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <template #header>
      <div class="vs-head">
        <span>{{ title }}</span>
        <div class="vs-actions">
          <GtVoucherSamplingEngine
            v-if="!isReadonly && wpId && projectId"
            :project-id="projectId"
            :workpaper-id="wpId"
            :account-code="accountCode"
            phase="final"
            :year="auditYear"
            @filled="onSampleFilled"
          />
          <el-button v-if="!isReadonly" size="small" @click="addRow">+ 新增</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" show-icon class="vs-note"
      title="对处置 / 后续计量相关记账凭证抽查：核对凭证号、日期、借贷金额与对方科目，验证处置损益、股利或权益调整的会计处理。" />

    <el-table :data="rows" border size="small" max-height="360" style="font-size: 13px">
      <el-table-column type="index" label="#" width="45" />
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.voucherDate" size="small" @change="persistRows" />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="业务内容" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persistRows" />
          <span v-else>{{ row.businessContent }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" @change="persistRows" />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" style="width:100%" @change="persistRows" />
          <span v-else>{{ Number(row.debitAmount || 0).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" style="width:100%" @change="persistRows" />
          <span v-else>{{ Number(row.creditAmount || 0).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="检查结论" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="persistRows" />
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persistRows" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="62" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!rows.length" description="点击抽凭引擎抽取处置相关凭证，或手工新增" :image-size="48" />
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import { useG7SubFormData } from '../composables/useG7SubFormData'
import {
  createG7VoucherSampleRow,
  parseG7VoucherSampleRows,
  mergeVoucherSamples,
  type G7VoucherSampleRow,
  type G7VoucherSample,
} from '../composables/g7VoucherSample'
import { G7_GROSS_FALLBACK_STANDARD } from '../composables/g7AccountScope'
import WpSamplingMethodologyBar from '../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist, snapshotToResponseMap } from '../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../composables/shared/samplingFillTarget'

const props = withDefaults(defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  storageKey: string
  auditYear?: number
  accountCode?: string
  title?: string
  htmlData?: Record<string, any> | null
}>(), {
  auditYear: 0,
  accountCode: G7_GROSS_FALLBACK_STANDARD,
  title: '凭证抽查',
  htmlData: null,
})

/** 审计年度：优先 prop，否则从 htmlData.project_context 派生（audit_year → bs_date 年份 → 当前年） */
const auditYear = computed<number>(() => {
  if (props.auditYear) return Number(props.auditYear)
  const ctx = (props.htmlData?.project_context ?? {}) as Record<string, any>
  const y = ctx.audit_year ?? ctx.auditYear
  if (y) return Number(y)
  const bs = ctx.bs_date ?? ctx.bsDate
  if (typeof bs === 'string' && bs.length >= 4) return Number(bs.slice(0, 4))
  return new Date().getFullYear()
})

const rows = ref<G7VoucherSampleRow[]>([])

const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

function parseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function persistRows(): void {
  if (props.isReadonly) return
  formData.debouncedSave(props.storageKey, {
    conclusion: JSON.stringify(rows.value),
    remark: null,
  })
}

function addRow(): void {
  if (props.isReadonly) return
  rows.value.push(createG7VoucherSampleRow(rows.value.length + 1))
  persistRows()
}

function removeRow(index: number): void {
  if (props.isReadonly) return
  rows.value.splice(index, 1)
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

const methodologyStore = ref(snapshotToResponseMap(props.htmlData))
const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
async function methodologyDirectPersist(itemId: string, remark: string) {
  // 无 allResponses 的宿主：写库同时更新本地只读表，供 bar 即时反映
  methodologyStore.value.set(itemId, { remark })
  await rawMethodologyPersist(itemId, remark)
}
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G7',
  allResponses: methodologyStore,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: { samples?: G7VoucherSample[] }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  if (props.isReadonly) return
  const samples = payload?.samples ?? []
  if (!samples.length) {
    ElMessage.info('未收到抽凭样本')
    return
  }
  const { rows: merged, added, skipped } = mergeVoucherSamples(rows.value, samples)
  rows.value = merged
  persistRows()
  ElMessage.success(`已回填 ${added} 笔抽凭样本${skipped ? `（${skipped} 笔凭证号重复已跳过）` : ''}`)
}

onMounted(async () => {
  await formData.load()
  const saved = formData.data.value.get(props.storageKey)
  let loaded = parseG7VoucherSampleRows(parseJson(saved?.conclusion as string | undefined))
  if (!loaded.length) {
    const snapshot = props.htmlData?.responses_snapshot?.[props.storageKey]
    loaded = parseG7VoucherSampleRows(parseJson(snapshot?.conclusion))
  }
  rows.value = loaded
})

defineExpose({ rows, onSampleFilled, mergeVoucherSamples })
</script>

<style scoped>
.g7-voucher-sample { margin-top: 12px; font-size: var(--wp-font-size, 13px); }
.vs-head { display: flex; align-items: center; justify-content: space-between; }
.vs-actions { display: flex; gap: 8px; align-items: center; }
.vs-note { margin-bottom: 10px; }
</style>
