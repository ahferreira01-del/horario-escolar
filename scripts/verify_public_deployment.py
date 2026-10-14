#!/usr/bin/env python3
"""Verificação externa, somente LEITURA, de um deploy HTTPS.

Uso após configuração HI_RELEASE_SHA no provedor:
  python scripts/verify_public_deployment.py \
    --url https://horario-inteligente.replit.app --expected-sha <COMMIT_SHA>

Não cria usuário, não faz login e não altera dados. Falha fechado se o site
não responder, divulgar outro SHA, estiver sem readiness ou tiver resposta
imprópria. Não é substituto do E2E completo 4K nem de auditoria LGPD.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
from urllib import request, error, parse


def check(url: str, expected_sha: str, timeout: float = 8) -> list[str]:
    parsed = parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in ("", "/") or parsed.port not in (None, 443)):
        raise ValueError("Informe apenas a URL base HTTPS pública (sem credenciais ou caminhos).")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_sha):
        raise ValueError("O SHA esperado precisa ter 40 caracteres hexadecimais.")

    result=[]
    hostname=parsed.hostname.lower()
    base=url.rstrip("/")
    opener=request.build_opener(request.HTTPSHandler(context=ssl.create_default_context()))

    for endpoint in ("/api/release", "/api/health", "/api/ready"):
        try:
            req=request.Request(base+endpoint, headers={
                "Accept":"application/json",
                "User-Agent":"Horário-Inteligente-Release-Verify/1.0"})
            with opener.open(req, timeout=timeout) as response:
                resolved=parse.urlsplit(response.geturl())
                # Não enviar SHA ou outros dados a redirecionamentos inesperados.
                if resolved.scheme!="https" or resolved.hostname!=hostname:
                    result.append(f"{endpoint}: FAIL redirecionamento externo")
                    continue
                status=response.status
                content_type=response.headers.get("Content-Type","")
                raw=response.read(4096)
            if status != 200 or "application/json" not in content_type:
                result.append(f"{endpoint}: FAIL HTTP/Content-Type")
                continue
            payload=json.loads(raw)
            if endpoint=="/api/release":
                if (payload.get("release_identified") is not True or
                        payload.get("release_sha") != expected_sha.lower()):
                    result.append(f"{endpoint}: FAIL identidade divergente/ausente")
                else:
                    result.append(f"{endpoint}: PASS SHA {expected_sha[:12].lower()}")
            elif endpoint=="/api/health":
                result.append(f"{endpoint}: "+("PASS" if payload.get("status")=="ok" else "FAIL status"))
            else:
                result.append(f"{endpoint}: "+("PASS" if payload.get("status")=="ready" else "FAIL status"))
        except (error.HTTPError,error.URLError,ValueError,TimeoutError,json.JSONDecodeError) as exc:
            # Não imprimir URLs assinadas, stacktraces ou respostas internas.
            result.append(f"{endpoint}: FAIL indisponível/resposta inválida ({type(exc).__name__})")
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-sha",required=True)
    parser.add_argument("--timeout",type=float,default=8)
    args=parser.parse_args(argv)
    if args.timeout<=0 or args.timeout>30:
        parser.error("Timeout precisa estar entre 0 e 30 segundos.")
    try:
        verdicts=check(args.url,args.expected_sha,args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    print("\n".join(verdicts))
    if not verdicts or not all(": PASS" in v for v in verdicts):
        print("PUBLIC_DEPLOYMENT_NOT_VERIFIED — não autorizar produção por este resultado.")
        return 1
    print("PUBLIC_DEPLOYMENT_READONLY_PASS — ainda faltam 4K, segurança, backup e aceite.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
