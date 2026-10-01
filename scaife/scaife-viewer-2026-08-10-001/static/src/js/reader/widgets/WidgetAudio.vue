<template>
  <div class="audio-widget-root">
    <audio
      ref="player"
      preload="none"
      @ended="onEnded"
      @error="onError"
    />
    <base-widget class="audio" v-if="packageInfo">
      <span slot="header">Audio</span>
      <div slot="body">
        <div class="form-check">
          <input
            id="audio-continuous"
            class="form-check-input"
            type="checkbox"
            :checked="continuous"
            @change="toggleContinuous"
          >
          <label class="form-check-label" for="audio-continuous">Continuous audio</label>
        </div>
        <div class="audio-status">{{ status || 'Stopped' }}</div>
        <div class="audio-package">
          <div class="audio-package-label">{{ packageInfo.label }}</div>
          <div class="audio-package-license">{{ packageInfo.license }}</div>
          <pre class="audio-attribution" v-if="packageInfo.attribution">{{ packageInfo.attribution }}</pre>
        </div>
      </div>
    </base-widget>
  </div>
</template>

<script>
/*
Owns the single <audio> element. The store decides *what* is playing
(audio.playingRef); this component turns that into play()/pause() calls and
reports `ended` back so continuous mode can advance to the next line. The
element sits outside <base-widget> so collapsing the widget does not
destroy it mid-clip.
*/
import constants from '../../constants';

export default {
  name: 'widget-audio',
  computed: {
    packageInfo() {
      return this.$store.state.audio.packageInfo;
    },
    clips() {
      return this.$store.state.audio.clips;
    },
    playingRef() {
      return this.$store.state.audio.playingRef;
    },
    continuous() {
      return this.$store.state.audio.continuous;
    },
    status() {
      return this.$store.state.audio.status;
    },
  },
  watch: {
    playingRef(ref) {
      const { player } = this.$refs;
      if (!player) {
        return;
      }
      if (ref === null) {
        player.pause();
        player.removeAttribute('src');
        return;
      }
      const clip = this.clips[ref];
      if (!clip) {
        return;
      }
      player.src = clip.url;
      const p = player.play();
      if (p && typeof p.catch === 'function') {
        p.catch(() => this.onError());
      }
    },
  },
  beforeDestroy() {
    const { player } = this.$refs;
    if (player) {
      player.pause();
    }
  },
  methods: {
    toggleContinuous() {
      this.$store.dispatch(`audio/${constants.AUDIO_TOGGLE_CONTINUOUS}`);
    },
    onEnded() {
      this.$store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc: document });
    },
    onError() {
      // Mirrors Android: in continuous mode an error skips ahead; otherwise stop.
      if (this.continuous) {
        this.$store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc: document });
      } else {
        this.$store.dispatch(`audio/${constants.AUDIO_STOP}`);
      }
    },
  },
};
</script>

<style>
.audio-widget-root audio {
  display: none;
}
.audio .audio-status {
  margin: 0.5rem 0;
  font-size: 0.9rem;
}
.audio .audio-package {
  margin-top: 0.75rem;
  font-size: 0.8rem;
  color: #6c757d;
}
.audio .audio-package-label {
  font-weight: bold;
}
.audio .audio-attribution {
  margin-top: 0.5rem;
  max-height: 14rem;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 0.75rem;
  color: #6c757d;
}
</style>
