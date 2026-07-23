<script setup lang="ts">
/**
 * GtB22BControlMatrix — B22B 企业层面控制矩阵登记册（致同源模板 B22B 真实结构）
 *
 * 方案 A：B22B 恢复为控制矩阵登记册（12 列可编辑表），取代原缺陷评价表。
 *
 * 复用快赢范式（对齐 GtB22BDeficiencyEvaluation.vue）：
 * - 双模式（useWorkpaperEntryDualMode + mode-toolbar + 健康 tag + GtOnlyOfficeSheet）
 * - 版本链（useWorkpaperVersionToolbar + GtWpVersionTrail + 版本历史按钮）
 * - 复核入口（GtReviewTrigger + useWorkpaperReviewThreads + provide getThreadDot/getRowDot）
 */
import { ref, computed, toRef, watch, provide, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  useB22BControlMatrix,
  ELEMENT_OPTIONS,
  ANTI_FRAUD_OPTIONS,
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
  type ControlPoint,
} from './composables/useB22BControlMatrix'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtReviewTrigger from './GtReviewTrigger.vue'
import GtWpVersionTrail from './version-trail/GtWpVersionTrail.vue'
import { useWorkpaperEntryDualMode } from './composables/useWorkpaperEntryDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

// ─── Props / Emits ─────────────────────────────────────────────────────────

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

// ─── Composable ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const {
  rows,
  loading,
  saving,
  loadAll,
  addRow,
  removeRow,
  updateField,
  pullFromB22A,
} = useB22BControlMatrix(wpIdRef, projectIdRef)

const isReadonly = computed(() => !!props.readonly)

// ─── 版本链 + 双模式 + 复核对话 ───────────────────────────────────────────────

const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = useWorkpaperVersionToolbar(wpIdRef)

const dualMode = useWorkpaperEntryDualMode({
  reloadAllResponses: async () => { await loadAll() },
  resolveOoSheetName: () => props.wpCode || 'B22B',
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

// 保存完成 → 触发版本快照
watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) scheduleAutoSnapshot?.()
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────

function handleAddRow(): void {
  if (isReadonly.value) return
  addRow()
  emit('save')
}

async function handleRemoveRow(index: number): Promise<void> {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm('确认删除该控制行？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  removeRow(index)
  emit('save')
}

function handleFieldChange(index: number, field: keyof ControlPoint, value: string): void {
  if (isReadonly.value) return
  updateField(index, field, value)
  emit('save')
}

async function handlePullFromB22A(): Promise<void> {
  if (isReadonly.value) return
  const added = await pullFromB22A()
  if (added > 0) emit('save')
}

// ─── 客户端 xlsx 导出（对齐 12 列）───────────────────────────────────────────

const REGISTER_COLUMNS: { key: keyof ControlPoint; label: string; width?: number }[] = [
  { key: 'element', label: '要素', width: 14 },
  { key: 'subCategory', label: '子类别', width: 14 },
  { key: 'code', label: '编号', width: 10 },
  { key: 'controlName', label: '控制名称', width: 22 },
  { key: 'description', label: '详细控制描述', width: 40 },
  { key: 'antiFraud', label: '是否为反舞弊控制', width: 12 },
  { key: 'frequency', label: '控制频率', width: 12 },
  { key: 'performer', label: '执行人', width: 14 },
  { key: 'competence', label: '执行内部控制的人员的知识经验技能', width: 24 },
  { key: 'relatedRisk', label: '与控制相关的风险', width: 14 },
  { key: 'nature', label: '自动/人工', width: 12 },
  { key: 'itApp', label: 'IT应用名称', width: 16 },
]

async function exportControlMatrix(): Promise<void> {
  if (rows.value.length === 0) {
    ElMessage.warning('暂无控制可导出，请先新增控制或从 B22A 带入')
    return
  }
  try {
    const XLSX = await import('xlsx')
    const aoa = [
      REGISTER_COLUMNS.map((c) => c.label),
      ...rows.value.map((r) => REGISTER_COLUMNS.map((c) => (r[c.key] as string) ?? '')),
    ]
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    ws['!cols'] = REGISTER_COLUMNS.map((c) => ({ wch: c.width ?? 14 }))
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '企业层面控制矩阵')
    XLSX.writeFile(wb, `B22B_企业层面控制矩阵_${props.year || ''}.xlsx`)
    ElMessage.success(`已导出 ${rows.value.length} 项控制`)
  } catch (e) {
    console.error('[B22B] 控制矩阵导出失败', e)
    ElMessage.error('导出失败')
  }
}

// ─── AI 辅助（暂不接入，纯结构表）────────────────────────────────────────────

// ─── Lifecycle ────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})

onBeforeUnmount(() => {
  // composable 内 onScopeDispose 已 flush
})
</script>

<template>
  <div class="gt-b22b-control-matrix" v-loading="loading">
    <!-- 版本历史 -->
    <GtWpVersionTrail ref="versionTrailRef" :wp-id="wpId" />

    <!-- 双模式工具栏 -->
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
      :sheet-name="props.wpCode || 'B22B'"
      :project-id="props.projectId"
      :whole-workbook="true"
      :readonly="isReadonly"
      @fallback="onOoFallback"
    />

    <template v-else>
      <!-- 审计目标 -->
      <el-alert :closable="false" type="info" show-icon class="b22b-objective">
        <template #title>
          <strong>审计目标：</strong>登记被审计单位企业层面控制矩阵，汇总各要素关键控制的名称、描述、
          频率、执行人、是否反舞弊、自动/人工、相关风险及 IT 应用，作为控制了解与后续测试的基础（CAS 1211、CAS 1231）。
        </template>
      </el-alert>

      <!-- 编制提示 -->
      <details class="b22b-tips">
        <summary>编制提示（控制矩阵登记册）</summary>
        <div class="tips-body">
          <p>本表为企业层面控制矩阵登记册，12 列严格对齐致同源模板。每行登记一项关键控制：</p>
          <ul>
            <li><strong>要素</strong>：控制环境 / 风险评估过程 / 信息与沟通 / 监督 / IT一般控制。</li>
            <li><strong>是否为反舞弊控制</strong>：识别与舞弊风险应对相关的控制（CAS 1141）。</li>
            <li><strong>控制频率 / 执行人 / 知识经验技能</strong>：评价控制执行的胜任能力与频率。</li>
            <li><strong>自动/人工 与 IT应用名称</strong>：判断对 IT 一般控制（C22 ITGC）的依赖程度。</li>
          </ul>
          <p>可点击「从 B22A 带入」，将 B22A 各要素已了解的控制点自动填入本矩阵（仅填空、去重，不覆盖已编辑行）。</p>
        </div>
      </details>

      <!-- 工具栏 -->
      <div class="matrix-toolbar">
        <div class="toolbar-left">
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="isReadonly"
            @click="handleAddRow"
          >
            + 新增控制
          </el-button>
          <el-button
            size="small"
            :disabled="isReadonly"
            @click="handlePullFromB22A"
          >
            从 B22A 带入
          </el-button>
          <el-button
            size="small"
            :disabled="rows.length === 0"
            @click="exportControlMatrix"
          >
            导出控制矩阵 (xlsx)
          </el-button>
        </div>
        <div class="toolbar-right">
          <GtReviewTrigger section-id="B22B-matrix" label="💬 复核" />
          <el-tag type="info" size="small">共 {{ rows.length }} 项控制</el-tag>
          <el-tag v-if="saving" type="info" size="small">保存中...</el-tag>
        </div>
      </div>

      <!-- 12 列控制矩阵 -->
      <el-table
        :data="rows"
        border
        size="small"
        class="matrix-table"
        max-height="620"
        empty-text="暂无控制，点击「新增控制」或「从 B22A 带入」"
      >
        <el-table-column type="index" label="#" width="46" fixed="left" />

        <el-table-column label="要素" width="130">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.element"
              :disabled="isReadonly"
              placeholder="选择要素"
              size="small"
              @change="(v: string) => handleFieldChange($index, 'element', v)"
            >
              <el-option v-for="o in ELEMENT_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="子类别" width="130">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.subCategory"
              :disabled="isReadonly"
              size="small"
              placeholder="子类别"
              @input="(v: string) => handleFieldChange($index, 'subCategory', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="编号" width="100">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.code"
              :disabled="isReadonly"
              size="small"
              placeholder="编号"
              @input="(v: string) => handleFieldChange($index, 'code', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="控制名称" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.controlName"
              :disabled="isReadonly"
              size="small"
              placeholder="控制名称"
              @input="(v: string) => handleFieldChange($index, 'controlName', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="详细控制描述" min-width="280">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.description"
              :disabled="isReadonly"
              type="textarea"
              :autosize="{ minRows: 2 }"
              size="small"
              placeholder="详细控制描述"
              @input="(v: string) => handleFieldChange($index, 'description', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="是否为反舞弊控制" width="130">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.antiFraud"
              :disabled="isReadonly"
              placeholder="是/否"
              size="small"
              clearable
              @change="(v: string) => handleFieldChange($index, 'antiFraud', v)"
            >
              <el-option v-for="o in ANTI_FRAUD_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="控制频率" width="130">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.frequency"
              :disabled="isReadonly"
              placeholder="频率"
              size="small"
              clearable
              @change="(v: string) => handleFieldChange($index, 'frequency', v)"
            >
              <el-option v-for="o in CONTROL_FREQUENCY_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="执行人" width="140">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.performer"
              :disabled="isReadonly"
              placeholder="执行人"
              size="small"
              clearable
              @change="(v: string) => handleFieldChange($index, 'performer', v)"
            >
              <el-option v-for="o in CONTROL_PERFORMER_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="执行人员的知识经验技能" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.competence"
              :disabled="isReadonly"
              type="textarea"
              :autosize="{ minRows: 2 }"
              size="small"
              placeholder="知识/经验/技能"
              @input="(v: string) => handleFieldChange($index, 'competence', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="与控制相关的风险" width="120">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.relatedRisk"
              :disabled="isReadonly"
              placeholder="风险"
              size="small"
              clearable
              @change="(v: string) => handleFieldChange($index, 'relatedRisk', v)"
            >
              <el-option v-for="o in CONTROL_RISK_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="自动/人工" width="150">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.nature"
              :disabled="isReadonly"
              placeholder="自动/人工"
              size="small"
              clearable
              @change="(v: string) => handleFieldChange($index, 'nature', v)"
            >
              <el-option v-for="o in CONTROL_NATURE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="IT应用名称" min-width="150">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.itApp"
              :disabled="isReadonly"
              size="small"
              placeholder="IT应用名称"
              @input="(v: string) => handleFieldChange($index, 'itApp', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ $index }">
            <el-button
              type="danger"
              link
              size="small"
              :disabled="isReadonly"
              @click="handleRemoveRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<style scoped>
.gt-b22b-control-matrix {
  padding: 16px;
  font-size: 13px;
  color: #303133;
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

.b22b-objective {
  margin-bottom: 10px;
}

.b22b-tips {
  margin-bottom: 12px;
  font-size: 13px;
}
.b22b-tips > summary {
  cursor: pointer;
  color: #1d4ed8;
  font-weight: 600;
  padding: 6px 10px;
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  border-radius: 3px;
}
.tips-body {
  padding: 10px 12px;
  background: #f8faff;
  border: 1px solid #dbeafe;
  border-radius: 0 0 4px 4px;
  line-height: 1.7;
  color: #374151;
}
.tips-body ul {
  margin: 6px 0;
  padding-left: 20px;
}

.matrix-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.matrix-table {
  width: 100%;
}

/* 全局字号归一 13px */
.gt-b22b-control-matrix :deep(.el-table),
.gt-b22b-control-matrix :deep(.el-table .cell),
.gt-b22b-control-matrix :deep(.el-input__inner),
.gt-b22b-control-matrix :deep(.el-textarea__inner),
.gt-b22b-control-matrix :deep(.el-select__wrapper),
.gt-b22b-control-matrix :deep(.el-tag) {
  font-size: 13px;
}
</style>
