// Lab 8: soak (endurance), break-point and spike tests. Same renter journey as Lab 4 / 6,
// but driven by an open model (arrival rate): the rate of NEW sessions stays constant even
// when the server slows down, so degradation shows up as latency/errors, not as a lower RPS.
//   docker compose ... run --rm --no-deps -e PROFILE=soak -e RATE=7 -e DURATION=60m \
//       k6 run -o experimental-prometheus-rw /scripts/soak.js
// One iteration = 6 HTTP requests (login, me, stations, vehicles, vehicle, vehicle state).
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const PROFILE = __ENV.PROFILE || 'soak';
const USERS = Number(__ENV.USERS || 100);
const RATE = Number(__ENV.RATE || 7); // sessions per second (x6 = HTTP requests per second)
const PASSWORD = 'LoadTest-Passw0rd';
const TAG = __ENV.RUN_TAG || PROFILE;

const PROFILES = {
  smoke: {
    executor: 'constant-arrival-rate', rate: RATE, timeUnit: '1s', duration: '30s',
    preAllocatedVUs: 20, maxVUs: 200,
  },
  soak: {
    executor: 'constant-arrival-rate', rate: RATE, timeUnit: '1s',
    duration: __ENV.DURATION || '60m', preAllocatedVUs: 50, maxVUs: 400,
  },
  // Stress: +2 sessions/s every minute until the system breaks (the test stops itself
  // through the abortOnFail thresholds below).
  breakpoint: {
    executor: 'ramping-arrival-rate', startRate: 2, timeUnit: '1s',
    preAllocatedVUs: 100, maxVUs: 1500,
    stages: Array.from({ length: 12 }, (_, i) => ({ target: 4 + i * 2, duration: '1m' })),
  },
  // Spike: calm baseline, sudden x5 jump for 2 minutes, then back to baseline to watch recovery.
  spike: {
    executor: 'ramping-arrival-rate', startRate: RATE, timeUnit: '1s',
    preAllocatedVUs: 100, maxVUs: 1500,
    stages: [
      { target: RATE, duration: '2m' },
      { target: RATE * 5, duration: '5s' },
      { target: RATE * 5, duration: '2m' },
      { target: RATE, duration: '5s' },
      { target: RATE, duration: '4m' },
    ],
  },
};

if (!PROFILES[PROFILE]) throw new Error(`Unknown PROFILE=${PROFILE}`);

const thresholds = {
  // Lab 8 pass criteria: error rate <= 0.1 %.
  'http_req_failed{phase:load}': PROFILE === 'soak' ? ['rate<=0.001'] : ['rate<0.5'],
  'http_req_duration{phase:load}': ['p(95)<1000'],
};
if (PROFILE === 'breakpoint') {
  thresholds['http_req_failed{phase:load}'] = [
    { threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '20s' },
  ];
}

export const options = {
  scenarios: { [PROFILE]: { ...PROFILES[PROFILE], tags: { phase: 'load' } } },
  thresholds,
  tags: { run: TAG },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  setupTimeout: '5m',
};

const email = (n) => `lt-user-${n}@loadtest.example.com`;

export function setup() {
  for (let n = 1; n <= USERS; n++) {
    const response = http.post(
      `${BASE_URL}/auth/register`,
      JSON.stringify({ email: email(n), password: PASSWORD, full_name: `Load Test ${n}` }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'setup' } },
    );
    if (response.status !== 201 && response.status !== 409) {
      throw new Error(`Cannot register ${email(n)}: HTTP ${response.status}`);
    }
  }
  const ids = http.get(`${BASE_URL}/vehicles`, { tags: { name: 'setup' } }).json()
    .filter((v) => v.license_plate.startsWith('LT-')).map((v) => v.id);
  if (ids.length === 0) throw new Error('Run python scripts/seed_loadtest.py first');
  return { ids };
}

export default function (data) {
  const user = email(Math.floor(Math.random() * USERS) + 1);
  const login = http.post(`${BASE_URL}/auth/login`, { username: user, password: PASSWORD },
    { tags: { name: 'POST /auth/login' } });
  if (!check(login, { 'login 200': (r) => r.status === 200 })) return;
  const auth = { headers: { Authorization: `Bearer ${login.json('access_token')}` } };
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const steps = [
    ['GET /auth/me', '/auth/me', auth],
    ['GET /stations', '/stations', {}],
    ['GET /vehicles', '/vehicles', {}],
    ['GET /vehicles/{id}', `/vehicles/${id}`, {}],
    ['GET /vehicles/{id}/state', `/vehicles/${id}/state`, {}],
  ];
  for (const [name, path, params] of steps) {
    const response = http.get(`${BASE_URL}${path}`, { ...params, tags: { name } });
    check(response, { [`${name} 200`]: (r) => r.status === 200 });
  }
}

export function handleSummary(data) {
  const out = `/scripts/results/lab8/${TAG}`;
  return {
    [`${out}_summary.json`]: JSON.stringify(data, null, 2),
    stdout: `\nsummary saved to ${out}_summary.json\n`,
  };
}
