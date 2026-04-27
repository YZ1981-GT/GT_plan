export interface ImportPollingFlowOptions<TStatus> {
  maxPolls: number
  onWait: () => Promise<void>
  fetchStatus: () => Promise<TStatus>
  onStatus: (status: TStatus) => Promise<void> | void
  shouldFinish: (status: TStatus) => boolean
  hasFailed: (status: TStatus) => boolean
  getFailureMessage: (status: TStatus) => string
  onSuccessStatus?: (status: TStatus) => Promise<void> | void
  onError?: (error: unknown) => Promise<void> | void
  timeoutMessage: string
}

export async function runImportPollingFlow<TStatus>(
  options: ImportPollingFlowOptions<TStatus>,
): Promise<void> {
  let done = false
  let pollCount = 0

  while (!done) {
    pollCount += 1
    if (pollCount > options.maxPolls) {
      throw new Error(options.timeoutMessage)
    }

    await options.onWait()

    try {
      const status = await options.fetchStatus()
      await options.onStatus(status)

      if (options.shouldFinish(status)) {
        done = true
        if (options.hasFailed(status)) {
          throw new Error(options.getFailureMessage(status))
        }
        if (options.onSuccessStatus) {
          await options.onSuccessStatus(status)
        }
      }
    } catch (error) {
      if (options.onError) {
        await options.onError(error)
      }
      if (error instanceof Error && error.message.includes('导入失败')) {
        throw error
      }
      done = true
    }
  }
}
