export interface BuildImportJobUrlOptions {
  basePath: string
  year?: number | null
  uploadToken?: string | null
  customMapping?: string | null
}

export function buildImportJobUrl(options: BuildImportJobUrlOptions): string {
  const params = new URLSearchParams()
  if (options.year) params.append('year', String(options.year))
  if (options.uploadToken) params.append('upload_token', options.uploadToken)
  if (options.customMapping) params.append('custom_mapping', options.customMapping)
  const query = params.toString()
  return query ? `${options.basePath}?${query}` : options.basePath
}

export async function fetchImportQueueStatus<TStatus>(
  request: () => Promise<TStatus>,
): Promise<TStatus> {
  return request()
}
