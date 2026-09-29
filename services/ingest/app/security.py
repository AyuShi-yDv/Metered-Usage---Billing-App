import hashlib, hmac, secrets

def new_secret() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return secret[:10], secret

def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    # API keys are 256-bit random values, so a fast salted digest preserves
    # lookup latency while remaining infeasible to brute-force offline.
    digest = hashlib.sha256(salt + secret.encode()).digest()
    return salt.hex() + ":" + digest.hex()

def verify_secret(secret: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":", 1)
    candidate = hashlib.sha256(bytes.fromhex(salt_hex) + secret.encode()).digest()
    return hmac.compare_digest(candidate.hex(), digest_hex)
