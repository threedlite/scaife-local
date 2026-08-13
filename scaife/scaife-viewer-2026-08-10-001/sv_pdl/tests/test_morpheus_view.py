"""Morpheus proxy view.

`morpheus_local` reshapes the Perseids service's deeply nested JSON into the
flat `{"Body": [...]}` the Vue frontend expects. Network is mocked, so this
runs offline and in CI. The `requests` library is a live upgrade risk here.
"""
from unittest import mock

from django.test import SimpleTestCase

import requests


# A trimmed but structurally faithful Morpheus response for μῆνιν.
MORPHEUS_RESPONSE = {
    "RDF": {
        "Annotation": {
            "Body": {
                "rest": {
                    "entry": {
                        "uri": None,
                        "dict": {
                            "hdwd": {"$": "μῆνις"},
                            "pofs": {"$": "noun"},
                            "decl": {"$": "3rd"},
                        },
                        "infl": {
                            "term": {
                                "stem": {"$": "μη—ν"},
                                "suff": {"$": "ιν"},
                            },
                            "pofs": {"$": "noun"},
                            "case": {"$": "accusative"},
                            "gend": {"$": "feminine"},
                            "num": {"$": "singular"},
                            "stemtype": {"$": "is_ews"},
                        },
                    }
                }
            }
        }
    }
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class MorpheusParamValidationTests(SimpleTestCase):
    def test_missing_word_is_400(self):
        self.assertEqual(self.client.get("/morpheus/", {"lang": "grc"}).status_code, 400)

    def test_missing_lang_is_400(self):
        self.assertEqual(self.client.get("/morpheus/", {"word": "x"}).status_code, 400)

    def test_invalid_lang_is_400(self):
        resp = self.client.get("/morpheus/", {"word": "x", "lang": "eng"})
        self.assertEqual(resp.status_code, 400)


class MorpheusReshapeTests(SimpleTestCase):
    @mock.patch("sv_pdl.views.requests.get")
    def test_flattens_to_body_list(self, mock_get):
        mock_get.return_value = FakeResponse(MORPHEUS_RESPONSE)
        data = self.client.get(
            "/morpheus/", {"word": "μῆνιν", "lang": "grc"}
        ).json()
        self.assertEqual(list(data), ["Body"])
        self.assertEqual(len(data["Body"]), 1)
        entry = data["Body"][0]
        self.assertEqual(entry["hdwd"], "μῆνις")
        self.assertEqual(entry["pofs"], "noun")
        self.assertEqual(entry["decl"], "3rd")

    @mock.patch("sv_pdl.views.requests.get")
    def test_inflection_fields_flattened(self, mock_get):
        mock_get.return_value = FakeResponse(MORPHEUS_RESPONSE)
        data = self.client.get(
            "/morpheus/", {"word": "μῆνιν", "lang": "grc"}
        ).json()
        infl = data["Body"][0]["infl"][0]
        self.assertEqual(infl["case"], "accusative")
        self.assertEqual(infl["gend"], "feminine")
        self.assertEqual(infl["num"], "singular")
        self.assertEqual(infl["suff"], "ιν")

    @mock.patch("sv_pdl.views.requests.get")
    def test_single_dict_body_coerced_to_list(self, mock_get):
        """Morpheus returns an object for one result and a list for many."""
        mock_get.return_value = FakeResponse(MORPHEUS_RESPONSE)
        data = self.client.get(
            "/morpheus/", {"word": "μῆνιν", "lang": "grc"}
        ).json()
        self.assertIsInstance(data["Body"], list)

    @mock.patch("sv_pdl.views.requests.get")
    def test_empty_body_returns_empty_list(self, mock_get):
        mock_get.return_value = FakeResponse(
            {"RDF": {"Annotation": {"Body": []}}}
        )
        data = self.client.get("/morpheus/", {"word": "zzz", "lang": "grc"}).json()
        self.assertEqual(data, {"Body": []})

    @mock.patch("sv_pdl.views.requests.get")
    def test_upstream_failure_degrades_gracefully(self, mock_get):
        """Morpheus being down must not 500 the reader."""
        mock_get.side_effect = requests.RequestException("connection refused")
        resp = self.client.get("/morpheus/", {"word": "x", "lang": "grc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"Body": []})

    @mock.patch("sv_pdl.views.requests.get")
    def test_calls_local_service_not_perseids(self, mock_get):
        """Regression guard for the whole point of this view: no traffic to
        services.perseids.org."""
        mock_get.return_value = FakeResponse(MORPHEUS_RESPONSE)
        self.client.get("/morpheus/", {"word": "μῆνιν", "lang": "grc"})
        called_url = mock_get.call_args[0][0]
        self.assertNotIn("perseids.org", called_url)
        self.assertIn("/analysis/word", called_url)
