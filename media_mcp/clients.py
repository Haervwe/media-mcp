import httpx
import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Annotated, Literal, Optional, Union
from pydantic import BeforeValidator
from .config import config
from .utils import poll_ace_step_job, save_base64_to_file, resolve_input_to_base64, unload_models, get_unique_path, sanitize_filename

logger = logging.getLogger(__name__)

def strip_quotes(v):
    """Strips surrounding quotes from a string if present."""
    if isinstance(v, str):
        # Handle both single and double quotes
        return v.strip("'\"")
    return v

# --- Types & Constants ---
ImageFormat = Annotated[
    Literal["square", "portrait", "landscape"],
    BeforeValidator(strip_quotes)
]
IMAGE_RESOLUTIONS = {
    "square": "1024x1024",
    "portrait": "896x1536",
    "landscape": "1536x896"
}

# 50+ languages supported by ACE Step
VocalLanguage = Annotated[
    Literal[
        "en", "zh", "ja", "ko", "es", "fr", "de", "it", "pt", "ru",
        "hi", "bn", "ar", "tr", "th", "vi", "sv", "nl", "pl", "he"
    ],
    BeforeValidator(strip_quotes)
]

MusicKey = Annotated[
    Literal[
        "C Major", "C# Major", "D Major", "D# Major", "E Major", "F Major", "F# Major", "G Major", "G# Major", "A Major", "A# Major", "B Major",
        "C Minor", "C# Minor", "D Minor", "D# Minor", "E Minor", "F Minor", "F# Minor", "G Minor", "G# Minor", "A Minor", "A# Minor", "B Minor",
        ""
    ],
    BeforeValidator(strip_quotes)
]

TimeSignature = Annotated[
    Literal["2", "3", "4", "5", "6", ""],
    BeforeValidator(strip_quotes)
]

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
        images: Annotated[Union[str, list[str]], "One or up to 3 images (base + references)"],
        prompt: Annotated[str, "Description of the changes or the target image"],
        format: Optional[Annotated[ImageFormat, "Image aspect ratio/format"]] = "square"
    ) -> Path:
        """Calls OpenAI-compatible image edits endpoint for stable-diffusion.cpp."""
        resolution = IMAGE_RESOLUTIONS.get(format, "1440x1440")
        
        # Ensure images is a list
        if isinstance(images, str):
            image_list = [images]
        else:
            image_list = images
            
        if not image_list:
            raise ValueError("No images provided for editing")
        if len(image_list) > 3:
            raise ValueError("Too many images provided. Maximum is 3 (1 base + 2 references).")
        
        temp_paths = []
        try:
            # Resolve all inputs to temporary files
            for idx, img_input in enumerate(image_list):
                logger.info(f"Resolving image input {idx} (type: {type(img_input)}): {img_input}")
                img_b64 = await resolve_input_to_base64(img_input)
                prefix = "edit_source" if idx == 0 else f"edit_ref_{idx}"
                temp_paths.append(save_base64_to_file(img_b64, prefix=prefix))
            
            async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
                # Prepare multipart files with indexed keys (image, image1, image2)
                # This matches the expected pattern for stable-diffusion.cpp multi-image edits
                files = {}
                opened_files = []
                for idx, path in enumerate(temp_paths):
                    field_name = "image" if idx == 0 else f"image{idx}"
                    f = open(path, "rb")
                    opened_files.append(f)
                    files[field_name] = f
                
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
                    for f in opened_files:
                        f.close()
        finally:
            for path in temp_paths:
                if path.exists():
                    os.remove(path)

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

    async def _fetch_song_from_library(self, title: str, client: httpx.AsyncClient) -> Optional[str]:
        """
        Fetches the user's song library and looks for a song with the matching title.
        Returns the resolved audio_url if found.
        """
        logger.info(f"Looking for song titled '{title}' in backend library...")
        try:
            resp = await client.get(f"{self.base_url}/api/songs", headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
            songs = data.get("songs", [])
            
            # Simple exact match or sanitized match
            target = title.strip().lower()
            for song in songs:
                if song.get("title", "").strip().lower() == target:
                    audio_url = song.get("audio_url")
                    logger.info(f"Found match in library! Permanent URL: {audio_url}")
                    return audio_url
        except Exception as e:
            logger.error(f"Failed to fetch songs from library: {e}")
        
        return None

    async def generate_song(
        self,
        prompt: Annotated[str, "Style, mood, and genre description of the song"],
        lyrics: Optional[Annotated[str, "Optional lyrics to sing"]] = "",
        language: Optional[Annotated[VocalLanguage, "Vocal language"]] = "en",
        tags: Optional[Annotated[str, "Optional music tags (instruments, mood, tempo)"]] = "",
        key: Optional[Annotated[MusicKey, "Musical key and scale"]] = "",
        time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature"]] = "",
        title: Optional[str] = None
    ) -> Path:
        """Calls ACE Step UI generate endpoint."""
        # Unload models to free VRAM
        await unload_models()

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
                "title": title if title else f"Song {uuid.uuid4().hex[:8]}"
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
            try:
                audio_response = await client.get(
                    f"{self.base_url}{audio_url}",
                    headers=self._get_headers()
                )
                audio_response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Initial audio URL {audio_url} 404'd. Backend likely renaming file. Retrying via library lookup...")
                    await asyncio.sleep(2) # Give backend time to finish move
                    
                    library_url = await self._fetch_song_from_library(payload["title"], client)
                    if library_url:
                        fetch_url = f"{self.base_url}{library_url}" if not library_url.startswith("http") else library_url
                        audio_response = await client.get(fetch_url, headers=self._get_headers())
                        audio_response.raise_for_status()
                    else:
                        raise
                else:
                    raise
            
            # Save to assets
            final_title = title if title else f"song_{uuid.uuid4().hex[:8]}"
            file_path = get_unique_path(config.ASSETS_DIR, final_title, ".wav")
            
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
        time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature"]] = "",
        title: Optional[str] = None
    ) -> Path:
        """Handles cover song generation flow: upload then generate."""
        # Unload models to free VRAM
        await unload_models()
        
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            await self._ensure_token(client)
            
            # 1. Resolve source
            is_path = audio.startswith(("/", "./", "../")) or os.path.exists(audio)
            if is_path and os.path.exists(audio):
                audio_path = Path(audio)
                is_temp = False
            else:
                audio_b64 = await resolve_input_to_base64(audio)
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
                    "title": title if title else f"Cover {uuid.uuid4().hex[:8]}",
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
                
                try:
                    audio_resp = await client.get(
                        f"{self.base_url}{audio_url}",
                        headers=self._get_headers()
                    )
                    audio_resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Initial cover URL {audio_url} 404'd. Backend likely renaming file. Retrying via library lookup...")
                        await asyncio.sleep(2)
                        
                        library_url = await self._fetch_song_from_library(payload["title"], client)
                        if library_url:
                            fetch_url = f"{self.base_url}{library_url}" if not library_url.startswith("http") else library_url
                            audio_resp = await client.get(fetch_url, headers=self._get_headers())
                            audio_resp.raise_for_status()
                        else:
                            raise
                    else:
                        raise
                
                final_title = title if title else f"cover_{uuid.uuid4().hex[:8]}"
                file_path = get_unique_path(config.ASSETS_DIR, final_title, ".wav")
                
                with open(file_path, "wb") as f:
                    f.write(audio_resp.content)
                
                return file_path
            finally:
                if 'files' in locals() and "audio" in files:
                    files["audio"][1].close()
                if is_temp and audio_path.exists():
                    os.remove(audio_path)
