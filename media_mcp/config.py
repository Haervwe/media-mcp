import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv()

class Config:
    # --- Image Generation (stable-diffusion.cpp / llama-swap) ---
    IMAGE_BASE_URL = os.getenv("IMAGE_API_BASE_URL", "http://localhost:4134")
    IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "flux-klein")
    IMAGE_SIZE_SQUARE = os.getenv("IMAGE_SIZE_SQUARE", "1024x1024")
    IMAGE_SIZE_PORTRAIT = os.getenv("IMAGE_SIZE_PORTRAIT", "896x1536")
    IMAGE_SIZE_LANDSCAPE = os.getenv("IMAGE_SIZE_LANDSCAPE", "1536x896")

    # --- Music Generation (ACE Step CPP UI) ---
    MUSIC_BASE_URL = os.getenv("MUSIC_API_BASE_URL", "http://localhost:3005")
    MUSIC_API_KEY = os.getenv("MUSIC_API_KEY", "")
    MUSIC_JWT_SECRET = os.getenv("MUSIC_JWT_SECRET", "")

    # --- Music Generation Parameters ---
    MUSIC_GUIDANCE_SCALE = float(os.getenv("MUSIC_GUIDANCE_SCALE", "9"))
    MUSIC_INFERENCE_STEPS = int(os.getenv("MUSIC_INFERENCE_STEPS", "12"))
    MUSIC_LM_CFG_SCALE = float(os.getenv("MUSIC_LM_CFG_SCALE", "2.2"))
    MUSIC_LM_TEMPERATURE = float(os.getenv("MUSIC_LM_TEMPERATURE", "0.8"))
    MUSIC_LM_TOP_P = float(os.getenv("MUSIC_LM_TOP_P", "0.92"))
    MUSIC_SHIFT = int(os.getenv("MUSIC_SHIFT", "3"))

    # --- Asset Storage ---
    ASSETS_DIR = Path(os.getenv("ASSETS_DIR", "/tmp/media-mcp-assets"))
    
    # Ensure assets directory exists
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Response Format ---
    RESPONSE_FORMAT = os.getenv("RESPONSE_FORMAT", "path").lower()

    # --- MCP Server Transport ---
    MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
    MCP_PORT = int(os.getenv("MCP_PORT", "8080"))

    # --- Timeout ---
    # Music generation can be slow
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))

    # --- Model Unloading ---
    # Comma-separated list of base URLs for llama-swap (e.g. http://localhost:4134)
    LLAMA_UNLOAD = os.getenv("LLAMA_UNLOAD", "")
    UNLOAD_WAIT_SECONDS = int(os.getenv("UNLOAD_WAIT_SECONDS", "2"))
    MAX_UNLOAD_POLLS = int(os.getenv("MAX_UNLOAD_POLLS", "30"))

config = Config()
