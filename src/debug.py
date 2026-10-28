import requests, json

payload = {
    "model": "maternion/mimo-v2.6-heretic:9b",
    "stream": False,
    "messages": [{"role": "user", "content": "Create /tmp/a.txt containing hello"}],
    "tools": [{
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    }],
}

r = requests.post("http://localhost:11434/api/chat", json=payload)
print(json.dumps(r.json()["message"], indent=2, ensure_ascii=False))