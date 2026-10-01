# Proposal: line-level audio in the local Scaife Viewer

Date: 2026-09-30. Branch: `feature/audio` (no commits beyond `main` yet).

Everything in sections 1–3 was checked against files on this machine on the
date above, and the items marked "live" were checked against the running
stack (`bootstrap.sh`, Colima, all four containers healthy, unit suite
123/123 green before any change). Section 4 onward is the proposed design;
each design choice says which fact it rests on. Items that could not be
verified are listed in section 9 rather than assumed. Section 10 records
what the live review changed.

## 0. Summary

- **Data.** The sibling project `~/git/hesiod` holds synthesized line-by-line
  readings of Hesiod as per-line `.mp4` files (AAC-LC, mono, 44.1 kHz). The
  release zip is `data/synth/hesiod_fs2_full/hesiod_chamberlain_tts_female_lettered.zip`:
  2,352 clips, one per `<l>` element in the three Perseus `perseus-grc2`
  TEI files this viewer already serves. The zip carries no manifest; the only
  key is the path `Hesiod/<Work>/book_1/line_<n>.mp4`.
- **UI reference.** The sibling mobile app `~/git/classicsviewer` shows a
  small play icon beside the line number of every line that has a clip.
  Tapping plays that one clip; tapping again stops it. A "Continuous Audio"
  toggle plays the following lines in sequence until the end of the page.
  There is no seek bar, speed control, player bar, or playing-line highlight.
- **Plan.** Add a fourth local Django app, `sv_pdl/localaudio`, following the
  `localdict` / `localcomm` pattern: a read-only bind mount, an idempotent
  sentinel-gated ingest command, a JSON endpoint keyed by CTS URN, and a file
  endpoint. On the Vue side: a play/stop icon in the existing line-number
  gutter of `TextPart.vue`, a single hidden `<audio>` element, and an "Audio"
  sidebar widget holding the continuous-playback toggle and the CC BY-SA
  attribution. Hesiod is the first package staged; the same manifest and
  ingest cover the other 14 hesiod packages (Appendix A), 65,051 clips
  in all.

## 1. Verified facts: the audio data (`~/git/hesiod`)

Source: `README.md`, `LICENSE`, `scripts/corpora.py`, `data/hesiod/lines.csv`,
and the zips under `data/synth/hesiod_fs2_full/`. Remote:
`origin https://github.com/threedlite/hesiod.git`, head `51d1e0e r5`.

### 1.1 What it is

From the README: "A synthesized reading of Hesiod (Theogony, Works and Days,
Shield of Heracles), the 33 Homeric Hymns, and the other hexameter poets in
Perseus … in reconstructed ancient Greek pronunciation, made by training a
text-to-speech model on David Chamberlain's line-by-line recording of the
Iliad and converting its output to a female voice."

It is TTS output, not a human recording. The pipeline is
`scripts/synth_hesiod.py` (FastSpeech2-style model + Vocos vocoder, then
`ffmpeg … -ar 44100 -ac 1 -c:a aac -b:a 96k`) and `scripts/convert_voice.py`
(male to female via WORLD; "timing unchanged").

### 1.2 The files

`.gitignore` excludes `*.mp4` and `data/synth/`, so **the audio exists only on
this machine's disk and is not in the hesiod git remote.**

Release zips for Hesiod (all dated 2026-09-24):

| Zip | Clips | Size on disk |
|---|---|---|
| `hesiod_chamberlain_tts_female.zip` | 2,328 | 147 MB (155,743,163 bytes uncompressed) |
| `hesiod_chamberlain_tts_female_lettered.zip` | 2,352 | 149 MB |

The zips contain nothing but `.mp4` entries (checked: zero non-mp4 entries).
The `_fs2_full` (unconverted male) variants also exist on disk but
`LICENSE` item 6 says "The unconverted synthesis is not distributed".

Per-work counts in the unlettered zip: Theogony 1,022; Works and Days 827;
Shield of Heracles 479. The lettered zip adds the 24 lines whose TEI `@n`
carries a letter suffix (Theogony 929a–t, Works and Days 169a–d).

Path scheme inside the zip, verified from `unzip -l`:

```
Hesiod/Theogony/book_1/line_1.mp4
Hesiod/Works and Days/book_1/line_99.mp4
Hesiod/Shield of Heracles/book_1/line_100.mp4
Hesiod/Theogony/book_1/line_929a.mp4        (lettered zip only)
```

`book_1` is constant for Hesiod: `scripts/corpora.py` line 31 declares the
corpus with `books=False`. The `Author/Work` strings are, per the same file,
copied from the mobile app's database (`authors.name`, `works.title`); they
are display strings, not identifiers.

### 1.3 Codec

`ffprobe` on `Hesiod/Theogony/book_1/line_1.mp4`:

```
codec_name=aac  sample_rate=44100  channels=1
format_name=mov,mp4,m4a,3gp,3g2,mj2  duration=4.890000  bit_rate=105092
```

Across the unlettered package: 2,328 clips, 12,065.6 s total (3.35 h),
mean 5.18 s per clip (min 4.34 s, max 6.00 s). Mean file size is about
67 KB (155,743,163 / 2,328).

### 1.4 How the audio is keyed to text

- **Inside the zip: the path only.** No manifest, JSON, CSV, or database.
- **In the hesiod repo (tracked):** `data/hesiod/lines.csv`, 2,352 data rows,
  header `work,tlg,book,n,text,text_clean,source`. Example:
  `Theogony,tlg001,1,1,"Μουσάων Ἑλικωνιάδων ἀρχώμεθʼ ἀείδειν,",…,tlg0020.tlg001.perseus-grc2.xml`.
  The `source` column names the exact Perseus TEI file, so the CTS version
  URN is `urn:cts:greekLit:tlg0020.<tlg>.perseus-grc2` and the passage
  reference is `n`.
- **No CTS URN string for Hesiod appears anywhere in the hesiod repo**; the
  only full URN in it is the Iliad's, in `LICENSE`.
- **No sub-line timing** (no SRT/VTT/word alignment) exists for the
  synthesized audio. `data/synth/hesiod_fs2_full/wav/synth_index.csv` holds
  per-token predicted frame durations from which word timing *could* be
  derived, but it is stale for lines that went through the retry pass
  (verified on `tlg001_1008`), and AAC encoder delay was not measured.
  Word-level sync is therefore out of scope for this proposal.

### 1.5 License

`LICENSE`: CC BY-SA 4.0 for "the synthesized Hesiod audio, the audio package,
the trained model weights, the derived tables, and the code and documents".
The attribution notice says: "Anyone redistributing this work or adapting it
must keep this notice and give the same credit." Credited sources are David
Chamberlain's Iliad recordings (CC BY 4.0, hypotactic.com), Perseus
canonical-greekLit (CC BY-SA 4.0), and the Perseus treebank (CC BY-SA 3.0).

### 1.6 Other corpora (covered by the same mechanism; Appendix A)

Fourteen further `*_chamberlain_tts_female.zip` packages exist on disk
(Homeric Hymns 147 MB, Homer 767 MB, Apollonius 367 MB, Theocritus 163 MB,
Moschus 31 MB, Bion 16 MB, Callimachus 59 MB, Aratus 73 MB, Quintus 557 MB,
Oppian 222 MB, Oppian of Apamea 136 MB, Nonnus 1,391 MB, Tryphiodorus 44 MB,
Colluthus 26 MB; about 4.0 GB in all). Every one of the 15 authors
(tlg0001, 0005, 0012, 0013, 0020, 0023, 0024, 0035, 0036, 0533, 0647, 0653,
2045, 2046, 4081) has a directory in this repo's
`data-sources/canonical-greekLit/data/`. Appendix A maps every
`Author/Work/book_N` folder to a version URN and diffs every zip against
the TEI in this repo: 65,173 TEI lines, 65,051 clips in the best zip set,
122 lines without audio, all explained (lost lines marked `<gap>`, and
Theocritus 28–30 skipped by the hesiod pipeline as non-hexameter).

## 2. Verified facts: the reference UI (`~/git/classicsviewer`)

Source: the Kotlin/XML Android app and the SwiftUI iOS app in
`/Users/user1/git/classicsviewer` (remote `threedlite/classicsviewer`, head
`e5e4b89 0.8.141`, 2026-09-29). `/Users/user1/git/classicsviewer.1` is an
older checkout (2026-04-07) and was not used.

### 2.1 Where the control sits

Android, `app/src/main/res/layout/item_text_line_with_speaker.xml`: an
`ImageButton` `@+id/playButton`, 24 dp square, `@drawable/ic_play_arrow`
(vector path `M8,5v14l11,-7z`), `contentDescription="Play audio"`,
`visibility="gone"` by default. It sits to the **left of the 48 dp line
number**, which sits left of the line text. It becomes visible only when
`audioMappings[line.lineNumber] != null`
(`TextLineWithSpeakerAdapter.kt:111-123`). Tint `0xFF999999` on the default
theme, `0xFF666666` when colours are inverted.

iOS, `ReaderView.swift:872-880`: a `Button` with SF Symbol
`isPlayingAudio ? "stop.fill" : "play.fill"`, 12 pt, `.primary` colour,
placed after the bookmark icon and before the monospaced line number.

### 2.2 Behaviour

- Tap a line's icon: stop whatever is playing, play that clip, snackbar
  "Playing line N". Tap the same line while it plays: pause, snackbar
  "Paused" (`TextViewerPagerActivity.kt:698-708`). iOS toggles play/stop on
  the same line and swaps the icon to `stop.fill`; Android has an
  `ic_pause.xml` but never references it, so its icon never changes.
- **Continuous Audio** (Android only): a checkable item in the reader
  overflow menu (`menu_text_viewer.xml`, `action_continuous_playback`),
  persisted in `SharedPreferences("audio_prefs")` key `continuous_playback`,
  default false. On clip completion `playNextLine()` walks
  `currentlyPlayingLine + 1 .. currentEndLine` for the next mapped line. At
  the end of the page it stops with "End of page audio. Navigate to next page
  to continue." and turns continuous mode off; it does not turn the page. On
  a playback error in continuous mode it skips ahead.
- One clip at a time: `ExoPlayer` `stop(); clearMediaItems(); setMediaItem();
  prepare(); play()`. Accepted extensions include `mp4`.
- **Not present on either platform:** seek bar, progress display, speed
  control, skip buttons, a bottom or floating player bar, highlighting of the
  playing line, auto-scroll, play-whole-passage.

### 2.3 Data model and packaging in the app

- Android table `audio_mappings(package_id, author_name, work_title,
  book_number INTEGER, line_number INTEGER, file_path, file_format,
  duration_ms, …)`, keyed by **display strings + integers, not CTS URNs**.
  `AudioImportWorker` derives the key from the zip path and parses the text
  after `line_` with `toIntOrNull()`, so lettered files (`line_929a.mp4`)
  are skipped. `LINE_LABELS_PROPOSAL.md` in that repo proposes fixing this;
  it is not implemented.
- Packages are zips imported from local storage; one package is active at a
  time (`is_active`). The app has no network permission and never streams.
- A "Manage Audio" screen lists packages (name, info, import date, delete)
  with an import FAB, and a separate download screen for the Play Asset
  Delivery Iliad pack. Neither is relevant to a single-user local web app.
- Tests: none for audio on either platform.

## 3. Verified facts: this repo

### 3.1 Texts

`data-sources/canonical-greekLit/data/tlg0020/` holds the three
`perseus-grc2` editions (and `perseus-eng2` translations). Line counts from
`grep -c '<l n='`:

| Work | Version URN | TEI `<l>` count | Lettered `@n` | Clips in lettered zip |
|---|---|---|---|---|
| Theogony | `urn:cts:greekLit:tlg0020.tlg001.perseus-grc2` | 1,042 | 20 | 1,042 |
| Works and Days | `urn:cts:greekLit:tlg0020.tlg002.perseus-grc2` | 831 | 4 | 831 |
| Shield of Heracles | `urn:cts:greekLit:tlg0020.tlg003.perseus-grc2` | 479 | 0 | 479 |

All three use a single-level `line` citation (`cRefPattern n="line"`).
Because the citation labels are `["line"]`, `chunk_config()` in
`packages/scaife-viewer-core/scaife_viewer/core/cts/toc.py:98-99` groups
30 nodes per chunk. Live: `/library/urn:…tlg001.perseus-grc2/redirect/`
sends the reader to `…:1-30`, and the TOC (`/library/<version>/json/`)
lists all 1,042 lines individually, `929a` … `929t` included.

Live: `/library/passage/…tlg001.perseus-grc2:928-931/json/` returns 24
`text-part` elements whose `reference` values are `928, 929, 929a … 929t,
930, 931`, and `…:929a/json/` resolves on its own (HTTP 200). So the
viewer already addresses lettered lines by exactly the string the lettered
zip uses in its file names.

The lettered zip matches the TEI line-for-line: 1,022 + 20 = 1,042,
827 + 4 = 831, 479. **The lettered zip is therefore the one to ingest.**

One caveat, live: the Shield's TOC lists only 413 of its 479 lines,
because 66 lines sit inside `<sp>` elements that the file's own citation
XPath cannot reach (Appendix A.4). Every Shield line still renders inside
the reader's pages, and the audio lookup is a range over each page, so
all 479 clips are playable; only direct links to those 66 lines fail.

### 3.2 How a passage reaches the browser

- `GET /library/passage/<urn>/json/` (`LibraryPassageView`, routed in
  `sv_pdl/urls.py`) returns (live, all keys): `ancestors`, `children`,
  `json_url`, `refs`, `text` (with `lang`, `label`, `ancestors`),
  `text_html`, `text_url`, `url`, `urn`, `word_tokens`. Previous and next
  pages are **not** in the body: they arrive in the HTTP `Link` header
  (`rel="prev"` / `rel="next"` with a `urn` parameter), which
  `static/src/js/api/index.js` merges in as `_prev` / `_next` via
  `pagination(r)`. Live example: `…:901-930` links to prev `…:851-900` and
  next `…:931-980`, i.e. page bounds are counted in nodes, so pages that
  contain lettered lines cover fewer numbered lines.
- `text_html` is produced by `sv_pdl/tei.xsl`. Its template for
  `t:div[@type='textpart']|t:l` (lines 198–214) emits
  `<text-part class="… leaf o" reference="<n>">…</text-part>`, where
  `reference` is the dotted ancestor path plus `@n`. For Hesiod that is the
  bare line number, including `929a`.
- `PassageRenderText.vue` compiles `text_html` at runtime as a Vue template
  with `TextPart`, `RefLower`, and `t: InlineToken` registered. `TextPart.vue`
  renders `<div class="textpart">` with a `.a` column (a `router-link`
  holding the line number, styled in `static/src/scss/_text.scss:141-175` as
  a 24 px-min sticky gutter, transparent until the passage is hovered) and a
  `.b` column holding the words.
- `Reader.vue` composes the page with `Skeleton.vue` (left sidebar, body,
  right sidebar). Widgets are `BaseWidget.vue` instances with a collapsible
  header; the right slot currently holds text-mode, highlight, morpheus,
  word-list, dictionary, commentary, display-settings, token-list, and
  New Alexandria commentary widgets.
- Vuex `reader` state (`static/src/js/vuex/reader/state.js`) holds
  `leftPassage`, `leftPassageText`, `textMode`, etc. `config.js` persists
  `reader.sidebarLeftOpened`, `reader.sidebarRightOpened`, and
  `reader.textMode` to `localStorage` via `vuex-persistedstate`.
- Icons come from `@fortawesome/free-solid-svg-icons` through
  `static/src/js/components/icons.js`, which registers ten icons by name.
- API helpers live in `static/src/js/api/index.js` (`getPassage`,
  `getPerseusCommentaryEntries`, …) using an axios instance.

### 3.3 Backend pattern for local data

`sv_pdl/localdict` and `sv_pdl/localcomm` are the precedent: a Django app
with `BigAutoField` models, explicit named indexes, a management command that
reads a read-only bind mount (`/host-lexica`, `/host-commentaries`) and is
idempotent, JSON views mimicking the upstream response shape, routes in
`sv_pdl/urls.py`, a sentinel-gated step in `deploy/entrypoint.sh` guarded by
`[ -d /host-… ]`, and tests in `sv_pdl/tests/` (`test_localdict_views.py`,
`test_offline_wiring.py::test_*_route_uses_local_view`).

### 3.4 Serving files

- Static files: WhiteNoise (`whitenoise==6.7.0`) serves `STATIC_ROOT`
  (`/site_media/static/`), populated at image build by `collectstatic`. No
  `WHITENOISE_ROOT` is configured.
- Media: `sv_pdl/urls.py` ends with
  `urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)`.
  Per Django's documentation this helper only adds a route when
  `settings.DEBUG` is true. `deploy/.env` (written by `bootstrap.sh`) sets
  `DEBUG=1`, and `settings.py` defaults `DEBUG` to `1`.
- HTTP Range (live, inside the container): Django 5.2.17's
  `django/views/static.py` and `django/http/response.py` contain no Range
  handling at all (`grep -i range` finds nothing in either), so a plain
  `FileResponse` always answers 200 with the whole file. WhiteNoise 6.7.0's
  `responders.py` does parse `HTTP_RANGE` and returns 206 partial content.
- Browser behaviour (host, headless Chrome from `/Applications`): an
  `<audio>` element given `Hesiod/Theogony/book_1/line_929a.mp4` over
  plain HTTP reported `canPlayType('audio/mp4; codecs="mp4a.40.2"')` =
  `"probably"`, fired `loadedmetadata` (duration 5.55 s) and `playing`,
  and `play()` resolved. Chrome sent `Range: bytes=0-` for the clip and
  accepted a 200 full-body reply from a server with no Range support.
  Firefox and Safari were not tested (section 9).
- `RateLimitMiddleware` applies `RATELIMIT_DEFAULT_RATE` (default `200/m`,
  per IP) to every request; no path exemption was found in
  `sv_pdl/middleware.py`.
- No Content-Security-Policy header is set anywhere in `sv_pdl/`.
- Bind mounts are declared in `deploy/docker-compose.override.local.yml` with
  host paths from `SCAIFE_REPO_ROOT` and `SCAIFE_DATA_SOURCES`, which
  `bootstrap.sh` exports (`SCAIFE_DATA_SOURCES` defaults to
  `$REPO_ROOT/data-sources`). The container runs gunicorn as UID 1000
  `scaife` after `entrypoint-locked.sh` drops privileges.

### 3.5 Build and test

- The Vue bundle is built inside the image (`Dockerfile` stage
  `static-build`, node 12.13: `npm run unit`, then `npm run build`);
  `bootstrap.sh` rebuilds it when `static/src` changes (README, "Applying
  updates"). Frontend jest specs live in `test/*.spec.js` (7 files, all for
  search or passage-links widgets).
- Python tests: `bash scripts/run-tests.sh` (123 unit tests, needs the stack
  up), `--integration` for the full 160. Lint: `bash scripts/lint.sh`.
- Host tools present: `/opt/homebrew/bin/ffprobe` and `ffmpeg`. Inside
  the `scaife-viewer` image neither exists (live: `which ffprobe ffmpeg`
  prints nothing).
- Python test pattern: `sv_pdl/tests/test_localcomm_views.py` uses
  `django.test.TestCase` with rows created in `setUpTestData` and calls
  the views through the test client. Frontend pattern:
  `test/WidgetPassageLinks.spec.js` uses `shallowMount` with a hand-built
  `Vuex.Store` passed through `mocks.$store`.
- `LICENSE` at the repo root enumerates the MIT-licensed local files,
  including `sv_pdl/localdict/**` and `sv_pdl/localcomm/**` (lines 77–78).
  `sv_pdl/templates/licenses.html` has tables headed "Code",
  "Data — text corpora", and "Data — dictionaries".
- The stack was brought up with `bootstrap.sh` for this review. Unit suite
  before any change: `Ran 123 tests … OK`.

## 4. Proposed design

### 4.1 Data staging (host side)

1. New gitignored directory `data-sources/audio/`. `bootstrap.sh` gains an
   optional `SCAIFE_AUDIO_SOURCES` variable (default
   `$DATA_SOURCES/audio`) and exports it like the other two paths. If the
   directory is absent, everything audio-related is skipped, exactly as the
   dictionary and commentary steps skip when their mounts are absent.
2. Package layout on the host: one directory per package, containing the
   unpacked zip tree plus a small manifest this repo owns:

   ```
   data-sources/audio/
     hesiod_chamberlain_tts_female_lettered/
       package.yaml
       Hesiod/Theogony/book_1/line_1.mp4
       Hesiod/Theogony/book_1/line_929a.mp4
       …
   ```

   `package.yaml` supplies what the zip does not carry (section 1.4):

   ```yaml
   slug: hesiod-chamberlain-tts-female-lettered
   label: Hesiod, synthesized reading (Chamberlain TTS, female voice)
   license: CC BY-SA 4.0
   attribution: |
     <the "Attribution notice" block from ~/git/hesiod/LICENSE, verbatim>
   source: https://github.com/threedlite/hesiod
   works:
     "Hesiod/Theogony":            urn:cts:greekLit:tlg0020.tlg001.perseus-grc2
     "Hesiod/Works and Days":      urn:cts:greekLit:tlg0020.tlg002.perseus-grc2
     "Hesiod/Shield of Heracles":  urn:cts:greekLit:tlg0020.tlg003.perseus-grc2
   cited_by_book: false    # Hesiod is cited by line only, so ref = n
   ```

   `cited_by_book: true` makes the ref `N.n` from `book_N/line_n.mp4`,
   which is how the viewer cites every multi-book text (Appendix A.1). A
   per-work override object is allowed for packages that mix the two
   (Moschus, Bion). Appendix A.3 gives the manifest for all 15 packages.

   The three URNs come from `data/hesiod/lines.csv` `source` column and the
   `__cts__.xml` files in this repo. The verbatim attribution block is
   required by the license (section 1.5).
3. `bootstrap.sh` does **not** fetch the zip: it is not in any git remote
   (section 1.2). The README documents how to unzip it into place. The
   `_lettered` zip is the one to use (section 3.1).
4. Compose override: add
   `${SCAIFE_AUDIO_SOURCES}:/host-audio:ro` next to the lexica and
   commentary mounts.

### 4.2 Django app `sv_pdl/localaudio`

Models (BigAutoField pks, named indexes, as in `localdict`):

```
AudioPackage: slug (unique), label, license, attribution (text),
              source_url, root_dir (relative to /host-audio), clip_count
AudioClip:    package FK, version_urn (e.g. urn:cts:greekLit:tlg0020.tlg001.perseus-grc2),
              ref (e.g. "929a"), ref_key (zero-padded sort key), path
              (relative to package root)
              unique (package, version_urn, ref); index (version_urn, ref_key)
```

`ref_key` is produced by the existing `sv_pdl/localcomm/refs.py::ref_key`,
which already turns `929a` into a zero-padded number plus tail
(`"000929a"`) and is exercised by `test_refs.py` and
`test_localcomm_views.py`. Range queries then use the same
`ref_key__gte` / `ref_key__lte` string comparison the commentary overlap
query relies on, so no new ordering rule is introduced. `duration_ms` is
dropped from the first version: the reference UI shows no progress or
duration, and the image has no `ffprobe` (section 3.5). If a package is
ever staged twice for the same version URN, the JSON view returns clips
from the lowest package id and logs the overlap; the mobile app's
equivalent is its single `is_active` package.

Management command `ingest_audio`:

- Walks `/host-audio/*/package.yaml`. For each package,
  `get_or_create` the `AudioPackage` row, then replace its clips
  (idempotent, like `ingest_dictionaries`).
- Maps `Author/Work` directory to a version URN via `works:`; the
  filename `line_<ref>.mp4` gives `ref`; `book_<N>/` is ignored when
  `cited_by_book: false`, else the ref becomes `<N>.<ref>`.
- Does not read the audio itself; the only per-file work is the path
  parse and a size check that the file is non-empty. No `ffprobe` in the
  image (section 3.5), and nothing in the UI needs durations.
- Logs and skips files whose path does not parse or whose `Author/Work`
  is not in the manifest, and reports counts per work at the end so the
  README can record measured figures.
- Validates coverage: for each version URN, parse the mounted TEI file
  directly (`<l n>` per top-level `textpart`, the same walk Appendix A
  used) and print lines with no clip and clips with no line. Do **not**
  use the resolver's `getReffs` for this: it cannot see `<sp>`-wrapped
  lines (Appendix A.4) and would wrongly report 66 Shield clips and 18
  Bion clips as "no such line". A third column, "unreachable in the
  viewer" (TEI lines absent from `getReffs`), is printed for information.
  For the Hesiod lettered zip the expected result is 0 missing, 0 extra,
  66 unreachable (all in the Shield); this is a check, not an assumption.

Entrypoint step, after the commentaries step:

```sh
if [ ! -f "${SENTINEL_DIR}/.audio_ingested" ] && [ -d /host-audio ]; then
    python manage.py ingest_audio && touch "${SENTINEL_DIR}/.audio_ingested"
fi
```

### 4.3 HTTP API

Two routes added to `api_patterns` in `sv_pdl/urls.py`:

- `GET /library/audio/<urn>/json/` — `urn` is a passage URN such as
  `urn:cts:greekLit:tlg0020.tlg001.perseus-grc2:1-30`. Returns

  ```json
  {"package": {"slug": "...", "label": "...", "license": "CC BY-SA 4.0",
               "attribution": "..."},
   "clips": [{"ref": "1", "url": "/library/audio/clip/<slug>/<version urn>/1/"}, …]}
  ```

  Range resolution: the passage URN is split at its **last** colon into
  the version URN and the reference. `parse_urn` from
  `sv_pdl/localcomm/refs.py` is not used for the URN, because it
  deliberately drops the edition (commentaries are edition-agnostic);
  audio is edition-specific, so `…tlg0533.tlg018.perseus-grc3` must not
  match a grc4 passage. `split_range` and `ref_key` from the same module
  are reused for the reference. The query is `version_urn = X AND ref_key >= ref_key(start) AND ref_key
  <= ref_key(end)`, ordered by `ref_key`. For the live page `…:928-931`
  this yields 24 clips in the same order as the 24 `text-part` elements.
  A text with no package returns `{"package": null, "clips": []}` with
  200, so the widget can hide itself the way `WidgetPerseusCommentary`
  hides on an empty result.

- `GET /library/audio/clip/<slug>/<version urn>/<ref>/` — serves the file
  under `/host-audio/<root_dir>/<path>` for the clip with that natural
  key. (Implemented this way rather than by database id, so URLs are
  deterministic across installs and re-ingests; see section 12.) The path
  is taken from the database row, never from the request, so no traversal
  surface exists. The route
  is independent of `DEBUG`, unlike the existing `MEDIA_URL` helper
  (section 3.4).

  **It must answer byte-range requests.** Chrome asks for `Range:
  bytes=0-` on every media load (section 3.4), and Django's `FileResponse`
  ignores the header. Chrome tolerated the resulting 200 in the headless
  test, but Apple's Safari documentation requires servers to honour byte
  ranges for media, and Firefox was not tested. Two ways to get 206
  responses without a new dependency, both already in the image:

  1. Build the response with WhiteNoise's responder: instantiate
     `whitenoise.responders.StaticFile(path, headers)` and return its
     `get_response(request.method, request.META)` wrapped in an
     `HttpResponse`/`StreamingHttpResponse`. This reuses the Range parser
     and 416 handling that WhiteNoise already tests, at the cost of using
     a class that is not part of its documented public API (pin is
     `whitenoise==6.7.0`; the class exists there, verified live).
  2. Implement the single-range case by hand: parse `bytes=a-b`, seek,
     return `StreamingHttpResponse(status=206)` with `Content-Range`,
     `Content-Length`, and `Accept-Ranges: bytes`; return 416 for an
     unsatisfiable range and 200 otherwise. About 40 lines, fully under
     this repo's tests.

  The proposal picks option 2 so the behaviour is explicit and covered by
  `test_localaudio_views.py`; option 1 is the fallback if the hand-rolled
  version shows a gap. Either way the view sets `Content-Type: audio/mp4`
  and `Cache-Control: public, max-age=86400`.

Rate limit: a page in continuous mode makes one JSON request plus one
per clip (30 to about 50) over a few minutes at 5 s per clip, well inside
`200/m`. No change to the limiter is proposed.

Site cache: `UpdateCacheMiddleware` / `FetchFromCacheMiddleware` are
active with `CACHE_MIDDLEWARE_SECONDS = 900`, backed by a per-process
`LocMemCache` in the local stack (no `REDIS_URL`; verified live with a
cache round-trip). The JSON endpoint is therefore cached for up to 15
minutes per gunicorn worker, exactly like the commentary endpoint; after
a re-ingest, restart the container or wait. The clip endpoint must return
a `StreamingHttpResponse`/`FileResponse`: Django's cache middleware does
not store streaming responses, so a full 200 body is never cached and
replayed to a later `Range` request. (Middleware behaviour per Django
source; the exclusion was not exercised here.)

### 4.4 Frontend

**Playback engine.** One `<audio>` element owned by a new `AudioPlayer`
Vuex module (`static/src/js/vuex/audio/`): state
`{ clipsByRef, package, playingRef, continuous }`, actions
`LOAD_AUDIO(passageUrn)`, `PLAY(ref)`, `STOP`, `TOGGLE_CONTINUOUS`. `PLAY`
sets `src` to the clip URL and calls `play()`; the element's `ended` event
dispatches the next mapped ref in **document order** when `continuous` is
true, or clears `playingRef` when it is false or the page has no further
clip. Document order is taken from the rendered leaf `text-part`
elements, not from `ref_key`: live, Apollonius renders `2.381, 2.382a,
2.383a, 2.382, 2.383`, so a sort by key would read the lines out of
sequence. `READER_LOAD` dispatches `STOP` before loading a new passage,
so navigating mid-clip silences the player and the next page starts
idle. `continuous` is added to the `vuex-persistedstate` `paths` list in
`config.js`, matching the mobile app's persisted preference. `LOAD_AUDIO`
is pushed onto the `ps` promise list in the existing `READER_LOAD` action
(`static/src/js/vuex/reader/actions.js:29-33`) right after the
`api.getPerseusCommentaryEntries(leftUrn, …)` call, which is already keyed
by the same left passage URN, using a new `api.getAudio(urn, cb)` helper.
Browsers block `play()` without a user gesture; every chain starts from a
click on a line icon, and a page change ends the chain (as on Android), so
no autoplay exemption is needed. The headless test confirmed `play()`
resolves once a gesture policy is satisfied.

**Per-line control (mirrors section 2.1).** `TextPart.vue` gains a new
first flex child, `<span class="audio-toggle">`, placed **before** the
existing `.a` `router-link` rather than inside it: `.a` is an anchor, and a
button nested in an anchor would both follow the link and be invalid HTML.
`.textpart` is already `display: flex` (`_text.scss:141`), so the span
becomes a third column to the left of the line number, which is where the
mobile app puts it. It renders only when `clipsByRef[reference]` exists
and the text-part is a leaf (`class` contains `leaf`). It shows the
FontAwesome `play` icon, or `stop` when `playingRef === reference`;
`faPlay` and `faStop` are added to `icons.js` (both exist in
`@fortawesome/free-solid-svg-icons` 5.x, already a dependency). Clicking
dispatches `PLAY(reference)` or `STOP`. The span gets its own colour rule
in `_text.scss` next to the `.a` rules (dim grey until the passage is
hovered, matching the mobile app's muted tint), plus a rule that keeps
the playing line's icon visible regardless of hover, and a
`display: none` in `_print.scss` alongside the existing `.textpart > .a`
print rule. Only the left (`highlighting: true`) passage gets controls;
parallel translations are unchanged.

**Sidebar widget "Audio"** (`WidgetAudio.vue`, added to the right slot of
`Reader.vue` after `widget-display-settings`, hidden when `package` is
null). Contents, top to bottom:

1. A checkbox "Continuous audio" bound to `continuous`, the web
   equivalent of the mobile app's overflow-menu item.
2. A status line: "Playing line N" while playing, "Stopped" otherwise,
   replacing the mobile app's snackbars. When continuous playback reaches
   the last mapped line of the page, the status reads "End of page audio.
   Use the next-page arrow to continue." and `continuous` stays as set
   (a deliberate departure from Android, which turns the toggle off; the
   web reader's next-page arrow is one click away in the same view).
3. The package label and the attribution text from `package.attribution`,
   as plain text below the controls.

**Not proposed**, to stay close to the reference UI (section 2.2): seek
bar, playback speed, skip buttons, a floating player bar, playing-line
highlight, auto-scroll, or automatic page turns. Each is a one-widget
follow-up if wanted; see section 11 (11.2 is the playing-line highlight,
which is the most likely first addition because `playingRef` is already
in the store).

### 4.5 Licensing and documentation

- `sv_pdl/templates/licenses.html` gains a "Data — audio" table beside
  the existing "Data — text corpora" and "Data — dictionaries" tables,
  and the README "Licenses" section a matching row: CC BY-SA 4.0, with
  the full attribution notice reproduced (section 1.5 requires keeping
  it). The root `LICENSE` file's MIT list (lines 77–78 name the two
  existing local apps) gains `sv_pdl/localaudio/**`.
- README additions: a "Features" table row (`Audio` · `/library/audio/…` ·
  `Postgres via sv_pdl/localaudio` + `/host-audio` files · offline ✓), a
  "Data volumes" row with the measured clip count, the staging
  instructions, the sentinel name, and the re-ingest recipe. Figures are to
  be filled in from the ingest command's output on a real run, per the
  repo's "verify before writing" convention.
- `SBOM-…md`: no new Python or npm dependency is introduced (FontAwesome
  icons and axios are already present).

## 5. Implementation steps

1. `bootstrap.sh`: `SCAIFE_AUDIO_SOURCES` export; compose override: the
   `/host-audio:ro` mount.
2. `sv_pdl/localaudio/`: `apps.py`, `models.py`, `migrations/0001_initial.py`
   (generated deliberately, committed by the user, per the entrypoint
   comment), `management/commands/ingest_audio.py`, `views.py`.
3. `sv_pdl/settings.py`: add `sv_pdl.localaudio` to `INSTALLED_APPS`.
   `sv_pdl/urls.py`: the two routes. `deploy/entrypoint.sh`: the sentinel
   step. `sv_pdl/openapi_spec.py`: describe the JSON route.
4. Frontend: `vuex/audio/*`, `api/index.js` `getAudio`, `constants.js`
   entries, `icons.js` (`faPlay`, `faStop`), `TextPart.vue`,
   `WidgetAudio.vue`, `Reader.vue`, `config.js` persisted path, `_text.scss`
   rules for `.audio-toggle`.
5. Docs and licence pages (section 4.5).
6. Stage the lettered zip under `data-sources/audio/…`, write
   `package.yaml`, run `bootstrap.sh`, record the measured counts. Any of
   the other 14 packages is staged the same way with its manifest from
   Appendix A.3; no code changes.

Everything is left as uncommitted working-tree changes; no git mutation is
part of this plan.

## 6. Tests

Python (`sv_pdl/tests/`, run with `bash scripts/run-tests.sh`):

- `test_localaudio_views.py` (same `TestCase` + `setUpTestData` shape as
  `test_localcomm_views.py`): JSON shape for a range with clips, for a
  range with lettered refs (`928-931` must return 24 clips in the order
  `928, 929, 929a … 929t, 930, 931`, matching the live `text_html`), for
  a text with no package (200, empty), and for a bad URN (404). Clip
  route: `Content-Type: audio/mp4` and `Accept-Ranges: bytes` on a plain
  GET; `Range: bytes=0-` gives 206 with the full length; `bytes=100-199`
  gives 206, `Content-Range: bytes 100-199/<size>` and exactly 100 bytes;
  an unsatisfiable range gives 416; unknown id gives 404; the served bytes
  equal the file on disk.
- `test_localaudio_ingest.py`: ingest a temporary tree with fake files
  including `line_929a.mp4`, a `book_2/line_382a.mp4` under a
  `cited_by_book: true` work (expect ref `2.382a`), and a per-work
  override object; assert rows, `ref_key`, idempotency on a second run,
  and that an unmapped `Author/Work` is skipped with a log line, not an
  exception.
- JSON view edition test: clips ingested for `…perseus-grc3` are not
  returned for a `…perseus-grc4` passage URN of the same work.
- `test_offline_wiring.py`: `test_audio_route_uses_local_view`, app in
  `INSTALLED_APPS`, and the mount path constant.
- Integration (tagged): after a real ingest, clip count per version URN
  equals the TEI `<l>` count from section 3.1 (1,042 / 831 / 479), and
  for every staged package the coverage report's missing/extra counts
  equal Appendix A.2.

Frontend (`test/WidgetAudio.spec.js`, jest, runs in the image build):
widget hidden when `package` is null; checkbox toggles `continuous`;
`ended` with `continuous` true dispatches the next ref and stops at the
last mapped ref.

Lint: `bash scripts/lint.sh` must stay clean.

## 7. Storage and performance figures

| Item | Value | Basis |
|---|---|---|
| Clips (Hesiod, lettered) | 2,352 | `unzip -l` |
| Bytes on disk, unpacked | ~157 MB | 155,743,163 bytes (unlettered zip, uncompressed) plus 24 lettered files at ~67 KB |
| Mean clip | 5.18 s, ~67 KB | ffprobe over the package (host) |
| Requests per page in continuous mode | 1 JSON + one per clip (30 nodes per page; up to 50 numbered lines around the lettered block) | live `Link` headers |
| Database rows | 2,352 + 1 | one per clip plus the package |
| All 15 packages, if staged | 65,051 clips, about 4.0 GB unpacked | Appendix A.2; zip sizes on disk |

Nothing here needs a Docker volume; the files stay on the host mount and
Postgres holds only paths and refs.

## 8. Alternatives considered

- **Serve the mount with WhiteNoise or the `MEDIA_URL` helper instead of a
  view.** Rejected: the helper is DEBUG-only (section 3.4) and both would
  expose the whole directory tree; the view serves only rows the ingest
  accepted.
- **Whole-work audio files with a cue table.** Rejected: the data is
  already per line and the reference UI is per line. Concatenation would
  also need the sub-line timing that does not exist (section 1.4).
- **Store clips in Postgres (bytea).** Rejected: binary blobs in the
  database for no query benefit, and re-ingest cost (about 157 MB for Hesiod alone).
- **Bundle the zip into the image.** Rejected: it is not in any remote and
  would add 150 MB to a layer that rebuilds on every source change.

## 9. Not verified / open

- **Firefox and Safari playback.** Only headless Chrome was exercised
  (section 3.4). Safari's byte-range requirement is the reason the clip
  view implements 206 responses; whether that is sufficient for Safari
  needs one manual check on first bring-up.
- **End-of-clip `ended` event timing.** The headless run used a virtual
  time budget and did not reach `ended`; continuous playback relies on
  that event and should be checked by hand on the first page.
- **Distribution of the zip.** It exists only on this machine; the
  proposal assumes the user copies it into `data-sources/audio/`. If it is
  to be published, the CC BY-SA notice must travel with it.
- **Bion, Fragmenta poem 3** is unreachable in the reader and 66 Shield
  of Heracles lines cannot be addressed individually (Appendix A.4: a
  direct-child citation XPath versus `<sp>`-wrapped lines in the Perseus
  TEI). Bion's 18 clips stay unused until the `refsDecl` is fixed
  upstream or patched locally; Shield audio is unaffected. The fix is
  written up as optional follow-up 11.1.
- **Callimachus `perseus-grc4`** shares line numbering with grc3 except
  one added line; aliasing the package to both editions is optional
  follow-up 11.3.
- **The `synth_index.csv` timing data** could support word highlighting
  later, but it is stale for retried lines and would need the
  `wav_retry_*` indexes merged first.

## 10. Review log (live stack, 2026-09-30)

Changes made to this proposal after starting the stack and re-checking
each claim. Each item names what was wrong or missing and what changed.

1. **Passage JSON shape was misdescribed.** The body has no `_prev` /
   `_next`; those come from the `Link` header via `api/pagination`. The
   recorded golden file had merged them. Section 3.2 corrected.
2. **Page bounds are node counts, not line numbers.** `…:901-930` links to
   next `…:931-980`. Pages around Theogony 929a–t therefore span more
   numbered lines than 30. Sections 3.2 and 7 corrected.
3. **Lettered lines confirmed end to end.** The live `text_html` for
   `928-931` carries `reference="929a"` … `"929t"`, and `…:929a` is a valid
   passage URN. The lettered zip is now stated as verified, not inferred.
4. **`ref_sort` replaced by the existing `ref_key`.** `localcomm/refs.py`
   already zero-pads numeric prefixes and keeps the letter tail, and it is
   covered by existing tests. Section 4.2 now reuses it.
5. **`duration_ms` dropped.** `ffprobe` is absent from the image and the
   reference UI never displays durations. Sections 4.2 and 4.3.
6. **Range support is a requirement, not a nice-to-have.** Django 5.2.17
   has no Range handling in `FileResponse` or the static view; Chrome asks
   for `bytes=0-` on every clip. Section 4.3 now specifies a 206-capable
   view with tests, with WhiteNoise's responder as a fallback.
7. **Chrome decode verified.** `canPlayType` "probably", metadata loaded,
   `playing` fired, `play()` resolved for a real clip served over HTTP.
   Section 3.4. Firefox and Safari remain open (section 9).
8. **Gutter placement corrected.** The line-number column is a
   `router-link`; the icon must be a sibling flex child before it, not a
   child of it. Section 4.4 also adds the print stylesheet rule.
9. **Load hook pinned to a line.** `LOAD_AUDIO` joins the `ps` list in
   `READER_LOAD` beside the commentary fetch, which uses the same
   `leftUrn`. Section 4.4.
10. **Licensing bookkeeping added.** Root `LICENSE` MIT list and the
    `licenses.html` "Data —" tables. Section 4.5.
11. **Multiple packages for one URN.** Not handled before; the JSON view
    now defines a deterministic choice and the ingest logs overlaps.
    Section 4.2.
12. **Test patterns named.** Python `TestCase` + `setUpTestData` and jest
    `shallowMount` with a mock store, matching existing specs. Sections
    3.5 and 6. Baseline before any change: 123/123 unit tests pass.
13. **All 15 packages mapped and diffed against the Perseus TEI in this
    repo** (Appendix A, added after the first review): folder → URN for
    every work, the `N.n` citation rule confirmed live for every
    multi-book text, 87/101 exact matches, every remaining gap traced to
    a `<gap>` line or the pipeline's deliberate skip of Theocritus 28–30,
    and one viewer defect found (Bion Fragmenta poem 3). The manifest
    key `book_in_ref` became `cited_by_book` with a per-work override.
14. **Bion poem 3 diagnosed.** The TEI's line-level `refsDecl` XPath
    requires `<l>` as a direct child of the poem div, while poem 3's lines
    are inside `<sp>`; the TOC is built from deepest-level `getReffs`
    only, so the poem gets no node and `heal()` redirects to poem 4.
    The same pattern hides 66 lines of Hesiod's Shield from the TOC and
    from direct links, though every Shield line still renders inside the
    reader's pages. Appendix A.4 gives the evidence and three fixes.
15. **Whole-document re-review.** Found and fixed: the JSON view was
    going to use `parse_urn`, which drops the edition (audio must stay
    edition-specific); the ingest coverage check was going to use the
    resolver, which cannot see `<sp>`-wrapped lines and would have
    flagged 84 valid clips; continuous playback was ordered by sort key,
    which misorders Apollonius `2.382a`; no stop on page navigation;
    the site cache middleware (900 s, LocMemCache, verified live) was
    not considered; a stale `ffprobe` sentence; the Shield caveat was
    missing from section 3.1; tests lacked book-cited and edition cases.
    Sections 0, 1.6, 3.1, 4.2–4.5, 5–8, A.3 and A.5 updated.

## 12. Implementation status (2026-09-30)

Implemented as specified in sections 4–6, left as uncommitted changes in
the working tree. Verified against the rebuilt stack:

| Check | Result |
|---|---|
| Image build (jest runs inside it) | 8 suites, 25 tests pass, including the new `WidgetAudio.spec.js` |
| `migrate` | `localaudio.0001_initial` applied; `makemigrations --check` clean (canary test) |
| Boot-time ingest | 2,352 clips; coverage 1042/1042, 831/831, 479/479, 0 missing, 0 extra |
| `--resolver-check` | Shield 66 unreachable, Theogony 0, Works and Days 0 (as A.4 predicted) |
| Unit suite | 144 tests pass (123 before + 21 new) |
| Integration suite | 181 tests pass |
| Lint | clean |
| JSON endpoint, live | `928-931` → 24 clips in document order, licence and attribution present; unknown text → `{"package": null, "clips": []}`; bad URN → 404 |
| Clip endpoint, live | 200 with `Accept-Ranges`, `Cache-Control`; `bytes=0-` → 206 identical to the file; `bytes=100-199` → 206, 100 bytes matching; `bytes=9999999-` → 416; unknown id → 404 |
| Reader page, headless Chrome | 24 play icons for the 24 rendered lines (`929a`–`929t` included), Audio widget with checkbox and attribution, one `<audio>` element |
| Real click, default autoplay policy | trusted click on line 928 → clip plays (`currentTime` 2.24 s at 2.5 s); with continuous on, playback advanced to 929 when the clip ended; clicking the playing line stopped it; `continuous` persisted in localStorage |

Deviations from the text above, all recorded in the code comments:

- `book_in_ref` is `cited_by_book` (section 4.1 already says so); a
  `works:` value may be a URN string or `{urn, cited_by_book}`.
- The ingest's resolver column is opt-in (`--resolver-check`) because it
  calls `getReffs` on every text, which is slow on the large corpora.
- The frontend loads clips for the passage URN the server *resolved*
  (inside the `getPassage` callback), not the requested one, so a healed
  URN still gets the right clips.
- A `HEAD` on the clip route returns the headers without a body.
- A 22-clip sample package (Homeric Hymn 27 to Artemis, 1.5 MB) is
  tracked in the repo under `audio-samples/` and mounted at
  `/host-audio-samples`, so a clone without the large packages still has
  a working demo; `ingest_audio` walks that mount and `/host-audio`, and
  `AudioPackage.root_dir` is the package's absolute directory.
- Clip URLs use the natural key (package slug, version URN, reference)
  instead of the row id. During verification a re-ingest renumbered the
  rows and a browser holding a cached JSON response hit 404s for the old
  ids; with natural keys the URL cannot go stale that way. Verified by a
  test that deletes and recreates a row and asserts the URL is unchanged.

Section 9 items still open after implementation: Firefox and Safari
playback, zip distribution, and the two `refsDecl` fixes (11.1).

## 11. Optional follow-ups (not part of this proposal)

Each item is independent of the audio work and can be done later or not
at all. None blocks anything in sections 4–6.

### 11.1 Make `<sp>`-wrapped lines citable in Bion Fragmenta and the Shield

Background and evidence: Appendix A.4. Two Perseus TEI files declare the
line level with a direct-child XPath while wrapping some lines in `<sp>`,
so those lines have no TOC node. Effect today: Bion Fragmenta poem 3 (18
lines) cannot be opened at all; 66 lines of Hesiod's Shield render inside
pages but cannot be linked, listed in the TOC, or used as a page endpoint.

Change (one attribute in each file, matching the 48 sibling files that
already use the descendant form):

| File | `replacementPattern` today | Change to |
|---|---|---|
| `data/tlg0036/tlg003/tlg0036.tlg003.perseus-grc2.xml` (line 57) | `…/tei:div/tei:div[@n='$1']/tei:l[@n='$2']` | `…/tei:div/tei:div[@n='$1']//tei:l[@n='$2']` |
| `data/tlg0020/tlg003/tlg0020.tlg003.perseus-grc2.xml` (line 48) | `…/tei:body/tei:div/tei:l[@n='$1']` | `…/tei:body/tei:div//tei:l[@n='$1']` |

Where to apply it, in order of preference:

1. **Upstream pull request** to `PerseusDL/canonical-greekLit` (the
   corpus here is at `790c842`, 2026-08-03). First check whether upstream
   has already changed either file; that was not done here because the
   setup is offline.
2. **Local patch** applied by `bootstrap.sh` after the corpus fetch,
   guarded so it is idempotent and skipped once upstream carries the fix.
   Record it in the README under "Changes made to the upstream app"
   (data, not code) and in `packages/README.md` only if the resolver is
   touched. The corpus directory is gitignored, so the patch must live in
   this repo as a script or a `sed` line, not as an edited file.

Expected results after the change, to be verified live and written into
the README as measured numbers:

- `/library/urn:cts:greekLit:tlg0036.tlg003.perseus-grc2/json/` TOC has
  16 entries starting at `3.1-3.5`, and `…:3.1/json/` returns
  `reference="3.1"`.
- `/library/urn:cts:greekLit:tlg0020.tlg003.perseus-grc2/json/` TOC has
  479 entries, and `…:78/json/` returns `reference="78"`.
- Resolver and ATLAS caches: delete `sv-data/atlas/sentinels/.atlas_db_prepared`
  so `prepare_atlas_db` re-runs, since the entrypoint rebuilds ATLAS only
  when that sentinel is absent; the search index sentinel is cleared by
  that step automatically (`deploy/entrypoint.sh`).
- Add two integration-tagged tests in `sv_pdl/tests/` asserting the TOC
  counts above, so a corpus re-fetch that drops the patch is caught.
- Audio: after the fix, the ingest coverage step (A.5) should report
  Bion Fragmenta 116/116 reachable and the Hesiod package unchanged.

Not recommended: changing `toc()` in the vendored resolver to union
every citation level. It would make poem 3 openable as a whole but its
lines would still not be addressable, and it diverges from upstream for
a data defect.

### 11.2 Playing-line highlight

`playingRef` is already in the store (section 4.4). A one-rule CSS
change on `.textpart` plus a class binding in `TextPart.vue` would
highlight the line being read. Deliberately left out to stay close to
the reference UI, which has no such highlight.

### 11.3 Callimachus `perseus-grc4` alias

Appendix A.2: grc4 shares every line number with grc3 except one added
line (`121a`, Hymn to Artemis). The manifest could list both URNs for
the same folders so readers of either edition get audio. Needs a
`works:` entry that accepts a list of URNs, and the coverage check would
report the single extra line.

### 11.4 Word-level highlighting from the synthesis timing tables

Section 1.4: `synth_index.csv` holds per-token frame durations that
could be converted to word offsets, but it is stale for lines that went
through the retry pass and the AAC encoder delay is unmeasured. A
prerequisite is a merge of the `wav_retry_*` indexes in the hesiod
project and a measured offset; only then is sub-line sync worth
designing.

## Appendix A. Package → CTS URN mapping for all 15 packages

Verified 2026-09-30 against `~/git/hesiod` (head `51d1e0e`, 2026-09-29)
and this repo's `data-sources/canonical-greekLit/data`, with the viewer
running. Method: every `.mp4` path in every release zip was parsed into
`(Author, Work, book, line)`; every `<l n>` in the TEI file named by the
corpus's `lines.csv` `source` column was collected per top-level
`<div type="textpart">`; the two sets were diffed per work
(scratch script, output kept out of the repo). Every TEI file exists here.
No zip contains anything but `.mp4` entries, and no folder string is
outside the table below.

### A.1 Reference rule (live)

- Works whose TEI has top-level `textpart` divs (book, poem, epigram,
  "tetralogy") are cited `<book>.<line>` by the viewer: the TOC lists one
  entry per top-level div, the first page is e.g. `1.1-1.30`, and leaf
  `text-part` elements carry `reference="1.1"`. So
  `Author/Work/book_N/line_n.mp4` → ref `N.n`.
- Works with a single `line` level are cited `<line>` and `book_1` is a
  constant: `book_1/line_n.mp4` → ref `n` (Hesiod, Hymns, Callimachus,
  Aratus, Colluthus, Tryphiodorus, Bion 1–2, Moschus 1–4).
- Letter suffixes and underscore ranges pass through unchanged: live leaf
  references include `2.382a` (Apollonius), `21.74_75` and `21.75_74`
  (Nonnus), `5.41_43` (Theocritus), `929a` (Hesiod). Nonnus book 1 begins
  at `1.0` (live first page `1.0-1.29`); the package has `line_0.mp4`.
- `ref_key` from `sv_pdl/localcomm/refs.py` sorts all of these: it
  zero-pads each dotted numeric token and keeps the tail.

### A.2 Per-package table

"TEI" is the `<l>` count in this repo's file. "Clips" is the unlettered
zip; "Lettered" is the `_lettered` zip where one exists (seven corpora).
"Gap" is TEI minus the best zip, with the cause.

| Package (`<c>_chamberlain_tts_female[_lettered].zip`) | Folder `Author/Work` | Version URN (`urn:cts:greekLit:`…) | TEI | Clips | Lettered | Gap and cause | Zip MB |
|---|---|---|---|---|---|---|---|
| hesiod | `Hesiod/Theogony` | `tlg0020.tlg001.perseus-grc2` | 1,042 | 1,022 | 1,042 | 0 | 147 / 149 |
| hesiod | `Hesiod/Works and Days` | `tlg0020.tlg002.perseus-grc2` | 831 | 827 | 831 | 0 | ″ |
| hesiod | `Hesiod/Shield of Heracles` | `tlg0020.tlg003.perseus-grc2` | 479 | 479 | 479 | 0 | ″ |
| hymns | `Homeric Hymns/Hymn N to …` (33 folders, A.3) | `tlg0013.tlg001` … `tlg033` `.perseus-grc2` | 2,342 | 2,326 | 2,342 | 0 | 147 / 148 |
| homer | `Homer/Odyssey` | `tlg0012.tlg002.perseus-grc2` | 12,107 | 12,107 | – | 0 | 767 |
| homer | `Homer/Epigrams` | `tlg0012.tlg003.perseus-grc1` | 109 | 109 | – | 0 | ″ |
| apollonius | `Apollonius Rhodius/Argonautica` | `tlg0001.tlg001.perseus-grc2` | 5,834 | 5,832 | 5,834 | 0 | 367 / 367 |
| theocritus | `Theocritus/Εἰδύλλια` | `tlg0005.tlg001.perseus-grc2` | 2,717 | 2,593 | 2,617 | 100: poems 28–30 (97 lines) left out by design as non-hexameter (`skip_books` in `corpora.py`); 27.9 and 27.44 are `<gap>`; 5.41_43 is an ellipsis line | 163 / 164 |
| moschus | `Moschus/Eros Drapeta` | `tlg0035.tlg001.perseus-grc2` | 29 | 29 | – | 0 | 31 |
| moschus | `Moschus/Europa` | `tlg0035.tlg002.perseus-grc2` | 166 | 166 | – | 0 | ″ |
| moschus | `Moschus/Epitaphius Bios` | `tlg0035.tlg003.perseus-grc2` | 126 | 126 | – | 0 | ″ |
| moschus | `Moschus/Megara` | `tlg0035.tlg004.perseus-grc2` | 125 | 125 | – | 0 | ″ |
| moschus | `Moschus/Fragmenta` (books 4–7) | `tlg0035.tlg005.perseus-grc2` | 35 | 35 | – | 0 | ″ |
| bion | `Bion of Phlossa/Epitaphius Adonis` | `tlg0036.tlg001.perseus-grc2` | 98 | 98 | – | 0 | 16 |
| bion | `Bion of Phlossa/Epithalamium Achillis et Deidameiae` | `tlg0036.tlg002.perseus-grc2` | 32 | 32 | – | 0 | ″ |
| bion | `Bion of Phlossa/Fragmenta` (books 3–18) | `tlg0036.tlg003.perseus-grc2` | 116 | 116 | – | 0, but see A.4 (poem 3) | ″ |
| callimachus | `Callimachus/Hymn to Zeus` | `tlg0533.tlg015.perseus-grc3` | 96 | 96 | – | 0 | 59 |
| callimachus | `Callimachus/Hymn to Apollo` | `tlg0533.tlg016.perseus-grc3` | 113 | 113 | – | 0 | ″ |
| callimachus | `Callimachus/Hymn to Artemis` | `tlg0533.tlg017.perseus-grc3` | 268 | 268 | – | 0 | ″ |
| callimachus | `Callimachus/Hymn to Delos` | `tlg0533.tlg018.perseus-grc3` | 326 | 325 | – | 1: line 200 is `<gap reason="lost">` | ″ |
| callimachus | `Callimachus/Hymn to Demeter` | `tlg0533.tlg020.perseus-grc3` | 138 | 138 | – | 0 | ″ |
| aratus | `Aratus Solensis/Phaenomena` | `tlg0653.tlg001.perseus-grc2` | 1,155 | 1,154 | 1,155 | 0 | 73 / 73 |
| quintus | `Quintus Smyrnaeus/Fall of Troy` | `tlg2046.tlg001.perseus-grc2` | 8,825 | 8,770 | 8,804 | 21: all `<gap>` lines (4.525 and twenty lettered lines such as 1.57a, 13.75a–c) | 557 / 559 |
| oppian | `Oppian/Halieutica` | `tlg0023.tlg001.perseus-grc2` | 3,506 | 3,506 | – | 0 | 222 |
| oppian_apamea | `Oppian of Apamea/Cynegetica` | `tlg0024.tlg001.perseus-grc2` | 2,144 | 2,144 | – | 0 | 136 |
| nonnus | `Nonnus of Panopolis/Dionysiaca` | `tlg2045.tlg001.perseus-grc2` | 21,329 | 21,325 | 21,329 | 0 (the four range-named lines are in the lettered zip) | 1,391 / 1,391 |
| tryphiodorus | `Tryphiodorus/The Taking of Ilios` | `tlg0647.tlg001.perseus-grc2` | 691 | 691 | – | 0 | 44 |
| colluthus | `Colluthus of Lycopolis/The Rape of Helen` | `tlg4081.tlg001.perseus-grc2` | 394 | 394 | – | 0 | 26 |

Totals: TEI 65,173 lines; unlettered zips 64,946 clips; best available
set (lettered where it exists) 65,051 clips; 122 lines without audio, all
accounted for above. 87 of the 101 work/variant pairs match the TEI
exactly; the other 14 differ only by the lettered lines the unlettered
zips omit or by the gaps listed.

Editions: Homer's Epigrams exist here only as `perseus-grc1`. Callimachus
exists as `perseus-grc3` (the file hesiod read) and `perseus-grc4`; their
`<l n>` sets are identical for four hymns, and grc4 adds `121a` to the
Hymn to Artemis. The mapping targets grc3; grc4 could be aliased later
without re-ingest. Every other work has a single `perseus-grc2` edition.

### A.3 Manifests

One `package.yaml` per package under `data-sources/audio/<package>/`.
`cited_by_book: true` means the ref is `N.n`; `false` means `n` and the
`book_1` segment is ignored. Author/Work strings are the zip folders,
verbatim. The common header fields (`slug`, `label`, `license`,
`attribution`, `source`) are as in section 4.1 and omitted below; the
attribution block is the same for every package because all share one
`LICENSE`.

```yaml
# hesiod_chamberlain_tts_female_lettered
cited_by_book: false
works:
  "Hesiod/Theogony":           urn:cts:greekLit:tlg0020.tlg001.perseus-grc2
  "Hesiod/Works and Days":     urn:cts:greekLit:tlg0020.tlg002.perseus-grc2
  "Hesiod/Shield of Heracles": urn:cts:greekLit:tlg0020.tlg003.perseus-grc2

# hymns_chamberlain_tts_female_lettered  (folder title N -> tlg0013.tlg0NN)
cited_by_book: false
works:
  "Homeric Hymns/Hymn 1 to Dionysus":                urn:cts:greekLit:tlg0013.tlg001.perseus-grc2
  "Homeric Hymns/Hymn 2 to Demeter":                 urn:cts:greekLit:tlg0013.tlg002.perseus-grc2
  "Homeric Hymns/Hymn 3 to Apollo":                  urn:cts:greekLit:tlg0013.tlg003.perseus-grc2
  "Homeric Hymns/Hymn 4 to Hermes":                  urn:cts:greekLit:tlg0013.tlg004.perseus-grc2
  "Homeric Hymns/Hymn 5 to Aphrodite":               urn:cts:greekLit:tlg0013.tlg005.perseus-grc2
  "Homeric Hymns/Hymn 6 to Aphrodite":               urn:cts:greekLit:tlg0013.tlg006.perseus-grc2
  "Homeric Hymns/Hymn 7 to Dionysus":                urn:cts:greekLit:tlg0013.tlg007.perseus-grc2
  "Homeric Hymns/Hymn 8 to Ares":                    urn:cts:greekLit:tlg0013.tlg008.perseus-grc2
  "Homeric Hymns/Hymn 9 to Artemis":                 urn:cts:greekLit:tlg0013.tlg009.perseus-grc2
  "Homeric Hymns/Hymn 10 to Aphrodite":              urn:cts:greekLit:tlg0013.tlg010.perseus-grc2
  "Homeric Hymns/Hymn 11 to Athena":                 urn:cts:greekLit:tlg0013.tlg011.perseus-grc2
  "Homeric Hymns/Hymn 12 to Hera":                   urn:cts:greekLit:tlg0013.tlg012.perseus-grc2
  "Homeric Hymns/Hymn 13 to Demeter":                urn:cts:greekLit:tlg0013.tlg013.perseus-grc2
  "Homeric Hymns/Hymn 14 to the Mother of the Gods": urn:cts:greekLit:tlg0013.tlg014.perseus-grc2
  "Homeric Hymns/Hymn 15 to Heracles":               urn:cts:greekLit:tlg0013.tlg015.perseus-grc2
  "Homeric Hymns/Hymn 16 to Asclepius":              urn:cts:greekLit:tlg0013.tlg016.perseus-grc2
  "Homeric Hymns/Hymn 17 To the Dioscuri":           urn:cts:greekLit:tlg0013.tlg017.perseus-grc2
  "Homeric Hymns/Hymn 18 to Hermes":                 urn:cts:greekLit:tlg0013.tlg018.perseus-grc2
  "Homeric Hymns/Hymn 19 to Pan":                    urn:cts:greekLit:tlg0013.tlg019.perseus-grc2
  "Homeric Hymns/Hymn 20 to Hephaestus":             urn:cts:greekLit:tlg0013.tlg020.perseus-grc2
  "Homeric Hymns/Hymn 21 to Apollo":                 urn:cts:greekLit:tlg0013.tlg021.perseus-grc2
  "Homeric Hymns/Hymn 22 to Poseidon":               urn:cts:greekLit:tlg0013.tlg022.perseus-grc2
  "Homeric Hymns/Hymn 23 to Zeus":                   urn:cts:greekLit:tlg0013.tlg023.perseus-grc2
  "Homeric Hymns/Hymn 24 to Hestia":                 urn:cts:greekLit:tlg0013.tlg024.perseus-grc2
  "Homeric Hymns/Hymn 25 to the Muses and Apollo":   urn:cts:greekLit:tlg0013.tlg025.perseus-grc2
  "Homeric Hymns/Hymn 26 to Dionysus":               urn:cts:greekLit:tlg0013.tlg026.perseus-grc2
  "Homeric Hymns/Hymn 27 to Artemis":                urn:cts:greekLit:tlg0013.tlg027.perseus-grc2
  "Homeric Hymns/Hymn 28 to Athena":                 urn:cts:greekLit:tlg0013.tlg028.perseus-grc2
  "Homeric Hymns/Hymn 29 to Hestia":                 urn:cts:greekLit:tlg0013.tlg029.perseus-grc2
  "Homeric Hymns/Hymn 30 to Earth":                  urn:cts:greekLit:tlg0013.tlg030.perseus-grc2
  "Homeric Hymns/Hymn 31 to Helios":                 urn:cts:greekLit:tlg0013.tlg031.perseus-grc2
  "Homeric Hymns/Hymn 32 to Selene":                 urn:cts:greekLit:tlg0013.tlg032.perseus-grc2
  "Homeric Hymns/Hymn 33 to the Dioscuri":           urn:cts:greekLit:tlg0013.tlg033.perseus-grc2

# homer_chamberlain_tts_female
cited_by_book: true
works:
  "Homer/Odyssey":  urn:cts:greekLit:tlg0012.tlg002.perseus-grc2
  "Homer/Epigrams": urn:cts:greekLit:tlg0012.tlg003.perseus-grc1

# apollonius_chamberlain_tts_female_lettered
cited_by_book: true
works:
  "Apollonius Rhodius/Argonautica": urn:cts:greekLit:tlg0001.tlg001.perseus-grc2

# theocritus_chamberlain_tts_female_lettered
cited_by_book: true
works:
  "Theocritus/Εἰδύλλια": urn:cts:greekLit:tlg0005.tlg001.perseus-grc2

# moschus_chamberlain_tts_female
cited_by_book: false            # works 1-4
works:
  "Moschus/Eros Drapeta":    urn:cts:greekLit:tlg0035.tlg001.perseus-grc2
  "Moschus/Europa":          urn:cts:greekLit:tlg0035.tlg002.perseus-grc2
  "Moschus/Epitaphius Bios": urn:cts:greekLit:tlg0035.tlg003.perseus-grc2
  "Moschus/Megara":          urn:cts:greekLit:tlg0035.tlg004.perseus-grc2
  "Moschus/Fragmenta":       {urn: urn:cts:greekLit:tlg0035.tlg005.perseus-grc2, cited_by_book: true}

# bion_chamberlain_tts_female
cited_by_book: false            # works 1-2
works:
  "Bion of Phlossa/Epitaphius Adonis":                   urn:cts:greekLit:tlg0036.tlg001.perseus-grc2
  "Bion of Phlossa/Epithalamium Achillis et Deidameiae": urn:cts:greekLit:tlg0036.tlg002.perseus-grc2
  "Bion of Phlossa/Fragmenta":                           {urn: urn:cts:greekLit:tlg0036.tlg003.perseus-grc2, cited_by_book: true}

# callimachus_chamberlain_tts_female
cited_by_book: false
works:
  "Callimachus/Hymn to Zeus":    urn:cts:greekLit:tlg0533.tlg015.perseus-grc3
  "Callimachus/Hymn to Apollo":  urn:cts:greekLit:tlg0533.tlg016.perseus-grc3
  "Callimachus/Hymn to Artemis": urn:cts:greekLit:tlg0533.tlg017.perseus-grc3
  "Callimachus/Hymn to Delos":   urn:cts:greekLit:tlg0533.tlg018.perseus-grc3
  "Callimachus/Hymn to Demeter": urn:cts:greekLit:tlg0533.tlg020.perseus-grc3

# aratus_chamberlain_tts_female_lettered
cited_by_book: false
works:
  "Aratus Solensis/Phaenomena": urn:cts:greekLit:tlg0653.tlg001.perseus-grc2

# quintus_chamberlain_tts_female_lettered
cited_by_book: true
works:
  "Quintus Smyrnaeus/Fall of Troy": urn:cts:greekLit:tlg2046.tlg001.perseus-grc2

# oppian_chamberlain_tts_female
cited_by_book: true
works:
  "Oppian/Halieutica": urn:cts:greekLit:tlg0023.tlg001.perseus-grc2

# oppian_apamea_chamberlain_tts_female
cited_by_book: true
works:
  "Oppian of Apamea/Cynegetica": urn:cts:greekLit:tlg0024.tlg001.perseus-grc2

# nonnus_chamberlain_tts_female_lettered
cited_by_book: true
works:
  "Nonnus of Panopolis/Dionysiaca": urn:cts:greekLit:tlg2045.tlg001.perseus-grc2

# tryphiodorus_chamberlain_tts_female
cited_by_book: false
works:
  "Tryphiodorus/The Taking of Ilios": urn:cts:greekLit:tlg0647.tlg001.perseus-grc2

# colluthus_chamberlain_tts_female
cited_by_book: false
works:
  "Colluthus of Lycopolis/The Rape of Helen": urn:cts:greekLit:tlg4081.tlg001.perseus-grc2
```

Because Moschus and Bion mix single-level works with a book-cited
`Fragmenta`, the manifest allows a per-work override object
(`{urn, cited_by_book}`); section 4.1's top-level `book_in_ref` key is
renamed `cited_by_book` to match. The ingest can also derive the flag
itself from the TEI (top-level `textpart` divs present or not), which is
what the diff script did; the manifest value then serves as a check.

### A.4 Viewer-side finding: lines wrapped in `<sp>` under a direct-child citation XPath

**Cause (verified in the container).** The viewer builds a text's TOC from
`default_resolver().getReffs(urn, level=<citation depth>)`
(`packages/scaife-viewer-core/scaife_viewer/core/cts/collections.py:216-228`),
i.e. from the deepest citation level only. MyCapytain evaluates the
`replacementPattern` XPath from the TEI `refsDecl` literally. Bion's
Fragmenta declares the line level as
`/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1']/tei:l[@n='$2']`
(a direct child `l`), but poem 3's eighteen `<l>` elements sit inside an
`<sp>` (speech) element, so none of them matches. Live in the container:
`getReffs(level=1)` returns all 16 poems including `3`;
`getReffs(level=2)` returns 98 refs, none starting with `3.`;
`getTextualNode(subreference='3.1')` raises `IndexError: list index out
of range`. The TOC tree therefore has no node under poem 3, no page chunk
is ever generated for it, and `heal()`
(`core/cts/heal.py`) redirects any request for `3` or `3.x` to the nearest
node that exists, which is why `…:3.1` renders `4.1` and `…:3` renders
poem 4.

**Second affected text: Hesiod, Shield of Heracles.** Same pattern
(`/tei:body/tei:div/tei:l[@n='$1']`) and five `<sp>` blocks: lines 78–101,
103–114, 327–337, 350–364 and 446–449, 66 lines in all. Live: the TOC
lists 413 of the 479 lines, and a request for `…:78` or `…:77-79` heals to
`77`. Unlike Bion, **every Shield line is still readable**: page bounds
are computed from the reachable refs, so the reader's pages run
`61-126`, `308-348`, `349-393`, `424-457` across the nested runs and the
XSL renders every `<l>` inside the extracted range (walked all 14 pages
live; no numbered line is outside a page). What fails for those 66 lines
is anything that uses a single line as an endpoint: the TOC, a direct
URL, the line-number link in the gutter, and search hits that resolve to
the line. Audio is unaffected there because the clip query is a range
over the page's start and end refs.

**Scope.** Of the 61 target TEI files, 13 declare a direct-child line
XPath; only these two also nest lines inside another element (the rest
have zero nested lines). The other 48 files use `//tei:l`, which reaches
nested lines, which is why Theocritus (2,717 lines, most inside `<sp>`)
and the Odyssey work. Both affected files are at upstream
`PerseusDL/canonical-greekLit` `790c842` (2026-08-03); whether upstream
has since changed either `refsDecl` was not checked (offline).

**Fixes, in order of preference.** (1) Upstream data fix: change the two
`replacementPattern`s to `//tei:l[@n='$1']`, matching the 48 sibling
files. (2) Local patch of the same one-line change applied to the mounted
corpus by `bootstrap.sh` (the corpus is a gitignored clone; the change
would need to be recorded in the README and re-applied on re-fetch).
(3) Resolver-side: have `toc()` union `getReffs` at every level so a
parent with no reachable children still gets a node; that only makes
poem 3 addressable as a whole, not its lines. The audio proposal does
not depend on any of these; it only means Bion poem 3's 18 clips are
unreachable until (1) or (2) lands.

### A.5 Coverage check built into the ingest

The `ingest_audio` coverage step (section 4.2) should reproduce the table
above by parsing the mounted TEI files directly: for each version URN,
report `TEI lines`, `clips`, `missing refs`, `extra refs`, and
`unreachable in viewer`. The expected non-zero "missing" values are
exactly the ones in A.2 (Callimachus Delos 1, Quintus 21, Theocritus
100); "extra" must be 0 everywhere; "unreachable" is expected to be 66
for the Shield and 18 for Bion's Fragmenta until follow-up 11.1 lands,
and 0 elsewhere. Any other value means the wrong zip or a changed corpus.
