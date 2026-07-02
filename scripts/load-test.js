import http from 'k6/http';
import { check, sleep } from 'k6';
import {Trend } from 'k6/metrics';

const p95Latency = new Trend('p95_latency');

export const options = {
    vus: 20,
    iterations: 200,
    thresholds: {
        http_req_duration: ['p(95)<2000'], // 95% of requests should be below 2000ms
        http_req_failed: ['rate<0.05'], // less than 1% of requests should fail
    },
};

export default function () {
    const res = http.get('http://shopn.chickenkiller.com/api/catalog/products');
    
    check(res, {
        'status is 200': (r) => r.status === 200,
        'response has products': (r) => JSON.parse(r.body).products !== undefined,
    });

    p95Latency.add(res.timings.duration);

    sleep(0.1);
}