import os
from PyPDF2 import PdfReader

# Estrae il testo dal pdf
def pdf_to_text(pdf_path: str, txt_path: str):
    if not os.path.exists(pdf_path):
        print(f"Errore: il file PDF '{pdf_path}' non esiste.")
        return

    try:
        reader = PdfReader(pdf_path)
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            else:
                print(f"Attenzione: pagina {i+1} vuota o non leggibile.")
        
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        
        print(f"Testo estratto correttamente in '{txt_path}'.")
    
    except Exception as e:
        print("Errore durante l'estrazione del testo:", e)


if __name__ == "__main__":
    
    script_dir = os.path.dirname(os.path.abspath(__file__))

    PDF_FILE = os.path.join(script_dir, "static", "regolamento.pdf")
    TXT_FILE = os.path.join(script_dir, "regolamento.txt")

    pdf_to_text(PDF_FILE, TXT_FILE)
