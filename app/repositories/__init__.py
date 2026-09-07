"""
Accesso ai dati, un modulo per aggregato.

Due regole valgono per tutto il pacchetto.

Primo: i repository ricevono un cursore e non lo creano. Chi chiama possiede la
connessione e decide i confini della transazione; il repository si limita a
leggere e scrivere dentro quei confini.

Secondo: i repository non committano mai. Il commit e' una decisione del
chiamante, perche' solo lui sa se l'operazione e' completa. Fa eccezione, per
ora, squadre.sposta_crediti(): committa al proprio interno ed e' un difetto noto
di atomicita', documentato dove e' definita e coperto da un test xfail.

Nessun modulo qui importa Flask.
"""
