"""Wallet.

Future role: load the keypair once, expose only the public key, and sign
transactions on behalf of the firewall. The secret key never leaves this
module and is never returned to the model.
"""
