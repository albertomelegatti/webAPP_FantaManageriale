"""
Client dei valori di mercato (app/core/transfermarkt_api.py): niente rete vera,
la sessione requests viene sostituita con una finta.
"""

import json

import pytest

from app.core import transfermarkt_api as api


class _RispostaFinta:
    def __init__(self, status_code=200, payload=None, testo=None):
        self.status_code = status_code
        self._payload = payload
        self._testo = testo if testo is not None else json.dumps(payload or {})

    @property
    def content(self):
        return self._testo.encode()

    def json(self):
        if self._payload is None:
            raise ValueError("non è JSON")
        return self._payload


class _SessioneFinta:
    """get()/post() pescano da mappe url -> _RispostaFinta preparate dal test."""

    def __init__(self, risposte_get=None, risposte_post=None):
        self.risposte_get = risposte_get or {}
        self.risposte_post = risposte_post or {}
        self.chiamate_post = []

    def get(self, url, **kwargs):
        return self.risposte_get.get(url, _RispostaFinta(404, payload={}))

    def post(self, url, **kwargs):
        self.chiamate_post.append((url, kwargs))
        body = kwargs.get("json", {})
        return self.risposte_post.get(body.get("url"), _RispostaFinta(502, testo="ko"))


def _url(id_tm):
    return api._CEAPI_URL.format(id=id_tm)


def _payload(*mw):
    return {"list": [{"mw": v, "datum_mw": "Jun 1, 2026"} for v in mw]}


@pytest.fixture(autouse=True)
def _no_brightdata(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)


def _installa_sessione(monkeypatch, sessione):
    monkeypatch.setattr(api, "_sessione", lambda: sessione)


class TestValoreDi:
    def test_diretta_ok(self, monkeypatch):
        s = _SessioneFinta({_url(1): _RispostaFinta(200, _payload("€30.00m", "€45.00m"))})
        _installa_sessione(monkeypatch, s)
        assert api._valore_di(1) == 45_000_000

    def test_404_non_prova_brightdata(self, monkeypatch):
        s = _SessioneFinta({_url(2): _RispostaFinta(404, payload={})})
        _installa_sessione(monkeypatch, s)
        assert api._valore_di(2) is None
        assert s.chiamate_post == []

    def test_bloccata_senza_chiave_brightdata(self, monkeypatch):
        s = _SessioneFinta({_url(3): _RispostaFinta(403, testo="datadome")})
        _installa_sessione(monkeypatch, s)
        assert api._valore_di(3) is None
        assert s.chiamate_post == []

    def test_bloccata_con_fallback_brightdata(self, monkeypatch):
        monkeypatch.setenv("BRIGHTDATA_API_KEY", "chiave")
        s = _SessioneFinta(
            risposte_get={_url(4): _RispostaFinta(403, testo="datadome")},
            risposte_post={_url(4): _RispostaFinta(200, _payload("€12.00m"))},
        )
        _installa_sessione(monkeypatch, s)
        assert api._valore_di(4) == 12_000_000
        assert s.chiamate_post and s.chiamate_post[0][0] == api._BRIGHTDATA_ENDPOINT


class TestRecuperaValoriMercato:
    def test_dizionario_per_gli_id(self, monkeypatch):
        s = _SessioneFinta({
            _url(1): _RispostaFinta(200, _payload("€10.00m")),
            _url(2): _RispostaFinta(200, _payload("€20.00m")),
        })
        _installa_sessione(monkeypatch, s)
        assert api.recupera_valori_mercato([1, 2, 2]) == {1: 10_000_000, 2: 20_000_000}

    def test_id_non_risolti_a_none(self, monkeypatch):
        s = _SessioneFinta({_url(1): _RispostaFinta(200, _payload("€10.00m"))})
        _installa_sessione(monkeypatch, s)
        assert api.recupera_valori_mercato([1, 999]) == {1: 10_000_000, 999: None}

    def test_lista_vuota(self, monkeypatch):
        _installa_sessione(monkeypatch, _SessioneFinta())
        assert api.recupera_valori_mercato([]) == {}
