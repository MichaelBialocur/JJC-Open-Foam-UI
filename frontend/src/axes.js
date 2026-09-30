// Decimal steps stay on the familiar 1, 2, 5, 10 sequence at any magnitude.
export function niceScale(min, max, { includeZero = false, intervals = 5 } = {}) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1, step: .2, ticks: [0, .2, .4, .6, .8, 1] }
  if (includeZero) { min = Math.min(0, min); max = Math.max(0, max) }
  if (min === max) {
    const span = Math.abs(min) * .1 || 1
    min = min >= 0 ? Math.max(0, min - span) : min - span
    max += span
  }
  const raw = (max - min) / intervals
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].find(n => n * power >= raw * (1 - 1e-12)) * power
  const first = Math.floor(min / step + 1e-10), last = Math.ceil(max / step - 1e-10)
  const clean = n => Number(n.toPrecision(12)) || 0
  return { min: clean(first * step), max: clean(last * step), step,
    ticks: Array.from({ length: last - first + 1 }, (_, i) => clean((first + i) * step)) }
}

export function logScale(min, max) {
  let lo = Math.floor(Math.log10(min)), hi = Math.ceil(Math.log10(max))
  if (lo === hi) { lo--; hi++ }
  const step = Math.max(1, Math.ceil((hi - lo) / 6))
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step
  return { min: lo, max: hi, ticks: Array.from({ length: (hi - lo) / step + 1 }, (_, i) => 10 ** (lo + i * step)) }
}

export function tickLabel(value) {
  if (value === 0) return '0'
  if (Math.abs(value) >= 1e6 || Math.abs(value) < .0001) return value.toExponential().replace('e+', 'e')
  return Number(value.toPrecision(10)).toLocaleString('en', { maximumFractionDigits: 10 })
}
