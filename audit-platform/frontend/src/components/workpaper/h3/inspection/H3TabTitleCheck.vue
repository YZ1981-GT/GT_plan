<template>
  <div class="h3-tab-title-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 实地查看并查验产权证书原件，复印件须加盖公章；结合 L1 检查抵押担保。</p>
        <p>2. 办证中资产须填预计办证日、进度说明及是否权属纠纷。</p>
        <p>3. 建议顺序：H3-2 → H3-9 → 一键联动 → 同步 L1 抵押 → 同步附注受限 → 起草结论。</p>
        <p>4. 面积容差：±1㎡ 或 0.5% 内视为可接受差异；超出标黄/红。</p>
        <p>5. 行级附件可挂产权证复印件、抵押登记证明；OCR 为扩展入口。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="I. 审计目标：核实投资性房地产由被审计单位拥有或控制，识别面积差异、权属瑕疵、办证中及抵押/查封等权利限制。"
    />

    <el-card shadow="never" class="procedure-card">
      <template #header>
        <div class="card-header">
          <span>II. 审计过程</span>
          <el-button v-if="!isReadonly" size="small" @click="onFillProcedure">填入标准程序</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditProcedure"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="记录执行的审计程序…"
        :disabled="isReadonly"
        @change="saveAuditProcedure"
      />
    </el-card>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('navigate-sheet', 'H3-9')">← H3-9</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H3-5 增减检查')">H3-5 追查</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H3-13')">H3-13 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H3-10')">H3-10 减值</el-button>
        <GtIndexChip value="wp:L1" :context-project-id="projectId" />
      </div>
      <div class="toolbar-right">
        <span class="auditee-wrap">
          <span class="auditee-label">被审计单位</span>
          <el-input
            v-model="auditeeName"
            size="small"
            style="width: 160px"
            :disabled="isReadonly"
            placeholder="单位名称"
            @change="onAuditeeChange"
          />
        </span>
        <span class="chip-wrap"><GtIndexChip value="wp:H3-12" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
      </div>
    </div>

    <!-- 完整性勾稽 -->
    <div class="check-bar">
      <el-tag
        v-for="c in completenessChecks"
        :key="c.code"
        size="small"
        :type="checkTagType(c.status)"
        class="check-tag"
        :title="c.detail"
      >
        {{ c.label }}：{{ c.detail }}
      </el-tag>
    </div>

    <!-- 汇总 -->
    <div class="summary-row">
      <span>权属异常 <strong :class="{ 'text-danger': ownerAnomalies.length > 0 }">{{ ownerAnomalies.length }}</strong></span>
      <span>面积异常 <strong :class="{ 'text-warn': areaDiffRows.length > 0 }">{{ areaDiffRows.length }}</strong></span>
      <span>可接受差异 <strong>{{ areaAcceptableRows.length }}</strong></span>
      <span>不一致 <strong :class="{ 'text-warn': mismatchRows.length > 0 }">{{ mismatchRows.length }}</strong></span>
      <span>权利受限 <strong :class="{ 'text-warn': restrictedRows.length > 0 }">{{ restrictedRows.length }}</strong></span>
      <span>办证中 <strong :class="{ 'text-warn': pendingCertRows.length > 0 }">{{ pendingCertRows.length }}</strong></span>
      <span>抽样 <strong>{{ sampledRows.length }}</strong></span>
      <span>抵押价值合计 <strong>{{ totalMortgageValue.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</strong></span>
    </div>

    <el-alert
      v-if="impairmentHints.length"
      type="warning"
      :closable="false"
      show-icon
      class="impair-alert"
      :title="`减值关注 ${impairmentHints.length} 项：${impairmentHints.slice(0, 2).join('；')}${impairmentHints.length > 2 ? '…' : ''}`"
    />

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">+ 新增</el-button>

      <el-dropdown v-if="!isReadonly" trigger="click" @command="onH32Command">
        <el-button size="small">从 H3-2 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="addNew">新增缺失行</el-dropdown-item>
            <el-dropdown-item command="fillEmpty">补全空白</el-dropdown-item>
            <el-dropdown-item command="overwrite">覆盖同步</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-dropdown v-if="!isReadonly" trigger="click" @command="onH39Command">
        <el-button size="small">从 H3-9 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="fillEmpty">补全产权字段</el-dropdown-item>
            <el-dropdown-item command="addNew">新增缺失行</el-dropdown-item>
            <el-dropdown-item command="overwrite">覆盖同步</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <el-button v-if="!isReadonly" size="small" type="success" @click="onImportAll">一键联动</el-button>
      <el-button v-if="!isReadonly" size="small" :loading="l1Loading" @click="onSyncL1">同步 L1 抵押</el-button>
      <el-button v-if="!isReadonly" size="small" @click="onSyncDisclosure">同步附注受限</el-button>
      <el-button v-if="!isReadonly" size="small" @click="onSyncBackH39">回写 H3-9</el-button>
      <el-button v-if="!isReadonly" size="small" @click="onFillCertArea">预填证载面积</el-button>
      <el-button v-if="!isReadonly" size="small" @click="onApplyAuditee">带入被审计单位</el-button>
      <el-button v-if="!isReadonly" size="small" @click="onSample">抽样(80%)</el-button>

      <el-dropdown size="small" class="export-dropdown" @command="handleExportCmd">
        <el-button size="small" :loading="importing">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <!-- 主表 -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass" max-height="560">
      <el-table-column prop="seq" label="#" width="42" align="center" fixed />
      <el-table-column label="抽样" width="52" align="center" fixed>
        <template #default="{ row }">
          <el-tag v-if="row.sampled" size="small" type="success">抽</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="账面(登记簿)资产信息" align="center">
        <el-table-column prop="bookOwner" label="所有者" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.bookOwner" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="assetCode" label="编号" width="80">
          <template #default="{ row, $index }">
            <el-input v-model="row.assetCode" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="location" label="坐落" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.location" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="bookArea" label="账面面积" width="82" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.bookArea" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面原值" width="92" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="产权证明核对" align="center">
        <el-table-column prop="certStatus" label="办证状态" width="92">
          <template #default="{ row, $index }">
            <el-select v-model="row.certStatus" size="small" :disabled="isReadonly" @change="onCellChange($index)">
              <el-option label="已办证" value="已办证" />
              <el-option label="办证中" value="办证中" />
              <el-option label="无需办证" value="无需办证" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="certName" label="证书名称" width="88">
          <template #default="{ row, $index }">
            <el-input v-model="row.certName" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="titleCertNo" label="产权证号" min-width="110">
          <template #default="{ row, $index }">
            <el-input v-model="row.titleCertNo" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="certArea" label="证载面积" width="88" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.certArea" size="small" :disabled="isReadonly" @change="onCertAreaChange($index, row)" />
            <el-tag v-if="row.certAreaPending" size="small" type="info">待核实</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="面积差异" width="88" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{
                'text-warn': isAreaAnomaly(row.certArea, row.bookArea),
                'text-ok': isAreaAcceptableDiff(row.certArea, row.bookArea),
              }"
              :title="isAreaAcceptableDiff(row.certArea, row.bookArea) ? '可接受差异（容差内）' : ''"
            >
              {{ row.areaDiff.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="certOwner" label="证载所有人" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.certOwner" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="isAuditEntity" label="被审计单位" width="92" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.isAuditEntity" size="small" :disabled="isReadonly" @change="onCellChange($index)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="matchConsistent" label="核对一致" width="80" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.matchConsistent" size="small" :disabled="isReadonly" @change="onCellChange($index)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待查" value="待查" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="inconsistentReason" label="不一致原因" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.inconsistentReason" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="expectedCertDate" label="预计办证日" width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-model="row.expectedCertDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              :disabled="isReadonly || row.certStatus !== '办证中'"
              style="width: 100%"
              @change="onCellChange($index)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="certProgressNote" label="办证进度" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.certProgressNote" size="small" :disabled="isReadonly || row.certStatus !== '办证中'" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="hasDispute" label="权属纠纷" width="80" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.hasDispute" size="small" :disabled="isReadonly" @change="onCellChange($index)">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="certPurpose" label="证载用途" width="72">
          <template #default="{ row, $index }">
            <el-input v-model="row.certPurpose" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="actualPurpose" label="实际用途" width="72">
          <template #default="{ row, $index }">
            <el-input v-model="row.actualPurpose" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="抵押/权利限制" align="center">
        <el-table-column prop="isRestricted" label="权利受限" width="80" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.isRestricted" size="small" :disabled="isReadonly" @change="onCellChange($index)">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="mortgageArea" label="抵押面积" width="80" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.mortgageArea" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="mortgageValue" label="抵押价值" width="90" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.mortgageValue" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="mortgageNature" label="抵押性质" width="80">
          <template #default="{ row, $index }">
            <el-input v-model="row.mortgageNature" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="seizure" label="查封" width="70">
          <template #default="{ row, $index }">
            <el-input v-model="row.seizure" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="refIndex" label="索引号" width="70">
          <template #default="{ row, $index }">
            <el-input v-model="row.refIndex" size="small" :disabled="isReadonly" placeholder="L1-8" @change="onCellChange($index)" />
          </template>
        </el-table-column>
        <el-table-column prop="sourceTags" label="来源" width="70">
          <template #default="{ row }">
            <span class="source-tags">{{ row.sourceTags || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="80">
          <template #default="{ row, $index }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index)" />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="联动" width="88" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="traceCountForTitle(row) > 0"
            size="small"
            link
            type="primary"
            @click="goToH35Trace(row)"
          >H3-5({{ traceCountForTitle(row) }})</el-button>
          <span v-else class="muted-link">-</span>
        </template>
      </el-table-column>

      <el-table-column label="附件" width="100" align="center" fixed="right">
        <template #default="{ $index }">
          <ItemAttachment
            v-if="projectId && wpId"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="H3-12"
            :item-index="$index + 1"
            accept=".pdf,.png,.jpg,.jpeg"
          />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="90" align="center" fixed="right">
        <template #default="{ row, $index }">
          <el-button type="primary" link size="small" :disabled="isReadonly" @click="handleTitleOcr(row)">📎OCR</el-button>
          <el-button type="danger" link size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 办证中清单 -->
    <el-card v-if="pendingCertRows.length" shadow="never" class="pending-card">
      <template #header>
        <div class="card-header">
          <span>办证中资产清单（{{ pendingCertRows.length }}）</span>
        </div>
      </template>
      <el-table :data="pendingCertRows" border size="small">
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="bookValue" label="账面原值" width="110" align="right">
          <template #default="{ row }">{{ Number(row.bookValue).toLocaleString('zh-CN') }}</template>
        </el-table-column>
        <el-table-column prop="expectedCertDate" label="预计办证日" width="120" />
        <el-table-column prop="certProgressNote" label="进度说明" min-width="140" />
        <el-table-column prop="hasDispute" label="权属纠纷" width="90" align="center" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>III. 审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-12')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-12')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }" placeholder="记录核对情况、例外事项及影响…" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>IV. 审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="A、权属完整合法。B、除下列事项外未见异常。C、存在权属瑕疵或限制，需披露。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabTitleCheck.vue — H3-12 产权核对（全量增强）
 */
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH3TitleCheck, isAreaAnomaly, isAreaAcceptableDiff } from '../../composables/useH3TitleCheck'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport } from '../../composables/useH3ImportExport'
import { resolveProjectClientName } from '../../composables/h3TitleRowModel'
import type { TitleRow } from '../../composables/h3TitleRowModel'
import { H3RowNavigationKey } from '../../composables/useH3RowNavigation'
import { findTraceRowsForTitle, parseTraceRows } from '../../composables/h3AdditionTitleLink'
import { normalizeTraceRow } from '../../composables/h3AdditionCheckModel'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel?: 'cost' | 'fair_value'
  htmlData?: any
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const h3Nav = inject(H3RowNavigationKey, null)

const measurementModelRef = computed(() => props.measurementModel ?? 'cost') as any
const auditeeName = ref('')

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelRef,
})

const {
  rows, addRow, removeRow, updateRow,
  ownerAnomalies, areaDiffRows, areaAcceptableRows, mismatchRows, restrictedRows,
  pendingCertRows, sampledRows, totalMortgageValue, impairmentHints, completenessChecks,
  l1Loading,
  buildDraftConclusion, importFromH32, importFromH39, importFromAll,
  syncFromL1, syncToDisclosure, syncBackToH39, fillCertAreaPending, applyAuditee,
  runSample, getProcedureTemplate,
} = useH3TitleCheck({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelRef,
  auditeeName,
  getValue, setValue, saveImmediate,
})

const { exportTemplate, exportData, importData, importing } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelRef,
  onImported: () => {
  },
})

const NOTE_KEY = 'H3-12-audit-note'
const CONCLUSION_KEY = 'H3-12-audit-conclusion'
const PROCEDURE_KEY = 'H3-12-audit-procedure'
const AUDITEE_KEY = 'H3-12-auditee-name'
const auditNote = ref('')
const auditConclusion = ref('')
const auditProcedure = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const traceRowsForLink = computed(() => {
  void props.allResponses.size
  const parseItem = (key: string) => {
    const raw = getValue(key)
    return parseTraceRows(raw).map((r, i) => normalizeTraceRow(r, i))
  }
  return [...parseItem('H3-5-cost-trace-rows'), ...parseItem('H3-5-fair-trace-rows')]
})

function traceCountForTitle(row: TitleRow): number {
  return findTraceRowsForTitle(row, traceRowsForLink.value).length
}

function goToH35Trace(row: TitleRow) {
  const traces = findTraceRowsForTitle(row, traceRowsForLink.value)
  if (!traces.length || !h3Nav) {
    ElMessage.info('未找到关联的 H3-5 证→账追查行')
    return
  }
  const tr = traces[0]
  h3Nav.navigateToRow({
    sheet: 'H3-5',
    rowId: tr.rowId,
    section: 'trace',
    assetName: row.assetName,
    titleCertNo: row.titleCertNo,
    sourceRef: tr.sourceRef,
  })
}

function persistKey(key: string, val: string, target: { value: string }) {
  if (props.isReadonly) return
  target.value = val
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: val })
  void saveImmediate(key, val)
}
function saveAuditNote(val: string) { persistKey(NOTE_KEY, val, auditNote) }
function saveAuditConclusion(val: string) { persistKey(CONCLUSION_KEY, val, auditConclusion) }
function saveAuditProcedure(val: string) { persistKey(PROCEDURE_KEY, val, auditProcedure) }
function onAuditeeChange(val: string) { persistKey(AUDITEE_KEY, val, auditeeName) }

/** 优先已保存名称，否则从 project_context.client_name 带入 */
function initAuditeeName(): void {
  const saved = props.allResponses.get(AUDITEE_KEY)?.remark?.trim()
  if (saved) {
    auditeeName.value = saved
    return
  }
  const fromCtx = resolveProjectClientName(props.htmlData)
  if (!fromCtx) return
  auditeeName.value = fromCtx
  if (!props.isReadonly) {
    onAuditeeChange(fromCtx)
    applyAuditee()
  }
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
  const p = props.allResponses.get(PROCEDURE_KEY)
  if (p?.remark) auditProcedure.value = p.remark
  initAuditeeName()
  h3Nav?.consumeFocus('H3-12')
})

watch(
  () => props.htmlData,
  () => {
    if (!auditeeName.value.trim() && !props.allResponses.get(AUDITEE_KEY)?.remark?.trim()) {
      initAuditeeName()
    }
  },
  { deep: true },
)

function onCellChange(index: number) { updateRow(index) }
function onCertAreaChange(index: number, row: any) {
  row.certAreaPending = false
  updateRow(index)
}

function getRowClass({ row }: { row: any }): string {
  const hl = h3Nav?.rowHighlightClass(row.rowId)
  if (hl) return hl
  if (row.isAuditEntity === '否' || row.matchConsistent === '否' || row.hasDispute === '是') return 'row-danger'
  if (row.certStatus === '办证中') return 'row-pending'
  if (isAreaAnomaly(row.certArea, row.bookArea) || row.isRestricted === '是') return 'row-warn'
  if (isAreaAcceptableDiff(row.certArea, row.bookArea)) return 'row-ok-diff'
  return ''
}

function checkTagType(status: string) {
  if (status === 'ok') return 'success'
  if (status === 'error') return 'danger'
  if (status === 'warn') return 'warning'
  return 'info'
}

function onDraftConclusion() { saveAuditConclusion(buildDraftConclusion()) }
function onFillProcedure() { saveAuditProcedure(getProcedureTemplate()) }

function onH32Command(cmd: string) {
  const overwrite = cmd === 'overwrite'
  const mode = cmd === 'addNew' ? 'addNew' : 'fillEmpty'
  const result = importFromH32(mode as any, overwrite)
  ElMessage[result.added || result.updated ? 'success' : 'info'](result.message)
}
function onH39Command(cmd: string) {
  const overwrite = cmd === 'overwrite'
  const mode = cmd === 'addNew' ? 'addNew' : 'fillEmpty'
  const result = importFromH39(mode as any, overwrite)
  ElMessage[result.added || result.updated ? 'success' : 'info'](result.message)
}
function onImportAll() {
  const result = importFromAll()
  ElMessage[result.added || result.updated ? 'success' : 'info'](result.message)
}
async function onSyncL1() {
  const result = await syncFromL1(false)
  ElMessage[result.updated ? 'success' : 'info'](result.message)
}
function onSyncDisclosure() {
  const result = syncToDisclosure()
  ElMessage.success(result.message)
}
function onSyncBackH39() {
  const result = syncBackToH39(false)
  ElMessage[result.updated ? 'success' : 'info'](result.message)
}
function onFillCertArea() {
  const n = fillCertAreaPending()
  ElMessage[n ? 'success' : 'info'](n ? `已预填 ${n} 行证载面积（待原件核实）` : '无需预填')
}
function onApplyAuditee() {
  if (!auditeeName.value.trim()) {
    ElMessage.warning('请先填写被审计单位名称')
    return
  }
  const n = applyAuditee()
  ElMessage[n ? 'success' : 'info'](n ? `已带入 ${n} 个字段` : '字段已填写，无需带入')
}
function onSample() {
  const plan = runSample({ targetCoverage: 0.8, minCount: 5 })
  ElMessage.success(plan.message)
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H3-12')
  else if (cmd === 'export-data') await exportData('H3-12')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}
async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importData('H3-12', file)
  ElMessageBox.alert('导入完成。若页面未刷新，请切换 sheet 后返回查看。', '提示')
}

/** 产权证 OCR：上传不动产权证/房产证 → 识别 → 确认 → 回填权属字段 */
async function handleTitleOcr(row: TitleRow) {
  if (props.isReadonly) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const loading = ElMessage({ message: '正在识别产权证…', type: 'info', duration: 0 })
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h3/real-estate-title-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      loading.close()
      const data = res.data?.data ?? res.data
      const f = data?.extracted_fields
      if (!f) { ElMessage.warning('未识别到有效字段，请重试或手工录入'); return }
      const area = Number(f.buildingArea) || Number(f.landArea) || 0
      await ElMessageBox.confirm(
        `识别结果（置信度 ${(Number(data.confidence) * 100).toFixed(0)}%）：\n` +
          `权证号：${f.titleCertNo || '-'}\n权利人：${f.certOwner || '-'}\n` +
          `坐落：${f.address || '-'}\n证载面积：${area || '-'} ㎡\n用途：${f.certPurpose || '-'}\n` +
          `他项权利：${f.otherRights || '-'}\n\n确认填入「${row.assetName || '本行'}」？`,
        '产权证 OCR 识别结果',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
      if (idx < 0) return
      const r = rows.value[idx]
      if (f.titleCertNo) r.titleCertNo = f.titleCertNo
      if (f.certOwner) { r.certOwner = f.certOwner; if (!r.bookOwner) r.bookOwner = f.certOwner }
      if (f.address && !r.location) r.location = f.address
      if (area > 0) { r.certArea = area; r.certAreaPending = false }
      if (f.certPurpose && !r.certPurpose) r.certPurpose = f.certPurpose
      if (f.mortgageNature && !r.mortgageNature) r.mortgageNature = f.mortgageNature
      if (f.titleCertNo && r.certStatus !== '已办证') r.certStatus = '已办证'
      r.ocrResult = JSON.stringify({ at: Date.now(), confidence: data.confidence, fields: f })
      updateRow(idx)
      const restrictedHint = /抵押|查封|冻结|质押/.test(String(f.otherRights || '') + String(f.mortgagee || ''))
      ElMessage.success(restrictedHint ? '已填入；他项权利含抵押/查封，请核对「权利受限」列' : '已填入识别结果')
    } catch (err: any) {
      loading.close()
      if (err === 'cancel' || String(err).includes('cancel')) return
      console.warn('[H3-12 title OCR]', err)
      ElMessage.error('识别失败，请重试或手工录入')
    }
  }
  input.click()
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-title-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert, .impair-alert { margin-bottom: 12px; }
.procedure-card { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.auditee-wrap { display: inline-flex; align-items: center; gap: 4px; }
.auditee-label { font-size: 12px; color: #909399; white-space: nowrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.check-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.check-tag { max-width: 100%; }
.summary-row { display: flex; align-items: center; gap: 14px; margin: 8px 0 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; flex-wrap: wrap; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.export-dropdown { margin-left: 0; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.audit-table :deep(.row-pending) { background-color: #f4f4f5 !important; }
.audit-table :deep(.row-ok-diff) { background-color: #f0f9eb !important; }
.audit-table :deep(.h3-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: h3-row-flash 1.2s ease-in-out 0s 2; }
@keyframes h3-row-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: #d9ecff; }
}
.muted-link { color: var(--el-text-color-placeholder); font-size: 12px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); }
.text-warn { color: var(--el-color-warning); }
.text-danger { color: var(--el-color-danger); }
.text-ok { color: var(--el-color-success); }
.source-tags { font-size: 11px; color: #909399; }
.pending-card, .audit-note-card { margin-top: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
</style>
