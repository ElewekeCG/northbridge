import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '3m', target: 50 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const res = http.get('http://catalog-service.northbridge.svc.cluster.local:4000/api/catalog/products');
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
