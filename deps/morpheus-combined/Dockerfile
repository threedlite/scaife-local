# Multi-stage build: Perseids Morpheus (C, MPL-2.0) + morpheus-perseids-api
# (Ruby Sinatra wrapper, MIT). Compiles natively for the host arch.
#
# Expects the docker build context to be the repo's `deps/` directory
# (that's the ${SCAIFE_REPO_ROOT}/deps path exported by bootstrap.sh),
# so both `morpheus-perseids/` and `morpheus-perseids-api/` are visible.
#
# Neither source repository is tracked in this repo — both are fetched by
# scripts/fetch-data.sh and gitignored — so this file is the only place
# their build can be pinned or patched. Anything that would normally be a
# commit to the API repo (a gem bump, a version pin) has to happen here,
# against the working tree, at build time.
#
# Behaviour is covered by sv_pdl/tests/test_morpheus.py, which compares
# live analyses against golden/morpheus.json at three layers (RDF/JSON,
# nokogiri's XML, and the Django view). Run it after changing anything
# below:
#
#     bash scripts/run-tests.sh --integration
#     bash scripts/run-morpheus-tests.sh      # upstream's own rspec suite

# Declared before the first FROM so it is a *global* build arg and can be
# interpolated into the `FROM ruby:...` lines below. An ARG written between
# stages belongs to the preceding stage instead, and would expand to an
# empty string there.
ARG RUBY_VERSION=3.4.10

# --------------------------------------------------------------------------
# The C engine. Deliberately still built on ubuntu:22.04 even though the
# runtime has moved to Debian bookworm: pinning the compiler and libc that
# produced today's known-good analyses keeps the Ruby upgrade a change of
# exactly one variable. The binary links against libc only (verified with
# ldd: linux-vdso, libc.so.6, ld-linux), and it was built against glibc
# 2.35, so it runs unchanged on bookworm's 2.36.
# --------------------------------------------------------------------------
FROM ubuntu:22.04 AS morpheus-build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -qq -y build-essential flex
COPY morpheus-perseids /morpheus
WORKDIR /morpheus
RUN cd src/ && make clean && CFLAGS='-std=gnu89 -fcommon' make && make install

# --------------------------------------------------------------------------
# Gem build.
#
# Ruby comes from the official image rather than from apt. Ubuntu 22.04
# ships Ruby 3.0.2, which reached end-of-life on 2024-03-31 and therefore
# receives no security fixes at all; the distro package cannot be moved
# forward without moving the whole base image.
#
# 3.4 is the ceiling here, not a conservative choice: the API's Gemfile
# declares `ruby '~> 3.0'`, which permits >= 3.0 and < 4.0, so the 4.x
# images are excluded until upstream widens that constraint.
#
# This stage exists so the compiler never reaches the runtime image. puma,
# nio4r, ffi and racc all build native extensions, which needs
# build-essential — and build-essential drags in perl. On bookworm that is
# 20 unfixable CRITICAL advisories (perl x4, libxml2, linux-libc-dev,
# zlib1g) for packages the running service never calls. The production
# stage below copies out only the built bundle.
# --------------------------------------------------------------------------
FROM ruby:${RUBY_VERSION}-slim-bookworm AS gem-builder
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends \
    libxml2-dev libxslt1-dev build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY morpheus-perseids-api /app
WORKDIR /app

# nokogiri is pinned rather than left to float. The Gemfile requires it
# unversioned, and the committed Gemfile.lock resolved to 1.14.3, which is
# affected by GHSA-353f-x4gh-cqq8 (critical) in the libxml2 it vendors;
# the fix landed in 1.18.9.
#
# The pin is applied by rewriting the requirement in the Gemfile, because
# there is no fork of the API repo to commit it to. Editing the Gemfile
# invalidates the lock for nokogiri alone — bundler's resolution is
# conservative, so every other gem stays at its locked version and the
# upgrade surface stays small. The `grep` is a guard: if upstream ever
# reformats that line, the sed silently matches nothing, and this build
# must fail loudly rather than quietly shipping 1.14.3 again.
#
# nokogiri regenerates the RDF/XML response (lib/parser.rb), so the
# byte-for-byte XML assertions in test_morpheus.py are what actually
# verify this bump. It resolves to a precompiled platform gem
# (aarch64-linux-gnu / x86_64-linux-gnu) that vendors its own libxml2, so
# the libxml2-dev above is only a fallback for the source gem.
ARG NOKOGIRI_VERSION=1.19.4
RUN sed -i "s/^gem 'nokogiri'.*/gem 'nokogiri', '${NOKOGIRI_VERSION}'/" Gemfile \
 && grep -q "gem 'nokogiri', '${NOKOGIRI_VERSION}'" Gemfile \
 && gem install bundler

# `bundle install --without` is deprecated in bundler 2.x in favour of
# configuration, which also persists into `bundle exec` at runtime. The
# config lands in /app/.bundle, so it travels with the COPY below.
RUN bundle config set --local without 'development test' \
 && bundle install

# --------------------------------------------------------------------------
# Test image: upstream's own rspec suite (spec/), which needs the
# development and test groups. Never deployed, so it keeps the toolchain.
# Built and run by scripts/run-morpheus-tests.sh.
# --------------------------------------------------------------------------
FROM gem-builder AS morpheus-test
ENV RACK_ENV=test \
    MORPHLIB=/morpheus/stemlib \
    EXECUTABLE=/morpheus/bin/morpheus
COPY --from=morpheus-build /morpheus/bin /morpheus/bin
COPY --from=morpheus-build /morpheus/stemlib /morpheus/stemlib
RUN bundle config unset --local without \
 && bundle install
CMD ["bundle", "exec", "rspec"]

# --------------------------------------------------------------------------
# Production image. Last stage, so it is what `docker compose build`
# produces when no --target is given.
#
# Starts from a clean Ruby image: no compiler, no perl, no libxml2-dev.
# Only the built bundle, the app, and the Morpheus binary are carried over.
# --------------------------------------------------------------------------
FROM ruby:${RUBY_VERSION}-slim-bookworm AS morpheus-production
ENV LANG=C.UTF-8 \
    RACK_ENV=production \
    BUNDLE_SILENCE_ROOT_WARNING=1 \
    REDIS_ENABLED=false \
    MORPHLIB=/morpheus/stemlib \
    EXECUTABLE=/morpheus/bin/morpheus \
    PORT=1500

COPY --from=morpheus-build /morpheus/bin /morpheus/bin
COPY --from=morpheus-build /morpheus/stemlib /morpheus/stemlib

# /app carries the patched Gemfile, its lock, and .bundle/config; the
# bundle carries the gems themselves, native extensions included. Both
# stages share the same base image and architecture, so the compiled
# extensions load unchanged.
COPY --from=gem-builder /app /app
COPY --from=gem-builder /usr/local/bundle /usr/local/bundle
WORKDIR /app

EXPOSE 1500
CMD ["bundle", "exec", "ruby", "app.rb"]
