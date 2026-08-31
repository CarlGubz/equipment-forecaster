import type { AnalyzeResult, AppConfig, SampleInfo } from "./types";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function getConfig(): Promise<AppConfig> {
  return handle(await fetch("/api/config"));
}

export async function getSamples(): Promise<SampleInfo[]> {
  const data = await handle<{ samples: SampleInfo[] }>(await fetch("/api/samples"));
  return data.samples;
}

export async function analyzeSample(sample: string, useAi: boolean): Promise<AnalyzeResult> {
  const form = new FormData();
  form.append("sample", sample);
  form.append("use_ai", String(useAi));
  return handle(await fetch("/api/analyze", { method: "POST", body: form }));
}

export async function analyzeFile(file: File, useAi: boolean): Promise<AnalyzeResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("use_ai", String(useAi));
  return handle(await fetch("/api/analyze", { method: "POST", body: form }));
}
