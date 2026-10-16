#!/usr/bin/env python3
"""Teste HTTP real do backend em SQLite efêmero. NÃO é homologação PostgreSQL.

Sobe uvicorn na máquina local, cria uma base descartável, testa autenticação,
convites, CSRF, unidades e isolamento por organização na camada de API.
Não expõe servidor publicamente nem grava credenciais no pacote.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT=Path(__file__).resolve().parent.parent
BACKEND=ROOT/'backend'
PASSWORD='Senha-Somente-Teste-123!'


def run(cmd, env, timeout=30):
    p=subprocess.run([sys.executable,*cmd],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError('Comando de preparação falhou: '+p.stderr[-1000:])


def client(base):
    opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(method,path,data=None,csrf=None):
        headers={'Accept':'application/json'}
        if data is not None: headers['Content-Type']='application/json'
        if csrf: headers['X-CSRF-Token']=csrf
        req=Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            with opener.open(req,timeout=10) as res:
                return res.status,json.loads(res.read())
        except HTTPError as e:
            try: payload=json.loads(e.read())
            except Exception: payload={}
            return e.code,payload
    return request


def expect(code,expected,label):
    if code!=expected:raise RuntimeError(f'{label}: HTTP {code}; esperado {expected}')


def smoke():
    with tempfile.TemporaryDirectory(prefix='horario-f4g-') as temporary:
        db=Path(temporary)/'smoke.sqlite'
        env=os.environ.copy()
        env.update({'DATABASE_URL':f'sqlite:///{db}', 'ENVIRONMENT':'development',
                    'SESSION_SECRET':secrets.token_urlsafe(48),'COOKIE_SECURE':'false',
                    'USER_PROVISIONING_MODE':'email',
                    'PYTHONPATH':str(BACKEND)})
        run(['-m','app.cli','init-db'],env)
        run(['-m','app.cli','bootstrap-platform','--email','root@example.com',
             '--name','Admin de Teste','--password',PASSWORD],env)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                                 cwd=BACKEND,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            root=client(base)
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError('Servidor encerrou inesperadamente.')
                try:
                    if root('GET','/api/health')[0]==200:break
                except (URLError,ConnectionError):pass
                time.sleep(.15)
            else:raise RuntimeError('Servidor não ficou pronto.')
            steps=[]
            expect(root('GET','/api/auth/me')[0],401,'sem login');steps.append('sem sessão: 401')
            code,login=root('POST','/api/auth/login',{'email':'root@example.com','password':PASSWORD})
            expect(code,200,'login plataforma');csrf=login['csrf'];steps.append('login plataforma: 200')
            code,tenant=root('POST','/api/platform/tenants',{'name':'Rede Teste A',
                'first_admin_name':'Diretor A','first_admin_email':'diretor-a@example.com'},csrf)
            expect(code,201,'criar organização A');tid=tenant['id']
            token=parse_qs(urlsplit(tenant['dev_invitation_url']).query)['token'][0]
            director=client(base)
            code,accept=director('POST','/api/auth/accept-invitation',{'tenant_id':tid,
                'token':token,'name':'Diretor A','password':PASSWORD})
            expect(code,200,'convite diretor');dcsrf=accept['csrf'];steps.append('convite por e-mail: aceito')
            expect(director('POST',f'/api/tenants/{tid}/schools',{'name':'Escola sem CSRF'})[0],403,'CSRF')
            code,school=director('POST',f'/api/tenants/{tid}/schools',{'name':'Escola Centro'},dcsrf)
            expect(code,201,'criar escola');steps.append('escola e CSRF: validados')
            code,tenant2=root('POST','/api/platform/tenants',{'name':'Rede Teste B',
                'first_admin_name':'Diretor B','first_admin_email':'diretor-b@example.com'},csrf)
            expect(code,201,'criar organização B');tid2=tenant2['id']
            token2=parse_qs(urlsplit(tenant2['dev_invitation_url']).query)['token'][0]
            other=client(base)
            code,accept2=other('POST','/api/auth/accept-invitation',{'tenant_id':tid2,
                'token':token2,'name':'Diretor B','password':PASSWORD})
            expect(code,200,'convite B')
            expect(other('GET',f'/api/tenants/{tid}/schools')[0],403,'isolamento entre organizações')
            expect(director('GET',f'/api/tenants/{tid2}/schools')[0],403,'isolamento reverso')
            steps.append('isolamento API entre duas organizações: 403 nos dois sentidos')
            expect(director('GET',f'/api/tenants/{tid}/schools')[0],200,'acesso permitido')
            steps.append('acesso à escola autorizada: 200')
            return {'status':'PASS','mode':'FastAPI HTTP real + SQLite efêmero; não prova RLS',
                    'checks':steps,'postgresql_verified':False,'frontend_verified':False}
        finally:
            process.terminate()
            try:process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate(timeout=5)


if __name__=='__main__':
    try:print(json.dumps(smoke(),ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'status':'FAIL','error':str(exc)},ensure_ascii=False,indent=2))
        sys.exit(1)
