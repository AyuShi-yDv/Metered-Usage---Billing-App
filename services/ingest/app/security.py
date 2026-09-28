import hashlib, hmac, secrets

def new_secret() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return secret[:10], secret

def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 310_000)
    return salt.hex() + ":" + digest.hex()

def verify_secret(secret: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt_hex), 310_000)
    return hmac.compare_digest(candidate.hex(), digest_hex)
