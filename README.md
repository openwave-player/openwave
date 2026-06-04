# OpenWave

![Versão](https://img.shields.io/badge/versão-0.1.3-blue.svg)
![Licença](https://img.shields.io/badge/licença-MIT-green.svg)
![Plataforma](https://img.shields.io/badge/plataforma-Linux-lightgrey.svg)

**OpenWave** é um player de música para Linux desenvolvido em Python com GTK3. Ele foi desenhado com foco na simplicidade, leveza e planejado especialmente para harmonizar com a estética do tema **Mint-Y** (Linux Mint).

Gerencie sua biblioteca de áudio local com uma interface limpa, leitura inteligente de metadados e suporte nativo a playlists e favoritos.

---

## Recursos

* **Interface GTK3 Limpa:** Integração perfeita com ambientes desktop baseados em GTK (projetado com a estética Mint-Y em mente).
* **Leitura de Metadados:** Suporte avançado à leitura de tags de áudio e extração de capas embutidas usando o `mutagen` e `GStreamer`.
* **Gestão de Biblioteca:** Escaneamento automático de pastas, organização dinâmica por **Artistas** e **Álbuns**.
* **Playlists & Favoritos:** Crie playlists personalizadas e favorite suas faixas preferidas rapidamente.
* **Fila de Reprodução Inteligente:** Modo aleatório (shuffle), reprodução sequencial e histórico de faixas.
* **Atualização Automática:** Mecanismo integrado (`updater.py`) que verifica novas versões no GitHub e aplica atualizações sem complicações.
* **Instalador Gráfico Integrado:** Acompanha um assistente (`installer.py`) para instalação no perfil do usuário, criação de atalhos (`.desktop`) ou remoção completa.

## Formatos Suportados
O OpenWave suporta uma ampla variedade de formatos de áudio nativamente, incluindo:
`MP3`, `WAV`, `OGG`, `FLAC`, `M4A`, `AAC`, `OPUS`, `WMA`, `AIFF`, `ALAC`, `MP2`, `MKA`.

---

## Instalação

### Pré-requisitos
Certifique-se de ter o Python 3 instalado no seu sistema, juntamente com as bibliotecas GTK e GStreamer. Em distribuições baseadas em Debian/Ubuntu (como o Linux Mint), você pode instalar as dependências com:

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly python3-mutagen python3-pip

```

*(Nota: O instalador do OpenWave tentará instalar o `mutagen` via pip automaticamente caso ele não seja encontrado no sistema).*

### Instalando o OpenWave

O projeto conta com um assistente de instalação gráfico para facilitar o processo.

1. Clone o repositório:
```bash
git clone [https://github.com/openwave-player/openwave.git](https://github.com/openwave-player/openwave.git)
cd openwave

```


2. Execute o instalador:
```bash
python3 installer.py

```


3. Siga os passos na tela do assistente. Ele copiará os arquivos necessários para `~/.local/share/openwave` e criará um atalho no seu menu de aplicativos.

---

## Como Usar

* **Pelo Menu do Sistema:** Procure por "OpenWave" no seu menu de aplicativos e inicie por lá.
* **Via Terminal:** Se preferir rodar direto pelo terminal após instalar:
```bash
python3 ~/.local/share/openwave/app.py

```


* **Primeiro Acesso:** Ao abrir pela primeira vez, clique no ícone de pasta na barra superior para escolher o diretório onde suas músicas estão armazenadas. O OpenWave vai ler sua biblioteca automaticamente!

---

## Estrutura do Projeto

O código está organizado em uma arquitetura modular simples:

* `installer.py`: Assistente gráfico de instalação/desinstalação.
* `app.py`: Ponto de entrada do aplicativo (que se comunica com o script de atualização).
* `openwave/`:
* `window.py`: Interface principal, fluxo de telas e eventos.
* `player.py`: Encapsulamento do pipeline GStreamer (`playbin`).
* `ui_builder.py`: Fábrica de componentes visuais e CSS customizado.
* `utils.py`: Leitura de arquivos e extração de metadados.
* `updater.py`: Checagem e download assíncrono de atualizações.
* `dialogs.py`: Telas de diálogo (Sobre, Criação de Playlists).



---

## Contribuindo

Se você encontrou um bug ou tem uma ideia de nova funcionalidade:

1. Faça um *fork* do projeto.
2. Crie uma *branch* para sua modificação (`git checkout -b feature/minha-feature`).
3. Faça o commit das suas alterações (`git commit -m 'Adicionando nova feature'`).
4. Faça um *push* para a branch (`git push origin feature/minha-feature`).
5. Abra um **Pull Request**.

---

# Licença

Este projeto é distribuído sob a Licença **MIT**. Veja o arquivo `LICENSE` (ou o cabeçalho do código) para mais detalhes.

---

## Autor

**Mateus Calixto**

* Contato: contato@mateuscalixto.com.br
* GitHub: [openwave-player](https://github.com/openwave-player/openwave)

*Inspiração visual: Linux Mint Desktop Team.*
*Ícones Simbólicos: GNOME Project.*

---

## Screenshots
![screenshots/Captura de tela de 2026-06-04 12-40-33.png](https://raw.githubusercontent.com/openwave-player/openwave/refs/heads/main/screenshots/Captura%20de%20tela%20de%202026-06-04%2012-40-33.png)
![screenshots/Captura de tela de 2026-06-04 12-40-57.png](https://raw.githubusercontent.com/openwave-player/openwave/refs/heads/main/screenshots/Captura%20de%20tela%20de%202026-06-04%2012-40-57.png)
![screenshots/Captura de tela de 2026-06-04 12-40-46.png](https://raw.githubusercontent.com/openwave-player/openwave/refs/heads/main/screenshots/Captura%20de%20tela%20de%202026-06-04%2012-40-46.png)
