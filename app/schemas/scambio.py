"""Schema del form di proposta di scambio."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Il menu del frontend mostra etichette discorsive, l'enum del database usa
# valori brevi. La conversione stava dentro la route, in una funzione locale.
TIPO_PRESTITO_DA_ETICHETTA = {
    'Secco': 'secco',
    'Con diritto di riscatto': 'diritto_di_riscatto',
    'Diritto': 'diritto_di_riscatto',
    'Con obbligo di riscatto': 'obbligo_di_riscatto',
    'Obbligo': 'obbligo_di_riscatto',
}

# Un prestito scade il 1 luglio dell'anno scelto, a fine giornata.
MESE_SCADENZA, GIORNO_SCADENZA = 7, 1


def _intero(valore, default=0) -> int:
    """Un campo numerico vuoto vale zero; uno non numerico anche.

    E' il comportamento che il codice precedente otteneva con
    `int(request.form.get(...) or 0)`, con la differenza che li' un valore non
    numerico sollevava ValueError e faceva fallire la richiesta.
    """
    if valore in (None, ""):
        return default
    try:
        return int(valore)
    except (TypeError, ValueError):
        return default


def _interi(valori) -> list[int]:
    return [int(v) for v in (valori or []) if str(v).isdigit()]


class PrestitoProposto(BaseModel):
    """Un prestito incluso in una proposta di scambio.

    Nasce sospeso: si attiva solo se la proposta viene accettata.
    """

    giocatore: int
    tipo: str
    crediti_riscatto: int = 0
    data_fine: datetime

    @field_validator("crediti_riscatto")
    @classmethod
    def _secco_non_ha_riscatto(cls, v, info):
        """Un prestito secco non prevede riscatto: qualunque cifra inserita nel
        form va ignorata, non salvata."""
        if info.data.get("tipo") == "secco":
            return 0
        return v


class PropostaScambio(BaseModel):
    """Una proposta di scambio, come arriva dal form.

    Valida la forma dei dati, non la loro coerenza col gioco: che le pick
    esistano, o che i crediti bastino, lo verificano repository e service.
    """

    squadra_destinataria: str = Field(min_length=1)
    crediti_offerti: int = 0
    crediti_richiesti: int = 0
    giocatori_offerti: list[int] = Field(default_factory=list)
    giocatori_richiesti: list[int] = Field(default_factory=list)
    pick_offerta: list[int] = Field(default_factory=list)
    pick_richiesta: list[int] = Field(default_factory=list)
    messaggio: str = ""
    # Chi presta e' la squadra destinataria per i prestiti richiesti, la
    # proponente per quelli offerti.
    prestiti_richiesti: list[PrestitoProposto] = Field(default_factory=list)
    prestiti_offerti: list[PrestitoProposto] = Field(default_factory=list)

    @property
    def offerta_vuota(self) -> bool:
        return not (self.giocatori_offerti or self.crediti_offerti
                    or self.pick_offerta or self.prestiti_offerti)

    @property
    def richiesta_vuota(self) -> bool:
        return not (self.giocatori_richiesti or self.crediti_richiesti
                    or self.pick_richiesta or self.prestiti_richiesti)

    @property
    def e_vuota(self) -> bool:
        """Una proposta in cui non si offre ne' si chiede nulla non ha senso."""
        return self.offerta_vuota and self.richiesta_vuota

    @classmethod
    def da_form(cls, form, anni_ammessi: list[int], anno_default: int) -> "PropostaScambio":
        """Costruisce la proposta dai campi grezzi del form.

        I due blocchi prestito del form, ciascuno con una parte richiesta e una
        offerta, sono quattro combinazioni della stessa struttura: qui vengono
        percorse in un ciclo invece che ripetute a mano.
        """
        richiesti, offerti = [], []
        for blocco in (1, 2):
            if form.get(f"enable_prestito{blocco}") is None:
                continue
            for verso, destinazione in (("richiesto", richiesti), ("offerto", offerti)):
                # il suffisso del campo data segue il genere dell'etichetta
                suffisso_data = "richiesta" if verso == "richiesto" else "offerta"
                prestito = _prestito_da_form(
                    form, blocco, verso, suffisso_data, anni_ammessi, anno_default)
                if prestito:
                    destinazione.append(prestito)

        return cls(
            squadra_destinataria=(form.get("squadra_destinataria") or "").strip(),
            crediti_offerti=_intero(form.get("crediti_offerti")),
            crediti_richiesti=_intero(form.get("crediti_richiesti")),
            giocatori_offerti=_interi(form.getlist("giocatori_offerti")),
            giocatori_richiesti=_interi(form.getlist("giocatori_richiesti")),
            pick_offerta=_interi(form.getlist("pick_offerta")),
            pick_richiesta=_interi(form.getlist("pick_richiesta")),
            messaggio=(form.get("messaggio") or "").strip(),
            prestiti_richiesti=richiesti,
            prestiti_offerti=offerti,
        )


def _anno_scadenza(valore, anni_ammessi: list[int], anno_default: int) -> datetime:
    """Il 1 luglio dell'anno scelto, a fine giornata.

    Un anno fuori da quelli ammessi ricade sul predefinito invece di essere
    rifiutato: il campo arriva da un menu a tendina, quindi un valore diverso
    significa richiesta manipolata, non errore dell'utente.
    """
    anno = None
    if valore:
        try:
            anno = int(str(valore)[:4])
        except ValueError:
            anno = None
    if anno not in anni_ammessi:
        anno = anno_default
    return datetime(anno, MESE_SCADENZA, GIORNO_SCADENZA, 23, 59, 59)


def _prestito_da_form(form, blocco: int, verso: str, suffisso_data: str,
                      anni_ammessi: list[int], anno_default: int):
    """Un prestito, se il form ne descrive uno completo. None altrimenti."""
    giocatore = form.get(f"prestito{blocco}_{verso}")
    etichetta = (form.get(f"prestito{blocco}_tipo_{verso}") or "").strip()
    if not giocatore or not etichetta:
        return None

    tipo = TIPO_PRESTITO_DA_ETICHETTA.get(etichetta)
    if not tipo:
        return None

    return PrestitoProposto(
        giocatore=int(giocatore),
        tipo=tipo,
        crediti_riscatto=_intero(form.get(f"prestito{blocco}_riscatto_{verso}")),
        data_fine=_anno_scadenza(
            form.get(f"prestito{blocco}_data_fine_{suffisso_data}"), anni_ammessi, anno_default),
    )
