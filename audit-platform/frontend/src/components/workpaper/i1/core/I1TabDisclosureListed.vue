<template>
  <div class="i1-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制无形资产披露——原值/累计摊销/减值/账面价值分类变动，与 I1-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 Excel + CAS6/CAS30）：①分类列 × 变动行 → ②期末=期初+增−减、账面价值=原值−摊销−减值 →
        ③补充研发占比/寿命不确定/抵押/减值/高价出售/重要单项 → ④同步附注五、26。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="success" effect="plain">五、26 无形资产</el-tag>
        <el-radio-group v-if="!isReadonly" v-model="presetLocal" size="small" @change="onPresetChange">
          <el-radio-button value="full">全量列</el-radio-button>
          <el-radio-button value="compact">模板精简</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handlePull(false)">从 I1-2/检查表取数</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handlePull(true)">取数并覆盖文字</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="i1-disclosure-listed-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注（五、26）</el-button>
        <el-button size="small" type="primary" plain @click="emit('open-ai', 'disclosure-listed')">AI 辅助</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:I1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:I1-9" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div v-if="crossCheck.hasAnyWarning" class="cross-warning">
      披露合计与 I1 审定表差异：原值 {{ fmt(crossCheck.costDiff) }} / 摊销 {{ fmt(crossCheck.amortDiff) }} / 减值 {{ fmt(crossCheck.impairDiff) }}
    </div>
    <div v-if="prepValidation.blocking.length || prepValidation.warnings.length" class="prep-box">
      <div v-for="(m, i) in prepValidation.blocking" :key="'b'+i" class="prep-block">⛔ {{ m }}</div>
      <div v-for="(m, i) in prepValidation.warnings" :key="'w'+i" class="prep-warn">⚠ {{ m }}</div>
    </div>

    <section class="block">
      <div class="block-head">
        <h3 class="block-title">无形资产情况</h3>
        <div v-if="!isReadonly" class="cat-bar">
          <el-button size="small" @click="handleAddCat">+ 增加资产类别列</el-button>
          <span class="hint">源模板「……」列：按被审计单位实际类别扩展</span>
        </div>
      </div>
      <div class="movement-wrap">
        <el-table
          :data="movementRowDefs"
          border
          size="small"
          class="wp-table movement-table"
          :row-class-name="movementRowClass"
        >
          <el-table-column label="项  目" min-width="220" fixed>
            <template #default="{ row }">
              <span :style="{ paddingLeft: `${row.indent * 12}px` }" :class="`kind-${row.kind}`">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-for="cat in categories"
            :key="cat.key"
            :label="cat.label"
            min-width="110"
            align="right"
          >
            <template #header>
              <div class="cat-header">
                <span>{{ cat.label }}</span>
                <el-button
                  v-if="!isReadonly && !isDefaultCat(cat.key)"
                  link
                  size="small"
                  type="danger"
                  @click="removeCategory(cat.key)"
                >
                  删
                </el-button>
              </div>
            </template>
            <template #default="{ row }">
              <template v-if="row.kind === 'section'">—</template>
              <WpAmountInput
                v-else-if="row.editable && !isReadonly"
                :model-value="rawCell(movement, row.key, cat.key)"
                size="small"
                style="width:100%"
                @change="(v: number) => updateMovement(row.key, cat.key, v)"
              />
              <span v-else class="formula-cell">{{ fmt(cellOf(row, cat.key)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合  计" min-width="110" align="right" fixed="right">
            <template #default="{ row }">
              <span v-if="row.kind === 'section'">—</span>
              <span v-else class="formula-cell">{{ fmt(totalOf(row)) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <section class="block notes-block">
      <h3 class="block-title">文字说明（同步至附注）</h3>
      <div class="note-item">
        <label>① 内部研发占比</label>
        <el-input v-model="noteRdRatio" type="textarea" :rows="2" :disabled="isReadonly" :placeholder="GUIDANCE.rdRatio" @change="persist" />
      </div>
      <div class="note-item">
        <label>② 寿命不确定判断依据</label>
        <el-input v-model="noteIndefinite" type="textarea" :rows="2" :disabled="isReadonly" :placeholder="GUIDANCE.indefinite" @change="persist" />
      </div>
      <div class="note-item">
        <label>③ 抵押担保</label>
        <el-input v-model="noteMortgage" type="textarea" :rows="2" :disabled="isReadonly" :placeholder="GUIDANCE.mortgage" @change="persist" />
      </div>
      <div class="note-item">
        <label>④ 减值测试</label>
        <el-input v-model="noteImpairment" type="textarea" :rows="3" :disabled="isReadonly" :placeholder="GUIDANCE.impairment" @change="persist" />
      </div>
      <div class="note-item">
        <label>⑤ 高价出售</label>
        <el-input v-model="noteSale" type="textarea" :rows="2" :disabled="isReadonly" :placeholder="GUIDANCE.sale" @change="persist" />
      </div>
      <div class="note-item">
        <label>⑥ 重要单项说明</label>
        <el-input v-model="noteImportant" type="textarea" :rows="2" :disabled="isReadonly" :placeholder="GUIDANCE.important" @change="persist" />
      </div>
    </section>

    <section class="block">
      <h3 class="block-title">本期摊销费用归属（I1-9）</h3>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="生产成本">{{ fmt(amortAlloc.productionCost) }}</el-descriptions-item>
        <el-descriptions-item label="制造费用">{{ fmt(amortAlloc.manufacturing) }}</el-descriptions-item>
        <el-descriptions-item label="销售费用">{{ fmt(amortAlloc.selling) }}</el-descriptions-item>
        <el-descriptions-item label="管理费用">{{ fmt(amortAlloc.management) }}</el-descriptions-item>
        <el-descriptions-item label="研发费用">{{ fmt(amortAlloc.rd) }}</el-descriptions-item>
        <el-descriptions-item label="其他">{{ fmt(amortAlloc.other) }}</el-descriptions-item>
        <el-descriptions-item label="合计">{{ fmt(amortAlloc.total) }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <section class="block">
      <h3 class="block-title">确认为无形资产的数据资源</h3>
      <el-table :data="dataResourceRows" border size="small">
        <el-table-column prop="label" label="项目" min-width="160" />
        <el-table-column label="金额" min-width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.field && !isReadonly"
              :model-value="(dataResource as any)[row.field]"
              size="small"
              style="width:100%"
              @change="(v: number) => updateDataResource(row.field, v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.value) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-input
        v-model="noteDataResource"
        class="mt8"
        type="textarea"
        :rows="2"
        :disabled="isReadonly"
        placeholder="数据资源寿命/摊销/减值/受限等补充说明"
        @change="persist"
      />
    </section>

    <section class="block">
      <div class="block-head">
        <h3 class="block-title">重要单项无形资产</h3>
        <el-button v-if="!isReadonly" size="small" @click="addImportantRow">+ 行</el-button>
      </div>
      <el-table :data="importantRows" border size="small">
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :disabled="isReadonly" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-model="row.bookValue" size="small" :disabled="isReadonly" style="width:100%" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="剩余摊销期限(月)" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.remainingAmortMonths" :controls="false" size="small" :disabled="isReadonly" style="width:100%" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeImportantRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="block">
      <div class="block-head">
        <h3 class="block-title">未办妥权属证书</h3>
        <el-button v-if="!isReadonly" size="small" @click="addTitleCertRow">+ 行</el-button>
      </div>
      <p class="hint">{{ GUIDANCE.titleCert }}</p>
      <el-table :data="titleCertRows" border size="small">
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :disabled="isReadonly" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-model="row.bookValue" size="small" :disabled="isReadonly" style="width:100%" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.reason" size="small" :disabled="isReadonly" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeTitleCertRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-card shadow="never" class="audit-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :rows="3" :disabled="isReadonly" @change="persist" />
    </el-card>
    <el-card shadow="never" class="audit-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusion" type="textarea" :rows="2" :disabled="isReadonly" @change="persist" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI1ListedDisclosure } from '../../composables/useI1Disclosure'
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  I1_LISTED_GUIDANCE,
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  rawCell,
  type MovementRowDef,
} from '../../composables/i1ListedDisclosureModel'
import {
  dataResourceAmortEnd,
  dataResourceBookEnd,
  dataResourceCostEnd,
  dataResourceImpairEnd,
  type I1ListedCategoryPreset,
} from '../../composables/i1DisclosureEnhance'
import { buildI1ListedSyncPayloads } from '../../composables/i1DisclosureSyncPayload'
import { I1_DISCLOSURE_SHEET_NAME, I1_NOTE_SECTION } from '../../composables/i1NoteSectionMap'
import { useRestrictedAssetsSync } from '../../composables/useRestrictedAssetsSync'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
}>()

const GUIDANCE = I1_LISTED_GUIDANCE
const noteSectionId = I1_NOTE_SECTION.listed
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const isSyncing = ref(false)
const movementRowDefs = I1_LISTED_MOVEMENT_ROWS

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'I1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const {
  categoryPreset,
  categories,
  movement,
  noteRdRatio,
  noteIndefinite,
  noteMortgage,
  noteImpairment,
  noteSale,
  noteImportant,
  noteDataResource,
  titleCertRows,
  importantRows,
  dataResource,
  amortAlloc,
  auditNote,
  auditConclusion,
  crossCheck,
  prepValidation,
  persist,
  updateMovement,
  addCategory,
  removeCategory,
  setCategoryPreset,
  addTitleCertRow,
  removeTitleCertRow,
  addImportantRow,
  removeImportantRow,
  updateDataResource,
  pullFromSources,
} = useI1ListedDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => emit('save', id, v),
})

const presetLocal = ref<I1ListedCategoryPreset>(categoryPreset.value)
watch(categoryPreset, (v) => { presetLocal.value = v })

function onPresetChange(v: string | number | boolean | undefined) {
  setCategoryPreset((v === 'compact' ? 'compact' : 'full') as I1ListedCategoryPreset)
}

const dataResourceRows = computed(() => {
  const m = dataResource.value
  return [
    { label: '原值期初', field: 'costBegin', value: m.costBegin },
    { label: '原值增加-外购', field: 'costIncPurchase', value: m.costIncPurchase },
    { label: '原值增加-内部研发', field: 'costIncRd', value: m.costIncRd },
    { label: '原值增加-其他', field: 'costIncOther', value: m.costIncOther },
    { label: '原值减少', field: 'costDec', value: m.costDec },
    { label: '原值期末', field: '', value: dataResourceCostEnd(m) },
    { label: '摊销期初', field: 'amortBegin', value: m.amortBegin },
    { label: '摊销增加', field: 'amortInc', value: m.amortInc },
    { label: '摊销减少', field: 'amortDec', value: m.amortDec },
    { label: '摊销期末', field: '', value: dataResourceAmortEnd(m) },
    { label: '减值期初', field: 'impairBegin', value: m.impairBegin },
    { label: '减值增加', field: 'impairInc', value: m.impairInc },
    { label: '减值减少', field: 'impairDec', value: m.impairDec },
    { label: '减值期末', field: '', value: dataResourceImpairEnd(m) },
    { label: '账面价值期末', field: '', value: dataResourceBookEnd(m) },
  ]
})

function fmt(n: number): string {
  const x = Number(n) || 0
  if (Math.abs(x) < 0.005) return '-'
  return x.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function isDefaultCat(key: string) {
  return I1_LISTED_DEFAULT_CATEGORIES.some((c) => c.key === key) || key === 'land' || key === 'patent' || key === 'knowhow' || key === 'data'
}
function cellOf(row: MovementRowDef, catKey: string) {
  return i1ListedCellValue(movement.value, row, catKey)
}
function totalOf(row: MovementRowDef) {
  return i1ListedTotalCellValue(movement.value, row, categories.value)
}
function movementRowClass({ row }: { row: MovementRowDef }) {
  if (row.kind === 'section') return 'row-section'
  if (row.kind === 'calc' || row.kind === 'book' || row.kind === 'subtotal') return 'row-calc'
  return ''
}

async function handleAddCat() {
  try {
    const { value } = await ElMessageBox.prompt('资产类别名称', '增加类别列', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：域名',
    })
    const name = (value || '').trim()
    if (!name) return
    const ok = addCategory(name)
    if (!ok) ElMessage.warning(`类别「${name}」已存在，未新增`)
  } catch (e) {
    // 与国企版同构：区分「用户取消」（reject 'cancel'/'close'）与实现异常，
    // 异常必须落控制台 + 用户可见提示，不得被裸 catch 吞掉（见 I1TabDisclosureSoe 注释）。
    if (e === 'cancel' || e === 'close') return
    console.error('[I1-listed] 新增资产类别列失败', e)
    ElMessage.error('新增资产类别列失败，请重试；若反复失败请联系管理员')
  }
}

function handlePull(overwriteNotes: boolean) {
  const res = pullFromSources({ overwriteNotes })
  ElMessage({ type: res.count ? 'success' : 'warning', message: res.message })
}

/**
 * 受限资产共享表（listed `五、32`）的「无形资产」段。
 *
 * 数据源 = I1-8 无形资产权属检查表（`I1-8-rows`，取 `mortgageRestricted='Y'` 的行、
 * 金额取「抵押价值」`mortgageValue`，与 `useI1TitleCheck.totalMortgage` 同口径）。
 * 该表**只有期末口径** → 只推主表、不推「（续：上年年末）」。
 *
 * 🔴 与本页「未办妥权属证书的土地使用权」是**两种不同披露**：权属证书未办妥 ≠
 * 所有权/使用权受到限制，故 `titleCertRows` 绝不进受限资产表。
 */
const syncRestrictedAssets = useRestrictedAssetsSync({
  owner: 'BS-032',
  variant: () => 'listed',
  wpId: () => props.wpId,
  projectId: () => props.projectId,
  responses: () => props.allResponses as unknown as Map<string, { remark?: string | null }>,
  applicableStandards: () => props.applicableStandards,
  sheetNames: I1_DISCLOSURE_SHEET_NAME,
  isReadonly: () => props.isReadonly,
})

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  if (prepValidation.value.blocking.length) {
    ElMessage.error(prepValidation.value.blocking[0])
    return
  }
  if (prepValidation.value.warnings.length) {
    try {
      await ElMessageBox.confirm(
        `存在 ${prepValidation.value.warnings.length} 项编制提示，是否仍同步到附注？\n` + prepValidation.value.warnings.slice(0, 3).join('\n'),
        '同步确认',
        { type: 'warning', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  persist()
  const payloads = buildI1ListedSyncPayloads(props.wpId, props.applicableStandards || [], {
    categories: categories.value,
    movement: movement.value,
    noteRdRatio: noteRdRatio.value,
    noteIndefinite: noteIndefinite.value,
    noteMortgage: noteMortgage.value,
    noteImpairment: noteImpairment.value,
    noteSale: noteSale.value,
    noteImportant: noteImportant.value,
    titleCertRows: titleCertRows.value,
    importantRows: importantRows.value,
    dataResource: dataResource.value,
    noteDataResource: noteDataResource.value,
    amortAlloc: amortAlloc.value,
  })
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    eventBus.emit('disclosure:note-text-updated' as any, {
      projectId: props.projectId,
      sectionIds: [noteSectionId],
      wpId: props.wpId,
      sheet: '附注披露信息（上市公司）',
    })
    ElMessage.success(`已同步至附注 ${noteSectionId}（${rows} 行）`)
    // 受限资产共享表的「无形资产」段（跨循环共享表，只替换本段、他段原样保留）
    await syncRestrictedAssets()
  } catch (e: any) {
    ElMessage.error(e?.message || '同步失败')
  } finally {
    isSyncing.value = false
  }
}

/**
 * 自动同步专用包装 —— **绝不弹模态确认框**。
 *
 * 🔴 修掉一处预存在缺陷：原实现在 `syncToNotes()` **内部**调
 * `autoSync.scheduleAutoSync(syncToNotes)` = 调度自己 → 点一次同步就进入
 * 800ms 周期的无限 POST（直到组件卸载 `cancelPending`）。平台守卫
 * `disclosureAutoSyncCoverage` 的自递归检测只认 `syncToDisclosureNotes` 这个函数名，
 * 故 I1 用 `syncToNotes` 命名逃过了那一轮清理。
 *
 * 现改为监听**实际数据**（与 `buildI1ListedSyncPayloads` 所用字段一致）；
 * 有阻断项/编制提示时自动路径直接跳过（提示只在手动点按钮时弹）。
 */
async function autoSyncToNotes(): Promise<void> {
  if (prepValidation.value.blocking.length || prepValidation.value.warnings.length) return
  await syncToNotes()
}

watch(
  [
    categories,
    movement,
    titleCertRows,
    importantRows,
    dataResource,
    amortAlloc,
    noteRdRatio,
    noteIndefinite,
    noteMortgage,
    noteImpairment,
    noteSale,
    noteImportant,
    noteDataResource,
    auditNote,
    auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(autoSyncToNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i1-disc-listed { padding: 12px 16px; font-size: 13px; }
.objective { margin-bottom: 10px; }
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-context p { margin: 0; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.block { margin-bottom: 16px; }
.block-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; }
.cat-bar { display: flex; align-items: center; gap: 8px; }
.hint { font-size: 12px; color: #64748b; }
.movement-wrap { overflow-x: auto; }
.movement-table :deep(.row-section) { background: #f1f5f9; font-weight: 600; }
.movement-table :deep(.row-calc) { background: #f0fdf4; }
.formula-cell { border-bottom: 1px dashed #94a3b8; cursor: help; }
.kind-section { font-weight: 700; }
.cat-header { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.notes-block .note-item { margin-bottom: 10px; }
.notes-block label { display: block; font-size: 12px; color: #475569; margin-bottom: 4px; }
.audit-card { margin-top: 12px; }
.cross-warning {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
  color: #854d0e;
  font-size: 12px;
}
.prep-box { margin-bottom: 10px; font-size: 12px; }
.prep-block { color: #b91c1c; margin-bottom: 2px; }
.prep-warn { color: #a16207; margin-bottom: 2px; }
.mt8 { margin-top: 8px; }
</style>
