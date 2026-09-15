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
const cleanBadge = document.getElementById('cleanBadge');
const cleanBtn = document.getElementById('cleanBtn');
const bestBtn = document.getElementById('bestBtn');
const audioBtn = document.getElementById('audioBtn');
const cleanQuality = document.getElementById('cleanQuality');

let currentUrl = '';

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
  fetchBtn.querySelector('span').textContent = loading ? 'Checking video…' : 'Get download links';
}

function trackEvent(name, params = {}) {
  if (typeof window.gtag === 'function') {
    window.gtag('event', name, params);
  }
}

function trackAndNavigate(name, params, destination) {
  let navigated = false;
  const go = () => {
    if (navigated) return;
    navigated = true;
    window.location.href = destination;
  };

  if (typeof window.gtag === 'function') {
    window.gtag('event', name, {
      ...params,
      event_callback: go,
      event_timeout: 700
    });
    window.setTimeout(go, 750);
  } else {
    go();
  }
}

function buildDownload(kind) {
  if (!currentUrl) return;
  const params = new URLSearchParams({ url: currentUrl, kind });
  const destination = `/api/download?${params.toString()}`;
  const eventName = {
    'video-clean': 'download_clean',
    'video-best': 'download_mp4',
    'audio-mp3': 'download_mp3'
  }[kind] || 'download_started';

  trackAndNavigate(eventName, { format: kind }, destination);
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

cleanBtn.addEventListener('click', () => buildDownload('video-clean'));
bestBtn.addEventListener('click', () => buildDownload('video-best'));
audioBtn.addEventListener('click', () => buildDownload('audio-mp3'));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = input.value.trim();
  result.classList.add('hidden');
  showMessage('');

  if (!url) {
    showMessage('Paste a TikTok video link first.');
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
    if (!response.ok) throw new Error(data.detail || 'Could not resolve this TikTok video.');

    currentUrl = url;
    thumb.src = data.thumbnail || '';
    thumb.style.visibility = data.thumbnail ? 'visible' : 'hidden';
    title.textContent = data.title || 'TikTok video';
    author.textContent = data.author ? `@${String(data.author).replace(/^@/, '')}` : 'TikTok creator';
    duration.textContent = formatDuration(data.duration);
    duration.style.display = data.duration ? 'block' : 'none';

    cleanBtn.disabled = !data.clean_available;
    cleanBadge.classList.toggle('off', !data.clean_available);
    cleanBadge.textContent = data.clean_available ? 'Clean stream found' : 'Clean stream unavailable';
    cleanQuality.textContent = data.clean_available
      ? (data.clean_resolution ? `${data.clean_resolution} · best clean stream` : 'Best clean stream')
      : 'TikTok only exposed a branded stream';

    result.classList.remove('hidden');
    showMessage('Video ready. Choose a download format.', true);
    trackEvent('video_resolved', {
      clean_available: data.clean_available ? 'yes' : 'no'
    });
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
