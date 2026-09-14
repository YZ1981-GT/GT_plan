<template>
  <section class="g4-status-panel" data-testid="g4-sheet-status">
    <header class="status-head">
      <h4>G4 套件编制进度</h4>
      <p>数据、结论与关键质量闸门（基于已保存 checklist）</p>
    </header>
    <div class="status-grid">
      <div v-for="item in items" :key="item.code" class="status-card" :class="item.tone">
        <div class="code">{{ item.code }}</div>
        <div class="label">{{ item.label }}</div>
        <div class="flags">
          <el-tag size="small" :type="item.hasData ? 'success' : 'info'" effect="plain">
            {{ item.hasData ? '已有数据' : '未填' }}
          </el-tag>
          <el-tag v-if="item.hasData" size="small" :type="item.conclusionComplete ? 'success' : 'warning'" effect="plain">
            结论 {{ item.conclusionComplete ? '完成' : '待补' }}
          </el-tag>
          <el-tag v-if="item.gate != null" size="small" :type="item.gate ? 'success' : 'warning'" effect="plain">
            闸门 {{ item.gate ? '就绪' : '待办' }}
          </el-tag>
          <el-tag v-if="item.balance != null" size="small" :type="item.balance ? 'success' : 'danger'" effect="plain">
            勾稽 {{ item.balance ? '平' : '差' }}
          </el-tag>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { evaluateG4SuiteStatus } from '../composables/g4SuiteStatus'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
}>()

const items = computed(() => evaluateG4SuiteStatus(props.allResponses))
</script>

<style scoped>
.g4-status-panel {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid #e8ecf2;
  border-radius: 8px;
  background: #fafbfc;
}
.status-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: #1f2a37; }
.status-head p { margin: 2px 0 10px; font-size: 12px; color: #86909c; }
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(145px, 1fr));
  gap: 8px;
}
.status-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px 10px; background: #fff; }
.status-card.ok { border-color: #c6e8d4; background: #f0f9f4; }
.status-card.warn { border-color: #f0d9b8; background: #fff8f0; }
.status-card.idle { opacity: 0.82; }
.code { font-weight: 700; font-size: 12px; color: #303133; }
.label { margin: 2px 0 6px; font-size: 12px; color: #606266; }
.flags { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
