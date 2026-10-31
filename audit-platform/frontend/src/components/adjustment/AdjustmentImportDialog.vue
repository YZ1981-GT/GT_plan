<template>
  <el-dialog v-model="visible" title="Excel 导入调整分录" width="980px" append-to-body :close-on-click-modal="false">
    <el-steps :active="step" finish-status="success" simple class="gt-adj-imp-steps">
      <el-step title="选择文件" />
      <el-step title="预检" />
      <el-step title="导入结果" />
    </el-steps>

    <template v-if="step === 0">
      <div class="gt-adj-imp-section">
        <div class="gt-adj-imp-label">1. 下载模板</div>
        <el-button size="small" plain :type="templateType === 'soe' ? 'primary' : ''" @click="emit('download-template', 'soe')">
          📘 国企版模板{{ templateType === 'soe' ? '（当前项目）' : '' }}
        </el-button>
        <el-button size="small" plain :type="templateType === 'listed' ? 'primary' : ''" @click="emit('download-template', 'listed')">
          📗 上市版模板{{ templateType === 'listed' ? '（当前项目）' : '' }}
        </el-button>
        <div class="gt-adj-imp-hint">
          模板含审计调整、重分类两张录入表和【项目科目库】。同一编号的多行为一笔；不填编号的连续行借贷平衡后自动成为一笔；
          金额精确到分、不能为负，同一行只填借方或贷方。
        </div>
      </div>
      <div class="gt-adj-imp-section">
        <div class="gt-adj-imp-label">2. 导入方式</div>
        <el-radio-group v-model="mode">
          <el-radio value="append">追加：每笔都新建为草稿（自动编号）</el-radio>
          <el-radio value="overwrite">按编号覆盖：同编号的草稿 / 已驳回分录整笔替换，其余新建</el-radio>
        </el-radio-group>
        <div v-if="mode === 'overwrite'" class="gt-adj-imp-hint">
          已提交复核、已批准或来自底稿同步的同编号分录不会被覆盖，预检会标「跳过」并写明原因。
        </div>
      </div>
      <div class="gt-adj-imp-section">
        <div class="gt-adj-imp-label">3. 选择文件</div>
        <el-upload v-model:file-list="fileList" drag :auto-upload="false" accept=".xlsx,.xlsm" :on-change="onFileChange"
          :on-remove="() => (file = null)">
          <div class="gt-adj-imp-drop">把填好的模板拖到这里，或点击选择（.xlsx）</div>
        </el-upload>
      </div>
    </template>

    <template v-else-if="step === 1 && preview">
      <el-alert v-for="e in preview.structure_errors" :key="e" type="error" :title="e" show-icon :closable="false" class="gt-adj-imp-alert" />
      <el-alert v-for="w in preview.warnings" :key="w" type="warning" :title="w" show-icon :closable="false" class="gt-adj-imp-alert" />
      <div class="gt-adj-imp-summary">
        <span>共 {{ preview.summary.total }} 笔：<b class="is-ok">{{ preview.summary.ok }}</b> 笔可导入</span>
        <span v-if="preview.summary.replace">（其中替换 {{ preview.summary.replace }} 笔）</span>
        <span>，<b class="is-err">{{ preview.summary.error }}</b> 笔有错误</span>
        <span v-if="preview.summary.skip">，<b>{{ preview.summary.skip }}</b> 笔将跳过</span>
        <span v-if="preview.example_skipped" class="gt-adj-imp-muted">（已忽略模板示例 {{ preview.example_skipped }} 行）</span>
        <span class="gt-adj-imp-spacer" />
        <el-checkbox v-model="onlyProblems" size="small">只看有问题的</el-checkbox>
      </div>
      <el-table :data="shownGroups" border size="small" max-height="430" row-key="key">
        <el-table-column type="expand" width="36">
          <template #default="{ row }">
            <table class="gt-adj-imp-lines">
              <tr v-for="(ln, i) in row.lines" :key="i">
                <td>{{ ln.label }}</td>
                <td>{{ ln.account_code || '（未匹配）' }} {{ ln.account_name }}</td>
                <td class="gt-amt">{{ Number(ln.debit) ? fmtAmount(ln.debit) : '' }}</td>
                <td class="gt-amt">{{ Number(ln.credit) ? fmtAmount(ln.credit) : '' }}</td>
              </tr>
            </table>
          </template>
        </el-table-column>
        <el-table-column label="编号" prop="adjustment_no" width="110" />
        <el-table-column label="类型" prop="adjustment_type" width="60" />
        <el-table-column label="摘要" prop="description" min-width="150" show-overflow-tooltip />
        <el-table-column label="来源行" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ rowsLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="借方合计" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.total_debit" /></template>
        </el-table-column>
        <el-table-column label="贷方合计" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.total_credit" /></template>
        </el-table-column>
        <el-table-column label="处理" width="64">
          <template #default="{ row }">
            <el-tag size="small" :type="ACTION_TAGS[row.action as string]">{{ ACTION_LABELS[row.action as string] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" min-width="230">
          <template #default="{ row }">
            <span v-if="row.ok" class="is-ok">✓ 可导入</span>
            <span v-else-if="row.skip_reason" class="gt-adj-imp-muted">{{ row.skip_reason }}</span>
            <div v-else class="is-err">
              <div v-for="e in row.errors" :key="e">{{ e }}</div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <template v-else-if="step === 2 && result">
      <el-result :icon="result.failed ? 'warning' : 'success'" :title="result.message"
        sub-title="导入的分录都是草稿，不计入试算表；提交复核并批准后才计入审定数。" class="gt-adj-imp-result" />
      <div v-if="result.failed_rows.length" class="gt-adj-imp-list">
        <div class="gt-adj-imp-label">失败（未导入）</div>
        <div v-for="f in result.failed_rows" :key="`${f.adj_no}-${f.row}`" class="is-err">
          {{ f.adj_no }}（第 {{ (f.rows_in_group || [f.row]).join('、') }} 行）：{{ f.error }}
        </div>
      </div>
      <div v-if="result.skipped_rows?.length" class="gt-adj-imp-list">
        <div class="gt-adj-imp-label">跳过</div>
        <div v-for="s in result.skipped_rows" :key="`${s.adj_no}-${s.row}`" class="gt-adj-imp-muted">{{ s.adj_no }}：{{ s.reason }}</div>
      </div>
      <div v-if="result.warnings?.length" class="gt-adj-imp-list">
        <div v-for="w in result.warnings" :key="w" class="gt-adj-imp-muted">{{ w }}</div>
      </div>
    </template>

    <template #footer>
      <template v-if="step === 0">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :disabled="!file || year == null" :loading="loading === 'preview'" @click="runPreview">预检</el-button>
      </template>
      <template v-else-if="step === 1">
        <el-button @click="step = 0">上一步</el-button>
        <el-button type="primary" :disabled="!preview?.summary.ok || !canEdit" :loading="loading === 'import'"
          :title="canEdit ? '' : '项目已归档或无编辑权限'" @click="runImport">导入 {{ preview?.summary.ok || 0 }} 笔</el-button>
      </template>
      <template v-else>
        <el-button @click="restart">继续导入</el-button>
        <el-button v-if="result?.created?.length && canEdit" type="primary" plain @click="submitImported">
          提交复核（本次 {{ result.created.length }} 笔）
        </el-button>
        <el-button type="primary" @click="visible = false">完成</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * Excel 导入调整分录（spec adjustment-hall-entry-review-closure 需求 2）：下载模板 → 选文件与方式 → 预检（逐笔解析结果，
 * 不写库）→ 导入（逐笔独立保存，一笔失败不影响其他笔）→ 结果停留在弹窗，可一键提交本次导入的分录复核。
 */
import { computed, ref } from 'vue'
import type { UploadFile, UploadUserFile } from 'element-plus'
import {
  importAdjustmentsFile, previewAdjustmentImport, type AdjustmentImportPreview, type AdjustmentImportPreviewGroup,
  type AdjustmentImportResult,
} from '@/services/auditPlatformApi'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { fmtAmount } from '@/utils/formatters'
import { reportAdjustmentError } from '@/composables/useAdjustmentHallActions'

const props = withDefaults(defineProps<{
  projectId: string
  year: number | null
  templateType?: string
  canEdit?: boolean
}>(), { templateType: '', canEdit: true })

const emit = defineEmits<{
  'download-template': [type: 'soe' | 'listed']
  imported: [result: AdjustmentImportResult]
  'submit-review': [rows: Array<{ entry_group_id: string; adjustment_no: string | null }>]
}>()

/** 预检「处理」列：create 新建 / replace 覆盖模式下整笔替换 / skip 跳过（附原因） */
const ACTION_LABELS: Record<string, string> = { create: '新建', replace: '替换', skip: '跳过' }
const ACTION_TAGS: Record<string, 'success' | 'warning' | 'info'> = { create: 'success', replace: 'warning', skip: 'info' }

const visible = ref(false)
const step = ref(0)
const mode = ref<'append' | 'overwrite'>('append')
const file = ref<File | null>(null)
const fileList = ref<UploadUserFile[]>([])
const preview = ref<AdjustmentImportPreview | null>(null)
const result = ref<AdjustmentImportResult | null>(null)
const loading = ref<'' | 'preview' | 'import'>('')
const onlyProblems = ref(false)

const shownGroups = computed(() => (preview.value?.groups || []).filter((g) => !onlyProblems.value || !g.ok))

function rowsLabel(g: AdjustmentImportPreviewGroup): string {
  const label = g.lines[0]?.label || ''
  const sheet = label.includes(' 第 ') ? label.split(' 第 ')[0] : ''
  return `${sheet ? `${sheet} ` : ''}第 ${g.rows.join('、')} 行`
}

function onFileChange(uploadFile: UploadFile) {
  fileList.value = [uploadFile]
  file.value = uploadFile.raw || null
}

function restart() {
  step.value = 0
  file.value = null
  fileList.value = []
  preview.value = null
  result.value = null
  onlyProblems.value = false
}

function open() {
  restart()
  mode.value = 'append'
  visible.value = true
}

async function runPreview() {
  if (!file.value || props.year == null) return
  loading.value = 'preview'
  try {
    preview.value = await previewAdjustmentImport(props.projectId, props.year, mode.value, file.value)
    onlyProblems.value = false
    step.value = 1
  } catch (err) {
    reportAdjustmentError(err, '预检')
  } finally {
    loading.value = ''
  }
}

async function runImport() {
  if (!file.value || props.year == null) return
  loading.value = 'import'
  try {
    result.value = await importAdjustmentsFile(props.projectId, props.year, mode.value, file.value)
    step.value = 2
    emit('imported', result.value)
  } catch (err) {
    reportAdjustmentError(err, '导入')
  } finally {
    loading.value = ''
  }
}

function submitImported() {
  const rows = (result.value?.created || []).map((c) => ({ entry_group_id: c.entry_group_id, adjustment_no: c.adjustment_no }))
  visible.value = false
  emit('submit-review', rows)
}

defineExpose({ open })
</script>

<style scoped>
.gt-adj-imp-steps { margin-bottom: 14px; }
.gt-adj-imp-section { margin-bottom: 16px; }
.gt-adj-imp-label { font-weight: 600; margin-bottom: 6px; }
.gt-adj-imp-hint { margin-top: 6px; font-size: var(--gt-font-size-xs); line-height: 1.6; color: var(--gt-color-text-tertiary); }
.gt-adj-imp-drop { padding: 18px 0; color: var(--gt-color-text-secondary); }
.gt-adj-imp-alert { margin-bottom: 8px; }
.gt-adj-imp-summary { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin-bottom: 8px; font-size: var(--gt-font-size-sm); }
.gt-adj-imp-spacer { flex: 1; }
.gt-adj-imp-muted { color: var(--gt-color-text-tertiary); }
.gt-adj-imp-lines { width: 100%; border-collapse: collapse; font-size: var(--gt-font-size-xs); }
.gt-adj-imp-lines td { padding: 3px 8px; border-bottom: 1px solid var(--gt-color-border-light); }
.gt-adj-imp-lines td.gt-amt { text-align: right; width: 130px; }
.gt-adj-imp-result { padding: 8px 0; }
.gt-adj-imp-list { margin-top: 10px; font-size: var(--gt-font-size-sm); line-height: 1.7; }
.is-ok { color: var(--gt-color-success); font-weight: 600; }
.is-err { color: var(--gt-color-coral); }
</style>
