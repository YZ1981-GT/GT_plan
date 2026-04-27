export interface BuildImportFormDataOptions {
  files?: File[] | null
  uploadToken?: string | null
  mappingFieldName?: string
  mappingPayload?: string | null
}

export function shouldReuseImportUploadToken(uploadToken?: string | null): boolean {
  return Boolean(uploadToken)
}

export function buildImportFormData(options: BuildImportFormDataOptions): FormData {
  const formData = new FormData()
  if (!shouldReuseImportUploadToken(options.uploadToken)) {
    for (const file of options.files || []) {
      formData.append('files', file)
    }
  }
  if (options.mappingPayload) {
    formData.append(options.mappingFieldName || 'custom_mapping', options.mappingPayload)
  }
  return formData
}
