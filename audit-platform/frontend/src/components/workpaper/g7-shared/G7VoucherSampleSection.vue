<!--
  G7 处置 / 后续计量「凭证抽查」区块（Task 5.1，共享）。

  G7-10/G7-11/G7-12 是测算表无凭证明细行 → 本区块提供独立的凭证抽查行，
  挂载抽凭引擎（account-code=1511，阶段取项目当前审计阶段），@filled 经共享回填函数按分录指纹去重回填。
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
            :account-code="effectiveAccountCode"
            :year="auditYear"
            @filled="onSampleFilled"
            @undo-request="vs.onUndoRequest"
          />
          <el-button v-if="!isReadonly" size="small" @click="addRow">+ 新增</el-button>
        </div>
      </div>
    </template>

    <el-alert type="info" :closable="false" show-icon class="vs-note"
      title="对处置 / 后续计量相关记账凭证抽查：核对凭证号、日期、借贷金额与对方科目，验证处置损益、股利或权益调整的会计处理。" />

    <el-table :data="rows" border size="small" max-height="360" style="font-size: 13px" :row-class-name="vs.voucherRowClass">
      <el-table-column type="index" label="#" width="45" />
      <!-- 阶段 / 来源 / 配对（共享回填函数写的行元数据） -->
      <el-table-column label="来源" width="150">
        <template #default="{ row }">
          <VoucherRowMetaCell :row="row" :locked="vs.isVoucherRowLocked(row)" :project-id="projectId" :year="auditYear" />
        </template>
      </el-table-column>
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
          <WpAmountInput v-if="!isReadonly" v-model="row.debitAmount" size="small" style="width:100%" @change="persistRows" />
          <span v-else>{{ Number(row.debitAmount || 0).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" v-model="row.creditAmount" size="small" style="width:100%" @change="persistRows" />
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
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, computed, onMounted, inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import VoucherRowMetaCell from '../voucher-sampling/VoucherRowMetaCell.vue'
import type { EngineFilledPayload } from '../composables/shared/voucherCheckFill'
import { useG7SubFormData } from '../composables/useG7SubFormData'
import { parseG7VoucherSampleRows, useG7VoucherSampleRows } from '../composables/g7VoucherSample'
import { gCycleScope } from '../composables/gCycleAccountScope'
import type { TbSourceCodes } from '../composables/shared/tbSourceCodes'
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
  accountCode: undefined,
  title: '凭证抽查',
  htmlData: null,
})

// 科目映射码：优先从上层 provide 注入的 tb_source_codes 取映射后的真实码，未注入时退兜底码
const _injectedTbSrc = inject<Ref<TbSourceCodes | null> | null>('tbSourceCodes', null)
/** 实际使用的 account-code：prop 优先，否则走 inject → gCycleScope('G7') → 兜底 */
const effectiveAccountCode = computed(() =>
  props.accountCode ?? gCycleScope('G7')!.queryCodes(_injectedTbSrc?.value ?? null, 'gross').join(','),
)

const auditYear = computed<number | null>(() => {
  if (props.auditYear) return Number(props.auditYear)
  const ctx = (props.htmlData?.project_context ?? {}) as Record<string, any>
  const y = ctx.audit_year ?? ctx.auditYear
  if (y) return Number(y)
  const bs = ctx.bs_date ?? ctx.bsDate
  if (typeof bs === 'string' && bs.length >= 4) return Number(bs.slice(0, 4))
  return null
})

const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

function parseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

// 行、增删、保存与抽凭回填 / 撤销 / 年审阶段预审行只读（共享回填函数，见 g7VoucherSample.useG7VoucherSampleRows）
const vs = useG7VoucherSampleRows({
  projectId: () => props.projectId,
  readonly: () => props.isReadonly,
  save: (json) => formData.debouncedSave(props.storageKey, { conclusion: json, remark: null }),
})
const rows = vs.rows
const persistRows = vs.persist
const addRow = vs.addRow
const removeRow = vs.removeRow

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

/** 抽凭引擎回填：共享回填函数一个对方科目一行（后端配对），按分录指纹去重，填完由它保存并提示填入几行 */
async function onSampleFilled(payload: EngineFilledPayload & { methodology?: SamplingMethodologySnapshot }): Promise<void> {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology(payload?.methodology)

  if (props.isReadonly) return
  if (!payload?.samples?.length) {
    ElMessage.info('未收到抽凭样本')
    return
  }
  await vs.onEngineFilled(payload)
}

onMounted(async () => {
  void vs.voucherFillReady()
  await formData.load()
  const saved = formData.data.value.get(props.storageKey)
  let payload = parseJson(saved?.conclusion as string | undefined)
  if (!parseG7VoucherSampleRows(payload).length) {
    const snapshot = props.htmlData?.responses_snapshot?.[props.storageKey]
    payload = parseJson(snapshot?.conclusion)
  }
  vs.load(payload)
})

defineExpose({ rows, onSampleFilled })
</script>

<style scoped>
.g7-voucher-sample { margin-top: 12px; font-size: var(--wp-font-size, 13px); }
.vs-head { display: flex; align-items: center; justify-content: space-between; }
.vs-actions { display: flex; gap: 8px; align-items: center; }
.vs-note { margin-bottom: 10px; }
</style>
