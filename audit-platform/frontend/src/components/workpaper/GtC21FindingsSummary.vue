<script setup lang="ts">
/**
 * GtC21FindingsSummary — C21-1 IT 审计发现汇总表（交互式，替代 OnlyOffice 占位）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 5.1 + 8.3
 * Requirements: 5.1, 5.2, 5.3, 5.4, 12.1, 12.2, 12.3, 12.4
 *
 * 职责：
 *  - 汇总 useC22BundleState.defects（各子页「是否异常=是」的缺陷）为汇总视图（Req 5.1 / 12.1）。
 *    父组件在子页缺陷评估变更时刷新 defects（reactive）→ 本视图自动更新（Req 5.2 / 12.4）。
 *  - 每条缺陷行展示：缺陷编号 / 所属控制点 / 缺陷描述（问题描述），并允许补充
 *    影响分析（风险及影响）+ 整改建议 + 财务报表认定（9 认定）+ 补偿性控制 /
 *    相关报表项目 / 对审计工作的影响 / 备注（Req 5.3）。补充持久化于 C22 父底稿
 *    checklist_responses，item_id = `C22.C21-1.{controlId}.{field}`（见 c21SummaryItemId）。
 *  - 每条缺陷行提供 GtIndexChip（prop `value`）跳回来源控制点子页（双向追溯，Req 5.4 / 12.3）。
 *  - 每条缺陷行提供 GtIndexChip 跳转 A14 缺陷评价底稿并带入摘要（Req 12.2）：
 *    controlId + defectNo + description 作为跳转上下文。
 *  - 缺陷回写保留来源控制点编号与子页索引（Req 12.3：双向追溯）。
 *  - 保留 Phase0 §5 第二张表「上年度/上次审计发现整改情况」（动态行，持久化）。
 *
 * 只读模式（Req 9）：全部补充字段与整改表禁止编辑，仅可浏览与跳转。
 * 🔴 铁律：GtIndexChip prop `value`；字体 13px；补充区/整改表 el-card 包裹；http(axios) 保存。
 */
import { ref, reactive, computed, watch, onMounted, onScopeDispose, defineAsyncComponent } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  c21SummaryItemId,
  C21_CARRYOVER_ITEM_ID,
  FS_ASSERTIONS,
  type ItgcDefect,
  type C21SummaryField,
  type ChecklistResponse,
} from './composables/useC22BundleState'

const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

const props = defineProps<{
  /** C22 父底稿 wp_id（补充字段持久化于此工作簿的 checklist_responses） */
  wpId: string
  projectId?: string
  /** 汇总缺陷（来自 useC22BundleState.defects，父组件传入并保持 reactive） */
  defects: ItgcDefect[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'updated'): void
}>()

const isReadonly = computed(() => props.readonly === true)

// ─── 缺陷补充字段本地状态（controlId → 字段集合） ───
interface DefectSupplement {
  impact: string
  remediation: string
  assertions: string[]
  compensating: string
  reportItem: string
  auditEffect: string
  note: string
}

function emptySupplement(): DefectSupplement {
  return {
    impact: '',
    remediation: '',
    assertions: [],
    compensating: '',
    reportItem: '',
    auditEffect: '',
    note: '',
  }
}

/** controlId → 补充字段 */
const supplements = reactive<Record<string, DefectSupplement>>({})

/** 上年度整改表行 */
interface CarryoverRow {
  defectNo: string
  category: string
  controlType: string
  appSystem: string
  finding: string
  riskImpact: string
  remediation: string
  clientReply: string
}
const carryoverRows = ref<CarryoverRow[]>([])

const loading = ref(false)

/** 确保某控制点的补充槽存在 */
function ensureSlot(controlId: string): DefectSupplement {
  if (!supplements[controlId]) supplements[controlId] = emptySupplement()
  return supplements[controlId]
}

// ─── 加载补充字段（仅 C22.C21-1. 前缀） ───
async function loadSupplements(): Promise<void> {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { params: { project_id: props.projectId }, _silent: true } as any,
    )
    const list: ChecklistResponse[] = Array.isArray(res) ? res : ((res as any)?.data ?? [])
    const byId = new Map<string, ChecklistResponse>()
    for (const r of list) {
      if (r?.item_id && r.item_id.startsWith('C22.C21-1.')) byId.set(r.item_id, r)
    }
    // 逐控制点回填
    for (const d of props.defects) {
      const slot = ensureSlot(d.controlId)
      const read = (field: C21SummaryField): string =>
        byId.get(c21SummaryItemId(d.controlId, field))?.remark ?? ''
      slot.impact = read('impact')
      slot.remediation = read('remediation')
      slot.compensating = read('compensating')
      slot.reportItem = read('report-item')
      slot.auditEffect = read('audit-effect')
      slot.note = read('note')
      slot.assertions = parseAssertions(read('assertions'))
    }
    // 上年度整改表
    const co = byId.get(C21_CARRYOVER_ITEM_ID)?.remark ?? ''
    carryoverRows.value = parseCarryover(co)
  } catch {
    // 加载失败保持空表，不阻塞
  } finally {
    loading.value = false
  }
}

function parseAssertions(raw: string): string[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr.filter((x) => FS_ASSERTIONS.includes(x)) : []
  } catch {
    return []
  }
}

function parseCarryover(raw: string): CarryoverRow[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any) => ({
      defectNo: String(r?.defectNo ?? ''),
      category: String(r?.category ?? ''),
      controlType: String(r?.controlType ?? ''),
      appSystem: String(r?.appSystem ?? ''),
      finding: String(r?.finding ?? ''),
      riskImpact: String(r?.riskImpact ?? ''),
      remediation: String(r?.remediation ?? ''),
      clientReply: String(r?.clientReply ?? ''),
    }))
  } catch {
    return []
  }
}

// ─── 保存（PUT checklist-responses） ───
async function putItem(itemId: string, value: string): Promise<void> {
  if (!props.wpId || isReadonly.value) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: itemId, conclusion: null, remark: value || null }],
    })
    emit('updated')
  } catch {
    // 静默：保存失败保留本地值
  }
}

// debounce 文本字段（2s），即时保存枚举/多选
const _timers = new Map<string, ReturnType<typeof setTimeout>>()

function saveFieldDebounced(controlId: string, field: C21SummaryField): void {
  if (isReadonly.value) return
  const itemId = c21SummaryItemId(controlId, field)
  const slot = ensureSlot(controlId)
  const value = fieldValue(slot, field)
  const prev = _timers.get(itemId)
  if (prev) clearTimeout(prev)
  _timers.set(itemId, setTimeout(() => {
    _timers.delete(itemId)
    void putItem(itemId, value)
  }, 2000))
}

function saveFieldNow(controlId: string, field: C21SummaryField): void {
  if (isReadonly.value) return
  const itemId = c21SummaryItemId(controlId, field)
  const prev = _timers.get(itemId)
  if (prev) { clearTimeout(prev); _timers.delete(itemId) }
  void putItem(itemId, fieldValue(ensureSlot(controlId), field))
}

function fieldValue(slot: DefectSupplement, field: C21SummaryField): string {
  switch (field) {
    case 'impact': return slot.impact
    case 'remediation': return slot.remediation
    case 'assertions': return JSON.stringify(slot.assertions)
    case 'compensating': return slot.compensating
    case 'report-item': return slot.reportItem
    case 'audit-effect': return slot.auditEffect
    case 'note': return slot.note
  }
}

function onAssertionsChange(controlId: string): void {
  saveFieldNow(controlId, 'assertions')
}

function flushPending(): void {
  for (const [itemId, t] of _timers) {
    clearTimeout(t)
    // best-effort flush
    const m = itemId.match(/^C22\.C21-1\.(.+)\.(impact|remediation|assertions|compensating|report-item|audit-effect|note)$/)
    if (m) {
      const controlId = m[1]
      const field = m[2] as C21SummaryField
      const slot = supplements[controlId]
      if (slot) void putItem(itemId, fieldValue(slot, field))
    }
  }
  _timers.clear()
}

// ─── 上年度整改表增删改（即时持久化 JSON） ───
function persistCarryover(): void {
  if (isReadonly.value) return
  void putItem(C21_CARRYOVER_ITEM_ID, JSON.stringify(carryoverRows.value))
}

function addCarryoverRow(): void {
  if (isReadonly.value) return
  carryoverRows.value.push({
    defectNo: '', category: '', controlType: '', appSystem: '',
    finding: '', riskImpact: '', remediation: '', clientReply: '',
  })
  persistCarryover()
}

function removeCarryoverRow(idx: number): void {
  if (isReadonly.value) return
  carryoverRows.value.splice(idx, 1)
  persistCarryover()
}

// ─── 展示：缺陷行（合并 defect + supplement） ───
const findingRows = computed(() =>
  props.defects.map((d, i) => ({
    index: i + 1,
    defect: d,
    slot: ensureSlot(d.controlId),
    /** 跳回来源控制点子页（bundle 内 ?sheet= 路由，Req 5.4 双向追溯） */
    sourceRef: `sheet:${d.controlId}`,
    /** 跳转 A14 缺陷评价底稿并带入摘要（Req 12.2：controlId + defectNo + description） */
    a14Ref: `A14`,
  })),
)

/**
 * A14 缺陷评价跳转 + 带入缺陷摘要（Req 12.2）。
 * GtIndexChip 自身完成路由跳转到 A14；本处补发结构化缺陷上下文 payload，
 * 供 A14 缺陷评价底稿预填缺陷摘要。
 */
function onDefectJumpToA14(defect: ItgcDefect): void {
  eventBus.emit('c22:defect-to-a14', {
    projectId: props.projectId,
    wpId: props.wpId,
    controlId: defect.controlId,
    defectNo: defect.defectNo,
    description: defect.description,
    group: defect.group,
    sheet: defect.sheet,
    appSystem: defect.appSystem,
  })
}

/** 类别（Phase0 §5：ITGC 一律「IT一般控制」；控制类型细分 = group） */
function categoryLabel(): string {
  return 'IT一般控制'
}

// ─── Lifecycle ───
onMounted(loadSupplements)
// defects 变更（如新增控制点缺陷）时，为新控制点补齐补充槽并重载已存补充
watch(
  () => props.defects.map((d) => d.controlId).join('|'),
  () => { void loadSupplements() },
)
onScopeDispose(flushPending)

defineExpose({
  supplements,
  carryoverRows,
  findingRows,
  loadSupplements,
  saveFieldNow,
  saveFieldDebounced,
  onAssertionsChange,
  onDefectJumpToA14,
  addCarryoverRow,
  removeCarryoverRow,
})
</script>

<template>
  <div class="c21-findings" v-loading="loading">
    <!-- 方法论上下文（琥珀块） -->
    <div class="c21f-guide">
      <span class="c21f-guide-icon">📋</span>
      <span class="c21f-guide-text">
        <strong>C21-1 IT 审计发现汇总表</strong>：自动汇总各 IT 控制域子页「是否发现异常 = 是」的缺陷。
        请补充<strong>影响分析</strong>（风险及影响）、<strong>整改建议</strong>与<strong>财务报表认定</strong>。
        点击每条缺陷的<strong>来源控制点</strong>标签可跳回来源子页核对；
        点击<strong>缺陷评价</strong>标签可跳转 A14 缺陷评价底稿并带入缺陷摘要。
      </span>
    </div>

    <!-- ═══ 本年度 IT 审计发现（汇总缺陷） ═══ -->
    <el-card class="c21f-card" shadow="never">
      <template #header>
        <div class="c21f-card-head">
          <span class="c21f-card-title">一、本年度 IT 审计发现（{{ findingRows.length }} 项）</span>
        </div>
      </template>

      <div v-if="findingRows.length === 0" class="c21f-empty">
        暂无 IT 审计发现（各控制域子页均未发现异常）。
      </div>

      <div
        v-for="row in findingRows"
        :key="row.defect.controlId"
        class="c21f-finding"
      >
        <!-- 缺陷头：缺陷编号 + 所属控制点（chip 跳回子页）+ A14跳转 + 类别 -->
        <div class="c21f-finding-head">
          <span class="c21f-defect-no">{{ row.defect.defectNo || '（未编号）' }}</span>
          <span class="c21f-sep">·</span>
          <span class="c21f-label-inline">来源控制点</span>
          <GtIndexChip :value="row.sourceRef" :validate="false" />
          <span class="c21f-sep">·</span>
          <span class="c21f-label-inline">缺陷评价</span>
          <GtIndexChip
            :value="row.a14Ref"
            :validate="true"
            :context-project-id="projectId"
            @click="onDefectJumpToA14(row.defect)"
          />
          <el-tag size="small" effect="plain" type="info">{{ row.defect.group }}</el-tag>
          <el-tag size="small" effect="plain">{{ categoryLabel() }}</el-tag>
          <span v-if="row.defect.appSystem" class="c21f-app">应用系统：{{ row.defect.appSystem }}</span>
        </div>
        <!-- 来源追溯信息（Req 12.3：保留来源控制点编号与子页索引） -->
        <div class="c21f-traceability">
          <span class="c21f-trace-label">追溯：</span>
          <span class="c21f-trace-info">控制点 {{ row.defect.controlId }} · Sheet {{ row.defect.sheet }} · {{ row.defect.group }}</span>
        </div>

        <!-- 问题描述（来源子页缺陷描述，只读回显） -->
        <div class="c21f-field">
          <label class="c21f-field-label">问题描述</label>
          <div class="c21f-desc-text">{{ row.defect.description || '—' }}</div>
        </div>

        <!-- 补充：影响分析（风险及影响） -->
        <div class="c21f-field">
          <label class="c21f-field-label">影响分析（风险及影响）</label>
          <el-input
            v-model="row.slot.impact"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="分析该 IT 控制缺陷可能导致的风险及对财务报表的影响"
            @input="saveFieldDebounced(row.defect.controlId, 'impact')"
          />
        </div>

        <!-- 补充：整改建议 -->
        <div class="c21f-field">
          <label class="c21f-field-label">整改建议</label>
          <el-input
            v-model="row.slot.remediation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="针对该缺陷提出的整改建议"
            @input="saveFieldDebounced(row.defect.controlId, 'remediation')"
          />
        </div>

        <!-- 补充：财务报表认定（9 认定，多选点选） -->
        <div class="c21f-field">
          <label class="c21f-field-label">财务报表认定</label>
          <el-checkbox-group
            v-model="row.slot.assertions"
            :disabled="isReadonly"
            class="c21f-assertions"
            @change="onAssertionsChange(row.defect.controlId)"
          >
            <el-checkbox
              v-for="a in FS_ASSERTIONS"
              :key="a"
              :label="a"
              :value="a"
              border
              size="small"
            >{{ a }}</el-checkbox>
          </el-checkbox-group>
        </div>

        <!-- 补充：补偿性控制 / 相关报表项目 / 对审计工作的影响 / 备注 -->
        <div class="c21f-grid">
          <div class="c21f-field">
            <label class="c21f-field-label">补偿性控制及有效性</label>
            <el-input
              v-model="row.slot.compensating"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              :readonly="isReadonly"
              placeholder="是否存在补偿性控制及其有效性"
              @input="saveFieldDebounced(row.defect.controlId, 'compensating')"
            />
          </div>
          <div class="c21f-field">
            <label class="c21f-field-label">相关报表项目</label>
            <el-input
              v-model="row.slot.reportItem"
              size="small"
              :readonly="isReadonly"
              placeholder="如：营业收入、应收账款"
              @input="saveFieldDebounced(row.defect.controlId, 'report-item')"
            />
          </div>
          <div class="c21f-field">
            <label class="c21f-field-label">对审计工作的影响</label>
            <el-input
              v-model="row.slot.auditEffect"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              :readonly="isReadonly"
              placeholder="对相关财务报表审计工作的影响（如扩大实质性程序）"
              @input="saveFieldDebounced(row.defect.controlId, 'audit-effect')"
            />
          </div>
          <div class="c21f-field">
            <label class="c21f-field-label">备注</label>
            <el-input
              v-model="row.slot.note"
              size="small"
              :readonly="isReadonly"
              placeholder="备注"
              @input="saveFieldDebounced(row.defect.controlId, 'note')"
            />
          </div>
        </div>
      </div>
    </el-card>

    <!-- ═══ 上年度/上次审计发现整改情况（Phase0 §5 第二张表） ═══ -->
    <el-card class="c21f-card" shadow="never">
      <template #header>
        <div class="c21f-card-head">
          <span class="c21f-card-title">二、上年度/上次审计发现整改情况</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="addCarryoverRow"
          >+ 新增整改记录</el-button>
        </div>
      </template>

      <el-table :data="carryoverRows" size="small" border class="c21f-carryover-table">
        <el-table-column label="缺陷编号" width="110">
          <template #default="{ row }">
            <el-input v-model="row.defectNo" size="small" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="类别" width="120">
          <template #default="{ row }">
            <el-input v-model="row.category" size="small" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="控制类型" width="120">
          <template #default="{ row }">
            <el-input v-model="row.controlType" size="small" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="涉及应用程序" width="130">
          <template #default="{ row }">
            <el-input v-model="row.appSystem" size="small" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="审计发现" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.finding" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="可能存在的风险及影响" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.riskImpact" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="整改情况" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.remediation" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column label="客户回复" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.clientReply" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :readonly="isReadonly" @input="persistCarryover" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="72" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeCarryoverRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="carryoverRows.length === 0" class="c21f-empty">暂无上年度整改记录。</div>
    </el-card>
  </div>
</template>

<style scoped>
.c21-findings {
  font-size: 13px;
  padding: 4px 2px 24px;
}

/* 方法论琥珀块 */
.c21f-guide {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  color: #7d5b1e;
  line-height: 1.5;
}
.c21f-guide-icon { font-size: 15px; }

.c21f-card {
  margin-bottom: 12px;
}
.c21f-card :deep(.el-card__header) {
  padding: 8px 12px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
}
.c21f-card :deep(.el-card__body) {
  padding: 12px;
}
.c21f-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.c21f-card-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-text, #303133);
}

.c21f-empty {
  text-align: center;
  padding: 24px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* 单条缺陷 */
.c21f-finding {
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 6px;
  background: var(--gt-color-bg-page, #fafafa);
}
.c21f-finding:last-child { margin-bottom: 0; }
.c21f-finding-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--gt-color-border, #dcdfe6);
}
.c21f-defect-no {
  font-family: var(--gt-font-mono, monospace);
  font-weight: 700;
  color: #f56c6c;
}
.c21f-sep { color: var(--gt-color-text-placeholder, #c0c4cc); }
.c21f-label-inline {
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 600;
}
.c21f-app {
  color: var(--gt-color-text-secondary, #606266);
  font-size: 12px;
}

/* 来源追溯信息（Req 12.3） */
.c21f-traceability {
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border-radius: 3px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.c21f-trace-label {
  font-weight: 600;
  color: var(--gt-color-text-secondary, #606266);
}
.c21f-trace-info {
  font-family: var(--gt-font-mono, monospace);
}

.c21f-field {
  margin-bottom: 10px;
}
.c21f-field:last-child { margin-bottom: 0; }
.c21f-field-label {
  display: block;
  margin-bottom: 4px;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 600;
}
.c21f-desc-text {
  padding: 6px 8px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border-radius: 4px;
  line-height: 1.5;
  color: var(--gt-color-text, #303133);
}
.c21f-assertions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 补充字段 2 列网格 */
.c21f-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.c21f-carryover-table {
  font-size: 13px;
}
</style>
