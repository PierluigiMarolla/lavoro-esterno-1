"""Test per app.services.phone_crypto: normalizzazione, cifratura, hashing."""

from __future__ import annotations

import pytest

from app.services.phone_crypto import (
    PhoneCryptoError,
    decrypt_phone,
    encrypt_phone,
    normalize_phone,
    phone_lookup_hash,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+39 333 1234567", "+393331234567"),
        ("0039-333-1234567", "+393331234567"),
        ("333 1234567", "+393331234567"),
        ("3331234567", "+393331234567"),
        ("+39(333)1234567", "+393331234567"),
        ("350\u200b8490562", "+393508490562"),
        ("tel:+393923508765", "+393923508765"),
    ],
)
def test_normalize_phone_variants_converge(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_normalize_phone_rejects_empty() -> None:
    with pytest.raises(PhoneCryptoError):
        normalize_phone("")
    with pytest.raises(PhoneCryptoError):
        normalize_phone("   ")


def test_normalize_phone_rejects_invalid_format() -> None:
    with pytest.raises(PhoneCryptoError):
        normalize_phone("not-a-phone-number")


def test_encrypt_decrypt_roundtrip() -> None:
    original = "+39 333 1234567"
    encrypted = encrypt_phone(original)
    assert isinstance(encrypted, bytes)
    assert encrypted != original.encode("utf-8")

    decrypted = decrypt_phone(encrypted)
    assert decrypted == normalize_phone(original)


def test_encrypt_is_non_deterministic_but_decrypts_consistently() -> None:
    """Due cifrature dello stesso numero devono produrre ciphertext diversi
    (nonce casuale) ma decifrare sempre allo stesso valore normalizzato."""
    original = "+393331234567"
    encrypted_a = encrypt_phone(original)
    encrypted_b = encrypt_phone(original)

    assert encrypted_a != encrypted_b
    assert decrypt_phone(encrypted_a) == decrypt_phone(encrypted_b) == original


def test_phone_lookup_hash_is_deterministic_across_formats() -> None:
    variants = ["+39 333 1234567", "0039-333-1234567", "3331234567"]
    hashes = {phone_lookup_hash(v) for v in variants}
    assert len(hashes) == 1


def test_phone_lookup_hash_differs_for_different_numbers() -> None:
    hash_a = phone_lookup_hash("+393331234567")
    hash_b = phone_lookup_hash("+393339999999")
    assert hash_a != hash_b


def test_phone_lookup_hash_is_hex_sha256_length() -> None:
    h = phone_lookup_hash("+393331234567")
    assert len(h) == 64
    int(h, 16)  # solleva ValueError se non è esadecimale valido
