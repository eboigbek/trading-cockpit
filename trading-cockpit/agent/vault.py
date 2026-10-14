"""Tresor-Modus: verschlüsselt alle Kontodaten mit einem Passwort.

Ist die Umgebungsvariable COCKPIT_PASSWORT gesetzt (bei GitHub als Secret),
werden state.json, trades.csv und cockpit.json nur noch verschlüsselt
gespeichert (Endung .enc). Wer das öffentliche Projekt ansieht, sieht nur
Zeichensalat. Das Cockpit entschlüsselt die Daten im Browser mit demselben
Passwort.

Verfahren: AES-256-GCM, Schlüssel aus dem Passwort per PBKDF2-SHA256
(310.000 Runden), für jede Datei neues Salt und neuer IV. Der Browser kann
das mit der eingebauten WebCrypto-Schnittstelle ohne Zusatzbibliothek lesen.

Sicherheitsregel: Liegt eine verschlüsselte Datei vor, aber das Passwort fehlt
oder ist falsch, bricht der Bot ab, statt mit einem leeren Konto neu zu
beginnen und die echten Daten zu überschreiben.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

ENV = "COCKPIT_PASSWORT"
ITERATIONS = 310_000
SUFFIX = ".enc"


class VaultError(RuntimeError):
    pass


def password() -> Optional[str]:
    pw = os.environ.get(ENV, "")
    return pw if pw else None


def active() -> bool:
    return password() is not None


def _key(pw: str, salt: bytes, iterations: int) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(pw.encode())


def encrypt(text: str, pw: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(pw, salt, ITERATIONS)).encrypt(iv, text.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return json.dumps({"v": 1, "alg": "AES-256-GCM", "kdf": "PBKDF2-SHA256", "iter": ITERATIONS,
                       "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)})


def decrypt(blob: str, pw: str) -> str:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        env = json.loads(blob)
        salt, iv, ct = (base64.b64decode(env[k]) for k in ("salt", "iv", "ct"))
        return AESGCM(_key(pw, salt, int(env["iter"]))).decrypt(iv, ct, None).decode("utf-8")
    except InvalidTag:
        raise VaultError("Falsches Passwort – Daten können nicht entschlüsselt werden.") from None
    except (ValueError, KeyError) as e:
        raise VaultError(f"Verschlüsselte Datei beschädigt: {e}") from None


def read_text(path: str) -> Optional[str]:
    """Liest eine Datei – verschlüsselt (bevorzugt) oder im Klartext. None, wenn keine existiert."""
    enc = path + SUFFIX
    if os.path.exists(enc):
        pw = password()
        if not pw:
            raise VaultError(f"{enc} ist verschlüsselt, aber {ENV} ist nicht gesetzt. "
                             "Abbruch, damit keine Daten überschrieben werden.")
        with open(enc, "r", encoding="utf-8") as f:
            return decrypt(f.read(), pw)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def write_text(path: str, text: str) -> None:
    """Schreibt atomar; im Tresor-Modus nur verschlüsselt (Klartext-Datei wird entfernt)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pw = password()
    target = path + SUFFIX if pw else path
    if not pw and os.path.exists(path + SUFFIX):
        raise VaultError(f"{path + SUFFIX} existiert, aber {ENV} fehlt – schreibe nicht im Klartext.")
    data = encrypt(text, pw) if pw else text
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    os.replace(tmp, target)
    if pw and os.path.exists(path):
        os.remove(path)  # Klartext nach Umstellung entfernen


def remove(path: str) -> None:
    for p in (path, path + SUFFIX):
        if os.path.exists(p):
            os.remove(p)
