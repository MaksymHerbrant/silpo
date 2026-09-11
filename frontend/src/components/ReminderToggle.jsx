/** Перемикач нагадування прямо в рядку — окремий екран налаштувань зайвий. */
export default function ReminderToggle({ on, busy, onToggle }) {
  return (
    <button
      className={`switch${on ? ' on' : ''}`}
      role="switch"
      aria-checked={on}
      aria-label={on ? 'Вимкнути нагадування' : 'Увімкнути нагадування'}
      disabled={busy}
      onClick={(e) => { e.stopPropagation(); onToggle(!on) }}
    >
      <span className="knob" />
    </button>
  )
}
