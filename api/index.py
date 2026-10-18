import os
import uuid
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# from supabase import create_client, Client # (Descomente para produção real)

app = FastAPI(title="ShopinVigia API - Módulo Master SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# CONFIGURAÇÕES (VERCEL & SUPABASE)
# =====================================================================
# Senha exclusiva do dono saas. Se não achar no .env, usa '123456' como padrão
SENHA_MASTER_VERCEL = os.getenv("SENHA_MASTER", "123456")

# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================================
# MODELOS DE DADOS (PYDANTIC)
# =====================================================================
class LoginRequest(BaseModel):
    senha_master: str

class ClienteAtualizarRequest(BaseModel):
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None

class StatusFinanceiroRequest(BaseModel):
    id: int
    status: str

class ReciboRequest(BaseModel):
    id_cliente: str
    info_empresa: dict
    info_cliente: dict
    competencia: str
    informacoes: str
    obs: str

# =====================================================================
# AUTENTICAÇÃO
# =====================================================================
def verificar_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autorizado")
    if authorization.split(" ")[1] != "token_master_producao_shopinvigia":
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return True

# =====================================================================
# ROTAS DE LOGIN E DASHBOARD
# =====================================================================
@app.post("/api/master/login")
def login(dados: LoginRequest):
    """Valida a senha com a variável do ambiente vercel."""
    if dados.senha_master == SENHA_MASTER_VERCEL:
        return {"mensagem": "Autenticado", "token": "token_master_producao_shopinvigia"}
    raise HTTPException(status_code=401, detail="Acesso Negado")

@app.get("/api/master/dashboard", dependencies=[Depends(verificar_token)])
def dashboard():
    """Alimenta o gráfico de total usado no DB e os alertas do master."""
    return {
        "db_usado": 320,  # MB
        "novos_clientes": 2, 
        "vencidos": 5 
    }

# =====================================================================
# ROTAS: CLIENTES EMPRESA (CRUD COMPLETO)
# =====================================================================
@app.get("/api/master/clientes", dependencies=[Depends(verificar_token)])
def listar_clientes(busca: str = "", status: str = ""):
    """Busca registros por nome, id, data, status."""
    # Retornando dados fictícios para você testar a interface do Frontend
    clientes_mock = [
        {"id": 1, "data_cadastro": "15/10/2026", "nome": "Loja de Roupas Silva", "status": "ativo"},
        {"id": 2, "data_cadastro": "12/10/2026", "nome": "Eletrônicos Vigia", "status": "vencido"},
        {"id": 3, "data_cadastro": "05/09/2026", "nome": "Armarinho Central", "status": "bloqueado"},
    ]
    return clientes_mock

@app.put("/api/master/clientes/{id_cliente}/toggle-status", dependencies=[Depends(verificar_token)])
def toggle_status(id_cliente: int):
    """Botão Ativar/Bloquear e emissão de notificação por email."""
    return {"mensagem": f"Status do cliente {id_cliente} alternado com notificação enviada."}

@app.put("/api/master/clientes/{id_cliente}", dependencies=[Depends(verificar_token)])
def alterar_cliente(id_cliente: int, dados: ClienteAtualizarRequest):
    """Botão Alterar dados do cliente."""
    return {"mensagem": "Dados do cliente atualizados."}

@app.delete("/api/master/clientes/{id_cliente}", dependencies=[Depends(verificar_token)])
def excluir_cliente(id_cliente: int):
    """Botão Excluir cliente do banco."""
    return {"mensagem": "Cliente excluído do sistema."}

@app.post("/api/master/clientes/{id_cliente}/contrato", dependencies=[Depends(verificar_token)])
def emitir_contrato(id_cliente: int):
    """Botão Emitir Contrato."""
    return {"mensagem": "Contrato emitido."}

# =====================================================================
# ROTAS: FINANCEIRO E RECIBOS
# =====================================================================
@app.get("/api/master/financeiro/graficos", dependencies=[Depends(verificar_token)])
def graficos_faturamento(periodo: str = "mes"):
    """Gráficos X,Y de faturamento (dia, semana, mês)."""
    return {"labels": ["Semana 1", "Semana 2", "Semana 3", "Semana 4"], "valores": [1500, 2300, 1800, 3100]}

@app.get("/api/master/financeiro/notificacoes", dependencies=[Depends(verificar_token)])
def notificacoes_inadimplencia():
    """Gráficos X,Y de notificações (vencer, vencidos, bloqueados)."""
    return {"a_vencer": 12, "vencidos": 5, "bloqueados": 2}

@app.get("/api/master/financeiro/lista", dependencies=[Depends(verificar_token)])
def financeiro_lista(busca: str = ""):
    """Sistema de busca avançado na lista financeira."""
    # Retornando dados fictícios para testar a aba financeira
    lista_mock = [
        {"id": 1, "nome": "Loja de Roupas Silva", "cnpj": "11.222.333/0001-44", "data_vencimento": "05/11/2026", "status": "ativo"},
        {"id": 2, "nome": "Eletrônicos Vigia", "cnpj": "55.666.777/0001-88", "data_vencimento": "10/10/2026", "status": "vencido"}
    ]
    return lista_mock

@app.put("/api/master/financeiro/status", dependencies=[Depends(verificar_token)])
def atualizar_status_financeiro(dados: StatusFinanceiroRequest):
    """Alterna manualmente o status e carimba, mantendo ativo até próxima data."""
    return {"mensagem": "Status financeiro atualizado."}

@app.post("/api/master/config/pix", dependencies=[Depends(verificar_token)])
async def configurar_pix(qr_code: UploadFile = File(...), chave_pix: str = Form(...)):
    """Upload da foto do PIX e armazenamento da chave para o app cliente."""
    return {"mensagem": "Configuração salva e visível no app do cliente."}

@app.post("/api/master/recibos", dependencies=[Depends(verificar_token)])
def gerar_comprovante(dados: ReciboRequest):
    """Gera comprovante PDF com info da empresa, competência e obs de termos."""
    return {"mensagem": "Comprovante carimbado e enviado."}
