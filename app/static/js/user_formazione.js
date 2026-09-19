document.addEventListener('DOMContentLoaded', function () {
    const selectModulo = document.getElementById('selectModulo');
    const formModulo = document.getElementById('formModulo');
    if (selectModulo && formModulo) {
        selectModulo.addEventListener('change', function () {
            formModulo.submit();
        });
    }

    const campo = document.getElementById('campoFormazione');
    if (!campo) return;

    const linee = JSON.parse(campo.dataset.linee);
    const inputNascosti = document.getElementById('inputNascosti');
    const overlay = document.getElementById('overlayPosto');
    const btnChiudi = document.getElementById('btnChiudiPicker');
    const pickerTitolo = document.getElementById('pickerTitolo');
    const pickerLista = document.getElementById('pickerLista');

    const NOME_POSTO = { tit: 'Titolare', ris: '1ª riserva', ter: '2ª riserva' };

    // Stesso schema colore per ruolo della macro ruolo_colorato in _macros.html:
    // va tenuto allineato se quella cambia.
    const COLORE_RUOLO = {
        por: '#e0951b',
        dd: '#22a558', ds: '#22a558', dc: '#22a558', b: '#22a558',
        e: '#3f7fff', m: '#3f7fff', c: '#3f7fff',
        w: '#a855f7', t: '#a855f7',
        a: '#ef4444', pc: '#ef4444',
    };
    // etichetta e' "/"-separata per gli slot (slot_label in app/domini/moduli.py,
    // es. "W/A") ma ","-separata per il ruolo di un giocatore (pulisci_ruolo,
    // es. "Dd,Dc"): stessa funzione per entrambi, split su entrambi i separatori.
    const coloreEtichetta = (etichetta) => COLORE_RUOLO[etichetta.split(/[,/]/)[0].trim().toLowerCase()] || '#5a6570';

    // Stato corrente lato client: slot.indice -> {tit, ris, ter} (id giocatore
    // o null). Parte dalle selezioni gia' salvate, renderizzate dal server.
    const stato = {};
    for (const riga of linee) {
        for (const slot of riga) {
            stato[slot.indice] = Object.assign({}, slot.selezionati);
        }
    }

    const trovaCandidato = (slot, id) => slot.candidati.find((c) => c.id === id);

    // Un giocatore gia' schierato altrove (in un'altra posizione o come
    // titolare/riserva di un'altra) non compare selezionabile: evita di dover
    // scoprire il doppio impiego solo dopo aver salvato.
    const idGiaUsati = (slotIndiceEscluso, postoEscluso) => {
        const usati = new Set();
        for (const indice in stato) {
            for (const posto in stato[indice]) {
                if (indice == slotIndiceEscluso && posto === postoEscluso) continue;
                const id = stato[indice][posto];
                if (id) usati.add(id);
            }
        }
        return usati;
    };

    function apriPicker(slot, posto) {
        pickerTitolo.textContent = slot.etichetta + ' · ' + NOME_POSTO[posto];
        const usati = idGiaUsati(slot.indice, posto);
        pickerLista.innerHTML = '';

        const vuoto = document.createElement('li');
        vuoto.className = 'campetto-candidato italic text-muted';
        vuoto.textContent = '— nessuno —';
        vuoto.addEventListener('click', function () { assegna(slot.indice, posto, null); chiudiPicker(); });
        pickerLista.appendChild(vuoto);

        for (const c of slot.candidati) {
            const occupatoAltrove = usati.has(c.id);
            const li = document.createElement('li');
            li.className = 'campetto-candidato' + (occupatoAltrove ? ' occupato' : '');
            const nome = document.createElement('span');
            nome.textContent = c.nome;
            const ruolo = document.createElement('span');
            ruolo.className = 'text-xs font-semibold';
            ruolo.style.color = coloreEtichetta(c.ruolo);
            ruolo.textContent = c.ruolo;
            li.appendChild(nome);
            li.appendChild(ruolo);
            if (!occupatoAltrove) {
                li.addEventListener('click', function () { assegna(slot.indice, posto, c.id); chiudiPicker(); });
            }
            pickerLista.appendChild(li);
        }

        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    }

    function chiudiPicker() {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }

    function assegna(slotIndice, posto, id) {
        stato[slotIndice][posto] = id;
        render();
    }

    function render() {
        campo.innerHTML = '';
        inputNascosti.innerHTML = '';

        for (const riga of linee) {
            const rigaEl = document.createElement('div');
            rigaEl.className = 'campetto-riga';

            for (const slot of riga) {
                const slotEl = document.createElement('div');
                slotEl.className = 'campetto-slot';

                const badge = document.createElement('span');
                badge.className = 'campetto-badge';
                badge.style.background = coloreEtichetta(slot.etichetta);
                badge.textContent = slot.etichetta;
                slotEl.appendChild(badge);

                ['tit', 'ris', 'ter'].forEach(function (posto) {
                    const id = stato[slot.indice][posto];
                    const candidato = id ? trovaCandidato(slot, id) : null;

                    const postoEl = document.createElement('div');
                    postoEl.className = 'campetto-posto campetto-posto-editabile campetto-posto-' + posto +
                        (candidato ? '' : ' vuoto');
                    if (posto === 'tit' && candidato && candidato.campioncino) {
                        const foto = document.createElement('img');
                        foto.className = 'campetto-foto';
                        foto.loading = 'lazy';
                        foto.alt = '';
                        // Non tutti i giocatori hanno la caricatura (vedi
                        // app/core/formato.py): se manca si nasconde, niente
                        // ripiego su uno stile diverso.
                        foto.onerror = function () { foto.remove(); };
                        foto.src = candidato.campioncino;
                        postoEl.appendChild(foto);
                    }
                    const nomeEl = document.createElement('span');
                    nomeEl.textContent = candidato ? candidato.nome : (posto === 'tit' ? '—' : NOME_POSTO[posto]);
                    postoEl.appendChild(nomeEl);
                    postoEl.addEventListener('click', function () { apriPicker(slot, posto); });
                    slotEl.appendChild(postoEl);

                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'slot_' + slot.indice + '_' + posto;
                    input.value = id || '';
                    inputNascosti.appendChild(input);
                });

                rigaEl.appendChild(slotEl);
            }

            campo.appendChild(rigaEl);
        }
    }

    btnChiudi.addEventListener('click', chiudiPicker);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) chiudiPicker(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') chiudiPicker(); });

    render();
});
