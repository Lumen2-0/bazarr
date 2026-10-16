# coding=utf-8

import ast
import logging
import os
import threading
import time

from app.config import settings
from app.database import (database, get_subtitles, select, TableEpisodes, TableMovies, TableShows)
from utilities.path_mappings import path_mappings

from .main import extract_and_translate_embedded, translate_subtitles_file

# A translation takes minutes: do not queue the same one again while it may still be running.
RETRY_AFTER_SECONDS = 3600
_in_flight = {}
_lock = threading.Lock()


def _is_ai_file(path):
    return bool(path) and os.path.splitext(os.path.splitext(path)[0])[1].lower() == '.ai'


def _pick_source(subtitles, source_language):
    """Best subtitle to translate from: an external file first, otherwise an embedded text track."""
    candidates = sorted((s for s in subtitles if s['code2'] == source_language and not s['forced']),
                        key=lambda s: bool(s['hi']))
    for subtitle in candidates:
        if subtitle['path'] and not _is_ai_file(subtitle['path']):
            return subtitle['path'], None
    for subtitle in candidates:
        if not subtitle['path'] and subtitle.get('embedded_track_id') is not None:
            return None, subtitle['id']
    return None


def _claim(key):
    now = time.time()
    with _lock:
        if now - _in_flight.get(key, 0) < RETRY_AFTER_SECONDS:
            return False
        _in_flight[key] = now
        return True


def auto_translate_missing(media_type, media_id):
    """Queue a translation for each wanted language that providers could not supply.

    Called after the providers search for an episode/movie. Disabled by default
    (settings.translator.auto_translate). The video must be older than auto_translate_delay_hours so that real
    subtitles have time to be published; if one shows up later, Bazarr's normal upgrade replaces the AI one.
    """
    if not settings.translator.auto_translate:
        return

    targets_wanted = {str(x).strip() for x in settings.translator.auto_translate_languages if str(x).strip()}
    source_language = str(settings.translator.auto_translate_source).strip()
    if not targets_wanted or not source_language:
        return

    if media_type == 'episode':
        row = database.execute(
            select(TableEpisodes.missing_subtitles, TableEpisodes.path)
            .where(TableEpisodes.sonarrEpisodeId == media_id)).first()
        metadata = database.execute(
            select(TableEpisodes.path, TableEpisodes.sonarrSeriesId, TableEpisodes.season, TableEpisodes.episode,
                   TableShows.imdbId, TableShows.tvdbId)
            .join(TableShows).where(TableEpisodes.sonarrEpisodeId == media_id)).first()
        video_path = path_mappings.path_replace(row.path) if row else None
        subtitles = get_subtitles(sonarr_episode_id=media_id)
    else:
        row = database.execute(
            select(TableMovies.missing_subtitles, TableMovies.path)
            .where(TableMovies.radarrId == media_id)).first()
        metadata = database.execute(
            select(TableMovies.path, TableMovies.imdbId, TableMovies.tmdbId)
            .where(TableMovies.radarrId == media_id)).first()
        video_path = path_mappings.path_replace_movie(row.path) if row else None
        subtitles = get_subtitles(radarr_id=media_id)

    if not row or not row.missing_subtitles or not video_path or not metadata:
        return

    # only plain wanted languages ("fr"), not the ":hi" / ":forced" variants
    targets = [language for language in ast.literal_eval(row.missing_subtitles)
               if ':' not in language and language in targets_wanted and language != source_language]
    if not targets:
        return

    try:
        age_hours = (time.time() - os.path.getmtime(video_path)) / 3600
    except OSError:
        return
    if age_hours < settings.translator.auto_translate_delay_hours:
        logging.debug(f'BAZARR automatic translation postponed for {video_path}: video is {age_hours:.1f}h old')
        return

    source = _pick_source(subtitles, source_language)
    if not source:
        logging.debug(f'BAZARR automatic translation: no usable {source_language} source for {video_path}')
        return
    source_path, embedded_subtitles_id = source

    for target in targets:
        if not _claim((media_type, media_id, target)):
            continue
        logging.info(f'BAZARR no {target} subtitles found for {video_path}: translating from {source_language}')
        common = dict(video_path=video_path, from_lang=source_language, to_lang=target, forced=False, hi=False,
                      media_type=media_type,
                      sonarr_series_id=metadata.sonarrSeriesId if media_type == 'episode' else None,
                      sonarr_episode_id=media_id if media_type == 'episode' else None,
                      radarr_id=media_id if media_type == 'movie' else None,
                      metadata=metadata, original_format=False)
        try:
            if embedded_subtitles_id is not None:
                extract_and_translate_embedded(subtitles_id=embedded_subtitles_id, **common)
            else:
                translate_subtitles_file(source_srt_file=source_path, **common)
        except Exception:
            logging.exception(f'BAZARR could not queue the automatic translation for {video_path}')
