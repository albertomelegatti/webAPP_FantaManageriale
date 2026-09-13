"""Autenticazione: credenziali di admin e squadre."""


def hash_password_admin(cur, username: str) -> str | None:
    cur.execute("SELECT hash_password FROM admin WHERE username = %s;", (username,))
    riga = cur.fetchone()
    return riga["hash_password"] if riga else None


def credenziali_squadra(cur, username: str) -> dict | None:
    """Hash della password e nome della squadra con questo username."""
    cur.execute("SELECT hash_password, nome FROM squadra WHERE username = %s;", (username,))
    return cur.fetchone()


def hash_password_squadra(cur, username: str) -> str | None:
    cur.execute("SELECT hash_password FROM squadra WHERE username = %s;", (username,))
    riga = cur.fetchone()
    return riga["hash_password"] if riga else None


def aggiorna_password(cur, username: str, nuovo_hash: str) -> None:
    cur.execute("UPDATE squadra SET hash_password = %s WHERE username = %s;", (nuovo_hash, username))


def nome_da_username(cur, username: str) -> str:
    cur.execute("SELECT nome FROM squadra WHERE username = %s;", (username,))
    return cur.fetchone()["nome"]
