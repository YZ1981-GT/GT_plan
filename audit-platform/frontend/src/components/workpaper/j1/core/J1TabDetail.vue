<template>
  <div class="j1-tab-detail">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：核实应付职工薪酬各项目期初、本期变动及期末余额的完整性与准确性，验证"期末=期初+增加-减少"（负债贷方口径2211）勾稽关系成立。
      </template>
      <template #default>
        <ul class="ao-list">
          <li><b>完整性</b>：所有应付职工薪酬均已记录（负债重点认定）</li>
          <li><b>存在</b>：记录的应付职工薪酬在资产负债表日确实存在</li>
          <li><b>计价和分摊</b>：金额以恰当金额包括在财务报表中</li>
          <li><b>列报与披露</b>：已按CAS 9恰当列报</li>
        </ul>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="['HTML', 'OnlyOffice']" size="small" />
      <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
      <div class="ml-auto" style="display:flex;gap:8px;align-items:center;">
        <el-dropdown trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('detail')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('detail')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <template v-if="mode === 'HTML'">
      <!-- 分区1: 短期薪酬 -->
      <J1DetailSection
        :title="J1_SECTIONS[0].title"
        :rows="shortTermRows"
        :total-row="shortTermTotal"
        :is-dynamic="false"
        :is-readonly="isReadonly"
        section-key="shortTerm"
        @update-cell="(rowId, field, val) => updateCell('shortTerm', rowId, field, val)"
      />

      <!-- 分区2: 离职后福利 -->
      <J1DetailSection
        :title="J1_SECTIONS[1].title"
        :rows="postEmploymentRows"
        :total-row="postEmploymentTotal"
        :is-dynamic="false"
        :is-readonly="isReadonly"
        section-key="postEmployment"
        @update-cell="(rowId, field, val) => updateCell('postEmployment', rowId, field, val)"
      />

      <!-- 分区3: 辞退福利 -->
      <J1DetailSection
        :title="J1_SECTIONS[2].title"
        :rows="severanceRows"
        :total-row="severanceTotal"
        :is-dynamic="true"
        :is-readonly="isReadonly"
        section-key="severance"
        @update-cell="(rowId, field, val) => updateCell('severance', rowId, field, val)"
        @add-row="addRow('severance')"
        @remove-row="(rowId) => removeRow('severance', rowId)"
      />

      <!-- 全表合计 -->
      <el-card shadow="never" class="section-card">
        <div class="grand-total-bar">
          <span class="gt-label">应付职工薪酬合计</span>
          <span class="gt-item">未审期末: <b>{{ fmtNum(grandTotal.unadjEnd) }}</b></span>
          <span class="gt-item">审定期末: <b>{{ fmtNum(grandTotal.auditedEnd) }}</b></span>
        </div>
      </el-card>

      <!-- 审计说明 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">三、审计说明</span>
            <div class="header-right">
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                plain
                :loading="aiNoteLoading"
                @click="generateAiNote"
              >
                🤖 AI辅助
              </el-button>
            </div>
          </div>
        </template>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 5 }"
          placeholder="审计说明可概述：(1)程序的测试情况、结果；(2)拟调整事项及其调整分录、未调整事项及其影响；审计范围受到限制情况及其影响。"
          :disabled="isReadonly"
          @change="saveAuditText"
        />
      </el-card>

      <!-- 审计结论 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">四、审计结论</span>
            <div class="header-right">
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                plain
                :loading="aiConclusionLoading"
                @click="generateAiConclusion"
              >
                🤖 AI辅助
              </el-button>
            </div>
          </div>
        </template>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 3 }"
          placeholder="审计结论可参考：A、未见异常。B、除上述重大未调整事项外，其余未见异常。C、由于存在以下重大未调整事项（就审计范围受到限制无法获取充分、适当证据），不可确认。"
          :disabled="isReadonly"
          @change="saveAuditText"
        />
      </el-card>
    </template>

    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式（明细表J1-2）" />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><b>提示1：</b>审计说明可概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。</p>
        <p><b>提示2：</b>对于本期计提和支付的重大奖金、利润分享福利及其他易于导致错报的职工薪酬项目应当：</p>
        <p style="padding-left:16px;">（1）了解相关计提政策、审批流程的设计与执行有效性；（2）获取相关支持性文件；（3）验证计提依据是否充分、合理；（4）核对计算的准确性和完整性；（5）对异常波动、异常支付对象等进行分析；（6）对于尚未支付的项目，确定该项负债是否被正确计量；（7）执行截止测试，追踪至后续付款。</p>
        <p><b>提示3：关注带薪休假</b></p>
        <p style="padding-left:16px;">1.确定所有员工均已包含；2.确定企业确认带薪休假的方法是否正确；3.关注小时工资费用来源是否合理，并与相关的记录核对。</p>
        <p><b>提示4：对于设定提存计划的额外关注</b></p>
        <p style="padding-left:16px;">结合计提比例(倒检查)，确定代扣员工储存款的总额是否合理，是否按时归付缴纳。</p>
        <p><b>公式说明：</b>灰色底纹列为自动计算列。未审期末=期初+增加-减少；审定期初=未审期初+期初调整；审定增加=未审增加+账项增加；审定减少=未审减少+账项减少；审定期末=审定期初+审定增加-审定减少。负债贷方口径（CAS 9）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useJ1Detail, J1_SECTIONS } from '@/composables/workpaper/j1/useJ1Detail'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import J1DetailSection from './J1DetailSection.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, { item_id: string; conclusion: string | null; remark: string | null }>
  isReadonly?: boolean
  saveImmediate?: (items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>) => Promise<void>
}>()

const isReadonly = computed(() => props.isReadonly ?? false)

// Build allResponses ref from props or empty
const allResponsesRef = ref<Map<string, { item_id: string; conclusion: string | null; remark: string | null }>>(
  props.allResponses || new Map()
)

// Default save function (parent should provide)
async function defaultSave(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>): Promise<void> {
  // noop if parent doesn't provide
}

const {
  shortTermRows,
  postEmploymentRows,
  severanceRows,
  shortTermTotal,
  postEmploymentTotal,
  severanceTotal,
  grandTotal,
  auditNote,
  auditConclusion,
  updateCell,
  addRow,
  removeRow,
  saveAuditText,
} = useJ1Detail({
  allResponses: allResponsesRef,
  saveImmediate: props.saveImmediate || defaultSave,
  isReadonly: toRef(props, 'isReadonly') as any || ref(false),
})

const mode = ref('HTML')
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)

const totalRowCount = computed(() =>
  shortTermRows.value.length + postEmploymentRows.value.length + severanceRows.value.length
)

function fmtNum(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) importData('detail', file)
  }
  input.click()
}

// ─── AI 辅助生成 ────────────────────────────────────────────────────────────

const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

async function generateAiNote() {
  aiNoteLoading.value = true
  try {
    const context = buildAiContext()
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'audit-note',
      prompt: '请根据应付职工薪酬明细表J1-2的数据，生成审计说明。说明应概述：(1)程序的测试情况、结果；(2)拟调整事项及其调整分录、未调整事项及其影响；(3)审计范围受到限制情况及其影响。',
      context,
      existingContent: auditNote.value,
    })
    const generated = res.data?.data?.content || res.data?.content
    if (generated) {
      auditNote.value = generated
      saveAuditText()
      ElMessage.success('AI生成审计说明完成')
    }
  } catch (e) {
    ElMessage.warning('AI生成失败，请手动填写')
  } finally {
    aiNoteLoading.value = false
  }
}

async function generateAiConclusion() {
  aiConclusionLoading.value = true
  try {
    const context = buildAiContext()
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'audit-conclusion',
      prompt: '请根据应付职工薪酬明细表J1-2的数据和审计说明，生成审计结论。结论可参考：A、未见异常；B、除上述重大未调整事项外，其余未见异常；C、由于存在重大未调整事项，不可确认。',
      context,
      existingContent: auditConclusion.value,
    })
    const generated = res.data?.data?.content || res.data?.content
    if (generated) {
      auditConclusion.value = generated
      saveAuditText()
      ElMessage.success('AI生成审计结论完成')
    }
  } catch (e) {
    ElMessage.warning('AI生成失败，请手动填写')
  } finally {
    aiConclusionLoading.value = false
  }
}

function buildAiContext(): Record<string, string> {
  const ctx: Record<string, string> = {
    '底稿类型': 'J1-2 应付职工薪酬明细表',
    '科目': '2211 应付职工薪酬（贷方/负债类）',
    '短期薪酬审定期末': fmtNum(shortTermTotal.value.auditedEnd),
    '离职后福利审定期末': fmtNum(postEmploymentTotal.value.auditedEnd),
    '辞退福利审定期末': fmtNum(severanceTotal.value.auditedEnd),
    '全表审定期末': fmtNum(grandTotal.value.auditedEnd),
  }
  if (auditNote.value) ctx['已有审计说明'] = auditNote.value
  return ctx
}
</script>

<style scoped>
.j1-tab-detail { padding: 16px; }
.audit-objective { margin-bottom: 14px; }
:deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }
.mode-bar { display: flex; align-items: center; margin-bottom: 12px; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.ml-auto { margin-left: auto; }
.section-card { margin-bottom: 12px; }
:deep(.section-card .el-card__header) { padding: 8px 12px; }
:deep(.section-card .el-card__body) { padding: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 14px; }
.header-right { margin-left: auto; }
.grand-total-bar { display: flex; align-items: center; gap: 24px; padding: 8px 0; font-size: 14px; }
.gt-label { font-weight: 600; }
.gt-item b { color: #409eff; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 4px 0; }
.oo-placeholder { display: flex; align-items: center; justify-content: center; min-height: 300px; }
</style>
