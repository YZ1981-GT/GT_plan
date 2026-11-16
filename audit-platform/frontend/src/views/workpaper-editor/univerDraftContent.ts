/**
 * Univer 工作簿 → 未保存草稿正文（draft overlay 前端一半）。
 *
 * Feature: chat-host-draft-overlay / Task 4
 *
 * ## 为什么不直接 `JSON.stringify(workbook.getSnapshot())`
 *
 * Univer snapshot 把**样式、合并、列宽、条件格式、数据验证**全带上，一张真实底稿动辄
 * 几 MB；而后端上限是 20 万字符（超限直接 422、**不裁剪**，design §2）。把 snapshot 原样
 * 交上去的结果是：用户打开开关、点了发送、整轮对话失败。
 *
 * 模型需要的只是「哪个 sheet 的哪个格子是什么值」。所以这里只序列化**非空单元格的
 * 值与公式**，并按行号/列号排序，保证同一次未保存状态每次取值逐字相同（服务端按
 * sha256 判重，顺序抖动会让同一份草稿算出不同 hash）。
 *
 * ## 为什么不用 `Range.getValues()`
 *
 * 那要走 `getActiveSheet()` + 活动区域，只覆盖**当前 sheet** 的**选中区域**。用户改了
 * 别的 sheet 的格子时会被静默漏掉 —— 而「改一处不保存」正是本功能的验收场景。
 * snapshot 里 `cellData` 是全簿的，不需要选区。
 */

/** Univer snapshot 里一个格子的最小形状（其余字段本模块刻意忽略）。 */
interface UniverCellLike {
  v?: unknown
  f?: unknown
  p?: unknown
}

interface UniverSheetLike {
  name?: unknown
  cellData?: Record<string, Record<string, UniverCellLike | undefined>> | null
}

interface UniverSnapshotLike {
  sheets?: Record<string, UniverSheetLike | undefined> | null
  sheetOrder?: unknown
}

/** Excel 列号（0 基）→ 列字母（`0 → A`、`26 → AA`）。 */
export function columnLetter(index: number): string {
  let remaining = Math.max(0, Math.floor(index))
  let out = ''
  do {
    out = String.fromCharCode(65 + (remaining % 26)) + out
    remaining = Math.floor(remaining / 26) - 1
  } while (remaining >= 0)
  return out
}

function cellText(cell: UniverCellLike): string {
  const formula = typeof cell.f === 'string' ? cell.f.trim() : ''
  const value = cell.v
  const rendered =
    value === null || value === undefined
      ? ''
      : typeof value === 'object'
        ? (() => {
            try {
              return JSON.stringify(value)
            } catch {
              return String(value)
            }
          })()
        : String(value)
  if (formula && rendered) return `${formula} → ${rendered}`
  return formula || rendered
}

/**
 * 把工作簿 snapshot 摊成「`sheet` + `A1` 地址 + 值」的紧凑文本。
 *
 * * 空值格跳过（未保存草稿里没有内容就不该占 token）；
 * * sheet 顺序取 `sheetOrder`，缺失时按 id 排序 —— 保证稳定；
 * * 超过 `maxChars` 时**截断并显式说明**，不静默丢弃：前端截断的文案会出现在草稿正文里，
 *   模型与用户都看得出「后面还有」。这与后端「超限直接 422 不裁剪」并不矛盾 ——
 *   后端拒收的是**客户端声称完整**的超长草稿，而这里明确声明了截断位置。
 */
export function serializeUniverDraft(
  snapshot: unknown,
  options: { maxChars?: number } = {},
): string | null {
  const maxChars = options.maxChars ?? 180_000
  if (!snapshot || typeof snapshot !== 'object') return null
  const typed = snapshot as UniverSnapshotLike
  const sheets = typed.sheets
  if (!sheets || typeof sheets !== 'object') return null

  const order = Array.isArray(typed.sheetOrder)
    ? typed.sheetOrder.filter((id): id is string => typeof id === 'string' && id in sheets)
    : []
  const ids = order.length > 0 ? order : Object.keys(sheets).sort()

  const lines: string[] = []
  let truncated = false
  let used = 0
  for (const id of ids) {
    const sheet = sheets[id]
    if (!sheet || typeof sheet !== 'object') continue
    const name = typeof sheet.name === 'string' && sheet.name.trim() ? sheet.name.trim() : id
    const cellData = sheet.cellData
    if (!cellData || typeof cellData !== 'object') continue

    // 🔴 这里**不排序**：ECMAScript 规定 `Object.keys` 把「整数索引键」按数值升序返回
    //    （`OrdinaryOwnPropertyKeys`），而下面 `Number.isInteger` 过滤掉其余形态 ⇒ 行列号
    //    天然升序。实测变异（删掉这两处 sort）**零用例变红**，说明排序是对结果没有作用的
    //    代码，按「删掉没有作用的读法」的纪律移除。确定性仍由 JS 键序保证 —— 那才是服务端
    //    sha256 判重需要的（同一份未保存状态两次取值必须逐字相同）。
    const rows = Object.keys(cellData)
      .map(Number)
      .filter((row) => Number.isInteger(row) && row >= 0)

    const sheetLines: string[] = []
    for (const row of rows) {
      const rowCells = cellData[String(row)]
      if (!rowCells || typeof rowCells !== 'object') continue
      const cols = Object.keys(rowCells)
        .map(Number)
        .filter((col) => Number.isInteger(col) && col >= 0)
      for (const col of cols) {
        const cell = rowCells[String(col)]
        if (!cell || typeof cell !== 'object') continue
        const text = cellText(cell)
        if (!text.trim()) continue
        sheetLines.push(`${columnLetter(col)}${row + 1}=${text}`)
      }
    }
    if (sheetLines.length === 0) continue

    const header = `【${name}】`
    const block = [header, ...sheetLines].join('\n')
    if (used + block.length > maxChars) {
      const room = Math.max(0, maxChars - used - header.length - 40)
      if (room > 0) {
        lines.push(header)
        lines.push(block.slice(header.length + 1, header.length + 1 + room))
      }
      truncated = true
      break
    }
    lines.push(block)
    used += block.length + 1
  }

  if (lines.length === 0) return null
  const body = lines.join('\n')
  return truncated ? `${body}\n……（草稿超出上限，后面还有内容未纳入）` : body
}
