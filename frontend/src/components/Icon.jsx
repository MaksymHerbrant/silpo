/**
 * Один набір лінійних іконок замість емодзі: однакова товщина лінії,
 * однаковий розмір, колір — від тексту поруч. Емодзі виглядали по-різному
 * на iOS і Android і сперечались із кольором бренду.
 */
const PATHS = {
  home: 'M3 11.5 12 4l9 7.5M5 10v10h5v-6h4v6h5V10',
  tag: 'M3 12V4h8l9 9-8 8-9-9Z M7.5 8h.01',
  basket: 'M3 10h18l-1.5 10h-15L3 10Z M8 10l3-6M16 10l-3-6M9 14v3M15 14v3',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  dots: 'M5 12h.01M12 12h.01M19 12h.01',
  bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2Z M10 21h4',
  bellOff: 'M6 16V11a6 6 0 0 1 9.5-4.9M18 13v3l2 2H4l2-2 M10 21h4M3 3l18 18',
  check: 'M5 12.5 10 17 19 7',
  warn: 'M12 4 2.5 20h19L12 4Z M12 10v4M12 17h.01',
  lock: 'M6 11h12v9H6v-9Z M9 11V8a3 3 0 0 1 6 0v3',
  leaf: 'M5 19c0-8 5-13 14-13-1 9-6 14-14 13Z M5 19l8-8',
  plug: 'M9 3v5M15 3v5M6 8h12l-1 5a5 5 0 0 1-10 0L6 8Z M12 18v3',
  cart: 'M3 4h2l2.5 11h11L21 7H7 M9 20h.01M17 20h.01',
  block: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M6 6l12 12',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z M12 12h.01',
  spark: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1',
}

export default function Icon({ name, size = 20, className = '', ...rest }) {
  const d = PATHS[name]
  if (!d) return null
  return (
    <svg
      className={`ico ${className}`.trim()}
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.75"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" {...rest}
    >
      <path d={d} />
    </svg>
  )
}
