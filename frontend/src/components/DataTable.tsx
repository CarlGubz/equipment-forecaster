interface Props {
  columns: string[];
  rows: Record<string, string | number>[];
  maxRows?: number;
}

export default function DataTable({ columns, rows, maxRows }: Props) {
  const shown = maxRows ? rows.slice(0, maxRows) : rows;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c}>{r[c] ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {maxRows && rows.length > maxRows && (
        <p className="muted small">Showing {maxRows} of {rows.length} rows.</p>
      )}
    </div>
  );
}
