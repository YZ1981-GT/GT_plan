/**
 * ShortcutManager — 快捷键管理
 * Phase 8 Task 9.3
 */
import { eventBus } from '@/utils/eventBus'
import { commitAllGridEdits, isGridSink, isInsideGridEditor } from '@/components/grid/GridKernel'

export interface ShortcutEntry {
  key: string
  handler: () => void
  description: string
  scope?: string
}

/**
 * 检查当前焦点是否在输入框/文本域/可编辑元素内
 * 用于在输入框中忽略全局快捷键（Escape 除外）
 *
 * 表格的焦点承接框（透明 textarea，spec excel-style-table-editing ADR-4）不算输入框：
 * 选中单元格时 Ctrl+S / Ctrl+E / F5 等全局快捷键照常生效。
 */
export function isInputFocused(event: KeyboardEvent): boolean {
  return isTextEntryTarget(event.target)
}

/**
 * 键盘事件目标是不是文字输入处（输入框 / 文本域 / 可编辑区）。页面自己的快捷键（Backspace 返回、Ctrl+K 搜索、
 * Ctrl+Z 撤销结构改动等）判「在输入框里不拦截」时用它：表格承接框不算输入框，选中单元格时页面快捷键照常。
 */
export function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement) || isGridSink(target)) return false
  // isContentEditable 认继承的可编辑区；jsdom 不实现它，contentEditable === 'true' 兜底（与改造前的判定一致）
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || !!target.isContentEditable || target.contentEditable === 'true'
}

/** 单元格编辑中按 Ctrl+S：先提交这一格，再按保存快捷键处理（R8.2）。 */
function isGridEditorSave(event: KeyboardEvent): boolean {
  return (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 's' && isInsideGridEditor(event.target)
}

class ShortcutManager {
  private shortcuts: Map<string, ShortcutEntry> = new Map()
  private enabled = true

  register(key: string, handler: () => void, description: string, scope = '全局') {
    this.shortcuts.set(key, { key, handler, description, scope })
  }

  unregister(key: string) {
    this.shortcuts.delete(key)
  }

  handleKeydown(event: KeyboardEvent) {
    if (!this.enabled) return
    if (isGridEditorSave(event)) {
      commitAllGridEdits()
    } else if (isInputFocused(event) && event.key !== 'Escape') {
      // 在输入框/文本域/可编辑元素里忽略快捷键（Escape 除外）
      return
    }
    const key = this.getShortcutKey(event)
    const entry = this.shortcuts.get(key)
    if (entry) {
      entry.handler()
      event.preventDefault()
    }
  }

  getShortcutKey(event: KeyboardEvent): string {
    const modifiers: string[] = []
    if (event.ctrlKey || event.metaKey) modifiers.push('Ctrl')
    if (event.shiftKey) modifiers.push('Shift')
    if (event.altKey) modifiers.push('Alt')
    modifiers.push(event.key.toUpperCase())
    return modifiers.join('+')
  }

  getAll(): ShortcutEntry[] {
    return Array.from(this.shortcuts.values())
  }

  setEnabled(v: boolean) {
    this.enabled = v
  }

  install() {
    document.addEventListener('keydown', (e) => this.handleKeydown(e))
  }

  uninstall() {
    document.removeEventListener('keydown', (e) => this.handleKeydown(e))
  }
}

export const shortcutManager = new ShortcutManager()

// Default shortcuts from design doc
export function registerDefaultShortcuts(_router: any) {
  shortcutManager.register('Ctrl+S', () => {
    eventBus.emit('shortcut:save')
  }, '保存当前编辑内容', '底稿编辑/附注编辑/报告编辑')

  // [R9 F9 Task 31] Ctrl+Z/Y 不再由 shortcutManager 注册
  // Univer 编辑器内置 undo/redo 命令系统，原生处理 Ctrl+Z/Ctrl+Shift+Z
  // 如果 shortcutManager 拦截这些快捷键，会阻止 Univer 的撤销/重做功能

  // 注意：不注册 Ctrl+F，避免阻止浏览器原生搜索。
  // 各模块（TrialBalance/DisclosureEditor）自行监听 keydown 实现表内搜索。

  shortcutManager.register('Ctrl+G', () => {
    eventBus.emit('shortcut:goto')
  }, '跳转到指定科目', '试算表/穿透查询')

  shortcutManager.register('Ctrl+E', () => {
    eventBus.emit('shortcut:export')
  }, '导出当前页面', '报表/附注/底稿')

  shortcutManager.register('Ctrl+ENTER', () => {
    eventBus.emit('shortcut:submit')
  }, '提交/确认', '表单/弹窗')

  shortcutManager.register('ESCAPE', () => {
    eventBus.emit('shortcut:escape')
  }, '关闭弹窗/退出全屏', '全局')

  shortcutManager.register('F5', () => {
    eventBus.emit('shortcut:refresh')
  }, '刷新当前数据', '全局')

  shortcutManager.register('Ctrl+/', () => {
    eventBus.emit('shortcut:help')
  }, '显示快捷键帮助面板', '全局')

  shortcutManager.register('F1', () => {
    eventBus.emit('shortcut:help')
  }, '显示快捷键帮助面板', '全局')

  shortcutManager.register('Ctrl+TAB', () => {
    eventBus.emit('shortcut:tab-focus')
  }, '切换栏目焦点', '三栏/四栏布局')

  shortcutManager.register('Ctrl+ARROWUP', () => {
    eventBus.emit('shortcut:list-up')
  }, '列表项上移', '列表页')

  shortcutManager.register('Ctrl+ARROWDOWN', () => {
    eventBus.emit('shortcut:list-down')
  }, '列表项下移', '列表页')

  shortcutManager.install()
}
