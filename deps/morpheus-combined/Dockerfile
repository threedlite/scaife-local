# Multi-stage build: Perseids Morpheus (C, MPL-2.0) + morpheus-perseids-api
# (Ruby Sinatra wrapper, MIT). Compiles natively for the host arch.
#
# Expects the docker build context to be the repo's `deps/` directory
# (that's the ${SCAIFE_REPO_ROOT}/deps path exported by bootstrap.sh),
# so both `morpheus-perseids/` and `morpheus-perseids-api/` are visible.
FROM ubuntu:22.04 AS morpheus-build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -qq -y build-essential flex
COPY morpheus-perseids /morpheus
WORKDIR /morpheus
RUN cd src/ && make clean && CFLAGS='-std=gnu89 -fcommon' make && make install

FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends \
    ruby ruby-dev libxml2 libxml2-dev libxslt1-dev build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Bring the built Morpheus binary + stemlib data in
COPY --from=morpheus-build /morpheus/bin /morpheus/bin
COPY --from=morpheus-build /morpheus/stemlib /morpheus/stemlib

# Ruby API
COPY morpheus-perseids-api /app
WORKDIR /app
ENV RACK_ENV=production \
    BUNDLE_SILENCE_ROOT_WARNING=1 \
    REDIS_ENABLED=false \
    MORPHLIB=/morpheus/stemlib \
    EXECUTABLE=/morpheus/bin/morpheus \
    PORT=1500
RUN gem install bundler && bundle install --without development test

EXPOSE 1500
CMD ["bundle", "exec", "ruby", "app.rb"]
