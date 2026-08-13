<template>
  <base-widget class="token-list" v-if="enabled && show">
    <span slot="header">Token List</span>
    <div slot="body">
      <table>
        <template v-for="token in tokenList">
          <tr v-for="(analysis, idx) in token.analyses">
            <th class="text"><template v-if="idx === 0">{{ token.text }}</template></th>
            <td class="parse">{{ analysis.parse }}</td>
            <td class="text">{{ analysis.lemma }}</td>
          </tr>
        </template>
      </table>
    </div>
  </base-widget>
</template>

<script>
import URN from '../../urn';

export default {
  name: 'widget-token-list',
  computed: {
    text() {
      return this.$store.getters['reader/text'];
    },
    passage() {
      return this.$store.getters['reader/passage'];
    },
    enabled() {
      // Offline build: fetches from morph.perseus.org.
      // Disabled to keep the app runtime network-free.
      return false;
    },
  },
  data() {
    return {
      show: false,
      tokenList: [],
    };
  },
  watch: {
    passage: 'fetchTokenList',
  },
  created() {
    if (this.enabled) {
      this.fetchTokenList();
    }
  },
  methods: {
    async fetchTokenList() {
      // Offline build: never call morph.perseus.org, even via the passage
      // watcher (which fires regardless of `enabled`).
      if (!this.enabled) return;
      const server = 'https://morph.perseus.org';
      const { urn } = this.passage;
      const res = await fetch(`${server}/read/${urn}/json/`);
      if (!res.ok) {
        if (res.status === 404) {
          this.show = false;
          return;
        }
        throw new Error(res.status);
      }
      if (this.show === false) {
        this.show = true;
      }
      const data = await res.json();
      this.tokenList = data.tokens;
    },
  },
};
</script>
