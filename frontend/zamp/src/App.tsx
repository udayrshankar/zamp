import { useEffect, useRef, useState } from 'react'
import type { DragEvent, MouseEvent } from 'react'
import { HomePage } from './components/HomePage'
import { InvoicePage } from './components/InvoicePage'
import { PurchaseOrderPage } from './components/PurchaseOrderPage'
import { PurchaseOrdersPage } from './components/PurchaseOrdersPage'
import { navigate, useHashRoute } from './hooks/useHashRoute'
import { useInvoiceUpload } from './hooks/useInvoiceUpload'
import './App.css'

function App() {
  const path = useHashRoute()
  const [section, id] = path.split('/').filter(Boolean)
  const [dragging, setDragging] = useState(false)
  const main = useRef<HTMLElement>(null)

  const { upload, uploading, error } = useInvoiceUpload((ids) => {
    navigate(ids.length === 1 ? `/invoices/${ids[0]}` : '/')
  })

  // A new page starts at the top, with keyboard and screen reader focus on it.
  // The first load is left alone so Tab still begins at the skip link.
  const previousPath = useRef(path)
  useEffect(() => {
    if (previousPath.current === path) return
    previousPath.current = path
    window.scrollTo(0, 0)
    main.current?.focus({ preventScroll: true })
  }, [path])

  const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    void upload([...event.dataTransfer.files])
  }

  const handleDragLeave = (event: DragEvent) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
  }

  // A plain #main link would change the hash route, so this moves focus instead.
  const skipToMain = (event: MouseEvent) => {
    event.preventDefault()
    main.current?.focus()
  }

  const onPurchaseOrders = section === 'purchase-orders'

  return (
    <div
      className="app"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className={dragging ? 'drop-sky drop-sky-on' : 'drop-sky'} aria-hidden="true">
        <p>Drop it to check it.</p>
      </div>

      <a className="skip-link" href="#main" onClick={skipToMain}>
        Skip to main content
      </a>

      <header className="nav">
        <a className="brand" href="#/">
          <svg viewBox="0 0 28 18" aria-hidden="true">
            <circle cx="9" cy="9" r="8.5" />
            <circle cx="19" cy="9" r="8.5" opacity="0.55" />
          </svg>
          PO Matcher
        </a>
        <nav aria-label="Main">
          <a href="#/" aria-current={!onPurchaseOrders ? 'page' : undefined}>
            Invoices
          </a>
          <a href="#/purchase-orders" aria-current={onPurchaseOrders ? 'page' : undefined}>
            Purchase orders
          </a>
        </nav>
      </header>

      <main className="page" ref={main} tabIndex={-1}>
        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        {section === 'invoices' && id ? (
          <InvoicePage key={id} id={id} />
        ) : onPurchaseOrders && id ? (
          <PurchaseOrderPage id={id} />
        ) : onPurchaseOrders ? (
          <PurchaseOrdersPage />
        ) : (
          <HomePage uploading={uploading} onFiles={(files) => void upload(files)} />
        )}
      </main>
    </div>
  )
}

export default App
