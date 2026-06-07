// A compact inline line chart for a single metric series, drawn as SVG.
// Numeric values only; non-numeric points are skipped.
export default function MetricChart({ periods, values, width = 320, height = 64 }) {
  const points = (values || [])
    .map((v, i) => [periods?.[i], Number(v)])
    .filter(([, v]) => Number.isFinite(v));
  if (points.length < 2) return null;

  const nums = points.map(([, v]) => v);
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const pad = 6;
  const stepX = (width - pad * 2) / (points.length - 1);

  const coords = points.map(([, v], i) => {
    const x = pad + i * stepX;
    const y = height - pad - ((v - min) / span) * (height - pad * 2);
    return [x, y];
  });
  const path = coords.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
      {coords.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="2.5" />
      ))}
    </svg>
  );
}
