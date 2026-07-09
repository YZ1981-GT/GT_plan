<template>
  <div class="j1-tab-detail">
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="['HTML', 'OnlyOffice']" size="small" />
      <el-dropdown class="ml-auto" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('detail')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('detail')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <template v-if="mode === 'HTML'">
      <el-card shadow="never">
        <template #header>
          <span class="section-title">应付职工薪酬明细表</span>
        </template>
        <el-table :data="rows" border size="small" style="font-size: 13px" max-height="600">
          <el-table-column prop="label" label="项目" min-width="140" fixed />
          <el-table-column label="期初段" align="center">
            <el-table-column prop="beginUnadj" label="未审" width="90" align="right" />
            <el-table-column prop="beginAje" label="AJE" width="80" align="right" />
            <el-table-column prop="beginRje" label="RJE" width="80" align="right" />
            <el-table-column prop="beginAudited" label="审定" width="100" align="right" />
          </el-table-column>
          <el-table-column label="期末段" align="center">
            <el-table-column prop="endUnadj" label="未审" width="90" align="right" />
            <el-table-column prop="endAje" label="AJE" width="80" align="right" />
            <el-table-column prop="endRje" label="RJE" width="80" align="right" />
            <el-table-column prop="endAudited" label="审定" width="100" align="right" />
          </el-table-column>
          <el-table-column label="附注（负债期末=期初+贷-借）" align="center">
            <el-table-column prop="noteBegin" label="期初" width="90" align="right" />
            <el-table-column prop="noteIncrease" label="增加" width="90" align="right" />
            <el-table-column prop="noteDecrease" label="减少" width="90" align="right" />
            <el-table-column label="期末" width="100" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+增加-减少">{{ row.noteEnd?.toFixed(2) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式（明细表J1-2）" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1Detail } from '@/composables/workpaper/j1/useJ1Detail'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const mode = ref('HTML')
const htmlDataRef = ref(props.htmlData || {})
const { rows, initFromHtmlData } = useJ1Detail(htmlDataRef)
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) importData('detail', file)
  }
  input.click()
}
</script>

<style scoped>
.j1-tab-detail { padding: 16px; }
.mode-bar { display: flex; align-items: center; margin-bottom: 12px; gap: 12px; }
.ml-auto { margin-left: auto; }
.section-title { font-weight: 600; font-size: 15px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
</style>
