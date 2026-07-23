<template>
  <div class="k10-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与完整性：</b>各明细项其他收益真实发生、记录完整，合计与 K10-1 审定数一致；</li>
        <li><b>准确性与分类：</b>各项金额准确、按补助类型/性质恰当分类。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 + 导入导出 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K10-2 其他收益明细表</h3>
        <el-tag size="small" type="info" effect="plain">{{ detail.rows.value.length }} 行</el-tag>
      </div>
      <div class="header-actions">
        <el-popover placement="bottom-end" trigger="click" :width="240">
          <template #reference>
            <el-button size="small">⚙ 列设置</el-button>
          </template>
          <div class="col-prefs">
            <div class="col-prefs-presets">
              <el-button size="small" text @click="colPrefs.applyPreset('full')">全部</el-button>
              <el-button size="small" text @click="colPrefs.applyPreset('core')">核心</el-button>
              <el-button size="small" text @click="colPrefs.applyPreset('audited')">审定</el-button>
              <el-button size="small" text @click="colPrefs.hideEmptyColumns()">隐藏空列</el-button>
              <el-button size="small" text @click="colPrefs.resetDefault()">重置</el-button>
            </div>
            <el-divider style="margin:8px 0" />
            <div class="col-prefs-list">
              <el-checkbox
                v-for="c in colPrefs.columns"
                :key="c.key"
                :model-value="colPrefs.isVisible(c.key)"
                size="small"
                @change="(v: any) => (colPrefs.visible.value[c.key] = !!v)"
              >{{ c.label }}</el-checkbox>
            </div>
          </div>
        </el-popover>
        <el-dropdown size="small" trigger="click" @command="handleImportExport">
          <el-button size="small" type="info" plain>
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K10-2-detail" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        逐笔登记本期其他收益明细，按补助项目分行。类型包括：即征即退/财政贴息/研发补助/稳岗补贴/其他。
        <strong>审定数=未审+AJE+重分类</strong>。合计行联动K10-1审定表，用于交叉验证。
      </p>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K10-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-4" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 明细表格（12列） ═══ -->
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="560"
    >
      <!-- 序号 -->
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed="left" />

      <!-- 补助项目 -->
      <el-table-column prop="projectName" label="补助项目" min-width="140" fixed="left">
        <template #default="{ row }">
          <span>{{ row.projectName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 类型（dropdown） -->
      <el-table-column v-if="colPrefs.isVisible('grantType')" prop="grantType" label="类型" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly && row.isEditable"
            :model-value="row.grantType"
            size="small"
            placeholder="—"
            @change="(v: string) => detail.updateCell(row.rowKey, 'grantType', v)"
          >
            <el-option v-for="opt in GRANT_TYPE_OPTIONS" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.grantType || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 判断依据 -->
      <el-table-column v-if="colPrefs.isVisible('judgmentBasis')" prop="judgmentBasis" label="判断依据" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && row.isEditable"
            :model-value="row.judgmentBasis"
            size="small"
            @change="(v: string) => detail.updateCell(row.rowKey, 'judgmentBasis', v)"
          />
          <span v-else>{{ row.judgmentBasis || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 本期未审 -->
      <el-table-column v-if="colPrefs.isVisible('unadjusted')" prop="unadjusted" label="本期未审" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.unadjusted"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'unadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column v-if="colPrefs.isVisible('aje')" prop="aje" label="AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.aje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'aje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- 重分类 -->
      <el-table-column v-if="colPrefs.isVisible('rje')" prop="rje" label="重分类" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.rje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'rje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定（公式列） -->
      <el-table-column label="审定" width="110" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="审定 = 未审 + AJE + 重分类">审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.unadjusted} + ${row.aje} + ${row.rje} = ${row.audited}`">
            {{ fmtAmt(row.audited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 上年未审 -->
      <el-table-column v-if="colPrefs.isVisible('priorUnadj')" prop="priorUnadj" label="上年未审" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.priorUnadj"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'priorUnadj', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorUnadj) }}</span>
        </template>
      </el-table-column>

      <!-- 上年AJE -->
      <el-table-column v-if="colPrefs.isVisible('priorAje')" prop="priorAje" label="上年AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable"
            :model-value="row.priorAje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => detail.updateCell(row.rowKey, 'priorAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- 上年审定（公式列） -->
      <el-table-column label="上年审定" width="100" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="上年审定 = 上年未审 + 上年AJE">上年审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.priorUnadj} + ${row.priorAje} = ${row.priorAudited}`">
            {{ fmtAmt(row.priorAudited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 文件索引号 -->
      <el-table-column v-if="colPrefs.isVisible('fileRef')" prop="fileRef" label="文件索引号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && row.isEditable"
            :model-value="row.fileRef"
            size="small"
            @change="(v: string) => detail.updateCell(row.rowKey, 'fileRef', v)"
          />
          <span v-else>{{ row.fileRef || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" link size="small" type="danger" @click="handleRemoveRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行（底部固定） ═══ -->
    <div class="subtotal-bar">
      <span class="subtotal-label">合  计</span>
      <span class="subtotal-item">本期未审: <strong>{{ fmtAmt(detail.subtotal.value.unadjusted) }}</strong></span>
      <span class="subtotal-item">AJE: <strong>{{ fmtAmt(detail.subtotal.value.aje) }}</strong></span>
      <span class="subtotal-item">重分类: <strong>{{ fmtAmt(detail.subtotal.value.rje) }}</strong></span>
      <span class="subtotal-item formula-value" :title="`审定合计 = ${detail.subtotal.value.unadjusted} + ${detail.subtotal.value.aje} + ${detail.subtotal.value.rje}`">
        审定: <strong>{{ fmtAmt(detail.subtotal.value.audited) }}</strong>
      </span>
      <span class="subtotal-item">上年审定: <strong>{{ fmtAmt(detail.subtotal.value.priorAudited) }}</strong></span>
    </div>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增补助项目</el-button>
      <el-button
        v-if="detail.rows.value.length === 0"
        size="small"
        type="warning"
        plain
        :disabled="isReadonly"
        @click="handleSeedCommon"
      >预置常见项目</el-button>
    </div>

    <!-- ═══ 底部统计面板 ═══ -->
    <div class="stats-panel">
      <div class="stat-item">
        <span class="stat-label">明细行数</span>
        <span class="stat-value">{{ detail.rows.value.length }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">本期审定合计</span>
        <span class="stat-value">{{ fmtAmt(detail.subtotal.value.audited) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">上年审定合计</span>
        <span class="stat-value">{{ fmtAmt(detail.subtotal.value.priorAudited) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">类型分布</span>
        <span class="stat-value">{{ typeDistribution }}</span>
      </div>
    </div>

    <!-- 导入 file input (隐藏) -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFileSelected" />

    <!-- ═══ 明细分析说明（AI辅助） ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>明细分析说明</span>
          <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写其他收益明细分析说明（补助类型分布、金额构成、同比变动及异常项）..."
        @change="handleNoteSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐笔登记本期其他收益明细，按补助项目分行记录</li>
        <li>类型选择：即征即退/财政贴息/研发补助/稳岗补贴/其他</li>
        <li>审定数 = 未审 + AJE + 重分类（公式自动计算）</li>
        <li>合计行自动聚合，联动K10-1审定表发生额（交叉验证）</li>
        <li>动态行新增需先输入补助项目名称</li>
        <li>支持导入导出（模板/数据/导入）</li>
        <li>建议行数>43时使用导入功能批量填入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabDetail.vue — K10-2 其他收益明细表（12列11公式，动态行）
 *
 * Spec: .kiro/specs/k10-other-income/ | Task: 4.3
 * Requirements: 3.1-3.4
 *
 * 功能：
 * - 12列：序号/补助项目/类型(dropdown)/判断依据/本期未审/AJE/重分类/审定(formula)/上年未审/上年AJE/上年审定(formula)/文件索引号
 * - 动态行新增（ElMessageBox.prompt 先输名称）
 * - el-dropdown 导入导出（uses useK10ImportExport）
 * - 合计行 + 底部统计面板
 * - max-height 560（>43行虚拟区域）
 * - GtIndexChip跨底稿引用（K10-1 / K10-4）
 */
import { ref, computed, inject, toRef, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useK10Detail, GRANT_TYPE_OPTIONS } from '../../composables/useK10Detail'
import { K10_INCOME_SOURCES } from '../../composables/k10IncomeSources'
import { useK10ImportExport } from '../../composables/useK10ImportExport'
import { useK10DetailColumnPrefs } from '../../composables/useK10DetailColumnPrefs'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const reloadResponses = inject<(() => Promise<void>) | null>('k10ReloadResponses', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const detail = useK10Detail({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const importExport = useK10ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K10-2',
})

// ─── 列显隐偏好（⚙列设置，12 列） ──────────────────────────────────────────────
const colPrefs = useK10DetailColumnPrefs(computed(() => detail.rows.value))

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template':
      importExport.exportTemplate()
      break
    case 'export-data':
      importExport.exportData()
      break
    case 'import-data':
      importFileInput.value?.click()
      break
  }
}

async function handleImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  const result = await importExport.importData(file)
  if (result && result.rowCount > 0) {
    // 导入后从服务器重新加载 checklist_responses → 明细行刷新（避免旧态）
    if (reloadResponses) {
      try { await reloadResponses() } catch { /* best effort */ }
    }
    ElMessage.success(`已导入 ${result.rowCount} 行明细`)
  }
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly)

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入补助项目名称', '新增补助项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：总额法政府补助/增值税进项加计抵减/个税手续费返还...',
    })
    if (value?.trim()) {
      detail.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowKey: string): void {
  detail.removeRow(rowKey)
}

/** 预置源模板常见其他收益项目（仅空表时，给出编制起点） */
async function handleSeedCommon(): Promise<void> {
  if (detail.rows.value.length > 0) return
  try {
    await ElMessageBox.confirm(
      `将预置 ${K10_INCOME_SOURCES.length} 个源模板常见其他收益项目作为编制起点（金额留空待填）。是否继续？`,
      '预置常见项目',
      { confirmButtonText: '确认预置', cancelButtonText: '取消', type: 'info' },
    )
    K10_INCOME_SOURCES.forEach((name) => detail.addRow(name))
    ElMessage.success(`已预置 ${K10_INCOME_SOURCES.length} 个常见项目`)
  } catch { /* cancelled */ }
}

// ─── 统计 ────────────────────────────────────────────────────────────────────

const typeDistribution = computed(() => {
  const rows = detail.rows.value
  if (rows.length === 0) return '—'
  const types = new Set(rows.map(r => r.grantType).filter(Boolean))
  return `${types.size} 种类型`
})

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 明细分析说明 + AI ─────────────────────────────────────────────────────────
const noteText = ref('')
const aiLoading = ref(false)

function loadNote(): void {
  const saved = props.allResponses.get('K10-2-note')
  if (saved) noteText.value = (saved.remark ?? saved.conclusion ?? '') as string
}

function handleNoteSave(): void {
  emit('save', 'K10-2-note', { remark: noteText.value })
}

async function handleAiAssist(): Promise<void> {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const st = detail.subtotal.value
    const ctx = {
      明细行数: String(detail.rows.value.length),
      本期审定合计: String(st.audited),
      上年审定合计: String(st.priorAudited),
      类型分布: typeDistribution.value,
      明细: detail.rows.value.map(r => `${r.projectName}(${r.grantType}):审定${r.audited}`).join('；'),
    }
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'K10-2-note',
      prompt: '为K10其他收益明细表生成分析说明：补助类型分布、金额构成、本期与上年同比变动、异常项关注点。',
      existingContent: noteText.value,
      context: ctx,
    })
    const content = (res?.data?.content ?? res?.content ?? '') as string
    if (content) { noteText.value = content; handleNoteSave(); ElMessage.success('AI生成完成') }
    else ElMessage.warning('AI未返回内容，请手动填写')
  } catch { ElMessage.warning('AI生成失败，请手动填写') } finally { aiLoading.value = false }
}

onMounted(() => { loadNote() })
</script>

<style scoped>
.k10-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-left h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

/* 公式列样式 */
:deep(.formula-col) .cell { border-bottom: 1px dashed #909399; }
.formula-header {
  cursor: help;
  border-bottom: 1px dashed #606266;
  padding-bottom: 1px;
}
.formula-value {
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
  padding-bottom: 1px;
}

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.subtotal-bar {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  margin-top: 10px; padding: 8px 14px;
  background: #f5f7fa; border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}
.subtotal-label { font-weight: 700; color: #303133; min-width: 48px; }
.subtotal-item { color: #606266; }
.subtotal-item strong { color: #303133; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

.stats-panel {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-top: 16px; padding: 12px 16px;
  background: #fafafa; border-radius: 8px; border: 1px solid #ebeef5;
}
.stat-item { text-align: center; }
.stat-label { display: block; font-size: 11px; color: #909399; margin-bottom: 4px; }
.stat-value { display: block; font-size: 14px; font-weight: 600; color: #303133; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }

.note-card { margin-top: 16px; }
.note-card-header { display: flex; justify-content: space-between; align-items: center; }
.note-card-header span { font-weight: 600; font-size: 14px; }

.col-prefs-presets { display: flex; flex-wrap: wrap; gap: 4px; }
.col-prefs-list { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow-y: auto; }
</style>
