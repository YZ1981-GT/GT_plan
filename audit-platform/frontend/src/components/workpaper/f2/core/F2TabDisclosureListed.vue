<script setup lang="ts">
/** F2TabDisclosureListed — 附注披露（上市），对齐源模板结构 */
import { ref, toRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useF2DisclosureListed } from '../../composables/useF2DisclosureListed'
import {
  buildF2ListedSubTableData,
  buildF2SyncPayload,
} from '../../composables/f2DisclosureSyncPayload'
import { F2_NOTE_SECTION } from '../../composables/f2NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  applicableStandards: string[]
}>()

function fmtAmount(v: number): string {
  return !v ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(ratio: number): string {
  if (!ratio) return '-'
  return `${(ratio * 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

const {
  isApplicable,
  section1Rows, section1Total,
  section2Rows, section2Total, section2QualRows,
  s3EndRows, s3EndTotal, s3PriorRows, s3PriorTotal,
  s5Rows, s5Total, s6Rows, s6Total, s7Rows, s7Total,
  noteCategory, noteNrv, noteProvision, s4BorrowText, noteRe,
  dataUpdatedVisible,
  updateS2Field, updateQualField,
  updateS3Row, addS3Row, removeS3Row,
  updateS5, updateS6, updateS7,
  addS5, addS6, addS7, removeS5, removeS6, removeS7,
  getSyncSnapshot,
} = useF2DisclosureListed({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

const isSyncing = ref(false)
const noteSectionId = F2_NOTE_SECTION.listed

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'F2', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildF2SyncPayload(
    'listed',
    props.wpId,
    props.applicableStandards,
    buildF2ListedSubTableData(getSyncSnapshot()),
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市公司附注同步')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${noteSectionId} 存货」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<template>
  <div class="f2-disclosure-listed">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />

    <template v-else>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. （1）存货分类：账面余额 / 跌价准备 / 账面价值 × 期末与上年年末，自 F2-1 审定表跨 sheet 取数（只读）。</p>
          <p>2. （2）跌价准备变动：期初/计提默认取自 F2-1；期末=期初+计提+其他−转回或转销−其他，应与（1）期末跌价勾稽。</p>
          <p>3. （3）按组合计提：比例分母为 0 时显示「-」，避免除零错误；房企另填（5）～（7）。</p>
          <p>4. 可「同步到附注」推送至附注模块「{{ noteSectionId }} 存货」。</p>
        </div>
      </details>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="objective-alert"
        title="审计目标：核实上市公司存货附注披露的分类、账面价值与跌价准备完整准确，确保与 F2-1 及财务报表列报一致。"
      />

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" plain :loading="isSyncing" :disabled="isReadonly" @click="syncToDisclosureNotes">
            同步到附注
          </el-button>
          <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        </div>
        <div class="toolbar-right">
          <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
          <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        </div>
      </div>

      <el-alert
        v-if="dataUpdatedVisible"
        type="info"
        title="审定表数据已更新，附注分类/跌价变动已自动刷新"
        :closable="false"
        show-icon
        class="update-bar"
      />

      <!-- (1) 存货分类 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 存货分类
          <el-tooltip content="数据来源：F2-1 审定表原值/跌价准备审定数" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Total]" size="small" border stripe style="width:100%">
          <el-table-column prop="label" label="存货种类" min-width="140" fixed>
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowKey === '__total__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.endGross) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="跌价准备/合同履约成本减值准备" min-width="150" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.endImpairment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.endNet) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="上年年末数" align="center">
            <el-table-column label="账面余额" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.priorGross) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="跌价准备/合同履约成本减值准备" min-width="150" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.priorImpairment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.priorNet) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
        <p class="hint-text">注：根据企业具体情况分类，房地产开发企业应增加「开发成本」「开发产品」等种类（见下方（5）～（7））。</p>
        <div class="note-block">
          <div class="note-label">分类说明</div>
          <el-input v-model="noteCategory" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly" placeholder="存货分类补充说明..." />
        </div>
      </div>

      <!-- (2) 跌价准备变动 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 存货跌价准备及合同履约成本减值准备
          <el-tooltip content="期初/计提默认取自 F2-1；期末公式勾稽（1）期末跌价" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
        </h4>
        <el-alert
          v-if="Math.abs(section2Total.tieDiff) >= 0.01"
          type="warning"
          :closable="false"
          show-icon
          class="tie-alert"
          :title="`跌价准备合计勾稽差异 ${fmtAmount(section2Total.tieDiff)}（变动表期末 − 分类表期末跌价）`"
        />
        <el-table :data="[...section2Rows, section2Total]" size="small" border stripe style="width:100%">
          <el-table-column prop="label" label="存货种类" min-width="130" fixed>
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowKey === '__total__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.opening) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="计提" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.incProvision) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.incProvision"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'incProvision', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="其他" min-width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.incOther) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.incOther"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'incOther', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="本期减少" align="center">
            <el-table-column label="转回或转销" min-width="120" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decReversal) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decReversal"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decReversal', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="其他" min-width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decOther) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decOther"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decOther', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末余额" min-width="110" align="right">
            <template #default="{ row }">
              <span :class="{ 'tie-warn': Math.abs(row.tieDiff) >= 0.01, 'subtotal-label': row.rowKey === '__total__' }">
                {{ fmtAmount(row.ending) }}
              </span>
            </template>
          </el-table-column>
        </el-table>

        <h4 class="card-title sub">存货跌价准备及合同履约成本减值准备（续）</h4>
        <el-table :data="section2QualRows" size="small" border stripe style="width:100%">
          <el-table-column prop="label" label="存货种类" min-width="120" />
          <el-table-column label="确定可变现净值/剩余对价与将要发生的成本的具体依据" min-width="240">
            <template #default="{ row }">
              <el-input
                :model-value="row.nrvBasis"
                size="small"
                :disabled="isReadonly"
                placeholder="NRV 确定依据"
                @change="(v: string) => updateQualField(row.rowKey, 'nrvBasis', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期转回或转销存货跌价准备/合同履约成本减值准备的原因" min-width="240">
            <template #default="{ row }">
              <el-input
                :model-value="row.reversalReason"
                size="small"
                :disabled="isReadonly"
                placeholder="转回/转销原因"
                @change="(v: string) => updateQualField(row.rowKey, 'reversalReason', v)"
              />
            </template>
          </el-table-column>
        </el-table>
        <p class="hint-text">【披露确定可变现净值的具体依据及本期转回或转销存货跌价准备的原因。】</p>
        <div class="note-block">
          <div class="note-label">NRV / 跌价政策说明</div>
          <el-input v-model="noteNrv" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="可变现净值确定方法..." />
          <el-input v-model="noteProvision" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" class="mt-8" placeholder="跌价准备计提政策说明..." />
        </div>
      </div>

      <!-- (3) 按组合计提 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (3) 按组合计提存货跌价准备
          <el-button size="small" :disabled="isReadonly" @click="addS3Row('end')">+ 期末组合</el-button>
        </h4>
        <p class="hint-text">15号文第十九条（六）：按组合计提的，应分类披露不同组合存货的期初/期末余额及跌价准备、计提标准和比例。</p>
        <h5 class="sub-title">期末余额</h5>
        <el-table :data="[...s3EndRows, s3EndTotal]" size="small" border stripe style="width:100%">
          <el-table-column label="组合" min-width="140">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">合计</span>
              <el-input
                v-else
                :model-value="row.groupName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateS3Row('end', row.rowId, 'groupName', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.balance) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.balance"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS3Row('end', row.rowId, 'balance', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" min-width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.balancePct) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="存货跌价准备" align="center">
            <el-table-column label="金额" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.impairment) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.impairment"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS3Row('end', row.rowId, 'impairment', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="计提标准" min-width="120">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" />
                <el-input
                  v-else
                  :model-value="row.provisionStandard"
                  size="small"
                  :disabled="isReadonly"
                  @change="(v: string) => updateS3Row('end', row.rowId, 'provisionStandard', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" min-width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.impairmentPct) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="账面价值" min-width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.netValue) }}</template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" size="small" type="danger" link @click="removeS3Row('end', row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>

        <h5 class="sub-title">
          上年年末余额
          <el-button size="small" :disabled="isReadonly" @click="addS3Row('prior')">+ 上年组合</el-button>
        </h5>
        <el-table :data="[...s3PriorRows, s3PriorTotal]" size="small" border stripe style="width:100%">
          <el-table-column label="组合" min-width="140">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">合计</span>
              <el-input
                v-else
                :model-value="row.groupName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateS3Row('prior', row.rowId, 'groupName', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.balance) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.balance"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS3Row('prior', row.rowId, 'balance', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" min-width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.balancePct) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="存货跌价准备" align="center">
            <el-table-column label="金额" min-width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.impairment) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.impairment"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS3Row('prior', row.rowId, 'impairment', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="计提标准" min-width="120">
              <template #default="{ row }">
                <span v-if="row.rowId === '__total__'" />
                <el-input
                  v-else
                  :model-value="row.provisionStandard"
                  size="small"
                  :disabled="isReadonly"
                  @change="(v: string) => updateS3Row('prior', row.rowId, 'provisionStandard', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" min-width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.impairmentPct) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="账面价值" min-width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.netValue) }}</template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" size="small" type="danger" link @click="removeS3Row('prior', row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="note-block">
          <div class="note-label">（4）借款费用资本化说明</div>
          <el-input v-model="s4BorrowText" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly" placeholder="存货期末余额中含有的借款费用资本化金额及其计算标准和依据..." />
        </div>
      </div>

      <!-- (5) 开发成本 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (5) 开发成本
          <el-button size="small" :disabled="isReadonly" @click="addS5">+ 添加</el-button>
        </h4>
        <el-table :data="[...s5Rows, s5Total]" size="small" border stripe style="width:100%">
          <el-table-column label="项目名称" min-width="140">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">合计</span>
              <el-input v-else :model-value="row.projectName" size="small" :disabled="isReadonly" @change="(v: string) => updateS5(row.rowId, 'projectName', v)" />
            </template>
          </el-table-column>
          <el-table-column label="开工时间" min-width="120">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" />
              <el-input v-else :model-value="row.startDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="(v: string) => updateS5(row.rowId, 'startDate', v)" />
            </template>
          </el-table-column>
          <el-table-column label="预计竣工时间" min-width="120">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" />
              <el-input v-else :model-value="row.expectedCompleteDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="(v: string) => updateS5(row.rowId, 'expectedCompleteDate', v)" />
            </template>
          </el-table-column>
          <el-table-column label="预计总投资" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.estimatedInvestment) }}</span>
              <el-input-number v-else :model-value="row.estimatedInvestment" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS5(row.rowId, 'estimatedInvestment', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末数" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.endBalance) }}</span>
              <el-input-number v-else :model-value="row.endBalance" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS5(row.rowId, 'endBalance', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="上年年末数" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.priorBalance) }}</span>
              <el-input-number v-else :model-value="row.priorBalance" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS5(row.rowId, 'priorBalance', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末跌价准备" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.endImpairment) }}</span>
              <el-input-number v-else :model-value="row.endImpairment" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS5(row.rowId, 'endImpairment', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" size="small" type="danger" link @click="removeS5(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- (6) 开发产品 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (6) 开发产品
          <el-button size="small" :disabled="isReadonly" @click="addS6">+ 添加</el-button>
        </h4>
        <el-table :data="[...s6Rows, s6Total]" size="small" border stripe style="width:100%">
          <el-table-column label="项目名称" min-width="140">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">合计</span>
              <el-input v-else :model-value="row.projectName" size="small" :disabled="isReadonly" @change="(v: string) => updateS6(row.rowId, 'projectName', v)" />
            </template>
          </el-table-column>
          <el-table-column label="竣工时间" min-width="120">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" />
              <el-input v-else :model-value="row.completeDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="(v: string) => updateS6(row.rowId, 'completeDate', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.opening) }}</span>
              <el-input-number v-else :model-value="row.opening" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS6(row.rowId, 'opening', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.increase) }}</span>
              <el-input-number v-else :model-value="row.increase" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS6(row.rowId, 'increase', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.decrease) }}</span>
              <el-input-number v-else :model-value="row.decrease" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS6(row.rowId, 'decrease', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" min-width="100" align="right">
            <template #default="{ row }">
              <span class="subtotal-label">{{ fmtAmount(row.ending) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末跌价准备" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.endImpairment) }}</span>
              <el-input-number v-else :model-value="row.endImpairment" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS6(row.rowId, 'endImpairment', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" size="small" type="danger" link @click="removeS6(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- (7) 周转房 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (7) 周转房
          <el-button size="small" :disabled="isReadonly" @click="addS7">+ 添加</el-button>
        </h4>
        <el-table :data="[...s7Rows, s7Total]" size="small" border stripe style="width:100%">
          <el-table-column label="项目名称" min-width="160">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">合计</span>
              <el-input v-else :model-value="row.projectName" size="small" :disabled="isReadonly" @change="(v: string) => updateS7(row.rowId, 'projectName', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.opening) }}</span>
              <el-input-number v-else :model-value="row.opening" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS7(row.rowId, 'opening', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.increase) }}</span>
              <el-input-number v-else :model-value="row.increase" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS7(row.rowId, 'increase', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="110" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="subtotal-label">{{ fmtAmount(row.decrease) }}</span>
              <el-input-number v-else :model-value="row.decrease" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="(v: number | undefined) => updateS7(row.rowId, 'decrease', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="subtotal-label">{{ fmtAmount(row.ending) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" size="small" type="danger" link @click="removeS7(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="note-block">
          <div class="note-label">房企披露说明</div>
          <el-input v-model="noteRe" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly" placeholder="对停工/烂尾/空置项目若不计提或计提比例较低，应详细说明理由..." />
        </div>
        <p class="hint-text">房地产开发企业列示存货跌价准备时，对于开发中项目可以合并列示。</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-disclosure-listed :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-disclosure-listed :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.update-bar, .tie-alert { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 24px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-title.sub { margin-top: 16px; }
.sub-title { margin: 12px 0 8px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.subtotal-label { font-weight: 600; }
.cross-sheet-cell { color: #409eff; }
.tie-warn { color: #e6a23c; font-weight: 600; }
.hint-text { margin: 8px 0; font-size: 12px; color: #909399; line-height: 1.5; }
.note-block { margin-top: 10px; }
.note-label { font-size: 12px; color: #606266; margin-bottom: 4px; }
.mt-8 { margin-top: 8px; }
</style>
