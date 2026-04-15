import httpx
import os
import uuid
import logging
from pathlib import Path
from typing import Annotated, Literal, Optional, Union
from .config import config
from .utils import poll_ace_step_job, save_base64_to_file, resolve_input_to_base64

logger = logging.getLogger(__name__)

# --- Types & Constants ---
ImageFormat = Literal["square", "portrait", "landscape"]
IMAGE_RESOLUTIONS = {
    "square": "1440x1440",
    "portrait": "1088x1920",
    "landscape": "1920x1088"
}

# 50+ languages supported by ACE Step
VocalLanguage = Literal[
    "en", "zh", "ja", "ko", "es", "fr", "de", "it", "pt", "ru",
    "hi", "bn", "ar", "tr", "th", "vi", "sv", "nl", "pl", "he"
]

MusicKey = Literal[
    "C Major", "C# Major", "D Major", "D# Major", "E Major", "F Major", "F# Major", "G Major", "G# Major", "A Major", "A# Major", "B Major",
    "C Minor", "C# Minor", "D Minor", "D# Minor", "E Minor", "F Minor", "F# Minor", "G Minor", "G# Minor", "A Minor", "A# Minor", "B Minor",
    ""
]

TimeSignature = Literal["2", "3", "4", "5", "6", ""]

class MediaClient:
    def __init__(self):
        self.headers = {}
        if config.IMAGE_API_KEY:
            self.headers["Authorization"] = f"Bearer {config.IMAGE_API_KEY}"

    async def generate_image(
        self,
        prompt: Annotated[str, "Detailed description of the image to generate"],
        format: Optional[Annotated[ImageFormat, "Image aspect ratio/format"]] = "square"
    ) -> Path:
        """Calls OpenAI-compatible image generations endpoint."""
        resolution = IMAGE_RESOLUTIONS.get(format, "1440x1440")
        
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            payload = {
                "prompt": prompt,
                "model": config.IMAGE_MODEL,
                "size": resolution,
                "n": 1,
                "response_format": "b64_json" # Prefer b64 to save locally
            }
            
            response = await client.post(
                f"{config.IMAGE_BASE_URL}/v1/images/generations",
                json=payload,
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract first image
            b64_data = data["data"][0]["b64_json"]
            return save_base64_to_file(b64_data, prefix="generated_img")

    async def edit_image(
        self,
        image: Annotated[str, "Local file path or base64-encoded source image"],
        prompt: Annotated[str, "Description of the changes or the target image"],
        format: Optional[Annotated[ImageFormat, "Image aspect ratio/format"]] = "square"
    ) -> Path:
        """Calls OpenAI-compatible image edits endpoint."""
        resolution = IMAGE_RESOLUTIONS.get(format, "1440x1440")
        
        # Resolve input (path or b64) to base64
        image_b64 = resolve_input_to_base64(image)

        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            # Save b64 to file to send as multipart (API requires file)
            temp_image = save_base64_to_file(image_b64, prefix="edit_source")
            
            files = {
                "image": open(temp_image, "rb")
            }
            data = {
                "prompt": prompt,
                "model": config.IMAGE_MODEL,
                "n": "1",
                "size": resolution,
                "response_format": "b64_json"
            }
            
            try:
                response = await client.post(
                    f"{config.IMAGE_BASE_URL}/v1/images/edits",
                    data=data,
                    files=files,
                    headers=self.headers
                )
                response.raise_for_status()
                result_data = response.json()
                b64_result = result_data["data"][0]["b64_json"]
                return save_base64_to_file(b64_result, prefix="edited_img")
            finally:
                files["image"].close()
                if os.path.exists(temp_image):
                    os.remove(temp_image)

class MusicClient:
    def __init__(self):
        self.base_url = config.MUSIC_BASE_URL
        self._token = config.MUSIC_API_KEY

    async def _ensure_token(self, client: httpx.AsyncClient):
        """Fetches a token via /api/auth/auto if missing."""
        if not self._token:
            logger.info("Fetching auto-auth token for ACE Step...")
            try:
                resp = await client.get(f"{self.base_url}/api/auth/auto")
                resp.raise_for_status()
                self._token = resp.json().get("token")
            except Exception as e:
                logger.error(f"Failed to auto-auth with ACE Step: {e}")
                raise

    def _get_headers(self):
        """Returns headers with Bearer token if available."""
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def generate_song(
        self,
        prompt: Annotated[str, "Style, mood, and genre description of the song"],
        lyrics: Optional[Annotated[str, "Optional lyrics to sing"]] = "",
        language: Optional[Annotated[VocalLanguage, "Vocal language"]] = "en",
        tags: Optional[Annotated[str, "Optional music tags (instruments, mood, tempo)"]] = "",
        key: Optional[Annotated[MusicKey, "Musical key and scale"]] = "",
        time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature"]] = ""
    ) -> Path:
        """Calls ACE Step UI generate endpoint."""
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            await self._ensure_token(client)
            
            payload = {
                "taskType": "text2music",
                "songDescription": prompt,
                "style": f"{tags}, {prompt}" if tags else prompt,
                "lyrics": lyrics,
                "instrumental": not bool(lyrics),
                "vocalLanguage": language,
                "keyScale": key,
                "timeSignature": time_signature,
                "title": f"Song {uuid.uuid4().hex[:8]}"
            }
            
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data["jobId"]
            
            # Poll for result
            result = await poll_ace_step_job(job_id, client, headers=self._get_headers())
            
            # ACE Step returns audioUrls (list). We take the first one.
            audio_url = result["audioUrls"][0]
            
            # Download the actual audio
            audio_response = await client.get(
                f"{self.base_url}{audio_url}",
                headers=self._get_headers()
            )
            audio_response.raise_for_status()
            
            # Save to assets
            filename = f"song_{uuid.uuid4().hex}.wav"
            file_path = config.ASSETS_DIR / filename
            with open(file_path, "wb") as f:
                f.write(audio_response.content)
            
            return file_path

    async def generate_cover(
        self,
        audio: Annotated[str, "Local file path or base64-encoded source audio file (song)"],
        style_prompt: Optional[Annotated[str, "Description of the target style or instructions"]] = "",
        strength: Optional[Annotated[float, "Strength of the source audio influence (0.0 to 1.0)"]] = 0.7,
        tags: Optional[Annotated[str, "Optional music tags for the cover style"]] = "",
        lyrics: Optional[Annotated[str, "Optional lyrics to sing"]] = "",
        language: Optional[Annotated[VocalLanguage, "Vocal language"]] = "en",
        key: Optional[Annotated[MusicKey, "Musical key and scale"]] = "",
        time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature"]] = ""
    ) -> Path:
        """Handles cover song generation flow: upload then generate."""
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            await self._ensure_token(client)
            
            # 1. Resolve source
            is_path = audio.startswith(("/", "./", "../")) or os.path.exists(audio)
            if is_path and os.path.exists(audio):
                audio_path = Path(audio)
                is_temp = False
            else:
                audio_b64 = resolve_input_to_base64(audio)
                audio_path = save_base64_to_file(audio_b64, prefix="cover_source")
                is_temp = True
            
            try:
                # Proper multipart upload
                files = {
                    "audio": (audio_path.name, open(audio_path, "rb"), "audio/wav")
                }
                
                upload_resp = await client.post(
                    f"{self.base_url}/api/generate/upload-audio",
                    files=files,
                    headers=self._get_headers()
                )
                upload_resp.raise_for_status()
                source_url = upload_resp.json()["url"]
                
                # 2. Trigger generation
                # Aligning EXACTLY with the payload provided by the user to avoid ROCm errors
                payload = {
                    "allowLmBatch": True,
                    "audioCoverStrength": strength,
                    "audioFormat": "mp3",
                    "autogen": False,
                    "batchSize": 1,
                    "bpm": 0,
                    "cfgIntervalEnd": 1,
                    "cfgIntervalStart": 0,
                    "constrainedDecodingDebug": False,
                    "getLrc": False,
                    "getScores": False,
                    "guidanceScale": 9,
                    "inferMethod": "ode",
                    "inferenceSteps": 12,
                    "instruction": "Fill the audio semantic mask based on the given conditions:",
                    "instrumental": not bool(lyrics),
                    "isFormatCaption": False,
                    "keyScale": key,
                    "lmBackend": "pt",
                    "lmBatchChunkSize": 8,
                    "lmCfgScale": 2.2,
                    "lmModel": "acestep-5Hz-lm-0.6B",
                    "lmNegativePrompt": "",
                    "lmTemperature": 0.8,
                    "lmTopK": 0,
                    "lmTopP": 0.92,
                    "lyrics": lyrics,
                    "randomSeed": True,
                    "referenceAudioTitle": audio_path.name,
                    "referenceAudioUrl": source_url,
                    "repaintingEnd": -1,
                    "repaintingStart": 0,
                    "scoreScale": 0.5,
                    "seed": -1,
                    "shift": 3,
                    "style": f"{tags}, {style_prompt}" if tags else style_prompt,
                    "taskType": "text2music",
                    "thinking": False,
                    "timeSignature": time_signature,
                    "title": f"Cover {uuid.uuid4().hex[:8]}",
                    "useAdg": False,
                    "useCotCaption": True,
                    "useCotLanguage": True,
                    "useCotMetas": True,
                    "vocalLanguage": language
                }
                
                logger.info(f"Sending generation request with payload: {payload}")
                
                gen_resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers=self._get_headers()
                )
                gen_resp.raise_for_status()
                job_id = gen_resp.json()["jobId"]
                
                # 3. Poll and Download
                result = await poll_ace_step_job(job_id, client, headers=self._get_headers())
                audio_url = result["audioUrls"][0]
                
                audio_resp = await client.get(
                    f"{self.base_url}{audio_url}",
                    headers=self._get_headers()
                )
                audio_resp.raise_for_status()
                
                filename = f"cover_{uuid.uuid4().hex}.wav"
                file_path = config.ASSETS_DIR / filename
                with open(file_path, "wb") as f:
                    f.write(audio_resp.content)
                
                return file_path
            finally:
                if 'files' in locals() and "audio" in files:
                    files["audio"][1].close()
                if is_temp and audio_path.exists():
                    os.remove(audio_path)
