/* global describe, expect, it, beforeEach, jest */
import { shallowMount, createLocalVue } from '@vue/test-utils';
import Vuex from 'vuex';

import WidgetAudio from '../static/src/js/reader/widgets/WidgetAudio.vue';
import audioModule, { renderedOrder } from '../static/src/js/vuex/audio';
import constants from '../static/src/js/constants';

const localVue = createLocalVue();
localVue.use(Vuex);

function makeStore(overrides = {}) {
  const state = {
    passageUrn: null,
    packageInfo: null,
    clips: {},
    playingRef: null,
    continuous: false,
    status: '',
    ...overrides,
  };
  return new Vuex.Store({
    modules: {
      audio: { ...audioModule, state },
    },
  });
}

const CLIPS = {
  1: { ref: '1', url: '/library/audio/clip/1/' },
  2: { ref: '2', url: '/library/audio/clip/2/' },
  '2a': { ref: '2a', url: '/library/audio/clip/3/' },
  3: { ref: '3', url: '/library/audio/clip/4/' },
};

function pageWith(refs) {
  document.body.innerHTML = refs
    .map(r => `<div class="textpart leaf" data-audio-ref="${r}"></div>`)
    .join('');
  return document;
}

describe('WidgetAudio', () => {
  it('renders nothing but the player when there is no package', () => {
    const wrapper = shallowMount(WidgetAudio, { localVue, store: makeStore() });
    expect(wrapper.find('audio').exists()).toBe(true);
    expect(wrapper.find('base-widget-stub').exists()).toBe(false);
  });

  it('shows the package, licence and attribution when present', () => {
    const store = makeStore({
      packageInfo: { label: 'Hesiod TTS', license: 'CC BY-SA 4.0', attribution: 'credit' },
      clips: CLIPS,
    });
    const wrapper = shallowMount(WidgetAudio, { localVue, store, stubs: { 'base-widget': { template: '<div><slot name="body"/></div>' } } });
    expect(wrapper.text()).toContain('Hesiod TTS');
    expect(wrapper.text()).toContain('CC BY-SA 4.0');
    expect(wrapper.text()).toContain('credit');
    expect(wrapper.text()).toContain('Stopped');
  });

  it('checkbox toggles continuous', () => {
    const store = makeStore({ packageInfo: { label: 'x', license: 'y' } });
    const wrapper = shallowMount(WidgetAudio, { localVue, store, stubs: { 'base-widget': { template: '<div><slot name="body"/></div>' } } });
    wrapper.find('input[type=checkbox]').trigger('change');
    expect(store.state.audio.continuous).toBe(true);
    wrapper.find('input[type=checkbox]').trigger('change');
    expect(store.state.audio.continuous).toBe(false);
  });
});

describe('audio store', () => {
  let store;
  beforeEach(() => {
    store = makeStore({ clips: CLIPS, packageInfo: { label: 'x', license: 'y' } });
  });

  it('PLAY sets playingRef and status only for a known ref', () => {
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '2a' });
    expect(store.state.audio.playingRef).toBe('2a');
    expect(store.state.audio.status).toBe('Playing line 2a');
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '999' });
    expect(store.state.audio.playingRef).toBe('2a');
  });

  it('ENDED with continuous off stops', () => {
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '1' });
    store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc: pageWith(['1', '2']) });
    expect(store.state.audio.playingRef).toBe(null);
    expect(store.state.audio.status).toBe('Stopped');
  });

  it('ENDED with continuous on follows document order, not key order', () => {
    store.commit(`audio/${constants.SET_AUDIO_CONTINUOUS}`, { continuous: true });
    // Apollonius-style: 2a is rendered before 2.
    const doc = pageWith(['1', '2a', '2', '3']);
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '1' });
    store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc });
    expect(store.state.audio.playingRef).toBe('2a');
    store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc });
    expect(store.state.audio.playingRef).toBe('2');
  });

  it('ENDED skips rendered lines that have no clip and stops at the page end', () => {
    store.commit(`audio/${constants.SET_AUDIO_CONTINUOUS}`, { continuous: true });
    const doc = pageWith(['2', 'nope', '3']);
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '2' });
    store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc });
    expect(store.state.audio.playingRef).toBe('3');
    store.dispatch(`audio/${constants.AUDIO_ENDED}`, { doc });
    expect(store.state.audio.playingRef).toBe(null);
    expect(store.state.audio.status).toMatch(/End of page audio/);
    expect(store.state.audio.continuous).toBe(true);
  });

  it('renderedOrder reads data-audio-ref in DOM order', () => {
    expect(renderedOrder(pageWith(['5', '5a', '6']))).toEqual(['5', '5a', '6']);
  });

  it('LOAD stores clips keyed by ref and clears playback', () => {
    const api = require('../static/src/js/api').default; // eslint-disable-line global-require
    api.getAudio = jest.fn((urn, cb) => {
      cb({ package: { label: 'p', license: 'l' }, clips: [{ ref: '7', url: '/u' }] });
      return Promise.resolve();
    });
    store.dispatch(`audio/${constants.AUDIO_PLAY}`, { ref: '1' });
    return store.dispatch(`audio/${constants.AUDIO_LOAD}`, { urn: 'urn:x:1-30' }).then(() => {
      expect(store.state.audio.playingRef).toBe(null);
      expect(store.state.audio.clips).toEqual({ 7: { ref: '7', url: '/u' } });
      expect(store.state.audio.packageInfo.label).toBe('p');
      expect(api.getAudio).toHaveBeenCalledWith('urn:x:1-30', expect.any(Function));
    });
  });
});
