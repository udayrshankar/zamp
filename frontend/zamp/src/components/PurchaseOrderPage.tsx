import { useCallback } from 'react'
import { getPurchaseOrder } from '../api/purchaseOrders'
import { navigate } from '../hooks/useHashRoute'
import { usePolling } from '../hooks/usePolling'
import { Icon } from './Icon'
import { PurchaseOrderForm } from './PurchaseOrderForm'

const neverPoll = () => false
const backToList = () => navigate('/purchase-orders')

function ExistingOrder({ id }: { id: string }) {
  const load = useCallback(() => getPurchaseOrder(id), [id])
  const { data, error } = usePolling(load, neverPoll)

  if (error) return <p className="alert">This purchase order couldn't be loaded. {error}</p>
  if (!data) return null
  return <PurchaseOrderForm order={data} onSaved={backToList} onDeleted={backToList} />
}

export function PurchaseOrderPage({ id }: { id: string }) {
  return (
    <div className="narrow">
      <a className="back" href="#/purchase-orders">
        <Icon name="back" />
        Purchase orders
      </a>
      {id === 'new' ? (
        <PurchaseOrderForm order={null} onSaved={backToList} onDeleted={backToList} />
      ) : (
        <ExistingOrder key={id} id={id} />
      )}
    </div>
  )
}
