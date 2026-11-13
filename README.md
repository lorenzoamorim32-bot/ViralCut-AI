# ViralCut AI — versão com link do YouTube

## O que esta versão faz
- Recebe links de vídeos individuais do YouTube (não playlists).
- Baixa/processa o vídeo no servidor usando yt-dlp.
- Transcreve a fala com faster-whisper.
- Sugere trechos por uma pontuação heurística baseada na transcrição.
- Permite revisar e selecionar os trechos antes da exportação.
- Exporta os cortes em MP4 vertical 9:16 e entrega um ZIP.

## Importante
Use apenas vídeos que você possui ou para os quais tenha autorização para baixar, processar e reutilizar. O acesso e processamento de vídeos do YouTube pode estar sujeito aos Termos de Serviço do YouTube e aos direitos autorais. A ferramenta não remove restrições, DRM, vídeos privados ou paywalls.

A pontuação não prevê viralização. É uma heurística inicial. O enquadramento é central, sem rastreamento de rosto/objeto, então revise os resultados.

## Executar em um servidor com Docker
O Docker precisa estar no servidor que hospeda o site; não é necessário instalar Docker no computador de quem acessa o site.
1. Instale Docker Engine/Compose no servidor.
2. Envie esta pasta ao servidor.
3. Na pasta do projeto, execute `docker compose up --build -d`.
4. Configure domínio, HTTPS, firewall e limite de tamanho/duração para produção.
5. Acesse `http://IP-DO-SERVIDOR:8000` para teste.

## Teste local (opcional)
Com Docker Desktop funcionando, abra PowerShell na pasta que contém `docker-compose.yml` e execute `docker compose up --build`. Depois acesse http://localhost:8000.

## Limitações desta versão
- Processamento em CPU pode ser lento; o modelo Whisper é baixado na primeira análise.
- A memória dos trabalhos é temporária; reiniciar o serviço apaga o histórico dos jobs.
- Para uso público, implemente autenticação, fila de tarefas, limpeza automática de arquivos, limites de duração/tamanho, armazenamento persistente e monitoramento.
- A hospedagem deve permitir FFmpeg, downloads de vídeo e armazenamento temporário suficiente.
