<template>
  <div class="h8-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：确认使用权资产附注披露（国有企业）的租赁分类及变动明细完整、准确，符合 CAS21 及国资监管信息公开要求。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露（国企）：按国资委信息公开要求和CAS21准则，披露使用权资产明细及变动。国企版含更详细的租赁分类信息。32行255列。</p>
    </div>

    <!-- 索引 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-disc-S" />
    </div>

    <!-- 披露摘要 -->
    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="section-title">
          <span>使用权资产附注披露（国企版，32行255列）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'disclosure-soe')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'disclosure-soe')">复核</el-button>
          </div>
        </div>
      </template>
      <div class="disclosure-info">
        <p>国企版含：详细租赁分类（房屋/设备/车辆/其他）× 变动明细（原值/折旧/减值）× 多期对比。数据量大建议使用OO编辑。</p>
      </div>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>附注格式（32行255列）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'附注披露信息（国企）'"
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
        <li>国企版附注需分类更细（房屋/设备/车辆/其他各自列示）</li>
        <li>含多期对比数据（当期/上期）</li>
        <li>255列宽表建议直接在OO中操作</li>
        <li>数据应与H8-1审定表保持一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisclosureSoe.vue — 附注披露（国企）
 * 32行255列，OO渲染wrapper（宽表）
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
const AUDIT_NOTE_KEY = 'H8-disclosure-soe-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-disclosure-soe-audit-conclusion'
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
.h8-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }

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
