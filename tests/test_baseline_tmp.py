import pytest
from tests.conta_query import conta_query
pytestmark = pytest.mark.db

def test_baseline(app, monkeypatch, nome_squadra, gate_aperto):
    from app.repositories import configurazione as cr
    monkeypatch.setattr(cr, "mercato_aperto", lambda cur: True)
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=False, nome_squadra=nome_squadra, username="test")
    with conta_query(monkeypatch) as registro:
        r = c.get(f"/mercato/mercato/{nome_squadra}")
    print(f"\n  status={r.status_code}")
    print(f"  QUERY TOTALI: {len(registro)}")
    print(f"  CHECKOUT dal pool: {len(registro.checkout)}")
    import collections
    for q, n in collections.Counter(x[:60] for x in registro).most_common(8):
        print(f"    {n:3d}x  {q}")
