import posthog, { isPostHogEnabled } from './posthog'

export const posthogLog = {
  invoiceUploadStarted(invoiceCount: number) {
    if (isPostHogEnabled) {
      posthog.logger.info('invoice upload started', { invoice_count: invoiceCount })
    }
  },

  invoiceUploadCompleted(invoiceCount: number) {
    if (isPostHogEnabled) {
      posthog.logger.info('invoice upload completed', { invoice_count: invoiceCount })
    }
  },

  invoiceUploadPartiallyFailed(failureCount: number) {
    if (isPostHogEnabled) {
      posthog.logger.warn('invoice upload partially failed', { failure_count: failureCount })
    }
  },
}
