<template>
  <div class="h8-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：确认使用权资产附注披露（上市公司）的分类、原值/累计折旧/减值/净值变动及到期日分析等信息完整、准确，符合 CAS21 及证监会信息披露要求。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露（上市公司）：按CAS21准则及证监会信息披露要求，披露使用权资产分类、折旧金额、期初期末余额变动等信息。48行7列。</p>
    </div>

    <!-- 索引 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-disc-L" />
    </div>

    <!-- 披露摘要 -->
    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="section-title">
          <span>使用权资产附注披露（上市公司，48行7列）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'disclosure-listed')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'disclosure-listed')">复核</el-button>
          </div>
        </div>
      </template>
      <div class="disclosure-info">
        <p>披露内容：各类使用权资产原值/累计折旧/减值/净值变动表 + 到期日分析 + 未纳入计量的可变租金</p>
      </div>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>附注格式（48行7列）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'附注披露信息（上市公司）'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载">
            <template #image><span style="font-size:40px">📋</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="请输入审计说明..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="请输入审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注应按资产类别分项列示</li>
        <li>应披露：原值、累计折旧、减值、净值的期初/增加/减少/期末</li>
        <li>还应披露：未纳入计量的可变租金支出、短期/低价值豁免金额</li>
        <li>数据应与H8-1审定表一致（EventBus联动）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisclosureListed.vue — 附注披露（上市公司）
 * 48行7列，OO渲染wrapper
 * Spec: Task 4.10 | Requirements: 1.2
 */
import { ref, watch, defineAsyncComponent } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() =>
  import('../../GtOnlyOfficeSheet.vue').catch(() => ({ template: '<div>OO不可用</div>' })),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const showOO = ref(true)

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-disclosure-listed-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-disclosure-listed-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}
</script>

<style scoped>
.h8-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.summary-card { margin-bottom: 16px; }
.disclosure-info { font-size: 12px; color: var(--el-text-color-secondary); }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 500px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
