import os
import json
import urllib.request

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from agent_tools import consultar_sessio, buscar_aules

URL = "https://dcc-llm-gw.uab.cat/uabthehack/v1/chat/completions"
TIMEOUT = 90       # segons d'espera per resposta del model
MAX_PASSOS = 8     # rondes d'eines com a màxim per pregunta


# ============================================================
# DEFINICIÓ DE LES EINES PER A ORNITH
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_sessio",
            "description": "Consulta la informació d'una sessió.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_sessio": {
                        "type": "string",
                        "description": "Identificador de la sessió."
                    }
                },
                "required": ["id_sessio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_aules",
            "description": (
                "Busca aules compatibles i comprova la disponibilitat "
                "horària per a una sessió."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id_sessio": {
                        "type": "string",
                        "description": "Identificador de la sessió."
                    }
                },
                "required": ["id_sessio"]
            }
        }
    }
]


# ============================================================
# EXECUCIÓ DE LES EINES
# ============================================================

def executar_eina(nom, arguments):

    if nom == "consultar_sessio":
        return consultar_sessio(**arguments)

    if nom == "buscar_aules":
        return buscar_aules(**arguments)

    return {"error": f"Eina desconeguda: {nom}"}


# ============================================================
# CRIDA A ORNITH
# ============================================================

def cridar_ornith(messages):

    payload = {
        "model": "ornith",
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
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

    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


# ============================================================
# BUCLE DE L'AGENT
# ============================================================

def parlar(pregunta):

    messages = [
        {
            "role": "system",
            "content": (
                "Ets Ornith, un assistent expert en planificació "
                "d'horaris universitaris. "
                "Utilitza les eines disponibles per consultar sessions "
                "i buscar aules. "
                "No inventis disponibilitats ni dades. "
                "No recomanis aules que apareguin com a no disponibles."
            )
        },
        {
            "role": "user",
            "content": pregunta
        }
    ]

    for _ in range(MAX_PASSOS):

        resultat = cridar_ornith(messages)
        message = resultat["choices"][0]["message"]

        # Si el model no demana cap eina, acabem
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            return message.get("content", "")

        messages.append(message)

        # Executem totes les eines sol·licitades
        for call in tool_calls:

            nom = call["function"]["name"]

            arguments = json.loads(
                call["function"]["arguments"]
            )

            print(f"\n[ORNITH] Executant eina: {nom}")
            print(f"[ARGUMENTS] {arguments}")

            resposta_eina = executar_eina(
                nom,
                arguments
            )

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(
                    resposta_eina,
                    ensure_ascii=False,
                    default=str
                )
            })

    return "No he pogut acabar la consulta: massa passos amb les eines."


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

if __name__ == "__main__":

    pregunta = input("Què vols consultar a Ornith? ")

    try:
        resposta = parlar(pregunta)
        print("\nORNITH:")
        print(resposta)

    except Exception as e:
        print("\nERROR:")
        print(type(e).__name__, str(e))

