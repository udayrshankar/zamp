export function formatAmount(amount: number | null | undefined, currency?: string | null): string {
  if (amount === null || amount === undefined) return '—'
  const number = amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return currency ? `${currency} ${number}` : number
}
