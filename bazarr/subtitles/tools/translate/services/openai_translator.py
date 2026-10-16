# coding=utf-8

import json
import logging
import re

import json_tricks
import pysubs2
import requests
import srt

from app.config import settings
from app.jobs_queue import jobs_queue
from languages.get_languages import language_from_alpha2, language_from_alpha3
from radarr.history import history_log_movie
from sonarr.history import history_log
from ..core.translator_utils import add_translator_info, get_description, create_process_result

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BATCH_SIZE = 100
DEFAULT_OPENAI_TIMEOUT = 300


class OpenAITranslatorService:
    """Translate subtitles with any OpenAI-compatible chat completions endpoint.

    Works with OpenAI, OpenRouter, LiteLLM, Ollama, vLLM, LM Studio, etc.: anything that exposes
    ``POST {base_url}/chat/completions``.
    """

    def __init__(self, source_srt_file, dest_srt_file, to_lang, media_type, sonarr_series_id, sonarr_episode_id,
                 radarr_id, forced, hi, video_path, from_lang, orig_to_lang, **kwargs):
        self.source_srt_file = source_srt_file
        self.dest_srt_file = dest_srt_file
        self.to_lang = to_lang
        self.from_lang = from_lang
        self.media_type = media_type
        self.sonarr_series_id = sonarr_series_id
        self.sonarr_episode_id = sonarr_episode_id
        self.radarr_id = radarr_id
        self.video_path = video_path
        self.forced = forced
        self.hi = hi
        self.orig_to_lang = orig_to_lang

        self.job_id = None
        self.current_progress = 0
        self.target_language = None
        self.description = None
        self.model_name = None
        self.batch_size = DEFAULT_OPENAI_BATCH_SIZE
        self.session = requests.Session()

    @staticmethod
    def get_instruction(language, description):
        instruction = (
            f"You are an assistant that translates subtitles to {language}.\n"
            "You will receive a JSON array of objects with the keys 'index' and 'content'.\n"
            "'index' is the index of the subtitle dialog and 'content' is the dialog to translate.\n"
            "Reply with ONLY a JSON array of objects with the same 'index' values and the translated 'content'. "
            "Return exactly one object per input object, keep the indices unchanged, do not merge or split "
            "entries, keep line breaks and formatting tags (such as <i>) and do not add any comment or markdown.\n"
            "Translate dialogs faithfully as they are. If a line has multiple sentences, try to keep each line "
            "to about 40-50 characters."
        )
        if description:
            instruction += "\nAdditional user instruction: '" + description + "'"
        return instruction

    def _get_batch_size(self):
        try:
            return max(1, int(settings.translator.openai_batch_size))
        except (AttributeError, TypeError, ValueError):
            return DEFAULT_OPENAI_BATCH_SIZE

    def _endpoint(self):
        base_url = str(settings.translator.openai_url or '').strip().rstrip('/')
        if not base_url:
            raise ValueError('Please provide the base URL of an OpenAI-compatible API.')
        return f'{base_url}/chat/completions'

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        api_key = str(settings.translator.openai_key or '').strip()
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    @staticmethod
    def _parse_response_content(content):
        content = re.sub(r'^```(?:json)?\s*(.*?)\s*```$', r'\1', content.strip(), flags=re.DOTALL)
        return json_tricks.loads(content)

    def _request_batch(self, batch):
        payload = {
            'model': self.model_name,
            'temperature': 0.2,
            'messages': [
                {'role': 'system', 'content': self.get_instruction(self.target_language, self.description)},
                {'role': 'user', 'content': json.dumps(batch, ensure_ascii=False)},
            ],
        }
        response = self.session.post(self._endpoint(), headers=self._headers(), data=json.dumps(payload),
                                     timeout=DEFAULT_OPENAI_TIMEOUT)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        translated = self._parse_response_content(content)

        expected = {str(item['index']) for item in batch}
        returned = {str(item.get('index')) for item in translated if isinstance(item, dict)}
        if len(translated) != len(batch) or expected != returned:
            raise ValueError(f'The model returned {len(translated)} lines instead of the expected {len(batch)} '
                             f'or different indices.')
        return translated

    def _process_batch(self, batch, translated_subtitle, retry_num=3):
        try:
            translated = self._request_batch(batch)
        except Exception as e:
            # Rate limits and server errors: retry the same batch; malformed answers: split the batch in two.
            if retry_num <= 0:
                raise
            if len(batch) > 1:
                mid = len(batch) // 2
                self._process_batch(batch[:mid], translated_subtitle, retry_num - 1)
                self._process_batch(batch[mid:], translated_subtitle, retry_num - 1)
                return
            logger.debug(f'BAZARR retrying a translation request after error: {e}')
            return self._process_batch(batch, translated_subtitle, retry_num - 1)

        for line in translated:
            translated_subtitle[int(line['index'])].content = str(line['content'])

        self.current_progress += len(batch)
        jobs_queue.update_job_progress(job_id=self.job_id, progress_value=self.current_progress)

    def translate(self, job_id):
        self.job_id = job_id
        try:
            logger.info(f'BAZARR is sending subtitle file to an OpenAI-compatible API for translation '
                        f'{self.source_srt_file}')
            self.model_name = str(settings.translator.openai_model or '').strip()
            if not self.model_name:
                raise ValueError('Please provide a model name.')
            self.target_language = language_from_alpha3(self.to_lang)
            self.batch_size = self._get_batch_size()
            self.description = get_description(self.media_type, self.radarr_id, self.sonarr_series_id)

            pysubs2.load(self.source_srt_file, encoding='utf-8')  # fail early on unreadable files
            with open(self.source_srt_file, 'r', encoding='utf-8') as f:
                original_subtitle = list(srt.parse(f.read()))
            translated_subtitle = [srt.Subtitle(s.index, s.start, s.end, s.content, s.proprietary)
                                   for s in original_subtitle]

            total = len(original_subtitle)
            jobs_queue.update_job_progress(job_id=job_id, progress_max=total,
                                           progress_message=self.source_srt_file)

            for start in range(0, total, self.batch_size):
                batch = [{'index': str(i), 'content': original_subtitle[i].content}
                         for i in range(start, min(start + self.batch_size, total))]
                self._process_batch(batch, translated_subtitle)

            with open(self.dest_srt_file, 'w', encoding='utf-8') as f:
                f.write(srt.compose(translated_subtitle))

            add_translator_info(self.dest_srt_file, f'# Subtitles translated with {self.model_name} # ')
        except Exception as e:
            logger.error(f'BAZARR encountered an error translating with an OpenAI-compatible API: {e}')
            jobs_queue.update_job_progress(job_id=job_id, progress_message=f'Translation failed: {e}')
            raise

        message = (f'{language_from_alpha2(self.from_lang)} subtitles translated to '
                   f'{language_from_alpha3(self.to_lang)}.')
        result = create_process_result(message, self.video_path, self.orig_to_lang, self.forced, self.hi,
                                       self.dest_srt_file, self.media_type)
        if self.media_type == 'episode':
            history_log(action=6, sonarr_series_id=self.sonarr_series_id, sonarr_episode_id=self.sonarr_episode_id,
                        result=result)
        else:
            history_log_movie(action=6, radarr_id=self.radarr_id, result=result)

        return self.dest_srt_file
