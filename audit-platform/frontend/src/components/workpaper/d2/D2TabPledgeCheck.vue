<script setup lang="ts">
/**
 * D2TabPledgeCheck — 应收账款质押及保理检查 D2-12
 *
 * 双区块：质押情况 + 保理终止确认(CAS 23)
 * 打磨基准：D1TabPledgeCheck（审计目标 / 全字段可编辑 / 审定表联动核对 /
 *           行级复核+索引 / 审计说明+结论+AI / 编制提示）
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { useD2PledgeCheck } from '../composables/useD2PledgeCheck'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import D2ReferenceBlock from './D2ReferenceBlock.vue'
import D2DerecognitionOverview from './D2DerecognitionOverview.vue'
import { FACTORING_REFERENCE_SECTIONS, FACTORING_REFERENCE_SOURCE } from '../composables/d2ReferenceExamples'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-12',
)

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function onReview(sectionId: string): void {
  if (openReviewDialog) openReviewDialog(sectionId)
}

const {
  pledgeRows,
  factoringRows,
  pledgeTotal,
  pledgeRatio,
  pledgeRatioWarning,
  auditedTotal,
  adjDataLoaded,
  factoringDerecognizedCount,
  auditNote,
  auditConclusion,
  addPledgeRow,
  addFactoringRow,
  removeRow,
  updateCell,
  saveAuditNote,
  saveAuditConclusion,
} = useD2PledgeCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const STATUS_OPTIONS = ['有效', '已解除', '部分解除']

// ─── AI 辅助 ──────────────────────────────────────────────────────────────
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, generateAndConfirm } = useD2AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildAiContext(extra = ''): Record<string, unknown> {
  return {
    sheet: 'D2-12',
    pledgeRowCount: pledgeRows.value.length,
    pledgeTotal: pledgeTotal.value,
    auditedTotal: auditedTotal.value,
    pledgeRatio: `${(pledgeRatio.value * 100).toFixed(1)}%`,
    factoringRowCount: factoringRows.value.length,
    factoringDerecognizedCount: factoringDerecognizedCount.value,
    guidance: extra,
  }
}

async function generateNoteAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'pledge-note',
      auditNote.value,
      buildAiContext('结合质押比例与受限资产披露、保理终止确认判定生成审计说明。'),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'pledge-conclusion',
      auditConclusion.value,
      buildAiContext(`质押比例：${(pledgeRatio.value * 100).toFixed(1)}%`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

async function handleImport(file: File): Promise<boolean> {
  await onImportFile(file)
  return false
}

// 逐份保理合同的 9 步判断由 D2DerecognitionOverview 组件（卡片/矩阵双视图 + 向导）承载

const GUIDANCE_TEXTS = [
  '受限资产披露（CAS 36 第六十六条）：因质押、保理等受到限制的应收账款，应在附注披露其账面价值及受限情况。',
  '质押比例预警：当质押金额占审定应收账款比例超过 50% 时，关注企业流动性风险及对持续经营假设的影响。',
  '保理业务终止确认（CAS 23）：风险与报酬已实质转移的，应终止确认；风险未转移且未保留控制的，亦终止确认；否则应作为质押融资处理（不终止确认）。',
  '保理合同应重点核对追索权条款、回购义务、劣后级安排，判断风险报酬是否实质转移。',
]
</script>

<template>
  <div class="d2-tab-pledge">
    <div class="tab-header">
      <h4>质押及保理检查 D2-12</h4>
      <GtReviewTrigger section-id="D2-pledge-header" />
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>核实应收账款质押及保理业务的完整性与准确性，评估受限资产披露充分性（CAS 36）及保理终止确认的恰当性（CAS 23）。</p>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button-group>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="handleImport" style="display:inline-block">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <!-- 质押比例警告 -->
    <el-alert v-if="pledgeRatioWarning" type="warning" :closable="false" show-icon class="pledge-alert">
      ⚠️ {{ pledgeRatioWarning }}
    </el-alert>

    <!-- 质押区域 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">
          质押情况
          <el-tag size="small" :type="pledgeRatio > 0.5 ? 'danger' : 'info'" style="margin-left:8px">
            质押比例 {{ (pledgeRatio * 100).toFixed(1) }}%
          </el-tag>
        </span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addPledgeRow">+ 添加质押</el-button>
      </div>
      <el-table :data="pledgeRows" border size="small" max-height="460" style="width: 100%">
        <el-table-column label="质押债务人" min-width="130" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" placeholder="债务人" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-pledge" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="质押金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.pledgeAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'pledgeAmount', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.pledgeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="质押日期" width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.pledgeDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" size="small" placeholder="质押日期" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'pledgeDate', v || '')" />
            <span v-else>{{ row.pledgeDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="质权人" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.pledgee" size="small" placeholder="质权人" @change="(v: string) => updateCell(row.rowId, 'pledgee', v)" />
            <span v-else>{{ row.pledgee || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="质押目的" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.pledgePurpose" size="small" placeholder="质押目的" @change="(v: string) => updateCell(row.rowId, 'pledgePurpose', v)" />
            <span v-else>{{ row.pledgePurpose || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.expiryDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" size="small" placeholder="到期日" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'expiryDate', v || '')" />
            <span v-else>{{ row.expiryDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.status" size="small" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'status', v)">
              <el-option v-for="o in STATUS_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <el-tag v-else :type="row.status === '有效' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="150">
          <template #default="{ row }">
            <div class="index-cell">
              <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="索引号" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row.rowId)">
              <template #reference>
                <el-button type="danger" link size="small">✕</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>暂无质押记录，点击"+ 添加质押"录入</template>
      </el-table>

      <!-- 质押汇总核对区 -->
      <div class="section-subtitle">质押汇总</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>质押金额合计</th>
            <th>审定表应收账款审定数</th>
            <th>质押比例</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="recon-num">{{ displayPrefs.fmtAmount(pledgeTotal) }}</td>
            <td class="recon-num">
              <template v-if="adjDataLoaded">{{ displayPrefs.fmtAmount(auditedTotal) }}</template>
              <el-tooltip v-else content="审定表(D2-1)审定数未加载，请先编制审定表" placement="top">
                <span class="adj-warn">- ⚠️</span>
              </el-tooltip>
            </td>
            <td class="recon-num" :class="{ 'pledge-warning-cell': pledgeRatio > 0.5 }">
              {{ adjDataLoaded ? (pledgeRatio * 100).toFixed(1) + '%' : 'N/A' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 保理终止确认区域 -->
    <div class="section-block">
      <!-- 源模板示例内嵌编制参考：保理合同条款分析 + 9步终止确认流程 -->
      <D2ReferenceBlock
        title="保理终止确认编制参考（合同条款分析清单 + 9步终止确认判断流程）"
        :source="FACTORING_REFERENCE_SOURCE"
        :sections="FACTORING_REFERENCE_SECTIONS as any"
      />
      <div class="section-header">
        <span class="section-title">
          保理终止确认 (CAS 23)
          <el-tag size="small" type="success" style="margin-left:8px">自动判定终止确认 {{ factoringDerecognizedCount }} 笔</el-tag>
        </span>
        <div style="display:flex; gap:8px;">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addFactoringRow">+ 添加保理</el-button>
        </div>
      </div>
      <el-table :data="factoringRows" border size="small" max-height="460" style="width: 100%">
        <el-table-column label="债务人" min-width="130" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" placeholder="债务人" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-pledge" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="保理金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.factoringAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'factoringAmount', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.factoringAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保理日期" width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.factoringDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" size="small" placeholder="保理日期" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'factoringDate', v || '')" />
            <span v-else>{{ row.factoringDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保理商" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.factor" size="small" placeholder="保理商" @change="(v: string) => updateCell(row.rowId, 'factor', v)" />
            <span v-else>{{ row.factor || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险已转移" width="100" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" :model-value="row.riskTransferred" size="small" @change="(v: boolean) => updateCell(row.rowId, 'riskTransferred', v)" />
            <el-tag v-else :type="row.riskTransferred ? 'success' : 'info'" size="small">{{ row.riskTransferred ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="保留控制" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" :model-value="row.controlRetained" size="small" @change="(v: boolean) => updateCell(row.rowId, 'controlRetained', v)" />
            <el-tag v-else :type="row.controlRetained ? 'warning' : 'info'" size="small">{{ row.controlRetained ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="终止确认（自动判定）" width="150" align="center">
          <template #default="{ row }">
            <el-tag :type="row.derecognition === '终止确认' ? 'success' : 'warning'" size="small">{{ row.derecognition }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row.rowId)">
              <template #reference>
                <el-button type="danger" link size="small">✕</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>暂无保理记录，点击"+ 添加保理"录入</template>
      </el-table>
      <el-alert type="info" :closable="false" class="cas-hint">
        终止确认自动判定：风险已转移 → 终止确认；风险未转移且未保留控制 → 终止确认；否则 → 不终止确认（作质押融资处理）。
        逐份合同的 9 步专业判断（CAS 23）见下方总览。
      </el-alert>

      <!-- 逐份保理合同 9 步判断总览：卡片式（单体）+ 矩阵式（汇总） -->
      <D2DerecognitionOverview
        :factoring-rows="factoringRows"
        :wp-id="wpId"
        :project-id="projectId"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
      />
    </div>

    <!-- 审计说明 -->
    <div class="section-subtitle">审计说明</div>
    <div class="note-section">
      <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" placeholder="请输入审计说明..." :disabled="isReadonly" @change="(v: string) => saveAuditNote(v || '')" />
      <div class="note-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计说明' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNoteAI">🤖 AI</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-pledge-note')">💬 复核</el-button>
      </div>
    </div>

    <!-- 审计结论 -->
    <div class="section-subtitle">审计结论</div>
    <div class="note-section">
      <el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditConclusion" placeholder="请输入审计结论..." :disabled="isReadonly" @change="(v: string) => saveAuditConclusion(v || '')" />
      <div class="note-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计结论' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusionAI">🤖 AI</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-pledge-conclusion')">💬 复核</el-button>
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>

  </div>
</template>

<style scoped>
.d2-tab-pledge { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; align-items: center; margin-bottom: 12px; gap: 12px; }
.pledge-alert { margin-bottom: 12px; }
.section-block { margin-bottom: 22px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.section-subtitle { font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.index-cell { display: flex; align-items: center; gap: 6px; }
.index-cell .el-input { flex: 1; }
.recon-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
.recon-table th, .recon-table td { border: 1px solid #ebeef5; padding: 8px 10px; }
.recon-table th { background: #f5f7fa; font-weight: 600; color: #303133; text-align: center; }
.recon-num { text-align: right; font-variant-numeric: tabular-nums; }
.adj-warn { color: #e6a23c; }
.pledge-warning-cell { color: #e6a23c !important; font-weight: 600; }
.cas-hint { margin-top: 8px; font-size: 12px; }
.note-section { margin-bottom: 8px; }
.note-actions { margin-top: 6px; display: flex; gap: 8px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
</style>
