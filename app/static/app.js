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
let downloadUnlockTimer = null;

const actionButtons = [cleanBtn, bestBtn, audioBtn];

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

function getDownloadFrame() {
  let frame = document.getElementById('downloadFrame');
  if (frame) return frame;

  frame = document.createElement('iframe');
  frame.id = 'downloadFrame';
  frame.name = 'downloadFrame';
  frame.title = 'Download transfer';
  frame.setAttribute('aria-hidden', 'true');
  frame.tabIndex = -1;
  frame.className = 'download-frame';
  document.body.appendChild(frame);
  return frame;
}

function restoreActionButton(button, kind) {
  button.classList.remove('preparing');
  button.removeAttribute('aria-busy');

  const copy = actionCopy(kind);
  const strong = button.querySelector('strong');
  const small = button.querySelector('small');
  if (strong) strong.textContent = copy.title;
  if (small) small.textContent = copy.subtitle;
}

function setDownloadBusy(active, activeButton = null, activeKind = '') {
  downloadBusy = active;

  if (downloadUnlockTimer) {
    window.clearTimeout(downloadUnlockTimer);
    downloadUnlockTimer = null;
  }

  if (active) {
    actionButtons.forEach((button) => {
      button.disabled = true;
    });

    if (activeButton) {
      activeButton.classList.add('preparing');
      activeButton.setAttribute('aria-busy', 'true');
      const strong = activeButton.querySelector('strong');
      const small = activeButton.querySelector('small');
      if (strong) strong.textContent = 'Preparing download…';
      if (small) small.textContent = 'Please wait — this can take a few seconds';
    }

    showMessage(`Preparing your ${platformLabel()} download… Please wait and avoid clicking again.`, true);

    // Attachment responses do not reliably fire a browser event when the
    // Save/Download handoff begins, so use a conservative unlock fallback.
    downloadUnlockTimer = window.setTimeout(() => {
      setDownloadBusy(false, activeButton, activeKind);
    }, 20000);
    return;
  }

  restoreActionButton(cleanBtn, 'video-clean');
  restoreActionButton(bestBtn, 'video-best');
  restoreActionButton(audioBtn, 'audio-mp3');

  cleanBtn.disabled = currentPlatform !== 'tiktok' || !cleanAvailable;
  bestBtn.disabled = false;
  audioBtn.disabled = false;
  showMessage('Download started. You can choose another format.', true);
}

function startDownload(name, params, destination, button, kind) {
  const begin = () => {
    const frame = getDownloadFrame();
    frame.src = destination;
  };

  setDownloadBusy(true, button, kind);

  if (typeof window.gtag === 'function') {
    let started = false;
    const go = () => {
      if (started) return;
      started = true;
      begin();
    };

    window.gtag('event', name, {
      ...params,
      event_callback: go,
      event_timeout: 700
    });
    window.setTimeout(go, 750);
  } else {
    begin();
  }
}

function buildDownload(kind, button) {
  if (!currentUrl || downloadBusy) return;
  if (currentPlatform === 'instagram' && kind === 'video-clean') return;

  const params = new URLSearchParams({ url: currentUrl, kind });
  const destination = `/api/download?${params.toString()}`;

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

  startDownload(
    eventName,
    { format: kind, platform: currentPlatform },
    destination,
    button,
    kind
  );
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
