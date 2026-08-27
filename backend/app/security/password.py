"""Hashing e verifica delle password con Argon2 (via argon2-cffi).

Argon2id (default di `PasswordHasher`) è la scelta raccomandata da OWASP per
il password hashing: resistente sia ad attacchi GPU (memory-hard) sia a
side-channel (variante "id" combina le proprietà di Argon2i e Argon2d).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Restituisce l'hash Argon2 (stringa auto-descrittiva, include salt e
    parametri) da salvare in `users.password_hash`."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una password in chiaro contro il suo hash. Non solleva mai
    eccezioni verso il chiamante: restituisce semplicemente True/False."""
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash malformato/incompatibile: trattato come mismatch, non come
        # errore di sistema, per non far trapelare dettagli utili a un
        # attaccante tramite differenze di comportamento.
        return False
