<script setup lang="ts">
/**
 * GtB22CDesignEffectiveness — B22C 企业层面控制设计有效性评价（缺陷汇总表）
 *
 * 致同 2025 修订版 B22C 源模板「评价设计有效性-缺陷汇总表」的结构化实现。
 * 按 5 个要素区块汇总各要素识别出的控制缺陷，判断是否构成值得关注的缺陷（CAS 1152）。
 */
import { ref, computed, toRef, watch, provide, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  useB22CDesignEffectiveness,
  BLOCK_KEYS,
  SIGNIFICANT_INDICATORS,
  SEVERITY_FACTORS,
  SEVERITY_VALUES,
  type BlockKey,
  type DeficiencyField,
} from './composables/useB22CDesignEffectiveness'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtReviewTrigger from './GtReviewTrigger.vue'
import GtWpVersionTrail from './version-trail/GtWpVersionTrail.vue'
import { useWorkpaperEntryDualMode } from './composables/useWorkpaperEntryDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Props / Emits ────────────────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const {
  loading,
  saving,
  overallNote,
  blocks,
  overallHasSignificant,
  stats,
  indicatorChecks,
  factorChecks,
  suggestedSignificant,
  indicatorCheckedCount,
  factorCheckedCount,
  loadAll,
  loadFromUpstream,
  addDeficiency,
  removeDeficiency,
  setDeficiencyField,
  setSectionSignificant,
  setSectionNote,
  setOverallNote,
  setIndicatorCheck,
  setFactorCheck,
} = useB22CDesignEffectiveness(wpIdRef, projectIdRef)

function onIndicatorChange(idx: number, val: boolean) {
  if (props.readonly) return
  setIndicatorCheck(idx, val)
}
function onFactorChange(idx: number, val: boolean) {
  if (props.readonly) return
  setFactorCheck(idx, val)
}

// ─── 版本链 + 双模式 + 复核对话 ───────────────────────────────────────────────
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = useWorkpaperVersionToolbar(wpIdRef)

const dualMode = useWorkpaperEntryDualMode({
  reloadAllResponses: async () => { await loadAll() },
  resolveOoSheetName: () => props.wpCode || 'B22C',
})
const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: string) => { void dualMode.switchMode(v as 'html' | 'onlyoffice') },
})
const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  { label: '在线编辑(OnlyOffice)', value: 'onlyoffice' as const, disabled: !dualMode.ooAvailable.value },
])
function onOoFallback(): void { void dualMode.switchMode('html') }

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef as any)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) scheduleAutoSnapshot?.()
})

// ─── Local state ────────────────────────────────────────────────────────────

const pulling = ref(false)

// ─── Handlers ─────────────────────────────────────────────────────────────────

function onAddDeficiency(blockKey: BlockKey) {
  if (props.readonly) return
  addDeficiency(blockKey)
  emit('save')
}

function onRemoveDeficiency(blockKey: BlockKey, idx: number) {
  if (props.readonly) return
  removeDeficiency(blockKey, idx)
  emit('save')
}

function onDeficiencyFieldChange(
  blockKey: BlockKey,
  idx: number,
  field: DeficiencyField,
  value: string | boolean
) {
  if (props.readonly) return
  setDeficiencyField(blockKey, idx, field, value)
  emit('save')
}

function onSectionSignificantChange(blockKey: BlockKey, val: boolean | null) {
  if (props.readonly) return
  setSectionSignificant(blockKey, val)
  emit('save')
}

function onSectionNoteChange(blockKey: BlockKey, val: string) {
  if (props.readonly) return
  setSectionNote(blockKey, val)
}

function onOverallNoteChange(val: string) {
  if (props.readonly) return
  setOverallNote(val)
}

/** 从 B22A/B22B 带入缺陷 */
async function handlePullUpstream() {
  if (props.readonly || pulling.value) return
  pulling.value = true
  try {
    const b22aResponses = await fetchUpstreamResponses('B22A')
    const b22bResponses = await fetchUpstreamResponses('B22B')

    if (b22aResponses.length === 0 && b22bResponses.length === 0) {
      ElMessage.warning('未找到 B22A/B22B 底稿数据')
      return
    }

    const { added } = loadFromUpstream(b22aResponses, b22bResponses)
    if (added > 0) {
      ElMessage.success(`已带入 ${added} 条上游缺陷`)
      emit('save')
      // 滚动到最后一个区块的新增条目
      setTimeout(() => {
        const cards = document.querySelectorAll('.b22c-block-card')
        if (cards.length > 0) {
          const last = cards[cards.length - 1]
          last.scrollIntoView({ behavior: 'smooth', block: 'center' })
          last.classList.add('b22c-highlight')
          setTimeout(() => last.classList.remove('b22c-highlight'), 2000)
        }
      }, 100)
    } else {
      ElMessage.info('无新增缺陷（已带入或上游无缺陷）')
    }
  } catch {
    ElMessage.error('带入上游缺陷失败')
  } finally {
    pulling.value = false
  }
}

/** 先按 wp_code 查 wpId 再 GET 其 checklist-responses */
async function fetchUpstreamResponses(wpCode: string): Promise<any[]> {
  try {
    const res = await api.get(`/api/projects/${props.projectId}/workpapers`, {
      params: { wp_code: wpCode },
    })
    const workpapers: any[] = Array.isArray(res) ? res : res?.data ?? []
    if (workpapers.length === 0) return []
    const upstreamWpId = workpapers[0].id || workpapers[0].wp_id
    if (!upstreamWpId) return []
    const respRes = await api.get(`/api/workpapers/${upstreamWpId}/checklist-responses`)
    const responses: any[] = Array.isArray(respRes) ? respRes : respRes?.data ?? []
    return responses.map((r) => ({
      item_id: r.item_id,
      conclusion: r.conclusion ?? null,
      remark: r.remark ?? null,
      wp_ref: r.wp_ref ?? null,
    }))
  } catch {
    return []
  }
}

// ─── EventBus（可选：控制缺陷变更时刷新） ──────────────────────────────────────

function onDeficiencyChanged() {
  // 上游缺陷变更时重新加载已存数据（不自动覆盖编辑，仅刷新持久层）
  loadAll()
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  ;(eventBus as any).on('control:deficiency-changed', onDeficiencyChanged)
})

onBeforeUnmount(() => {
  ;(eventBus as any).off('control:deficiency-changed', onDeficiencyChanged)
})
</script>

<template>
  <div class="gt-b22c-design-effectiveness" v-loading="loading">
    <!-- 版本历史 -->
    <GtWpVersionTrail ref="versionTrailRef" :wp-id="wpId" />

    <!-- 双模式工具栏（参照 D4：健康检查拉取成功才允许切 OnlyOffice） -->
    <div class="b22-mode-toolbar">
      <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
      <el-tag v-if="dualMode.checking.value" size="small" type="info">OnlyOffice 检测中…</el-tag>
      <el-tag v-else-if="dualMode.ooAvailable.value" size="small" type="success">OnlyOffice 就绪（拉取成功）</el-tag>
      <el-tag v-else size="small" type="warning">OnlyOffice 不可用（健康检查未通过）</el-tag>
      <el-button size="small" text type="primary" @click="openVersionHistory">版本历史</el-button>
    </div>

    <!-- OnlyOffice 整册视图 -->
    <GtOnlyOfficeSheet
      v-if="renderMode === 'onlyoffice'"
      :key="wpCode"
      :wp-id="props.wpId"
      :sheet-name="props.wpCode || 'B22C'"
      :project-id="props.projectId"
      :whole-workbook="true"
      :readonly="props.readonly"
      @fallback="onOoFallback"
    />

    <template v-else>
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="b22c-objective">
      <template #title>
        评价企业层面控制的设计有效性，汇总各要素识别出的控制缺陷并判断是否构成值得关注的缺陷（CAS 1152）。
      </template>
    </el-alert>

    <!-- 值得关注缺陷判断矩阵（源模板指引，可勾选，驱动结论建议） -->
    <el-card class="b22c-judgment-card" shadow="never" :body-style="{ padding: '14px 16px' }">
      <template #header>
        <div class="judgment-header">
          <span class="block-title">值得关注缺陷判断矩阵（CAS 1152）</span>
          <el-tag v-if="suggestedSignificant" type="danger" size="small">系统建议：存在值得关注的缺陷</el-tag>
          <el-tag v-else type="info" size="small">系统建议：暂无值得关注缺陷迹象</el-tag>
        </div>
      </template>

      <div class="judgment-section">
        <p class="judgment-subtitle">
          一、存在下列迹象通常表明存在值得关注的缺陷（勾选=该迹象存在）
          <span class="judgment-count">已勾选 {{ indicatorCheckedCount }}/{{ SIGNIFICANT_INDICATORS.length }}</span>
        </p>
        <div class="judgment-checks">
          <el-checkbox
            v-for="(txt, i) in SIGNIFICANT_INDICATORS"
            :key="`ind-${i}`"
            :model-value="indicatorChecks[i]"
            :disabled="readonly"
            class="judgment-check"
            @update:model-value="(v: boolean) => onIndicatorChange(i, v)"
          >
            {{ txt }}
          </el-checkbox>
        </div>
      </div>

      <div class="judgment-section">
        <p class="judgment-subtitle">
          二、判断严重程度时应考虑的因素（勾选=已在职业判断中考虑）
          <span class="judgment-count">已考虑 {{ factorCheckedCount }}/{{ SEVERITY_FACTORS.length }}</span>
        </p>
        <div class="judgment-checks">
          <el-checkbox
            v-for="(txt, i) in SEVERITY_FACTORS"
            :key="`fac-${i}`"
            :model-value="factorChecks[i]"
            :disabled="readonly"
            class="judgment-check"
            @update:model-value="(v: boolean) => onFactorChange(i, v)"
          >
            {{ txt }}
          </el-checkbox>
        </div>
      </div>

      <el-alert
        v-if="suggestedSignificant && !overallHasSignificant"
        type="warning"
        :closable="false"
        show-icon
        class="judgment-hint"
      >
        <template #title>
          已勾选值得关注缺陷迹象，但各区块/整体结论尚未标记"存在值得关注的缺陷"，请复核区块小结与整体结论。
        </template>
      </el-alert>
    </el-card>

    <!-- 带入上游缺陷 -->
    <div class="b22c-toolbar">
      <el-button type="primary" :loading="pulling" :disabled="readonly" @click="handlePullUpstream">
        从 B22A/B22B 带入缺陷
      </el-button>
      <span class="toolbar-hint">从企业层面控制了解（B22A）与缺陷评价（B22B）自动汇总识别出的缺陷</span>
    </div>

    <!-- 5 个要素区块 -->
    <el-card
      v-for="block in blocks"
      :key="block.key"
      class="b22c-block-card"
      shadow="never"
      :body-style="{ padding: '16px' }"
    >
      <template #header>
        <div class="block-header">
          <span class="block-title">{{ block.name }}</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="readonly"
            @click="onAddDeficiency(block.key)"
          >
            新增缺陷
          </el-button>
        </div>
      </template>

      <!-- 缺陷条目表 -->
      <el-table :data="block.deficiencies" size="small" border class="b22c-def-table">
        <el-table-column type="index" label="序号" width="56" align="center" />
        <el-table-column label="缺陷描述" min-width="240">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.desc"
              :disabled="readonly"
              type="textarea"
              :autosize="{ minRows: 2 }"
              placeholder="描述识别出的控制缺陷"
              @update:model-value="(v: string) => onDeficiencyFieldChange(block.key, $index, 'desc', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="控制缺陷" width="90" align="center">
          <template #default="{ row, $index }">
            <el-checkbox
              :model-value="row.isControlDeficiency"
              :disabled="readonly"
              @update:model-value="(v: boolean) => onDeficiencyFieldChange(block.key, $index, 'isControlDeficiency', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="严重程度" width="130" align="center">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.severity"
              :disabled="readonly"
              size="small"
              clearable
              placeholder="未评定"
              @update:model-value="(v: string) => onDeficiencyFieldChange(block.key, $index, 'severity', v)"
            >
              <el-option v-for="s in SEVERITY_VALUES" :key="s" :label="s" :value="s" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="值得关注的缺陷" width="120" align="center">
          <template #default="{ row }">
            <!-- 派生显示：severity∈{重大,重要}→是（CAS1152，severity 为权威，只读） -->
            <el-tag v-if="row.isSignificant" type="danger" size="small">是</el-tag>
            <span v-else class="derived-no">否</span>
          </template>
        </el-table-column>
        <el-table-column label="重要职业判断" min-width="220">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.judgment"
              :disabled="readonly"
              type="textarea"
              :autosize="{ minRows: 2 }"
              placeholder="记录重要的职业判断"
              @update:model-value="(v: string) => onDeficiencyFieldChange(block.key, $index, 'judgment', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="72" align="center">
          <template #default="{ $index }">
            <el-button
              size="small"
              type="danger"
              link
              :disabled="readonly"
              @click="onRemoveDeficiency(block.key, $index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <span class="empty-hint">暂无缺陷条目</span>
        </template>
      </el-table>

      <!-- 区块小结 -->
      <div class="block-summary">
        <div class="summary-row">
          <span class="summary-label">汇总来看，所识别出的缺陷是否表明存在值得关注的缺陷：</span>
          <el-radio-group
            :model-value="block.sectionSignificant"
            :disabled="readonly"
            @change="(v: boolean) => onSectionSignificantChange(block.key, v)"
          >
            <el-radio :value="true">是</el-radio>
            <el-radio :value="false">否</el-radio>
          </el-radio-group>
        </div>
        <el-input
          :model-value="block.sectionNote"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2 }"
          placeholder="说明（可选）"
          class="summary-note"
          @update:model-value="(v: string) => onSectionNoteChange(block.key, v)"
        />
      </div>
    </el-card>

    <!-- 整体结论 -->
    <el-card class="b22c-overall-card" shadow="never">
      <template #header>
        <span class="block-title">整体结论</span>
        <GtReviewTrigger section-id="B22C-overall-note" label="💬 复核" />
      </template>

      <div class="overall-stats">
        <el-tag type="warning" size="large">控制缺陷 {{ stats.controlDeficiencyCount }} 项</el-tag>
        <el-tag type="danger" size="large">值得关注的缺陷 {{ stats.significantCount }} 项</el-tag>
      </div>

      <el-alert
        v-if="overallHasSignificant"
        type="warning"
        :closable="false"
        show-icon
        class="overall-warning"
      >
        <template #title>
          存在值得关注的缺陷，需与项目合伙人及治理层沟通（CAS 1152）
        </template>
      </el-alert>

      <el-input
        :model-value="overallNote"
        :disabled="readonly"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="整体评价说明（可选）"
        class="overall-note"
        @update:model-value="onOverallNoteChange"
      />
    </el-card>

    <!-- 保存状态提示 -->
    <div v-if="saving" class="b22c-saving-indicator">
      <el-tag type="info" size="small">保存中...</el-tag>
    </div>
    </template>
  </div>
</template>

<style scoped>
.gt-b22c-design-effectiveness {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
  font-size: 13px;
  color: #303133;
}

/* 全局字号归一 13px */
.gt-b22c-design-effectiveness :deep(.el-table),
.gt-b22c-design-effectiveness :deep(.el-table .cell),
.gt-b22c-design-effectiveness :deep(.el-input__inner),
.gt-b22c-design-effectiveness :deep(.el-textarea__inner),
.gt-b22c-design-effectiveness :deep(.el-checkbox__label),
.gt-b22c-design-effectiveness :deep(.el-radio__label) {
  font-size: 13px;
}

/* 区块标题左侧主色强调条 */
.gt-b22c-design-effectiveness :deep(.el-card__header) .block-title {
  border-left: 3px solid var(--el-color-primary, #3B82F6);
  padding-left: 8px;
  display: inline-block;
  line-height: 1.3;
}

.b22c-objective {
  margin-bottom: 12px;
}

/* 双模式工具栏 */
.b22-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.b22c-overall-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.b22c-judgment-card {
  margin-bottom: 16px;
}
.b22c-judgment-card :deep(.el-card__header) {
  padding: 10px 16px;
}
.judgment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.judgment-section {
  margin-bottom: 10px;
}
.judgment-subtitle {
  font-weight: 600;
  font-size: 13px;
  color: #606266;
  margin: 4px 0 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.judgment-count {
  font-weight: 400;
  font-size: 12px;
  color: #909399;
}
.judgment-checks {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 4px 16px;
}
.judgment-check {
  height: auto;
  white-space: normal;
  line-height: 1.5;
  margin-right: 0;
}
.judgment-hint {
  margin-top: 8px;
}

.b22c-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.toolbar-hint {
  font-size: 12px;
  color: #909399;
}

.b22c-block-card {
  margin-bottom: 16px;
}

.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.block-title {
  font-weight: 600;
  font-size: 14px;
}

.b22c-def-table {
  width: 100%;
}

.empty-hint {
  color: #909399;
  font-size: 13px;
}

.derived-no {
  color: #909399;
  font-size: 13px;
}

.block-summary {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
}

.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.summary-label {
  font-size: 13px;
  color: #606266;
}

.summary-note {
  margin-top: 4px;
}

.b22c-overall-card {
  margin-bottom: 16px;
}

.overall-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.overall-warning {
  margin-bottom: 12px;
}

.overall-note {
  margin-top: 4px;
}

.b22c-saving-indicator {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 100;
}

/* 带入新增高亮动画 */
.b22c-highlight {
  animation: b22c-flash 2s ease-out;
}
@keyframes b22c-flash {
  0% { box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.5); }
  100% { box-shadow: none; }
}
</style>
