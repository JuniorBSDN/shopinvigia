import os
import uuid
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client, Client

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
SENHA_MASTER_VERCEL = os.getenv("SENHA_MASTER")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("As variáveis SUPABASE_URL e SUPABASE_KEY devem estar configuradas no ambiente.")

# Cliente oficial do Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    """Valida a senha master diretamente contra a variável da Vercel."""
    if SENHA_MASTER_VERCEL and dados.senha_master == SENHA_MASTER_VERCEL:
        return {"mensagem": "Autenticado", "token": "token_master_producao_shopinvigia"}
    raise HTTPException(status_code=401, detail="Acesso Negado")

@app.get("/api/master/dashboard", dependencies=[Depends(verificar_token)])
def dashboard():
    """Consulta métricas reais de clientes e status direto no Supabase."""
    try:
        # Busca contagem de clientes vencidos no Supabase
        vencidos_res = supabase.table('clientes').select('id', count='exact').eq('status', 'vencido').execute()
        vencidos_count = vencidos_res.count or 0

        # Busca contagem de novos clientes no Supabase
        novos_res = supabase.table('clientes').select('id', count='exact').eq('status', 'novo').execute()
        novos_count = novos_res.count or 0

        # Busca total geral de clientes para estimativa de DB
        total_res = supabase.table('clientes').select('id', count='exact').execute()
        total_count = total_res.count or 0

        db_usado_estimado = min(500, max(10, total_count * 5))

        return {
            "db_usado": db_usado_estimado,
            "novos_clientes": novos_count,
            "vencidos": vencidos_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no Supabase: {str(e)}")

# =====================================================================
# ROTAS: CLIENTES EMPRESA (CONSULTAS REAIS SUPABASE)
# =====================================================================
@app.get("/api/master/clientes", dependencies=[Depends(verificar_token)])
def listar_clientes(busca: str = "", status: str = ""):
    """Busca registros reais na tabela 'clientes' do Supabase com filtros."""
    try:
        query = supabase.table('clientes').select('*')
        
        if busca:
            query = query.or_(f"nome.ilike.%{busca}%,cnpj.ilike.%{busca}%")
        if status:
            query = query.eq('status', status)

        res = query.order('id', desc=True).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar clientes no Supabase: {str(e)}")

@app.put("/api/master/clientes/{id_cliente}/toggle-status", dependencies=[Depends(verificar_token)])
def toggle_status(id_cliente: int):
    """Busca o cliente no Supabase, inverte o status (ativo/bloqueado) e atualiza."""
    try:
        res = supabase.table('clientes').select('status').eq('id', id_cliente).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        status_atual = res.data[0].get('status')
        novo_status = 'bloqueado' if status_atual == 'ativo' else 'ativo'

        supabase.table('clientes').update({'status': novo_status}).eq('id', id_cliente).execute()
        return {"mensagem": f"Status do cliente {id_cliente} alterado para {novo_status} no Supabase."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao alterar status no Supabase: {str(e)}")

@app.put("/api/master/clientes/{id_cliente}", dependencies=[Depends(verificar_token)])
def alterar_cliente(id_cliente: int, dados: ClienteAtualizarRequest):
    """Atualiza colunas do cliente diretamente na tabela 'clientes' do Supabase."""
    try:
        payload = {k: v for k, v in dados.dict().items() if v is not None}
        if payload:
            supabase.table('clientes').update(payload).eq('id', id_cliente).execute()
        return {"mensagem": "Dados do cliente atualizados com sucesso no Supabase."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar cliente no Supabase: {str(e)}")

@app.delete("/api/master/clientes/{id_cliente}", dependencies=[Depends(verificar_token)])
def excluir_cliente(id_cliente: int):
    """Exclui o registro da tabela 'clientes' no Supabase."""
    try:
        supabase.table('clientes').delete().eq('id', id_cliente).execute()
        return {"mensagem": f"Cliente {id_cliente} excluído do Supabase."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao excluir cliente no Supabase: {str(e)}")

@app.post("/api/master/clientes/{id_cliente}/contrato", dependencies=[Depends(verificar_token)])
def emitir_contrato(id_cliente: int):
    """Insere o contrato na tabela 'contratos' do Supabase."""
    try:
        res = supabase.table('clientes').select('id, nome').eq('id', id_cliente).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        supabase.table('contratos').insert({
            'cliente_id': id_cliente,
            'status': 'emitido',
            'detalhes': f"Contrato emitido para {res.data[0].get('nome')}"
        }).execute()

        return {"mensagem": f"Contrato do cliente {id_cliente} gravado no Supabase."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao emitir contrato no Supabase: {str(e)}")

# =====================================================================
# ROTAS: FINANCEIRO E RECIBOS (SUPABASE REAL)
# =====================================================================
@app.get("/api/master/financeiro/graficos", dependencies=[Depends(verificar_token)])
def graficos_faturamento(periodo: str = "mes"):
    """Consulta os dados de faturamento na tabela 'faturamentos' do Supabase."""
    try:
        res = supabase.table('faturamentos').select('label, valor').order('id', desc=False).execute()
        if res.data:
            labels = [item.get('label', '') for item in res.data]
            valores = [float(item.get('valor', 0)) for item in res.data]
        else:
            labels = []
            valores = []
        return {"labels": labels, "valores": valores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar faturamento no Supabase: {str(e)}")

@app.get("/api/master/financeiro/notificacoes", dependencies=[Depends(verificar_token)])
def notificacoes_inadimplencia():
    """Contagem dinâmica de adimplência/inadimplência na tabela 'clientes' do Supabase."""
    try:
        a_vencer = supabase.table('clientes').select('id', count='exact').eq('status', 'a_vencer').execute().count or 0
        vencidos = supabase.table('clientes').select('id', count='exact').eq('status', 'vencido').execute().count or 0
        bloqueados = supabase.table('clientes').select('id', count='exact').eq('status', 'bloqueado').execute().count or 0
        return {"a_vencer": a_vencer, "vencidos": vencidos, "bloqueados": bloqueados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar inadimplência no Supabase: {str(e)}")

@app.get("/api/master/financeiro/lista", dependencies=[Depends(verificar_token)])
def financeiro_lista(busca: str = ""):
    """Consulta a lista de cobranças/clientes diretamente na tabela 'clientes' do Supabase."""
    try:
        query = supabase.table('clientes').select('id, nome, cnpj, data_vencimento, status')
        if busca:
            query = query.or_(f"nome.ilike.%{busca}%,cnpj.ilike.%{busca}%")
        
        res = query.order('id', desc=True).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar financeiro no Supabase: {str(e)}")

@app.put("/api/master/financeiro/status", dependencies=[Depends(verificar_token)])
def atualizar_status_financeiro(dados: StatusFinanceiroRequest):
    """Atualiza o status financeiro do cliente na tabela 'clientes' do Supabase."""
    try:
        supabase.table('clientes').update({'status': dados.status}).eq('id', dados.id).execute()
        return {"mensagem": f"Status financeiro do cliente {dados.id} atualizado para {dados.status} no Supabase."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar status no Supabase: {str(e)}")

@app.post("/api/master/config/pix", dependencies=[Depends(verificar_token)])
async def configurar_pix(qr_code: UploadFile = File(...), chave_pix: str = Form(...)):
    """Faz upload da imagem do QR Code para o Bucket 'pix' do Supabase e salva a chave na tabela 'config_pagamento'."""
    try:
        foto_bytes = await qr_code.read()
        filename = f"qr_{uuid.uuid4()}.png"

        # Upload para o Supabase Storage (Bucket 'pix')
        try:
            supabase.storage.from_("pix").upload(filename, foto_bytes)
            public_url = supabase.storage.from_("pix").get_public_url(filename)
        except Exception:
            public_url = ""

        # Upsert na tabela 'config_pagamento'
        supabase.table('config_pagamento').upsert({'id': 1, 'chave_pix': chave_pix, 'qr_code_url': public_url}).execute()
        return {"mensagem": "Configuração PIX salva com sucesso no Supabase!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar PIX no Supabase: {str(e)}")

@app.post("/api/master/recibos", dependencies=[Depends(verificar_token)])
def gerar_comprovante(dados: ReciboRequest):
    """Insere o comprovante emitido na tabela 'recibos' do Supabase."""
    try:
        supabase.table('recibos').insert(dados.dict()).execute()
        return {"mensagem": "Comprovante gravado no Supabase com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gravar recibo no Supabase: {str(e)}")
