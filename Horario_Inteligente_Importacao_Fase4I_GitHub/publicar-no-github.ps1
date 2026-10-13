# Horário Inteligente — Importação segura da Fase 4I para o GitHub
# Esta operação NÃO altera a main. Faz push somente na branch de desenvolvimento.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = "https://github.com/ahferreira01-del/horario-escolar.git"
$branch = "development/fase4i-homologacao"
$origem = Join-Path $PSScriptRoot "codigo"
$destino = Join-Path $PSScriptRoot "repositorio-github"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git nao encontrado. Instale o Git for Windows e execute novamente."
}
if (-not (Test-Path -LiteralPath $origem -PathType Container)) {
    throw "Pasta codigo/ nao encontrada. Extraia o ZIP inteiro antes de executar."
}
if (Test-Path -LiteralPath $destino) {
    throw "A pasta repositorio-github/ ja existe. Remova-a ou mova-a antes de repetir. Nenhum arquivo existente sera apagado."
}

# Uma segunda barreira contra arquivos locais indesejados.
$bloqueados = @(Get-ChildItem -LiteralPath $origem -Recurse -Force -File |
    Where-Object {
        $_.Name -match '^\.env($|\.(?!example$))' -or
        $_.Extension -in @(".sqlite", ".sqlite3", ".db", ".pem", ".p12", ".pfx", ".key") -or
        $_.FullName -match '[\\/](node_modules|__pycache__|\.next|\.git)[\\/]'
    })
if ($bloqueados.Count -gt 0) {
    $bloqueados | ForEach-Object { Write-Host ("BLOQUEADO: " + $_.FullName) }
    throw "Arquivos potencialmente sensiveis encontrados. Revise o pacote antes de publicar."
}

Write-Host "1/5 Clonando branch segura: $branch"
& git clone --single-branch --branch $branch $repo $destino
if ($LASTEXITCODE -ne 0) { throw "Falha ao clonar. Verifique internet e autenticacao no GitHub." }

Write-Host "2/5 Copiando fontes e configuracoes da Fase 4I"
Get-ChildItem -LiteralPath $origem -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destino -Force -Recurse
}

Write-Host "3/5 Conferindo branch e alteracoes"
$atual = (& git -C $destino branch --show-current).Trim()
if ($atual -ne $branch) { throw "Branch inesperada: $atual. Publicacao abortada." }
& git -C $destino add -A
if ($LASTEXITCODE -ne 0) { throw "Erro ao preparar arquivos." }
& git -C $destino diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Foram encontrados problemas no diff. Revise antes de publicar." }
& git -C $destino diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw "Falha ao revisar diff." }

$alteracoes = & git -C $destino diff --cached --name-only
if (-not $alteracoes) {
    Write-Host "Nenhuma alteracao nova. A branch pode ja conter esta versao."
    exit 0
}
Write-Host ""
Write-Host "Destino: $repo"
Write-Host "Branch:  $branch"
Write-Host "ATENCAO: o repositorio GitHub esta PUBLICO. Confirme que o codigo pode ser publicado."
$resposta = Read-Host "Digite ENVIAR para confirmar o commit e o push"
if ($resposta -cne "ENVIAR") {
    Write-Host "Cancelado. Arquivos preparados apenas localmente em: $destino"
    exit 0
}

Write-Host "4/5 Gravando commit"
$nome = (& git -C $destino config user.name 2>$null)
$email = (& git -C $destino config user.email 2>$null)
if (-not $nome) { & git -C $destino config user.name "ahferreira01-del" }
if (-not $email) { & git -C $destino config user.email "262256958+ahferreira01-del@users.noreply.github.com" }
& git -C $destino commit -m "feat: importar aplicacao Horario Inteligente Fase 4I"
if ($LASTEXITCODE -ne 0) { throw "Falha no commit. Os arquivos permanecem no clone local." }

Write-Host "5/5 Enviando somente para a branch de desenvolvimento"
& git -C $destino push origin "HEAD:refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw "Falha no push. Corrija a autenticacao e repita o push dentro de repositorio-github/." }

Write-Host ""
Write-Host "Concluido. Verifique:"
Write-Host "https://github.com/ahferreira01-del/horario-escolar/pull/2"
Write-Host "https://github.com/ahferreira01-del/horario-escolar/actions"
Write-Host "Nao faca merge ate que os testes e a homologacao estejam aprovados."
