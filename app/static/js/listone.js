/**
 * Listone: filtri, ordinamento e paginazione nel browser.
 *
 * Il server manda i dati una volta sola e in forma compatta (i nomi dei campi
 * dichiarati una volta, poi una riga di valori per giocatore); le righe della
 * tabella le disegna questo file, venticinque per pagina. La pagina che arriva
 * dal server e' cosi' una frazione di prima, e il browser non deve costruire
 * cinquecento righe per mostrarne venticinque.
 *
 * Il percorso e' sempre lo stesso, dai dati completi allo schermo:
 *
 *     giocatori -> filtra -> ordina -> pagina -> disegna
 *
 * Filtri e ordinamento lavorano quindi su tutti i giocatori, non solo su quelli
 * visibili: cercare un nome lo trova anche se sta a pagina venti.
 */

const GIOCATORI_PER_PAGINA = 25;

// Gli stessi colori e le stesse icone delle macro `ruolo_colorato` e
// `contratto_icona` in templates/_macros.html, che restano in uso nelle altre
// pagine: toccare l'una senza l'altra fa divergere il listone dal resto
// dell'app. Il riferimento incrociato e' segnalato anche nel file delle macro.
const COLORI_RUOLO = {
    por: '#e0951b',
    dd: '#22a558', ds: '#22a558', dc: '#22a558', b: '#22a558',
    e: '#3f7fff', m: '#3f7fff', c: '#3f7fff',
    w: '#a855f7', t: '#a855f7',
    a: '#ef4444', pc: '#ef4444'
};

const ICONE_CONTRATTO = {
    'Indeterminato': 'bi-infinity',
    'Fanta-Prestito': 'bi-arrow-left-right',
    'Prestito Reale': 'bi-airplane',
    'Hold': 'bi-pause-circle',
    'Svincolato': 'bi-x-circle',
    'Primavera': 'bi-flower3'
};

// Il maiuscolo lo mette il CSS (`uppercase`), come nella macro `club_abbr`:
// qui il testo resta quello del club, ed e' anche la chiave di ordinamento.
const abbreviazioneClub = (club) => (club || '').slice(0, 3);

/** Espande la tabella compatta del server in un giocatore per oggetto. */
const espandiGiocatori = (compatti) =>
    compatti.righe.map((valori) => {
        const g = Object.fromEntries(compatti.campi.map((campo, i) => [campo, valori[i]]));
        // Precalcolate una volta qui perche' i filtri le rileggono a ogni tasto.
        g.nomeCercabile = g.nome.toLowerCase();
        g.ruoli = g.ruolo.split(',').map((r) => r.trim());
        return g;
    });

document.addEventListener('DOMContentLoaded', function () {
    const tabella = document.getElementById('listoneTable');
    const corpo = document.getElementById('listoneBody');
    const noResults = document.getElementById('noResults');
    const risultatiCount = document.getElementById('risultati-count');

    const filtroNome = document.getElementById('filtro-nome');
    const filtroContratto = document.getElementById('filtro-contratto');
    const filtroClub = document.getElementById('filtro-club');
    const filtroSquadraAtt = document.getElementById('filtro-squadra-att');
    const checkU21 = document.querySelectorAll('.filtro-u21-check');
    const chipRuolo = document.querySelectorAll('.chip-ruolo');


    const giocatori = espandiGiocatori(JSON.parse(document.getElementById('datiGiocatori').textContent));
    const loghiBase = tabella.dataset.loghiBase;
    const versioniLoghi = JSON.parse(tabella.dataset.loghiVersioni);

    // L'ordinamento iniziale e' quello in cui i giocatori arrivano dal server
    // (quotazione decrescente), segnalato dalla colonna QA gia' marcata.
    let ordinamento = null;
    let crescente = false;

    const paginatore = creaPaginazione({
        contenitore: document.getElementById('paginazione'),
        perPagina: GIOCATORI_PER_PAGINA,
        disegna: (dellaPagina) => corpo.replaceChildren(
            ...dellaPagina.map(disegnaRiga)),
        risaliA: tabella,
    });

    // --- Filtri -------------------------------------------------------------

    const criteriAttuali = () => ({
        nome: filtroNome.value.trim().toLowerCase(),
        contratto: filtroContratto.value,
        club: filtroClub.value,
        squadra: filtroSquadraAtt.value,
        u21: Array.from(checkU21).filter((c) => c.checked).map((c) => c.dataset.u21),
        ruoli: Array.from(chipRuolo).filter((c) => c.classList.contains('attivo')).map((c) => c.dataset.ruolo)
    });

    const passaFiltri = (g, criteri) =>
        (!criteri.nome || g.nomeCercabile.includes(criteri.nome)) &&
        (!criteri.contratto || g.tipo_contratto === criteri.contratto) &&
        (!criteri.club || g.club === criteri.club) &&
        (!criteri.squadra || g.squadra_att === criteri.squadra) &&
        (criteri.u21.length === 0 || criteri.u21.includes(g.u21)) &&
        (criteri.ruoli.length === 0 || g.ruoli.some((r) => criteri.ruoli.includes(r)));

    // --- Ordinamento --------------------------------------------------------

    // Come si ordina ogni colonna, per posizione nel <thead>. La colonna del
    // logo (indice 3) e' marcata `no-sort` nel template e infatti manca qui.
    // Le chiavi sono i valori che la cella mostra, cosi' l'ordine resta quello
    // che si vede.
    const ORDINAMENTI = {
        0: { chiave: (g) => g.nome, numerico: false },
        1: { chiave: (g) => g.ruolo, numerico: false },
        2: { chiave: (g) => abbreviazioneClub(g.club), numerico: false },
        4: { chiave: (g) => g.tipo_contratto || '', numerico: false },
        5: { chiave: (g) => g.quotazione, numerico: true }
    };

    const confronto = (colonna, versoCrescente) => {
        const verso = versoCrescente ? 1 : -1;
        return (a, b) => {
            const va = colonna.chiave(a);
            const vb = colonna.chiave(b);
            if (colonna.numerico) return verso * (va - vb);
            return verso * String(va).localeCompare(String(vb), 'it');
        };
    };

    // --- Disegno delle righe ------------------------------------------------

    const urlLogo = (username) => {
        const nome = username || 'svincolato';
        return loghiBase + nome + '.png?v=' + (versioniLoghi[nome] || 0);
    };

    const cella = (classi, figlio) => {
        const td = document.createElement('td');
        td.className = classi;
        if (figlio !== null) td.appendChild(figlio);
        return td;
    };

    const testo = (tag, classi, contenuto) => {
        const elemento = document.createElement(tag);
        if (classi) elemento.className = classi;
        elemento.textContent = contenuto;
        return elemento;
    };

    /** Un <span> colorato per ruolo, separati da una virgola attenuata. */
    const ruoloColorato = (ruoli) => {
        const contenitore = document.createElement('span');
        contenitore.className = 'whitespace-nowrap font-semibold';
        ruoli.forEach(function (ruolo, i) {
            if (i > 0) contenitore.appendChild(testo('span', 'text-muted', ','));
            const token = testo('span', '', ruolo);
            token.style.color = COLORI_RUOLO[ruolo.toLowerCase()] || 'var(--muted)';
            contenitore.appendChild(token);
        });
        return contenitore;
    };

    const iconaContratto = (tipo) => {
        if (!tipo) return null;
        // Contratto fuori dalla mappa: si mostra il testo, come fa la macro.
        if (!ICONE_CONTRATTO[tipo]) return testo('span', 'text-xs text-muted', tipo);

        const involucro = testo('span', 'inline-flex items-center align-middle text-muted', '');
        const icona = document.createElement('i');
        icona.className = 'bi ' + ICONE_CONTRATTO[tipo];
        involucro.appendChild(icona);
        return involucro;
    };

    const logoSquadra = (g) => {
        const logo = document.createElement('img');
        logo.src = urlLogo(g.squadra_username);
        logo.alt = g.squadra_username ? g.squadra_att : 'Svincolato';
        logo.className = 'mx-auto h-6 w-6 object-contain';
        logo.loading = 'lazy';
        return logo;
    };

    const disegnaRiga = (g) => {
        const riga = document.createElement('tr');
        riga.className = 'cursor-pointer hover:bg-panel-2';
        riga.appendChild(cella('overflow-hidden text-ellipsis whitespace-nowrap py-2 pr-1 font-medium',
                               document.createTextNode(g.nome)));
        riga.appendChild(cella('overflow-hidden py-2 pr-1', ruoloColorato(g.ruoli)));
        riga.appendChild(cella('overflow-hidden py-2 text-center text-muted',
                               g.club ? testo('span', 'whitespace-nowrap font-semibold uppercase text-muted',
                                              abbreviazioneClub(g.club)) : null));
        riga.appendChild(cella('py-2 text-muted', logoSquadra(g)));
        riga.appendChild(cella('py-2 text-center', iconaContratto(g.tipo_contratto)));
        riga.appendChild(cella('py-2 text-right tabular-nums', document.createTextNode(g.quotazione)));
        riga.addEventListener('click', () => apriScheda(g));
        return riga;
    };

    // --- Aggiornamento ------------------------------------------------------

    const aggiorna = () => {
        const criteri = criteriAttuali();
        const selezionati = giocatori.filter((g) => passaFiltri(g, criteri));

        // `sort` e' stabile: a parita' di chiave i giocatori restano nell'ordine
        // in cui arrivano dal server, quindi la stessa pagina mostra sempre gli
        // stessi giocatori.
        if (ordinamento !== null) selezionati.sort(confronto(ORDINAMENTI[ordinamento], crescente));

        risultatiCount.textContent = selezionati.length;
        noResults.classList.toggle('hidden', selezionati.length > 0);
        paginatore.mostra(selezionati);
    };

    // --- Scheda di dettaglio ------------------------------------------------

    const overlayGiocatore = document.getElementById('overlayGiocatore');
    const modalDetentoreRow = document.getElementById('modalDetentoreRow');
    const campo = (id) => document.getElementById(id);

    // Placeholder per i dati non ancora sincronizzati da Transfermarkt: testo
    // attenuato e corsivo per distinguerli a colpo d'occhio da un valore reale.
    const impostaCampoTransfermarkt = (elemento, valore) => {
        const nonSincronizzato = String(valore).startsWith('Non sincronizzat');
        elemento.textContent = valore;
        elemento.classList.toggle('text-muted', nonSincronizzato);
        elemento.classList.toggle('italic', nonSincronizzato);
        elemento.classList.toggle('font-medium', !nonSincronizzato);
    };

    const mostraSquadra = (elemento, nome, username) => {
        const logo = document.createElement('img');
        logo.src = urlLogo(username);
        logo.alt = '';
        logo.className = 'h-5 w-5 object-contain';
        elemento.replaceChildren(logo, testo('span', '', nome || 'Svincolato'));
    };

    const apriScheda = (g) => {
        campo('modalNome').textContent = g.nome;
        campo('modalRuolo').textContent = g.ruoli.join(', ');
        campo('modalClub').textContent = g.club;
        mostraSquadra(campo('modalSquadra'), g.squadra_att, g.squadra_username);

        const detentoreDiverso = g.detentore && g.detentore !== g.squadra_att;
        if (detentoreDiverso) mostraSquadra(campo('modalDetentore'), g.detentore, g.detentore_username);
        modalDetentoreRow.classList.toggle('hidden', !detentoreDiverso);
        modalDetentoreRow.classList.toggle('flex', detentoreDiverso);

        campo('modalContratto').textContent = g.tipo_contratto || '-';
        impostaCampoTransfermarkt(campo('modalDataNascita'), g.data_nascita);
        impostaCampoTransfermarkt(campo('modalScadenzaContratto'), g.scadenza_contratto_reale);
        impostaCampoTransfermarkt(campo('modalValoreMercato'), g.valore_mercato);
        campo('modalQuotazione').textContent = g.quotazione;
        campo('modalCosto').textContent = g.costo;

        overlayGiocatore.classList.remove('hidden');
        overlayGiocatore.classList.add('flex');
    };

    const chiudiScheda = () => {
        overlayGiocatore.classList.add('hidden');
        overlayGiocatore.classList.remove('flex');
    };

    // --- Collegamento dei controlli -----------------------------------------

    filtroNome.addEventListener('input', aggiorna);
    filtroContratto.addEventListener('change', aggiorna);
    filtroClub.addEventListener('change', aggiorna);
    filtroSquadraAtt.addEventListener('change', aggiorna);
    checkU21.forEach((c) => c.addEventListener('change', aggiorna));
    chipRuolo.forEach((chip) => chip.addEventListener('click', function () {
        chip.classList.toggle('attivo');
        aggiorna();
    }));

    const intestazioni = tabella.querySelectorAll('thead th');
    intestazioni.forEach(function (intestazione, indice) {
        if (!ORDINAMENTI[indice]) return;
        intestazione.addEventListener('click', function () {
            crescente = !intestazione.classList.contains('asc');
            ordinamento = indice;
            intestazioni.forEach((h) => h.classList.remove('asc', 'desc'));
            intestazione.classList.add(crescente ? 'asc' : 'desc');
            aggiorna();
        });
    });

    document.getElementById('btnChiudiGiocatore').addEventListener('click', chiudiScheda);
    overlayGiocatore.addEventListener('click', function (e) {
        if (e.target === overlayGiocatore) chiudiScheda();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') chiudiScheda();
    });

    aggiorna();
});
