<template>
  <div class="h1-tab-idle-check">
    <!-- 一、审计目标（对齐致同 H1-4 模板） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>确定资产负债表中记录的固定资产是存在的，且记录于恰当的账户。</li>
        <li>
          确定固定资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，
          相关披露恰当（含闲置资产减值迹象评价，CAS8 第5条）。
        </li>
      </ol>
    </el-alert>

    <el-alert
      v-if="stocktakeConcernCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="`H1-11 监盘小结推送了 ${stocktakeConcernCount} 项闲置/报废关注（备注含「来源:H1-11」），请核对并完善减值迹象判断。`"
    />

    <el-alert
      v-if="state.depStopWarnings.value.length > 0"
      type="error"
      :closable="false"
      show-icon
      class="objective-alert"
    >
      <template #title>
        折旧停提异常 {{ state.depStopWarnings.value.length }} 项（CAS4：闲置固定资产通常应继续计提折旧）
      </template>
      <ul class="warn-list">
        <li v-for="w in state.depStopWarnings.value.slice(0, 8)" :key="w.rowId">{{ w.message }}</li>
        <li v-if="state.depStopWarnings.value.length > 8">
          …另有 {{ state.depStopWarnings.value.length - 8 }} 项，见行内高亮
        </li>
      </ul>
    </el-alert>

    <!-- 二、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>二、审计过程</span></div>
      </template>
      <ol class="proc-list">
        <li>
          获取暂时闲置固定资产的相关证明文件，观察其实际状况，检查是否已按规定继续计提折旧，
          相关会计处理是否正确。
        </li>
        <li>
          考虑暂时闲置固定资产是否存在减值迹象（闲置、终止使用或计划提前处置），必要时联动
          <GtIndexChip value="wp:H1-14" :context-project-id="projectId" /> 进行减值测算。
        </li>
      </ol>
    </el-card>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-4" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ state.rows.value.length }} 项</el-tag>
      <el-tag v-if="state.statistics.value.indicationCount" size="small" type="danger">
        减值迹象 {{ state.statistics.value.indicationCount }}
      </el-tag>
      <el-tag v-if="state.statistics.value.depStopAnomalyCount" size="small" type="danger">
        停提异常 {{ state.statistics.value.depStopAnomalyCount }}
      </el-tag>
      <el-tag v-if="state.statistics.value.indicationNotImpairedCount" size="small" type="warning">
        有迹象未计提 {{ state.statistics.value.indicationNotImpairedCount }}
      </el-tag>
      <div class="toolbar-spacer" />
      <el-radio-group v-model="viewFilter" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="unused">①未使用</el-radio-button>
        <el-radio-button value="unneeded">②不需用</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 三、检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、闲置固定资产检查表</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" :loading="importLoading" @click="handleImportH12">
              从 H1-2 带入闲置
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow('unused')">
              + 未使用
            </el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleAddRow('unneeded')">
              + 不需用
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-4')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="displayRows"
        border
        stripe
        size="small"
        class="idle-table"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="summaryMethod"
      >
        <el-table-column type="index" label="序号" width="48" align="center" fixed />
        <el-table-column prop="idleType" label="类型" width="88">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.idleType"
              size="small"
              @change="(v: string) => onCell(row, 'idleType', v)"
            >
              <el-option label="未使用" value="unused" />
              <el-option label="不需用" value="unneeded" />
            </el-select>
            <span v-else>{{ row.idleType === 'unneeded' ? '不需用' : '未使用' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="固定资产类别" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              @change="onCell(row, 'category', row.category)"
            />
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="固定资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.name"
              size="small"
              @change="onCell(row, 'name', row.name)"
            />
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetNo" label="资产编号" width="96">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.assetNo"
              size="small"
              @change="onCell(row, 'assetNo', row.assetNo)"
            />
            <span v-else>{{ row.assetNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.originalCost"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => onCell(row, 'originalCost', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDep" label="累计折旧" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.accDep"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => onCell(row, 'accDep', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentProvision" label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairmentProvision"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => onCell(row, 'impairmentProvision', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="起止时间" width="200">
          <template #default="{ row }">
            <div v-if="!isReadonly" class="date-range">
              <el-date-picker
                v-model="row.idleStartDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="起始"
                style="width:96px"
                @change="(v: string) => onCell(row, 'idleStartDate', v || '')"
              />
              <span class="date-sep">~</span>
              <el-date-picker
                v-model="row.idleEndDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="截止"
                style="width:96px"
                @change="(v: string) => onCell(row, 'idleEndDate', v || '')"
              />
            </div>
            <span v-else>{{ formatPeriod(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="condition" label="状况" width="96">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.condition"
              size="small"
              filterable
              allow-create
              @change="(v: string) => onCell(row, 'condition', v)"
            >
              <el-option label="完好" value="完好" />
              <el-option label="需维修" value="需维修" />
              <el-option label="毁损" value="毁损" />
              <el-option label="待报废" value="待报废" />
            </el-select>
            <span v-else>{{ row.condition || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="idleReason" label="闲置原因" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.idleReason"
              size="small"
              @change="onCell(row, 'idleReason', row.idleReason)"
            />
            <span v-else>{{ row.idleReason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depContinued" label="继续折旧" width="88" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.depContinued"
              size="small"
              @change="(v: string) => onCell(row, 'depContinued', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
              <el-option label="N/A" value="NA" />
            </el-select>
            <span v-else>{{ depLabel(row.depContinued) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalSuggestion" label="处置计划" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.disposalSuggestion"
              size="small"
              @change="(v: string) => onCell(row, 'disposalSuggestion', v)"
            >
              <el-option label="继续闲置" value="idle" />
              <el-option label="计划处置" value="dispose" />
              <el-option label="转为使用" value="reuse" />
            </el-select>
            <span v-else>{{ state.planLabel(String(row.disposalSuggestion)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值迹象" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="state.hasImpairmentIndication(row) ? 'danger' : 'success'" size="small">
              {{ state.hasImpairmentIndication(row) ? '有' : '无' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="hasImpairment" label="已计提减值" width="96" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.hasImpairment"
              size="small"
              @change="(v: string) => onCell(row, 'hasImpairment', v)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ row.hasImpairment === 'Y' ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="→H1-14" width="72" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="state.hasImpairmentIndication(row)"
              value="wp:H1-14"
              :context-project-id="projectId"
            />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="onCell(row, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>未使用 {{ state.statistics.value.unusedCount }} / 不需用 {{ state.statistics.value.unneededCount }}</span>
        <span>原值合计 <b class="amount-cell">{{ fmtAmt(state.statistics.value.totalOriginalCost) }}</b></span>
        <span>净值合计 <b class="amount-cell">{{ fmtAmt(state.statistics.value.totalNetValue) }}</b></span>
        <span>已计提减值 <b class="amount-cell">{{ fmtAmt(state.statistics.value.impairedTotal) }}</b></span>
        <span>
          停提异常
          <b :class="{ 'error-amount': state.statistics.value.depStopAnomalyCount > 0 }">
            {{ state.statistics.value.depStopAnomalyCount }}
          </b>
          项
        </span>
        <span>
          有迹象未计提
          <b :class="{ 'error-amount': state.statistics.value.indicationNotImpairedCount > 0 }">
            {{ state.statistics.value.indicationNotImpairedCount }}
          </b>
          项 → 建议引入 H1-14
        </span>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计说明</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleRuleNoteDraft">规则草稿</el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly"
              :loading="aiNoteLoading"
              @click="handleAiNote"
            >
              AI 起草
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="填写指引：①闲置识别范围与抽样/全查依据；②观察状况与折旧处理结论；③减值迹象判断（起止时间、处置计划、CAS8）；④与 H1-14/附注披露联动情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>五、审计结论</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleRuleConclusionDraft">规则草稿</el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly"
              :loading="aiConclusionLoading"
              @click="handleAiConclusion"
            >
              AI 起草
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="经检查，闲置固定资产分类、计价及减值相关会计处理是否在所有重大方面符合企业会计准则的规定…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>「从 H1-2 带入」按类别/名称/备注等关键词识别未使用、不需用、闲置资产余额（去重刷新金额）。</li>
        <li>表①未使用 / 表②不需用：与账面口径一致；净值 = 原值 − 累计折旧 − 减值准备。</li>
        <li>折旧：闲置通常应继续计提；标记「否」或本期计提为 0 且未提足 → 停提异常警示。</li>
        <li>减值迹象：计划处置、毁损/待报废、或闲置≥1年且无复用计划 →「有」；有迹象未计提引入 H1-14。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH1IdleCheck,
  type IdleAssetRow,
  type IdleType,
} from '../../composables/useH1IdleCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const viewFilter = ref<'all' | IdleType>('all')
const importLoading = ref(false)
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

const NOTE_KEY = 'H1-4-audit-note'
const CONCLUSION_KEY = 'H1-4-audit-conclusion'

function saveAuditNote() {
  saveResponse(NOTE_KEY, auditNoteText.value)
}
function saveAuditConclusion() {
  saveResponse(CONCLUSION_KEY, conclusion.value)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})

const state = useH1IdleCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const displayRows = computed(() => {
  if (viewFilter.value === 'all') return state.rows.value
  return state.rows.value.filter((r) => r.idleType === viewFilter.value)
})

const stocktakeConcernCount = computed(() => {
  const fromRows = state.rows.value.filter((r) => String(r.remark || '').includes('来源:H1-11')).length
  const pushed = props.allResponses.get('H1-11-pushed-concerns')
  let n = 0
  if (pushed?.remark) {
    try {
      const p = JSON.parse(pushed.remark)
      n = Array.isArray(p?.items)
        ? p.items.filter((i: any) => i.suggest === 'idle' || i.suggest === 'both').length
        : 0
    } catch { /* ignore */ }
  }
  return Math.max(fromRows, n)
})

function onCell(row: IdleAssetRow, field: keyof IdleAssetRow, value: any) {
  state.updateCell(row.rowId, field, value)
}

function rowClassName({ row }: { row: IdleAssetRow }) {
  if (state.evaluateDepStopAnomaly(row)) return 'row-dep-stop'
  if (state.hasImpairmentIndication(row) && row.hasImpairment !== 'Y') return 'row-indication'
  return ''
}

async function handleImportH12() {
  importLoading.value = true
  try {
    const hasRows = state.rows.value.length > 0
    let replace = false
    if (hasRows) {
      try {
        await ElMessageBox.confirm(
          '已有闲置行。选择「合并」按编号/名称去重并刷新金额；选择「替换」清空后重导。',
          '从 H1-2 带入闲置',
          {
            distinguishCancelAndClose: true,
            confirmButtonText: '合并带入',
            cancelButtonText: '替换全部',
            type: 'info',
          },
        )
      } catch (action) {
        if (action === 'cancel') replace = true
        else return
      }
    }
    const r = state.importFromDetail({ replace })
    if (!r.candidates) {
      ElMessage.warning('H1-2 未识别到含「未使用/不需用/闲置」等关键词的明细（或原值为 0）')
      return
    }
    ElMessage.success(
      replace
        ? `已替换导入 ${r.added} 项闲置余额`
        : `带入完成：新增 ${r.added}，刷新 ${r.refreshed}（候选 ${r.candidates}）`,
    )
  } finally {
    importLoading.value = false
  }
}

async function handleAddRow(idleType: IdleType) {
  const label = idleType === 'unneeded' ? '不需用' : '未使用'
  const { value: name } = await ElMessageBox.prompt(`请输入${label}固定资产名称`, '新增闲置资产', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name) state.addRow(name, idleType)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

async function applyTextWithConfirm(target: 'note' | 'conclusion', text: string, title: string) {
  if (!text) {
    ElMessage.warning('草稿为空')
    return
  }
  const cur = target === 'note' ? auditNoteText.value : conclusion.value
  if (cur?.trim()) {
    try {
      await ElMessageBox.confirm(text.slice(0, 600) + (text.length > 600 ? '…' : ''), title, {
        confirmButtonText: '覆盖填入',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  if (target === 'note') {
    auditNoteText.value = text
    saveAuditNote()
  } else {
    conclusion.value = text
    saveAuditConclusion()
  }
  ElMessage.success('已填入，可继续编辑')
}

function handleRuleNoteDraft() {
  applyTextWithConfirm('note', state.buildNoteDraft(), '规则草稿 — 审计说明')
}

function handleRuleConclusionDraft() {
  applyTextWithConfirm('conclusion', state.buildConclusionDraft(), '规则草稿 — 审计结论')
}

function aiContext() {
  return {
    ruleDraft: state.buildConclusionDraft(),
    noteDraft: state.buildNoteDraft(),
    stats: state.statistics.value,
    depStopWarnings: state.depStopWarnings.value.slice(0, 15),
    rows: state.rows.value.slice(0, 30).map((r) => ({
      idleType: r.idleType,
      name: r.name,
      assetNo: r.assetNo,
      category: r.category,
      originalCost: r.originalCost,
      netValue: r.netValue,
      idleReason: r.idleReason,
      depContinued: r.depContinued,
      periodDepProvision: r.periodDepProvision,
      disposalSuggestion: r.disposalSuggestion,
      hasImpairment: r.hasImpairment,
      indication: state.hasImpairmentIndication(r),
      depStop: !!state.evaluateDepStopAnomaly(r),
    })),
  }
}

async function handleAiNote() {
  if (!props.wpId) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'idle-note',
        existingContent: auditNoteText.value || '',
        relatedContext: aiContext(),
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容，已可用规则草稿')
      return
    }
    await applyTextWithConfirm('note', text, 'AI 起草 — 审计说明')
  } catch (e: any) {
    ElMessage.warning(e?.response?.data?.detail || 'AI 起草失败，请用规则草稿或手工填写')
  } finally {
    aiNoteLoading.value = false
  }
}

async function handleAiConclusion() {
  if (!props.wpId) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'idle-conclusion',
        existingContent: conclusion.value || '',
        relatedContext: aiContext(),
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容，已可用规则草稿')
      return
    }
    await applyTextWithConfirm('conclusion', text, 'AI 起草 — 审计结论')
  } catch (e: any) {
    ElMessage.warning(e?.response?.data?.detail || 'AI 起草失败，请用规则草稿或手工填写')
  } finally {
    aiConclusionLoading.value = false
  }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPeriod(row: IdleAssetRow): string {
  const a = row.idleStartDate || ''
  const b = row.idleEndDate || ''
  if (!a && !b) return '—'
  return `${a || '?'}${b ? ` ~ ${b}` : ' 起'}`
}

function depLabel(v: string): string {
  if (v === 'Y') return '是'
  if (v === 'N') return '否'
  if (v === 'NA') return 'N/A'
  return v || '—'
}

function summaryMethod({ columns }: { columns: { property?: string }[] }) {
  const list = displayRows.value
  const sumCost = list.reduce((s, r) => s + (Number(r.originalCost) || 0), 0)
  const sumDep = list.reduce((s, r) => s + (Number(r.accDep) || 0), 0)
  const sumProv = list.reduce((s, r) => s + (Number(r.impairmentProvision) || 0), 0)
  const sumNet = list.reduce((s, r) => s + (Number(r.netValue) || 0), 0)
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.property === 'originalCost') return fmtAmt(sumCost)
    if (col.property === 'accDep') return fmtAmt(sumDep)
    if (col.property === 'impairmentProvision') return fmtAmt(sumProv)
    if (col.property === 'netValue') return fmtAmt(sumNet)
    return ''
  })
}
</script>

<style scoped>
.h1-tab-idle-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list, .proc-list { margin: 6px 0 0; padding-left: 20px; line-height: 1.7; font-size: 12px; }
.block-card { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.toolbar-spacer { flex: 1; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.title-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.idle-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.muted { color: var(--el-text-color-placeholder); }
.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; }
.date-range { display: flex; align-items: center; gap: 2px; }
.date-sep { color: var(--el-text-color-secondary); font-size: 11px; }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-indication) { background: var(--el-color-warning-light-9) !important; }
:deep(.row-dep-stop) { background: var(--el-color-danger-light-9) !important; }
.warn-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.6; }
</style>
