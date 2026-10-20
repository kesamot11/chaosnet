import { type ChangeEvent, type FormEvent, useState } from "react";
import { type StartResult, startExperiment } from "./api";
import { type FormValues, toSpec } from "./form";

const DEFAULTS: FormValues = {
  name: "",
  kind: "latency",
  direction: "both",
  ms: 200,
  kbps: 100,
  rate: 20,
  baseline_s: 10,
  inject_s: 15,
  recover_s: 10,
  max_p95_ms: 500,
  max_error_rate: 0.01,
};

type Props = { link: string }; // the link selected in the topology view

/** The experiment for one link (#77). On a refusal everything typed stays, with the reason. */
export function ExperimentForm({ link }: Props) {
  const [values, setValues] = useState(DEFAULTS);
  const [sending, setSending] = useState(false); // waiting for the controller's answer
  const [result, setResult] = useState<StartResult | null>(null); // null: not started yet

  // One change handler for every field: `field("ms")` updates values.ms.
  function field(key: keyof FormValues) {
    return (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const input = e.target;
      const value = input.type === "number" ? Number(input.value) : input.value;
      setValues({ ...values, [key]: value });
    };
  }

  async function submit(e: FormEvent) {
    e.preventDefault(); // a plain HTML form would reload the page
    setSending(true);
    const spec = toSpec(values, link);
    const res = await startExperiment(spec);
    setResult(res);
    setSending(false);
  }

  return (
    <form onSubmit={submit} aria-label="experiment">
      <h2>Experiment on {link}</h2>
      <label>
        Name <input value={values.name} onChange={field("name")} required />
      </label>
      <fieldset>
        <legend>Fault</legend>
        <label>
          Kind{" "}
          <select value={values.kind} onChange={field("kind")}>
            <option value="latency">latency</option>
            <option value="bandwidth">bandwidth</option>
            <option value="reset_peer">reset peer</option>
          </select>
        </label>
        <label>
          Direction{" "}
          <select value={values.direction} onChange={field("direction")}>
            <option value="both">both</option>
            <option value="request">request</option>
            <option value="response">response</option>
          </select>
        </label>
        <label>
          Latency ms{" "}
          <input
            type="number"
            value={values.ms}
            onChange={field("ms")}
            disabled={values.kind !== "latency"}
          />
        </label>
        <label>
          Bandwidth kbps{" "}
          <input
            type="number"
            value={values.kbps}
            onChange={field("kbps")}
            disabled={values.kind !== "bandwidth"}
          />
        </label>
      </fieldset>
      <fieldset>
        <legend>Load and phases</legend>
        <label>
          Requests/s <input type="number" value={values.rate} onChange={field("rate")} />
        </label>
        <label>
          Baseline s{" "}
          <input type="number" value={values.baseline_s} onChange={field("baseline_s")} />
        </label>
        <label>
          Inject s <input type="number" value={values.inject_s} onChange={field("inject_s")} />
        </label>
        <label>
          Recover s <input type="number" value={values.recover_s} onChange={field("recover_s")} />
        </label>
      </fieldset>
      <fieldset>
        <legend>Hypothesis: during inject</legend>
        <label>
          p95 at most ms{" "}
          <input type="number" value={values.max_p95_ms} onChange={field("max_p95_ms")} />
        </label>
        <label>
          Error rate at most (0–1){" "}
          <input
            type="number"
            step="0.01"
            value={values.max_error_rate}
            onChange={field("max_error_rate")}
          />
        </label>
      </fieldset>
      <button type="submit" disabled={sending}>
        {sending ? "Starting…" : "Start"}
      </button>
      {result?.ok === true && <p>Experiment #{result.experiment.id} started</p>}
      {result?.ok === false && <p role="alert">Not started: {result.reason}</p>}
    </form>
  );
}
