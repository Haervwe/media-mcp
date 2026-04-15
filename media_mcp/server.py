import logging
from typing import Optional, Annotated, Literal
from fastmcp import FastMCP
from .clients import MediaClient, MusicClient, ImageFormat, VocalLanguage, MusicKey, TimeSignature
from .utils import format_output
from .config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("media-mcp")

# Initialize FastMCP
mcp = FastMCP("MediaMCP")

# Core clients
media_client = MediaClient()
music_client = MusicClient()

@mcp.tool()
async def generate_image(
    prompt: Annotated[str, "Detailed description of the image to generate"],
    format: Optional[Annotated[ImageFormat, "Image format (square, portrait, landscape)"]] = "square"
) -> dict:
    """
    Generate an image from a text prompt using the local Flux model.
    """
    logger.info(f"Generating image: {prompt} (format: {format})")
    try:
        path = await media_client.generate_image(prompt, format=format)
        return format_output(path, {"prompt": prompt, "model": config.IMAGE_MODEL, "format": format})
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def edit_image(
    image: Annotated[str, "Local file path or base64-encoded source image"],
    prompt: Annotated[str, "Description of the changes or the target image"],
    format: Optional[Annotated[ImageFormat, "Image format (square, portrait, landscape)"]] = "square"
) -> dict:
    """
    Edit an existing image (image-to-image) using a prompt.
    """
    logger.info(f"Editing image with prompt: {prompt} (format: {format})")
    try:
        path = await media_client.edit_image(image, prompt, format=format)
        return format_output(path, {"prompt": prompt, "action": "edit", "format": format})
    except Exception as e:
        logger.error(f"Image editing failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def generate_song(
    prompt: Annotated[str, "Style, mood, and genre description of the song"],
    lyrics: Optional[Annotated[str, "Optional lyrics to sing"]] = "",
    tags: Optional[Annotated[str, "Optional music tags (instruments, mood, tempo)"]] = "",
    language: Optional[Annotated[VocalLanguage, "Vocal language"]] = "en",
    key: Optional[Annotated[MusicKey, "Musical key and scale"]] = "",
    time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature (2, 3, 4, 5, 6)"]] = ""
) -> dict:
    """
    Generate a complete song (music + vocals) from a prompt and optional lyrics.
    """
    logger.info(f"Generating song. Prompt: {prompt}, Language: {language}, Key: {key}, TS: {time_signature}")
    try:
        path = await music_client.generate_song(prompt, lyrics, language=language, tags=tags, key=key, time_signature=time_signature)
        return format_output(path, {"prompt": prompt, "lyrics": lyrics, "tags": tags, "language": language, "key": key, "time_signature": time_signature})
    except Exception as e:
        logger.error(f"Song generation failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def generate_cover(
    audio: Annotated[str, "Local file path or base64-encoded source audio file (song)"],
    style_prompt: Optional[Annotated[str, "Description of the target style or instructions"]] = "",
    strength: Optional[Annotated[float, "Strength of the source audio influence (0.0 to 1.0)"]] = 0.7,
    tags: Optional[Annotated[str, "Optional music tags for the cover style"]] = "",
    lyrics: Optional[Annotated[str, "Optional lyrics to sing"]] = "",
    language: Optional[Annotated[VocalLanguage, "Vocal language"]] = "en",
    key: Optional[Annotated[MusicKey, "Musical key and scale"]] = "",
    time_signature: Optional[Annotated[TimeSignature, "Rhythmic time signature (2, 3, 4, 5, 6)"]] = ""
) -> dict:
    """
    Generate a cover version of an existing audio file (voice conversion/style swap).
    """
    logger.info(f"Generating cover version. Style: {style_prompt}, Language: {language}, Key: {key}")
    try:
        path = await music_client.generate_cover(
            audio, style_prompt, strength=strength, tags=tags, lyrics=lyrics, 
            language=language, key=key, time_signature=time_signature
        )
        return format_output(path, {
            "style": style_prompt, "action": "cover", "strength": strength, 
            "tags": tags, "lyrics": lyrics, "language": language, "key": key, "time_signature": time_signature
        })
    except Exception as e:
        logger.error(f"Cover generation failed: {e}")
        return {"status": "error", "message": str(e)}

def main():
    logger.info(f"Starting MediaMCP server on {config.MCP_HOST}:{config.MCP_PORT} (streamable-http)")
    mcp.run(transport="streamable-http", host=config.MCP_HOST, port=config.MCP_PORT)

if __name__ == "__main__":
    main()
