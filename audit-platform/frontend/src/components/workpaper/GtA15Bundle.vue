<script setup lang="ts">
/** A15 持续经营 — 程序表 | A15-1 核对表 */
import { ref } from 'vue'
import GtAProgramConsole from './GtAProgramConsole.vue'
import GtEmbeddedChecklist from './GtEmbeddedChecklist.vue'

defineProps<{
  wpId: string
  readonly?: boolean
}>()

const active = ref('program')
</script>

<template>
  <div class="a15-bundle">
    <el-tabs v-model="active">
      <el-tab-pane label="审计程序" name="program">
        <GtAProgramConsole :wp-id="wpId" :embedded="true" />
      </el-tab-pane>
      <el-tab-pane label="A15-1 持续经营调查表" name="A15-1">
        <GtEmbeddedChecklist :wp-id="wpId" checklist-wp-code="A15-1" :readonly="readonly" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
