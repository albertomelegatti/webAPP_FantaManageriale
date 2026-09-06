"""
Gerarchia delle eccezioni di dominio.

Un errore di dominio è una condizione *attesa*, prevista dalle regole del gioco:
crediti insufficienti, slot esauriti, un'asta scaduta mentre la pagina era
aperta. Non è un bug, ed è distinta da un errore imprevisto: la prima si mostra
all'utente con un messaggio comprensibile, la seconda va scritta nei log con lo
stack trace.

Oggi queste condizioni sono gestite con un `flash()` seguito da un `return`
sparso nel corpo delle route. Sollevare un'eccezione permette invece ai service
(Fase 6) di dichiarare il fallimento senza sapere nulla di Flask, lasciando alla
route — o all'error handler centralizzato — il compito di tradurlo in una
risposta.
"""


class ErroreDominio(Exception):
    """Errore atteso, con un messaggio mostrabile all'utente.

    Il messaggio si passa al costruttore; se omesso viene usato quello di
    default della classe.
    """

    messaggio_default = "❌ Si è verificato un errore."

    def __init__(self, messaggio=None):
        self.messaggio_utente = messaggio or self.messaggio_default
        super().__init__(self.messaggio_utente)


class CreditiInsufficienti(ErroreDominio):
    messaggio_default = "❌ Crediti insufficienti per completare l'operazione."


class SlotEsauriti(ErroreDominio):
    messaggio_default = "❌ Non ci sono slot disponibili."


class SlotPrestitiEsauriti(ErroreDominio):
    messaggio_default = "❌ Non ci sono slot prestiti disponibili."


class RisorsaNonTrovata(ErroreDominio):
    messaggio_default = "❌ Elemento non trovato."


class OperazioneNonPermessa(ErroreDominio):
    """L'operazione è valida in generale, ma non in questo stato o per questa squadra."""

    messaggio_default = "❌ Operazione non consentita."


class StatoNonPiuValido(ErroreDominio):
    """Qualcosa è cambiato mentre la pagina era aperta: asta scaduta, scambio
    già annullato, prestito già terminato."""

    messaggio_default = "❌ La situazione è cambiata nel frattempo, ricarica la pagina."


class SezioneChiusa(ErroreDominio):
    """Mercato o aste chiusi dall'admin."""

    messaggio_default = "❌ Questa sezione è chiusa."
