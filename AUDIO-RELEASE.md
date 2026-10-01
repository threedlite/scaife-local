# Hosting the audio packages as a GitHub release

The line-by-line audio packages (see "Audio" in `README.md`) are too large
to commit: 15 zips, 4.35 GB, the largest 1.46 GB. This file explains how to
publish them as **release assets** on GitHub instead, and how a user of this
repo then fetches them.

**Status: published.** Release `audio-v1` went live on 2026-10-01 (UTC) at
<https://github.com/threedlite/scaife-local/releases/tag/audio-v1>, created
with the commands below (`gh` 2.87.3). What was measured:

- 17 assets, 4,353,375,924 bytes. Every asset's size and the SHA-256 that
  GitHub reports match the local files.
- The upload took about 2 minutes on this machine's connection (first
  asset created 01:38:46Z, last finished 01:40:51Z).
- The fetch steps were run without a GitHub login for two packages: Hesiod
  (156 MB in 6 s, checksum OK, unzipped tree identical to the copy staged
  by hand) and Bion (checksum OK, staged, ingested with 0 missing and 0
  extra, and a clip served by the viewer was byte-identical to the file in
  the zip). The other 13 zips have not been downloaded back.
- `gh release download` and the web-UI route are untested.

## What a release is, and why it fits

"Release" is a GitHub feature, not a git one. A release is a page attached
to a git **tag**; any files uploaded to it ("assets") are stored by GitHub
outside the repository. They are never part of a commit, a clone or the
repo's size, and each gets a stable public download URL.

| | Limit (GitHub documentation, not measured here) |
|---|---|
| File in a git push | rejected above 100 MiB, warning above 50 MiB |
| Release asset | under 2 GiB per file |
| Assets per release | 1,000 |
| Total release size, download bandwidth | no limit |

Every package fits: the largest, Nonnus, is 1,459,029,927 bytes (1.36 GiB).
Git LFS would also work but counts against a storage and bandwidth quota;
release assets do not.

## Which repo

The release lives **on this repo, `threedlite/scaife-local`**: this is
where the packages are used, and the `package.yaml` manifests that make
them usable belong to this viewer. Someone who clones the repo finds the
audio on its own Releases page.

The zips themselves are build output of the sibling `hesiod` project
(`~/git/hesiod/data/synth/<corpus>_fs2_full/`, gitignored there), which is
why the staging step below reads from that checkout. The tag therefore
points at a commit of this repo, not at the code that produced the audio;
the release notes record the `hesiod` commit instead.

The repo is public, so the download URLs need no login.

## What goes in the release

One zip per corpus, the `_lettered` variant where one exists (it matches
the TEI line for line; `AUDIO-PROPOSAL.md` Appendix A.2). Sizes measured
2026-09-30:

| Asset | Bytes |
|---|---|
| `apollonius_chamberlain_tts_female_lettered.zip` | 384,927,206 |
| `aratus_chamberlain_tts_female_lettered.zip` | 76,409,182 |
| `bion_chamberlain_tts_female.zip` | 16,349,247 |
| `callimachus_chamberlain_tts_female.zip` | 62,242,324 |
| `colluthus_chamberlain_tts_female.zip` | 26,957,595 |
| `hesiod_chamberlain_tts_female_lettered.zip` | 155,729,211 |
| `homer_chamberlain_tts_female.zip` | 803,993,618 |
| `hymns_chamberlain_tts_female_lettered.zip` | 155,343,542 |
| `moschus_chamberlain_tts_female.zip` | 32,060,029 |
| `nonnus_chamberlain_tts_female_lettered.zip` | 1,459,029,927 |
| `oppian_apamea_chamberlain_tts_female.zip` | 142,764,063 |
| `oppian_chamberlain_tts_female.zip` | 233,149,757 |
| `quintus_chamberlain_tts_female_lettered.zip` | 586,204,361 |
| `theocritus_chamberlain_tts_female_lettered.zip` | 171,582,427 |
| `tryphiodorus_chamberlain_tts_female.zip` | 46,607,624 |
| **Total** | **4,353,350,113** |

Plus two small files:

- `SHA256SUMS` — so a download can be verified.
- `AUDIO-LICENSE` — the hesiod project's `LICENSE`, content unchanged. The
  audio is CC BY-SA 4.0 and the attribution notice has to travel with it.
  It is renamed for the release so it is not mistaken for this repo's own
  `LICENSE`, which is a different file (MIT and CC BY 4.0).

### The manifests are not release assets

The zips contain only `.mp4` files, so a package cannot be ingested without
the `package.yaml` that maps each `Author/Work` folder to a CTS version
URN. Those 15 manifests are small text and are tracked in this repo, in
`audio-manifests/<package>.package.yaml`, so a clone already has them and
there is one copy to keep correct. The fetch step below copies the right
one into place.

They were checked on 2026-09-30 against the file listing of each zip and
the TEI in the running container, using the ingest's own parsing code
without writing to the database: every clip maps to a work (0 skipped), no
clip points at a line the TEI lacks (0 extra), and the totals are those of
`AUDIO-PROPOSAL.md` Appendix A.2 (65,173 TEI lines, 65,051 clips, 122
lines without audio: Theocritus 100, Quintus 21, Callimachus *Delos* 1).
Only Hesiod has been through a real ingest; the other 14 packages have not
been unzipped, ingested or played here.

## Creating the release

### 1. Stage the files

This step only gathers the files into one folder on this machine; the
upload to GitHub is step 3. The zips sit in 15 separate directories under
`~/git/hesiod/data/synth/`, alongside other variants that should not be
uploaded, so collecting the chosen 15 in one place lets the checksum and
upload commands each be a single line.

The folder holds symlinks (pointers to the original files) rather than
copies, which avoids duplicating 4.35 GB on disk. `shasum` and `gh` follow
the links and read the real files, so what gets uploaded is the actual zip
under its own name. Tested here: 15 links, checksums in 8 s, and the
`audio-v1` upload was made through these links.

```
STAGE=~/audio-release-stage
HESIOD=~/git/hesiod
mkdir -p "$STAGE"

for d in "$HESIOD"/data/synth/*_fs2_full; do
  c=$(basename "$d" _fs2_full)
  z="$d/${c}_chamberlain_tts_female_lettered.zip"
  [ -f "$z" ] || z="$d/${c}_chamberlain_tts_female.zip"
  ln -s "$z" "$STAGE/"
done

cp "$HESIOD/LICENSE" "$STAGE/AUDIO-LICENSE"

cd "$STAGE"
shasum -a 256 *.zip > SHA256SUMS        # Linux: sha256sum
find -L . -name '*.zip' -size +2147483647c   # must print nothing (2 GiB cap)
```

### 2. Write the release notes

Save as `$STAGE/NOTES.md`. Keep it short, but include the credit to David
Chamberlain and the licence line; the notes are what a visitor to the
release page sees, and the zips themselves carry no notice.

```
Synthesized line-by-line readings of 15 Greek hexameter corpora
(AAC in MP4, mono 44.1 kHz), one zip per corpus. Built by
https://github.com/threedlite/hesiod at commit 51d1e0e.

Derived from David Chamberlain, "A Reading of Homer (work in progress)",
hypotactic.com, © 2016, 2017 David Chamberlain, CC BY 4.0: the
text-to-speech model was trained on his recordings of the Iliad. The texts
read are from the Perseus Digital Library (CC BY-SA 4.0).

Licence: CC BY-SA 4.0. The full attribution notice is in the attached
AUDIO-LICENSE and must accompany any redistribution. (The viewer's own code
is licensed separately; see LICENSE in the repo.)

Verify a download with SHA256SUMS. Each zip needs the matching manifest
from audio-manifests/ in the repo; AUDIO-RELEASE.md there explains how to
fetch and ingest a package.
```

### 3. Create a draft, upload, check, publish

Needs the GitHub CLI logged in as someone with write access to the repo
(`gh auth login`, or `pbpaste | gh auth login --with-token` with a personal
access token that has the `repo` scope). Each command is a single line, so
it can be pasted one at a time.

```
REPO=threedlite/scaife-local
TAG=audio-v1

# Draft first: nothing is public and the tag does not exist yet.
gh release create "$TAG" --repo "$REPO" --draft --target main --title "Audio packages v1" --notes-file "$STAGE/NOTES.md"

# 4.35 GB; expect this to take a while. Safe to re-run after a dropped
# connection: --clobber replaces any half-uploaded asset of the same name.
gh release upload "$TAG" --repo "$REPO" --clobber "$STAGE"/*.zip "$STAGE/SHA256SUMS" "$STAGE/AUDIO-LICENSE"

# Compare names and sizes with the table above before publishing.
gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets[] | [.name, .size] | @tsv'

# Publish. This is the step that creates the tag and makes the URLs live.
gh release edit "$TAG" --repo "$REPO" --draft=false
```

Notes:

- `--target` is a branch or a full commit SHA that already exists **on
  GitHub**; the tag is created there, server-side, when the draft is
  published. No local `git tag` or `git push` is involved.
- The tag should point at a commit of this repo that can play the audio.
  Either merge first and keep `--target main`, or pass the full SHA of a
  pushed commit. `audio-v1` was created the second way, with
  `--target 683ed18ea92cd23c16def7bdbec1b9d1f9866d88` (the head of
  `feature/audio`), because the audio support was not yet on `main`. The
  assets download the same either way; the target only decides which
  commit the tag and the "Source code" links refer to.
- Use a tag that names the data, not the code (`audio-v1`, `audio-v2`, …),
  so it cannot collide with a code version tag later.
- GitHub adds "Source code (zip)" and "(tar.gz)" links for the tagged
  commit to every release. They are generated, not stored, and cannot be
  removed.

**Without the CLI:** on the repo page, Releases → "Draft a new release" →
"Choose a tag", type `audio-v1` and pick "Create new tag on publish" →
set the target → title and notes → drag the files into the attachment box
→ "Save draft", then "Publish release" once every upload shows complete.
Browser uploads of files over a gigabyte tend to be less reliable than `gh`.

## Fetching a package from the release

Every asset is at
`https://github.com/<REPO>/releases/download/<TAG>/<filename>`, with no
login needed. From the root of this repo:

```
REPO=threedlite/scaife-local
TAG=audio-v1
PKG=hesiod_chamberlain_tts_female_lettered
BASE=https://github.com/$REPO/releases/download/$TAG

curl -fL -O "$BASE/$PKG.zip" -O "$BASE/SHA256SUMS"
grep " $PKG.zip" SHA256SUMS | shasum -a 256 -c -     # expect "<PKG>.zip: OK"

mkdir -p "data-sources/audio/$PKG"
unzip -q "$PKG.zip" -d "data-sources/audio/$PKG"
cp "audio-manifests/$PKG.package.yaml" "data-sources/audio/$PKG/package.yaml"
rm "$PKG.zip" SHA256SUMS

docker exec -u scaife scaife-viewer python manage.py ingest_audio
```

`gh release download "$TAG" --repo "$REPO" --pattern "$PKG*"` does the same
download for anyone with the CLI. Staging layout and the ingest's coverage
report are described under "Audio" in `README.md`.

## Changing a release later

- **New or corrected audio: publish a new tag** (`audio-v2`) rather than
  replacing an asset under the old one. Assets can be overwritten in place
  (`gh release upload --clobber`), but anyone who already downloaded the
  old file, or recorded its checksum, then silently disagrees with the URL.
- Adding a file that was missing to an existing release is fine:
  `gh release upload "$TAG" --repo "$REPO" <file>`. Regenerate and
  re-upload `SHA256SUMS` only if a zip changed.
- A corrected manifest needs no new release: it is an ordinary change to
  `audio-manifests/` in this repo.
- `gh release delete "$TAG" --repo "$REPO"` removes the release and its
  assets but leaves the tag; add `--cleanup-tag` to remove both.

## Still open

- Merge `feature/audio` into `main`. The release notes send readers to
  `AUDIO-RELEASE.md` and `audio-manifests/`, which the default branch does
  not have until then.
- Optional: an opt-in step in `scripts/fetch-data.sh` (for example
  `SCAIFE_AUDIO_PACKAGES="hesiod hymns"`) that runs the fetch for each
  named package. It should stay opt-in: the default bring-up is about 3 GB
  and the full audio set would more than double it.
