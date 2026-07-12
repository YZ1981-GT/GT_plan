<template>
  <div class="h7-tab-policy-check">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：检查生产性生物资产会计政策的适当性与一贯性，确认分类、初始计量、后续计量（成本/公允价值）、折旧、减值及披露符合 CAS 5《生物资产》。
      </template>
    </el-alert>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-4 会计政策检查（CAS 5）— 当前计量模式：
            <el-tag size="small" :type="measurementModel === 'fair_value' ? 'warning' : 'success'">
              {{ measurementModel === 'fair_value' ? '公允价值模式' : '成本模式' }}
            </el-tag>
            <GtIndexChip value="wp:H7-1" />
            <el-tag size="small" type="info" class="row-tag">共 {{ items.length }} 项</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-4')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>合规 {{ complianceStat.符合 }} 项</span>
        <span :class="{ 'text-warn': complianceStat.不符合 > 0 }">不符合 {{ complianceStat.不符合 }} 项</span>
        <span>不适用 {{ complianceStat.不适用 }} 项</span>
        <span>未评估 {{ complianceStat.未评估 }} 项</span>
      </div>

      <el-table :data="items" border stripe size="small" class="check-table">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column prop="topic" label="检查要点" min-width="200">
          <template #default="{ row }"><span :class="{ 'na-row': !applicable(row) }">{{ row.topic }}</span></template>
        </el-table-column>
        <el-table-column prop="basis" label="准则依据" width="140" />
        <el-table-column prop="policy" label="企业实际会计政策" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && applicable(row)" v-model="row.policy" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" size="small" @change="persistItems" />
            <span v-else>{{ applicable(row) ? row.policy : '（当前计量模式不适用）' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="检查结论" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && applicable(row)" v-model="row.result" size="small" style="width:96px" @change="persistItems">
              <el-option v-for="r in RESULT_OPTIONS" :key="r" :label="r" :value="r" />
            </el-select>
            <el-tag v-else :type="resultTag(row.result)" size="small">{{ applicable(row) ? (row.result || '未评估') : '不适用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && applicable(row)" v-model="row.remark" size="small" @change="persistItems" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录会计政策适当性与一贯性的整体评价" @blur="persist('H7-4-conclusion', conclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS 5 将生物资产分为消耗性、生产性、公益性三类，生产性生物资产核算科目为 1621。</li>
        <li>成本模式下计提折旧（直线法等）并进行减值测试（减值一经确认，成熟生产性生物资产不得转回）。</li>
        <li>公允价值模式仅在有活跃市场且能可靠取得公允价值时采用，不计提折旧和减值，公允价值变动计入当期损益。</li>
        <li>会计政策变更应符合 CAS 28，并在附注中充分披露。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7PolicyCheck } from '../../composables/useH7PolicyCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; measurementModel?: 'cost' | 'fair_value'; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const check = useH7PolicyCheck(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const measurementModel = computed(() => props.measurementModel ?? 'cost')
const RESULT_OPTIONS = ['符合', '不符合', '不适用']

/** mode: 'both' | 'cost' | 'fair' — 政策要点适用的计量模式 */
interface PolicyItem { key: string; topic: string; basis: string; mode: 'both' | 'cost' | 'fair'; policy: string; result: string; remark: string }

const DEFAULT_ITEMS: Omit<PolicyItem, 'policy' | 'result' | 'remark'>[] = [
  { key: 'classify', topic: '生物资产分类是否恰当（消耗性/生产性/公益性）', basis: 'CAS 5 §3', mode: 'both' },
  { key: 'initial', topic: '初始计量是否按成本（外购/自行栽培繁殖）确认', basis: 'CAS 5 §9-13', mode: 'both' },
  { key: 'subsequent-cost', topic: '成本模式后续计量是否按成本减累计折旧减减值', basis: 'CAS 5 §17', mode: 'cost' },
  { key: 'depreciation', topic: '折旧方法（直线法等）、年限、残值率是否合理一贯', basis: 'CAS 5 §18', mode: 'cost' },
  { key: 'impairment', topic: '成本模式下减值迹象判断与减值测试是否恰当', basis: 'CAS 5 §21 / CAS 8', mode: 'cost' },
  { key: 'fair-precondition', topic: '公允价值模式采用前提（活跃市场+可靠计量）是否满足', basis: 'CAS 5 §22', mode: 'fair' },
  { key: 'fair-change', topic: '公允价值变动是否计入当期损益且披露充分', basis: 'CAS 5 §23', mode: 'fair' },
  { key: 'transfer', topic: '生物资产互转的会计处理是否正确（账面价值结转）', basis: 'CAS 5 §14', mode: 'both' },
  { key: 'disclosure', topic: '生物资产相关披露是否完整（分类、计量模式、增减变动）', basis: 'CAS 30 / CAS 5 §26', mode: 'both' },
]

const items = ref<PolicyItem[]>([])
const conclusion = ref('')

function applicable(row: PolicyItem): boolean {
  if (row.mode === 'both') return true
  return (row.mode === 'cost' && measurementModel.value === 'cost') || (row.mode === 'fair' && measurementModel.value === 'fair_value')
}

const complianceStat = computed(() => {
  const stat = { 符合: 0, 不符合: 0, 不适用: 0, 未评估: 0 }
  for (const it of items.value) {
    if (!applicable(it)) { stat.不适用++; continue }
    if (it.result === '符合') stat.符合++
    else if (it.result === '不符合') stat.不符合++
    else if (it.result === '不适用') stat.不适用++
    else stat.未评估++
  }
  return stat
})

function seed(): void {
  const raw = check.getString('H7-4-items')
  let saved: Record<string, Partial<PolicyItem>> = {}
  if (raw) { try { const p = JSON.parse(raw); if (p && typeof p === 'object') saved = p } catch { /* ignore */ } }
  items.value = DEFAULT_ITEMS.map((d) => ({
    ...d,
    policy: saved[d.key]?.policy ?? '',
    result: saved[d.key]?.result ?? '',
    remark: saved[d.key]?.remark ?? '',
  }))
  conclusion.value = check.getString('H7-4-conclusion')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistItems(): void {
  const payload: Record<string, Partial<PolicyItem>> = {}
  for (const it of items.value) payload[it.key] = { policy: it.policy, result: it.result, remark: it.remark }
  persist('H7-4-items', payload)
}

function resultTag(r: string): 'success' | 'danger' | 'info' {
  if (r === '符合') return 'success'
  if (r === '不符合') return 'danger'
  return 'info'
}
async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `会计政策检查：计量模式=${measurementModel.value === 'fair_value' ? '公允价值' : '成本'}，合规${complianceStat.value.符合}项，不符合${complianceStat.value.不符合}项。`
  const text = await generateAiText('h7-policy', ctx, conclusion.value)
  if (text) { conclusion.value = text; persist('H7-4-conclusion', conclusion.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
</script>

<style scoped>
.h7-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-warn { color: var(--el-color-warning); }
.check-table { font-size: var(--wp-font-size, 13px); }
.na-row { color: var(--el-text-color-secondary); }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
