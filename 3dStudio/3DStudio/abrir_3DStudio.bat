name: Build Windows EXE

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Instalar dependencias
        run: |
          pip install pyinstaller pillow numpy scipy
      - name: Gerar EXE
        run: |
          pyinstaller --onefile --windowed --name "3DStudio" app_corrigido.py
      - name: Upload EXE
        uses: actions/upload-artifact@v4
        with:
          name: 3DStudio-Windows
          path: dist/3DStudio.exe
          retention-days: 30
