"""
OpenAPI 3.0 spec for the local Scaife Viewer JSON API.

Hand-written to stay small — the spec is short enough to review as one
file, and doesn't require a heavy schema-generation dependency (DRF etc.).
"""

SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Scaife Viewer — Local API",
        "version": "1.0.0",
        "description": (
            "JSON endpoints backing the reader UI. All are safe to call "
            "from scripts. Everything runs locally — no external network "
            "access at runtime."
        ),
        "license": {"name": "MIT"},
    },
    "servers": [{"url": "/", "description": "Local Scaife Viewer"}],

    "tags": [
        {"name": "morphology", "description": "Form -> lemma parsing (Perseids Morpheus)"},
        {"name": "dictionaries", "description": "LSJ / Middle Liddell / Lewis & Short"},
        {"name": "commentaries", "description": "Open Commentaries on classical texts"},
        {"name": "library", "description": "CTS text catalog + passage retrieval"},
        {"name": "search", "description": "Elasticsearch-backed full-text search"},
    ],

    "paths": {

        # -------- morphology --------
        "/morpheus/": {
            "get": {
                "tags": ["morphology"],
                "summary": "Analyze an inflected word form",
                "description": (
                    "Returns morphological analyses from the local "
                    "Perseids Morpheus container. Handles Ancient Greek "
                    "(polytonic Unicode input) and Latin."
                ),
                "parameters": [
                    {"name": "word", "in": "query", "required": True,
                     "schema": {"type": "string"},
                     "example": "μῆνιν",
                     "description": "Inflected word form (Unicode)"},
                    {"name": "lang", "in": "query", "required": True,
                     "schema": {"type": "string", "enum": ["grc", "lat"]},
                     "example": "grc"},
                ],
                "responses": {
                    "200": {
                        "description": "Morphology analysis (empty Body if none)",
                        "content": {"application/json": {
                            "schema": {"$ref": "#/components/schemas/MorpheusResponse"}
                        }},
                    },
                    "400": {"description": "Missing or invalid parameters"},
                },
            }
        },

        # -------- dictionaries --------
        "/library/dictionaries/json/": {
            "get": {
                "tags": ["dictionaries"],
                "summary": "List all available dictionaries",
                "responses": {
                    "200": {
                        "description": "Dictionary catalog",
                        "content": {"application/json": {
                            "schema": {"$ref": "#/components/schemas/DictionaryList"}
                        }},
                    }
                },
            }
        },
        "/library/dictionaries/{slug}/entries/": {
            "get": {
                "tags": ["dictionaries"],
                "summary": "Search a dictionary for a lemma",
                "description": (
                    "Exact match on the accent-stripped, lowercased "
                    "headword, falling back to prefix match."
                ),
                "parameters": [
                    {"name": "slug", "in": "path", "required": True,
                     "schema": {"type": "string",
                                "enum": ["lsj", "middle-liddell",
                                         "lewis-and-short-latin-dictionary"]},
                     "example": "lsj"},
                    {"name": "q", "in": "query", "required": False,
                     "schema": {"type": "string"},
                     "example": "μῆνις",
                     "description": "Lemma (headword). Omit to page through the whole dictionary."},
                    {"name": "page", "in": "query", "required": False,
                     "schema": {"type": "integer", "minimum": 1, "default": 1}},
                ],
                "responses": {
                    "200": {
                        "description": "Entries",
                        "content": {"application/json": {
                            "schema": {"$ref": "#/components/schemas/DictionaryEntries"}
                        }},
                    },
                    "404": {"description": "Unknown dictionary slug"},
                },
            }
        },

        # -------- commentaries --------
        "/library/commentaries/{urn}/json/": {
            "get": {
                "tags": ["commentaries"],
                "summary": "Get commentary entries overlapping a passage URN",
                "description": (
                    "Matches on textgroup+work (edition-agnostic) and "
                    "returns commentaries whose target reference range "
                    "overlaps the query passage."
                ),
                "parameters": [
                    {"name": "urn", "in": "path", "required": True,
                     "schema": {"type": "string"},
                     "example": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"},
                    {"name": "page", "in": "query", "required": False,
                     "schema": {"type": "integer", "minimum": 1, "default": 1}},
                ],
                "responses": {
                    "200": {
                        "description": "Commentaries",
                        "content": {"application/json": {
                            "schema": {"$ref": "#/components/schemas/CommentaryList"}
                        }},
                    }
                },
            }
        },

        # -------- library --------
        "/library/json/": {
            "get": {
                "tags": ["library"],
                "summary": "Full catalog of text groups + works + editions",
                "responses": {"200": {"description": "Library tree"}},
            }
        },
        "/library/passage/{urn}/json/": {
            "get": {
                "tags": ["library"],
                "summary": "Fetch a passage",
                "parameters": [
                    {"name": "urn", "in": "path", "required": True,
                     "schema": {"type": "string"},
                     "example": "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1-1.7"},
                ],
                "responses": {"200": {"description": "Rendered passage"}},
            }
        },
        "/library/passage/{urn}/text/": {
            "get": {
                "tags": ["library"],
                "summary": "Fetch a passage as plain text",
                "parameters": [
                    {"name": "urn", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Plain text"}},
            }
        },
        "/library/passage/{urn}/xml/": {
            "get": {
                "tags": ["library"],
                "summary": "Fetch a passage as TEI XML",
                "parameters": [
                    {"name": "urn", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "TEI XML"}},
            }
        },
        "/corpora/repos/": {
            "get": {
                "tags": ["library"],
                "summary": "Content manifest (list of loaded corpora)",
                "responses": {"200": {"description": "Content manifest"}},
            }
        },
        "/corpora/corpus-metadata/": {
            "get": {
                "tags": ["library"],
                "summary": "Corpus metadata (author counts, etc.)",
                "responses": {"200": {"description": "Metadata"}},
            }
        },

        # -------- search --------
        "/search/json/": {
            "get": {
                "tags": ["search"],
                "summary": "Full-text search over indexed corpora",
                "parameters": [
                    {"name": "q", "in": "query", "required": True,
                     "schema": {"type": "string"},
                     "example": "μῆνιν"},
                    {"name": "type", "in": "query", "required": True,
                     "schema": {"type": "string", "enum": ["library", "reader"]},
                     "example": "library"},
                    {"name": "size", "in": "query", "required": False,
                     "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}},
                    {"name": "kind", "in": "query", "required": False,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Search results"}},
            }
        },
    },

    "components": {
        "schemas": {

            "MorpheusResponse": {
                "type": "object",
                "properties": {
                    "Body": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/MorpheusEntry"}
                    }
                },
                "example": {"Body": [{
                    "uri": None, "hdwd": "μῆνις",
                    "pofs": "noun", "decl": "3rd",
                    "infl": [{"stem": "μη—ν", "suff": "ιν",
                              "pofs": "noun", "case": "accusative",
                              "gend": "feminine", "num": "singular",
                              "stemtype": "is_ews"}]
                }]},
            },
            "MorpheusEntry": {
                "type": "object",
                "properties": {
                    "hdwd": {"type": "string", "description": "Lemma (dictionary headword)"},
                    "pofs": {"type": "string", "description": "Part of speech"},
                    "decl": {"type": "string"},
                    "uri": {"type": "string", "nullable": True},
                    "infl": {"type": "array",
                             "items": {"$ref": "#/components/schemas/MorpheusInflection"}},
                },
            },
            "MorpheusInflection": {
                "type": "object",
                "properties": {
                    "stem": {"type": "string"},
                    "suff": {"type": "string"},
                    "pofs": {"type": "string"},
                    "case": {"type": "string"},
                    "mood": {"type": "string"},
                    "tense": {"type": "string"},
                    "voice": {"type": "string"},
                    "gend": {"type": "string"},
                    "num": {"type": "string"},
                    "pers": {"type": "string"},
                    "dial": {"type": "string"},
                    "stemtype": {"type": "string"},
                },
            },

            "DictionaryList": {
                "type": "object",
                "properties": {
                    "results": {"type": "array",
                                "items": {"$ref": "#/components/schemas/Dictionary"}},
                },
            },
            "Dictionary": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "slug": {"type": "string"},
                    "label": {"type": "string"},
                    "lang": {"type": "string", "enum": ["grc", "lat"]},
                    "urn": {"type": "string"},
                    "data": {"type": "object"},
                },
                "example": {"id": 1, "slug": "lsj",
                            "label": "LSJ (Liddell-Scott-Jones)",
                            "lang": "grc", "urn": "urn:cite2:scaife-viewer:dictionaries.local:lsj",
                            "data": {}},
            },
            "DictionaryEntries": {
                "type": "object",
                "properties": {
                    "current_page": {"type": "integer"},
                    "total_pages": {"type": "integer"},
                    "results": {"type": "array",
                                "items": {"$ref": "#/components/schemas/DictionaryEntry"}},
                },
            },
            "DictionaryEntry": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "headword": {"type": "string"},
                    "headword_normalized": {"type": "string"},
                    "headword_normalized_stripped": {"type": "string"},
                    "intro_text": {"type": "string"},
                },
            },

            "CommentaryList": {
                "type": "object",
                "properties": {
                    "current_page": {"type": "integer"},
                    "total_pages": {"type": "integer"},
                    "results": {"type": "array",
                                "items": {"$ref": "#/components/schemas/CommentaryEntry"}},
                },
            },
            "CommentaryEntry": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "urn": {"type": "string", "description": "Citation URN of this note"},
                    "corresp": {"type": "string", "description": "Target passage URN"},
                    "lemma": {"type": "string"},
                    "content": {"type": "string", "description": "HTML"},
                },
            },
        }
    },
}
