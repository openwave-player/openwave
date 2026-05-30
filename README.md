# 🌊 OpenWave

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![GTK](https://img.shields.io/badge/GTK-3.0-orange?style=for-the-badge&logo=gnome&logoColor=white)
![GStreamer](https://img.shields.io/badge/GStreamer-1.0-green?style=for-the-badge&logo=gstreamer&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

O **OpenWave** é um leitor de áudio minimalista, rápido e elegante para Linux. Desenvolvido em Python com GTK 3 e GStreamer, o projeto foi carinhosamente planeado e esculpido para se integrar perfeitamente com a estética e o ecossistema visual do tema **Mint-Y (Linux Mint)**, mantendo ao mesmo tempo a flexibilidade de respeitar o pacote de ícones padrão de qualquer distribuição.

---

## ✨ Funcionalidades

- 📁 **Gestão de Biblioteca:** Selecione uma pasta local e o OpenWave organiza e indexa automaticamente as suas faixas por ordem alfabética.
- 🔍 **Pesquisa Instantânea:** Filtre músicas instantaneamente por título, artista ou álbum enquanto digita, tanto na barra principal como no painel lateral de artistas.
- 🗂️ **Navegação Inteligente por Artista/Álbum:** Interface segmentada que gera índices dinâmicos para isolar álbuns e artistas sem poluir a sua lista de reprodução principal.
- ⭐ **Favoritos e Playlists:** Marque as suas faixas preferidas num clique e crie ou faça a gestão de playlists personalizadas diretamente através do menu contextual de botões.
- 📂 **Amplo Suporte de Formatos:** Graças à integração nativa com o GStreamer, o leitor reproduz ficheiros `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, `.aac`, `.opus`, `.wma`, `.aiff`, `.aif`, `.alac`, `.mp2` e `.mka`.
- 🖼️ **Leitura Automatizada de Metadados:** Extração e renderização inteligente de capas de álbuns incorporadas (tags APIC/id3/covr) e tags de texto via Mutagen.

---

## 🚀 Instalação e Execução

O projeto inclui um **Assistente Gráfico de Configuração** (`installer.py`) que facilita tanto a instalação inicial (com criação automática de atalhos e ficheiros `.desktop`) como a desinstalação completa do sistema do utilizador.

### Pré-requisitos (Ubuntu / Debian / Linux Mint)

Antes de executar, certifique-se de que tem instaladas as dependências do sistema para o PyGObject, GStreamer e a biblioteca de manipulação de metadados `mutagen`:

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly
pip install mutagen

```

### Clonar e Instalar

```bash
# Clonar o repositório
git clone [https://github.com/openwave-player/openwave.git](https://github.com/openwave-player/openwave.git)

# Entrar na pasta
cd openwave

# Executar o assistente gráfico de instalação
python3 installer.py

```

O assistente encarregar-se-á de copiar os ficheiros para a sua pasta local e disponibilizar o atalho no menu de aplicações do seu ambiente de desktop.

---

## ⚙️ Configuração e Armazenamento

Os dados de configuração da aplicação (playlists criadas, caminhos indexados da biblioteca, histórico de reprodução e favoritos) são guardados de forma limpa no diretório padrão do utilizador, seguindo estritamente as especificações XDG:

* **Ficheiro de Estado:** `~/.config/openwave/state.json`
* **Ficheiros Binários e de Dados:** `~/.local/share/openwave/`
* **Atalho de Desktop:** `~/.local/share/applications/openwave.desktop`

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** [Python](https://www.python.org/) (v3.10 ou superior)
* **Interface Gráfica:** [PyGObject (GTK 3)](https://pygobject.readthedocs.io/)
* **Motor de Áudio:** [GStreamer 1.0](https://gstreamer.freedesktop.org/) (através do pipeline `playbin`)
* **Leitura de Tags:** [Mutagen](https://mutagen.readthedocs.io/)
* **Formatação de Dados:** Armazenamento leve baseado em estruturas JSON.

---

## 🤝 Créditos e Agradecimentos

O OpenWave orgulha-se de fazer parte e apoiar a comunidade de código aberto (*Open Source*):

* **Autor e Desenvolvedor Principal:** [Mateus Calixto](https://mateuscalixto.com.br)
* **Design de Ícones:** [GNOME Project](https://www.gnome.org/) (fornecimento dos ícones simbólicos padrão utilizados na interface).
* **Inspiração Visual:** [Linux Mint Desktop Team](https://linuxmint.com/) pela criação do deslumbrante tema e paleta de cores do ecossistema *Mint-Y*, servindo de base estrutural para os estilos CSS personalizados injetados na aplicação.

---

## 📄 Licença

Este projeto está licenciado sob a **Licença MIT** - consulte o ficheiro de licença para mais detalhes.
