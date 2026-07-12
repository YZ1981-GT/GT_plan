<template>
  <div class="h7-tab-stocktake-summary">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：汇总生产性生物资产监盘结果，评价盘盈盘亏对资产余额真实性与减值的影响，形成监盘结论（CAS 5 / CAS 1311 参照适用）。
      </template>
    </el-alert>

    <el-card shadow="never" class="dashboard-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-10 监盘小结
            <GtIndexChip value="wp:H7-9" />
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI总结</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-10')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :span="6"><div class="stat-box"><div class="stat-label">盘点总数</div><div class="stat-value">{{ stat.total }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box success"><div class="stat-label">账实相符</div><div class="stat-value">{{ stat.match }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box warning"><div class="stat-label">盘盈</div><div class="stat-value">{{ stat.surplus }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box danger"><div class="stat-label">盘亏</div><div class="stat-value">{{ stat.deficit }}</div></div></el-col>
      </el-row>
      <div class="match-rate-bar">
        <span>账实相符率：</span>
        <el-progress :percentage="Math.round(stat.matchRate)" :stroke-width="14" :format="() => stat.matchRate.toFixed(1) + '%'" style="flex:1" />
      </div>
    </el-card>

    <el-card shadow="never" v-if="surplusRows.length" class="detail-card">
      <template #header><span>盘盈明细（{{ surplusRows.length }} 项）</span></template>
      <el-table :data="surplusRows" border stripe size="small">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column prop="name" label="生物资产名称" min-width="130" />
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column label="数量差异" width="110" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtNum(qtyDiff(row)) }}</span></template></el-table-column>
        <el-table-column prop="diffReason" label="原因/处理建议" min-width="180" />
      </el-table>
    </el-card>

    <el-card shadow="never" v-if="deficitRows.length" class="detail-card">
      <template #header><span>盘亏明细（{{ deficitRows.length }} 项）</span></template>
      <el-table :data="deficitRows" border stripe size="small">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column prop="name" label="生物资产名称" min-width="130" />
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column label="数量差异" width="110" align="right"><template #default="{ row }"><span class="amount-cell text-danger">{{ fmtNum(qtyDiff(row)) }}</span></template></el-table-column>
        <el-table-column prop="diffReason" label="原因/处理建议" min-width="180" />
      </el-table>
    </el-card>

    <el-empty v-if="!totalRows" description="尚无 H7-9 盘点检查数据，请先在盘点检查表录入" :image-size="90" />

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>监盘总结与审计结论</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI总结</el-button>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="总结盘点结果、盘盈盘亏及标识异常情况，评价对资产余额真实性与减值的影响，形成审计结论..." @blur="persist('H7-10-conclusion', conclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>仪表板数据自动从 H7-9 盘点检查表汇总。</li>
        <li>盘亏需评估是否影响生产性生物资产余额（科目 1621）的真实性并考虑是否计提减值。</li>
        <li>账实相符率低于 95% 应进一步追查原因并扩大盘点范围。</li>
        <li>标识不一致、活体死亡未及时核销等异常应在结论中说明并提出调整建议。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Stocktake } from '../../composables/useH7Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const stk = useH7Stocktake(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

interface Row { rowId: string; name: string; category: string; bookQty: number; actualQty: number; result: string; diffReason: string }

const checkRows = ref<Row[]>([])
const conclusion = ref('')

function qtyDiff(r: Row): number { return (Number(r.actualQty) || 0) - (Number(r.bookQty) || 0) }
const totalRows = computed(() => checkRows.value.length)
const surplusRows = computed(() => checkRows.value.filter((r) => r.result === '盘盈'))
const deficitRows = computed(() => checkRows.value.filter((r) => r.result === '盘亏'))

const stat = computed(() => {
  const s = { total: checkRows.value.length, match: 0, surplus: 0, deficit: 0, matchRate: 0 }
  for (const r of checkRows.value) {
    if (r.result === '账实相符') s.match++
    else if (r.result === '盘盈') s.surplus++
    else if (r.result === '盘亏') s.deficit++
  }
  s.matchRate = s.total ? (s.match / s.total) * 100 : 0
  return s
})

function seed(): void {
  const raw = stk.getString('H7-9-rows')
  if (raw) {
    try {
      const p = JSON.parse(raw)
      if (Array.isArray(p)) checkRows.value = p.map((x: any) => ({
        rowId: x.rowId ?? '', name: x.name ?? '', category: x.category ?? '',
        bookQty: Number(x.bookQty) || 0, actualQty: Number(x.actualQty) || 0,
        result: x.result ?? '', diffReason: x.diffReason ?? '',
      }))
    } catch { /* ignore */ }
  }
  conclusion.value = stk.getString('H7-10-conclusion')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }

async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `监盘小结：盘点总数 ${stat.value.total}，账实相符 ${stat.value.match}，盘盈 ${stat.value.surplus}，盘亏 ${stat.value.deficit}，相符率 ${stat.value.matchRate.toFixed(1)}%。`
  const text = await generateAiText('h7-stocktake-summary', ctx, conclusion.value)
  if (text) { conclusion.value = text; persist('H7-10-conclusion', conclusion.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtNum(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h7-tab-stocktake-summary { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.dashboard-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.stat-box { text-align: center; padding: 12px; border-radius: 6px; background: var(--el-fill-color-light); }
.stat-box.success { background: var(--el-color-success-light-9); }
.stat-box.warning { background: var(--el-color-warning-light-9); }
.stat-box.danger { background: var(--el-color-danger-light-9); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value { font-size: 24px; font-weight: 700; margin-top: 4px; }
.match-rate-bar { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.detail-card { margin-bottom: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.text-danger { color: var(--el-color-danger); }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
