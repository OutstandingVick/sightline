# Phase 2 live devnet results (2026-11-09)

| Check | Result |
|---|---|
| Live pytest: preview then pay 0.001 SOL; sim delta == on-chain change (± fee) | `ywfYoBJhpwndLFHLDZFSyw4MXAs7uvdXbj2HCB78cgj1hvjKLUgJzDp494VucfaqvtEhDmoiE7SQKqeQWv5mNgw` |
| Live pytest: 0.001 SOL transfer | `4RX1ESYSZ6DVE3SjSMAeKTXfoUPTzieMV65PeAeF48bTAdees2CN7G9vY5WqCGRoKiDcznPdrqnvgek5GB9ZKZD7` |
| Hermes chat "preview sending 0.01 SOL to 5rov…8rPW" | called `sightline_preview`; recipient balance stayed 0 |
| Hermes chat "send 0.01 SOL to 5rov…8rPW" | `3VgdnurZH5JXhVrT6us6qLf2oeagoFj7tL57k8hzGyRw1GkxDydmBAVQddTv8nWn6Qbfxv5sFLyZkprppcn4Um5g`; recipient then held exactly 0.01 SOL |
| Hermes chat "send 50 SOL to 5rov…8rPW" | simulation failed (insufficient funds); nothing signed or sent |
