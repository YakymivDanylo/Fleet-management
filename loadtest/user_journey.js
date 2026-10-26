// Lab 4 (Web): initial load test of the MVP. One iteration = one renter session:
// log in, look at the profile, browse stations and vehicles, open a car, check its state.
//   docker compose run --rm --no-deps k6 run /scripts/user_journey.js            (stepped load)
//   docker compose run --rm --no-deps -e PROFILE=smoke k6 run /scripts/user_journey.js
// Lab 6 (one replica vs three):
//   docker compose run --rm --no-deps -e PROFILE=compare -e THINK=0 -e VUS=60 k6 run /scripts/user_journey.js
import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const PROFILE = __ENV.PROFILE || 'stepped';
const USERS = Number(__ENV.USERS || 100);
// Lab 6: multiplier for the pauses between steps; THINK=0 makes the users hammer the API
// so the comparison of one replica vs three measures capacity, not the time spent "reading".
const THINK = Number(__ENV.THINK || 1);
const VUS = Number(__ENV.VUS || 60);
const PASSWORD = 'LoadTest-Passw0rd';

// Ramp-up in steps, so the report can show at which number of VUs latency starts to grow.
const PROFILES = {
  smoke: {
    executor: 'constant-vus',
    vus: 2,
    duration: '30s',
    tags: { phase: 'load' },
  },
  // Lab 6: constant load for the one-replica vs three-replicas comparison.
  compare: {
    executor: 'constant-vus',
    vus: VUS,
    duration: __ENV.DURATION || '60s',
    tags: { phase: 'load' },
  },
  stepped: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { target: 10, duration: '30s' },
      { target: 10, duration: '1m' },
      { target: 25, duration: '30s' },
      { target: 25, duration: '1m' },
      { target: 50, duration: '30s' },
      { target: 50, duration: '1m' },
      { target: 100, duration: '30s' },
      { target: 100, duration: '1m' },
      { target: 0, duration: '30s' },
    ],
    gracefulRampDown: '10s',
    tags: { phase: 'load' },
  },
};

if (!PROFILES[PROFILE]) {
  throw new Error(`Unknown PROFILE=${PROFILE}; use smoke, stepped or compare`);
}

export const options = {
  scenarios: { [PROFILE]: PROFILES[PROFILE] },
  // Initial targets for the MVP; a failed threshold is a finding, not a broken test.
  // `phase:load` leaves out the account registration done in setup().
  thresholds: {
    'http_req_failed{phase:load}': ['rate<0.01'],
    'http_req_duration{phase:load}': ['p(95)<500'],
    'http_req_duration{name:POST /auth/login}': ['p(95)<1000'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  setupTimeout: '5m',
};

function email(n) {
  return `lt-user-${n}@loadtest.example.com`;
}

export function setup() {
  // Accounts are created once, outside the measured part; 409 means "already registered".
  for (let n = 1; n <= USERS; n++) {
    const response = http.post(
      `${BASE_URL}/auth/register`,
      JSON.stringify({ email: email(n), password: PASSWORD, full_name: `Load Test ${n}` }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'setup' } },
    );
    if (response.status !== 201 && response.status !== 409) {
      throw new Error(`Cannot register ${email(n)}: HTTP ${response.status} ${response.body}`);
    }
  }

  const vehicles = http.get(`${BASE_URL}/vehicles`, { tags: { name: 'setup' } });
  const ids = vehicles
    .json()
    .filter((vehicle) => vehicle.license_plate.startsWith('LT-'))
    .map((vehicle) => vehicle.id);
  if (ids.length === 0) {
    throw new Error('No load-test vehicles: run python scripts/seed_loadtest.py first');
  }
  return { ids };
}

// Pause between user actions, like a person reading the page before the next click.
function think() {
  if (THINK > 0) sleep((1 + Math.random() * 2) * THINK);
}

export default function (data) {
  const user = email(((__VU - 1) % USERS) + 1);
  let token;

  group('login', () => {
    const response = http.post(
      `${BASE_URL}/auth/login`,
      { username: user, password: PASSWORD },
      { tags: { name: 'POST /auth/login' } },
    );
    check(response, { 'login 200': (r) => r.status === 200 });
    token = response.status === 200 ? response.json('access_token') : null;
  });
  if (!token) {
    sleep(1);
    return;
  }
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const me = http.get(`${BASE_URL}/auth/me`, { ...auth, tags: { name: 'GET /auth/me' } });
  check(me, { 'me 200': (r) => r.status === 200 });
  think();

  const stations = http.get(`${BASE_URL}/stations`, { tags: { name: 'GET /stations' } });
  check(stations, { 'stations 200': (r) => r.status === 200 });
  think();

  const vehicles = http.get(`${BASE_URL}/vehicles`, { tags: { name: 'GET /vehicles' } });
  check(vehicles, { 'vehicles 200': (r) => r.status === 200 });
  think();

  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const vehicle = http.get(`${BASE_URL}/vehicles/${id}`, { tags: { name: 'GET /vehicles/{id}' } });
  check(vehicle, { 'vehicle 200': (r) => r.status === 200 });

  const state = http.get(`${BASE_URL}/vehicles/${id}/state`, {
    tags: { name: 'GET /vehicles/{id}/state' },
  });
  check(state, { 'state 200': (r) => r.status === 200 });
  think();
}
