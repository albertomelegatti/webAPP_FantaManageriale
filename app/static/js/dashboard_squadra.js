document.addEventListener('DOMContentLoaded', function () {
    const loghiBase = document.getElementById('paginaSquadra').dataset.loghiBase;
    const overlayGiocatore = document.getElementById('overlayGiocatore');
    const btnChiudiGiocatore = document.getElementById('btnChiudiGiocatore');
    const modalNome = document.getElementById('modalNome');
    const modalCampioncino = document.getElementById('modalCampioncino');
    const modalRuolo = document.getElementById('modalRuolo');
    const modalClub = document.getElementById('modalClub');
    const modalSquadra = document.getElementById('modalSquadra');
    const modalDetentoreRow = document.getElementById('modalDetentoreRow');
    const modalDetentore = document.getElementById('modalDetentore');
    const modalContratto = document.getElementById('modalContratto');
    const modalDataNascita = document.getElementById('modalDataNascita');
    const modalScadenzaContratto = document.getElementById('modalScadenzaContratto');
    const modalValoreMercato = document.getElementById('modalValoreMercato');
    const modalQuotazione = document.getElementById('modalQuotazione');
    const modalCosto = document.getElementById('modalCosto');

    // Placeholder per i dati non ancora sincronizzati da Transfermarkt: testo
    // attenuato e corsivo per distinguerli a colpo d'occhio da un valore reale.
    const impostaCampoTransfermarkt = (elemento, valore) => {
        const nonSincronizzato = String(valore).startsWith('Non sincronizzat');
        elemento.textContent = valore;
        elemento.classList.toggle('text-muted', nonSincronizzato);
        elemento.classList.toggle('italic', nonSincronizzato);
        elemento.classList.toggle('font-medium', !nonSincronizzato);
    };

    const logoUrl = (username) => loghiBase + (username || 'svincolato') + '.png';

    const squadraHtml = (nome, username) =>
        '<img src="' + logoUrl(username) + '" alt="" class="h-5 w-5 object-contain">' +
        '<span>' + (nome || 'Svincolato') + '</span>';

    const apriCardGiocatore = (info) => {
        modalNome.textContent = info.nome;
        mostraCampioncinoModal(modalCampioncino, info.campioncino);
        modalRuolo.textContent = info.ruolo.split(',').map(r => r.trim()).join(', ');
        modalClub.textContent = info.club;
        modalSquadra.innerHTML = squadraHtml(info.squadra_att, info.squadra_username);
        if (info.detentore && info.detentore !== info.squadra_att) {
            modalDetentore.innerHTML = squadraHtml(info.detentore, info.detentore_username);
            modalDetentoreRow.classList.remove('hidden');
            modalDetentoreRow.classList.add('flex');
        } else {
            modalDetentoreRow.classList.add('hidden');
            modalDetentoreRow.classList.remove('flex');
        }
        modalContratto.textContent = info.tipo_contratto || '-';
        impostaCampoTransfermarkt(modalDataNascita, info.data_nascita);
        impostaCampoTransfermarkt(modalScadenzaContratto, info.scadenza_contratto_reale);
        impostaCampoTransfermarkt(modalValoreMercato, info.valore_mercato);
        modalQuotazione.textContent = info.quotazione;
        modalCosto.textContent = info.costo;

        overlayGiocatore.classList.remove('hidden');
        overlayGiocatore.classList.add('flex');
    };

    const chiudiCardGiocatore = () => {
        overlayGiocatore.classList.add('hidden');
        overlayGiocatore.classList.remove('flex');
    };

    // Delega unica per tutte le tabelle della pagina (rosa, primavera, prestiti
    // in entrata e in uscita, pick del draft gia' usate).
    document.addEventListener('click', function (e) {
        const row = e.target.closest('tr[data-info]');
        if (!row) return;
        apriCardGiocatore(JSON.parse(row.dataset.info));
    });

    btnChiudiGiocatore.addEventListener('click', chiudiCardGiocatore);
    overlayGiocatore.addEventListener('click', function (e) {
        if (e.target === overlayGiocatore) chiudiCardGiocatore();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') chiudiCardGiocatore();
    });

    // Menù a tab: Rosa / Primavera / Draft / Prestiti. Le quattro sezioni sono
    // già tutte renderizzate dal server (stesso dato, nessuna query in più): il
    // click mostra solo il pannello corrispondente e nasconde gli altri.
    const tab = document.querySelectorAll('.tab-squadra');
    const pannelli = document.querySelectorAll('.pannello-squadra');
    tab.forEach(function (btn) {
        btn.addEventListener('click', function () {
            tab.forEach(t => t.setAttribute('aria-selected', String(t === btn)));
            pannelli.forEach(p => p.classList.toggle('hidden', p.dataset.panel !== btn.dataset.tab));
            if (btn.dataset.tab === 'movimenti') caricaMovimenti();
        });
    });

    // Movimenti: l'unica tab che non arriva col resto della pagina. Si chiede
    // al server alla prima apertura, una volta sola: caricarli sempre
    // costerebbe una query in piu' a ogni visita della dashboard.
    const pannelloMovimenti = document.querySelector('.pannello-squadra[data-panel="movimenti"]');
    let movimentiRichiesti = false;

    function caricaMovimenti() {
        if (movimentiRichiesti || !pannelloMovimenti) return;
        movimentiRichiesti = true;

        const corpo = document.getElementById('movimentiBody');
        const stato = document.getElementById('movimentiStato');
        const filtroStagione = document.getElementById('movimentiStagione');

        const paginatore = creaPaginazione({
            contenitore: document.getElementById('movimentiPaginazione'),
            perPagina: 10,
            disegna: (dellaPagina) => {
                corpo.replaceChildren(...dellaPagina.map(disegnaMovimento));
                nascondiFrecceInutili(corpo);
            },
            risaliA: pannelloMovimenti,
        });

        fetch(pannelloMovimenti.dataset.url)
            .then(res => {
                if (!res.ok) throw new Error(res.status);
                return res.json();
            })
            .then(compatti => {
                const movimenti = compatti.righe.map(valori =>
                    Object.fromEntries(compatti.campi.map((campo, i) => [campo, valori[i]])));

                if (!movimenti.length) {
                    stato.textContent = 'Nessun movimento per questa squadra.';
                    return;
                }
                stato.classList.add('hidden');

                // Le stagioni nel formato '24-25': l'ordine alfabetico
                // invertito e' quello cronologico, dalla piu' recente.
                const stagioni = [...new Set(movimenti.map(m => m.stagione).filter(Boolean))].sort().reverse();
                if (stagioni.length > 1) {
                    stagioni.forEach(s => filtroStagione.add(new Option(s, s)));
                    filtroStagione.classList.remove('hidden');
                }

                const aggiorna = () => paginatore.mostra(
                    movimenti.filter(m => !filtroStagione.value || m.stagione === filtroStagione.value));
                filtroStagione.addEventListener('change', aggiorna);
                aggiorna();
            })
            .catch(() => {
                stato.textContent = 'Impossibile caricare i movimenti, riprova.';
                // Al prossimo clic sulla tab si ritenta.
                movimentiRichiesti = false;
            });
    }

    // Stessa riga della pagina Movimenti di mercato: data e stagione sopra,
    // testo su una riga che si espande al clic.
    function disegnaMovimento(m) {
        const elemento = (tag, classi, testo) => {
            const e = document.createElement(tag);
            if (tag === 'button') e.type = 'button';
            if (classi) e.className = classi;
            if (testo !== undefined) e.textContent = testo;
            return e;
        };

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
    }

    // La freccia solo dove il testo e' davvero troncato: si misura dopo che
    // le righe sono nel documento.
    function nascondiFrecceInutili(corpo) {
        corpo.querySelectorAll('.mercato-toggle').forEach(function (apertura) {
            const testo = apertura.querySelector('.evento-testo');
            if (testo.scrollHeight <= testo.clientHeight + 1) {
                apertura.querySelector('.chevron').classList.add('hidden');
            }
        });
    }
});
