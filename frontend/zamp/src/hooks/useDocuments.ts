import { useCallback } from 'react'
import { getDocument, isFinished, listDocuments } from '../api/documents'
import type { DocumentDetail } from '../api/documents'
import { usePolling } from './usePolling'

type DocumentPage = Awaited<ReturnType<typeof listDocuments>>

const hasActiveDocuments = (page: DocumentPage) =>
  page.items.some((document) => !isFinished(document.status))

const isInProgress = (document: DocumentDetail) => !isFinished(document.status)

export function useDocuments() {
  const { data, error, refresh } = usePolling(listDocuments, hasActiveDocuments)
  return { documents: data?.items ?? [], error, refresh }
}

export function useDocument(id: string) {
  const load = useCallback(() => getDocument(id), [id])
  const { data, error } = usePolling(load, isInProgress)
  return { document: data, error }
}
