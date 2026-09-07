"""
Accesso ai dati, un modulo per aggregato.

Due regole valgono per tutto il pacchetto.

Primo: i repository ricevono un cursore e non lo creano. Chi chiama possiede la
connessione e decide i confini della transazione; il repository si limita a
leggere e scrivere dentro quei confini.

Secondo: i repository non committano mai. Il commit e' una decisione del
chiamante, perche' solo lui sa se l'operazione e' completa, e non intercettano
le eccezioni: un errore deve risalire perche' il chiamante possa annullare tutto.
La regola non ha eccezioni.

Nessun modulo qui importa Flask.
"""
