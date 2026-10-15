import os
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# from supabase import create_client, Client # (Descomente quando for conectar o banco real)

app = FastAPI(title="ShopinVigia API - Módulo Master")

# Configuração de CORS (Essencial para comunicação Frontend <-> Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Na produção, coloque a URL do seu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# CONFIGURAÇÕES DE AMBIENTE (VERCEL & SUPABASE)
# =====================================================================
# Senha exclusiva do dono saas, armazenada em uma variável do ambiente Vercel
SENHA_MASTER_REAL = os.getenv("SENHA_MASTER", "senha_padrao_local") 

# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================================
# MODELOS DE DADOS (Pydantic)
# =====================================================================
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

# =====================================================================
# DEPENDÊNCIA DE AUTENTICAÇÃO (Protege as rotas do Master)
# =====================================================================
def verificar_token_master(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou inválido")
    
    token = authorization.split(" ")[1]
    # Aqui você validaria o token real. Como é um master único, validamos um token fixo de sessão
    if token != "token_master_shopinvigia_secreto":
        raise HTTPException(status_code=401, detail="Sessão expirada ou inválida")
    return True

# =====================================================================
# ROTAS DO MÓDULO MASTER
# =====================================================================

@app.post("/api/master/login")
def login_master(dados: LoginRequest):
    """Valida a senha do prompt JS com a variável do Vercel."""
    if dados.senha_master == SENHA_MASTER_REAL:
        return {
            "mensagem": "Autenticado com sucesso", 
            "token": "token_master_shopinvigia_secreto" # Token retornado para o JS usar nas próximas requisições
        }
    raise HTTPException(status_code=401, detail="Acesso Negado: Chave de Segurança Incorreta.")


@app.get("/api/master/dashboard", dependencies=[Depends(verificar_token_master)])
def get_dashboard():
    """Retorna os indicadores da tela principal do Master."""
    # Exemplo de consulta futura no Supabase:
    # response = supabase.table('clientes').select('id', count='exact').execute()
    
    return {
        "db_usado": 120.5, # Em MB (Simulação do limite de 500MB)
        "novos_clientes": 2,
        "vencidos": 5
    }


@app.get("/api/master/clientes", dependencies=[Depends(verificar_token_master)])
def listar_clientes(busca: str = "", status: str = ""):
    """Retorna a lista de clientes/empresas cadastrados no SaaS."""
    # Exemplo de consulta Supabase:
    # query = supabase.table('clientes').select('*')
    # if status: query = query.eq('status', status)
    # clientes = query.execute().data
    
    # Dados mockados temporários para espelhar a UI até o DB estar populado
    clientes = [
        {"id": 1, "data_cadastro": "15/10/2026", "nome": "Supermercado Silva", "status": "ativo"},
        {"id": 2, "data_cadastro": "01/10/2026", "nome": "Boutique da Moda", "status": "bloqueado"},
    ]
    return clientes


@app.put("/api/master/clientes/{id_cliente}/toggle-status", dependencies=[Depends(verificar_token_master)])
def toggle_status_cliente(id_cliente: int):
    """Alterna o status do cliente (Ativo/Bloqueado) e dispara email."""
    # Logica de UPDATE no Supabase e envio de email de notificação
    # supabase.table('clientes').update({'status': 'bloqueado'}).eq('id', id_cliente).execute()
    return {"mensagem": f"Status do cliente {id_cliente} alterado. E-mail de notificação enviado."}


# --- FINANCEIRO ---

@app.get("/api/master/financeiro/graficos", dependencies=[Depends(verificar_token_master)])
def get_graficos_financeiros(periodo: str = "mes"):
    """Retorna dados para plotar os gráficos de faturamento (X,Y)."""
    return {
        "labels": ["01/10", "05/10", "10/10", "15/10"],
        "valores": [150.0, 300.0, 450.0, 200.0]
    }


@app.get("/api/master/financeiro/notificacoes", dependencies=[Depends(verificar_token_master)])
def get_notificacoes_financeiras():
    """Retorna dados de inadimplência."""
    return {"a_vencer": 12, "vencidos": 5, "bloqueados": 2}


@app.get("/api/master/financeiro/lista", dependencies=[Depends(verificar_token_master)])
def listar_financeiro(busca: str = ""):
    """Retorna a lista da aba Financeiro para geração de PDF e alteração de status."""
    return [
        {"id": 1, "nome": "Supermercado Silva", "cnpj": "00.000.000/0001-00", "data_vencimento": "10/11/2026", "status": "ativo"}
    ]


@app.put("/api/master/financeiro/status", dependencies=[Depends(verificar_token_master)])
def atualizar_status_financeiro(dados: StatusUpdateRequest):
    """Atualiza manualmente o status mantendo ativo até a próxima data de vencimento."""
    # supabase.table('clientes').update({'status': dados.status}).eq('id', dados.id).execute()
    return {"mensagem": "Status financeiro atualizado com sucesso."}


@app.post("/api/master/config/pix", dependencies=[Depends(verificar_token_master)])
async def configurar_pix(qr_code: UploadFile = File(...), chave_pix: str = Form(...)):
    """Recebe o upload da foto do PIX e a chave informada pelo Master."""
    # Aqui você faria o upload da imagem para o Storage do Supabase:
    # file_bytes = await qr_code.read()
    # supabase.storage.from_("pix_master").upload(f"qr_{uuid.uuid4()}.png", file_bytes)
    
    return {"mensagem": "Configuração PIX salva. Atualizada em tempo real para o app cliente."}


@app.post("/api/master/recibos", dependencies=[Depends(verificar_token_master)])
def gerar_recibo_pdf(dados: ReciboRequest):
    """Gera o carimbo/PDF de comprovante de pagamento para a aba do cliente."""
    # Aqui entra a lógica de salvar os dados do recibo no banco
    # supabase.table('recibos').insert({...}).execute()
    return {"mensagem": "PDF Gerado e carimbado com sucesso no painel do cliente."}
