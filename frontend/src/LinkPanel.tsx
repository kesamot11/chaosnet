import type { Link, LinkSettings } from "./api";

type Props = {
  link: Link; // as in the draft, if there is one
  onChange: (change: Partial<LinkSettings>) => void;
};

/**
 * The settings of the selected link (#185). A change goes into the draft like any other, and
 * the controller checks the values on Save (Tomáš). An empty retry budget is no budget (Tomáš).
 */
export function LinkPanel({ link, onChange }: Props) {
  return (
    <fieldset>
      <legend>Settings of {link.name}</legend>
      <label>
        Timeout (s){" "}
        <input
          type="number"
          step="0.1"
          value={link.timeout_s}
          onChange={(e) => onChange({ timeout_s: Number(e.target.value) })}
        />
      </label>{" "}
      <label>
        Retries{" "}
        <input
          type="number"
          value={link.max_retries}
          onChange={(e) => onChange({ max_retries: Number(e.target.value) })}
        />
      </label>{" "}
      <label>
        Backoff (s){" "}
        <input
          type="number"
          step="0.1"
          value={link.backoff_s}
          onChange={(e) => onChange({ backoff_s: Number(e.target.value) })}
        />
      </label>{" "}
      <label>
        Retry budget{" "}
        <input
          type="number"
          step="0.1"
          placeholder="off"
          value={link.retry_budget ?? ""}
          onChange={(e) =>
            onChange({ retry_budget: e.target.value === "" ? null : Number(e.target.value) })
          }
        />
      </label>{" "}
      <label>
        <input
          type="checkbox"
          checked={link.breaker}
          onChange={(e) => onChange({ breaker: e.target.checked })}
        />{" "}
        Circuit breaker
      </label>{" "}
      <label>
        <input
          type="checkbox"
          checked={link.fallback}
          onChange={(e) => onChange({ fallback: e.target.checked })}
        />{" "}
        Fallback
      </label>
    </fieldset>
  );
}
