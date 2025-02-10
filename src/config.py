import json

def build_api_request(prompt: str, config: dict) -> dict:
    """
    Builds the API request configuration based on the provider.
    """
    if config["provider"] == "anthropic":
        return {
            "api_endpoint": "https://api.anthropic.com/v1/messages",
            "headers": {
                "Content-Type": "application/json",
                "x-api-key": config["api_key"],
                "anthropic-version": "2023-06-01"
            },
            "body": json.dumps({
                "model": config["model"],
                "max_tokens": config["max_tokens"],
                "messages": [{"role": "user", "content": prompt}]
            }),
            "provider": config["provider"],
            "model": config["model"]
        }
    elif config["provider"] == "gemini":
        return {
            "api_endpoint": f"https://generativelanguage.googleapis.com/v1beta/models/{config['model']}:generateContent?key={config['api_key']}",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }),
            "provider": config["provider"],
            "model": config["model"]
        }
    elif config["provider"] == "openai":
        return get_openai_config(config["api_key"], prompt, config["max_tokens"], config["model"])
    elif config["provider"] == "deepseek":
        return get_deepseek_config(config["api_key"], prompt, config["max_tokens"], config["model"])
    else:
        raise ValueError(f"Unsupported provider: {config['provider']}")

def get_anthropic_config(api_key: str, prompt: str, max_tokens: int = 1024, model: str = "claude-3-5-sonnet-20241022"):
    return {
        "api_endpoint": "https://api.anthropic.com/v1/messages",
        "body": {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": f"{prompt}"}
            ]
        },
        "headers": {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    }

def get_gemini_config(api_key: str, prompt: str, max_tokens: int = 1024, model: str = "gemini-2.0-flash"):
    return {
        "api_endpoint": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        "body": {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        },
        "headers": {
            "Content-Type": "application/json"
        }
    }

def get_openai_config(api_key: str, prompt: str, max_tokens: int = 1024, model: str = "gpt-3.5-turbo"):
    return {
        "api_endpoint": "https://api.openai.com/v1/chat/completions",
        "body": {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        },
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    }

def get_deepseek_config(api_key: str, prompt: str, max_tokens: int = 1024, model: str = "deepseek-chat"):
    return {
        "api_endpoint": "https://api.deepseek.com/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        },
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    }

def extract_api_response(response: dict, provider: str):
    if provider == "anthropic":
        return get_anthropic_response(response)
    elif provider == "gemini":
        return get_gemini_response(response)
    elif provider == "openai":
        return get_openai_response(response)
    elif provider == "deepseek":
        return get_deepseek_response(response)
    else:
        raise ValueError(f"Invalid provider: {provider}")

def get_anthropic_response(response: dict):
    return {
        "content": response["content"][0]["text"],
        "usage": {
            "input_tokens": response["usage"]["input_tokens"],
            "output_tokens": response["usage"]["output_tokens"],
            "total_tokens": response["usage"]["input_tokens"] + response["usage"]["output_tokens"]
        }
    }

def get_gemini_response(response: dict):
    return {
        "content": response["candidates"][0]["content"]["parts"][0]["text"].strip(),
        "usage": {
            "input_tokens": response["usageMetadata"]["promptTokenCount"],
            "output_tokens": response["usageMetadata"]["candidatesTokenCount"],
            "total_tokens": response["usageMetadata"]["totalTokenCount"]
        }
    }

def get_openai_response(response: dict):
    return {
        "content": response["choices"][0]["message"]["content"],
        "usage": {
            "input_tokens": response["usage"]["prompt_tokens"],
            "output_tokens": response["usage"]["completion_tokens"],
            "total_tokens": response["usage"]["total_tokens"]
        }
    }

def get_deepseek_response(response: dict):
    return {
        "content": response["choices"][0]["message"]["content"],
        "usage": {
            "input_tokens": response["usage"]["prompt_tokens"],
            "output_tokens": response["usage"]["completion_tokens"],
            "total_tokens": response["usage"]["total_tokens"]
        }
    }
