/**
 * utils/knowledgeUpload —— 知识库上传的纯逻辑
 *
 * spec knowledge-upload-robustness-and-consumer-wiring（Requirement 4 / 5）
 *
 * 回归背景（2026-09-30 现读 KnowledgeBase.vue）：
 *  ① 拖拽文件夹时 `readEntries()` 只调一次 —— Chromium 每次最多返回 100 条，其余文件静默丢失；
 *  ② `entry.file()` 得到的 File 没有 webkitRelativePath —— 子文件夹结构被压平到目标根部；
 *  ③ 上传失败只报「N 失败」，原因只在控制台；后端 200 + failed[] 的逐文件失败被当成「成功 0 个」。
 */
import { describe, it, expect } from 'vitest'
import {
  buildUploadSummary,
  collectFromEntries,
  entriesFromDataTransfer,
  extractErrorReason,
  isOcrEligible,
  isOcrInProgress,
  isSystemJunkName,
  isSystemJunkPath,
  noTextHint,
  parseUploadResponse,
  readAllEntries,
  type FsEntryLike,
} from '../knowledgeUpload'

// ─── FileSystemEntry 替身：readEntries 按 Chromium 行为每次最多给 100 条 ───

const CHROMIUM_BATCH = 100

function fileEntry(fullPath: string, opts: { fail?: boolean } = {}): FsEntryLike {
  const name = fullPath.split('/').pop()!
  return {
    isFile: true,
    isDirectory: false,
    name,
    fullPath,
    file: (ok, err) => (opts.fail ? err?.(new Error('read failed')) : ok(new File([name], name))),
  }
}

function dirEntry(fullPath: string, children: FsEntryLike[], opts: { failRead?: boolean } = {}): FsEntryLike & { readCalls: number } {
  const entry: any = { isFile: false, isDirectory: true, name: fullPath.split('/').pop()!, fullPath, readCalls: 0 }
  entry.createReader = () => {
    let offset = 0
    return {
      readEntries: (ok: (e: FsEntryLike[]) => void, err?: (e: unknown) => void) => {
        entry.readCalls += 1
        if (opts.failRead) {
          err?.(new Error('dir read failed'))
          return
        }
        const batch = children.slice(offset, offset + CHROMIUM_BATCH)
        offset += batch.length
        ok(batch)
      },
    }
  }
  return entry
}

describe('readAllEntries / collectFromEntries', () => {
  it('250 个条目的目录全部取回（readEntries 必须反复调用直到返回空）', async () => {
    const files = Array.from({ length: 250 }, (_, i) => fileEntry(`/底稿/f${i}.txt`))
    const dir = dirEntry('/底稿', files)

    const { files: got, failed } = await collectFromEntries([dir])

    expect(got).toHaveLength(250)
    expect(failed).toEqual([])
    // 100 + 100 + 50 + 最后一次返回空 = 4 次；只调 1 次的旧实现只能拿到 100 个
    expect(dir.readCalls).toBe(4)
  })

  it('readAllEntries 恰好整批（100）时也读到空为止，不多不少', async () => {
    const dir = dirEntry('/x', Array.from({ length: 100 }, (_, i) => fileEntry(`/x/${i}.md`)))
    const all = await readAllEntries(dir.createReader!())
    expect(all).toHaveLength(100)
    expect(dir.readCalls).toBe(2)
  })

  it('保留嵌套层级：相对路径与 webkitRelativePath 同形（无前导 /）', async () => {
    const tree = dirEntry('/审计资料', [
      fileEntry('/审计资料/总览.docx'),
      dirEntry('/审计资料/函证', [
        fileEntry('/审计资料/函证/回函.pdf'),
        dirEntry('/审计资料/函证/银行', [fileEntry('/审计资料/函证/银行/工行.pdf')]),
      ]),
    ])
    const { files } = await collectFromEntries([tree, fileEntry('/单独.txt')])
    expect(files.map((f) => f.relativePath)).toEqual([
      '审计资料/总览.docx',
      '审计资料/函证/回函.pdf',
      '审计资料/函证/银行/工行.pdf',
      '单独.txt',
    ])
    expect(files[2].file.name).toBe('工行.pdf')
  })

  it('读取失败的文件与目录记入 failed，不中断其余条目', async () => {
    const tree = dirEntry('/a', [
      fileEntry('/a/ok.txt'),
      fileEntry('/a/bad.txt', { fail: true }),
      dirEntry('/a/locked', [fileEntry('/a/locked/x.txt')], { failRead: true }),
      fileEntry('/a/ok2.txt'),
    ])
    const { files, failed } = await collectFromEntries([tree])
    expect(files.map((f) => f.relativePath)).toEqual(['a/ok.txt', 'a/ok2.txt'])
    expect(failed).toEqual(['a/bad.txt', 'a/locked/'])
  })

  it('跳过系统临时文件与 __MACOSX 目录并计数', async () => {
    const tree = dirEntry('/d', [
      fileEntry('/d/报告.docx'),
      fileEntry('/d/~$报告.docx'),
      fileEntry('/d/.DS_Store'),
      fileEntry('/d/Thumbs.db'),
      dirEntry('/d/__MACOSX', [fileEntry('/d/__MACOSX/._报告.docx')]),
    ])
    const { files, skipped } = await collectFromEntries([tree])
    expect(files.map((f) => f.relativePath)).toEqual(['d/报告.docx'])
    expect(skipped).toBe(4)
  })
})

describe('entriesFromDataTransfer', () => {
  it('同步取出条目，跳过拿不到条目的项', () => {
    const e1 = fileEntry('/a.txt')
    const dt = {
      items: [
        { webkitGetAsEntry: () => e1 },
        { webkitGetAsEntry: () => null },
        {},
      ],
    } as unknown as DataTransfer
    expect(entriesFromDataTransfer(dt)).toEqual([e1])
    expect(entriesFromDataTransfer(null)).toEqual([])
  })
})

describe('isSystemJunkName / isSystemJunkPath', () => {
  it.each([
    ['~$底稿.xlsx', true],
    ['.~lock.底稿.xlsx#', true],
    ['._底稿.xlsx', true],
    ['.DS_Store', true],
    ['thumbs.db', true],
    ['desktop.ini', true],
    ['底稿.xlsx', false],
    ['~底稿.xlsx', false],
    ['.gitkeep', false],
  ])('%s → %s', (name, expected) => {
    expect(isSystemJunkName(name)).toBe(expected)
  })

  it('路径形态：__MACOSX 下的一切与末段为临时文件都算', () => {
    expect(isSystemJunkPath('资料/__MACOSX/x.pdf')).toBe(true)
    expect(isSystemJunkPath('资料/~$合同.docx')).toBe(true)
    expect(isSystemJunkPath('资料/合同.docx')).toBe(false)
    expect(isSystemJunkPath('')).toBe(false)
  })
})

// ─── 单文件上传结果 ─────────────────────────────────────────────────────────

const ok = (files: unknown[], failed: unknown[] = []) =>
  JSON.stringify({ code: 200, message: 'success', data: { uploaded: files.length, files, failed, folder_id: 'f' } })

describe('parseUploadResponse', () => {
  it('成功且抽到正文', () => {
    expect(parseUploadResponse(200, ok([{ id: 'd1', text_extracted: true, ocr_queued: false }]))).toEqual({
      ok: true, reason: '', textExtracted: true, ocrQueued: false,
    })
  })

  it('成功但未抽到正文、已交给后台识别（扫描件）', () => {
    expect(parseUploadResponse(200, ok([{ id: 'd1', text_extracted: false, ocr_queued: true }]))).toEqual({
      ok: true, reason: '', textExtracted: false, ocrQueued: true,
    })
  })

  it('成功但未抽到正文、不能识别（空白 txt 等）', () => {
    const out = parseUploadResponse(200, ok([{ id: 'd1', text_extracted: false, ocr_queued: false }]))
    expect([out.textExtracted, out.ocrQueued]).toEqual([false, false])
  })

  it('旧后端无 text_extracted / ocr_queued 字段时不误报', () => {
    const out = parseUploadResponse(200, ok([{ id: 'd1' }]))
    expect([out.textExtracted, out.ocrQueued]).toEqual([true, false])
  })

  it('200 + failed[]：逐文件失败带后端原因（旧实现只当成「成功 0 个」）', () => {
    const out = parseUploadResponse(200, ok([], [{ filename: 'a.txt', reason: '文件内容含无法存储的字符' }]))
    expect(out).toEqual({ ok: false, reason: '文件内容含无法存储的字符', textExtracted: false })
  })

  it('200 但既无 files 也无 failed：给通用原因', () => {
    expect(parseUploadResponse(200, ok([])).reason).toBe('文件未能保存，请重试')
  })

  it('错误状态码：取平台错误体 message；401 / 413 / 未知给中文兜底', () => {
    expect(parseUploadResponse(403, JSON.stringify({ code: 403, message: '只读账号不能修改知识库' })).reason)
      .toBe('只读账号不能修改知识库')
    expect(parseUploadResponse(413, JSON.stringify({ code: 413, message: '请求体过大，上限 850MB' })).reason)
      .toBe('请求体过大，上限 850MB')
    expect(parseUploadResponse(413, '').reason).toBe('文件过大，超出上传上限')
    expect(parseUploadResponse(401, '').reason).toContain('登录已过期')
    expect(parseUploadResponse(502, '<html>Bad Gateway</html>').reason).toBe('上传失败（HTTP 502）')
  })

  it('2xx 但响应不是 JSON', () => {
    expect(parseUploadResponse(200, 'not json').ok).toBe(false)
  })
})

describe('extractErrorReason', () => {
  it.each([
    [JSON.stringify({ message: '  原因A ' }), '原因A'],
    [JSON.stringify({ detail: '原因B' }), '原因B'],
    [JSON.stringify({ detail: { message: '原因C' } }), '原因C'],
    [JSON.stringify({ detail: [{ msg: 'field required' }] }), ''],
    ['<html/>', ''],
    ['', ''],
  ])('%s → %s', (text, expected) => {
    expect(extractErrorReason(text)).toBe(expected)
  })
})

// ─── 没有正文：区分扫描件（R4.2）与后台识别状态（dsh-kb-ocr Req 5.7） ─────────────

describe('isOcrEligible / noTextHint / isOcrInProgress', () => {
  it.each([
    ['扫描件.pdf', undefined, true],
    ['扫描件.PDF', undefined, true],
    ['目录/扫描件.pdf', undefined, true],
    ['无后缀名', 'pdf', true], // file_type 优先于文件名
    ['截图.png', undefined, true], // 图片与后端 OCR_SUFFIXES 同一份
    ['照片.JPEG', undefined, true],
    ['传真.tif', 'tif', true],
    ['名字像pdf.txt', 'txt', false],
    ['空白.txt', undefined, false],
    ['审计报告.final-reviewed-by-partner-v2', null, false], // 后端 file_type 置空的超长扩展名
    ['.pdf', undefined, false], // 点开头的隐藏文件没有扩展名
    ['图片.docx', 'docx', false],
  ])('%s (file_type=%s) → %s', (name, fileType, expected) => {
    expect(isOcrEligible(name, fileType as string | null | undefined)).toBe(expected)
  })

  it('排队 / 识别中：进度提示、不能重复发起识别', () => {
    for (const [status, label] of [['pending', '⏳ 排队识别中…'], ['running', '⏳ 正在识别文字…']]) {
      const hint = noTextHint('回函.pdf', 'pdf', status)
      expect(hint).toMatchObject({ label, tone: 'progress', retryable: false })
      expect(hint.title).toContain('自动刷新')
    }
  })

  it('识别失败：带后端中文原因、可重新识别；没有原因时如实说未知', () => {
    const hint = noTextHint('回函.pdf', 'pdf', 'failed', '远程 OCR 认证失败，请检查 API Key')
    expect(hint).toMatchObject({ label: '⚠ 识别失败，AI 无法引用', tone: 'warning', retryable: true })
    expect(hint.title).toBe('识别失败：远程 OCR 认证失败，请检查 API Key。可点「重新识别」再试')
    expect(noTextHint('回函.pdf', 'pdf', 'failed', '  ').title).toContain('原因未知')
  })

  it('识别完成但没有文字：可重新识别', () => {
    expect(noTextHint('空白页.pdf', 'pdf', 'empty')).toMatchObject({
      label: '⚠ 未识别出文字，AI 无法引用', tone: 'warning', retryable: true,
    })
  })

  it('存量扫描件（没有识别记录）可交给后台识别；其余类型不提扫描件、不给重新识别', () => {
    const scan = noTextHint('合同扫描.pdf', 'pdf', null)
    const blank = noTextHint('空白.txt', 'txt', null)
    expect(scan).toMatchObject({ label: '⚠ 未提取到正文（扫描件），AI 无法引用', retryable: true })
    expect(scan.title).toContain('重新识别')
    expect(blank).toMatchObject({ label: '⚠ 未提取到正文，AI 无法引用', retryable: false })
    expect(`${blank.label}${blank.title}`).not.toMatch(/OCR|扫描件|识别/)
  })

  it('任何状态都不再出现旧文案「需开启 OCR」（用户无处可开）', () => {
    for (const status of [null, 'pending', 'running', 'failed', 'empty', 'done']) {
      for (const [name, type] of [['a.pdf', 'pdf'], ['b.txt', 'txt']]) {
        const hint = noTextHint(name, type, status, 'x')
        expect(`${hint.label}${hint.title}`).not.toContain('开启 OCR')
      }
    }
  })

  it('isOcrInProgress 只认排队与识别中', () => {
    expect(['pending', 'running', 'done', 'empty', 'failed', null, undefined].map((s) => isOcrInProgress(s)))
      .toEqual([true, true, false, false, false, false, false])
  })
})

// ─── 结束汇总 ───────────────────────────────────────────────────────────────

describe('buildUploadSummary', () => {
  it('全部顺利：success 且无明细', () => {
    expect(buildUploadSummary({ fileCount: 3, failures: [], noText: [] })).toEqual({
      level: 'success', title: '上传完成：3 个文件', lines: [],
    })
  })

  it('失败逐条列出原因，超出上限时折叠', () => {
    const failures = Array.from({ length: 7 }, (_, i) => ({ name: `f${i}.txt`, reason: '原因' }))
    const s = buildUploadSummary({ fileCount: 10, failures, noText: [], maxItems: 5 })
    expect(s.level).toBe('warning')
    expect(s.title).toBe('上传完成：3 成功，7 失败')
    expect(s.lines.slice(0, 5)).toEqual(Array.from({ length: 5 }, (_, i) => `✗ f${i}.txt：原因`))
    expect(s.lines[5]).toBe('……另有 2 个文件上传失败')
  })

  it('扫描件已交给后台识别：仍是 success，告知进度去向', () => {
    const s = buildUploadSummary({ fileCount: 2, failures: [], noText: [], ocrQueued: ['函证/回函.pdf'] })
    expect(s).toEqual({
      level: 'success',
      title: '上传完成：2 个文件',
      lines: ['⏳ 扫描件已交给后台识别文字，完成后 AI 即可引用（进度见文档列表）：函证/回函.pdf'],
    })
  })

  it('旧后端（回执无 ocr_queued）的无正文扫描件：warning，指向「重新识别」', () => {
    const s = buildUploadSummary({ fileCount: 2, failures: [], noText: ['扫描件.pdf'] })
    expect(s.level).toBe('warning')
    expect(s.title).toBe('上传完成：2 个文件')
    expect(s.lines).toEqual(['⚠ 未提取到正文 · 可在文档列表点「重新识别」交给后台识别（AI 暂无法引用）：扫描件.pdf'])
  })

  // R4.2「区分扫描件」：空白 txt / 无扩展名文件不能说成扫描件
  // （2026-10-01 Playwright 实测：旧文案对空白 txt 与「扩展名」超长的文件也说「扫描件需开启 OCR」）
  it('排队识别 / 可识别未排队 / 不能识别三类分行，不出现「开启 OCR」', () => {
    const s = buildUploadSummary({
      fileCount: 5, failures: [],
      ocrQueued: ['回函.pdf'],
      noText: ['资料/扫描件.PDF', '空白.txt', '审计报告.final-reviewed-by-partner-v2', '图片.docx'],
    })
    expect(s.level).toBe('warning')
    expect(s.lines).toEqual([
      '⏳ 扫描件已交给后台识别文字，完成后 AI 即可引用（进度见文档列表）：回函.pdf',
      '⚠ 未提取到正文 · 可在文档列表点「重新识别」交给后台识别（AI 暂无法引用）：资料/扫描件.PDF',
      '⚠ 未提取到正文 · 文件为空、只含图片或该类型不支持提取文字（AI 无法引用）：空白.txt、审计报告.final-reviewed-by-partner-v2、图片.docx',
    ])
    expect(s.lines.join('')).not.toContain('开启 OCR')
    expect(s.lines[2]).not.toMatch(/OCR|识别/)
  })

  it('每类超出上限时各自折叠', () => {
    const scans = Array.from({ length: 7 }, (_, i) => `s${i}.pdf`)
    const s = buildUploadSummary({ fileCount: 9, failures: [], noText: ['空白.txt'], ocrQueued: scans, maxItems: 5 })
    expect(s.lines[0]).toBe('⏳ 扫描件已交给后台识别文字，完成后 AI 即可引用（进度见文档列表）：s0.pdf、s1.pdf、s2.pdf、s3.pdf、s4.pdf 等 7 个')
    expect(s.lines[1]).toContain('：空白.txt')
  })

  it('子文件夹失败与跳过的临时文件都有说明', () => {
    const s = buildUploadSummary({ fileCount: 1, failures: [], noText: [], folderFailures: ['a/b'], skipped: 2 })
    expect(s.level).toBe('warning')
    expect(s.lines).toEqual([
      '⚠ 子文件夹创建失败，其中文件已上传到上一级：a/b',
      '已跳过 2 个系统临时文件（如 ~$ 开头的 Office 锁文件）',
    ])
  })

  it('只有跳过的临时文件时仍是 success（不是问题）', () => {
    expect(buildUploadSummary({ fileCount: 1, failures: [], noText: [], skipped: 1 }).level).toBe('success')
  })
})
