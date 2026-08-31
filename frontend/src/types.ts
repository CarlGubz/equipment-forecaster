// Types mirroring the FastAPI /api responses.

export interface SampleInfo {
  name: string;
  label: string;
  columns: string[];
  rows: number;
}

export interface AppConfig {
  ai_enabled: boolean;
  model: string | null;
  base_url: string | null;
}

export interface ColumnMap {
  source: string | null;
  confidence: number;
  method: string;
}

export interface SchemaResult {
  mapping: Record<string, ColumnMap>;
  unmapped_source_columns: string[];
  missing_required: string[];
}

export interface PreprocessReport {
  input_rows: number;
  output_rows: number;
  dropped_missing_key: number;
  dropped_bad_date: number;
  dropped_duplicates: number;
  date_format_note: string;
  warnings: string[];
}

export type PredictionStatus =
  | "overdue"
  | "due_soon"
  | "scheduled"
  | "insufficient_history";

export interface Prediction {
  client: string;
  part_number: string;
  part_name: string;
  equipment: string;
  order_count: number;
  last_order_date: string;
  avg_interval_days: number | null;
  predicted_next_order_date: string | null;
  days_until_due: number | null;
  status: PredictionStatus;
  confidence: number;
  suggested_quantity: number;
  rationale: string;
}

export interface AnalyzeSummary {
  clients: string[];
  distinct_parts: number;
  overdue: number;
  due_soon: number;
}

export interface AnalyzeResult {
  source_name: string;
  as_of: string;
  ai_used: boolean;
  raw_preview: { columns: string[]; rows: Record<string, string>[] };
  schema: SchemaResult;
  preprocessing: PreprocessReport;
  cleaned_preview: Record<string, string | number>[];
  cleaned_csv: string;
  predictions: Prediction[];
  summary: AnalyzeSummary;
}
