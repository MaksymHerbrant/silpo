import { useEffect } from 'react'

/**
 * Модалка деталізації: клік по картці — і тут уся глибина по позиції.
 * Головний екран лишається чистим, а подробиці не губляться.
 */
export default function Sheet({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sheet-head">
          <span className="sheet-grip" aria-hidden="true" />
          <div className="sheet-title-row">
            <h2>{title}</h2>
            <button onClick={onClose} aria-label="Закрити">✕</button>
          </div>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  )
}
