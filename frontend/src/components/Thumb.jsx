/** Мініатюра товару. Без фото — нейтральна заглушка, а не порожнє місце. */
export default function Thumb({ src, size = 44 }) {
  const style = { width: size, height: size }
  return src
    ? <img className="thumb" src={src} alt="" loading="lazy" style={style} />
    : <span className="thumb ph" style={style} aria-hidden="true">🛒</span>
}
