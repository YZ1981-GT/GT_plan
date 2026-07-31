<script setup lang="ts">
/**
 * D1TabDetailCustomer.vue — 原值明细按客户 D1-3 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 10.1
 *
 * 对齐 D1-2 布局：审计目标/过程 + 明细表 + 审计意见区（说明/结论）+ AI
 * 列：客户名称|公司代码|关联关系|期初未审|期初AJE|期初RJE|期初审定|
 *   本期增加|本期减少|期末余额|重分类|期末未审|期末AJE|期末RJE|期末审定
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useD1DetailCustomer, type CustomerRow } from '../composables/useD1DetailCustomer'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1VirtualBrowse } from '../composables/useD1VirtualBrowse'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import { getWpIndex } from '@/services/workpaperApi'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
  relatedParties?: string[]
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const openReviewDialog = inject<((params: { sectionId: string }) => void) | null>('openReviewDialog', null)

// ─── Related Parties ─────────────────────────────────────────────────────────

const relatedParties = computed(() => {
  const raw = props.relatedParties
  if (!Array.isArray(raw)) return [] as string[]
  return raw
    .map((p) => (typeof p === 'string' ? p : String((p as any)?.name ?? (p as any)?.party_name ?? '')))
    .filter(Boolean)
})

const router = useRouter()
const jumpingToRpList = ref(false)

/**
 * 跳转被审计单位关联方清单：打开 B19，并切到「管理层提供的关联方清单」内页签
 * （B19-1 为同文件 sheet 且 override=skip，无独立底稿 ID）
 */
async function goToClientRelatedPartyList() {
  if (!props.projectId || jumpingToRpList.value) return
  jumpingToRpList.value = true
  try {
    const index = await getWpIndex(props.projectId)
    const b19 = index.find((i) => i.wp_code === 'B19')
    if (b19?.id) {
      await router.push({
        name: 'WorkpaperEditor',
        params: { projectId: props.projectId, wpId: b19.id },
        // sheet=程序表 sheet（确保挂载 b19-bundle）；view=内页签
        query: {
          sheet: 'B19识别关联方程序表',
          view: 'B19-1',
        },
      })
      return
    }
    ElMessage.warning('当前项目未找到 B19 识别关联方底稿，请先在底稿目录中启用')
  } catch {
    ElMessage.warning('无法打开被审计单位关联方清单')
  } finally {
    jumpingToRpList.value = false
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  filteredRows,
  subtotalRow,
  searchQuery,
  auditProcedures,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  importFromAuxBalance,
  importPostSettlementFromLedger,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
} = useD1DetailCustomer({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  relatedParties: relatedParties as Ref<string[]>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
})

const loadingPostSettlement = ref(false)
async function onImportPostSettlement() {

const loadingAux = ref(false)

/**
 * 从辅助余额表（tb_aux_balance 客户维度）一键导入客户明细。
 *
 * 科目由后端按报表映射 BS-005 解析（→ 标准码 → account_mapping → 原始码），
 * merge 语义 = 手工优先（已存在客户整行保留，不覆盖关联方标记 / 期后兑付 / 调整列）。
 */
async function onImportFromAux(): Promise<void> {
  if (props.isReadonly) return
  loadingAux.value = true
  try {
    await importFromAuxBalance()
  } finally {
    loadingAux.value = false
  }
}
  if (loadingPostSettlement.value) return
  loadingPostSettlement.value = true
  try {
    await importPostSettlementFromLedger()
  } finally {
    loadingPostSettlement.value = false
  }
}

const rowCount = computed(() => rows.value.length)
const { useLargeTable, tableMaxHeight } = useD1VirtualBrowse(rowCount)

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getTableData(): CustomerRow[] {
  return [...filteredRows.value, subtotalRow.value]
}

function getRowClassName({ row }: { row: CustomerRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  if (row.relationType === '关联方') return 'related-party-row'
  return ''
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentBalance', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: CustomerRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

// ─── Import/Export + AI ──────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-3')

const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingProcedures = ref(false)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

const AUDIT_OBJECTIVES = [
  '资产负债表中的应收票据已得到恰当的确认和计量；',
  '评价调整已记录于账户中；',
  '披露已得到恰当计量和列报。',
]

function buildDetailContext(guidance: string): Record<string, unknown> {
  const lines = rows.value.map((r) => {
    const rel = r.relationType ? `[${r.relationType}]` : ''
    return `${r.customerName || '未命名'}${rel}: 期初审定=${r.priorAudited}, 本期增加=${r.currentIncrease}, 本期减少=${r.currentDecrease}, 期末余额=${r.currentBalance}, 重分类=${r.reclassification}, 期末审定=${r.currentAudited}`
  })
  const st = subtotalRow.value
  const relatedCount = rows.value.filter((r) => r.relationType === '关联方').length
  return {
    sheet: 'D1-3',
    objectives: AUDIT_OBJECTIVES.join(' '),
    rowCount: rows.value.length,
    relatedPartyCount: relatedCount,
    tableSummary: lines.slice(0, 20).join('\n'),
    subtotal: `小计 期初审定=${st.priorAudited}, 期末余额=${st.currentBalance}, 期末审定=${st.currentAudited}`,
    auditProcedures: auditProcedures.value || '',
    guidance,
  }
}

async function generateAuditProceduresWithAI() {
  if (props.isReadonly) return
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'detail-audit-procedures',
      auditProcedures.value,
      buildDetailContext(
        '按编号列出D1-3原值明细表（按客户）应执行的审计过程，覆盖客户明细完整性、关联方识别、期初衔接、增减变动抽查、重分类核对、与总账/D1-2勾稽。',
      ),
      'AI · 审计过程',
    )
    if (text) saveAuditProcedures(text)
  } finally {
    aiLoadingProcedures.value = false
  }
}

async function generateAuditNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'detail-audit-note',
      auditNote.value,
      buildDetailContext(
        '根据D1-3按客户明细生成审计说明：客户构成、关联方余额、期初衔接、本期增减、重分类及与总账勾稽结果。',
      ),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateAuditConclusionWithAI() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'detail-audit-conclusion',
      auditConclusion.value,
      buildDetailContext(
        '根据D1-3明细与审计说明生成审计结论：按客户明细完整性、关联方披露充分性、与总账一致性、是否需调整。',
      ),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

function onReview(sectionId: string) {
  openReviewDialog?.({ sectionId })
}
</script>

<template>
  <div class="d1-tab-detail-customer">
    <div class="tab-header">
      <h4>应收票据原值明细表（按客户）D1-3</h4>
      <GtReviewTrigger section-id="D1-detail-cust-header" />
    </div>

    <!-- 一、审计目标 + 二、审计过程 -->
    <details class="methodology-collapse" open>
      <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
      <div class="methodology-body">
        <p class="method-title"><strong>一、审计目标：</strong></p>
        <ol class="method-objectives">
          <li v-for="(item, i) in AUDIT_OBJECTIVES" :key="'obj-' + i">{{ item }}</li>
        </ol>
        <div class="method-title-row">
          <p class="method-title"><strong>二、审计过程：</strong></p>
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计过程' : 'AI服务暂不可用'" placement="top">
            <el-button
              size="small"
              :loading="aiLoadingProcedures"
              :disabled="isReadonly || !aiAvailable"
              @click="generateAuditProceduresWithAI"
            >
              🤖 AI
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :model-value="auditProcedures"
          placeholder="请记录执行的审计程序，如：1. 获取按客户明细并与总账/D1-2核对……"
          :disabled="isReadonly"
          @input="(v: string) => saveAuditProcedures(v)"
        />
      </div>
    </details>

    <!-- Toolbar: Search + Import/Export + Add -->
    <div class="table-toolbar">
      <el-input
        v-model="searchQuery"
        size="small"
        placeholder="搜索客户名称..."
        clearable
        class="search-input"
      >
        <template #prefix>
          <span>🔍</span>
        </template>
      </el-input>
      <div class="toolbar-actions">
        <el-button-group size="small">
          <el-button @click="onExportTemplate">导出模板</el-button>
          <el-button @click="onExportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :before-upload="onImportFile"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-tooltip
          content="从辅助余额表(tb_aux_balance)按客户维度归集应收票据期初/本期增减/期末，科目由报表映射 BS-005 自动解析；已录入的客户保留不覆盖"
          placement="top"
        >
          <span>
            <el-button
              type="primary"
              plain
              size="small"
              :loading="loadingAux"
              :disabled="isReadonly"
              @click="onImportFromAux"
            >
              从辅助余额表导入
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip content="从次年序时账提取资产负债表日后科目1121贷方（票据承兑收款），按客户归集填入期后兑付列" placement="top">
          <el-button
            type="warning"
            plain
            size="small"
            :loading="loadingPostSettlement"
            :disabled="isReadonly"
            @click="onImportPostSettlement"
          >
            取期后兑付
          </el-button>
        </el-tooltip>
        <el-button
          type="primary"
          size="small"
          :disabled="isReadonly"
          @click="addRow()"
        >
          + 添加客户
        </el-button>
      </div>
    </div>

    <el-alert v-if="useLargeTable" type="info" :closable="false" show-icon class="large-table-hint">
      行数较多，已启用固定高度滚动浏览（{{ rowCount }} 行）
    </el-alert>

    <div class="table-scroll">
      <el-table
        class="detail-customer-table"
        :data="getTableData()"
        border
        size="small"
        :row-class-name="getRowClassName"
        style="width: 100%"
        :max-height="tableMaxHeight"
      >
        <el-table-column label="客户名称" min-width="160" fixed>
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span style="font-weight: 600">{{ row.customerName }}</span>
            </template>
            <template v-else>
              <div class="customer-name-cell">
                <el-input
                  :model-value="row.customerName"
                  size="small"
                  placeholder="客户名称"
                  :disabled="isReadonly"
                  @change="(v: string) => updateCell(row.rowId, 'customerName', v)"
                />
                <GtReviewDot row-prefix="D1-cust" :row-key="row.rowId" />
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                  @click="removeRow(row.rowId)"
                >
                  ✕
                </el-button>
              </div>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="公司代码" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="isCellEditable(row, 'companyCode')"
              :model-value="row.companyCode"
              size="small"
              placeholder=""
              @change="(v: string) => updateCell(row.rowId, 'companyCode', v)"
            />
            <span v-else>{{ row.companyCode || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="关联关系" min-width="100">
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span>-</span>
            </template>
            <template v-else>
              <el-tag
                v-if="row.relationType === '关联方'"
                type="warning"
                size="small"
              >
                关联方
              </el-tag>
              <span v-else-if="row.relationType">{{ row.relationType }}</span>
              <span v-else>-</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorUnadjusted')"
              class="cell-amount-input"
              :model-value="row.priorUnadjusted"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
          </template>
        </el-table-column>

        <el-table-column label="期初AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorAje')"
              class="cell-amount-input"
              :model-value="row.priorAje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorAje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorAje)" />
          </template>
        </el-table-column>

        <el-table-column label="期初RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorRje')"
              class="cell-amount-input"
              :model-value="row.priorRje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorRje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorRje)" />
          </template>
        </el-table-column>

        <el-table-column label="期初审定" min-width="110" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
          </template>
        </el-table-column>

        <el-table-column label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentIncrease')"
              class="cell-amount-input"
              :model-value="row.currentIncrease"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentIncrease', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentIncrease)" />
          </template>
        </el-table-column>

        <el-table-column label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentDecrease')"
              class="cell-amount-input"
              :model-value="row.currentDecrease"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentDecrease', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentDecrease)" />
          </template>
        </el-table-column>

        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600" v-html="fmtAmount(row.currentBalance)" />
          </template>
        </el-table-column>

        <el-table-column label="重分类" min-width="100" align="right">
          <template #header>
            <el-tooltip content="被审计单位重分类调整" placement="top">
              <span>重分类</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'reclassification')"
              class="cell-amount-input"
              :model-value="row.reclassification"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'reclassification', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.reclassification)" />
          </template>
        </el-table-column>

        <el-table-column label="期末未审" min-width="110" align="right">
          <template #default="{ row }">
            <span v-html="fmtAmount(row.currentUnadjusted)" />
          </template>
        </el-table-column>

        <el-table-column label="期末AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentAje')"
              class="cell-amount-input"
              :model-value="row.currentAje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentAje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentAje)" />
          </template>
        </el-table-column>

        <el-table-column label="期末RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentRje')"
              class="cell-amount-input"
              :model-value="row.currentRje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentRje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentRje)" />
          </template>
        </el-table-column>

        <el-table-column label="期末审定" min-width="110" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
          </template>
        </el-table-column>

        <el-table-column min-width="120" align="right">
          <template #header>
            <el-tooltip content="资产负债表日后票据承兑收款（存在性/可回收性证据；可点「取期后兑付」按客户自动归集）" placement="top">
              <span>期后兑付 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowId !== 'subtotal' && !isReadonly"
              class="cell-amount-input"
              :model-value="row.postSettlement"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'postSettlement', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.postSettlement)" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <p class="relation-legend">
      关联关系说明：橙色高亮行为关联方（自动匹配
      <strong>被审计单位关联方清单</strong>
      ，当前已加载
      <strong>{{ relatedParties.length }}</strong>
      家）；其余为非关联方。
      <a
        href="#"
        class="relation-legend-link"
        :class="{ 'is-loading': jumpingToRpList }"
        @click.prevent="goToClientRelatedPartyList"
      >
        {{ jumpingToRpList ? '打开中…' : '前往 B19-1 维护关联方清单 →' }}
      </a>
    </p>

    <!-- 三、审计说明 + 四、审计结论 -->
    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计意见区</span>
        </div>
      </template>
      <div class="opinion-body">
        <div class="opinion-field">
          <label>三、审计说明</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :model-value="auditNote"
            placeholder="请输入审计说明..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditNote(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingNote"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditNoteWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-cust-note')">💬 复核</el-button>
          </div>
        </div>
        <div class="opinion-field">
          <label>四、审计结论</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :model-value="auditConclusion"
            placeholder="请输入审计结论..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditConclusion(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingConclusion"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditConclusionWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-cust-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d1-tab-detail-customer {
  width: 100%;
  padding: 12px;
}

.detail-customer-table {
  width: 100%;
}

.detail-customer-table :deep(.cell-amount-input) {
  width: 100%;
}

.detail-customer-table :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input {
  width: 240px;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
}

.large-table-hint {
  margin-bottom: 8px;
}

.relation-legend {
  margin: 8px 0 16px;
  font-size: 12px;
  color: #909399;
}

.relation-legend-link {
  margin-left: 8px;
  color: #409eff;
  text-decoration: none;
  cursor: pointer;
}

.relation-legend-link:hover {
  text-decoration: underline;
}

.relation-legend-link.is-loading {
  pointer-events: none;
  opacity: 0.7;
}

:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

:deep(.el-table .related-party-row td) {
  background-color: #fdf6ec !important;
}

:deep(.negative-amount) {
  color: #f56c6c;
}

.customer-name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.customer-name-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

.methodology-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.8;
}

.method-title {
  margin: 8px 0 4px;
  font-size: var(--wp-font-size, 13px);
}

.method-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
}

.method-title-row .method-title {
  margin: 0;
}

.method-objectives {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.audit-opinion-card {
  margin-top: 16px;
  border: 1px solid #ebeef5;
}

.opinion-header {
  display: flex;
  align-items: center;
}

.opinion-title {
  font-weight: 600;
  font-size: 14px;
}

.opinion-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.opinion-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  font-size: var(--wp-font-size, 13px);
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
