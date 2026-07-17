<template>
  <div class="cycle-import-export">
    <el-segmented
      v-if="variants && variants.length > 1"
      v-model="activeSheet"
      :options="variantOptions"
      size="small"
      class="variant-bar"
    />
    <template v-if="expanded">
      <el-button size="small" :disabled="disabled" @click="exportTemplate(activeSheet)">
        下载模板
      </el-button>
      <el-button size="small" :disabled="disabled" @click="exportData(activeSheet)">
        导出 Excel
      </el-button>
      <el-upload
        :show-file-list="false"
        accept=".xlsx"
        :auto-upload="false"
        :disabled="disabled || importing"
        @change="onImportChange"
      >
        <el-button size="small" type="primary" plain :loading="importing" :disabled="disabled">
          导入 Excel
        </el-button>
      </el-upload>
    </template>
    <el-dropdown v-else trigger="click" size="small">
      <el-button size="small" :disabled="disabled">
        导入导出 ▾
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item @click="exportTemplate(activeSheet)">导出模板</el-dropdown-item>
          <el-dropdown-item @click="exportData(activeSheet)">导出数据</el-dropdown-item>
          <el-dropdown-item>
            <el-upload
              :show-file-list="false"
              accept=".xlsx"
              :auto-upload="false"
              :disabled="disabled || importing"
              @change="onImportChange"
            >
              <span>导入数据</span>
            </el-upload>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { useWorkpaperImportExport } from '../composables/useWorkpaperImportExport'

const props = defineProps<{
  wpId: string
  apiPrefix: string
  sheet: string
  disabled?: boolean
  expanded?: boolean
  variants?: readonly { label: string; sheet: string }[]
}>()

const emit = defineEmits<{
  imported: []
}>()

const activeSheet = ref(props.sheet)

watch(
  () => props.sheet,
  (s) => { activeSheet.value = s },
)

const variantOptions = computed(() =>
  (props.variants ?? []).map((v) => ({ label: v.label, value: v.sheet })),
)

const { exportTemplate, exportData, importData, importing } = useWorkpaperImportExport({
  wpId: toRef(props, 'wpId'),
  apiPrefix: props.apiPrefix,
})

async function onImportChange(f: { raw?: File } | File) {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  const result = await importData(activeSheet.value, file)
  if (result) emit('imported')
}
</script>

<style scoped>
.cycle-import-export { display: inline-flex; align-items: center; gap: 8px; }
.variant-bar { max-width: 360px; }
</style>
