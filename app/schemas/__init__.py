"""
Schemi dei form: leggono i dati grezzi della richiesta e restituiscono oggetti
tipizzati, gia' normalizzati e validati.

Servono dove il form e' abbastanza grande da rendere la lettura a mano un
problema: nuovo_scambio ne ha ventinove campi, e prima li estraeva uno per uno
con novanta righe di codice in cui la stessa logica compariva quattro volte.

Uno schema non tocca il database: valida la forma dei dati, non la loro
coerenza con lo stato del gioco. Che le pick esistano davvero, o che una squadra
abbia i crediti, resta compito del repository e del service.
"""
