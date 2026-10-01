/*
Line-level audio state. One passage's clips at a time, keyed by the same
`reference` string the rendered <text-part> elements carry, so TextPart can
look itself up. Playback order for "continuous" mode comes from the DOM
(document order of the rendered leaf text-parts), not from a key sort:
Apollonius renders 2.382a before 2.382, and the audio must follow the text.

The <audio> element lives in WidgetAudio.vue; this module only records what
should be playing. `continuous` is persisted (see config.js).
*/
import api from '../../api';
import constants from '../../constants';

const state = {
  passageUrn: null,
  packageInfo: null,
  clips: {}, // reference -> { ref, url }
  playingRef: null,
  continuous: false,
  status: '',
};

const getters = {
  hasClips: s => Object.keys(s.clips).length > 0,
};

const mutations = {
  [constants.SET_AUDIO_CLIPS](s, { passageUrn, packageInfo, clips }) {
    s.passageUrn = passageUrn;
    s.packageInfo = packageInfo;
    const byRef = {};
    (clips || []).forEach((c) => { byRef[c.ref] = c; });
    s.clips = byRef;
  },
  [constants.SET_AUDIO_PLAYING](s, { ref }) {
    s.playingRef = ref;
  },
  [constants.SET_AUDIO_CONTINUOUS](s, { continuous }) {
    s.continuous = continuous;
  },
  [constants.SET_AUDIO_STATUS](s, { status }) {
    s.status = status;
  },
};

// Order of the left passage's rendered lines that have a clip. TextPart
// stamps `data-audio-ref` on the lines it decorates, so this is exactly the
// set of visible play buttons, in document order.
function renderedOrder(doc) {
  const root = doc || (typeof document !== 'undefined' ? document : null);
  if (!root) {
    return [];
  }
  return Array.from(root.querySelectorAll('.textpart[data-audio-ref]'))
    .map(el => el.getAttribute('data-audio-ref'));
}

const actions = {
  [constants.AUDIO_LOAD]({ commit }, { urn }) {
    const passageUrn = urn ? urn.toString() : null;
    commit(constants.SET_AUDIO_PLAYING, { ref: null });
    commit(constants.SET_AUDIO_STATUS, { status: '' });
    if (!passageUrn) {
      commit(constants.SET_AUDIO_CLIPS, { passageUrn: null, packageInfo: null, clips: [] });
      return Promise.resolve();
    }
    return api.getAudio(passageUrn, (data) => {
      commit(constants.SET_AUDIO_CLIPS, {
        passageUrn,
        packageInfo: data.package,
        clips: data.clips,
      });
    }).catch(() => {
      commit(constants.SET_AUDIO_CLIPS, { passageUrn, packageInfo: null, clips: [] });
    });
  },
  [constants.AUDIO_PLAY]({ commit, state: s }, { ref }) {
    if (!s.clips[ref]) {
      return;
    }
    commit(constants.SET_AUDIO_PLAYING, { ref });
    commit(constants.SET_AUDIO_STATUS, { status: `Playing line ${ref}` });
  },
  [constants.AUDIO_STOP]({ commit, state: s }) {
    if (s.playingRef !== null) {
      commit(constants.SET_AUDIO_PLAYING, { ref: null });
      commit(constants.SET_AUDIO_STATUS, { status: 'Stopped' });
    }
  },
  // Called by the widget on the <audio> element's `ended` event.
  [constants.AUDIO_ENDED]({ commit, dispatch, state: s }, { doc } = {}) {
    const current = s.playingRef;
    if (current === null) {
      return;
    }
    if (!s.continuous) {
      commit(constants.SET_AUDIO_PLAYING, { ref: null });
      commit(constants.SET_AUDIO_STATUS, { status: 'Stopped' });
      return;
    }
    const order = renderedOrder(doc);
    const idx = order.indexOf(current);
    const next = idx >= 0 ? order.slice(idx + 1).find(r => s.clips[r]) : undefined;
    if (next === undefined) {
      commit(constants.SET_AUDIO_PLAYING, { ref: null });
      commit(constants.SET_AUDIO_STATUS, {
        status: 'End of page audio. Use the next-page arrow to continue.',
      });
      return;
    }
    dispatch(constants.AUDIO_PLAY, { ref: next });
  },
  [constants.AUDIO_TOGGLE_CONTINUOUS]({ commit, state: s }) {
    commit(constants.SET_AUDIO_CONTINUOUS, { continuous: !s.continuous });
  },
};

export default {
  namespaced: true,
  state,
  getters,
  mutations,
  actions,
};

export { renderedOrder };
