# 🌌 MediaMCP

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastMCP](https://img.shields.io/badge/Framework-FastMCP-orange.svg)](https://github.com/jlowin/fastmcp)

**MediaMCP** is a powerful Model Context Protocol (MCP) server designed for high-performance, local AI media generation. It provides a seamless interface for LLMs to generate and edit images, as well as compose and cover music using local backend services.

---

## ✨ Features

- 🖼️ **Image Generation**: Generate high-fidelity images using the **Flux** model via `stable-diffusion.cpp`.
- 🎨 **Image Editing**: Perform image-to-image transformations and edits with text guidance.
- 🎵 **Music Composition**: Create complete songs with vocals using **ACE Step**.
- 🎤 **Cover Generation**: Transform existing audio into new styles or voices (voice conversion).
- 🚀 **FastMCP Powered**: Built on the modern FastMCP framework for low-latency, scalable tool execution.
- 🔌 **Standardized Interface**: Exposes a clean API for any MCP-compliant client (like Claude Desktop or custom agents).

---

## 🛠️ Installation

### Prerequisites

- Python 3.11 or higher
- Access to local media generation backends:
  - `stable-diffusion.cpp` (or compatible API) for images.
  - `ACE Step CPP` (or compatible API) for music.

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/haervwe/media-mcp.git
   cd media-mcp
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   ```

4. **Configure environment variables:**
   Copy the example environment file and fill in your API keys and endpoints:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to match your local setup.

---

## 🚀 Usage

Start the MediaMCP server:

```bash
python -m media_mcp.server
```

The server will start on the host and port specified in your `.env` (default: `0.0.0.0:8080`) using the `streamable-http` transport.

---

## 🧰 Tools Provided

| Tool | Description | Key Parameters |
| :--- | :--- | :--- |
| `generate_image` | Generate a new image from text. | `prompt`, `format` |
| `edit_image` | Edit an existing image. | `image` (path/b64), `prompt`, `format` |
| `generate_song` | Create a full song with vocals. | `prompt`, `lyrics`, `language`, `key` |
| `generate_cover` | Create a cover of an audio file. | `audio` (path/b64), `style_prompt`, `strength` |

---

## ⚙️ Configuration

MediaMCP is highly configurable via environment variables in the `.env` file:

- `IMAGE_API_BASE_URL`: Endpoint for your image generation service.
- `MUSIC_API_BASE_URL`: Endpoint for your music generation service.
- `ASSETS_DIR`: Local directory where generated media files are stored.
- `RESPONSE_FORMAT`: Choose between `path` (file system path) or `base64` (inline content).
- `REQUEST_TIMEOUT`: Timeout for long-running generation tasks (default: 300s).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Developed with ❤️ for the AI community.
</p>
