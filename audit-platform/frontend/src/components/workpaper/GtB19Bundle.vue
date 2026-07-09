<script setup lang="ts">
/**
 * GtB19Bundle — B19 识别关联方程序表
 *
 * Excel 内含：
 * - B19识别关联方程序表 → 程序表
 * - B19-1管理层提供的关联方清单 → 同文件 sheet（wp_code_overrides 中 B19-1=skip，无独立底稿）
 *
 * B19-1 必须用父 wpId + OnlyOffice 打开对应 sheet，禁止按独立 wp_index 加载。
 */
import { ref, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import GtAProgramConsole from './GtAProgramConsole.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

const RP_LIST_SHEET = 'B19-1管理层提供的关联方清单'

const TABS = [
  {
    id: 'program',
    label: '程序表',
    aliases: ['program', 'B19识别关联方程序表', '识别关联方程序表'],
  },
  {
    id: 'B19-1',
    label: 'B19-1 管理层提供的关联方清单',
    aliases: [
      'B19-1',
      RP_LIST_SHEET,
      '管理层提供的关联方清单',
    ],
  },
]

const route = useRoute()
const active = ref('program')

function resolveTabId(raw?: string | null): string {
  if (!raw) return 'program'
  const s = String(raw).trim()
  for (const t of TABS) {
    if (t.id === s) return t.id
    if (t.aliases.some((a) => a === s || s.includes(a) || a.includes(s))) return t.id
  }
  return 'program'
}

watch(() => props.sheetName, () => {
  active.value = resolveActiveTab()
})

watch(
  () => [route.query.view, route.query.sheet] as const,
  () => {
    active.value = resolveActiveTab()
  },
)

function resolveActiveTab(): string {
  // 优先用 ?view= / ?sheet= 中的 B19-1 意图，再回退 props.sheetName
  const view = route.query.view as string | undefined
  const qSheet = route.query.sheet as string | undefined
  if (view) return resolveTabId(view)
  if (qSheet && resolveTabId(qSheet) === 'B19-1') return 'B19-1'
  return resolveTabId(props.sheetName || qSheet)
}

onMounted(() => {
  active.value = resolveActiveTab()
})
</script>

<template>
  <div class="gt-b19-bundle">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in TABS"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <GtAProgramConsole
          v-if="t.id === 'program'"
          :wp-id="wpId"
          :embedded="true"
          :readonly="readonly"
        />
        <div v-else-if="t.id === 'B19-1'" class="gt-b19-bundle__rp-list">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="被审计单位关联方清单"
            description="在此维护管理层提供的关联方名称与关系。各循环明细表（如 D1-3）将据此自动匹配「关联关系」列。"
            class="gt-b19-bundle__alert"
          />
          <GtOnlyOfficeSheet
            :wp-id="wpId"
            :sheet-name="RP_LIST_SHEET"
            :project-id="projectId"
            :readonly="readonly"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.gt-b19-bundle__alert {
  margin-bottom: 12px;
}

.gt-b19-bundle__rp-list {
  min-height: 480px;
}
</style>
