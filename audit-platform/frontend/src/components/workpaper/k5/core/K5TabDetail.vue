<template>
  <div class="k5-tab-detail">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有应当确认的预计负债项目均已记录（负债完整性重点）；</li>
        <li><b>存在与义务：</b>各项预计负债是存在的现时义务，明细合计与 K5-1 审定数一致；</li>
        <li><b>计价和分摊：</b>各项预计负债以最佳估计数恰当计量。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + 操作按钮 ═══ -->
    <div class="section-header">
      <h3>K5-2 预计负债明细表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="seedFromK5Adjudication">
          📥 从K5-1带入
        </el-button>
        <el-dropdown size="small" :disabled="isReadonly">
          <el-button size="small">导入导出 <el-icon><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="wp:K5-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-4" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-5" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-6" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ K5-1↔K5-2勾稽告警 ═══ -->
    <el-alert v-if="adjVsDetailDiff !== 0" :type="Math.abs(adjVsDetailDiff) > 0.01 ? 'warning' : 'success'" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>
        K5-1审定合计 {{ fmtNum(adjTotal) }} vs K5-2明细期末合计 {{ fmtNum(subtotals.auditedEnd || subtotals.endBalance) }}
        <span v-if="Math.abs(adjVsDetailDiff) > 0.01" style="color:#e6a23c;font-weight:600">  差异 {{ fmtNum(adjVsDetailDiff) }}</span>
        <span v-else style="color:#67c23a">  ✓ 一致</span>
      </template>
    </el-alert>

    <!-- ═══ 三区段Tab切换 ═══ -->
    <el-segmented v-model="activeSection" :options="sectionOptions" class="section-segmented" />

    <!-- ═══ 三级可能性色标图例 ═══ -->
    <div v-if="activeSection === 1" class="color-legend">
      <span class="legend-item"><span class="dot dot-red" /> 很可能（>50%）→ 确认</span>
      <span class="legend-item"><span class="dot dot-orange" /> 可能（≤50%）→ 披露</span>
      <span class="legend-item"><span class="dot dot-gray" /> 极小可能 → 不处理</span>
    </div>

    <!-- ═══ CAS13 或有事项确认决策树引导（判断区段显示）═══ -->
    <div v-if="activeSection === 1" class="cas13-decision-tree">
      <div class="dt-title">CAS13 或有事项确认三条件决策树</div>
      <div class="dt-flow">
        <div class="dt-step">
          <div class="dt-node dt-q">① 是否存在<b>现时义务</b>？<br/><span class="dt-hint">（过去事项导致的法定/推定义务）</span></div>
          <div class="dt-arrow">是 ↓</div>
        </div>
        <div class="dt-step">
          <div class="dt-node dt-q">② 履行该义务<b>很可能</b>导致经济利益流出？<br/><span class="dt-hint">（可能性>50%,结合律师意见/判决/经验）</span></div>
          <div class="dt-arrow">是 ↓</div>
        </div>
        <div class="dt-step">
          <div class="dt-node dt-q">③ 金额<b>能够可靠计量</b>？<br/><span class="dt-hint">（最佳估计数/区间中值/期望值加权）</span></div>
          <div class="dt-arrow">是 ↓</div>
        </div>
        <div class="dt-step">
          <div class="dt-node dt-a">✓ <b>确认预计负债</b>（三条件同时满足）</div>
        </div>
      </div>
      <div class="dt-alt">
        <span>任一条件不满足：</span>
        <span class="dt-tag dt-orange">②不满足(≤50%)→ 附注披露或有负债</span>
        <span class="dt-tag dt-gray">极小可能→ 不处理不披露</span>
      </div>
    </div>

    <!-- ═══ 区段0: 基础信息 ═══ -->
    <el-table
      v-if="activeSection === 0"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="项目名称" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.projectName" :disabled="isReadonly" size="small" @blur="handleUpdate(row.rowId, 'projectName', row.projectName)" />
        </template>
      </el-table-column>
      <el-table-column label="类型" width="130">
        <template #default="{ row }">
          <el-select v-model="row.provisionType" :disabled="isReadonly" size="small" placeholder="类型" @change="(v:string) => handleUpdate(row.rowId, 'provisionType', v)">
            <el-option v-for="t in provisionTypeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="现时义务描述" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.obligationDesc" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="handleUpdate(row.rowId, 'obligationDesc', row.obligationDesc)" />
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="计提" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.provision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'provision', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转销" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.release" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'release', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 计提 − 转销" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="handleRemoveRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 区段1: 判断信息 ═══ -->
    <el-table
      v-if="activeSection === 1"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column prop="projectName" label="项目" width="130" />
      <el-table-column label="可能性级别" width="140">
        <template #default="{ row }">
          <el-select v-model="row.likelihood" :disabled="isReadonly" size="small" placeholder="选择" @change="(v:string) => handleUpdate(row.rowId, 'likelihood', v)">
            <el-option label="很可能(>50%)" value="very_likely" />
            <el-option label="可能(≤50%)" value="possible" />
            <el-option label="极小可能" value="remote" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="确认决策" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.recognition" :type="recognitionTagType(row.recognition)" size="small">
            {{ recognitionLabel(row.recognition) }}
          </el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="色标" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row.likelihood" class="likelihood-dot" :style="{ background: likelihoodColorMap[row.likelihood] }" />
        </template>
      </el-table-column>
      <el-table-column label="确认依据" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.recognitionBasis" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="handleUpdate(row.rowId, 'recognitionBasis', row.recognitionBasis)" />
        </template>
      </el-table-column>
      <el-table-column label="计量方法" width="140">
        <template #default="{ row }">
          <el-select v-model="row.measurementMethod" :disabled="isReadonly" size="small" placeholder="方法" @change="(v:string) => handleUpdate(row.rowId, 'measurementMethod', v)">
            <el-option v-for="m in measurementOptions" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 区段2: 估计信息 ═══ -->
    <el-table
      v-if="activeSection === 2"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
      show-summary
      :summary-method="getEstimateSummary"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column prop="projectName" label="项目" width="130" />
      <el-table-column label="最佳估计数" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.measurementMethod === 'single'">
            <el-input-number v-model="row.bestEstimate" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => handleUpdate(row.rowId, 'bestEstimate', v)" />
          </template>
          <template v-else>
            <el-tooltip :content="row.measurementMethod === 'range' ? '(上限+下限)/2' : 'Σ(金额×概率)'" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.bestEstimate) }}</span>
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="区间上限" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.measurementMethod === 'range'" v-model="row.rangeUpper" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'rangeUpper', v)" />
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="区间下限" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.measurementMethod === 'range'" v-model="row.rangeLower" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'rangeLower', v)" />
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="110">
        <template #default="{ row }">
          <el-input v-model="row.voucherRef" :disabled="isReadonly" size="small" placeholder="凭证" @blur="handleUpdate(row.rowId, 'voucherRef', row.voucherRef)" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @blur="handleUpdate(row.rowId, 'conclusion', row.conclusion)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 区段3: 调整信息（未审→期初调整/账项调整/重分类调整→审定，对齐源模板）═══ -->
    <el-table
      v-if="activeSection === 3"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
      show-summary
      :summary-method="getAdjustSummary"
    >
      <el-table-column type="index" label="序" width="44" align="center" fixed />
      <el-table-column prop="projectName" label="项目" width="120" fixed />
      <el-table-column label="未审期末" width="100" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmtNum(row.endBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="期初调整" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.openingAdjust" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'openingAdjust', v)" />
        </template>
      </el-table-column>
      <el-table-column label="账项调整-增" width="105" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.ajeIncrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:88px" @change="(v:number) => handleUpdate(row.rowId, 'ajeIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="账项调整-减" width="105" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.ajeDecrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:88px" @change="(v:number) => handleUpdate(row.rowId, 'ajeDecrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="重分类-增" width="105" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.rjeIncrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:88px" @change="(v:number) => handleUpdate(row.rowId, 'rjeIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="重分类-减" width="105" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.rjeDecrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:88px" @change="(v:number) => handleUpdate(row.rowId, 'rjeDecrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="审定期初" width="105" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmtNum(row.auditedBegin) }}</span></template>
      </el-table-column>
      <el-table-column label="审定期末" width="115" align="right">
        <template #default="{ row }">
          <el-tooltip content="审定期初 + 审定增加 − 审定减少" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.auditedEnd) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计统计栏 ═══ -->
    <div class="summary-bar">
      <span>合计行数: {{ subtotals.count }}</span>
      <span>未审期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
      <span>审定期末合计: <strong>{{ fmtNum(subtotals.auditedEnd) }}</strong></span>
      <span>最佳估计合计: <strong>{{ fmtNum(subtotals.bestEstimate) }}</strong></span>
    </div>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="conclusion-card" style="margin-top:12px">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div style="margin-bottom:10px">
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述明细表编制情况：或有事项识别/可能性判断/最佳估计数计量方法/完整性核查/与K5-1勾稽情况等"
          @change="persistNote" />
      </div>
      <div>
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="基于上述明细检查，对预计负债明细的完整性、计量和分类形成结论..."
          @change="persistNote" />
      </div>
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>23列拆为3区段：基础（余额变动）→ 判断（或有事项可能性）→ 估计（最佳估计数计量）</li>
        <li>很可能(>50%)→确认预计负债并填最佳估计数；可能(≤50%)→披露或有负债进附注；极小可能→不处理</li>
        <li>计量方法：单一最可能金额 / 区间中值(上+下)/2 / 期望值加权Σ(金额×概率)</li>
        <li>明细表期末合计应与K5-1审定表审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDetail.vue — K5-2 预计负债明细表
 * 23列3区段Tab+或有判断+三级色标+42行虚拟滚动+动态行
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.3
 * Requirements: 3.1-3.6, 4.3-4.4, 5.5
 */
import { ref, toRef, computed, onMounted } from 'vue'
import { Plus, Delete, ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5Detail, LIKELIHOOD_COLOR_MAP } from '../../composables/useK5Detail'
import GtIndexChip from '../../shared/GtIndexChip.vue'
import http from '@/utils/http'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  detailRows,
  activeSection,
  subtotals,
  provisionTypeOptions,
  measurementOptions,
  likelihoodColorMap,
  updateCell,
  addRow,
  removeRow,
} = useK5Detail({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

// ─── 区段Tab options ─────────────────────────────────────────────────────────

const sectionOptions = [
  { label: '基础', value: 0 },
  { label: '判断', value: 1 },
  { label: '估计', value: 2 },
  { label: '调整', value: 3 },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUpdate(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function handleAddRow() { addRow() }
function handleRemoveRow(idx: number) { removeRow(idx) }
function handleAiGenerate() { emit('save', 'K5-2-ai-trigger', { remark: 'generate' }) }

// ─── K5-1↔K5-2勾稽 ─────────────────────────────────────────────────────────

const adjTotal = computed(() => {
  const item = props.allResponses.get('K5-1-audited-total')
  return Number(item?.remark ?? 0) || 0
})

const adjVsDetailDiff = computed(() => {
  const detailTotal = subtotals.value.auditedEnd || subtotals.value.endBalance || 0
  return adjTotal.value - detailTotal
})

// ─── 从K5-1带入明细种子 ─────────────────────────────────────────────────────

const K5_TYPE_LABELS = ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '其他']

async function seedFromK5Adjudication(): Promise<void> {
  // 读K5-1各类型行的期初/期末
  const seeds: Array<{ name: string; begin: number; end: number }> = []
  for (let i = 0; i < K5_TYPE_LABELS.length; i++) {
    const beginItem = props.allResponses.get(`K5-1-r${i}-begin`)
    const endItem = props.allResponses.get(`K5-1-r${i}-unadj`)
    const begin = Number(beginItem?.remark ?? 0) || 0
    const end = Number(endItem?.remark ?? 0) || 0
    if (begin > 0 || end > 0) {
      seeds.push({ name: K5_TYPE_LABELS[i], begin, end })
    }
  }

  if (seeds.length === 0) {
    ElMessage.warning('K5-1审定表暂无数据，请先填写审定表')
    return
  }

  try {
    await ElMessageBox.confirm(
      `从K5-1审定表带入 ${seeds.length} 个类型行作为明细种子：\n${seeds.map(s => `• ${s.name}：期初${fmtNum(s.begin)}/未审${fmtNum(s.end)}`).join('\n')}\n\n仅新增不存在的类型行（已有同名不覆盖）`,
      '从K5-1带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'info' }
    )

    let added = 0
    const existingNames = new Set(detailRows.value.map((r: any) => r.projectName))
    for (const s of seeds) {
      if (!existingNames.has(s.name)) {
        addRow(s.name)
        // 找到刚加的行，填入期初和期末
        const newRow = detailRows.value[detailRows.value.length - 1]
        if (newRow) {
          updateCell(newRow.rowId, 'provisionType', s.name)
          updateCell(newRow.rowId, 'beginBalance', s.begin)
          // endBalance 由公式算出，填期初+计提(=end-begin)
          if (s.end > s.begin) {
            updateCell(newRow.rowId, 'provision', s.end - s.begin)
          }
        }
        added++
      }
    }

    if (added > 0) {
      ElMessage.success(`已新增 ${added} 行明细种子`)
    } else {
      ElMessage.info('所有类型行已存在，未新增')
    }
  } catch { /* 用户取消 */ }
}

// ─── 审计说明与结论 ──────────────────────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

function loadNote(): void {
  const noteItem = props.allResponses.get('K5-2-audit-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const conclItem = props.allResponses.get('K5-2-audit-conclusion')
  if (conclItem?.remark) auditConclusion.value = conclItem.remark
}

function persistNote(): void {
  emit('save', 'K5-2-audit-note', { remark: auditNote.value })
  emit('save', 'K5-2-audit-conclusion', { remark: auditConclusion.value })
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleExportTemplate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-template`, null, { params: { sheet: 'K5-2' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'K5-2_明细表_模板.xlsx'; a.click(); URL.revokeObjectURL(url)
    ElMessage.success('模板已下载')
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-data`, null, { params: { sheet: 'K5-2' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'K5-2_明细表_数据.xlsx'; a.click(); URL.revokeObjectURL(url)
    ElMessage.success('数据已导出')
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]; if (!file) return
    const formData = new FormData(); formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/k5/import-data`, formData, { params: { sheet: 'K5-2' }, headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
      ElMessage.success(`导入成功，共 ${res?.data?.imported_count ?? res?.data?.data?.rowCount ?? 0} 条`)
    } catch (err: any) { ElMessage.error('导入失败：' + (err?.response?.data?.message || err?.response?.data?.detail || '文件格式错误')) }
  }
  input.click()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => { loadNote() })

// ─── 判断列辅助 ──────────────────────────────────────────────────────────────

function recognitionTagType(r: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (r === 'recognize') return 'danger'
  if (r === 'disclose') return 'warning'
  return 'info'
}

function recognitionLabel(r: string): string {
  if (r === 'recognize') return '确认'
  if (r === 'disclose') return '披露'
  if (r === 'ignore') return '不处理'
  return ''
}

// ─── Summary methods ─────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((_: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (idx === 5) { sums[idx] = fmtNum(subtotals.value.beginBalance); return }
    if (idx === 6) { sums[idx] = fmtNum(subtotals.value.provision); return }
    if (idx === 7) { sums[idx] = fmtNum(subtotals.value.release); return }
    if (idx === 8) { sums[idx] = fmtNum(subtotals.value.endBalance); return }
    sums[idx] = ''
  })
  return sums
}

function getEstimateSummary({ columns }: any) {
  const sums: string[] = []
  columns.forEach((_: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (idx === 2) { sums[idx] = fmtNum(subtotals.value.bestEstimate); return }
    sums[idx] = ''
  })
  return sums
}

function getAdjustSummary({ columns }: any) {
  const sums: string[] = []
  columns.forEach((_: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (idx === 2) { sums[idx] = fmtNum(subtotals.value.endBalance); return }
    if (idx === 3) { sums[idx] = fmtNum(subtotals.value.openingAdjust); return }
    if (idx === 4) { sums[idx] = fmtNum(subtotals.value.ajeIncrease); return }
    if (idx === 5) { sums[idx] = fmtNum(subtotals.value.ajeDecrease); return }
    if (idx === 6) { sums[idx] = fmtNum(subtotals.value.rjeIncrease); return }
    if (idx === 7) { sums[idx] = fmtNum(subtotals.value.rjeDecrease); return }
    if (idx === 9) { sums[idx] = fmtNum(subtotals.value.auditedEnd); return }
    sums[idx] = ''
  })
  return sums
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; flex-wrap: wrap; }
.cross-refs-label { color: #909399; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-weight: 600; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.section-segmented { margin-bottom: 12px; }
.color-legend { display: flex; gap: 16px; margin-bottom: 10px; font-size: 12px; color: #606266; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.dot-red { background: #F56C6C; }
.dot-orange { background: #E6A23C; }
.dot-gray { background: #909399; }
.likelihood-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.text-muted { color: #c0c4cc; font-size: 12px; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
/* CAS13 决策树 */
.cas13-decision-tree { margin-bottom: 12px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; font-size: 12px; }
.dt-title { font-weight: 600; color: #0369a1; margin-bottom: 8px; }
.dt-flow { display: flex; flex-direction: column; gap: 2px; }
.dt-step { display: flex; flex-direction: column; align-items: flex-start; }
.dt-node { padding: 4px 10px; border-radius: 4px; line-height: 1.5; }
.dt-q { background: #e0f2fe; border: 1px solid #7dd3fc; }
.dt-a { background: #dcfce7; border: 1px solid #86efac; font-weight: 600; color: #166534; }
.dt-arrow { padding-left: 16px; color: #0369a1; font-size: 11px; line-height: 1.2; }
.dt-hint { font-size: 11px; color: #64748b; }
.dt-alt { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 11px; color: #475569; }
.dt-tag { padding: 2px 6px; border-radius: 3px; font-size: 11px; }
.dt-orange { background: #fef3c7; color: #92400e; }
.dt-gray { background: #f1f5f9; color: #475569; }
</style>
