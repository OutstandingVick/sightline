"""Sightline: a Solana transaction firewall for Hermes Agent."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

TOOLSET = "sightline"
DEFAULT_RPC_URL = "https://api.devnet.solana.com"

STATUS_SCHEMA = {
    "name": "sightline_status",
    "description": (
        "Show the Sightline wallet status: Solana network, RPC URL and the "
        "wallet's public key. Never returns secret material."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
