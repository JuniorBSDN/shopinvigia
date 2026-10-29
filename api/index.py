import os
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictConnection
from psycopg2 import pool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ================= VARIÁVEIS DE AMBIENTE VERCEL ================
SENHA_MASTER = os.getenv("SENHA_MASTER", "admin123")
DATABASE_URL = os.getenv("DB_SHOP")

app = FastAPI(title="ShopinVigia - API Integrada (Master & Admin)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CONEXÃO BLINDADA SUPABASE ================
db_pool = None


def get_db():
    global db_pool
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="FALHA GRAVE: DATASHOP_URL não configurada.")
    if not db_pool:
        try:
            db_pool = pool.ThreadedConnectionPool(1, 10, dsn=DATABASE_URL, connection_factory=RealDictConnection)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro de conexão com DB: {str(e)}")

    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


# ================= MODELOS PYDANTIC =================
class MasterLogin(BaseModel):
    senha_master: str


class AdminLogin(BaseModel):
    cnpj: str


class AdminRegister(BaseModel):
    nome_loja: str
    cnpj: str
    whatsapp: str
    email: str


class UpdateStatus(BaseModel):
    id: int
    status: str


# ================= SEGURANÇA MASTER =================
security = HTTPBearer()


def verificar_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != "token_secreto_master_shopinvigia":
        raise HTTPException(status_code=401, detail="Sessão Inválida")
    return credentials.credentials


# ================= ROTAS DO ADMIN / GESTOR =================

@app.post("/api/admin/register")
def cadastrar_empresa(dados: AdminRegister, db=Depends(get_db)):
    cursor = db.cursor()
    try:
        # Verifica se CNPJ já existe
        cursor.execute("SELECT id FROM empresas WHERE cnpj = %s", (dados.cnpj,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="CNPJ já cadastrado no sistema.")

        # Regra do Escopo: 1 Semana Grátis
        vencimento = datetime.now() + timedelta(days=7)

        query = """
            INSERT INTO empresas (nome_fantasia, cnpj, whatsapp, email, status, vencimento) 
            VALUES (%s, %s, %s, %s, 'ativo', %s) RETURNING id
        """
        cursor.execute(query, (dados.nome_loja, dados.cnpj, dados.whatsapp, dados.email, vencimento))
        db.commit()
        return {"sucesso": True, "mensagem": "Conta criada com 1 semana gratuita."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()


@app.post("/api/admin/login")
def login_admin(dados: AdminLogin, db=Depends(get_db)):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, nome_fantasia, status FROM empresas WHERE cnpj = %s", (dados.cnpj,))
        empresa = cursor.fetchone()

        if not empresa:
            raise HTTPException(status_code=404, detail="CNPJ não encontrado.")

        # Se estiver bloqueado ou vencido, envia a flag para o frontend acionar o Modal do PIX
        if empresa['status'] in ['bloqueado', 'vencido']:
            return {"sucesso": False, "status": empresa['status'], "mensagem": "Acesso Bloqueado."}

        return {"sucesso": True, "token": f"token_admin_{empresa['id']}", "status": "ativo"}
    finally:
        cursor.close()


# ================= ROTAS DO MASTER (SAAS) =================

@app.post("/api/master/login")
def login_master(data: MasterLogin):
    if data.senha_master.strip() == SENHA_MASTER.strip():
        return {"token": "token_secreto_master_shopinvigia"}
    raise HTTPException(status_code=401, detail="Senha incorreta")


@app.get("/api/master/dashboard")
def master_dashboard(db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as total FROM empresas WHERE status = 'vencido'")
        vencidos = cursor.fetchone()['total']
        return {"db_usado": 22, "novos_clientes": 1, "vencidos": vencidos}
    finally:
        cursor.close()


@app.get("/api/master/clientes")
def master_clientes(busca: str = "", status: str = "", db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        query = "SELECT id, nome_fantasia as nome, cnpj, status, to_char(created_at, 'DD/MM/YYYY') as data_cadastro FROM empresas WHERE 1=1"
        params = []
        if busca:
            query += " AND (nome_fantasia ILIKE %s OR cnpj ILIKE %s)"
            params.extend([f"%{busca}%", f"%{busca}%"])
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY id DESC"

        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()


@app.put("/api/master/clientes/{id}/toggle")
def master_toggle_status(id: int, db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        cursor.execute("SELECT status FROM empresas WHERE id = %s", (id,))
        empresa = cursor.fetchone()
        if not empresa:
            raise HTTPException(status_code=404)

        novo_status = 'bloqueado' if empresa['status'] == 'ativo' else 'ativo'
        cursor.execute("UPDATE empresas SET status = %s WHERE id = %s", (novo_status, id))
        db.commit()
        return {"sucesso": True, "novo_status": novo_status}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()


@app.delete("/api/master/clientes/{id}")
def master_delete_cliente(id: int, db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM empresas WHERE id = %s", (id,))
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()


@app.get("/api/master/financeiro/lista")
def master_financeiro_lista(busca: str = "", db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        query = "SELECT id, nome_fantasia as nome, cnpj, status, to_char(vencimento, 'DD/MM/YYYY') as data_vencimento FROM empresas WHERE 1=1"
        params = []
        if busca:
            query += " AND nome_fantasia ILIKE %s"
            params.append(f"%{busca}%")
        cursor.execute(query, tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()


@app.put("/api/master/financeiro/status")
def master_financeiro_status(data: UpdateStatus, db=Depends(get_db), token: str = Depends(verificar_token)):
    cursor = db.cursor()
    try:
        if data.status == 'ativo':
            # Se for ativado no financeiro, joga o vencimento para 1 mês a frente (Carimbo)
            cursor.execute(
                "UPDATE empresas SET status = %s, vencimento = CURRENT_TIMESTAMP + INTERVAL '1 month' WHERE id = %s",
                (data.status, data.id))
        else:
            cursor.execute("UPDATE empresas SET status = %s WHERE id = %s", (data.status, data.id))
        db.commit()
        return {"sucesso": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
