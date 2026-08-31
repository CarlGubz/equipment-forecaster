import { useEffect, useMemo, useState } from "react";
import { analyzeFile, analyzeSample, getConfig, getSamples } from "./api";
import type { AnalyzeResult, AppConfig, SampleInfo } from "./types";
import { downloadText, predictionsToCsv } from "./utils";
import DataTable from "./components/DataTable";
import SchemaView from "./components/SchemaView";
import Predictions from "./components/Predictions";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [useAi, setUseAi] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [activeSource, setActiveSource] = useState<string>("");

  useEffect(() => {
    getConfig().then(setConfig).catch(() => setConfig({ ai_enabled: false, model: null, base_url: null }));
    getSamples().then(setSamples).catch(() => setSamples([]));
  }, []);

  async function run(fn: () => Promise<AnalyzeResult>, label: string) {
    setLoading(true);
    setError(null);
    setActiveSource(label);
    try {
      setResult(await fn());
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const onSample = (s: SampleInfo) => run(() => analyzeSample(s.name, useAi), s.label);
  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) run(() => analyzeFile(file, useAi), file.name);
    e.target.value = "";
  };

  const cleanedColumns = useMemo(
    () => (result?.cleaned_preview?.[0] ? Object.keys(result.cleaned_preview[0]) : []),
    [result]
  );

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Equipment Reorder Predictor</h1>
          <p className="subtitle">
            Predict the next equipment part each client will order — and when — so you can
            pre-stage it and prevent operational downtime.
          </p>
        </div>
        <AiBadge config={config} />
      </header>

      <section className="panel">
        <h2>1 · Choose a data source</h2>
        <p className="muted">
          Every client exports differently. Pick a sample or upload your own CSV — the app maps
          the columns, cleans the data, and forecasts reorders automatically.
        </p>

        <div className="sample-grid">
          {samples.map((s) => (
            <button
              key={s.name}
              className="sample-btn"
              disabled={loading}
              onClick={() => onSample(s)}
            >
              <span className="sample-label">{s.label}</span>
              <span className="muted small">
                {s.rows} rows · columns: {s.columns.join(", ")}
              </span>
            </button>
          ))}
        </div>

        <div className="controls">
          <label className="upload">
            <input type="file" accept=".csv,text/csv" onChange={onFile} disabled={loading} />
            <span className="upload-btn">Upload a CSV…</span>
          </label>

          <label className={`toggle ${!config?.ai_enabled ? "toggle-disabled" : ""}`}>
            <input
              type="checkbox"
              checked={useAi && !!config?.ai_enabled}
              disabled={!config?.ai_enabled}
              onChange={(e) => setUseAi(e.target.checked)}
            />
            <span>
              Use AI assist
              {!config?.ai_enabled && <span className="muted small"> (configure your Claude endpoint to enable)</span>}
            </span>
          </label>
        </div>
      </section>

      {loading && (
        <div className="panel status">
          <div className="spinner" /> Analyzing <strong>{activeSource}</strong>…
        </div>
      )}

      {error && (
        <div className="panel error-panel">
          <strong>Couldn’t analyze that file.</strong>
          <p>{error}</p>
        </div>
      )}

      {result && !loading && (
        <>
          <section className="panel">
            <div className="panel-head">
              <h2>2 · Schema mapping</h2>
              <span className="muted small">
                {result.ai_used ? "heuristic + AI assist" : "heuristic"}
              </span>
            </div>
            <p className="muted">
              Your column names, mapped onto one unified schema everything downstream relies on.
            </p>
            <SchemaView schema={result.schema} />

            <details className="raw-details">
              <summary>Show raw uploaded data ({result.raw_preview.columns.length} columns)</summary>
              <DataTable columns={result.raw_preview.columns} rows={result.raw_preview.rows} />
            </details>
          </section>

          <section className="panel">
            <h2>3 · Cleaned data</h2>
            <p className="muted">
              Dates normalized to ISO ({result.preprocessing.date_format_note} detected),
              identifiers standardized, duplicates and unusable rows removed.
            </p>
            <div className="report">
              <Stat label="Input rows" value={result.preprocessing.input_rows} />
              <Stat label="Output rows" value={result.preprocessing.output_rows} />
              <Stat label="Bad dates dropped" value={result.preprocessing.dropped_bad_date} />
              <Stat label="Blank part# dropped" value={result.preprocessing.dropped_missing_key} />
              <Stat label="Duplicates removed" value={result.preprocessing.dropped_duplicates} />
            </div>
            <DataTable columns={cleanedColumns} rows={result.cleaned_preview} maxRows={15} />
            <button
              className="ghost-btn"
              onClick={() =>
                downloadText(`cleaned_${result.source_name.replace(/\.[^.]+$/, "")}.csv`, result.cleaned_csv)
              }
            >
              ⬇ Download cleaned CSV
            </button>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>4 · Reorder forecast</h2>
              <button
                className="ghost-btn"
                onClick={() =>
                  downloadText(
                    `predictions_${result.source_name.replace(/\.[^.]+$/, "")}.csv`,
                    predictionsToCsv(result.predictions)
                  )
                }
              >
                ⬇ Download forecast CSV
              </button>
            </div>
            <p className="muted">
              For each part: its last order date and the predicted next order date, ranked by
              urgency. This is your pre-staging priority list.
            </p>
            <Predictions
              predictions={result.predictions}
              summary={result.summary}
              asOf={result.as_of}
            />
          </section>
        </>
      )}

      <footer className="footer muted small">
        FastAPI · Python · TypeScript/React · statistical forecasting with optional Claude assist.
      </footer>
    </div>
  );
}

function AiBadge({ config }: { config: AppConfig | null }) {
  if (!config) return null;
  return config.ai_enabled ? (
    <div className="ai-badge ai-on" title={config.base_url ?? ""}>
      ● AI assist on <span className="mono small">{config.model}</span>
    </div>
  ) : (
    <div className="ai-badge ai-off">● AI assist off — statistical mode</div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
