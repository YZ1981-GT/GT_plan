export interface ResolveImportSuccessOptions<TResult, TStage extends string> {
  result: TResult
  nextStage: TStage
}

export interface ApplyImportSuccessOptions<TResult, TStage extends string> {
  success: {
    result: TResult
    nextStage: TStage
  }
  applyResult: (result: TResult) => void | Promise<void>
  enterStage: (stage: TStage) => void | Promise<void>
  afterEnterStage?: (context: {
    result: TResult
    nextStage: TStage
  }) => void | Promise<void>
}

export function resolveImportSuccess<TResult, TStage extends string>(
  options: ResolveImportSuccessOptions<TResult, TStage>,
): {
  result: TResult
  nextStage: TStage
} {
  return {
    result: options.result,
    nextStage: options.nextStage,
  }
}

export async function applyImportSuccess<TResult, TStage extends string>(
  options: ApplyImportSuccessOptions<TResult, TStage>,
): Promise<void> {
  await options.applyResult(options.success.result)
  await options.enterStage(options.success.nextStage)
  if (options.afterEnterStage) {
    await options.afterEnterStage({
      result: options.success.result,
      nextStage: options.success.nextStage,
    })
  }
}
