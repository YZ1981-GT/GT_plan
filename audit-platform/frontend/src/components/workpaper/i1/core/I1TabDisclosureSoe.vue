<template>
  <div class="i1-disc-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按国企附注格式编制无形资产披露——原价/累计摊销/减值/账面价值分类变动，与 I1-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 Excel + 国企附注模板）：①四层合计+其中分类行 → ②期末=期初+增−减 →
        ③账面价值=原价−摊销−减值（增减列不适用）→ ④七项说明 → ⑤同步附注八、27。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（国有企业）</strong>
        <el-tag size="small" type="success" effect="plain">八、27 无形资产</el-tag>
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
          data-testid="i1-disclosure-soe-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注（八、27）</el-button>
        <el-button size="small" type="primary" plain @click="emit('open-ai', 'disclosure-soe')">AI 辅助</el-button>
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

    <div v-if="!isReadonly" class="cat-bar">
      <el-button size="small" @click="handleAddSoeCat">+ 增加资产类别</el-button>
      <span class="hint">源模板四层末「……」可扩位：按被审计单位实际类别扩展（四层同步新增）</span>
    </div>

    <section v-for="block in layers" :key="block.layer" class="block">
      <h3 class="block-title">{{ layerTitle(block.layer) }}</h3>
      <el-table :data="blockRows(block)" border size="small" class="wp-table" :row-class-name="rowClass">
        <el-table-column prop="label" label="项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.label }}</span>
            <el-button
              v-if="row.removable && !isReadonly"
              link
              type="danger"
              size="small"
              class="cat-del"
              @click="handleRemoveSoeCat(row.key)"
            >删</el-button>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.kind === 'detail' && !isReadonly && block.layer !== 'carrying'"
              :model-value="row.begin"
              :disabled="isReadonly || block.layer === 'carrying'"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCategory(block.layer, row.key, 'begin', v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="layerMeta(block.layer).movementNa">—</template>
            <WpAmountInput
              v-else-if="row.kind === 'detail' && !isReadonly"
              :model-value="row.increase"
              :disabled="isReadonly"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCategory(block.layer, row.key, 'increase', v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="layerMeta(block.layer).movementNa">—</template>
            <WpAmountInput
              v-else-if="row.kind === 'detail' && !isReadonly"
              :model-value="row.decrease"
              :disabled="isReadonly"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCategory(block.layer, row.key, 'decrease', v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.end) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="block notes-block">
      <h3 class="block-title">说明（同步至附注）</h3>
      <div v-for="item in noteFields" :key="item.key" class="note-item">
        <label>{{ item.label }}</label>
        <el-input
          v-model="item.model.value"
          type="textarea"
          :rows="2"
          :disabled="isReadonly"
          :placeholder="item.placeholder"
          @change="persist"
        />
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
import { ref, toRef, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI1SoeDisclosure } from '../../composables/useI1Disclosure'
import {
  I1_SOE_GUIDANCE,
  I1_SOE_LAYER_META,
  layerTotal,
  resolveCategoryEnd,
  resolveI1SoeCategories,
  type I1SoeLayer,
  type I1SoeLayerBlock,
} from '../../composables/i1SoeDisclosureModel'
import { buildI1SoeSyncPayloads } from '../../composables/i1DisclosureSyncPayload'
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

const noteSectionId = I1_NOTE_SECTION.soe
const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'I1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const {
  layers,
  noteIndefinite,
  noteMortgage,
  noteValuation,
  noteImpairment,
  noteNotReady,
  noteSale,
  noteTitle,
  amortAlloc,
  auditNote,
  auditConclusion,
  crossCheck,
  prepValidation,
  persist,
  updateCategory,
  addCategory,
  removeCategory,
  pullFromSources,
} = useI1SoeDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => emit('save', id, v),
})

/** 增加自定义资产类别（四层同时新增；先弹 prompt 输名，撞名拒绝）。 */
async function handleAddSoeCat() {
  try {
    const { value } = await ElMessageBox.prompt('资产类别名称', '增加资产类别', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：碳排放权',
    })
    const name = (value || '').trim()
    if (!name) return
    const ok = addCategory(name)
    if (!ok) ElMessage.warning(`类别「${name}」已存在，未新增`)
  } catch (e) {
    // 🔴 曾写成裸 `catch { /* cancelled */ }`，把 `addCategory` 内部抛的
    //    `TypeError: layers is not iterable` 一起吞了 ⇒ 点确认后**无提示、无新行、
    //    无库写入、控制台无 error**，缺陷完全不可见（浏览器实测才暴露）。
    //    ElMessageBox 取消/关闭 reject 的是字符串 'cancel'/'close'，
    //    据此把「用户取消」与「实现异常」分开，异常必须落到控制台 + 用户可见提示。
    if (e === 'cancel' || e === 'close') return
    console.error('[I1-soe] 新增资产类别失败', e)
    ElMessage.error('新增资产类别失败，请重试；若反复失败请联系管理员')
  }
}

const noteFields = [
  { key: 'indefinite', label: '1、寿命不确定', model: noteIndefinite, placeholder: I1_SOE_GUIDANCE.indefinite },
  { key: 'mortgage', label: '2、抵押担保', model: noteMortgage, placeholder: I1_SOE_GUIDANCE.mortgage },
  { key: 'valuation', label: '3、重大评估入账', model: noteValuation, placeholder: I1_SOE_GUIDANCE.valuation },
  { key: 'impairment', label: '4、减值原因', model: noteImpairment, placeholder: I1_SOE_GUIDANCE.impairment },
  { key: 'notReady', label: '5、未达可使用状态减值测试', model: noteNotReady, placeholder: I1_SOE_GUIDANCE.notReady },
  { key: 'sale', label: '6、高价出售', model: noteSale, placeholder: I1_SOE_GUIDANCE.sale },
  { key: 'title', label: '7、未办妥权属', model: noteTitle, placeholder: I1_SOE_GUIDANCE.title },
]

function layerTitle(layer: I1SoeLayer) {
  return I1_SOE_LAYER_META[layer].title
}
function layerMeta(layer: I1SoeLayer) {
  return I1_SOE_LAYER_META[layer]
}

function blockRows(block: I1SoeLayerBlock) {
  const meta = I1_SOE_LAYER_META[block.layer]
  const tot = layerTotal(block)
  const rows: Array<{
    kind: 'total' | 'detail'
    key: string
    label: string
    begin: number
    increase: number
    decrease: number
    end: number
  }> = [{
    kind: 'total',
    key: '_total',
    label: meta.title,
    begin: tot.begin,
    increase: tot.increase,
    decrease: tot.decrease,
    end: tot.end,
  }]
  for (const cat of resolveI1SoeCategories(layers.value)) {
    const m = block.categories.find((c) => c.key === cat.key)
    rows.push({
      kind: 'detail',
      key: cat.key,
      label: cat.label,
      removable: cat.removable && _SOE_CUSTOM_RE.test(cat.key),
      begin: m?.begin ?? 0,
      increase: m?.increase ?? 0,
      decrease: m?.decrease ?? 0,
      end: m ? resolveCategoryEnd(m, meta.movementNa) : 0,
    })
  }
  return rows
}

const _SOE_CUSTOM_RE = /^soe_custom_\d+$/

function rowClass({ row }: { row: { kind: string } }) {
  return row.kind === 'total' ? 'row-total' : ''
}

function handleRemoveSoeCat(key: string) {
  if (!removeCategory(key)) ElMessage.warning('默认类别不可删除')
}

function fmt(n: number): string {
  const x = Number(n) || 0
  if (Math.abs(x) < 0.005) return '-'
  return x.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handlePull(overwriteNotes: boolean) {
  const res = pullFromSources({ overwriteNotes })
  ElMessage({ type: res.count ? 'success' : 'warning', message: res.message })
}

/**
 * 受限资产共享表（soe `八、93`）的「无形资产」段。
 *
 * 数据源 = I1-8 无形资产权属检查表（`I1-8-rows`，取 `mortgageRestricted='Y'` 的行、
 * 金额取「抵押价值」`mortgageValue`，与 `useI1TitleCheck.totalMortgage` 同口径）。
 * 该表**只有期末口径** → soe 单表本就只有期末账面价值列，天然对齐。
 */
const syncRestrictedAssets = useRestrictedAssetsSync({
  owner: 'BS-032',
  variant: () => 'soe',
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
        `存在 ${prepValidation.value.warnings.length} 项编制提示，是否仍同步？`,
        '同步确认',
        { type: 'warning', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  persist()
  const payloads = buildI1SoeSyncPayloads(props.wpId, props.applicableStandards || [], {
    layers: layers.value,
    noteIndefinite: noteIndefinite.value,
    noteMortgage: noteMortgage.value,
    noteValuation: noteValuation.value,
    noteImpairment: noteImpairment.value,
    noteNotReady: noteNotReady.value,
    noteSale: noteSale.value,
    noteTitle: noteTitle.value,
    amortAlloc: amortAlloc.value,
  })
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
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
      sheet: '附注披露信息（国有企业）',
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
 * 现改为监听**实际数据**（与 `buildI1SoeSyncPayloads` 所用字段一致）；
 * 有阻断项/编制提示时自动路径直接跳过（提示只在手动点按钮时弹）。
 */
async function autoSyncToNotes(): Promise<void> {
  if (prepValidation.value.blocking.length || prepValidation.value.warnings.length) return
  await syncToNotes()
}

watch(
  [
    layers,
    amortAlloc,
    noteIndefinite,
    noteMortgage,
    noteValuation,
    noteImpairment,
    noteNotReady,
    noteSale,
    noteTitle,
    auditNote,
    auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(autoSyncToNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i1-disc-soe { padding: 12px 16px; font-size: 13px; }
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
.block-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
.wp-table :deep(.row-total) { background: #f0fdf4; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #94a3b8; }
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
</style>
