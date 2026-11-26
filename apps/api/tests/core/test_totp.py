import base64

from angel.core.secret_box import seal, unseal
from angel.core.totp import (
    code_at,
    hash_recovery_code,
    matching_step,
    new_recovery_codes,
    new_secret,
    otpauth_uri,
)

# RFC 6238 Appendix B: SHA-1 түлхүүр "12345678901234567890", 8 цифрийн сүүлийн 6.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


def test_matches_the_rfc_6238_test_vectors() -> None:
    for at, expected in [(59, "287082"), (1111111109, "081804"), (2000000000, "279037")]:
        assert code_at(RFC_SECRET, at // 30) == expected


def test_accepts_one_step_of_clock_drift_and_nothing_further() -> None:
    now = 1_800_000_000.0
    step = int(now // 30)

    for drift in (-1, 0, 1):
        assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step + drift), now) == step + drift
    for drift in (-2, 2):
        assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step + drift), now) is None


def test_a_used_code_cannot_be_used_again() -> None:
    now = 1_800_000_000.0
    step = int(now // 30)

    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, step), now, after=step) is None


def test_secrets_are_sealed_and_only_open_with_the_same_key() -> None:
    secret = new_secret()
    sealed = seal("k" * 40, secret)

    assert secret not in sealed
    assert unseal("k" * 40, sealed) == secret
    assert unseal("x" * 40, sealed) is None
    assert unseal("k" * 40, "garbage") is None
    assert seal("k" * 40, secret) != sealed  # шинэ nonce


def test_recovery_codes_are_unique_and_compared_loosely() -> None:
    codes = new_recovery_codes()

    assert len(set(codes)) == 10
    assert hash_recovery_code(codes[0].upper().replace("-", " ")) == hash_recovery_code(codes[0])


def test_the_enrolment_uri_names_the_account_and_issuer() -> None:
    uri = otpauth_uri("ABC", "a@b.co")

    assert uri == "otpauth://totp/Angel:a%40b.co?secret=ABC&issuer=Angel"
