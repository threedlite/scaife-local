from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from django.contrib import admin

from scaife_viewer.core.views import (
    CorporaReposView,
    CorpusMetadata,
    CTSApiGetPassageView,
    CTSApiGetValidReffView,
    LibraryCollectionVectorView,
    LibraryCollectionView,
    LibraryInfoView,
    LibraryPassageView,
    LibraryView,
    Reader,
    library_text_redirect,
    search,
    search_json,
)

from .localcomm.views import commentaries_json as local_commentaries_json
from .localdict.views import dictionaries_json as local_dictionaries_json
from .localdict.views import dictionary_entries as local_dictionary_entries
from .views import (
    about,
    app,
    home,
    licenses,
    morpheus_local,
    openapi_json,
    profile,
    swagger_ui,
)


api_patterns = (
    [
        path(
            "corpora/corpus-metadata/",
            CorpusMetadata.as_view(),
            name="corpora_corpus_metadata",
        ),
        path("corpora/repos/", CorporaReposView.as_view(), name="corpora_repos"),
        path("library/json/", LibraryView.as_view(format="json"), name="library"),
        path("library/json/info", LibraryInfoView.as_view(), name="library_info"),
        path(
            "library/vector/<str:urn>/",
            LibraryCollectionVectorView.as_view(),
            name="library_collection_vector",
        ),
        path(
            "library/passage/<str:urn>/json/",
            LibraryPassageView.as_view(format="json"),
            name="library_passage",
        ),
        path(
            "library/passage/<str:urn>/text/",
            LibraryPassageView.as_view(format="text"),
            name="library_passage_text",
        ),
        path(
            "library/passage/<str:urn>/xml/",
            LibraryPassageView.as_view(format="xml"),
            name="library_passage_xml",
        ),
        path("library/commentaries/<str:urn>/json/", local_commentaries_json, name="commentaries"),
        path("library/dictionaries/json/", local_dictionaries_json, name="dictionaries"),
        path(
            "library/dictionaries/<str:slug>/entries/",
            local_dictionary_entries,
            name="dictionary_entries",
        ),
        path(
            "library/<str:urn>/cts-api-xml/reffs/",
            CTSApiGetValidReffView.as_view(),
            name="library_cts_api_get_valid_reff",
        ),
        path(
            "library/<str:urn>/cts-api-xml/",
            CTSApiGetPassageView.as_view(),
            name="library_cts_api_xml",
        ),
        path(
            "library/<str:urn>/json/",
            LibraryCollectionView.as_view(format="json"),
            name="library_collection",
        ),
        path("search/json/", search_json, name="search"),
        path("morpheus/", morpheus_local, name="morpheus"),
    ],
    "api",
)

site_patterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("admin/", admin.site.urls),
    path("account/", include("account.urls")),
    path("api/docs/", swagger_ui, name="swagger_ui"),
    path("api/openapi.json", openapi_json, name="openapi_json"),
    path("licenses/", licenses, name="licenses"),
    path("profile/", profile, name="profile"),
    path("search/", search, name="search"),
    path("reading/", include("sv_pdl.reading.urls")),
    path("openid/", include("oidc_provider.urls", namespace="oidc_provider")),
    path(".well-known/", include("letsencrypt.urls")),
]

scaife_viewer_patterns = [
    path("", include(api_patterns)),
    path("library/", LibraryView.as_view(format="html"), name="library"),
    path(
        "library/<str:urn>/",
        LibraryCollectionView.as_view(format="html"),
        name="library_collection",
    ),
    path(
        "library/<str:urn>/redirect/",
        library_text_redirect,
        name="library_text_redirect",
    ),
    path("reader/<str:urn>/", Reader.as_view(), name="reader"),
]

urlpatterns = (
    site_patterns + scaife_viewer_patterns + [
        path("atlas/", include("scaife_viewer.atlas.urls")),
        path("<path:path>/", app, name="app"),
    ]
)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
