<template>
  <div class="new-alexandria-widget">
    <NewAlexandria :comments="comments" :key="passage.absolute" />
  </div>
</template>

<script>
// NOTE: (pletcher) This widget was originally provided by an external package at
// https://github.com/scaife-viewer/frontend/blob/main/packages/widget-new-alexandria/src/NewAlexandriaWidget.vue
// These packages are no longer being served correctly, so
// I'm inlining them here.
import qs from "query-string";
import { MODULE_NS } from "@scaife-viewer/store";

import NewAlexandria from "./NewAlexandria.vue";

export default {
  name: "NewAlexandriaWidget",
  scaifeConfig: {
    displayName: "New Alexandria Commentary",
  },
  components: {
    NewAlexandria,
  },
  created() {
    if (this.enabled) {
      this.fetchData();
    }
  },
  data() {
    return {
      comments: null,
    };
  },
  watch: {
    passage: "fetchData",
  },
  computed: {
    enabled() {
      // Offline build: fetches from chs-homer-proxy.herokuapp.com.
      // Disabled to keep the app runtime network-free.
      return false;
    },
    passage() {
      return this.$store.getters[`${MODULE_NS}/passage`];
    },
    endpoint() {
      // Unreachable while `enabled` is false. Kept for future local proxy.
      return "https://chs-homer-proxy.herokuapp.com/homer-chs-proxy/graphql/";
    },
    params() {
      const gqlQuery = `{
          commentsOn(urn: "${this.passage}") {
            _id
            latestRevision {
              title
              text
            }
            commenters {
              _id
              name
            }
          }
        }`;
      return this.passage ? qs.stringify({ query: gqlQuery }) : null;
    },
    url() {
      return `${this.endpoint}?${this.params}`;
    },
  },
  methods: {
    fetchData() {
      // Offline build: never call chs-homer-proxy.herokuapp.com, even via
      // the passage watcher (which fires regardless of `enabled`).
      if (!this.enabled) return;
      fetch(this.url)
        .then((response) => response.json())
        .then((data) => {
          this.comments = data.data.commentsOn;
        })
        .catch((error) => {
          // eslint-disable-next-line no-console
          console.log(error.message);
        });
    },
  },
};
</script>

<style lang="scss">
.new-alexandria-widget {
  width: 100%;
  img {
    max-width: 100%;
  }
}
</style>
