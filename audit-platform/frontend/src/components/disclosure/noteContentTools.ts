/**
 * 附注正文批量写入在编辑器里的两个挂载点：工具入口（上传 / 保存模板 / 引用模板 / 导入上年附注）与章节来源标记。
 * DisclosureEditor.vue 已到行数硬上限，经此一个 import 引入两者，不再增加编辑器行数。
 */
export { default as DisclosureNoteContentTools } from './DisclosureNoteContentTools.vue'
export { default as NoteSourceBadge } from './NoteSourceBadge.vue'
