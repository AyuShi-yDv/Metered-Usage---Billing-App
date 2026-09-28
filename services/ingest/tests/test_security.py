from app.security import hash_secret, new_secret, verify_secret
def test_secret_is_not_stored_plaintext():
    _, secret = new_secret(); stored = hash_secret(secret)
    assert secret not in stored
    assert verify_secret(secret, stored)
    assert not verify_secret(secret + "x", stored)
