# Extract Tool

Ferramenta de linha de comando para **descompactar** arquivos ZIP e RAR, reunir o conteúdo e **mover apenas fontes `.ttf`** para uma pasta de destino escolhida.

---

## Requisitos

- [uv](https://docs.astral.sh/uv/) instalado
- `unrar` instalado no sistema (necessário para arquivos RAR):
  ```bash
  # Arch Linux
  sudo pacman -S unrar

  # Debian/Ubuntu
  sudo apt install unrar
  ```

---

## Instalação e configuração

```bash
# Instalar as dependências com uv
uv sync
```

---

## Uso

```bash
uv run extract-tool run <ORIGEM> <DESTINO> [OPÇÕES]
```

| Argumento / Opção | Descrição |
|---|---|
| `ORIGEM` | Pasta que contém os arquivos ZIP/RAR |
| `DESTINO` | Pasta onde os `.ttf` serão guardados |
| `--work-dir PATH` | Pasta intermédia de extração (padrão: `<origem>/_extracted_tmp`) |
| `--keep-work` | Mantém a pasta de trabalho após a execução |
| `--dry-run` | Simula as operações sem mover nenhum ficheiro |

---

## Exemplos

```bash
# Extrair ZIPs/RARs de ./downloads e mover TTFs para ./fontes
uv run extract-tool run ./downloads ./fontes

# Ver o que seria feito sem mover nada
uv run extract-tool run ./downloads ./fontes --dry-run

# Manter a pasta de trabalho (útil para inspecionar o conteúdo extraído)
uv run extract-tool run ./downloads ./fontes --keep-work

# Usar uma pasta intermédia personalizada
uv run extract-tool run ./downloads ./fontes --work-dir /tmp/extracao
```

---

## Fluxo de funcionamento

```
ORIGEM/
├── pack1.zip  ┐
├── pack2.rar  ┤──► descompactar ──► reunir todos os ficheiros
└── pack3.zip  ┘                          │
                                          ▼
                               filtrar apenas .ttf
                                          │
                                          ▼
                                     DESTINO/
                                     ├── FonteA.ttf
                                     ├── FonteB.ttf
                                     └── FonteC.ttf
```

1. **Localiza** todos os `.zip` e `.rar` na pasta `ORIGEM`
2. **Extrai** cada arquivo para uma subpasta dentro da pasta de trabalho
3. **Reúne** todos os ficheiros extraídos numa lista plana
4. **Move** apenas os ficheiros `.ttf` para `DESTINO`
5. **Limpa** a pasta de trabalho (a menos que `--keep-work` seja usado)
