# Phase 3+4 live results (devnet, 2026-11-09)

All through Hermes chat (`hermes chat -q`, model `meituan/longcat-2.5:free`), recipient `76nK…TRX1`.

| Step | Outcome |
|---|---|
| "send 0.01 SOL" with no grant | APPROVE → single-query mode has no human → Hermes blocked; nothing sent |
| `/sightline grant 0.05 SOL to 76nK… for 1h max 0.02 note "phase4 live test"` | `g_c619` created and echoed |
| "send 0.01 SOL" | ALLOW by `g_c619` → sent `47yj661Sz6Mf5fi7EHKyBTxUBioPHxdvbr5y6zDYjRgS4Vaftii5fi8qpeDcmMZkeJAnbDyRrXRpnHqrZRXtbahD` |
| "send 0.03 SOL" | APPROVE: exceeds per-tx max 0.02 → not approved; nothing sent |
| send balance − 0.005 SOL | hard BLOCK: would leave less than the 0.01 SOL reserve |
| `/sightline revoke g_c619`, then "send 0.01 SOL" | APPROVE: grant g_c619 revoked → not approved; nothing sent |
| `/sightline verify` | ✓ 11 entries, chain intact |

Recipient balance afterwards: exactly 0.01 SOL (only the granted payment landed).

`/sightline log 20`:

```
#1  APPROVE (hook) 0.01 SOL → 76nK…TRX1: no grant for SOL on devnet
#2  grant g_c619 created: 0.05 SOL/24h
#3  ALLOW (hook) 0.01 SOL → 76nK…TRX1: covered by grant g_c619
#4  ALLOW (execute) 0.01 SOL → 76nK…TRX1: covered by grant g_c619
#5  signing 0.01 SOL → 76nK…TRX1 via grant g_c619
#6  sent #5: 47yj661S…tbahD
#7  APPROVE (hook) 0.03 SOL → 76nK…TRX1: exceeds per-tx max of grant g_c619: 0.03 > 0.02
#8  APPROVE (hook) 4.9 SOL → 76nK…TRX1: exceeds per-tx max of grant g_c619: 4.9 > 0.02
#9  BLOCK (hook) 4.95492444 SOL → 76nK…TRX1: would leave less than the 0.01 SOL reserve
#10 grant g_c619 revoked
#11 APPROVE (hook) 0.01 SOL → 76nK…TRX1: grant g_c619 revoked
```
