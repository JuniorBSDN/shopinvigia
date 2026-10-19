import os
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictConnection
from psycopg2 import pool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta

# ================= VARIÁVEIS DE AMBIENTE (VERCEL / SUPABASE) =================
SENHA_MASTER = os.getenv("SENHA_MASTER", "admin123") 
DATABASE_URL = os.getenv("DATASHOP_URL") 

# ================= INICIALIZAÇÃO DA APLICAÇÃO =================
app = FastAPI(
    title="ShopinVigia API - ERP Varejo",
    description="Backend consolidado para SaaS Master"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CONEXÃO COM O BANCO DE DADOS =================
try:
    db_pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=DATABASE_URL,
        connection_factory=RealDictConnection
    )
    print("Conexão com o banco estabelecida com sucesso!")
except Exception as e:
    print(f"Aviso: Falha ao conectar no banco. Erro: {e}")
    db_pool = None

def get_db():
    if not db_pool:
        raise HTTPException(status_code=500, detail="Banco de dados não conectado.")
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)

# ================= TRAVAS DE SEGURANÇA =================
security = HTTPBearer()

def verificar_token_master(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != "token_master_shopinvigia_super_admin":
        raise HTTPException(status_code=401, detail="Sessão Master Inválida ou Expirada")
    return credentials.credentials

# ================= MODELOS PYDANTIC (PAYLOADS) =================
class MasterAuth(BaseModel):
    senha: str

class LojistaCadastro(BaseModel):
    nome_fantasia: str
    cnpj: str
    email: str
    telefone: str
    senha: str
    razao_social: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

class ConfigPixUpdate(BaseModel):
    qrcode_imagens: str
    copia_e_cola: str

# ================= ROTAS DE AUTENTICAÇÃO E MÉTRICAS =================
@app.post("/api/master/auth")
def master_login(auth: MasterAuth):
    senha_ambiente = os.getenv("SENHA_MASTER", "admin123")
    if auth.senha and auth.senha.strip() == senha_ambiente.strip():
        return {
            "autorizado": True, 
            "token": "token_master_shopinvigia_super_admin",
            "mensagem": "Bem-vindo, Mestre."
        }
    raise HTTPException(status_code=401, detail="Senha Master incorreta.")

@app.get("/api/master/metrics")
def get_master_metrics(db=Depends(get_db), token: str = Depends(verificar_token_master)):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as total FROM empresas WHERE status != 'excluido'")
        total_clientes = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as pagantes FROM empresas WHERE plano != 'Trial' AND status = 'ativo'")
        pagantes = cursor.fetchone()['pagantes']
        mrr = float(pagantes) * 150.00 
        
        return {
            "db_disk_usage": "18 MB", 
            "total_clientes": total_clientes, 
            "mrr": f"R$ {mrr:,.2f}".replace('.', ',')
        }
    finally:
        cursor.close()

# ================= ROTAS DE GESTÃO DE EMPRESAS (MASTER.HTML) =================
@app.get("/api/master/empresas")
def list_empresas(db=Depends(get_db), token: str = Depends(verificar_token_master)):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, razao_social, nome_fantasia, cnpj, telefone, plano, vencimento, status, created_at FROM empresas ORDER BY id DESC")
        return cursor.fetchall()
    finally:
        cursor.close()

@app.put("/api/master/empresas/{empresa_id}")
def update_status_empresa(empresa_id: int, payload: StatusUpdate, db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """Rota chamada pelo 'Ativar/Bloq' e pelo select financeiro no master.html"""
    cursor = db.cursor()
    try:
        # Se for ativado manualmente, o master renova o vencimento para +30 dias
        vencimento_query = ", vencimento = CURRENT_DATE + INTERVAL '30 days'" if payload.status == "ativo" else ""
        
        query = f"UPDATE empresas SET status = %s {vencimento_query} WHERE id = %s RETURNING id, status, vencimento"
        cursor.execute(query, (payload.status, empresa_id))
        db.commit()
        atualizado = cursor.fetchone()
        
        if not atualizado:
            raise HTTPException(status_code=404, detail="Empresa não encontrada.")
            
        return {"sucesso": True, "mensagem": "Status atualizado.", "dados": atualizado}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()

@app.delete("/api/master/empresas/{empresa_id}")
def delete_empresa(empresa_id: int, db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """Rota chamada pelo botão de lixeira no master.html"""
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM empresas WHERE id = %s RETURNING id", (empresa_id,))
        db.commit()
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Empresa não encontrada.")
        return {"sucesso": True, "mensagem": "Empresa excluída permanentemente."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()

# ================= ROTA DE CONFIGURAÇÃO GLOBAL (PIX) =================
@app.put("/api/master/config-pix")
def update_config_pix(payload: ConfigPixUpdate, db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """Rota chamada pelo botão 'Salvar Configuração PIX' no master.html"""
    cursor = db.cursor()
    try:
        # Assumindo que existe uma tabela "configuracoes" com id=1 para armazenar as globais do sistema
        cursor.execute("""
            UPDATE configuracoes 
            SET pix_qrcode = %s, pix_chave = %s 
            WHERE id = 1 RETURNING id
        """, (payload.qrcode_imagens, payload.copia_e_cola))
        
        # Se a tabela estiver vazia, faz um insert
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO configuracoes (id, pix_qrcode, pix_chave) 
                VALUES (1, %s, %s)
            """, (payload.qrcode_imagens, payload.copia_e_cola))
            
        db.commit()
        return {"sucesso": True, "mensagem": "Configurações PIX atualizadas."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()

# ================= ROTA DE AUTO-CADASTRO (ADMIN.HTML) =================
@app.post("/api/empresas/cadastro", status_code=201)
def cadastrar_lojista_trial(data: LojistaCadastro, db=Depends(get_db)):
    """Criada em 100% FastAPI: Gera vencimento automático de +7 dias"""
    vencimento = datetime.now() + timedelta(days=7)
    razao = data.razao_social if data.razao_social else data.nome_fantasia

    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO empresas (razao_social, nome_fantasia, cnpj, telefone, email_admin, senha, status, plano, vencimento)
            VALUES (%s, %s, %s, %s, %s, %s, 'ativo', 'Trial', %s) RETURNING id;
        """, (razao, data.nome_fantasia, data.cnpj, data.telefone, data.email, data.senha, vencimento))
        db.commit()
        novo_id = cursor.fetchone()['id']
        return {
            "sucesso": True, 
            "mensagem": "Conta criada com 7 dias de teste grátis!", 
            "id": novo_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao cadastrar: {str(e)}")
    finally:
        cursor.close()

# ================= HEALTH CHECK =================
@app.get("/ping")
def ping():
    return {"status": "ShopinVigia API Online", "environment": os.getenv("VERCEL_ENV", "local")}
