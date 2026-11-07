import os
import json
import urllib.request
import sys

URL = "https://dcc-llm-gw.uab.cat/uabthehack/v1/chat/completions"

def ask_ornith(messages):
    payload = {
        "model": "ornith",
        "messages": messages,
        "stream": False,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        }
    }

    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['UTH_KEY']}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Uso: python test_ornith.py 'Tu pregunta aquí'")
        sys.exit(1)

    st = sys.argv[1]

    print(ask_ornith([
        {"role": "user", "content": st}
    ]))
