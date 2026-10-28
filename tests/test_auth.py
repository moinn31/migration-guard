from backend.auth import hash_password, verify_password
def test_password_hash_round_trip():
    hashed=hash_password('secret-password')
    assert hashed != 'secret-password'
    assert verify_password('secret-password', hashed)
    assert not verify_password('wrong', hashed)
