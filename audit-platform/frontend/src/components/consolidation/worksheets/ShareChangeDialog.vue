<template>
  <el-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)"
    :title="`净资产表_股比变${changeTimes}次 — ${companyName}`"
    width="95%" top="2vh" append-to-body destroy-on-close>
    <div class="sc-layout">
      <!-- 左侧：净资产变动 -->
      <div class="sc-left">
        <h4>{{ companyName }} 净资产变动</h4>
        <el-table :data="netAssetRows" border size="small" class="ws-table" max-height="600"
          :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
          <el-table-column prop="item" label="项目" width="200" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span :style="{ paddingLeft: (row.indent || 0) * 12 + 'px', fontWeight: row.bold ? 700 : 400 }">
                {{ row.item }}
              </span>
            </template>
          </el-table-column>
          <!-- 变动前 -->
          <el-table-column label="变动前" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!row.isHeader" v-model="row.before" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
          <!-- 变动后（1~N次） -->
          <el-table-column v-for="t in changeTimes" :key="t" :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!row.isHeader" v-model="row.after[t - 1]" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 右侧：权益法模拟区 -->
      <div class="sc-right">
        <h4>权益法模拟</h4>
        <!-- 直接持股 -->
        <div class="sc-section">
          <div class="sc-section-title">直接持股权益法模拟 — {{ companyName }}</div>
          <el-table :data="directEquityRows" border size="small" class="ws-table" max-height="400"
            :header-cell-style="headerStyle" :cell-style="cellStyle">
            <el-table-column prop="subject" label="一级科目" width="140" show-overflow-tooltip />
            <el-table-column prop="detail" label="二级明细" width="120" show-overflow-tooltip />
            <!-- 变动前/后 借贷列 -->
            <el-table-column v-for="t in (changeTimes + 1)" :key="'d' + t"
              :label="t === 1 ? '变动前' : (changeTimes === 1 ? '变动后' : `第${t-1}次变动后`)" align="center">
              <el-table-column label="借方" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-model="row.debit[t - 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷方" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-model="row.credit[t - 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>
        </div>

        <!-- 间接持股（可多个） -->
        <div v-for="(indirect, ii) in indirectCompanies" :key="ii" class="sc-section">
          <div class="sc-section-title">间接持股权益法模拟 — {{ indirect.name }}</div>
          <el-table :data="indirect.rows" border size="small" class="ws-table" max-height="300"
            :header-cell-style="headerStyle" :cell-style="cellStyle">
            <el-table-column prop="subject" label="一级科目" width="140" show-overflow-tooltip />
            <el-table-column prop="detail" label="二级明细" width="120" show-overflow-tooltip />
            <el-table-column v-for="t in (changeTimes + 1)" :key="'i' + ii + t"
              :label="t === 1 ? '变动前' : (changeTimes === 1 ? '变动后' : `第${t-1}次变动后`)" align="center">
              <el-table-column label="借方" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-model="row.debit[t - 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷方" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-model="row.credit[t - 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface EquitySimRow {
  subject: string; detail: string
  debit: (number | null)[]; credit: (number | null)[]
}
interface IndirectCompany { name: string; rows: EquitySimRow[] }

interface NetAssetChangeRow {
  item: string; before: number | null; after: (number | null)[]
  indent?: number; bold?: boolean; isHeader?: boolean
}

const props = defineProps<{
  visible: boolean
  companyName: string
  changeTimes: 1 | 2 | 3
  netAssetRows: NetAssetChangeRow[]
  directEquityRows: EquitySimRow[]
  indirectCompanies: IndirectCompany[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', data: { netAsset: NetAssetChangeRow[]; direct: EquitySimRow[]; indirect: IndirectCompany[] }): void
}>()

const netAssetRows = ref([...props.netAssetRows])
const directEquityRows = ref([...props.directEquityRows])
const indirectCompanies = ref([...props.indirectCompanies])

watch(() => props.netAssetRows, (v) => { netAssetRows.value = [...v] }, { deep: true })
watch(() => props.directEquityRows, (v) => { directEquityRows.value = [...v] }, { deep: true })
watch(() => props.indirectCompanies, (v) => { indirectCompanies.value = [...v] }, { deep: true })

function onSave() {
  emit('save', {
    netAsset: netAssetRows.value,
    direct: directEquityRows.value,
    indirect: indirectCompanies.value,
  })
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }

function rowClassName({ row }: { row: any }) {
  if (row.isHeader) return 'ws-row-header'
  if (row.bold) return 'ws-row-bold'
  return ''
}
</script>

<style scoped>
.sc-layout { display: flex; gap: 16px; overflow-x: auto; }
.sc-left { flex: 0 0 auto; min-width: 400px; }
.sc-right { flex: 1; min-width: 0; overflow-x: auto; }
.sc-section { margin-bottom: 16px; }
.sc-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 4px 8px; background: #f8f6fb; border-radius: 4px; }
h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.ws-row-header td) { background: #f8f6fb !important; font-weight: 600; }
.ws-table :deep(.ws-row-bold td) { font-weight: 600; }
.ws-computed { color: #4b2d77; font-weight: 500; }
</style>
