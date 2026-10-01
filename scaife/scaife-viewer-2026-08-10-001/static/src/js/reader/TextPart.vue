<template>
  <div class="textpart" :data-audio-ref="clip ? reference : null">
    <span
      v-if="clip"
      :class="['audio-toggle', { playing }]"
      :title="playing ? 'Stop' : `Play line ${n}`"
      role="button"
      @click.stop.prevent="toggleAudio"
    ><icon :name="playing ? 'stop' : 'play'" /></span>
    <router-link v-if="reference" class="a" :to="toRef(this.reference)"><div>{{ n }}</div></router-link>
    <div class="b">
      <slot></slot>
    </div>
  </div>
</template>

<script>
import ReaderNavigationMixin from '../mixins/ReaderNavigationMixin.vue';
import constants from '../constants';

export default {
  name: 'TextPart',
  mixins: [
    ReaderNavigationMixin,
  ],
  // Provided by PassageRenderText; only the left (highlighting) passage
  // gets audio controls, parallel versions do not.
  inject: {
    highlighting: { default: false },
  },
  props: {
    reference: {
      type: String,
    },
  },
  data() {
    return {
      visible: false,
    };
  },
  computed: {
    n() {
      return this.reference.split('.').pop();
    },
    clip() {
      if (!this.highlighting || !this.reference) {
        return null;
      }
      const { audio } = this.$store.state;
      return audio ? audio.clips[this.reference] || null : null;
    },
    playing() {
      return !!this.clip && this.$store.state.audio.playingRef === this.reference;
    },
  },
  methods: {
    toggleAudio() {
      if (this.playing) {
        this.$store.dispatch(`audio/${constants.AUDIO_STOP}`);
      } else {
        this.$store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: this.reference });
      }
    },
  },
};
</script>
