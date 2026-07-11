<template>
  <div class="h7-tab-addition-fair">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：验证公允价值模式下本期生产性生物资产增加的真实性与初始公允价值计量的可靠性，公允价值确定方法符合 CAS 5《生物资产》与 CAS 39《公允价值计量》。
      </template>
    </el-alert>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-6 增加检查（公允价值模式）— {{ rows.length }}项 合计 {{ fmtAmt(totalAmount) }}
            <GtIndexChip value="wp:H7-13" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-6')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        采用公允价值模式的前提：生物资产有活跃交易市场，能够可靠取得市场价格及相关信息（CAS 5 第二十二条）。
        初始公允价值优先取活跃市场报价，无活跃市场时采用近期交易价格或估值技术。
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="persistRows" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="资产类别" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" @change="persistRows">
              <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseType" label="增加方式" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.increaseType" size="small" @change="persistRows">
              <el-option v-for="t in INCREASE_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.increaseType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairValue" label="初始公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.fairValue" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairMethod" label="公允价值确定方法" width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.fairMethod" size="small" @change="persistRows">
              <el-option v-for="m in FAIR_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.fairMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairLevel" label="公允价值层级" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.fairLevel" size="small" style="width:96px" @change="persistRows">
              <el-option label="第一层级" value="第一层级" />
              <el-option label="第二层级" value="第二层级" />
              <el-option label="第三层级" value="第三层级" />
            </el-select>
            <span v-else>{{ row.fairLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reliable" label="可靠计量" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.reliable" size="small" style="width:80px" @change="persistRows">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.reliable === '是' ? 'success' : 'danger'" size="small">{{ row.reliable || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="检查结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="persistRows" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增增加项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录公允价值获取来源、层级判断依据与合理性评价" @blur="persist('H7-6-fair-note', auditNote)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>公允价值模式仅在存在活跃市场且能可靠取得公允价值时采用（CAS 5 第二十二条）。</li>
        <li>公允价值层级判断参考 CAS 39：第一层级=活跃市场报价，第二层级=可观察输入值，第三层级=不可观察输入值。</li>
        <li>初始公允价值应与 H7-13 公允价值复核表的复核结论保持一致。</li>
        <li>本期增加合计应与 H7-2 明细表（公允）本期增加勾稽一致。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7AdditionCheck } from '../../composables/useH7AdditionCheck'
import { calcSubtotal } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const check = useH7AdditionCheck(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const CATEGORY_OPTIONS = ['经济林木', '产畜（种畜/役畜）', '产蛋/产奶禽畜', '水产养殖', '其他']
const INCREASE_TYPES = ['外购', '自行栽培/繁殖', '在建工程转入', '接受捐赠', '互转转入', '其他']
const FAIR_METHODS = ['活跃市场报价', '近期交易价格', '市场法估值', '收益法估值', '成本法估值']

interface Row {
  rowId: string
  assetName: string
  category: string
  increaseType: string
  fairValue: number
  fairMethod: string
  fairLevel: string
  reliable: string
  voucherNo: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')

const totalAmount = computed(() => calcSubtotal(rows.value.map((r) => Number(r.fairValue) || 0)))

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    category: raw.category ?? '',
    increaseType: raw.increaseType ?? '',
    fairValue: Number(raw.fairValue) || 0,
    fairMethod: raw.fairMethod ?? '',
    fairLevel: raw.fairLevel ?? '',
    reliable: raw.reliable ?? '',
    voucherNo: raw.voucherNo ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = check.getString('H7-6-fair-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = check.getString('H7-6-fair-note')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-6-fair-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增增加项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ assetName: value })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `公允价值模式下本期生产性生物资产增加 ${rows.value.length} 项，合计公允价值 ${fmtAmt(totalAmount.value)}。`
  const text = await generateAiText('h7-addition-fair', ctx, auditNote.value)
  if (text) { auditNote.value = text; persist('H7-6-fair-note', auditNote.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-addition-fair { padding: 16px; font-size: 13px; }
.audit-goal { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.methodology-block { padding: 10px 14px; background: #fffbe6; border-left: 3px solid #e6a23c; border-radius: 4px; margin-bottom: 16px; font-size: 12px; }
.check-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
