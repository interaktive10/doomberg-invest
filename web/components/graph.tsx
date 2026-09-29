"use client";

import { useEffect, useRef } from "react";

// BRIEF §6 Capex Desk: the counterparty graph (Cytoscape.js). Companies are blue, counterparties grey; the table next
// to it lists the same edges as text. Zoom is capped, so a small graph isn't blown up to fill the box.
export interface GraphData {
  nodes: { id: string; label: string; kind: "company" | "entity" }[];
  edges: { id: string; source: string; target: string; label: string }[];
}

const STYLE = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      width: 18,
      height: 18,
      "font-size": 11,
      color: "#111827",
      "text-valign": "bottom",
      "text-margin-y": 5,
      "text-wrap": "ellipsis",
      "text-max-width": "120px",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "text-background-padding": "2px",
    },
  },
  { selector: "node[kind = 'company']", style: { "background-color": "#1e40af" } },
  { selector: "node[kind = 'entity']", style: { "background-color": "#6b7280" } },
  {
    selector: "edge",
    style: {
      width: 1.5,
      label: "data(label)",
      "font-size": 9,
      color: "#374151",
      "text-rotation": "autorotate",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "line-color": "#9ca3af",
      "target-arrow-color": "#9ca3af",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
    },
  },
];

export function CapexGraph({ data }: { data: GraphData }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let destroy: (() => void) | undefined;
    let cancelled = false;
    void import("cytoscape").then(({ default: cytoscape }) => {
      if (cancelled || ref.current === null) return;
      const cy = cytoscape({
        container: ref.current,
        elements: [...data.nodes.map((n) => ({ data: { ...n } })), ...data.edges.map((e) => ({ data: { ...e } }))],
        style: STYLE as never,
        layout: { name: "cose", animate: false, padding: 40 } as never,
        minZoom: 0.3,
        maxZoom: 1.6,
      });
      cy.fit(undefined, 40);
      destroy = () => cy.destroy();
    });
    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [data]);
  return (
    <div
      ref={ref}
      role="img"
      aria-label={`Counterparty graph: ${data.nodes.length} companies and counterparties, ${data.edges.length} links (listed in the table)`}
      className="h-80 w-full rounded-lg border border-gray-200 bg-gray-50 sm:h-96"
    />
  );
}
