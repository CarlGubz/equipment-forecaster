import type { SchemaResult } from "../types";

const REQUIRED = new Set(["order_date", "part_number"]);

export default function SchemaView({ schema }: { schema: SchemaResult }) {
  const entries = Object.entries(schema.mapping);
  return (
    <div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Canonical field</th>
              <th>Mapped from (your column)</th>
              <th>How</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([canon, m]) => (
              <tr key={canon}>
                <td>
                  <span className="mono">{canon}</span>
                  {REQUIRED.has(canon) && <span className="req">required</span>}
                </td>
                <td>
                  {m.source ? (
                    <span className="mono">{m.source}</span>
                  ) : (
                    <span className="muted">— not found —</span>
                  )}
                </td>
                <td>
                  <span className={`method method-${m.method}`}>{m.method}</span>
                </td>
                <td>
                  {m.source ? (
                    <div className="conf">
                      <div className="conf-bar">
                        <div className="conf-fill" style={{ width: `${m.confidence * 100}%` }} />
                      </div>
                      <span className="small">{Math.round(m.confidence * 100)}%</span>
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {schema.unmapped_source_columns.length > 0 && (
        <p className="muted small">
          Unused source columns: {schema.unmapped_source_columns.map((c) => (
            <span className="mono chip" key={c}>{c}</span>
          ))}
        </p>
      )}
    </div>
  );
}
