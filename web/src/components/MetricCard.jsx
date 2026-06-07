import Citations from "./Citations.jsx";
import MetricChart from "./MetricChart.jsx";

function formatValue(v, unit) {
  if (!Number.isFinite(Number(v))) return v;
  const n = Number(v);
  if (unit === "USD") return "$" + n.toLocaleString();
  return n.toLocaleString();
}

// A quantitative time-series extracted from memos, with an inline chart.
export default function MetricCard({ metric }) {
  const { periods = [], data_values = [], unit } = metric;
  return (
    <article className="panel metric-card">
      <header className="panel-head">
        <h3>{metric.series_name}</h3>
        {unit && <span className="unit">{unit}</span>}
      </header>
      {metric.description && <p className="signal">{metric.description}</p>}
      <div className="metric-chart-wrap">
        <MetricChart periods={periods} values={data_values} />
      </div>
      <div className="metric-table-wrap">
        <table className="metric-table">
          <tbody>
            <tr>
              {periods.map((p, i) => (
                <th key={i}>{p}</th>
              ))}
            </tr>
            <tr>
              {data_values.map((v, i) => (
                <td key={i}>{formatValue(v, unit)}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <Citations ids={metric.source_memo_ids} />
    </article>
  );
}
