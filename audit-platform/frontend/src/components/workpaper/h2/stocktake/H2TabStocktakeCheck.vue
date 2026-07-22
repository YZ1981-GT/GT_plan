<template>
  <div class="h2-tab-stocktake-check">
    <header class="chk-hero">
      <div class="chk-hero-main">
        <div class="chk-kicker">H2-13 · 双向抽盘</div>
        <h2 class="chk-title">在建工程盘点检查表</h2>
        <p class="chk-objective">
          从账面追查至现场（存在性），并从现场追查至账面（完整性）；
          比对账面、企业盘点与审计抽盘三数量，记录进度状况、是否达预定可使用状态及停工线索。
        </p>
      </div>
      <div class="chk-hero-actions">
        <GtIndexChip value="wp:H2-13" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ state.checkRows.value.length }} 项</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'H2-12')">← H2-12</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H2-14')">H2-14 →</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
        <el-button size="small" type="default" link @click="openReview('H2-13')">💬 复核</el-button>
      </div>
    </header>

    <div v-if="!isReadonly" class="action-bar">
      <el-button size="small" type="primary" @click="onImportFromDetail">从 H2-2 带入</el-button>
      <el-button size="small" @click="onImportFromPlan">按 H2-12 样本带入</el-button>
      <el-button size="small" @click="onSyncTotalCost">成本合计←H2-2</el-button>
      <el-button size="small" type="warning" plain @click="emit('navigate-sheet', 'H2-15')">
        停工→H2-15（{{ state.checkStats.value.stopped }}）
      </el-button>
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="!(state.checkStats.value.readyForUseCount > 0)"
        @click="onPushReadyToH25"
      >
        达可用→H2-5（{{ state.checkStats.value.readyForUseCount }}）
      </el-button>
      <el-button size="small" @click="onDraftNote">起草说明</el-button>
      <el-button size="small" @click="onDraftConclusion">起草结论</el-button>
    </div>

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H2-13"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.mp4,.mov"
    />

    <el-alert
      v-if="state.checkStats.value.stopped > 0"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:6px"
      :title="`发现 ${state.checkStats.value.stopped} 个停工项目（${state.stoppedProjectNames.value.join('、')}），需关注减值迹象 → H2-15`"
    />
    <el-alert
      v-if="state.checkStats.value.readyForUseCount > 0"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom:6px"
      :title="`有 ${state.checkStats.value.readyForUseCount} 项现场判断已达预定可使用状态，可一键回写 H2-5 挂账表核查是否及时转固`"
    />

    <nav class="st-sec-nav" aria-label="分区导航">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <section id="sec-obj" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>一、审计目标</h3>
          <p>存在 · 计价和分摊</p>
        </div>
      </header>
      <ul class="obj-list">
        <li>资产负债表中记录的在建工程是存在的，且已记录于恰当的账户</li>
        <li>在建工程以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述</li>
      </ul>
    </section>

    <section id="sec-sample" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>二、样本选取标准与规模</h3>
          <p>测试总体 → 特定样本 → 抽样总体 / 方法</p>
        </div>
        <el-button v-if="!isReadonly" size="small" plain @click="onSyncMetaFromPlan">从 H2-12 带入</el-button>
        <el-button v-if="!isReadonly" size="small" plain @click="onSyncTotalCost">成本←H2-2</el-button>
      </header>
      <el-form label-width="110px" size="small" class="meta-form">
        <el-form-item label="测试总体">
          <el-input
            :model-value="meta.testPopulation"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="如：期末在建工程项目数量 XX、金额 XX"
            @update:model-value="(v: string) => updateMeta('testPopulation', v)"
          />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="特定样本">
              <el-input
                :model-value="meta.specificSample"
                type="textarea"
                :rows="2"
                :disabled="isReadonly"
                placeholder="大额、关联方、长期停滞、异常工程等"
                @update:model-value="(v: string) => updateMeta('specificSample', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="抽样总体">
              <el-input
                :model-value="meta.samplingPopulation"
                type="textarea"
                :rows="2"
                :disabled="isReadonly"
                placeholder="测试总体剔除特定样本后的剩余项目"
                @update:model-value="(v: string) => updateMeta('samplingPopulation', v)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="抽样方法">
              <el-select
                :model-value="meta.samplingMethod"
                :disabled="isReadonly"
                style="width:100%"
                allow-create
                filterable
                @update:model-value="(v: string) => updateMeta('samplingMethod', v)"
              >
                <el-option v-for="m in SAMPLING_METHOD_OPTS" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="成本合计">
              <el-input-number
                :model-value="meta.totalBookCost ?? undefined"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                style="width:100%"
                placeholder="覆盖率分母，避免除零"
                @update:model-value="(v: number | undefined) => updateMeta('totalBookCost', v ?? null)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="抽样过程">
          <el-input
            :model-value="meta.samplingProcess"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="如：使用 IDEA 等审计软件选取样本…"
            @update:model-value="(v: string) => updateMeta('samplingProcess', v)"
          />
        </el-form-item>
      </el-form>
    </section>

    <section id="sec-process" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>三、审计过程</h3>
          <p>地点 · 人员 · 时间</p>
        </div>
      </header>
      <el-form label-width="110px" size="small" class="meta-form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="盘点地点">
              <el-input
                :model-value="meta.location"
                :disabled="isReadonly"
                placeholder="施工现场/仓库等"
                @update:model-value="(v: string) => updateMeta('location', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点时间">
              <el-input
                :model-value="meta.countTime"
                :disabled="isReadonly"
                placeholder="现场盘点起止时间"
                @update:model-value="(v: string) => updateMeta('countTime', v)"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="企业盘点人员">
              <el-input
                :model-value="meta.clientStaff"
                :disabled="isReadonly"
                placeholder="工程/财务陪同人员"
                @update:model-value="(v: string) => updateMeta('clientStaff', v)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="监盘人员">
              <el-input
                :model-value="meta.auditors"
                :disabled="isReadonly"
                placeholder="项目组签字人"
                @update:model-value="(v: string) => updateMeta('auditors', v)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </section>

    <section id="sec-exist" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>（一）从在建工程账面追查至现场</h3>
          <p>测存在性 · 账面 / 企业盘点 / 审计抽盘</p>
        </div>
        <div class="chk-card-actions">
          <el-tag v-if="b2fCov.varianceCount > 0" size="small" type="danger">{{ b2fCov.varianceCount }} 行差异</el-tag>
          <el-tag v-else-if="b2fRows.length" size="small" type="success">无差异</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('bookToFloor')">+ 明细行</el-button>
        </div>
      </header>
      <H2CheckDirectionTable
        :rows="b2fRows"
        :is-readonly="isReadonly"
        empty-text="暂无「账面→现场」明细；可从 H2-2 / H2-12 带入或新增"
        @update="onRowUpdate"
        @remove="(id) => state.removeCheckRow(id)"
      />
      <div v-if="b2fRows.length" class="coverage-bar">
        <span>抽盘账面金额合计 <b>{{ fmtAmt(b2fCov.sampleAmount) }}</b></span>
        <span>在建工程成本合计 <b>{{ meta.totalBookCost != null ? fmtAmt(meta.totalBookCost) : '—' }}</b></span>
        <span>
          覆盖率
          <b :class="{ 'warn-text': b2fCov.ratioPct != null && b2fCov.ratioPct < 5 }">
            {{ b2fCov.ratioPct != null ? `${b2fCov.ratioPct.toFixed(2)}%` : '—（请填成本合计）' }}
          </b>
        </span>
      </div>
    </section>

    <section id="sec-floor" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>（二）从现场追查至在建工程账面</h3>
          <p>测完整性 · 列结构与上表相同</p>
        </div>
        <div class="chk-card-actions">
          <el-tag v-if="f2bCov.varianceCount > 0" size="small" type="danger">{{ f2bCov.varianceCount }} 行差异</el-tag>
          <el-tag v-else-if="f2bRows.length" size="small" type="success">无差异</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('floorToBook')">+ 明细行</el-button>
        </div>
      </header>
      <H2CheckDirectionTable
        :rows="f2bRows"
        :is-readonly="isReadonly"
        empty-text="暂无「现场→账面」明细；完整性测试不可省略"
        @update="onRowUpdate"
        @remove="(id) => state.removeCheckRow(id)"
      />
      <div v-if="f2bRows.length" class="coverage-bar">
        <span>抽盘账面金额合计 <b>{{ fmtAmt(f2bCov.sampleAmount) }}</b></span>
        <span>在建工程成本合计 <b>{{ meta.totalBookCost != null ? fmtAmt(meta.totalBookCost) : '—' }}</b></span>
        <span>
          覆盖率
          <b :class="{ 'warn-text': f2bCov.ratioPct != null && f2bCov.ratioPct < 5 }">
            {{ f2bCov.ratioPct != null ? `${f2bCov.ratioPct.toFixed(2)}%` : '—（请填成本合计）' }}
          </b>
        </span>
      </div>
    </section>

    <div class="summary-bar">
      <span>账实相符 <b>{{ stats.matchCount }}</b></span>
      <span>盘盈 <b>{{ stats.surplusCount }}</b></span>
      <span>盘亏 <b :class="{ 'error-amount': stats.deficitCount > 0 }">{{ stats.deficitCount }}</b></span>
      <span>相符率 <b>{{ stats.matchRate.toFixed(1) }}%</b></span>
      <span>停工 <b :class="{ 'error-amount': stats.stopped > 0 }">{{ stats.stopped }}</b></span>
      <span>达可使用 <b>{{ stats.readyForUseCount }}</b></span>
    </div>

    <section id="sec-findings" class="chk-card">
      <header class="chk-card-head"><div><h3>四、盘点情况说明</h3></div></header>
      <el-input
        v-model="findingsText"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="描述现场盘点总体情况、形象进度与账面差异、停工/达可使用状态等定性发现…"
        @change="saveFindings"
      />
    </section>

    <section id="sec-note" class="chk-card">
      <header class="chk-card-head"><div><h3>五、审计说明</h3></div></header>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写：监盘执行情况、账实差异及原因、企业对盘盈盘亏的处理、停工减值/转固跟进。"
        @change="saveAuditNote"
      />
    </section>

    <section id="sec-conclusion" class="chk-card">
      <header class="chk-card-head"><div><h3>六、审计结论</h3></div></header>
      <el-input
        v-model="auditConclusionText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="就本节审计目标是否实现发表结论…"
        @change="saveAuditConclusion"
      />
    </section>

    <details class="compile-hint">
      <summary>提示</summary>
      <ol>
        <li>本表可作为在建工程盘点汇总表、明细表或抽盘表使用；亦可参照固定资产抽盘表结构。</li>
        <li>财务账面记录应与工程/资产管理部门记录核对一致；不一致应先调节。</li>
        <li>账面与实盘差异为盘盈/盘亏，须分析原因并说明企业处理方式。</li>
        <li>盘点时关注易移动/易侵占的存量工程物资，以及可能发生减值的停滞工程。</li>
        <li>是否达预定可使用状态影响转固与折旧起算；停工时间/原因直接影响减值准备判断（→H2-15）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakeCheck.vue — H2-13 盘点检查
 * 对齐致同模板结构，参照 H1-10 双向抽盘 + CIP 专用列
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH2Stocktake, type H2StocktakeCheckRow, type StocktakeDirection } from '../../composables/useH2Stocktake'
import { SAMPLING_METHOD_OPTS } from '../../composables/h2StocktakeCheckModel'
import { mergeH213ReadyIntoCipRows } from '../../composables/useH2TransferCheck'
import { useH2ImportExport } from '../../composables/useH2ImportExport'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import H2CheckDirectionTable from './H2CheckDirectionTable.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'check',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)
const { exportTemplate, exportData, importData } = useH2ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const NOTE_KEY = 'H2-13-audit-note'
const CONCLUSION_KEY = 'H2-13-audit-conclusion'
const FINDINGS_KEY = 'H2-13-findings'
const auditNoteText = ref('')
const auditConclusionText = ref('')
const findingsText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

function saveAuditNote() {
  if (props.isReadonly) return
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNoteText.value })
  saveResponse(NOTE_KEY, auditNoteText.value)
}
function saveAuditConclusion() {
  if (props.isReadonly) return
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusionText.value })
  saveResponse(CONCLUSION_KEY, auditConclusionText.value)
}
function saveFindings() {
  if (props.isReadonly) return
  props.allResponses.set(FINDINGS_KEY, { item_id: FINDINGS_KEY, conclusion: null, remark: findingsText.value })
  saveResponse(FINDINGS_KEY, findingsText.value)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
  const f = props.allResponses.get(FINDINGS_KEY)
  if (f?.remark) findingsText.value = f.remark
})

const meta = computed(() => state.checkMeta.value)
const b2fRows = computed(() => state.bookToFloorRows.value)
const f2bRows = computed(() => state.floorToBookRows.value)
const b2fCov = computed(() => state.bookToFloorCoverage.value)
const f2bCov = computed(() => state.floorToBookCoverage.value)
const stats = computed(() => state.checkStats.value)

const navItems = [
  { id: 'sec-obj', label: '一·目标' },
  { id: 'sec-sample', label: '二·样本' },
  { id: 'sec-process', label: '三·过程' },
  { id: 'sec-exist', label: '账面→现场' },
  { id: 'sec-floor', label: '现场→账面' },
  { id: 'sec-findings', label: '四·情况' },
  { id: 'sec-note', label: '五·说明' },
  { id: 'sec-conclusion', label: '六·结论' },
]
const { activeId, scrollTo } = useStickySectionNav(navItems)

function updateMeta(field: keyof typeof meta.value, value: any) {
  state.updateCheckMeta(field, value)
}

function addRow(direction: StocktakeDirection) {
  state.addCheckRow('', direction)
}

function onRowUpdate(rowId: string, patch: Partial<H2StocktakeCheckRow>) {
  state.updateCheckRow(rowId, patch)
}

function onSyncMetaFromPlan() {
  state.syncCheckMetaFromPlan()
  ElMessage.success('已从 H2-12 带入地点/人员/特定样本（仅填空项）')
}

function onImportFromDetail() {
  const { imported } = state.importCheckRowsFromDetail({ maxRows: 50 })
  ElMessage.success(imported ? `已从 H2-2 带入 ${imported} 项（账面→现场，大额优先）` : 'H2-2 无可用明细或均已存在')
}

function onImportFromPlan() {
  const { imported } = state.importCheckRowsFromPlan()
  ElMessage.success(imported ? `已按 H2-12 样本带入 ${imported} 项` : '未带入新行（可能已存在或计划为空）')
}

function onSyncTotalCost() {
  const total = state.syncTotalBookCostFromDetail()
  if (total > 0) {
    ElMessage.success(`成本合计已取自 H2-2：${total.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  } else {
    ElMessage.warning('H2-2 无成本数据可取')
  }
}

/** 达可用=是 → 一键回写 H2-5 表一挂账 */
function onPushReadyToH25() {
  if (props.isReadonly) return
  const h213 = state.checkRows.value
  const readyCount = h213.filter(r => r.readyForUse === '是').length
  if (!readyCount) {
    ElMessage.warning('无「达可用=是」的盘点行')
    return
  }

  let existingCip: any[] = []
  const resp = props.allResponses.get('H2-5-cip-rows')
  const raw = resp?.remark ?? resp?.conclusion
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existingCip = parsed
    } catch { /* ignore */ }
  }

  const { rows, updated, added } = mergeH213ReadyIntoCipRows(existingCip as any, h213)
  if (updated + added === 0) {
    ElMessage.info('达可用项目已在 H2-5 挂账表中，未新增')
    return
  }

  const toPersist = rows.map(r => ({
    rowId: r.rowId,
    name: r.name,
    cipOriginal: r.cipOriginal,
    capitalizedInterest: r.capitalizedInterest,
    impairment: r.impairment,
    budget: r.budget,
    plannedReadyDate: r.plannedReadyDate,
    startDate: r.startDate,
    readyCriteria: r.readyCriteria,
    readyForUse: r.readyForUse,
    readyDate: r.readyDate,
    notTransferReason: r.notTransferReason,
    proposedTransferPct: r.proposedTransferPct,
    postPeriodTransfer: r.postPeriodTransfer,
    postPeriodVoucherNos: r.postPeriodVoucherNos,
    usefulLifeYears: r.usefulLifeYears,
    salvageRatePct: r.salvageRatePct,
    remark: r.remark,
  }))
  saveResponse('H2-5-cip-rows', toPersist)
  ElMessage.success(`已回写 H2-5 挂账表：更新 ${updated}、新增 ${added}。可切换至 H2-5 继续核查。`)
}

function onDraftNote() {
  if (props.isReadonly) return
  auditNoteText.value = state.draftCheckNoteLocal()
  saveAuditNote()
  ElMessage.success('已起草审计说明，可继续编辑')
}

function onDraftConclusion() {
  if (props.isReadonly) return
  auditConclusionText.value = state.draftCheckConclusionLocal()
  saveAuditConclusion()
  ElMessage.success('已起草审计结论，可继续编辑')
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H2-13')
  else if (cmd === 'export-data') await exportData('H2-13')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importData('H2-13', file)
  ElMessageBox.alert('导入完成。若页面未刷新，请切换 sheet 后返回查看。', '提示')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-stocktake-check {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chk-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 12px 14px;
  background: linear-gradient(135deg, var(--el-fill-color-lighter), var(--el-bg-color));
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.chk-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--el-color-primary);
  font-weight: 600;
  margin-bottom: 4px;
}
.chk-title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 650;
  color: var(--el-text-color-primary);
}
.chk-objective {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
  max-width: 640px;
}
.chk-hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.st-sec-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 6px 0;
  background: var(--el-bg-color);
}
.st-sec-btn {
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  border-radius: 14px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.st-sec-btn.active {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.chk-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-bg-color);
}
.chk-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.chk-card-head h3 {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
}
.chk-card-head p {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chk-card-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.obj-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.meta-form { max-width: 960px; }
.coverage-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
  padding: 8px 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 12px;
}
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 13px;
}
.warn-text { color: var(--el-color-warning); }
.error-amount { color: var(--el-color-danger); }
.compile-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; }
</style>
