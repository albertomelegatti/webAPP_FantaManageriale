/**
 * Paginazione condivisa.
 *
 * Tiene la pagina corrente, disegna la barra dei numeri e chiede alla pagina
 * ospite di disegnare gli elementi che le competono. Non sa nulla di cosa sta
 * impaginando: riceve una lista e una funzione che la disegna.
 *
 * Chi la usa fa sempre e solo due cose: filtra e ordina la propria lista, poi
 * la passa a `mostra()`. Della pagina corrente, dei numeri e delle frecce non
 * si occupa piu'.
 *
 *     const paginatore = creaPaginazione({
 *         contenitore: document.getElementById('paginazione'),
 *         perPagina: 25,
 *         disegna: (elementi) => { ... },
 *     });
 *     paginatore.mostra(giaFiltratiEOrdinati);
 *
 * Il contenitore arriva vuoto dal template, con addosso le sue classi di
 * impaginazione: la disposizione resta una scelta della pagina, i comandi che
 * ci stanno dentro li costruisce questo file.
 */

/**
 * I numeri di pagina da mostrare: sempre il primo, l'ultimo e quelli attorno
 * alla pagina corrente, con `null` dove la sequenza salta (si disegna come
 * puntini). Con venti pagine mostrarle tutte non ci starebbe su un telefono,
 * ma il primo e l'ultimo devono restare raggiungibili con un clic.
 */
const numeriDaMostrare = (corrente, totali) => {
    const scelti = new Set([1, totali, corrente - 1, corrente, corrente + 1]);
    // Vicino ai bordi la finestra si allarga, cosi' la fila non si accorcia.
    if (corrente <= 3) [2, 3, 4].forEach((n) => scelti.add(n));
    if (corrente >= totali - 2) [totali - 3, totali - 2, totali - 1].forEach((n) => scelti.add(n));

    const numeri = [...scelti].filter((n) => n >= 1 && n <= totali).sort((a, b) => a - b);
    const conPuntini = [];
    numeri.forEach(function (n, i) {
        if (i > 0 && n - numeri[i - 1] > 1) conPuntini.push(null);
        conPuntini.push(n);
    });
    return conPuntini;
};


const creaPaginazione = ({ contenitore, perPagina, disegna, risaliA = null }) => {
    let elementi = [];
    let pagina = 1;

    const freccia = (icona, etichetta) => {
        const bottone = document.createElement('button');
        bottone.type = 'button';
        bottone.className = 'freccia-pagina';
        bottone.setAttribute('aria-label', etichetta);
        const segno = document.createElement('i');
        segno.className = 'bi ' + icona;
        bottone.appendChild(segno);
        return bottone;
    };

    const precedente = freccia('bi-chevron-left', 'Pagina precedente');
    const successiva = freccia('bi-chevron-right', 'Pagina successiva');
    const numeri = document.createElement('div');
    numeri.className = 'flex flex-wrap items-center justify-center gap-1';
    contenitore.replaceChildren(precedente, numeri, successiva);

    const pagineTotali = () => Math.max(1, Math.ceil(elementi.length / perPagina));

    const disegnaNumeri = (totali) => {
        numeri.replaceChildren(...numeriDaMostrare(pagina, totali).map(function (n) {
            if (n === null) {
                const puntini = document.createElement('span');
                puntini.className = 'puntini-pagina';
                puntini.textContent = '…';
                return puntini;
            }

            const corrente = n === pagina;
            const bottone = document.createElement('button');
            bottone.type = 'button';
            bottone.className = corrente ? 'numero-pagina attivo' : 'numero-pagina';
            bottone.textContent = n;
            if (corrente) bottone.setAttribute('aria-current', 'page');
            else bottone.addEventListener('click', () => vaiA(n));
            return bottone;
        }));
    };

    const aggiorna = () => {
        const totali = pagineTotali();
        pagina = Math.min(pagina, totali);

        const inizio = (pagina - 1) * perPagina;
        disegna(elementi.slice(inizio, inizio + perPagina));

        disegnaNumeri(totali);
        contenitore.classList.toggle('hidden', totali === 1);
        precedente.disabled = pagina === 1;
        successiva.disabled = pagina === totali;
    };

    const vaiA = (nuovaPagina) => {
        pagina = nuovaPagina;
        aggiorna();
        if (risaliA) risaliA.scrollIntoView({ block: 'start', behavior: 'smooth' });
    };

    precedente.addEventListener('click', () => vaiA(pagina - 1));
    successiva.addEventListener('click', () => vaiA(pagina + 1));

    return {
        /** Rimpiazza gli elementi e riparte dalla prima pagina.
         *
         *  Riparte sempre: si chiama dopo un cambio di filtro o di ordinamento,
         *  e restare sulla ventesima pagina davanti a un elenco che ne ha due
         *  non direbbe nulla. */
        mostra(nuoviElementi) {
            elementi = nuoviElementi;
            pagina = 1;
            aggiorna();
        },
    };
};
