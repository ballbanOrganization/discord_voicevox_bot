import asyncio
import json
import random
from collections import defaultdict
from typing import Any

import aiohttp

from .config import DEFAULT_VOICEVOX_URL

ALL_RANDOM_SPEAKER_ID = -1


class VoiceVoxError(RuntimeError):
    """Raised when the VOICEVOX engine cannot complete a request."""


class VoiceVox:
    def __init__(
        self,
        url: str = DEFAULT_VOICEVOX_URL,
        timeout: float = 10.0,
        session: aiohttp.ClientSession | None = None,
    ):
        self.url = url.rstrip("/") + "/"
        self.timeout = timeout
        self.speaker_dict: defaultdict[str, dict[str, int]] = defaultdict(dict)
        self._last_random_speaker_id: int | None = None
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or getattr(self._session, "closed", False):
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            self._owns_session = True
        return self._session

    async def _request_json(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        session = await self._get_session()
        try:
            async with session.request(
                method,
                f"{self.url}{endpoint}",
                **kwargs,
            ) as response:
                await self._raise_for_status(response, endpoint)
                try:
                    return await response.json()
                except (aiohttp.ContentTypeError, ValueError) as error:
                    raise VoiceVoxError(
                        f"VOICEVOX returned invalid JSON for /{endpoint}."
                    ) from error
        except asyncio.TimeoutError as error:
            raise VoiceVoxError(f"VOICEVOX timed out on /{endpoint}.") from error
        except aiohttp.ClientError as error:
            raise VoiceVoxError(f"VOICEVOX request failed on /{endpoint}.") from error

    async def _request_bytes(self, method: str, endpoint: str, **kwargs: Any) -> bytes:
        session = await self._get_session()
        try:
            async with session.request(
                method,
                f"{self.url}{endpoint}",
                **kwargs,
            ) as response:
                await self._raise_for_status(response, endpoint)
                return await response.read()
        except asyncio.TimeoutError as error:
            raise VoiceVoxError(f"VOICEVOX timed out on /{endpoint}.") from error
        except aiohttp.ClientError as error:
            raise VoiceVoxError(f"VOICEVOX request failed on /{endpoint}.") from error

    @staticmethod
    async def _raise_for_status(
        response: aiohttp.ClientResponse, endpoint: str
    ) -> None:
        if response.status < 400:
            return
        body = (await response.text())[:200]
        detail = f": {body}" if body else ""
        raise VoiceVoxError(
            f"VOICEVOX returned HTTP {response.status} for /{endpoint}{detail}"
        )

    async def load_speakers(self) -> list[dict[str, Any]]:
        speakers = await self._request_json("GET", "speakers")
        speaker_dict: defaultdict[str, dict[str, int]] = defaultdict(dict)
        for speaker in speakers:
            speaker_name = speaker["name"]
            for style in speaker.get("styles", []):
                speaker_dict[speaker_name][style["name"]] = int(style["id"])
        self.speaker_dict = speaker_dict
        return speakers

    async def get_speakers(self) -> list[dict[str, Any]]:
        return await self.load_speakers()

    async def get_query(self, text: str, speaker: int) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "audio_query",
            params={"text": text, "speaker": str(speaker)},
        )

    async def get_synthesis(self, query: dict[str, Any], speaker: int) -> bytes:
        return await self._request_bytes(
            "POST",
            "synthesis",
            params={"speaker": str(speaker)},
            data=json.dumps(query, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    async def text_to_sound(self, text: str, speaker: int = 3) -> bytes:
        query = await self.get_query(text, speaker)
        return await self.get_synthesis(query, speaker)

    def get_speaker_name(self, speaker_id: int) -> str:
        for speaker_name, styles in self.speaker_dict.items():
            for style_name, style_id in styles.items():
                if style_id == speaker_id:
                    return style_name + speaker_name
        return "名称なし"

    def get_random_speaker_id(self) -> int:
        speaker_ids = [
            style_id
            for styles in self.speaker_dict.values()
            for style_id in styles.values()
        ]
        if not speaker_ids:
            raise VoiceVoxError("No VOICEVOX speakers have been loaded.")
        candidates = speaker_ids
        if len(set(speaker_ids)) > 1 and self._last_random_speaker_id in speaker_ids:
            candidates = [
                speaker_id
                for speaker_id in speaker_ids
                if speaker_id != self._last_random_speaker_id
            ]
        selected_speaker_id = random.choice(candidates)
        self._last_random_speaker_id = selected_speaker_id
        return selected_speaker_id

    async def close(self) -> None:
        if (
            self._owns_session
            and self._session is not None
            and not getattr(self._session, "closed", False)
        ):
            await self._session.close()

    async def __aenter__(self) -> "VoiceVox":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
