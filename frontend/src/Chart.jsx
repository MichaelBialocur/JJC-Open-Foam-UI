import { niceScale, logScale, tickLabel } from './axes'

export default function Chart({ title, series, xLabel, yLabel, logarithmic = false, xDomain, zeroBaseline = true }) {
  const usable = series.map(s => ({ ...s, points: s.points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y) && (!logarithmic || p.y > 0)) }))
  const points = usable.flatMap(s => s.points)
  if (!points.length) return <div className="chart-empty">{title} · available after the solver writes results</div>
  const transform = y => logarithmic ? Math.log10(y) : y
  const xs = niceScale(xDomain?.[0] ?? Math.min(...points.map(p => p.x)), xDomain?.[1] ?? Math.max(...points.map(p => p.x)))
  const ymin = Math.min(...points.map(p => p.y)), ymax = Math.max(...points.map(p => p.y))
  const ys = logarithmic ? logScale(ymin, ymax) : niceScale(ymin, ymax, { includeZero: zeroBaseline })
  const px = x => 74 + (x - xs.min) / (xs.max - xs.min) * 458
  const py = y => 214 - (transform(y) - ys.min) / (ys.max - ys.min) * 170
  return <figure className="chart"><figcaption>{title}</figcaption>
    <svg viewBox="0 0 570 268" role="img" aria-label={`${title}. ${xLabel}; ${yLabel}`}>
      {ys.ticks.map(y => <g key={y}><line x1="74" x2="532" y1={py(y)} y2={py(y)} stroke={y === 0 ? '#c5d9e8' : '#293746'} strokeWidth={y === 0 ? 1.6 : 1} />
        <text x="65" y={py(y)+4} textAnchor="end" className={y === 0 ? 'zero-tick' : ''}>{logarithmic ? `10${superscript(Math.round(Math.log10(y)))}` : tickLabel(y)}</text></g>)}
      {xs.ticks.map(x => <g key={x}><line x1={px(x)} x2={px(x)} y1="214" y2="220" stroke="#71879b" />
        <text x={px(x)} y="238" textAnchor="middle">{tickLabel(x)}</text></g>)}
      <line x1="74" x2="74" y1="44" y2="214" stroke="#71879b" />
      <text x="74" y="25">{yLabel}</text><text x="303" y="263" textAnchor="middle">{xLabel}</text>
      {usable.map(s => <polyline key={s.name} fill="none" stroke={s.color} strokeWidth="2.3" strokeDasharray={s.dashed ? '5 4' : undefined} points={s.points.map(p => `${px(p.x)},${py(p.y)}`).join(' ')} />)}
    </svg>
    <div className="legend">{usable.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
  </figure>
}

function superscript(value) { return String(value).split('').map(c => ({ '-': '⁻', '0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹' }[c])).join('') }
