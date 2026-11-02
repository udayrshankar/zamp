import { listAllPurchaseOrders } from '../api/purchaseOrders'
import { usePolling } from '../hooks/usePolling'
import { poSubtitle } from '../poSearch'

const neverPoll = () => false

export function PurchaseOrdersPage() {
  const { data, error } = usePolling(listAllPurchaseOrders, neverPoll)

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Purchase orders</h1>
          <p className="lead">Invoices are checked against these.</p>
        </div>
        <a className="button button-solid" href="#/purchase-orders/new">
          Add a purchase order
        </a>
      </header>

      {error && (
        <p className="alert" role="alert">
          The list couldn't be loaded. {error}
        </p>
      )}
      {data?.length === 0 && <p className="hint">Add your first purchase order to start matching.</p>}

      <ul className="rows">
        {data?.map((order) => (
          <li key={order.id}>
            <a className="row row-plain" href={`#/purchase-orders/${order.id}`}>
              <strong>{order.po_number}</strong>
              <span className="row-sentence">{poSubtitle(order)}</span>
            </a>
          </li>
        ))}
      </ul>
    </>
  )
}
