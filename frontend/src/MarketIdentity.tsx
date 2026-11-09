import { useId } from "react";
import type { IdentityDimension, MarketDetail } from "./types";
import "./MarketIdentity.css";

const notRecorded = "Not recorded in this snapshot";
const dimensions: Array<{ key: IdentityDimension; field: keyof MarketDetail; label: string }> = [
  { key: "buyer", field: "buyer", label: "Buyer" },
  { key: "job", field: "job_to_be_done", label: "Job to be done" },
  { key: "delivery", field: "delivery_model", label: "Delivery model" },
  { key: "workforce", field: "workforce_model", label: "Workforce model" },
  { key: "economics_risk", field: "economics_risk", label: "Economics and risk" },
  { key: "acquisition_universe", field: "acquisition_universe", label: "Acquisition universe" },
  { key: "ambient_ai_workflow", field: "ambient_ai_workflow", label: "Ambient AI workflow" },
];

function recordedText(value: unknown): string {
  return typeof value === "string" && value.length > 0 ? value : notRecorded;
}

function RecordedList({ items, evidenceIds = false }: { items?: string[] | null; evidenceIds?: boolean }) {
  if (items == null) return <p className="market-identity-missing">{notRecorded}</p>;
  if (items.length === 0) return <p className="market-identity-missing">None recorded</p>;
  return <ul className={evidenceIds ? "market-identity-evidence-list" : "market-identity-exclusions"}>
    {items.map((item, index) => <li key={`${index}-${item}`}>{evidenceIds ? <code>{item}</code> : item}</li>)}
  </ul>;
}

export function MarketIdentity({ market }: { market: MarketDetail }) {
  const id = useId();
  return <>
    <section className="panel market-identity" aria-labelledby={`${id}-title`}>
      <p className="eyebrow">Operating identity</p>
      <h2 id={`${id}-title`}>Why this boundary exists</h2>
      <p className="market-identity-intro">These are the selected market record’s operating dimensions. Boundary confidence is reported on a 0–1 scale; it is not an investment score.</p>
      <div className="market-identity-grid">
        {dimensions.map(({ key, field, label }) => {
          const confidence = market.confidence_by_dimension?.[key];
          return <article className="market-identity-dimension" key={key} aria-labelledby={`${id}-${key}`}>
            <h3 id={`${id}-${key}`}>{label}</h3>
            <p className="market-identity-narrative">{recordedText(market[field])}</p>
            <dl className="market-identity-meta">
              <div><dt>Boundary confidence</dt><dd>{typeof confidence === "number" && Number.isFinite(confidence) ? `${confidence} / 1` : notRecorded}</dd></div>
              <div><dt>Evidence class</dt><dd>{recordedText(market.evidence_by_dimension?.[key])}</dd></div>
            </dl>
          </article>;
        })}
      </div>
    </section>
    <section className="panel market-identity" aria-labelledby={`${id}-exclusions`}>
      <p className="eyebrow">Boundary limits</p>
      <h2 id={`${id}-exclusions`}>Explicit exclusions</h2>
      <RecordedList items={market.explicit_exclusions} />
    </section>
    <section className="panel market-identity" aria-labelledby={`${id}-evidence`}>
      <p className="eyebrow">Evidence references</p>
      <h2 id={`${id}-evidence`}>Supporting and contrary evidence</h2>
      <p className="market-identity-intro">These references apply to the market record as a whole. Evidence classes above describe each dimension.</p>
      <details><summary>Supporting evidence IDs</summary><RecordedList items={market.supporting_evidence_ids} evidenceIds /></details>
      <details><summary>Counterevidence IDs</summary><RecordedList items={market.counterevidence_ids} evidenceIds /></details>
    </section>
  </>;
}
