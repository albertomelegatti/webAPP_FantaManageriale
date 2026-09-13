/**
 * Movimenti di mercato: filtri, ordinamento e paginazione nel browser.
 *
 * Stesso impianto del listone. Il server manda i dati una volta sola e in forma
 * compatta; le righe le disegna questo file, venticinque per pagina. Prima ne
 * arrivavano seicento gia' in HTML, con il testo integrale di ogni movimento:
 * mezzo megabyte, quasi tutto nascosto al primo filtro.
 *
 * Il percorso e' sempre lo stesso, dai dati completi allo schermo:
 *
 *     movimenti -> filtra -> ordina -> pagina -> disegna
 *
 * Filtri e ordinamento lavorano su tutti i movimenti, non solo su quelli
 * visibili: una ricerca li trova anche se stanno a pagina venti.
 */

const MOVIMENTI_PER_PAGINA = 25;

/** Espande la tabella compatta del server in un movimento per oggetto. */
const espandiMovimenti = (compatti) =>
    compatti.righe.map((valori) => {
        const m = Object.fromEntries(compatti.campi.map((campo, i) => [campo, valori[i]]));
        // Precalcolato qui perche' due filtri su tre lo rileggono a ogni tasto.
        m.eventoCercabile = m.evento.toLowerCase();
        return m;
    });


document.addEventListener('DOMContentLoaded', function () {
    const corpo = document.getElementById('mercatoBody');
    const noResults = document.getElementById('noResults');
    const filtroStagione = document.getElementById('filterStagione');
    const filtroSquadra = document.getElementById('filterSquadra');
    const filtroEvento = document.getElementById('filterEvento');
    const bottoneData = document.getElementById('sortData');
    const iconaData = document.getElementById('sortIcon');

    const movimenti = espandiMovimenti(JSON.parse(document.getElementById('datiMovimenti').textContent));

    // I movimenti arrivano dal server gia' dal piu' recente, e la freccia lo
    // dichiara: il primo clic inverte, non riconferma.
    let crescente = false;

    const paginatore = creaPaginazione({
        contenitore: document.getElementById('paginazione'),
        perPagina: MOVIMENTI_PER_PAGINA,
        disegna: (dellaPagina) => {
            corpo.replaceChildren(...dellaPagina.map(disegnaRiga));
            nascondiFrecceInutili();
        },
        risaliA: corpo,
    });

    // --- Filtri -------------------------------------------------------------

    const criteriAttuali = () => ({
        stagione: filtroStagione.value.toLowerCase(),
        squadra: filtroSquadra.value.toLowerCase(),
        cercato: filtroEvento.value.toLowerCase(),
    });

    // La squadra si cerca dentro il testo del movimento: il legame non e'
    // registrato in una colonna, e questo e' l'unico modo disponibile oggi
    // (vedi app/repositories/movimenti.py).
    const passaFiltri = (m, criteri) =>
        (!criteri.stagione || m.stagione.toLowerCase() === criteri.stagione) &&
        (!criteri.squadra || m.eventoCercabile.includes(criteri.squadra)) &&
        (!criteri.cercato || m.eventoCercabile.includes(criteri.cercato));

    // --- Disegno delle righe ------------------------------------------------

    const elemento = (tag, classi, contenuto) => {
        const e = document.createElement(tag);
        // `type` prima di `class`: e' l'ordine in cui li scriveva il template,
        // e tenerlo uguale rende il markup confrontabile riga per riga.
        if (tag === 'button') e.type = 'button';
        if (classi) e.className = classi;
        if (contenuto !== undefined) e.textContent = contenuto;
        return e;
    };

    const disegnaRiga = (m) => {
        const riga = elemento('div', 'py-2.5 text-sm');

        const intestazione = elemento('div', 'flex items-center justify-between gap-2 text-[11px] text-muted');
        intestazione.append(elemento('span', '', m.data), elemento('span', '', m.stagione));

        const apertura = elemento('button', 'mercato-toggle mt-1 flex w-full items-start justify-between gap-2 text-left');
        const testo = elemento('span', 'evento-testo line-clamp-1 min-w-0 flex-1 break-words', m.evento);
        const freccia = elemento('i', 'bi bi-chevron-down chevron mt-0.5 shrink-0 text-muted transition-transform');
        apertura.append(testo, freccia);
        apertura.addEventListener('click', function () {
            testo.classList.toggle('line-clamp-1');
            freccia.classList.toggle('rotate-180');
        });

        riga.append(intestazione, apertura);
        return riga;
    };

    /** La freccia serve solo dove il testo e' davvero troncato dal line-clamp.
     *
     *  Va deciso dopo che le righe sono nel documento, perche' si misura
     *  l'altezza resa: prima dell'inserimento non c'e' niente da misurare. */
    const nascondiFrecceInutili = () => {
        corpo.querySelectorAll('.mercato-toggle').forEach(function (apertura) {
            const testo = apertura.querySelector('.evento-testo');
            if (testo.scrollHeight <= testo.clientHeight + 1) {
                apertura.querySelector('.chevron').classList.add('hidden');
            }
        });
    };

    // --- Aggiornamento ------------------------------------------------------

    const aggiorna = () => {
        const criteri = criteriAttuali();
        const selezionati = movimenti.filter((m) => passaFiltri(m, criteri));

        // Le date arrivano in forma ISO, quindi l'ordine alfabetico e quello
        // cronologico coincidono e non serve interpretarle.
        if (crescente) selezionati.sort((a, b) => a.data.localeCompare(b.data));
        else selezionati.sort((a, b) => b.data.localeCompare(a.data));

        noResults.classList.toggle('hidden', selezionati.length > 0);
        paginatore.mostra(selezionati);
    };

    // --- Collegamento dei controlli -----------------------------------------

    filtroStagione.addEventListener('change', aggiorna);
    filtroSquadra.addEventListener('change', aggiorna);
    filtroEvento.addEventListener('input', aggiorna);

    bottoneData.addEventListener('click', function () {
        crescente = !crescente;
        iconaData.textContent = crescente ? '▲' : '▼';
        aggiorna();
    });

    aggiorna();
});
