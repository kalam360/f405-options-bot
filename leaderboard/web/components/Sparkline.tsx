// A dependency-free equity sparkline. Pure SVG, rendered on the server — no
// client JavaScript, no charting library. Green if the series ended up, red down.

export function Sparkline({
  data,
  width = 140,
  height = 36,
}: {
  data: number[];
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) {
    return <span className="muted">no data yet</span>;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1; // avoid divide-by-zero on a flat line
  const pad = 2;

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (width - 2 * pad);
    // SVG y grows downward, so invert.
    const y = pad + (1 - (v - min) / span) * (height - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const up = data[data.length - 1] >= data[0];
  const stroke = up ? "#22c55e" : "#ef4444";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="equity sparkline"
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
