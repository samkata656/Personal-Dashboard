"""Reads what's playing from Windows' media controls, the same info as the volume popup."""

import asyncio
import datetime
import hashlib
import threading
import time

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
except ImportError:
    SessionManager = None

READ_TIMEOUT_SECONDS = 1.5
ART_TIMEOUT_SECONDS = 1.0
MAX_ART_BYTES = 5 * 1024 * 1024
# Apps can change the song name a moment before the picture, so keep rechecking it for a while.
ART_SETTLE_SECONDS = 15

IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
}

IDLE = {"status": "idle"}

# Windows' media objects are only touched from this one background thread.
_loop = asyncio.new_event_loop()
_manager = None
_track = None
_track_started = 0.0
_art = None  # (id, image bytes, content type)


def start():
    threading.Thread(target=_loop.run_forever, daemon=True).start()


def read_music():
    """Returns what's playing right now. Raises an error if Windows can't be asked."""
    if SessionManager is None:
        raise RuntimeError("The winrt packages are not installed")
    future = asyncio.run_coroutine_threadsafe(_read(), _loop)
    try:
        return future.result(timeout=READ_TIMEOUT_SECONDS)
    except Exception:
        future.cancel()
        raise


def read_art():
    """Returns (image bytes, content type) for the current song, or None if it has no picture."""
    return _art[1:] if _art else None


def image_type(data):
    for signature, content_type in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            return content_type
    return None


def pick_session(sessions, current):
    """Prefers whatever is actually playing, then whatever Windows considers current."""
    candidates = ([current] if current else []) + list(sessions)
    for session in candidates:
        if session.get_playback_info().playback_status == PlaybackStatus.PLAYING:
            return session
    return current


def position_and_duration(timeline, playing, now):
    """Apps only report their position now and then, so add the time passed since the last report."""
    duration = (timeline.end_time - timeline.start_time).total_seconds()
    if duration <= 0:
        return None, None

    position = (timeline.position - timeline.start_time).total_seconds()
    if playing:
        elapsed = (now - timeline.last_updated_time).total_seconds()
        if 0 <= elapsed <= duration:
            position += elapsed
    return max(0.0, min(position, duration)), duration


async def _fetch_art(properties):
    if not properties.thumbnail:
        return None
    stream = await properties.thumbnail.open_read_async()
    if not 0 < stream.size <= MAX_ART_BYTES:
        return None
    buffer = Buffer(stream.size)
    result = await stream.read_async(buffer, stream.size, InputStreamOptions.READ_AHEAD)
    data = bytes(result)
    content_type = image_type(data)
    if not content_type:
        return None
    return hashlib.sha1(data).hexdigest()[:16], data, content_type


async def _update_art(track, properties):
    global _track, _track_started, _art
    if track != _track:
        _track = track
        _track_started = time.monotonic()
        _art = None
    if _art and time.monotonic() - _track_started > ART_SETTLE_SECONDS:
        return
    try:
        fresh = await asyncio.wait_for(_fetch_art(properties), ART_TIMEOUT_SECONDS)
    except Exception:
        return  # A missing picture should never take the song name down with it.
    if fresh:
        _art = fresh


async def _read():
    global _manager, _track, _art
    try:
        if _manager is None:
            _manager = await SessionManager.request_async()
        session = pick_session(_manager.get_sessions(), _manager.get_current_session())
        if session is None:
            _track, _art = None, None
            return IDLE

        status = session.get_playback_info().playback_status
        playing = status in (PlaybackStatus.PLAYING, PlaybackStatus.CHANGING)
        properties = await session.try_get_media_properties_async()
        if not properties.title or not (playing or status == PlaybackStatus.PAUSED):
            _track, _art = None, None
            return IDLE

        await _update_art((session.source_app_user_model_id, properties.title, properties.artist), properties)

        now = datetime.datetime.now(datetime.timezone.utc)
        position, duration = position_and_duration(session.get_timeline_properties(), playing, now)
        return {
            "status": "playing" if playing else "paused",
            "title": properties.title,
            "artist": properties.artist,
            "position": position,
            "duration": duration,
            "art_id": _art[0] if _art else None,
        }
    except Exception:
        _manager = None  # Ask Windows for a fresh connection next time.
        raise
