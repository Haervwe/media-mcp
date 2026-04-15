import os
import asyncio
import base64
import uuid
import time
import httpx
import logging
from pathlib import Path
from .config import config

logger = logging.getLogger(__name__)

def save_base64_to_file(b64_string: str, prefix: str = "input") -> Path:
    """Saves a base64 string to a temporary file in the assets directory."""
    try:
        # Strip potential header (data:image/png;base64,...)
        if "," in b64_string:
            b64_string = b64_string.split(",")[1]
        
        data = base64.b64decode(b64_string)
        # Determine extension based on prefix
        if any(x in prefix.lower() for x in ["img", "image", "edit", "pic"]):
            ext = ".png"
        elif any(x in prefix.lower() for x in ["audio", "song", "cover", "music"]):
            ext = ".wav"
        else:
            ext = ".bin"
        filename = f"{prefix}_{uuid.uuid4()}{ext}"
        file_path = config.ASSETS_DIR / filename
        
        with open(file_path, "wb") as f:
            f.write(data)
        
        return file_path
    except Exception as e:
        logger.error(f"Failed to save base64 to file: {e}")
        raise

def resolve_input_to_base64(input_val: str) -> str:
    """
    Detects if the input is a local file path or a base64 string.
    If it's a path and exists, reads it and returns base64.
    If it's already base64, returns it as is.
    """
    if not input_val:
        raise ValueError("Input is empty")

    # Check if it looks like a path and exists
    if input_val.startswith(("/", "./", "../")) or os.path.exists(input_val):
        path = Path(input_val)
        if path.exists():
            return file_to_base64(path)
    
    # Otherwise, assume it's already base64
    return input_val

def file_to_base64(file_path: Path) -> str:
    """Reads a file and returns its base64 representation."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def format_output(file_path: Path, metadata: dict = None) -> dict:
    """Formats the output based on RESPONSE_FORMAT."""
    result = {
        "status": "success",
        "metadata": metadata or {}
    }
    
    if config.RESPONSE_FORMAT == "base64":
        result["data"] = file_to_base64(file_path)
    else:
        result["path"] = str(file_path)
    
    # Also provide the filename for convenience
    result["filename"] = file_path.name
    return result

async def poll_ace_step_job(job_id: str, client: httpx.AsyncClient, headers: dict = None) -> dict:
    """Polls ACE Step UI for job completion."""
    start_time = time.time()
    while time.time() - start_time < config.REQUEST_TIMEOUT:
        try:
            response = await client.get(
                f"{config.MUSIC_BASE_URL}/api/generate/status/{job_id}",
                headers=headers
            )
            
            if response.status_code == 429:
                logger.warning(f"Rate limited (429) while polling {job_id}. Waiting 10s...")
                await asyncio.sleep(10)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status")
            if status == "succeeded":
                return data.get("result")
            elif status == "failed":
                error_msg = data.get("error", "Unknown generation error")
                raise Exception(f"Music generation failed: {error_msg}")
            
            # Still running or queued - wait 5 seconds (async)
            await asyncio.sleep(5)
        except Exception as e:
            if isinstance(e, httpx.HTTPError) and e.response and e.response.status_code == 429:
                logger.warning(f"Caught 429 in exception handler for {job_id}. Waiting 10s...")
                await asyncio.sleep(10)
                continue
            
            if isinstance(e, httpx.HTTPError):
                logger.error(f"HTTP error while polling job {job_id}: {e}")
            else:
                raise
    
    raise TimeoutError(f"Music generation timed out after {config.REQUEST_TIMEOUT}s")
