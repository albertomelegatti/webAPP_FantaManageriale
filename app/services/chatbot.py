import os
from openai import OpenAI
from dotenv import load_dotenv

from app.core.logging import get_logger
from app.core.tempo import oggi
from app.services import chatbot_dati

logger = get_logger(__name__)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Modelli gratuiti del catalogo NVIDIA. Il modello e' configurabile perche' quel
# catalogo cambia senza preavviso: deepseek-v3.1-terminus e' stato ritirato e
# il chatbot rispondeva solo "errore" finche' qualcuno non toccava il codice.
CHATBOT_BASE_URL = os.getenv("CHATBOT_BASE_URL", "https://integrate.api.nvidia.com/v1")
CHATBOT_MODEL = os.getenv("CHATBOT_MODEL", "deepseek-ai/deepseek-v4.1-flash")

# Quanta conversazione si rimanda al modello. La cronologia la tiene il browser
# (il server non conserva stato fra le richieste), quindi va limitata qui: e'
# testo che arriva dal client.
MESSAGGI_MAX = 12
CARATTERI_MAX_MESSAGGIO = 2000

# Giri domanda-strumento-risposta concessi per una risposta: una domanda che
# confronta due squadre ne usa due o tre, oltre c'e' un modello che gira a vuoto.
GIRI_STRUMENTI_MAX = 5

_client = None


def _get_client():
    """Creato al primo uso: senza chiave l'import fallirebbe e con lui l'app
    intera, mentre cosi' si rompe solo il chatbot."""
    global _client
    if _client is None:
        _client = OpenAI(base_url=CHATBOT_BASE_URL, api_key=OPENAI_API_KEY, timeout=60)
    return _client


# Carica regolamento
# Il file vive nella radice del package (app/regolamento.txt), non accanto a
# questo modulo: risolviamo il percorso partendo da lì invece che da __file__,
# altrimenti spostare il modulo farebbe fallire la lettura in silenzio.
REGOLAMENTO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "regolamento.txt"
)


def load_regolamento():
    try:
        with open(REGOLAMENTO_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "⚠️ Nessun regolamento disponibile."

REGOLAMENTO = load_regolamento()


def _prompt_di_sistema() -> str:
    squadre = chatbot_dati.nomi_squadre()
    elenco_squadre = ", ".join(squadre) if squadre else "non disponibili"
    return (
        "Sei l'assistente della lega di Fantacalcio Manageriale \"Lega dei Guru Tattici\". "
        f"Oggi è il {oggi().strftime('%d/%m/%Y')}.\n\n"
        "Rispondi sempre in italiano, in modo chiaro e conciso. Usa il markdown con misura: "
        "grassetto per i numeri chiave, elenchi puntati per più voci, tabelle solo per "
        "confronti fra più squadre o giocatori.\n\n"
        "Due fonti, da non confondere:\n"
        "1. Il REGOLAMENTO qui sotto, per le regole. Quando rispondi su una regola, cita la "
        "sezione (es. \"Mercato › Svincoli\"). Se la regola non c'è, rispondi che non è "
        "specificato nel regolamento e suggerisci di chiedere al direttore di lega: non "
        "inventare regole e non usare regole del fantacalcio classico.\n"
        "2. Gli STRUMENTI, per i dati attuali della lega (crediti, rose, giocatori, movimenti, "
        "aste, albo d'oro, stato del mercato). Per qualunque dato attuale chiama uno strumento: "
        "non dedurlo e non ricordarlo dai messaggi precedenti se potrebbe essere cambiato. "
        "Se uno strumento risponde con un errore, dillo.\n\n"
        "Le domande possono combinare le due cose (es. \"quanto mi costa svincolare X?\": "
        "prendi la quotazione con lo strumento e applica la regola del regolamento, mostrando "
        "il calcolo).\n\n"
        f"Squadre della lega: {elenco_squadre}.\n\n"
        f"--- REGOLAMENTO ---\n{REGOLAMENTO}\n--- FINE REGOLAMENTO ---"
    )


def pulisci_cronologia(messaggi) -> list[dict]:
    """La conversazione inviata dal browser, ridotta a cio' che il modello puo'
    ricevere: solo ruoli user/assistant (un 'system' dal client riscriverebbe
    le istruzioni), testi troncati, ultimi MESSAGGI_MAX, e la prima battuta
    sempre dell'utente."""
    puliti = []
    for m in messaggi if isinstance(messaggi, list) else []:
        if not isinstance(m, dict):
            continue
        ruolo, testo = m.get("role"), m.get("content")
        if ruolo not in ("user", "assistant") or not isinstance(testo, str) or not testo.strip():
            continue
        puliti.append({"role": ruolo, "content": testo.strip()[:CARATTERI_MAX_MESSAGGIO]})

    puliti = puliti[-MESSAGGI_MAX:]
    while puliti and puliti[0]["role"] != "user":
        puliti.pop(0)
    return puliti


def get_answer(messaggi) -> str:
    """Risposta all'ultimo messaggio della conversazione.

    `messaggi` e' la cronologia [{role, content}] o, per compatibilita', una
    domanda singola come stringa.
    """
    if isinstance(messaggi, str):
        messaggi = [{"role": "user", "content": messaggi}]
    conversazione = pulisci_cronologia(messaggi)

    if not conversazione or conversazione[-1]["role"] != "user":
        return "Devi inserire una domanda valida."

    try:
        client = _get_client()
        messaggi_modello = [{"role": "system", "content": _prompt_di_sistema()}, *conversazione]

        for giro in range(GIRI_STRUMENTI_MAX + 1):
            # All'ultimo giro niente strumenti: il modello deve rispondere con
            # quello che ha raccolto finora.
            con_strumenti = giro < GIRI_STRUMENTI_MAX
            completion = client.chat.completions.create(
                model=CHATBOT_MODEL,
                messages=messaggi_modello,
                **({"tools": chatbot_dati.STRUMENTI} if con_strumenti else {}),
                temperature=0.2,
                top_p=0.7,
                max_tokens=1500,
                stream=False,
            )
            messaggio = completion.choices[0].message
            chiamate = messaggio.tool_calls or []

            if not chiamate:
                testo = (messaggio.content or "").strip()
                return testo or "Non sono riuscito a formulare una risposta, riprova."

            messaggi_modello.append({
                "role": "assistant",
                "content": messaggio.content or "",
                "tool_calls": [{
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                } for c in chiamate],
            })
            for c in chiamate:
                logger.info("Chatbot: strumento %s(%s)", c.function.name, c.function.arguments)
                messaggi_modello.append({
                    "role": "tool",
                    "tool_call_id": c.id,
                    "content": chatbot_dati.esegui(c.function.name, c.function.arguments),
                })

        return "Non sono riuscito a formulare una risposta, riprova."
    except Exception:
        logger.exception("Errore chatbot")
        return "⚠️ Errore nella comunicazione con il modello."
