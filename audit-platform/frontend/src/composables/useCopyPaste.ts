import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { SelectedCell } from '@/composables/useCellSelection'
export interface PasteDiffCell { rowIdx: number; colIdx: number; key: string; oldValue: string; newValue: string }
export interface PasteDiffResult { cells: PasteDiffCell[]; rowCount: number; colCount: number; overflowCount: number }
export interface PasteAuditSummary { action: 'paste'; timestamp: number; rowCount: number; colCount: number; cellCount: number; startRow: number; startCol: number; sampleChanges: Array<{ key: string; row: number; old: string; new: string }> }
export interface UndoEntry { type: 'paste'; timestamp: number; changes: Array<{ rowIdx: number; colIdx: number; key: string; oldValue: string; newValue: string }> }
export function parseAmountString(raw: string): string {
  if (raw == null) return ''
  const trimmed = raw.trim()
  if (trimmed === '' || trimmed === '-' || trimmed === '\u2014' || trimmed === '\u2013') return ''
  if (trimmed.endsWith('%')) { const np = trimmed.slice(0, -1).replace(/,/g, '').trim(); const n = Number(np); if (!isNaN(n)) return String(n / 100); return trimmed }
  const bm = trimmed.match(/^\((.+)\)$/)
  if (bm) { const inner = bm[1].replace(/,/g, '').trim(); const n = Number(inner); if (!isNaN(n)) return String(-n); return trimmed }
  const nc = trimmed.replace(/,/g, ''); const n = Number(nc)
  if (!isNaN(n) && nc !== '') return String(n)
  return trimmed
}
export function parseHtmlTable(html: string): string[][] | null {
  if (!html || !/<table[\s>]/i.test(html)) return null
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const table = doc.querySelector('table')
  if (!table) return null
  const trs = table.querySelectorAll('tr')
  if (trs.length === 0) return null
  const matrix: string[][] = []
  for (const tr of trs) {
    const cells = tr.querySelectorAll('td, th')
    const row: string[] = []
    for (const cell of cells) row.push((cell.textContent || '').trim())
    if (row.length > 0) matrix.push(row)
  }
  return matrix.length > 0 ? matrix : null
}
export function parseTextMatrix(text: string): string[][] {
  if (!text || !text.trim()) return []
  return text.split(/\r?\n/).filter(l => l.length > 0).map(l => l.split('\t'))
}
function escapeHtml(s: string): string { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') }
export async function copySelection(selectedCells: SelectedCell[], tableData: Record<string, any>[], columns: { key: string; label: string }[]): Promise<void> {
  if (!selectedCells.length) { ElMessage.warning('\u8BF7\u5148\u9009\u4E2D\u8981\u590D\u5236\u7684\u5355\u5143\u683C'); return }
  const rs = selectedCells.map(c => c.row), cs = selectedCells.map(c => c.col)
  const minR = Math.min(...rs), maxR = Math.max(...rs), minC = Math.min(...cs), maxC = Math.max(...cs)
  const lines: string[][] = []
  for (let r = minR; r <= maxR; r++) { const rc: string[] = []; for (let c = minC; c <= maxC; c++) { const cl = selectedCells.find(x => x.row === r && x.col === c); if (cl?.value != null) rc.push(String(cl.value)); else { const rd = tableData[r], cd = columns[c]; rc.push(rd && cd ? String(rd[cd.key] ?? '') : '') } } lines.push(rc) }
  const text = lines.map(r => r.join('\t')).join('\n')
  const htmlR = lines.map(r => '<tr>' + r.map(c => '<td>' + escapeHtml(c) + '</td>').join('') + '</tr>').join('')

  const html = '<table border="1">' + htmlR + '</table>'
  try { await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })]); ElMessage.success('已复制') } catch (e) { await navigator.clipboard?.writeText(text); ElMessage.success('已复制为文本格式') }
}
export function buildPasteDiff(pasteMatrix: string[][], selectedCells: SelectedCell[], tableData: Record<string, any>[], columns: { key: string; label: string }[], normalizeAmounts = true): PasteDiffResult {
  const cells: PasteDiffCell[] = []; let overflowCount = 0
  if (!selectedCells.length || !pasteMatrix.length) return { cells, rowCount: 0, colCount: 0, overflowCount: 0 }
  const sR = Math.min(...selectedCells.map(c => c.row)), sC = Math.min(...selectedCells.map(c => c.col))
  for (let ri = 0; ri < pasteMatrix.length; ri++) { const tR = sR + ri; if (tR >= tableData.length) { overflowCount += pasteMatrix[ri].length; continue }; for (let ci = 0; ci < pasteMatrix[ri].length; ci++) { const tC = sC + ci; if (tC >= columns.length) { overflowCount++; continue }; const cd = columns[tC]; const nv = normalizeAmounts ? parseAmountString(pasteMatrix[ri][ci]) : pasteMatrix[ri][ci]; const ov = String(tableData[tR][cd.key] ?? ''); if (ov !== nv) cells.push({ rowIdx: tR, colIdx: tC, key: cd.key, oldValue: ov, newValue: nv }) } }
  return { cells, rowCount: pasteMatrix.length, colCount: pasteMatrix.length > 0 ? Math.max(...pasteMatrix.map(r => r.length)) : 0, overflowCount }
}
export function pasteToSelection(event: ClipboardEvent, selectedCells: SelectedCell[], tableData: Record<string, any>[], columns: { key: string; label: string }[], options?: { onCellChange?: (r: number, c: number, k: string, v: string) => void; undoStack?: UndoEntry[]; onAuditLog?: (s: PasteAuditSummary) => void; normalizeAmounts?: boolean; onNotify?: (msg: string) => void }): number {
  const opts = options || {}; const norm = opts.normalizeAmounts !== false
  const hd = event.clipboardData?.getData('text/html') || ''; const td = event.clipboardData?.getData('text/plain') || ''
  const hm = parseHtmlTable(hd); const pm = (hm && hm.length > 0) ? hm : parseTextMatrix(td)
  if (!pm.length || !selectedCells.length) return 0
  const sR = Math.min(...selectedCells.map(c => c.row)), sC = Math.min(...selectedCells.map(c => c.col))
  const changes: UndoEntry['changes'] = []; let written = 0
  for (let ri = 0; ri < pm.length; ri++) { const tR = sR + ri; if (tR >= tableData.length) break; for (let ci = 0; ci < pm[ri].length; ci++) { const tC = sC + ci; if (tC >= columns.length) break; const cd = columns[tC]; const v = norm ? parseAmountString(pm[ri][ci]) : pm[ri][ci]; const ov = String(tableData[tR][cd.key] ?? ''); changes.push({ rowIdx: tR, colIdx: tC, key: cd.key, oldValue: ov, newValue: v }); tableData[tR][cd.key] = v; if (opts.onCellChange) opts.onCellChange(tR, tC, cd.key, v); written++ } }
  if (opts.undoStack && changes.length > 0) opts.undoStack.push({ type: 'paste', timestamp: Date.now(), changes })
  if (opts.onAuditLog && changes.length > 0) opts.onAuditLog({ action: 'paste', timestamp: Date.now(), rowCount: pm.length, colCount: pm.length > 0 ? Math.max(...pm.map(r => r.length)) : 0, cellCount: written, startRow: sR, startCol: sC, sampleChanges: changes.slice(0, 5).map(c => ({ key: c.key, row: c.rowIdx, old: c.oldValue.slice(0, 20), new: c.newValue.slice(0, 20) })) })
  const msg = `已粘贴 ${pm.length} 行 × ${pm[0]?.length || 0} 列（${written} 格）`
  if (written > 0) { if (opts.onNotify) opts.onNotify(msg); else ElMessage.success(msg) }
  return written
}
export function undoLastPaste(undoStack: UndoEntry[], tableData: Record<string, any>[], onCellChange?: (r: number, c: number, k: string, v: string) => void): boolean {
  if (undoStack.length === 0) return false
  const entry = undoStack.pop()!; for (const ch of entry.changes) { if (ch.rowIdx < tableData.length) { tableData[ch.rowIdx][ch.key] = ch.oldValue; if (onCellChange) onCellChange(ch.rowIdx, ch.colIdx, ch.key, ch.oldValue) } }
  ElMessage.info(`已撤销粘贴（${entry.changes.length} 格）`); return true
}
export function setupPasteListener(containerRef: Ref<HTMLElement | { $el: HTMLElement } | null>, handler: (event: ClipboardEvent) => void): void {
  const onPaste = (e: ClipboardEvent) => { const t = e.target as HTMLElement; if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) return; e.preventDefault(); handler(e) }
  onMounted(() => { const el = containerRef.value; if (!el) return; const dom = '$el' in el ? (el as any).$el : el; if (dom) dom.addEventListener('paste', onPaste) })
  onUnmounted(() => { const el = containerRef.value; if (!el) return; const dom = '$el' in el ? (el as any).$el : el; if (dom) dom.removeEventListener('paste', onPaste) })
}
export function usePasteEnhanced() {
  const undoStack = ref<UndoEntry[]>([]); const auditLog = ref<PasteAuditSummary[]>([]); const lastDiff = ref<PasteDiffResult | null>(null)
  const recordAudit = (s: PasteAuditSummary) => { auditLog.value.push(s); if (auditLog.value.length > 50) auditLog.value = auditLog.value.slice(-50) }
  const undo = (td: Record<string, any>[], cb?: (r: number, c: number, k: string, v: string) => void) => undoLastPaste(undoStack.value, td, cb)
  const canUndo = () => undoStack.value.length > 0
  const clearUndoStack = () => { undoStack.value = [] }
  return { undoStack, auditLog, lastDiff, recordAudit, undo, canUndo, clearUndoStack }
}
