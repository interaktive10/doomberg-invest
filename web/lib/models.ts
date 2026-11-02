// The OpenRouter models and efforts Settings may pick per task (docs/SPEC_ISSUES.md 69). A mirror of
// config/quotas.yaml openrouter.choices / efforts (tests/test_web_parity.py checks the two match); the pipeline reads
// the pick from app_settings llm_models / llm_effort and ignores anything not listed there. Pure, so
// tests/models.test.ts covers it.

export interface ModelChoice {
  id: string;
  label: string;
  /** $ per million tokens in and out, as OpenRouter listed them on 2026-11-02 */
  in: number;
  out: number;
}

export const CHOICES: readonly ModelChoice[] = [
  { id: "deepseek/deepseek-v4.1-flash-1017", label: "DeepSeek V4.1 Flash 1017", in: 0.3, out: 1.2 },
  { id: "deepseek/deepseek-v4.1-flash", label: "DeepSeek V4.1 Flash", in: 0.04, out: 0.5 },
  { id: "z-ai/glm-5.3-flash", label: "GLM 5.3 Flash", in: 0.03, out: 0.09 },
  { id: "qwen/qwen3.5-flash-02-23", label: "Qwen 3.5 Flash", in: 0.07, out: 0.26 },
  { id: "openai/gpt-6-luna", label: "GPT-6 Luna", in: 0.1, out: 0.5 },
  { id: "anthropic/claude-haiku-5.5", label: "Claude Haiku 5.5", in: 0.1, out: 0.5 },
  { id: "openai/gpt-oss-120b", label: "gpt-oss 120B", in: 0.15, out: 0.6 },
];

export const EFFORTS = ["none", "low", "medium", "high"] as const;
export type Effort = (typeof EFFORTS)[number];

export const TASKS = [
  { key: "extract", label: "Reading filings", hint: "Pulls facts out of filings and announcements: hundreds of calls a day." },
  { key: "card", label: "Cards and themes", hint: "Writes research cards, checks their claims and rethinks the themes: a few calls a day." },
] as const;
export type Task = (typeof TASKS)[number]["key"];

/** What the config uses before Settings picks anything (config/quotas.yaml openrouter.models / reasoning). */
export const DEFAULTS: { models: Record<Task, string>; effort: Record<Task, Effort> } = {
  models: { extract: "deepseek/deepseek-v4.1-flash-1017", card: "deepseek/deepseek-v4.1-flash-1017" },
  effort: { extract: "low", card: "high" },
};

export const EFFORT_LABEL: Record<Effort, string> = {
  none: "Off (no reasoning)",
  low: "Low",
  medium: "Medium",
  high: "High (slower, more tokens)",
};

/** "$0.30 in · $1.20 out per million tokens". */
export function priceText(m: ModelChoice): string {
  return `$${m.in.toFixed(2)} in · $${m.out.toFixed(2)} out per million tokens`;
}

/** The stored pick, read safely: a listed model and effort per task, else the default. */
export function picked(models: unknown, effort: unknown): { models: Record<Task, string>; effort: Record<Task, Effort> } {
  const m = (models && typeof models === "object" ? models : {}) as Record<string, unknown>;
  const e = (effort && typeof effort === "object" ? effort : {}) as Record<string, unknown>;
  const out = { models: { ...DEFAULTS.models }, effort: { ...DEFAULTS.effort } };
  for (const { key } of TASKS) {
    const mv = m[key];
    if (typeof mv === "string" && CHOICES.some((c) => c.id === mv)) out.models[key] = mv;
    const ev = e[key];
    if (typeof ev === "string" && (EFFORTS as readonly string[]).includes(ev)) out.effort[key] = ev as Effort;
  }
  return out;
}
