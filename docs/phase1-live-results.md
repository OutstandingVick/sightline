# Phase 1 live devnet results (2026-11-07)

| Check | Result |
|---|---|
| `pytest` live test, 0.001 SOL to a fresh address | `ortUmreneWk1sn34m9Snf7bwhHCqTeACSQ7NVmVvHStpBxHh5B1dQhQuXDeZcw3eWUCBWnWionHSb2sdAw2argS` |
| Test mint created + 1000 minted | `2stAXgSvf7HwNDupeyzH7YgWQWsjhhbHtXKQnikpoTk6nHMVugDzLmYBPy4qT6uMgTFhnkkwTg1PhbbGiQJ6S2fv` |
| `execute_intent` SPL transfer to an address with no ATA | `2CiPjsLz34kNQKCoHGDE7RgU2dEiT3pziW6VK67fakWDc5cSZY2srru8DG7M7a1xzH4ZmBXzWv9jYMg1F3iH586b` |
| Hermes chat: "send 0.01 SOL to …" | `5v82ZkT2H1dB8fbJ8B1kuvgpJALABpNmMDkYVPkEMdtESkVVsE8dYVbNW15qnCD6fabUAyhHepmvj2thiUkRQeCe` |
| Hermes chat: "send 1 of token 53vs… to …" (no ATA) | `4dXSTT589u3DeoAXwsEMLaCeFVnF1dZ9wzeuxvo1ZyRKzzHhAadqdF8FcX2UKSiCQ4ibvFH52zoHPCa1DDzMqDqK` |
| Hermes chat: "what's my balance?" | called `sightline_balance`; SOL + test token listed |

Explorer: `https://explorer.solana.com/tx/<sig>?cluster=devnet`

Model used for chat checks: `meituan/longcat-2.5:free` via Nous Portal.
