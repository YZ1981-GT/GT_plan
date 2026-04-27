import { buildImportFormData } from '@/utils/importFormData'

export interface BuildImportPreviewUrlOptions {
  basePath: string
  year?: number | null
  previewRows?: number | null
}

export interface NormalizeImportPreviewResultOptions<TPreview> {
  result: TPreview
  getUploadToken: (result: TPreview) => string | null | undefined
  getYear?: (result: TPreview) => number | null | undefined
}

export interface ResolveImportPreviewSuccessOptions<TPreview, TStage extends string> {
  result: TPreview
  nextStage: TStage
  getUploadToken: (result: TPreview) => string | null | undefined
  getYear?: (result: TPreview) => number | null | undefined
}

export interface ApplyImportPreviewSuccessOptions<TPreview, TStage extends string> {
  previewSuccess: {
    payload: TPreview
    uploadToken: string
    year: number | null
    nextStage: TStage
  }
  applyUploadToken: (uploadToken: string) => void
  applyYear?: (year: number | null) => void
  applyPayload: (payload: TPreview) => void | Promise<void>
  enterStage: (stage: TStage) => void | Promise<void>
  afterEnterStage?: (context: {
    payload: TPreview
    nextStage: TStage
    uploadToken: string
    year: number | null
  }) => void | Promise<void>
}

export function buildImportPreviewFormData(files: File[]): FormData {
  return buildImportFormData({ files, uploadToken: null })
}

export function buildImportPreviewUrl(options: BuildImportPreviewUrlOptions): string {
  const params = new URLSearchParams()
  if (options.year) params.append('year', String(options.year))
  if (options.previewRows) params.append('preview_rows', String(options.previewRows))
  const query = params.toString()
  return query ? `${options.basePath}?${query}` : options.basePath
}

export function normalizeImportPreviewResult<TPreview>(
  options: NormalizeImportPreviewResultOptions<TPreview>,
): {
  payload: TPreview
  uploadToken: string
  year: number | null
} {
  return {
    payload: options.result,
    uploadToken: options.getUploadToken(options.result) || '',
    year: options.getYear ? (options.getYear(options.result) ?? null) : null,
  }
}

export function resolveImportPreviewSuccess<TPreview, TStage extends string>(
  options: ResolveImportPreviewSuccessOptions<TPreview, TStage>,
): {
  payload: TPreview
  uploadToken: string
  year: number | null
  nextStage: TStage
} {
  const normalized = normalizeImportPreviewResult({
    result: options.result,
    getUploadToken: options.getUploadToken,
    getYear: options.getYear,
  })
  return {
    ...normalized,
    nextStage: options.nextStage,
  }
}

export async function applyImportPreviewSuccess<TPreview, TStage extends string>(
  options: ApplyImportPreviewSuccessOptions<TPreview, TStage>,
): Promise<void> {
  options.applyUploadToken(options.previewSuccess.uploadToken)
  if (options.applyYear) {
    options.applyYear(options.previewSuccess.year)
  }
  await options.applyPayload(options.previewSuccess.payload)
  await options.enterStage(options.previewSuccess.nextStage)
  if (options.afterEnterStage) {
    await options.afterEnterStage({
      payload: options.previewSuccess.payload,
      nextStage: options.previewSuccess.nextStage,
      uploadToken: options.previewSuccess.uploadToken,
      year: options.previewSuccess.year,
    })
  }
}
