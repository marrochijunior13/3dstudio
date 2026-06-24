# 3D Studio — Build Windows EXE

Este repositório gera automaticamente o **3DStudio.exe** para Windows via GitHub Actions.

## Como usar

### 1. Criar repositório no GitHub
- Acesse [github.com/new](https://github.com/new)
- Crie um repositório (pode ser privado)

### 2. Enviar estes arquivos
```bash
git init
git add .
git commit -m "primeiro commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git push -u origin main
```

### 3. Baixar o EXE gerado
- Acesse a aba **Actions** no seu repositório
- Clique no workflow mais recente
- Baixe o arquivo **3DStudio-Windows** em **Artifacts**
- Extraia o ZIP e execute o `3DStudio.exe`

## Dependências incluídas no EXE
- Python 3.11
- Pillow (PIL)
- NumPy
- SciPy
- Tkinter (interface gráfica)
