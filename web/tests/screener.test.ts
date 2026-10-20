import { describe, expect, it } from "vitest";
import type { ScreenSpec } from "@/lib/screener";
import { repoFile } from "./repo";

describe("the spec Candidates sends to screen(spec) (pipeline/screener.py is the contract)", () => {
  it("uses only fields pipeline/screener.py's ScreenSpec has", () => {
    const py = repoFile("pipeline/screener.py");
    const fields = /class ScreenSpec\(BaseModel\):([\s\S]*?)\n\n/.exec(py)?.[1] ?? "";
    const spec: Required<ScreenSpec> = { market: "us", buckets: ["candidate"], families_all: ["text"], limit: 2000 };
    for (const key of Object.keys(spec)) expect([key, new RegExp(`\\n\\s+${key}: `).test(fields)]).toEqual([key, true]);
  });
});
