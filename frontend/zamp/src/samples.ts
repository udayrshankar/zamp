import type { Decision } from './api/runs'

export const GITHUB_URL = 'https://github.com/udayrshankar/Zamp-Assignment'

/** Built into the web image from backend/tests/fixtures/iitm. */
export const SAMPLES_ZIP = '/samples/iitm-test-invoices.zip'

export interface Sample {
  file: string
  tests: string
  quality: string
  expected: Decision
  note?: string
}

export interface SampleGroup {
  folder: 'correct' | 'incorrect'
  title: string
  summary: string
  samples: Sample[]
}

// Mirrors backend/tests/fixtures/iitm/README.md. Their POs are already on file.
export const SAMPLE_GROUPS: SampleGroup[] = [
  {
    folder: 'correct',
    title: 'Should be accepted',
    summary: 'Each matches its PO. They test how well the invoice is read, from clean PDFs to phone photos.',
    samples: [
      { file: '01-clear-digital.pdf', tests: 'Matches the PO exactly', quality: 'Clear digital PDF', expected: 'accept' },
      { file: '02-clean-scan-with-freight.pdf', tests: 'Freight and CGST/SGST add up to the PO', quality: 'Clean scan', expected: 'accept' },
      { file: '03-skewed-scan.pdf', tests: 'Exact match', quality: 'Skewed scan, 3.5°', expected: 'accept' },
      { file: '04-blurry-scan.pdf', tests: 'Exact match', quality: 'Blurry scan', expected: 'accept' },
      { file: '05-noisy-scan.pdf', tests: 'Exact match', quality: 'Noisy, speckled scan', expected: 'accept' },
      { file: '06-fax-copy.pdf', tests: 'Exact match', quality: 'Low-resolution fax', expected: 'accept' },
      { file: '07-phone-photo.pdf', tests: 'Exact match', quality: 'Angled phone photo, uneven light', expected: 'accept' },
      { file: '08-faint-scan.pdf', tests: 'PO quoted only indirectly, without the IITM prefix', quality: 'Faint, pale scan', expected: 'accept' },
      { file: '09-rotated-scan.pdf', tests: 'Exact match', quality: 'Scanned sideways, 90°', expected: 'accept' },
      { file: '10-two-page-digital.pdf', tests: 'A 12-item, two-page invoice matches the PO', quality: 'Clear digital, 2 pages', expected: 'accept' },
      { file: '11-split-bill-first-month.pdf', tests: 'First monthly bill on a six-month PO', quality: 'Clear digital PDF', expected: 'accept' },
    ],
  },
  {
    folder: 'incorrect',
    title: 'Should be caught',
    summary: 'Each has something wrong that a person needs to see. Run the accepted set first, since 06 and 09 build on it.',
    samples: [
      { file: '01-clear-digital-overbilled.pdf', tests: 'About 15% over the PO', quality: 'Clear digital PDF', expected: 'reject' },
      { file: '02-clean-scan-wrong-vendor.pdf', tests: 'A different company quotes a real PO', quality: 'Clean scan', expected: 'reject' },
      { file: '03-skewed-scan-5pct-over.pdf', tests: 'About 5% over the PO', quality: 'Skewed scan, 3.5°', expected: 'review' },
      { file: '04-blurry-scan-bad-maths.pdf', tests: "Line items don't add up to the taxable value", quality: 'Blurry scan', expected: 'review' },
      { file: '05-noisy-scan-extra-item.pdf', tests: "Bills an item that isn't on the PO", quality: 'Noisy, speckled scan', expected: 'review' },
      { file: '06-fax-duplicate-of-correct-01.pdf', tests: 'A re-sent copy of accepted 01', quality: 'Low-resolution fax', expected: 'reject' },
      { file: '07-phone-photo-no-invoice-number.pdf', tests: 'The invoice number is missing', quality: 'Angled phone photo', expected: 'review' },
      { file: '08-faint-unknown-po.pdf', tests: "Quotes a PO that doesn't exist", quality: 'Faint, pale scan', expected: 'review', note: 'It pauses to ask for the PO. Choose “There is no PO”.' },
      { file: '09-rotated-split-bill-too-far.pdf', tests: 'With accepted 11, takes the six-month PO over its limit', quality: 'Scanned sideways, 90°', expected: 'reject' },
      { file: '10-two-page-wrong-currency.pdf', tests: 'Billed in USD against an INR PO', quality: 'Clear digital, 2 pages', expected: 'review' },
      { file: '11-password-protected.pdf', tests: "Can't be opened, so a person must look", quality: 'Password-protected PDF', expected: 'review' },
    ],
  },
]

export const SAMPLE_COUNT = SAMPLE_GROUPS.reduce((total, group) => total + group.samples.length, 0)

export function sampleUrl(folder: SampleGroup['folder'], file: string) {
  return `/samples/${folder}/${file}`
}
