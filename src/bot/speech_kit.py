"""Yandex SpeechKit client for voice-to-text conversion."""

import logging
import requests
import json

logger = logging.getLogger(__name__)

class YandexSpeechKit:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

    def speech_to_text(self, voice_content: bytes) -> str | None:
        """
        Convert voice content (ogg) to text using Yandex SpeechKit.
        """
        headers = {
            'Authorization': f'Api-Key {self.api_key}',
        }
        
        params = {
            'lang': 'ru-RU',
            'topic': 'general',
            'profanityFilter': 'false',
            'format': 'oggopus',
        }
        
        try:
            response = requests.post(
                self.url, 
                params=params, 
                headers=headers, 
                data=voice_content
            )
            
            if response.status_code != 200:
                logger.error(f"Yandex SpeechKit error: {response.status_code} - {response.text}")
                return None
            
            result = response.json()
            return result.get('result')
            
        except Exception as e:
            logger.error(f"Failed to call Yandex SpeechKit: {e}")
            return None
