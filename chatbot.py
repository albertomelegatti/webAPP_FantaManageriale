import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=OPENAI_API_KEY
)

# Carica regolamento
def load_regolamento():
    try:
        with open(os.path.join(os.path.dirname(__file__), "regolamento.txt"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "⚠️ Nessun regolamento disponibile."

REGOLAMENTO = load_regolamento()

# Restituisce la risposta alla domanda basata sul regolamento.
def get_answer(question: str) -> str:
    
    if not question.strip():
        return "Devi inserire una domanda valida."

    try:
        completion = client.chat.completions.create(
            model="deepseek-ai/deepseek-v3.1-terminus",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei un assistente esperto del regolamento del Fantacalcio Manageriale. "
                        "Usa solo le informazioni seguenti e rispondi in modo chiaro e conciso. "
                        "Se la domanda non è trattata, rispondi: 'Non è specificato nel regolamento.'\n\n"
                        f"--- REGOLAMENTO ---\n{REGOLAMENTO}\n--- FINE ---"
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=0.2,
            top_p=0.7,
            max_tokens=512,
            stream=False,
        )

        return completion.choices[0].message.content.strip()
    except Exception as e:
        print("Errore chatbot:", e)
        return "⚠️ Errore nella comunicazione con il modello."

