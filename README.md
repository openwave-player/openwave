# 🌊 OpenWave

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![GTK](https://img.shields.io/badge/GTK-3.0-orange?style=for-the-badge&logo=gnome&logoColor=white)
![GStreamer](https://img.shields.io/badge/GStreamer-1.0-green?style=for-the-badge&logo=gstreamer&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

O **OpenWave** é um leitor de áudio minimalista, rápido e elegante para Linux. Desenvolvido em Python com GTK 3 e GStreamer, o projeto foi carinhosamente planeado e esculpido para se integrar perfeitamente com a estética e o ecossistema visual do tema **Mint-Y (Linux Mint)**, mantendo ao mesmo tempo a flexibilidade de respeitar o pacote de ícones padrão de qualquer distribuição.

---

## ✨ Funcionalidades

- 📁 **Gestão de Biblioteca:** Selecione uma pasta local e o OpenWave organiza automaticamente as suas faixas por ordem alfabética.
- 🔍 **Pesquisa Instantânea:** Filtre músicas instantaneamente por título ou artista enquanto digita.
- 📂 **Amplo Suporte de Formatos:** Reproduz nativamente `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, `.aac`, `.opus`, e muito mais através do motor GStreamer.
- ⭐ **Favoritos:** Marque as suas músicas preferidas com um único clique para acesso rápido.
- 🎶 **Playlists Personalizadas:** Crie e faça a gestão de listas de reprodução dinâmicas.
- 🎨 **Leitura de Metadados e Capas:** Extração automática de tags de áudio (título/artista) e exibição da capa do álbum integrada no ficheiro (*embedded art*).
- 🧠 **Persistência de Estado:** Lembra-se da sua última pasta aberta, das suas playlists e dos seus favoritos entre sessões.

---

## 🚀 Como Executar

### 1. Pré-requisitos (Dependências do Sistema)

Como o OpenWave utiliza a biblioteca gráfica nativa do sistema e o GStreamer, precisa de instalar as dependências de introspeção do PyGObject no seu sistema Linux.

**No Linux Mint / Ubuntu / Debian:**

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly

```

**No Arch Linux:**

```bash
sudo pacman -S python-gobject gtk3 gstreamer gst-plugins-good gst-plugins-ugly

```

### 2. Clonar e Executar

Clone este repositório para a sua máquina local e execute o ficheiro principal:

```bash
# Clonar o repositório
git clone [https://github.com/openwave-player/openwave.git](https://github.com/openwave-player/openwave.git)

# Entrar na pasta
cd openwave

# Executar a aplicação
python3 app.py

```

---

## ⚙️ Configuração e Armazenamento

Os dados de configuração da aplicação (playlists, caminho da biblioteca e favoritos) são guardados de forma limpa no diretório padrão do utilizador, seguindo as especificações XDG:

```text
~/.config/openwave/state.json

```

---

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** [Python](https://www.python.org/)
* **Interface Gráfica:** [PyGObject (GTK 3)](https://pygobject.readthedocs.io/)
* **Motor de Áudio:** [GStreamer](https://gstreamer.freedesktop.org/)
* **Formatação de Dados:** JSON para armazenamento leve de estado.

---

## 🤝 Créditos e Agradecimentos

O OpenWave orgulha-se de fazer parte e apoiar a comunidade de código aberto (*Open Source*):

* **Autor e Desenvolvedor Principal:** Mateus Calixto ([contato@mateuscalixto.com.br]())
* **Design de Ícones:** [GNOME Project](https://www.gnome.org/) (fornecimento dos ícones simbólicos padrão).
* **Inspiração Visual:** [Linux Mint Desktop Team](https://linuxmint.com/) pela criação do deslumbrante tema e paleta de cores do ecossistema *Mint-Y*, que serviu de fundação para o design minimalista desta aplicação.

---

## 📄 Licença

Este projeto está licenciado sob a Licença **MIT** - consulte o ficheiro [LICENSE](https://www.google.com/search?q=LICENSE) para obter mais detalhes.

```

### Dicas para o seu repositório:
1. **Adicione as imagens:** Quando tiver a interface pronta, tire uns *prints* (capturas de ecrã), coloque-os numa pasta chamada `screenshots` no seu repositório e substitua os links do `via.placeholder.com` pelos caminhos relativos (ex: `screenshots/biblioteca.png`).
2. **Ficheiro LICENSE:** Lembre-se de criar um ficheiro chamado `LICENSE` na raiz do GitHub e colar o texto padrão da licença MIT lá dentro, já que definiu isso no seu `Gtk.AboutDialog` e no README.

```
