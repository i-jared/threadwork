def build_api_request(prompt: str, config: dict):
    if config["provider"] == "anthropic":
        return get_anthropic_config(config["api_key"], prompt, config["max_tokens"], config["model"])
    elif config["provider"] == "gemini":
        return get_gemini_config(config["api_key"], prompt, config["max_tokens"], config["model"])
    else:
        raise ValueError(f"Invalid provider: {config['provider']}")

def get_anthropic_config(api_key: str,prompt: str, max_tokens: int = 1024, model: str = "claude-3-5-sonnet-20241022"):
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
