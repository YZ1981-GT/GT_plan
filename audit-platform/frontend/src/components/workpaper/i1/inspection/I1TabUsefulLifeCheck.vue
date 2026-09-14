<template>
  <div class="i1-tab-useful-life-check">
    <div class="methodology-context">
      <p>
        <strong>编制逻辑（对齐 Excel I1-7 / CAS6 §11-15）：</strong>
        按三路径判定使用寿命——①合同性权利或其他法定权利；②权利到期后续约；③没有法定使用年限时估计。
        使用寿命不确定的不摊销，须记录管理层判断依据，并每年减值测试（CAS8）；有限寿命至少每年复核，变更按 CAS28 会计估计变更处理。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：检查被审计单位确定无形资产使用寿命的依据，分析其合理性。"
    />

    <details class="procedure-details" open>
      <summary>二、审计过程</summary>
      <ol>
        <li>逐项分析合同/法定年限、续约安排及无法定年限时的估计是否合理，填入下表。</li>
        <li>
          对使用寿命不确定的无形资产，询问管理层：是否识别出任何潜在因素导致该项资产拥有有限的使用寿命，
          以及是否按照原定用途继续使用该资产。
        </li>
      </ol>
    </details>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" :disabled="isReadonly" @click="handleSeedFromDetail">从 I1-2 带入</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
        <el-button size="small" type="default" link @click="handleReview">💬 复核</el-button>
        <el-tag size="small" :type="prepValidation.ok ? 'success' : 'danger'">
          {{ prepValidation.ok ? '编制校验通过' : `待完善 ${prepValidation.messages.length}` }}
        </el-tag>
        <el-tag v-if="indefiniteCount > 0" size="small" type="warning">不摊销 {{ indefiniteCount }}</el-tag>
        <el-tag v-if="changedCount > 0" size="small" type="warning">本期变更 {{ changedCount }}</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-2')">← I1-2</el-tag>
      </div>
    </div>

    <el-alert
      v-if="!prepValidation.ok"
      type="warning"
      :closable="false"
      show-icon
      class="mb-8"
      :title="prepValidation.messages[0]"
      :description="prepValidation.messages.slice(1, 3).join('；') || undefined"
    />

    <!-- 主表：使用寿命判定（对齐 Excel 多级表头） -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>使用寿命确定分析</span>
          <span class="hint">剩余年限 = 原始寿命(月)/12 − 已用年限；寿命月=0 表示不确定</span>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="480"
        class="check-table"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="序号" width="48" align="center" fixed />

        <el-table-column prop="name" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.name"
              size="small"
              @change="(v: string) => updateField(row.rowId, 'name', v)"
            />
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 合同性权利或其他法定权利 -->
        <el-table-column label="合同性权利或其他法定权利" align="center">
          <el-table-column label="是否适用" width="88" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.legalApplicable"
                size="small"
                placeholder="-"
                @change="(v: string) => updateField(row.rowId, 'legalApplicable', v)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <span v-else>{{ ynLabel(row.legalApplicable) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="规定年限" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.legalPrescribedYears ?? undefined"
                :controls="false"
                size="small"
                :min="0"
                :precision="1"
                @change="(v: number | undefined) => updateField(row.rowId, 'legalPrescribedYears', v ?? null)"
              />
              <span v-else>{{ row.legalPrescribedYears ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="已确定寿命" width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.legalDeterminedLife"
                size="small"
                @change="(v: string) => updateField(row.rowId, 'legalDeterminedLife', v)"
              />
              <span v-else>{{ row.legalDeterminedLife || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 权利到期后续约 -->
        <el-table-column label="权利到期后续约的情况" align="center">
          <el-table-column label="是否适用" width="88" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.renewalApplicable"
                size="small"
                placeholder="-"
                @change="(v: string) => updateField(row.rowId, 'renewalApplicable', v)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <span v-else>{{ ynLabel(row.renewalApplicable) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="续约计入年限" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.renewalYearsInLife ?? undefined"
                :controls="false"
                size="small"
                :min="0"
                :precision="1"
                @change="(v: number | undefined) => updateField(row.rowId, 'renewalYearsInLife', v ?? null)"
              />
              <span v-else>{{ row.renewalYearsInLife ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="已确定寿命" width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.renewalDeterminedLife"
                size="small"
                @change="(v: string) => updateField(row.rowId, 'renewalDeterminedLife', v)"
              />
              <span v-else>{{ row.renewalDeterminedLife || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 没有法定使用年限 -->
        <el-table-column label="没有法定使用年限" align="center">
          <el-table-column label="是否估计寿命" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.noLegalEstimate"
                size="small"
                placeholder="-"
                @change="(v: string) => updateField(row.rowId, 'noLegalEstimate', v)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <span v-else>{{ ynLabel(row.noLegalEstimate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="是否合理" width="88" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.noLegalReasonable"
                size="small"
                placeholder="-"
                @change="(v: string) => updateField(row.rowId, 'noLegalReasonable', v)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
              <span v-else>{{ ynLabel(row.noLegalReasonable) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="寿命不确定" width="96" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isIndefinite"
              size="small"
              @change="(v: string) => updateField(row.rowId, 'isIndefinite', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.isIndefinite === 'Y' ? 'warning' : 'info'" size="small">
              {{ ynLabel(row.isIndefinite) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="不确定判断依据" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && isIndefiniteRow(row)"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :model-value="row.indefiniteJudgmentBasis"
              size="small"
              placeholder="管理层判断依据"
              @change="(v: string) => updateField(row.rowId, 'indefiniteJudgmentBasis', v)"
            />
            <span v-else-if="isIndefiniteRow(row)">{{ row.indefiniteJudgmentBasis || '—' }}</span>
            <span v-else class="na-cell">—</span>
          </template>
        </el-table-column>

        <el-table-column label="原始寿命(月)" width="100" align="right">
          <template #header>
            <el-tooltip content="0 = 使用寿命不确定（不摊销）；联动 I1-10/11" placement="top">
              <span class="formula-col-header">原始寿命(月)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.usefulLifeMonths"
              :controls="false"
              size="small"
              :min="0"
              :precision="0"
              @change="(v: number | undefined) => updateField(row.rowId, 'usefulLifeMonths', v ?? 0)"
            />
            <span v-else-if="isIndefiniteRow(row)" class="indefinite-tag">不摊销</span>
            <span v-else>{{ row.usefulLifeMonths }}</span>
          </template>
        </el-table-column>

        <el-table-column label="已用年限" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && !isIndefiniteRow(row)"
              :model-value="row.usedYears"
              :controls="false"
              size="small"
              :min="0"
              :precision="1"
              @change="(v: number | undefined) => updateField(row.rowId, 'usedYears', v ?? 0)"
            />
            <span v-else-if="isIndefiniteRow(row)" class="na-cell">—</span>
            <span v-else>{{ row.usedYears ?? '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="剩余年限" width="88" align="right">
          <template #header>
            <el-tooltip content="剩余年限 = 原始寿命(月)/12 − 已用年限" placement="top">
              <span class="formula-col-header">剩余年限</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span v-if="isIndefiniteRow(row)" class="indefinite-tag">不确定</span>
            <span v-else class="formula-cell">{{ fmtYears(calcRemainingYears(row)) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期变更" width="88" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isChanged"
              size="small"
              @change="(v: string) => updateField(row.rowId, 'isChanged', v)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isChanged === '是' ? 'warning' : 'info'" size="small">
              {{ row.isChanged || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="变更原因" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isChanged === '是'"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :model-value="row.changeReason"
              size="small"
              placeholder="CAS28 估计变更原因"
              @change="(v: string) => updateField(row.rowId, 'changeReason', v)"
            />
            <span v-else-if="row.isChanged === '是'">{{ row.changeReason || '—' }}</span>
            <span v-else class="na-cell">—</span>
          </template>
        </el-table-column>

        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.docIndex"
              size="small"
              placeholder="文件索引"
              @change="(v: string) => updateField(row.rowId, 'docIndex', v)"
            />
            <span v-else>{{ row.docIndex || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="结论" width="96" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              placeholder="-"
              @change="(v: string) => updateField(row.rowId, 'conclusion', v)"
            >
              <el-option label="合理" value="合理" />
              <el-option label="需关注" value="需关注" />
              <el-option label="不合理" value="不合理" />
            </el-select>
            <el-tag v-else :type="conclusionTagType(row.conclusion)" size="small">
              {{ row.conclusion || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              @change="(v: string) => updateField(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="联动" width="78" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="isIndefiniteRow(row)"
              value="wp:I1-12"
              :context-project-id="projectId"
            />
            <GtIndexChip
              v-else
              value="wp:I1-10"
              :context-project-id="projectId"
            />
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>资产总数: <b>{{ rows.length }}</b></span>
        <span>不摊销项: <b :class="{ 'warn-count': indefiniteCount > 0 }">{{ indefiniteCount }}</b></span>
        <span>本期变更: <b :class="{ 'warn-count': changedCount > 0 }">{{ changedCount }}</b></span>
        <span>合理: <b class="ok-count">{{ conclusionStats.reasonable }}</b></span>
        <span>需关注: <b class="warn-count">{{ conclusionStats.attention }}</b></span>
        <span>不合理: <b class="error-count">{{ conclusionStats.unreasonable }}</b></span>
        <GtIndexChip value="wp:I1-10" :context-project-id="projectId" />
        <GtIndexChip value="wp:I1-11" :context-project-id="projectId" />
        <GtIndexChip value="wp:I1-12" :context-project-id="projectId" />
      </div>
    </el-card>

    <!-- 管理层询问（Excel 下半表） -->
    <el-card shadow="never" class="inquiry-card">
      <template #header>
        <div class="section-title">
          <span>询问管理层（使用寿命不确定）</span>
          <el-button size="small" :disabled="isReadonly || indefiniteCount === 0" @click="syncInquiryFromIndefinite">
            同步不确定项
          </el-button>
        </div>
      </template>
      <p class="inquiry-hint">
        对于使用寿命不确定的无形资产，询问管理层是否识别出任何潜在因素导致该项资产拥有有限的使用寿命，
        以及是否按照原定用途继续使用该资产。
      </p>
      <el-table v-if="inquiryRows.length" :data="inquiryRows" border stripe size="small">
        <el-table-column type="index" label="#" width="44" align="center" />
        <el-table-column prop="name" label="资产名称" min-width="120" />
        <el-table-column label="账面净值" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.netBookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否识别出有限寿命因素" min-width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.identifiedFiniteFactors"
              size="small"
              placeholder="-"
              @change="(v: string) => updateInquiryField(row.rowId, 'identifiedFiniteFactors', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.identifiedFiniteFactors) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否按原定用途继续使用" min-width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.continuedOriginalUse"
              size="small"
              placeholder="-"
              @change="(v: string) => updateInquiryField(row.rowId, 'continuedOriginalUse', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.continuedOriginalUse) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注（记录相关发现）" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.findings"
              size="small"
              @change="(v: string) => updateInquiryField(row.rowId, 'findings', v)"
            />
            <span v-else>{{ row.findings || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无使用寿命不确定的资产；在主表将「寿命不确定」标为「是」后自动同步" :image-size="64" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>三、审计说明</span></div></template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：三路径判定依据、合同/法律年限核对、续约安排、不确定项管理层询问及减值测试安排等。"
        @change="saveNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="applyDraftConclusion">生成结论草稿</el-button>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handlePublish">
              📤 发布不确定清单
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对各项无形资产使用寿命估计合理性的审计结论…"
        @change="saveConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-4" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-10" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-11" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-12" :context-project-id="projectId" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>优先「从 I1-2 带入」名称/寿命月数/净值，再按 Excel 三路径补齐判定字段</li>
        <li>法定权利适用时填规定年限与已确定寿命；续约适用时填续约计入年限</li>
        <li>无法定年限时勾选是否估计及是否合理；不确定则填管理层判断依据并完成询问表</li>
        <li>原始寿命填 0 或「寿命不确定=是」→ 不摊销，联动 I1-12 减值测试</li>
        <li>本期变更=是须说明原因（CAS28）；发布不确定清单供 I1-12 取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabUsefulLifeCheck.vue — I1-7 使用寿命检查表
 * 对齐 Excel：三路径判定 + 不确定寿命管理层询问 + 说明/结论
 */
import { toRef, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI1UsefulLifeCheck,
  type I1UsefulLifeRow,
  type Yn,
} from '../../composables/useI1UsefulLifeCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const {
  rows,
  inquiryRows,
  auditNote,
  auditConclusion,
  indefiniteCount,
  changedCount,
  conclusionStats,
  prepValidation,
  updateField,
  updateInquiryField,
  addRow,
  removeRow,
  seedFromDetail,
  syncInquiryFromIndefinite,
  saveNote,
  saveConclusion,
  publishIndefiniteList,
  draftConclusion,
  calcRemainingYears,
  isIndefiniteRow,
} = useI1UsefulLifeCheck({
  allResponses: toRef(props, 'allResponses'),
  onSave(itemId, value) {
    emit('save', itemId, value)
  },
})

function ynLabel(v: Yn | string): string {
  if (v === 'Y' || v === '是') return '是'
  if (v === 'N' || v === '否') return '否'
  return '—'
}

function fmtYears(val: number | null): string {
  if (val == null) return '—'
  if (val <= 0) return '已到期'
  return val.toFixed(1)
}

function fmtAmt(val: number): string {
  if (!val) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function conclusionTagType(conclusion: string): 'success' | 'warning' | 'danger' | 'info' {
  if (conclusion === '合理') return 'success'
  if (conclusion === '需关注') return 'warning'
  if (conclusion === '不合理') return 'danger'
  return 'info'
}

function rowClassName({ row }: { row: I1UsefulLifeRow }): string {
  if (isIndefiniteRow(row)) return 'indefinite-row'
  if (row.conclusion === '不合理') return 'error-row'
  return ''
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入无形资产名称', '新增使用寿命检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX专利/商标/软件著作权',
    })
    if (name?.trim()) {
      addRow(name.trim())
      ElMessage.success('已新增')
    }
  } catch { /* cancelled */ }
}

function handleSeedFromDetail() {
  const r = seedFromDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleReview() {
  openReviewDialog('I1-7')
}

function applyDraftConclusion() {
  saveConclusion(draftConclusion())
  ElMessage.success('已生成结论草稿，请审阅后定稿')
}

function handlePublish() {
  publishIndefiniteList()
  ElMessage.success('已发布不确定寿命清单（I1-7-indefinite-list），可供 I1-12 取数')
}
</script>

<style scoped>
.i1-tab-useful-life-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }

.objective-alert { margin-bottom: 12px; }
.mb-8 { margin-bottom: 8px; }

.procedure-details {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: #f8fafc;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 12px;
}
.procedure-details summary { cursor: pointer; font-weight: 600; }
.procedure-details ol { margin: 6px 0 0; padding-left: 20px; line-height: 1.8; }

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; }
.nav-chip { cursor: pointer; }

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 500;
}
.section-title .hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.title-actions { display: flex; gap: 8px; align-items: center; }

.check-table { font-size: var(--wp-font-size, 13px); }
.check-table :deep(.el-table__header th) {
  font-size: 11px;
  font-weight: 600;
  background: #f8fafc;
}
.check-table :deep(.el-input-number) { width: 100%; }

.formula-col-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  font-variant-numeric: tabular-nums;
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.indefinite-tag {
  color: var(--el-color-warning-dark-2);
  font-weight: 600;
  font-size: 12px;
}
.na-cell { color: var(--el-text-color-placeholder); }

:deep(.indefinite-row) td { background: #fffbeb !important; }
:deep(.error-row) td { background: #fef2f2 !important; }

.summary-bar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.ok-count { color: var(--el-color-success); }
.warn-count { color: var(--el-color-warning-dark-2); }
.error-count { color: var(--el-color-danger); }

.inquiry-card,
.note-card { margin-top: 16px; }
.inquiry-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 10px;
  line-height: 1.6;
}

.jump-targets {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.jump-label { font-size: 12px; color: var(--el-text-color-secondary); }

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
