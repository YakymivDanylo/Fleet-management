import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const PROFILE = __ENV.PROFILE || 'normal';
const STEADY = __ENV.STEADY || '60s';
const PEAK_RPS = Number(__ENV.PEAK_RPS || 1500);

const PROFILES = {
  normal: {
    executor: 'ramping-arrival-rate',
    startRate: 10,
    timeUnit: '1s',
    preAllocatedVUs: 20,
    maxVUs: 100,
    stages: [
      { target: 50, duration: '20s' }, 
      { target: 50, duration: STEADY },
      { target: 0, duration: '10s' },
    ],
  },
  peak: {
    executor: 'ramping-arrival-rate',
    startRate: 50,
    timeUnit: '1s',
    preAllocatedVUs: 200,
    maxVUs: 1000,
    stages: [
      { target: PEAK_RPS, duration: '30s' },
      { target: PEAK_RPS, duration: STEADY },
      { target: 0, duration: '10s' },
    ],
  },
  fault: {
    executor: 'constant-arrival-rate',
    rate: 30,
    timeUnit: '1s',
    duration: __ENV.STEADY || '40s',
    preAllocatedVUs: 50,
    maxVUs: 400,
  },
};

const SLO = {
  normal: { p95: 100, errorRate: 0.01 },
  peak: { p95: 100, errorRate: 0.01 },
  fault: { p95: 1000, errorRate: 0.01 },
};

const slo = SLO[PROFILE];
if (!slo) {
  throw new Error(`Unknown PROFILE=${PROFILE}; use normal, peak or fault`);
}

export const degraded = new Rate('degraded_responses');

export const options = {
  scenarios: { [PROFILE]: PROFILES[PROFILE] },
  thresholds: {
    http_req_duration: [`p(95)<${Number(__ENV.P95_MS || slo.p95)}`],
    http_req_failed: [`rate<${Number(__ENV.MAX_ERROR_RATE || slo.errorRate)}`],
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const response = http.get(`${BASE_URL}/vehicles`);
  if (response.status !== 200) {
    throw new Error(`Cannot list vehicles: HTTP ${response.status}`);
  }
  const ids = response
    .json()
    .filter((vehicle) => vehicle.license_plate.startsWith('LT-'))
    .map((vehicle) => vehicle.id);
  if (ids.length === 0) {
    throw new Error('No load-test vehicles: run python scripts/seed_loadtest.py first');
  }
  return { ids };
}

export default function (data) {
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const response = http.get(`${BASE_URL}/vehicles/${id}/state`, {
    tags: { name: 'GET /vehicles/{id}/state' },
    timeout: '10s',
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
    'body has vehicle state': (r) => r.status === 200 && r.json('vehicle_id') === id,
  });
  degraded.add(response.status === 200 && response.json('degraded') === true);
}
