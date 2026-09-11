import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'

/**
 * Спільний кошик застосунку.
 *
 * Товар, доданий з будь-якого екрана, лягає сюди — не в кошик Сільпо.
 * У MCP пишемо один раз, на «Оформити». Тому додавання дешеве й оборотне:
 * гість може збирати набір по кількох екранах і передумувати.
 */
const CartContext = createContext(null)

const EMPTY = { items: [], count: 0, positions: 0, total: 0 }

export function CartProvider({ children }) {
  const [cart, setCart] = useState(EMPTY)
  const [pending, setPending] = useState({})   // product_id -> true, поки летить запит

  const reload = useCallback(async () => {
    try {
      setCart(await api.cart())
    } catch {
      // Кошик не критичний для решти екранів — мовчки лишаємо попередній стан
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  const add = useCallback(async (item) => {
    setPending((p) => ({ ...p, [item.product_id]: true }))
    try {
      setCart(await api.cartAdd(item))
    } finally {
      setPending((p) => { const n = { ...p }; delete n[item.product_id]; return n })
    }
  }, [])

  const setQuantity = useCallback(async (id, quantity) => {
    setCart(await api.cartQuantity(id, quantity))
  }, [])

  const remove = useCallback(async (id) => {
    setCart(await api.cartRemove(id))
  }, [])

  const has = useCallback(
    (productId) => cart.items.some((i) => i.product_id === productId),
    [cart.items],
  )

  return (
    <CartContext.Provider value={{ cart, add, setQuantity, remove, reload, has, pending, setCart }}>
      {children}
    </CartContext.Provider>
  )
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart треба викликати всередині <CartProvider>')
  return ctx
}
