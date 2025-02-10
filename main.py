import sys
# Add the 'src' directory to the Python path so that modules in there (e.g., config.py) can be imported.
sys.path.append("src")

import os
import aiohttp
from aiohttp import web
from config import build_api_request, extract_api_response
from dotenv import load_dotenv
from aiohttp.web import middleware
from aiohttp.web_request import Request
from aiohttp.web_response import Response

# Load environment variables from .env
load_dotenv()

routes = web.RouteTableDef()

# Define configuration for each provider using environment variables.
anthropic_config = {
    "provider": "anthropic",
    "api_key": os.getenv("ANTHROPIC_API_KEY"),
    "max_tokens": 50,
    "model": "claude-3-5-sonnet-20241022"
}
gemini_config = {
    "provider": "gemini",
    "api_key": os.getenv("GEMINI_API_KEY"),
    "max_tokens": 50,
    "model": "gemini-2.0-flash"
}
openai_config = {
    "provider": "openai",
    "api_key": os.getenv("OPENAI_API_KEY"),
    "max_tokens": 50,
    "model": "gpt-3.5-turbo"
}
deepseek_config = {
    "provider": "deepseek",
    "api_key": os.getenv("DEEPSEEK_API_KEY"),
    "max_tokens": 50,
    "model": "deepseek-reasoner"
}

# Build a dictionary of provider configurations.
provider_configs = {
    "Anthropic": anthropic_config,
    "Gemini": gemini_config,
    "OpenAI": openai_config,
    "DeepSeek": deepseek_config
}

@middleware
async def cors_middleware(request: Request, handler):
    response: Response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = 'http://localhost:5173'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@routes.get('/')
async def handle_root(request):
    return web.json_response({"status": "ok", "providers": list(provider_configs.keys())})

app = web.Application(middlewares=[cors_middleware])
app.add_routes(routes)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8000) 