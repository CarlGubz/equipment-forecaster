import type { AnalyzeSummary, Prediction } from "../types";
import { daysLabel, statusLabel } from "../utils";

interface Props {
  predictions: Prediction[];
  summary: AnalyzeSummary;
  asOf: string;
}

export default function Predictions({ predictions, summary, asOf }: Props) {
  return (
    <div>
      <div className="cards">
        <SummaryCard label="Parts tracked" value={predictions.length} tone="neutral" />
        <SummaryCard label="Overdue" value={summary.overdue} tone="overdue" />
        <SummaryCard label="Due soon (≤21d)" value={summary.due_soon} tone="due_soon" />
        <SummaryCard label="As of" value={asOf} tone="neutral" small />
      </div>

      <div className="table-wrap">
        <table className="data-table pred-table">
          <thead>
            <tr>
              <th>Priority</th>
              <th>Part</th>
              <th>Equipment</th>
              <th>Last ordered</th>
              <th>Predicted next order</th>
              <th>Timing</th>
              <th>Cycle</th>
              <th>Qty</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {predictions.map((p, i) => (
              <tr key={p.part_number + i} className={`row-${p.status}`} title={p.rationale}>
                <td>
                  <span className={`badge badge-${p.status}`}>{statusLabel(p.status)}</span>
                </td>
                <td>
                  <div className="part-cell">
                    <span className="mono strong">{p.part_number}</span>
                    <span className="muted small">{p.part_name}</span>
                  </div>
                </td>
                <td className="small">{p.equipment || "—"}</td>
                <td className="mono small">{p.last_order_date}</td>
                <td className="mono strong">{p.predicted_next_order_date ?? "—"}</td>
                <td className={p.days_until_due !== null && p.days_until_due < 0 ? "danger" : ""}>
                  {daysLabel(p.days_until_due)}
                </td>
                <td className="small">
                  {p.avg_interval_days ? `~${Math.round(p.avg_interval_days)}d` : "—"}
                </td>
                <td className="small">{p.suggested_quantity}</td>
                <td>
                  <div className="conf">
                    <div className="conf-bar">
                      <div className="conf-fill" style={{ width: `${p.confidence * 100}%` }} />
                    </div>
                    <span className="small">{Math.round(p.confidence * 100)}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Hover a row to see the reasoning behind each prediction.</p>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
  small,
}: {
  label: string;
  value: string | number;
  tone: string;
  small?: boolean;
}) {
  return (
    <div className={`card card-${tone}`}>
      <div className="card-label">{label}</div>
      <div className={`card-value ${small ? "card-value-sm" : ""}`}>{value}</div>
    </div>
  );
}
