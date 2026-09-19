const SNIPIVO_FRONTEND_VERSION = '1.6.0';
const form = document.getElementById('downloadForm');
const input = document.getElementById('videoUrl');
const fetchBtn = document.getElementById('fetchBtn');
const pasteBtn = document.getElementById('pasteBtn');
const message = document.getElementById('message');
const result = document.getElementById('result');
const thumb = document.getElementById('thumb');
const previewFallback = document.getElementById('previewFallback');
const title = document.getElementById('title');
const author = document.getElementById('author');
const duration = document.getElementById('duration');
const previewKind = document.getElementById('previewKind');
const platformBadge = document.getElementById('platformBadge');
const mediaTypeBadge = document.getElementById('mediaTypeBadge');
const cleanBadge = document.getElementById('cleanBadge');
const cleanBtn = document.getElementById('cleanBtn');
const bestBtn = document.getElementById('bestBtn');
const audioBtn = document.getElementById('audioBtn');
const cleanQuality = document.getElementById('cleanQuality');
const bestQuality = document.getElementById('bestQuality');
const audioQuality = document.getElementById('audioQuality');
const qualityControls = document.getElementById('qualityControls');
const videoQualityGroup = document.getElementById('videoQualityGroup');
const audioQualityGroup = document.getElementById('audioQualityGroup');
const videoQualityOptions = document.getElementById('videoQualityOptions');
const audioQualityOptions = document.getElementById('audioQualityOptions');

let currentUrl = '';
let currentPlatform = 'tiktok';
let currentContentType = 'video';
let currentImageCount = 0;
let cleanAvailable = false;
let downloadBusy = false;
let prepareElapsedTimer = null;
let prepareAbortController = null;
let currentVideoQualities = [];
let currentAudioQualities = [];
let selectedVideoQuality = 'best';
let selectedAudioBitrate = 192;

const actionButtons = [cleanBtn, bestBtn, audioBtn];

function setPreviewImage(url) {
  if (!url) {
    thumb.removeAttribute('src');
    thumb.style.visibility = 'hidden';
    previewFallback.classList.remove('hidden');
    return;
  }
  previewFallback.classList.add('hidden');
  thumb.style.visibility = 'visible';
  thumb.src = url;
}

thumb.addEventListener('error', () => {
  thumb.style.visibility = 'hidden';
  previewFallback.classList.remove('hidden');
});
thumb.addEventListener('load', () => {
  previewFallback.classList.add('hidden');
  thumb.style.visibility = 'visible';
});

function platformLabel() {
  return currentPlatform === 'instagram' ? 'Instagram' : 'TikTok';
}

function primaryKind() {
  if (currentContentType === 'image') return 'image-single';
  if (currentContentType === 'carousel') return 'images-zip';
  return 'video-best';
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return '';
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 ** 2)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function findVideoQuality(value = selectedVideoQuality) {
  return currentVideoQualities.find((option) => String(option.value) === String(value)) || null;
}

function findAudioQuality(value = selectedAudioBitrate) {
  return currentAudioQualities.find((option) => Number(option.value) === Number(value)) || null;
}

function sizeSuffix(option) {
  const formatted = option && formatBytes(option.approx_bytes);
  return formatted ? ` · ~${formatted}` : '';
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
    const option = findVideoQuality();
    const quality = option ? option.label : 'Best';
    return {
      title: 'Download MP4',
      subtitle: `${quality} video${sizeSuffix(option)}`
    };
  }
  if (kind === 'audio-mp3') {
    const option = findAudioQuality();
    const label = option ? option.label : `${selectedAudioBitrate} kbps`;
    return { title: 'Download MP3', subtitle: `${label} audio${sizeSuffix(option)}` };
  }
  if (kind === 'image-single') {
    return { title: 'Download image', subtitle: 'Original available image file' };
  }
  if (kind === 'images-zip') {
    return {
      title: 'Download all images',
      subtitle: `${currentImageCount || 'All'} images in one ZIP`
    };
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

function refreshActionCopy() {
  const mappings = [
    [cleanBtn, 'video-clean'],
    [bestBtn, primaryKind()],
    [audioBtn, 'audio-mp3']
  ];
  mappings.forEach(([button, kind]) => {
    if (button.classList.contains('preparing')) return;
    const copy = actionCopy(kind);
    const strong = button.querySelector('strong');
    const small = button.querySelector('small');
    if (strong) strong.textContent = copy.title;
    if (small) small.textContent = copy.subtitle;
  });
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

function createQualityPill(option, selected, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `quality-pill${selected ? ' selected' : ''}`;
  button.dataset.value = String(option.value);
  button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  const size = formatBytes(option.approx_bytes);
  button.innerHTML = `<strong>${option.label}</strong>${size ? `<small>~${size}</small>` : ''}`;
  button.addEventListener('click', onClick);
  return button;
}

function renderQualityControls(data) {
  currentVideoQualities = Array.isArray(data.video_qualities) ? data.video_qualities : [];
  currentAudioQualities = Array.isArray(data.audio_qualities) ? data.audio_qualities : [];

  const isVideo = currentContentType === 'video';
  qualityControls.classList.toggle('hidden', !isVideo);
  videoQualityGroup.classList.toggle('hidden', !isVideo);
  audioQualityGroup.classList.toggle('hidden', !isVideo);
  videoQualityOptions.innerHTML = '';
  audioQualityOptions.innerHTML = '';

  if (!isVideo) return;

  if (!currentVideoQualities.length) {
    currentVideoQualities = [{ value: 'best', label: 'Best', approx_bytes: null }];
  }
  if (!currentAudioQualities.length) {
    currentAudioQualities = [128, 192, 320].map((value) => ({ value, label: `${value} kbps`, approx_bytes: null }));
  }

  selectedVideoQuality = currentVideoQualities.some((q) => String(q.value) === 'best')
    ? 'best'
    : String(currentVideoQualities[0].value);
  selectedAudioBitrate = currentAudioQualities.some((q) => Number(q.value) === 192)
    ? 192
    : Number(currentAudioQualities[0].value);

  currentVideoQualities.forEach((option) => {
    const pill = createQualityPill(option, String(option.value) === String(selectedVideoQuality), () => {
      if (downloadBusy) return;
      selectedVideoQuality = String(option.value);
      [...videoQualityOptions.children].forEach((node) => {
        const active = node.dataset.value === selectedVideoQuality;
        node.classList.toggle('selected', active);
        node.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      refreshActionCopy();
      trackEvent('quality_selected', {
        platform: currentPlatform,
        content_type: currentContentType,
        format_group: 'video',
        media_quality: selectedVideoQuality
      });
    });
    videoQualityOptions.appendChild(pill);
  });

  currentAudioQualities.forEach((option) => {
    const pill = createQualityPill(option, Number(option.value) === Number(selectedAudioBitrate), () => {
      if (downloadBusy) return;
      selectedAudioBitrate = Number(option.value);
      [...audioQualityOptions.children].forEach((node) => {
        const active = Number(node.dataset.value) === selectedAudioBitrate;
        node.classList.toggle('selected', active);
        node.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      refreshActionCopy();
      trackEvent('quality_selected', {
        platform: currentPlatform,
        content_type: currentContentType,
        format_group: 'audio',
        media_quality: `${selectedAudioBitrate}kbps`
      });
    });
    audioQualityOptions.appendChild(pill);
  });
}

function configureActions() {
  const isVideo = currentContentType === 'video';
  const isImageMedia = currentContentType === 'image' || currentContentType === 'carousel';

  cleanBtn.classList.toggle('hidden', !isVideo || currentPlatform === 'instagram');
  audioBtn.classList.toggle('hidden', !isVideo);
  bestBtn.classList.toggle('accent', isImageMedia);

  restoreActionButton(cleanBtn, 'video-clean');
  restoreActionButton(bestBtn, primaryKind());
  restoreActionButton(audioBtn, 'audio-mp3');

  cleanBtn.disabled = !isVideo || currentPlatform !== 'tiktok' || !cleanAvailable;
  bestBtn.disabled = false;
  audioBtn.disabled = !isVideo;
}

function resetActionButtons() {
  configureActions();
}

function setDownloadBusy(active, activeButton = null, kind = null) {
  downloadBusy = active;
  clearPrepareTimer();

  document.querySelectorAll('.quality-pill').forEach((button) => {
    button.disabled = active;
  });

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

  const selectedDescription = kind === 'video-best'
    ? (findVideoQuality()?.label || 'Best')
    : kind === 'audio-mp3'
      ? `${selectedAudioBitrate} kbps`
      : currentContentType === 'carousel'
        ? `${currentImageCount} images`
        : currentContentType === 'image' ? 'image' : 'media';

  let elapsed = 0;
  if (small) small.textContent = `${selectedDescription} · connecting… 0s`;
  prepareElapsedTimer = window.setInterval(() => {
    elapsed += 1;
    if (small) {
      small.textContent = elapsed < 8
        ? `${selectedDescription} · preparing… ${elapsed}s`
        : `${selectedDescription} · still preparing… ${elapsed}s`;
    }
  }, 1000);

  showMessage(`Preparing your ${platformLabel()} file. It will download automatically when ready.`, true);
}

function handoffPreparedDownload(button, kind, data = {}) {
  const resolvedUrl = data.download_url || button.dataset.downloadUrl;
  if (!resolvedUrl) return false;

  trackEvent('download_handoff', {
    format: kind,
    platform: currentPlatform,
    content_type: currentContentType,
    video_quality: kind === 'video-best' ? selectedVideoQuality : undefined,
    audio_bitrate: kind === 'audio-mp3' ? selectedAudioBitrate : undefined,
    automatic: 'yes'
  });

  const actualSize = formatBytes(data.size_bytes);
  window.location.assign(resolvedUrl);
  showMessage(
    actualSize
      ? `Download started · ${actualSize}. Check your browser downloads or Files app if needed.`
      : 'Download started. Check your browser downloads or Files app if needed.',
    true
  );

  window.setTimeout(() => {
    resetActionButtons();
    document.querySelectorAll('.quality-pill').forEach((qualityButton) => {
      qualityButton.disabled = false;
    });
  }, 2500);
  return true;
}

function eventNameForDownload(kind) {
  if (kind === 'image-single') {
    return currentPlatform === 'instagram' ? 'download_instagram_image' : 'download_tiktok_image';
  }
  if (kind === 'images-zip') {
    return currentPlatform === 'instagram' ? 'download_instagram_images_zip' : 'download_tiktok_images_zip';
  }
  if (currentPlatform === 'instagram') {
    return {
      'video-best': 'download_instagram_mp4',
      'audio-mp3': 'download_instagram_mp3'
    }[kind] || 'download_started';
  }
  return {
    'video-clean': 'download_clean',
    'video-best': 'download_mp4',
    'audio-mp3': 'download_mp3'
  }[kind] || 'download_started';
}

async function buildDownload(kind, button) {
  if (!currentUrl || downloadBusy) return;
  if (currentPlatform === 'instagram' && kind === 'video-clean') return;

  trackEvent(eventNameForDownload(kind), {
    format: kind,
    platform: currentPlatform,
    content_type: currentContentType,
    image_count: currentImageCount,
    video_quality: kind === 'video-best' ? selectedVideoQuality : undefined,
    audio_bitrate: kind === 'audio-mp3' ? selectedAudioBitrate : undefined
  });
  setDownloadBusy(true, button, kind);

  prepareAbortController = new AbortController();
  const timeout = window.setTimeout(() => prepareAbortController.abort(), 90000);

  try {
    const response = await fetch('/api/prepare-download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: currentUrl,
        kind,
        video_quality: selectedVideoQuality,
        audio_bitrate: selectedAudioBitrate
      }),
      signal: prepareAbortController.signal
    });

    let data = {};
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      const fallback = response.status === 429
        ? 'Snipivo is receiving too many requests right now. Please wait a moment and try again.'
        : response.status >= 500
          ? 'The server could not finish this download. Please retry in a moment.'
          : 'The download could not be prepared. Please try again.';
      throw new Error(data.detail || fallback);
    }

    downloadBusy = false;
    clearPrepareTimer();
    handoffPreparedDownload(button, kind, data);
  } catch (error) {
    downloadBusy = false;
    clearPrepareTimer();
    resetActionButtons();
    document.querySelectorAll('.quality-pill').forEach((qualityButton) => {
      qualityButton.disabled = false;
    });
    const timedOut = error && error.name === 'AbortError';
    showMessage(
      timedOut
        ? 'This download took longer than 90 seconds. Please try once more or choose a lower video quality.'
        : (error.message || 'The download could not be prepared.'),
      false
    );
    trackEvent('download_failed', {
      stage: 'prepare',
      platform: currentPlatform,
      content_type: currentContentType,
      format: kind,
      video_quality: selectedVideoQuality,
      audio_bitrate: selectedAudioBitrate,
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
bestBtn.addEventListener('click', () => buildDownload(primaryKind(), bestBtn));
audioBtn.addEventListener('click', () => buildDownload('audio-mp3', audioBtn));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = input.value.trim();
  result.classList.add('hidden');
  showMessage('');

  if (!url) {
    showMessage('Paste a TikTok or Instagram post link first.');
    return;
  }

  if (prepareAbortController) {
    prepareAbortController.abort();
    prepareAbortController = null;
  }
  downloadBusy = false;
  clearPrepareTimer();

  setLoading(true);
  try {
    const response = await fetch('/api/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    if (!response.ok) {
      const fallback = response.status === 429
        ? 'Too many requests right now. Wait a moment and try again.'
        : 'Could not resolve this post.';
      throw new Error(data.detail || fallback);
    }

    currentUrl = url;
    currentPlatform = data.platform === 'instagram' ? 'instagram' : 'tiktok';
    currentContentType = ['image', 'carousel'].includes(data.content_type) ? data.content_type : 'video';
    currentImageCount = Number(data.image_count || 0);

    setPreviewImage(data.thumbnail || '');
    thumb.alt = currentContentType === 'video'
      ? `${platformLabel()} video thumbnail`
      : `${platformLabel()} image preview`;
    title.textContent = data.title || `${platformLabel()} media`;
    author.textContent = data.author
      ? `@${String(data.author).replace(/^@/, '')}`
      : `${platformLabel()} creator`;
    duration.textContent = formatDuration(data.duration);
    duration.style.display = data.duration ? 'block' : 'none';

    platformBadge.textContent = platformLabel();
    platformBadge.classList.toggle('instagram', currentPlatform === 'instagram');

    const typeLabel = currentContentType === 'carousel'
      ? `Carousel · ${currentImageCount}`
      : currentContentType === 'image' ? 'Photo' : 'Video';
    mediaTypeBadge.textContent = typeLabel;
    previewKind.textContent = typeLabel;

    cleanAvailable = currentContentType === 'video'
      && currentPlatform === 'tiktok'
      && Boolean(data.clean_available);

    if (currentContentType === 'video') {
      cleanBadge.classList.toggle('hidden', currentPlatform === 'instagram');
      cleanBadge.classList.toggle('off', !cleanAvailable);
      cleanBadge.textContent = cleanAvailable ? 'Clean stream found' : 'Clean stream unavailable';
      cleanQuality.textContent = cleanAvailable
        ? (data.clean_resolution ? `${data.clean_resolution} · best clean stream` : 'Best clean stream')
        : 'TikTok only exposed a branded stream';
    } else {
      cleanBadge.classList.remove('hidden', 'off');
      cleanBadge.textContent = currentContentType === 'carousel'
        ? `${currentImageCount} images`
        : 'Image post';
    }

    renderQualityControls(data);
    configureActions();
    result.classList.remove('hidden');

    const mediaDescription = currentContentType === 'carousel'
      ? `${currentImageCount} images ready. Download them together as a ZIP.`
      : currentContentType === 'image'
        ? 'Image ready. Download the available original image.'
        : 'Video ready. Choose a quality and download format.';
    showMessage(`${platformLabel()} ${mediaDescription}`, true);

    trackEvent('media_resolved', {
      platform: currentPlatform,
      content_type: currentContentType,
      image_count: currentImageCount,
      clean_available: cleanAvailable ? 'yes' : 'no',
      max_height: data.max_height || 0
    });
    if (currentContentType === 'video') {
      trackEvent('video_resolved', {
        platform: currentPlatform,
        clean_available: cleanAvailable ? 'yes' : 'no',
        max_height: data.max_height || 0
      });
    } else {
      trackEvent('image_post_resolved', {
        platform: currentPlatform,
        content_type: currentContentType,
        image_count: currentImageCount
      });
    }
    if (currentPlatform === 'instagram') {
      trackEvent('instagram_resolved', { content_type: currentContentType });
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
