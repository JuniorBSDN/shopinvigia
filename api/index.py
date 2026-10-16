import os
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ShopinVigia API - Master")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Puxa estritamente a variável de ambiente do Vercel (Produção)
SENHA_MASTER = os.getenv("SENHA_MASTER")

class LoginRequest(BaseModel):
    senha_master: str

class StatusUpdateRequest(BaseModel):
    id: int
    status: str

class ReciboRequest(BaseModel):
    id_cliente: str
    info_empresa: dict
    info_cliente: dict
    competencia: str
    informacoes: str
    obs: str

def verificar_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autorizado")
    if authorization.split(" ")[1] != "token_master_producao":
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return True

@app.post("/api/master/login")
def login(dados: LoginRequest):
    if dados.senha_master == SENHA_MASTER:
        return {"mensagem": "Autenticado", "token": "token_master_producao"}
    raise HTTPException(status_code=401, detail="Acesso Negado")

@app.get("/api/master/dashboard", dependencies=[Depends(verificar_token)])
def dashboard():
    return {"db_usado": 0, "novos_clientes": 0, "vencidos": 0}

@app.get("/api/master/clientes", dependencies=[Depends(verificar_token)])
def clientes(busca: str = "", status: str = ""):
    return []

@app.put("/api/master/clientes/{id_cliente}/toggle", dependencies=[Depends(verificar_token)])
def toggle_status(id_cliente: int):
    return {"mensagem": "Status alterado"}

@app.get("/api/master/financeiro/graficos", dependencies=[Depends(verificar_token)])
def graficos(periodo: str = "mes"):
    return {"labels": [], "valores": []}

@app.get("/api/master/financeiro/notificacoes", dependencies=[Depends(verificar_token)])
def notificacoes():
    return {"a_vencer": 0, "vencidos": 0, "bloqueados": 0}

@app.get("/api/master/financeiro/lista", dependencies=[Depends(verificar_token)])
def financeiro_lista(busca: str = ""):
    return []

@app.put("/api/master/financeiro/status", dependencies=[Depends(verificar_token)])
def financeiro_status(dados: StatusUpdateRequest):
    return {"mensagem": "Status atualizado"}

@app.post("/api/master/config/pix", dependencies=[Depends(verificar_token)])
async def config_pix(qr_code: UploadFile = File(...), chave_pix: str = Form(...)):
    return {"mensagem": "PIX salvo"}

@app.post("/api/master/recibos", dependencies=[Depends(verificar_token)])
def emitir_recibo(dados: ReciboRequest):
    return {"mensagem": "Recibo gerado"}
