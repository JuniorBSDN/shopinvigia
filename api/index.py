import os
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictConnection
from psycopg2 import pool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ================= VARIÁVEIS DE AMBIENTE (VERCEL / SUPABASE) =================
# Em produção (Vercel), essas variáveis serão injetadas automaticamente.
# Localmente, você pode criar um arquivo .env ou setar no seu terminal.
SENHA_MASTER = os.getenv("SENHA_MASTER", "admin123") # "admin123" é um fallback para teste local
DATABASE_URL = os.getenv("DATASHOP_URL") # String de conexão PostgreSQL fornecida pelo Supabase

# ================= INICIALIZAÇÃO DA APLICAÇÃO =================
app = FastAPI(
    title="ShopinVigia API - ERP Varejo",
    description="Backend consolidado para SaaS de Lojas de Roupas, Sapatos e Acessórios"
)

# Libera o CORS para o frontend (seu painel em HTML/JS) conseguir comunicar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CONEXÃO COM O BANCO DE DADOS (SUPABASE) =================
# Usamos Connection Pool para suportar múltiplos acessos simultâneos sem derrubar o banco
try:
    db_pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=DATABASE_URL,
        connection_factory=RealDictConnection
    )
    print("Conexão com o Supabase estabelecida com sucesso!")
except Exception as e:
    print(f"Aviso: Não foi possível conectar ao banco de dados no momento. Verifique a DATABASE_URL. Erro: {e}")
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
    # O painel Master envia o token no cabeçalho.
    # Em um cenário real, você gera um JWT. Aqui validamos a string fixa para o Super Admin.
    if credentials.credentials != "token_master_shopinvigia_super_admin":
        raise HTTPException(status_code=401, detail="Sessão Master Inválida ou Expirada")
    return credentials.credentials


# ================= MODELOS PYDANTIC (PAYLOADS) =================
class MasterAuth(BaseModel):
    senha: str

class EmpresaCreate(BaseModel):
    razao_social: str
    nome_fantasia: str
    cnpj: str
    telefone: str
    email_admin: str
    endereco: str


# ================= ROTAS DO MASTER =================

@app.post("/api/master/auth")
def master_login(auth: MasterAuth):
    # Pega a senha da Vercel ou usa "admin123" como fallback local para nunca travar
    senha_ambiente = os.getenv("SENHA_MASTER", "admin123")
    
    # Remove espaços em branco acidentais que venham do input ou da Vercel
    if auth.senha and auth.senha.strip() == senha_ambiente.strip():
        return {
            "autorizado": True, 
            "token": "token_master_shopinvigia_super_admin",
            "mensagem": "Bem-vindo, Mestre."
        }
    
    raise HTTPException(
        status_code=401, 
        detail="Senha Master incorreta."
    )
@app.get("/api/master/metrics")
def get_master_metrics(db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """
    Retorna os indicadores para o Dashboard do Master (Total de Lojas, Faturamento MRR).
    """
    cursor = db.cursor()
    try:
        # Conta empresas ativas
        cursor.execute("SELECT COUNT(*) as total FROM empresas WHERE status != 'excluido'")
        total_clientes = cursor.fetchone()['total']
        
        # Simula o MRR (Receita Recorrente) assumindo R$ 150 por cliente ativo
        cursor.execute("SELECT COUNT(*) as pagantes FROM empresas WHERE plano != 'Trial' AND status = 'ativo'")
        pagantes = cursor.fetchone()['pagantes']
        mrr = float(pagantes) * 150.00 
        
        return {
            "db_disk_usage": "18 MB", # Num cenário real, usaríamos pg_database_size()
            "total_clientes": total_clientes, 
            "mrr": f"R$ {mrr:,.2f}".replace('.', ',')
        }
    finally:
        cursor.close()


@app.get("/api/master/empresas")
def list_empresas(db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """
    Lista todos os clientes (lojistas) cadastrados no SaaS.
    """
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, razao_social, nome_fantasia, cnpj, plano, vencimento, status FROM empresas ORDER BY id DESC")
        res = cursor.fetchall()
        return res
    finally:
        cursor.close()


@app.post("/api/master/empresas")
def create_empresa(emp: EmpresaCreate, db=Depends(get_db), token: str = Depends(verificar_token_master)):
    """
    Cria uma nova loja manualmente via Painel Master.
    """
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO empresas (razao_social, nome_fantasia, cnpj, telefone, email_admin, endereco, plano, vencimento, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Trial', 5, 'ativo') RETURNING id;
        """, (emp.razao_social, emp.nome_fantasia, emp.cnpj, emp.telefone, emp.email_admin, emp.endereco))
        db.commit()
        novo_id = cursor.fetchone()['id']
        return {"mensagem": "Loja cadastrada com sucesso", "id": novo_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao cadastrar: {str(e)}")
    finally:
        cursor.close()

# Rota extra para simular se a API está online antes do banco estar configurado
@app.get("/ping")
def ping():
    return {"status": "ShopinVigia API Online", "environment": os.getenv("VERCEL_ENV", "local")}
