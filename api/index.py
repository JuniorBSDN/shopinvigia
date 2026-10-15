import os
from fastapi import FastAPI, HTTPException

app = FastAPI()
# Lê a senha direto da variável de ambiente do Vercel
SENHA_REAL = os.getenv("SENHA_MASTER") 

@app.post("/api/master/login")
def login_master(dados: dict):
    if dados.get("senha_master") == SENHA_REAL:
        return {"mensagem": "Acesso Liberado", "token": "token_de_sessao"}
    else:
        raise HTTPException(status_code=401, detail="Senha incorreta")
