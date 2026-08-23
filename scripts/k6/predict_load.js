// Replays the ramped drift fixture against POST /predictions, populating
// prediction_events with a "recession" window whose intensity grows over
// the run — barely any drift at first, a clear one by the end — for the
// drift notebook to compare against the reference dataset.
//
// The fixture's payloads are ordered by increasing drift intensity
// (payload 0 untouched, payload 9999 full scenario — see
// scripts/generate_drift_fixtures.py). To make that ramp visible in wall
// clock time rather than instantaneous, each VU must walk the fixture in
// lockstep with the others: at a given iteration tick, the 20 VUs consume
// 20 *consecutive* fixture entries (index = __ITER * VUS + (__VU - 1)),
// not entries spread `ITERATIONS_PER_VU` apart — otherwise every tick
// would already span nearly the full ramp, and the "grows over time"
// effect would be invisible on the Grafana dashboard.
//
// Paced to ~15 minutes total by default (SLEEP_SECONDS between each VU's
// iterations) so the ramp is slow enough to watch live — set
// SLEEP_SECONDS=0 to go back to firing as fast as possible.
//
// Usage: k6 run scripts/k6/predict_load.js
//        k6 run -e BASE_URL=http://localhost:8000 -e API_TOKEN=... -e SLEEP_SECONDS=0 scripts/k6/predict_load.js
//
// Vigilance: BASE_URL defaults to the local docker-compose stack. Pointing
// this at anything else (e.g. the deployed VPS) injects synthetic
// "recession" predictions into real production monitoring/dashboards —
// that's a deliberate choice to make explicitly, not this script's default.

import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const FIXTURE_PATH = __ENV.FIXTURE_PATH || "./fixtures/drifted_payloads.json";
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API_TOKEN = __ENV.API_TOKEN || "";

const VUS = 20;
const ITERATIONS_PER_VU = 500; // 20 x 500 = 10,000 payloads, matching the fixture size.
// 500 iterations x 1.8s ≈ 15 minutes per VU, all VUs running in parallel.
const SLEEP_SECONDS = __ENV.SLEEP_SECONDS !== undefined ? Number(__ENV.SLEEP_SECONDS) : 1.8;

const payloads = new SharedArray("drift payloads", function () {
  return JSON.parse(open(FIXTURE_PATH));
});

export const options = {
  scenarios: {
    predict: {
      executor: "per-vu-iterations",
      vus: VUS,
      iterations: ITERATIONS_PER_VU,
      maxDuration: "20m",
    },
  },
};

export default function () {
  const index = (__ITER * VUS + (__VU - 1)) % payloads.length;
  const payload = payloads[index];

  const headers = { "Content-Type": "application/json" };
  if (API_TOKEN) {
    headers["Authorization"] = `Bearer ${API_TOKEN}`;
  }

  const response = http.post(`${BASE_URL}/predictions`, JSON.stringify(payload), { headers });

  check(response, {
    "status is 200": (r) => r.status === 200,
  });

  if (SLEEP_SECONDS > 0) {
    sleep(SLEEP_SECONDS);
  }
}
