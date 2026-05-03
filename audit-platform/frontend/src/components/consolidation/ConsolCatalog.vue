<template>
  <div class="cc-catalog">
    <!-- 国企/上市切换 -->
    <div class="cc-header">
      <el-radio-group v-model="standard" size="small" @change="loadData">
        <el-radio-button value="soe">国企版</el-radio-button>
        <el-radio-button value="listed">上市版</el-radio-button>
      </el-radio-group>
    </div>

    <!-- Tab 切换：报表 / 附注 -->
    <el-tabs v-model="activeTab" size="small" class="cc-tabs">
      <el-tab-pane label="报表" name="reports">
        <div class="cc-tree">
          <el-tree :data="reportTree" :props="{ label: 'label', children: 'children' }"
            node-key="key" default-expand-all highlight-current
            @node-click="onReportClick">
            <template #default="{ data }">
              <span class="cc-tree-node">
                <span>{{ data.icon }} {{ data.label }}</span>
                <el-tag v-if="data.count" size="small" type="info" style="margin-left:4px">{{ data.count }}行</el-tag>
              </span>
            </template>
          </el-tree>
        </div>
      </el-tab-pane>
      <el-tab-pane label="附注" name="notes">
        <div class="cc-tree">
          <el-input v-model="noteSearch" size="small" placeholder="搜索附注..." clearable style="margin-bottom:6px" />
          <el-tree :data="noteTree" :props="{ label: 'label', children: 'children' }"
            node-key="key" default-expand-all highlight-current
            :filter-node-method="filterNote" ref="noteTreeRef"
            @node-click="onNoteClick">
            <template #default="{ data }">
              <span class="cc-tree-node">
                <span>{{ data.label }}</span>
                <el-tag v-if="data.tableCount" size="small" type="info" style="margin-left:4px">{{ data.tableCount }}表</el-tag>
              </span>
            </template>
          </el-tree>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import http from '@/utils/http'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const standard = ref('soe')
const activeTab = ref('reports')
const noteSearch = ref('')
const noteTreeRef = ref<any>(null)

// ─── 报表树 ──────────────────────────────────────────────────────────────────
const reportTree = computed(() => [
  { key: 'bs', label: '资产负债表', icon: '📋', type: 'balance_sheet' },
  { key: 'is', label: '利润表', icon: '📈', type: 'income_statement' },
  { key: 'cf', label: '现金流量表', icon: '💰', type: 'cash_flow_statement' },
  { key: 'eq', label: '权益变动表', icon: '📊', type: 'equity_statement' },
  { key: 'cfs', label: '现金流附表', icon: '📑', type: 'cash_flow_supplement' },
  { key: 'imp', label: '资产减值准备表', icon: '⚠️', type: 'impairment_provision' },
])

// ─── 附注树 ──────────────────────────────────────────────────────────────────
const noteTree = ref<any[]>([])

async function loadData() {
  try {
    const { data } = await http.get(`/api/note-templates/${standard.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const sections = data?.data ?? data ?? []
    if (!Array.isArray(sections)) { noteTree.value = []; return }

    const chapterMap: Record<string, { label: string; children: any[] }> = {}
    const chapterOrder = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
    const chapterLabels: Record<string, string> = {
      '一': '一、公司概况', '二': '二、编制基础', '三': '三、会计政策',
      '四': '四、税项', '五': '五、报表科目注释', '六': '六、其他',
      '七': '七、关联方', '八': '八、或有事项', '九': '九、承诺', '十': '十、日后事项',
    }

    for (const sec of sections) {
      const sectionId = sec.section_id || sec.note_section || ''
      const title = sec.section_title || sec.title || ''
      const chapterMatch = sectionId.match(/^([一二三四五六七八九十]+)/)
      const chapter = chapterMatch ? chapterMatch[1] : '其他'

      if (!chapterMap[chapter]) {
        chapterMap[chapter] = { label: chapterLabels[chapter] || `${chapter}、其他`, children: [] }
      }
      chapterMap[chapter].children.push({
        key: `note_${sectionId}`,
        label: title.length > 22 ? title.slice(0, 22) + '...' : title,
        fullTitle: title,
        sectionId,
        tableCount: (sec.tables || []).length || (sec.table_template ? 1 : 0),
      })
    }

    const tree: any[] = []
    for (const ch of chapterOrder) {
      if (chapterMap[ch]) {
        tree.push({ key: `ch_${ch}`, label: chapterMap[ch].label, children: chapterMap[ch].children })
      }
    }
    if (chapterMap['其他']) tree.push({ key: 'ch_other', label: '其他', children: chapterMap['其他'].children })
    noteTree.value = tree
  } catch { noteTree.value = [] }
}

function filterNote(value: string, data: any) {
  if (!value) return true
  return (data.label || '').includes(value) || (data.fullTitle || '').includes(value)
}

watch(noteSearch, (val) => { noteTreeRef.value?.filter(val) })

function onReportClick(data: any) {
  if (data.type) {
    window.dispatchEvent(new CustomEvent('consol-catalog-select', {
      detail: { type: 'report', reportType: data.type, standard: standard.value }
    }))
  }
}

function onNoteClick(data: any) {
  if (data.sectionId) {
    window.dispatchEvent(new CustomEvent('consol-catalog-select', {
      detail: { type: 'note', sectionId: data.sectionId, title: data.fullTitle || data.label, standard: standard.value }
    }))
  }
}

onMounted(() => loadData())
</script>

<style scoped>
.cc-catalog { display: flex; flex-direction: column; height: 100%; }
.cc-header { padding: 8px 10px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0; }
.cc-tabs { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.cc-tabs :deep(.el-tabs__header) { padding: 0 10px; margin-bottom: 0; }
.cc-tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; }
.cc-tabs :deep(.el-tab-pane) { height: 100%; overflow-y: auto; }
.cc-tree { padding: 6px; }
.cc-tree-node { display: flex; align-items: center; font-size: 12px; }
</style>
