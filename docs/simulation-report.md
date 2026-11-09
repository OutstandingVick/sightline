# SimulationReport

Fields (all JSON-safe; Decimals are strings):

| Field | Type | Meaning |
|---|---|---|
| `ok` | bool | Simulation succeeded and balance data was complete |
| `error` | str \| null | Human-readable reason when `ok` is false |
| `logs` | list[str] | Last 30 program log lines (each ≤300 chars) |
| `compute_units` | int \| null | `unitsConsumed` |
| `fee_lamports` | int | `getFeeForMessage`, falling back to the simulation's `fee` |
| `sol_delta_lamports` | int | Our wallet's SOL change, fee included (negative = out) |
| `token_deltas` | list | Our wallet's token changes: `{mint, symbol, delta_ui, decimals}` |
| `programs` | list[str] | Program ids invoked by top-level instructions, first-use order |
| `unknown_programs` | list[str] | Subset of `programs` not in the known map |
| `writable_accounts` | list[str] | From the message header |
| `creates_accounts` | bool | Any account created with data |
| `created_accounts` | list[str] | Those accounts |
| `rent_lamports` | int | Lamports moved into created accounts |
| `recipient_received` | str \| null | What the intent's recipient gains, UI units |
| `slot` | int \| null | Slot the simulation ran against |
| `sol_post_lamports` | int \| null | Our SOL balance after the tx (firewall reserve check) |
| `instructions` | list[str] | Decoded top-level instructions, e.g. `Token.TransferChecked` (firewall) |

Each `token_deltas` entry also has `pre_ui`: our balance of that mint before the tx
(firewall's 90% rule).

## Sample (devnet, "preview 1 USDC to a fresh address", and a 50 SOL overdraft)

```json
{
  "usdc_new_ata": {
    "summary": "You send 1 USDC to 4FRE…wgaa.\nCreates their USDC account (≈0.00148844 SOL rent). Network fee ≈ 0.000005 SOL. Programs: Associated Token, Token.",
    "would_succeed": true,
    "sent": false,
    "intent": {
      "kind": "transfer_spl",
      "recipient": "4FREK3kWJyJNbMcDrHK3JJKuWY7YUznahDxRaBp7wgaa",
      "amount": "1",
      "mint": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
      "decimals": 6,
      "symbol": "USDC"
    },
    "simulation": {
      "ok": true,
      "error": null,
      "logs": [
        "Program ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL invoke [1]",
        "Program log: CreateIdempotent",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [2]",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA consumed 179 of 394571 compute units",
        "Program return: TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA pQAAAAAAAAA=",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
        "Program 11111111111111111111111111111111 invoke [2]",
        "Program 11111111111111111111111111111111 success",
        "Program log: Initialize the associated token account",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [2]",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA consumed 37 of 389482 compute units",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [2]",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA consumed 233 of 387019 compute units",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
        "Program ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL consumed 13518 of 400000 compute units",
        "Program ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL success",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [1]",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA consumed 105 of 386482 compute units",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success"
      ],
      "compute_units": 13623,
      "fee_lamports": 5000,
      "sol_delta_lamports": -1493440,
      "token_deltas": [
        {
          "mint": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
          "symbol": "USDC",
          "delta_ui": "-1",
          "decimals": 6
        }
      ],
      "programs": [
        "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
      ],
      "unknown_programs": [],
      "writable_accounts": [
        "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg",
        "6ZttwaETEszn2JFNaaFZ9ixw41Gc5S5gC5oEjAU7F9NB",
        "AJX8fL2p3RG74SRCfcqMYJUu63hdCqgBBYx3YRk2xHKp"
      ],
      "creates_accounts": true,
      "created_accounts": [
        "AJX8fL2p3RG74SRCfcqMYJUu63hdCqgBBYx3YRk2xHKp"
      ],
      "rent_lamports": 1488440,
      "recipient_received": "1"
    }
  },
  "overdraft": {
    "summary": "✗ Simulation failed: insufficient funds. Nothing was sent.",
    "simulation": {
      "ok": false,
      "error": "insufficient funds",
      "logs": [
        "Program 11111111111111111111111111111111 invoke [1]",
        "Transfer: insufficient lamports 4979929440, need 50000000000",
        "Program 11111111111111111111111111111111 failed: custom program error: 0x1"
      ],
      "compute_units": 150,
      "fee_lamports": 5000,
      "sol_delta_lamports": 0,
      "token_deltas": [],
      "programs": [
        "11111111111111111111111111111111"
      ],
      "unknown_programs": [],
      "writable_accounts": [
        "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg",
        "4FREK3kWJyJNbMcDrHK3JJKuWY7YUznahDxRaBp7wgaa"
      ],
      "creates_accounts": false,
      "created_accounts": [],
      "rent_lamports": 0,
      "recipient_received": null
    }
  }
}
```
