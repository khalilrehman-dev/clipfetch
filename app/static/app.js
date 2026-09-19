const SNIPIVO_FRONTEND_VERSION = '1.4.0';
const form = document.getElementById('downloadForm');
const input = document.getElementById('videoUrl');
const fetchBtn = document.getElementById('fetchBtn');
const pasteBtn = document.getElementById('pasteBtn');
const message = document.getElementById('message');
const result = document.getElementById('result');
const thumb = document.getElementById('thumb');
const title = document.getElementById('title');
const author = document.getElementById('author');
const duration = document.getElementById('duration');
const platformBadge = document.getElementById('platformBadge');
const cleanBadge = document.getElementById('cleanBadge');
const cleanBtn = document.getElementById('cleanBtn');
const bestBtn = document.getElementById('bestBtn');
const audioBtn = document.getElementById('audioBtn');
const cleanQuality = document.getElementById('cleanQuality');

let currentUrl = '';
let currentPlatform = 'tiktok';
let cleanAvailable = false;
let downloadBusy = false;
let prepareElapsedTimer = null;
let prepareAbortController = null;

const actionButtons = [cleanBtn, bestBtn, audioBtn];
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

function platformLabel() {
  return currentPlatform === 'instagram' ? 'Instagram' : 'TikTok';
}

function actionCopy(kind) {
  if (kind === 'video-clean') {
    return {
      title: 'Without watermark',
      subtitle: cleanAvailable
        ? (cleanQuality.textContent || 'Best clean stream')
        : 'Clean stream unavailable'
    };
  }
  if (kind === 'video-best') {
    return currentPlatform === 'instagram'
      ? { title: 'Download MP4', subtitle: 'Best available Instagram video' }
      : { title: 'Best available MP4', subtitle: 'Best video option' };
  }
  if (kind === 'audio-mp3') {
    return { title: 'Download MP3', subtitle: '192 kbps audio' };
  }
  return { title: 'Download', subtitle: '' };
}

function formatDuration(seconds) {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function showMessage(text, ok = false) {
  message.textContent = text || '';
  message.classList.toggle('ok', ok);
}

function setLoading(loading) {
  fetchBtn.disabled = loading;
  fetchBtn.querySelector('span').textContent = loading ? 'Checking link…' : 'Get download links';
}

function trackEvent(name, params = {}) {
  if (typeof window.gtag === 'function') {
    window.gtag('event', name, params);
  }
}

function clearPrepareTimer() {
  if (prepareElapsedTimer) {
    window.clearInterval(prepareElapsedTimer);
    prepareElapsedTimer = null;
  }
}

function restoreActionButton(button, kind) {
  button.classList.remove('preparing', 'ready');
  button.removeAttribute('aria-busy');
  delete button.dataset.downloadUrl;

  const copy = actionCopy(kind);
  const strong = button.querySelector('strong');
  const small = button.querySelector('small');
  if (strong) strong.textContent = copy.title;
  if (small) small.textContent = copy.subtitle;
}

function resetActionButtons() {
  restoreActionButton(cleanBtn, 'video-clean');
  restoreActionButton(bestBtn, 'video-best');
  restoreActionButton(audioBtn, 'audio-mp3');

  cleanBtn.disabled = currentPlatform !== 'tiktok' || !cleanAvailable;
  bestBtn.disabled = false;
  audioBtn.disabled = false;
}

function setDownloadBusy(active, activeButton = null) {
  downloadBusy = active;
  clearPrepareTimer();

  if (!active) {
    resetActionButtons();
    return;
  }

  actionButtons.forEach((button) => {
    button.disabled = true;
  });

  if (!activeButton) return;

  activeButton.classList.add('preparing');
  activeButton.setAttribute('aria-busy', 'true');
  const strong = activeButton.querySelector('strong');
  const small = activeButton.querySelector('small');
  if (strong) strong.textContent = 'Preparing download…';

  let elapsed = 0;
  if (small) small.textContent = 'Connecting securely… 0s';
  prepareElapsedTimer = window.setInterval(() => {
    elapsed += 1;
    if (small) {
      small.textContent = elapsed < 8
        ? `Connecting securely… ${elapsed}s`
        : `Still preparing… ${elapsed}s — please keep this page open`;
    }
  }, 1000);

  showMessage(`Preparing your ${platformLabel()} file. Keep this page open — Snipivo will tell you when it is ready.`, true);
}

function handoffPreparedDownload(button, kind, downloadUrl = null) {
  const resolvedUrl = downloadUrl || button.dataset.downloadUrl;
  if (!resolvedUrl) return false;

  trackEvent('download_handoff', {
    format: kind,
    platform: currentPlatform,
    ios: isIOS ? 'yes' : 'no',
    automatic: 'yes'
  });

  // Use a same-origin top-level navigation so the browser can hand the
  // prepared attachment directly to its download manager. Unlike popup
  // windows, location navigation does not require a second user click.
  window.location.assign(resolvedUrl);
  showMessage('Download started. Check your browser downloads or Files app if needed.', true);

  window.setTimeout(() => {
    resetActionButtons();
  }, 2500);
  return true;
}

async function buildDownload(kind, button) {
  if (!currentUrl) return;
  if (currentPlatform === 'instagram' && kind === 'video-clean') return;

  if (downloadBusy) return;

  let eventName = 'download_started';
  if (currentPlatform === 'instagram') {
    eventName = {
      'video-best': 'download_instagram_mp4',
      'audio-mp3': 'download_instagram_mp3'
    }[kind] || eventName;
  } else {
    eventName = {
      'video-clean': 'download_clean',
      'video-best': 'download_mp4',
      'audio-mp3': 'download_mp3'
    }[kind] || eventName;
  }

  trackEvent(eventName, { format: kind, platform: currentPlatform });
  setDownloadBusy(true, button);

  prepareAbortController = new AbortController();
  const timeout = window.setTimeout(() => prepareAbortController.abort(), 90000);

  try {
    const response = await fetch('/api/prepare-download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentUrl, kind }),
      signal: prepareAbortController.signal
    });

    let data = {};
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      throw new Error(data.detail || 'The download could not be prepared. Please try again.');
    }

    downloadBusy = false;
    clearPrepareTimer();
    showMessage(`File ready. Starting your ${platformLabel()} download…`, true);
    handoffPreparedDownload(button, kind, data.download_url);
  } catch (error) {
    downloadBusy = false;
    clearPrepareTimer();
    resetActionButtons();
    const timedOut = error && error.name === 'AbortError';
    showMessage(
      timedOut
        ? 'This download is taking too long. Please try once more or choose another format.'
        : (error.message || 'The download could not be prepared.'),
      false
    );
    trackEvent('download_failed', {
      stage: 'prepare',
      platform: currentPlatform,
      format: kind,
      reason: timedOut ? 'timeout' : 'prepare_error'
    });
  } finally {
    window.clearTimeout(timeout);
    prepareAbortController = null;
  }
}

pasteBtn.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    input.value = text;
    input.focus();
  } catch {
    input.focus();
    showMessage('Clipboard access was blocked by your browser. Paste the link manually.');
  }
});

cleanBtn.addEventListener('click', () => buildDownload('video-clean', cleanBtn));
bestBtn.addEventListener('click', () => buildDownload('video-best', bestBtn));
audioBtn.addEventListener('click', () => buildDownload('audio-mp3', audioBtn));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = input.value.trim();
  result.classList.add('hidden');
  showMessage('');

  if (!url) {
    showMessage('Paste a TikTok or Instagram video link first.');
    return;
  }

  if (prepareAbortController) {
    prepareAbortController.abort();
    prepareAbortController = null;
  }
  downloadBusy = false;
  clearPrepareTimer();
  resetActionButtons();

  setLoading(true);
  try {
    const response = await fetch('/api/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not resolve this video.');

    currentUrl = url;
    currentPlatform = data.platform === 'instagram' ? 'instagram' : 'tiktok';

    thumb.src = data.thumbnail || '';
    thumb.style.visibility = data.thumbnail ? 'visible' : 'hidden';
    thumb.alt = `${platformLabel()} video thumbnail`;
    title.textContent = data.title || `${platformLabel()} video`;
    author.textContent = data.author
      ? `@${String(data.author).replace(/^@/, '')}`
      : `${platformLabel()} creator`;
    duration.textContent = formatDuration(data.duration);
    duration.style.display = data.duration ? 'block' : 'none';

    platformBadge.textContent = platformLabel();
    platformBadge.classList.toggle('instagram', currentPlatform === 'instagram');

    cleanAvailable = currentPlatform === 'tiktok' && Boolean(data.clean_available);
    cleanBtn.classList.toggle('hidden', currentPlatform === 'instagram');
    cleanBadge.classList.toggle('hidden', currentPlatform === 'instagram');
    cleanBtn.disabled = !cleanAvailable;
    cleanBadge.classList.toggle('off', !cleanAvailable);
    cleanBadge.textContent = cleanAvailable ? 'Clean stream found' : 'Clean stream unavailable';
    cleanQuality.textContent = cleanAvailable
      ? (data.clean_resolution ? `${data.clean_resolution} · best clean stream` : 'Best clean stream')
      : 'TikTok only exposed a branded stream';

    restoreActionButton(bestBtn, 'video-best');
    restoreActionButton(audioBtn, 'audio-mp3');

    result.classList.remove('hidden');
    showMessage(`${platformLabel()} video ready. Choose a download format.`, true);

    trackEvent('video_resolved', {
      platform: currentPlatform,
      clean_available: cleanAvailable ? 'yes' : 'no'
    });
    if (currentPlatform === 'instagram') {
      trackEvent('instagram_resolved', { content_type: 'video' });
    }

    result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    trackEvent('download_failed', {
      stage: 'resolve',
      reason: 'resolve_error'
    });
    showMessage(error.message || 'Something went wrong.');
  } finally {
    setLoading(false);
  }
});
