<script setup lang="ts">
/** F2TabDisclosureSoe — 附注披露（国企），对齐源模板结构 */
import { ref, toRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useF2DisclosureSoe } from '../../composables/useF2DisclosureSoe'
import {
  buildF2SoeSubTableData,
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

const {
  isApplicable,
  section1Rows, section1Total,
  section2Rows, section2Total,
  noteCategory, s3BorrowText, s4AmortText, noteText, landNote,
  dataUpdatedVisible,
  updateS2Field,
  getSyncSnapshot,
} = useF2DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

const isSyncing = ref(false)
const noteSectionId = F2_NOTE_SECTION.soe

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
    'soe',
    props.wpId,
    props.applicableStandards,
    buildF2SoeSubTableData(getSyncSnapshot()),
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
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
  <div class="f2-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

    <template v-else>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. （1）存货分类：账面余额/跌价准备/账面价值 × 期末与期初，自 F2-1 跨 sheet 取数；「其中」行不计入合计。</p>
          <p>2. 原材料=材料+在途；自制半成品及在产品含开发成本；库存商品含开发产品。</p>
          <p>3. （2）跌价变动：期末=期初+计提+其他−转回−转销−其他，应与（1）期末跌价勾稽。</p>
          <p>4. 可「同步到附注」推送至附注模块「{{ noteSectionId }} 存货」。</p>
        </div>
      </details>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="objective-alert"
        title="审计目标：核实国有企业存货附注披露的分类、账面价值与跌价准备完整准确，确保与 F2-1 及主管部门列报要求一致。"
      />

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" plain :loading="isSyncing" :disabled="isReadonly" @click="syncToDisclosureNotes">
            同步到附注
          </el-button>
          <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
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
          <el-tooltip content="数据来源：F2-1 审定表；「其中」行不计入合计" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Total]" size="small" border stripe style="width:100%" row-class-name="soe-row">
          <el-table-column prop="label" label="项目" min-width="220" fixed>
            <template #default="{ row }">
              <span
                :class="{
                  'subtotal-label': row.rowKey === '__total__',
                  'detail-label': row.kind === 'detail',
                }"
              >{{ row.label }}</span>
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
          <el-table-column label="期初数" align="center">
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
        <p class="hint-text">注：房地产开发企业应在「其他」中披露土地储备的面积、本期增加及期末余额等情况。</p>
        <div class="note-block">
          <div class="note-label">土地储备 / 分类说明</div>
          <el-input v-model="landNote" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="土地储备面积、本期增加及期末余额..." />
          <el-input v-model="noteCategory" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" class="mt-8" placeholder="存货分类补充说明..." />
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
          <el-table-column prop="label" label="存货种类" min-width="200" fixed>
            <template #default="{ row }">
              <span
                :class="{
                  'subtotal-label': row.rowKey === '__total__',
                  'detail-label': row.kind === 'detail',
                }"
              >{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" min-width="100" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.opening) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="计提" min-width="100" align="right">
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
            <el-table-column label="其他" min-width="90" align="right">
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
            <el-table-column label="转回" min-width="90" align="right">
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
            <el-table-column label="转销" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decWriteOff) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decWriteOff"
                  :controls="false"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decWriteOff', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="其他" min-width="90" align="right">
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
          <el-table-column label="期末数" min-width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'tie-warn': Math.abs(row.tieDiff) >= 0.01, 'subtotal-label': row.rowKey === '__total__' }">
                {{ fmtAmount(row.ending) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- (3) 借款费用资本化 -->
      <div class="disclosure-card">
        <h4 class="card-title">(3) 借款费用资本化</h4>
        <el-input
          v-model="s3BorrowText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="存货期末余额中含有借款费用资本化金额为XXX元。计算标准和依据..."
        />
      </div>

      <!-- (4) 合同履约成本摊销 -->
      <div class="disclosure-card">
        <h4 class="card-title">(4) 合同履约成本本期摊销金额的说明</h4>
        <el-input
          v-model="s4AmortText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="说明合同履约成本本期摊销金额..."
        />
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">其他附注说明</h4>
        <el-input
          v-model="noteText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="其他应披露事项..."
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
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
.subtotal-label { font-weight: 600; }
.detail-label { color: #606266; padding-left: 12px; }
.cross-sheet-cell { color: #409eff; }
.tie-warn { color: #e6a23c; font-weight: 600; }
.hint-text { margin: 8px 0; font-size: 12px; color: #909399; line-height: 1.5; }
.note-block { margin-top: 10px; }
.note-label { font-size: 12px; color: #606266; margin-bottom: 4px; }
.mt-8 { margin-top: 8px; }
</style>
