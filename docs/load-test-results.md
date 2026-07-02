ec2-user@ip-172-31-28-172 northbridge]$ k6 run ~/northbridge/scripts/load-test.js

         /\      Grafana   /‾‾/  
    /\  /  \     |\  __   /  /   
   /  \/    \    | |/ /  /   ‾‾\ 
  /          \   |   (  |  (‾)  |
 / __________ \  |_|\_\  \_____/ 


     execution: local
        script: /home/ec2-user/northbridge/scripts/load-test.js
        output: -

     scenarios: (100.00%) 1 scenario, 20 max VUs, 10m30s max duration (incl. graceful stop):
              * default: 200 iterations shared among 20 VUs (maxDuration: 10m0s, gracefulStop: 30s)



  █ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<2000' p(95)=9.57ms

    http_req_failed
    ✓ 'rate<0.05' rate=0.00%


  █ TOTAL RESULTS 

    checks_total.......: 400     287.281073/s
    checks_succeeded...: 100.00% 400 out of 400
    checks_failed......: 0.00%   0 out of 400

    ✓ status is 200
    ✓ response has products

    CUSTOM
    p95_latency....................: avg=12.413668 min=1.542134 med=3.970429 max=177.224383 p(90)=8.601317 p(95)=101.735298

    HTTP
    http_req_duration..............: avg=6.89ms    min=466.64µs med=2.24ms   max=177.22ms   p(90)=6.25ms   p(95)=9.57ms    
      { expected_response:true }...: avg=6.89ms    min=466.64µs med=2.24ms   max=177.22ms   p(90)=6.25ms   p(95)=9.57ms    
    http_req_failed................: 0.00%  0 out of 400
    http_reqs......................: 400    287.281073/s

    EXECUTION
    iteration_duration.............: avg=136.32ms  min=102.62ms med=105.88ms max=443.13ms   p(90)=140.88ms p(95)=410.83ms  
    iterations.....................: 200    143.640536/s
    vus............................: 20     min=20       max=20
    vus_max........................: 20     min=20       max=20

    NETWORK
    data_received..................: 422 kB 303 kB/s
    data_sent......................: 65 kB  46 kB/s




running (00m01.4s), 00/20 VUs, 200 complete and 0 interrupted iterations
default ✓ [ 100% ] 20 VUs  00m01.4s/10m0s  200/200 shared iters
[ec2-user@ip-172-31-28-172 northbridge]$ 