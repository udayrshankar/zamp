export function formatAmount(amount: number | null | undefined, currency?: string | null): string {
  if (amount === null || amount === undefined) return '—'
  const number = amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return currency ? `${currency} ${number}` : number
}

/** "nvidia/nemotron-3.5-lightning-30b-a3b" reads as "nemotron-3.5-lightning-30b-a3b". */
export function modelName(model: string): string {
  return model.split('/').pop() ?? model
}
