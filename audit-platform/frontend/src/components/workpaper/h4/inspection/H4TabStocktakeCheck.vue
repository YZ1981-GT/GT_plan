<template>
  <div class="h4-tab-stocktake-check">
    <header class="chk-hero">
      <div class="chk-hero-main">
        <div class="chk-kicker">H4-6 · 双向抽盘</div>
        <h2 class="chk-title">工程物资盘点检查表</h2>
        <p class="chk-objective">
          从账面追查至实物（存在性），并从实物追查至账面（完整性）；
          比对账面、企业盘点与审计抽盘三数量，记录品质状况并联动减值关注。
        </p>
      </div>
      <div class="chk-hero-actions">
        <GtIndexChip value="wp:H4-6" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-6A')">← H4-6A</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-6B')">H4-6B →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-7')">H4-7 →</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
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
        <el-button size="small" type="default" link @click="openReview('H4-6')">💬 复核</el-button>
      </div>
    </header>

    <div v-if="!isReadonly" class="action-bar">
      <el-button size="small" type="primary" @click="onImportFromH42('bookToFloor')">从 H4-2 带入（存在）</el-button>
      <el-button size="small" @click="onImportFromH42('floorToBook')">从 H4-2 带入（完整）</el-button>
      <el-button size="small" @click="onSyncTotalCost">期末余额←H4-2</el-button>
      <el-button size="small" type="warning" plain :disabled="!concernN" @click="onPushConcernsToH47">
        推送减值关注→H4-7（{{ concernN }}）
      </el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="!(stats.surplusCount + stats.deficitCount)"
        @click="onPushAje"
      >
        推送盘盈盘亏→H4-3
      </el-button>
      <el-button size="small" @click="onDraftNote">起草说明</el-button>
      <el-button size="small" @click="onDraftConclusion">起草结论</el-button>
    </div>

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H4-6"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.mp4,.mov"
    />

    <el-alert
      v-if="stats.varianceCount > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom:6px"
      :title="`发现 ${stats.varianceCount} 项三数量差异，须在差异原因列说明并追查`"
    />
    <el-alert
      v-if="stats.concernCount > 0"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:6px"
      :title="`发现 ${stats.concernCount} 项品质/盘亏关注（闲置·积压·毁损·盘亏），建议推送至 H4-7`"
    />
    <el-alert
      v-if="stats.bookToFloorCount > 0 && stats.floorToBookCount === 0"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:6px"
      title="已做账面→实物存在性抽盘，但尚未记录实物→账面完整性测试，建议补充"
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
          <p>存在 · 完整性 · 计价和分摊 / 列报</p>
        </div>
      </header>
      <ul class="obj-list">
        <li>资产负债表中记录的工程物资是存在的，并由被审计单位拥有或控制</li>
        <li>所有应当记录的工程物资均已记录</li>
        <li>工程物资以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述</li>
      </ul>
    </section>

    <section id="sec-sample" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>二、样本选取标准与规模</h3>
          <p>测试总体 → 特定样本 → 抽样总体 / 方法</p>
        </div>
        <el-button v-if="!isReadonly" size="small" plain @click="onSyncTotalCost">余额←H4-2</el-button>
      </header>
      <el-form label-width="120px" size="small" class="meta-form">
        <el-form-item label="测试总体">
          <el-input
            :model-value="meta.testPopulation"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="如：期末工程物资数量 XX、余额合计 XX"
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
                placeholder="大额、关联方、长期积压、异常规格等"
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
            <el-form-item label="期末余额合计">
              <WpAmountInput
                :model-value="meta.totalBookCost ?? undefined"
                :disabled="isReadonly"
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
      <el-form label-width="120px" size="small" class="meta-form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="抽盘地点">
              <el-input
                :model-value="meta.location"
                :disabled="isReadonly"
                placeholder="仓库/工地堆场等"
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
                placeholder="仓管/工程/财务陪同人员"
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
          <h3>（一）从工程物资账面追查至实物</h3>
          <p>测存在性 · 账面 / 企业盘点 / 审计抽盘</p>
        </div>
        <div class="chk-card-actions">
          <el-tag v-if="b2fCov.varianceCount > 0" size="small" type="danger">{{ b2fCov.varianceCount }} 行差异</el-tag>
          <el-tag v-else-if="b2fRows.length" size="small" type="success">无差异</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('bookToFloor')">+ 明细行</el-button>
        </div>
      </header>
      <H4CheckDirectionTable
        :rows="b2fRows"
        :is-readonly="isReadonly"
        empty-text="暂无「账面→实物」明细；可从 H4-2 带入或新增"
        @update="onRowUpdate"
        @remove="removeRow"
      />
      <div v-if="b2fRows.length" class="coverage-bar">
        <span>抽盘账面金额合计 <b>{{ fmtAmt(b2fCov.sampleAmount) }}</b></span>
        <span>期末余额合计 <b>{{ meta.totalBookCost != null ? fmtAmt(meta.totalBookCost) : '—' }}</b></span>
        <span>
          覆盖率
          <b :class="{ 'warn-text': b2fCov.ratioPct != null && b2fCov.ratioPct < 5 }">
            {{ b2fCov.ratioPct != null ? `${b2fCov.ratioPct.toFixed(2)}%` : '—（请填期末余额合计）' }}
          </b>
        </span>
      </div>
    </section>

    <section id="sec-floor" class="chk-card">
      <header class="chk-card-head">
        <div>
          <h3>（二）从工程物资实物追查至账面</h3>
          <p>测完整性 · 列结构与上表相同</p>
        </div>
        <div class="chk-card-actions">
          <el-tag v-if="f2bCov.varianceCount > 0" size="small" type="danger">{{ f2bCov.varianceCount }} 行差异</el-tag>
          <el-tag v-else-if="f2bRows.length" size="small" type="success">无差异</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('floorToBook')">+ 明细行</el-button>
        </div>
      </header>
      <H4CheckDirectionTable
        :rows="f2bRows"
        :is-readonly="isReadonly"
        empty-text="暂无「实物→账面」明细；完整性测试不可省略"
        @update="onRowUpdate"
        @remove="removeRow"
      />
      <div v-if="f2bRows.length" class="coverage-bar">
        <span>抽盘账面金额合计 <b>{{ fmtAmt(f2bCov.sampleAmount) }}</b></span>
        <span>期末余额合计 <b>{{ meta.totalBookCost != null ? fmtAmt(meta.totalBookCost) : '—' }}</b></span>
        <span>
          覆盖率
          <b :class="{ 'warn-text': f2bCov.ratioPct != null && f2bCov.ratioPct < 5 }">
            {{ f2bCov.ratioPct != null ? `${f2bCov.ratioPct.toFixed(2)}%` : '—（请填期末余额合计）' }}
          </b>
        </span>
      </div>
    </section>

    <div class="summary-bar">
      <span>账实相符 <b>{{ stats.matchCount }}</b></span>
      <span>盘盈 <b>{{ stats.surplusCount }}</b></span>
      <span>盘亏 <b :class="{ 'error-amount': stats.deficitCount > 0 }">{{ stats.deficitCount }}</b></span>
      <span>相符率 <b>{{ stats.matchRate.toFixed(1) }}%</b></span>
      <span>闲置/积压 <b :class="{ 'warn-text': stats.idleCount > 0 }">{{ stats.idleCount }}</b></span>
      <span>毁损/待报废 <b :class="{ 'warn-text': stats.damagedCount > 0 }">{{ stats.damagedCount }}</b></span>
      <span v-if="stats.deficitAmount > 0">盘亏金额 <b class="error-amount">{{ fmtAmt(stats.deficitAmount) }}</b></span>
    </div>

    <section id="sec-note" class="chk-card">
      <header class="chk-card-head">
        <div><h3>四、盘点情况说明</h3></div>
        <el-button size="small" @click="generateAI('H4-6')">AI</el-button>
      </header>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写：双向抽盘执行情况、三数量差异及原因、闲置/毁损/积压处理；监盘计划与小结可参考固定资产做法。"
        @change="saveAuditNote"
      />
    </section>

    <section id="sec-conclusion" class="chk-card">
      <header class="chk-card-head"><div><h3>五、审计结论</h3></div></header>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="就本节审计目标是否实现发表结论…"
        @change="saveAuditConclusion"
      />
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ol>
        <li>本表对齐致同「工程物资盘点检查表」：目标→样本→过程→三数量明细→说明→结论。</li>
        <li>三数量：账面 / 企业盘点 / 审计抽盘；差异列自动计算（抽盘−账面、抽盘−企业、企业−账面）。</li>
        <li>期末余额合计须先填（或自 H4-2 同步），否则覆盖率显示「—」而非除零错误。</li>
        <li>品质为闲置/积压/毁损或盘亏时，推送减值关注至 H4-7。</li>
        <li>完整性测试（实物→账面）不可省略，避免仅测存在性。</li>
        <li>监盘计划见 H4-6A，监盘小结见 H4-6B（参照固定资产范式）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H4TabStocktakeCheck.vue — H4-6 盘点检查表（致同五段式 + 双向抽盘 + 三数量）
 */
import { ref, computed, toRef, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useH4Stocktake } from '../../composables/useH4Stocktake'
import { useH4ImportExport } from '../../composables/useH4ImportExport'
import {
  SAMPLING_METHOD_OPTS,
  type StocktakeDirection,
  type H4StocktakeCheckRow,
} from '../../composables/h4StocktakeCheckModel'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import H4CheckDirectionTable from './H4CheckDirectionTable.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const {
  rows, meta, auditNote, auditConclusion, stats,
  bookToFloorRows, floorToBookRows, bookToFloorCoverage, floorToBookCoverage,
  addRow, removeRow, updateRow, updateMeta,
  saveAuditNote, saveAuditConclusion,
  importFromH42, syncTotalBookCost, draftNote, draftConclusion, concernCount,
  pushImpairmentConcernsToH47, pushAjeDraftToH43, loadAll,
} = useH4Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses') as any,
})

const { exportTemplate, exportData, importData, isImporting: importing } = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => loadAll(),
})

const fileInputRef = ref<HTMLInputElement | null>(null)
const b2fRows = bookToFloorRows
const f2bRows = floorToBookRows
const b2fCov = bookToFloorCoverage
const f2bCov = floorToBookCoverage
const concernN = computed(() => concernCount())
const isReadonly = computed(() => props.isReadonly)
const projectId = computed(() => props.projectId)
const wpId = computed(() => props.wpId)

const navItems = [
  { id: 'sec-obj', label: '一·目标' },
  { id: 'sec-sample', label: '二·样本' },
  { id: 'sec-process', label: '三·过程' },
  { id: 'sec-exist', label: '账面→实物' },
  { id: 'sec-floor', label: '实物→账面' },
  { id: 'sec-note', label: '四·说明' },
  { id: 'sec-conclusion', label: '五·结论' },
]
const { activeId, scrollTo } = useStickySectionNav(navItems)

function onRowUpdate(rowId: string, patch: Partial<H4StocktakeCheckRow>) {
  updateRow(rowId, patch)
}

function onImportFromH42(direction: StocktakeDirection) {
  const r = importFromH42({ direction, maxRows: 50 })
  ElMessage[r.added ? 'success' : 'info'](r.message)
}

function onSyncTotalCost() {
  const r = syncTotalBookCost()
  ElMessage[r.ok ? 'success' : 'warning'](r.message)
}

function onPushConcernsToH47() {
  const r = pushImpairmentConcernsToH47()
  ElMessage[r.concernCount > 0 ? 'success' : 'info'](r.message)
  if (r.concernCount > 0) emit('navigate-sheet', 'H4-7')
}

function onPushAje() {
  const res = pushAjeDraftToH43()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function onDraftNote() {
  draftNote()
  ElMessage.success('已起草盘点情况说明，可继续编辑')
}

function onDraftConclusion() {
  draftConclusion()
  ElMessage.success('已起草审计结论，可继续编辑')
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H4-6')
  else if (cmd === 'export-data') await exportData('H4-6')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importData('H4-6', file)
  loadAll()
  ElMessageBox.alert('导入完成。若页面未刷新，请切换 sheet 后返回查看。', '提示')
}

const aiLoading = ref(false)
async function generateAI(section: string) {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      context: { wpCode: 'H4', sheet: 'H4-6 盘点检查表', section },
      existingContent: '',
    })
    const text = res.data?.data?.text ?? res.data?.text ?? ''
    if (text) {
      ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '关闭' }).catch(() => {})
    } else {
      ElMessage.warning('AI 暂无建议')
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}
function openReview(section: string) { openReviewDialog(section) }

function fmtAmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-stocktake-check {
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
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.st-sec-btn.active,
.st-sec-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
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
  gap: 12px;
  margin-bottom: 10px;
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
.chk-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.obj-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.meta-form :deep(.el-form-item) { margin-bottom: 10px; }
.coverage-bar,
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 10px 12px;
  margin-top: 10px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.warn-text,
.error-amount { color: var(--el-color-danger); }
.compile-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; line-height: 1.7; }
@media (max-width: 900px) {
  .chk-hero { flex-direction: column; }
}
</style>
