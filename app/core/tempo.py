"""
Date e orari: fuso di riferimento e formattazione per l'interfaccia.

Funzioni pure. Il fuso è quello di Roma perché tutte le scadenze del gioco
(fine asta, fine prestito, chiusura mercato) sono espresse in ora italiana.
"""

from datetime import datetime

import pytz

ROME_TZ = pytz.timezone("Europe/Rome")


def oggi():
    """Data odierna nel fuso di Roma. Unico punto in cui l'app legge "adesso",
    così i confronti fra date restano coerenti fra moduli."""
    return datetime.now(ROME_TZ).date()


def calcola_eta(data_nascita):
    if not data_nascita:
        return None
    riferimento = oggi()
    return (riferimento.year - data_nascita.year
            - ((riferimento.month, riferimento.day) < (data_nascita.month, data_nascita.day)))


def formatta_data_nascita_con_eta(data_nascita):
    """'07/03/1990 (36 anni)', o None se il dato non è ancora sincronizzato da Transfermarkt."""
    if not data_nascita:
        return None
    return f"{data_nascita.strftime('%d/%m/%Y')} ({calcola_eta(data_nascita)} anni)"


def formatta_scadenza_contratto(scadenza_contratto):
    """'1 anno e 3 mesi', arrotondando i mesi per eccesso (un giorno che avanza
    conta comunque come un mese intero). 'Scaduto' se la data è passata, None se
    il dato non è ancora sincronizzato da Transfermarkt."""
    if not scadenza_contratto:
        return None

    riferimento = oggi()
    if scadenza_contratto <= riferimento:
        return "Scaduto"

    mesi = (scadenza_contratto.year - riferimento.year) * 12 + (scadenza_contratto.month - riferimento.month)
    if scadenza_contratto.day < riferimento.day:
        mesi -= 1
    if scadenza_contratto.day != riferimento.day:
        mesi += 1

    anni, mesi = divmod(mesi, 12)

    parti = []
    if anni:
        parti.append(f"{anni} ann{'o' if anni == 1 else 'i'}")
    if mesi:
        parti.append(f"{mesi} mes{'e' if mesi == 1 else 'i'}")
    return " e ".join(parti)


def formatta_data(data_input):
    """Converte una data (stringa o datetime) in 'dd/mm/YYYY HH:MM'.

    Rimuove automaticamente millisecondi e fuso orario. Una stringa che non è
    una data ISO valida viene restituita invariata.
    """
    if data_input is None:
        return None

    if isinstance(data_input, str):
        data_input = data_input.split("+")[0].split("Z")[0].split(".")[0]
        try:
            data_input = datetime.fromisoformat(data_input)
        except ValueError:
            return data_input

    if isinstance(data_input, datetime):
        return data_input.strftime("%d/%m/%Y %H:%M")

    return str(data_input)
