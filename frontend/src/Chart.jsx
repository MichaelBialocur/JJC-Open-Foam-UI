export default function Chart({ title, series, xLabel, yLabel, logarithmic = false }) {
  const usable = series.map(s => ({ ...s, points: s.points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y) && (!logarithmic || p.y > 0)) }))
  const points = usable.flatMap(s => s.points)
  if (!points.length) return <div className="chart-empty">{title} · available after the solver writes results</div>
  const transform = y => logarithmic ? Math.log10(y) : y
  const x0 = Math.min(...points.map(p => p.x)), x1 = Math.max(...points.map(p => p.x))
  let y0 = Math.min(...points.map(p => transform(p.y))), y1 = Math.max(...points.map(p => transform(p.y)))
  const padding = (y1 - y0 || Math.abs(y1) || 1) * .08
  y0 -= padding; y1 += padding
  const px = x => 62 + (x - x0) / (x1 - x0 || 1) * 474
  const py = y => 214 - (transform(y) - y0) / (y1 - y0) * 170
  const tick = n => Math.abs(n) > 9999 || (n !== 0 && Math.abs(n) < .001) ? n.toExponential(1) : Number(n.toPrecision(3)).toString()
  return <figure className="chart"><figcaption>{title}</figcaption>
    <svg viewBox="0 0 570 268" role="img" aria-label={`${title}. ${xLabel}; ${yLabel}`}>
      {[0, 1, 2, 3, 4].map(i => {
        const fraction = i / 4, y = y0 + fraction * (y1 - y0), x = x0 + fraction * (x1 - x0)
        return <g key={i}><line x1="62" x2="536" y1={214 - fraction * 170} y2={214 - fraction * 170} stroke="#293746" />
          <text x="55" y={218 - fraction * 170} textAnchor="end">{logarithmic ? `10^${y.toFixed(1)}` : tick(y)}</text>
          <text x={px(x)} y="235" textAnchor="middle">{tick(x)}</text></g>
      })}
      <text x="62" y="25">{yLabel}</text><text x="298" y="260" textAnchor="middle">{xLabel}</text>
      {usable.map(s => <polyline key={s.name} fill="none" stroke={s.color} strokeWidth="2.3" strokeDasharray={s.dashed ? '5 4' : undefined} points={s.points.map(p => `${px(p.x)},${py(p.y)}`).join(' ')} />)}
    </svg>
    <div className="legend">{usable.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
  </figure>
}
