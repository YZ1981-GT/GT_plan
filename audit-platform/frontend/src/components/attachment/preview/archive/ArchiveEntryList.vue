<template>
  <div class="gt-archive-list" data-testid="archive-entry-list">
    <div
      v-for="(e, idx) in entries"
      :key="idx"
      class="gt-archive-list__row"
      data-testid="archive-entry-row"
    >
      <span class="gt-archive-list__name" data-field="name">{{ e.name }}</span>
      <span class="gt-archive-list__size" data-field="size">{{ e.size }}</span>
      <span class="gt-archive-list__time" data-field="time">{{ e.mtime || '—' }}</span>
      <span class="gt-archive-list__dir" data-field="directory">{{ e.isDirectory ? 'dir' : 'file' }}</span>
      <span
        v-if="e.suspicious"
        class="gt-archive-list__flag"
        data-field="suspicious"
      >suspicious</span>
      <span
        v-if="e.unparsable"
        class="gt-archive-list__flag"
        data-field="unparsable"
      >unparsable</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ArchiveEntryMeta } from '../archive/archiveContainer'

defineProps<{
  entries: ArchiveEntryMeta[]
}>()
</script>

<style scoped>
.gt-archive-list { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.gt-archive-list__row { display: grid; grid-template-columns: 1fr 80px 140px 48px auto; gap: 8px; }
.gt-archive-list__flag { color: var(--gt-color-danger, #c45656); }
</style>
