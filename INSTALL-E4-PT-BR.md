# Guia de instalação — WhateverXe Enhanced E4 (0.8.5) | PT-BR

> Pré-release experimental. A CI não comprova aceleração em hardware real. Use uma EFI de teste em pendrive, mantenha a EFI funcional original e um backup dos dados. Este guia complementa uma EFI OpenCore que já inicializa o macOS; não é uma EFI universal.

## 1. Requisitos e downloads

- [WhateverXe Enhanced E4](https://github.com/rodrigosalesf/WhateverXe-Enhanced/releases/tag/v0.8.5-enhanced-e4): use o ZIP RELEASE; DEBUG apenas para investigação. Extraia `WhateverXe.kext`, não o dSYM.
- [Lilu 1.7.2 ou superior compatível](https://github.com/acidanthera/Lilu/releases).
- [AMFIAnchor e AMFIAnchorInjector](https://github.com/b00t0x/AMFIAnchor#install-with-opencore): use o build e o injector oficial correspondente à CA do Graphics.
- [WhateverXe Graphics 0.4.5](https://github.com/b00t0x/WhateverXe-Graphics/releases/tag/v0.4.5): pacote instalado no macOS, não na EFI. Não misture versões sem verificar compatibilidade.
- OpenCore e ocvalidate da mesma versão, e um editor de plist (por exemplo, [ProperTree](https://github.com/corpnewt/ProperTree)).

GPU Intel Xe-LP com PCI ID contemplado na [lista de dispositivos](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/c24d6d8bc8e3b98977eab4e146c8d26463a0d338/docs/device-selection.md). Backend implementado não significa que todas as portas e painéis foram validados. Para o Acer Aspire A515-57/i5-12450H, confirme o PCI ID real e DVMT; tela interna Alder Lake-H de 48 EUs ainda não foi validada nesta Enhanced.

| macOS | Versão exigida pela base 0.8.5 |
| --- | --- |
| Big Sur | 11.7.11 |
| Monterey | 12.7.6 |
| Ventura | 13.7.8 |
| Sonoma | 14.8.9 |
| Sequoia | 15.8.x |
| Tahoe | 26.7 ou posterior compatível |

## 2. Arquivos na EFI

```text
EFI/
  OC/
    ACPI/
      SSDT-PNLF.aml       # opcional, para brilho do painel interno
    Kexts/
      Lilu.kext
      AMFIAnchor.kext
      AMFIAnchorInjector.kext
      WhateverXe.kext
    config.plist
```

Preserve as demais kexts e SSDTs necessárias ao seu computador. Desative a entrada de WhateverGreen.kext e a de AMFIPass 1.4.1 Mod antiga, se presentes; não carregue as duas alternativas gráficas. AMFI deve permanecer habilitado. Caso use OCLP para outros patches, siga as instruções do AMFIAnchor para AMFIPass oficial após o anchor e o injector.

## 3. config.plist — Kernel > Add

Adicione/atualize as entradas sem duplicar Lilu. Ordem relativa abaixo (outras kexts mantêm suas dependências).

| BundlePath (String) | ExecutablePath (String) | PlistPath (String) | Enabled (Boolean) |
| --- | --- | --- | --- |
| Lilu.kext | Contents/MacOS/Lilu | Contents/Info.plist | True |
| AMFIAnchor.kext | Contents/MacOS/AMFIAnchor | Contents/Info.plist | True |
| AMFIAnchorInjector.kext | **vazio** | Contents/Info.plist | True |
| WhateverXe.kext | Contents/MacOS/WhateverXe | Contents/Info.plist | True |

Para cada entrada, os campos adicionais do OpenCore são Arch (String, Any), Comment (String, livre), MinKernel e MaxKernel (String). Para AMFIAnchor e injector: MinKernel **20.0.0**, MaxKernel **25.99.99** conforme documentação oficial (Darwin 20–25). Para WhateverXe, a mesma faixa é uma delimitação recomendada para este guia, não requisito novo da Enhanced. Preserve a faixa compatível da entrada Lilu existente; se nova, pode usar 20.0.0–25.99.99 nesta EFI destinada aos sistemas acima. Injector é codeless: ExecutablePath deve ser string vazia, nunca um executável inventado.

Exemplo de uma entrada XML a inserir dentro do array Kernel > Add (não substitua o array inteiro):
```xml
<dict>
    <key>Arch</key><string>Any</string>
    <key>BundlePath</key><string>WhateverXe.kext</string>
    <key>Comment</key><string>WhateverXe Enhanced E4</string>
    <key>Enabled</key><true/>
    <key>ExecutablePath</key><string>Contents/MacOS/WhateverXe</string>
    <key>MaxKernel</key><string>25.99.99</string>
    <key>MinKernel</key><string>20.0.0</string>
    <key>PlistPath</key><string>Contents/Info.plist</string>
</dict>
```

## 4. config.plist — NVRAM > Add

GUID: `7C436110-AB2A-4BBB-A880-FE41995C9F82`.

| Chave | Tipo | Valor |
| --- | --- | --- |
| boot-args | String | -allow3d -disablegfxfirmware |
| csr-active-config | Data | 03080000 |

Acrescente os argumentos aos necessários para sua EFI, sem sobrescrever os demais. Remova argumentos antigos que desabilitem AMFI (por exemplo amfi=0x80) e ipc_control_port_options=0 se utilizados apenas para a antiga pilha gráfica. O valor SIP 0x803 reduz proteções do sistema: avalie o risco e use apenas componentes de confiança. Não desative AMFI globalmente.

Exemplo XML das duas propriedades dentro do dicionário do GUID:
```xml
<key>boot-args</key>
<string>-allow3d -disablegfxfirmware</string>
<key>csr-active-config</key>
<data>AwgAAA==</data>
```

ProperTree exibe Data em hexadecimal; XML plist usa Base64. Se valores antigos persistirem, faça backup e use Reset NVRAM pelo OpenCore (isso pode remover entradas de boot e outras variáveis), ou configure NVRAM > Delete para as chaves que precisam ser substituídas, preservando o restante.

## 5. DVMT e DeviceProperties

Preferencialmente configure DVMT Pre-Allocated para 96 MB na BIOS/UEFI, se a opção estiver disponível.

- **96 MB:** não adicione o patch DVMT abaixo nem -igfxdvmt.
- **60 MB fixos:** acrescente `-igfxdvmt` aos boot-args e as propriedades abaixo.
- **DVMT desconhecido/outro valor:** não aplique o patch de 60 MB por tentativa; confirme a reserva real. Não faça mod de BIOS sem procedimento específico e recuperação.

Caminho usual: DeviceProperties > Add > `PciRoot(0x0)/Pci(0x2,0x0)`. Confirme o caminho PCI da iGPU na sua máquina.

| Chave | Tipo | Hexadecimal (somente 60 MB) |
| --- | --- | --- |
| framebuffer-patch-enable | Data | 01000000 |
| framebuffer-stolenmem | Data | 0000C003 |

Exemplo XML dentro de DeviceProperties > Add, mesclando com o dicionário existente da iGPU:
```xml
<key>PciRoot(0x0)/Pci(0x2,0x0)</key>
<dict>
    <key>framebuffer-patch-enable</key>
    <data>AQAAAA==</data>
    <key>framebuffer-stolenmem</key>
    <data>AADAAw==</data>
</dict>
```

Esses valores não aumentam a memória reservada fisicamente. A detecção de GPU é automática: não imponha device-id, AAPL,ig-platform-id ou spoof de outra arquitetura por padrão. Remova spoofs antigos da iGPU quando conflitantes; não apague propriedades de outros dispositivos. Para Alder Lake/Raptor Lake abrangidos, tiling é automático: não use -yTileDisable nem adicione AAPL,GfxYTile por padrão. Não há SMBIOS ou configuração completa de ACPI universal para E4.

## 6. Brilho da tela interna

Use SSDT-PNLF.aml adequado ao namespace ACPI do computador. Copie em EFI/OC/ACPI e registre em ACPI > Add:
- Path (String): SSDT-PNLF.aml
- Enabled (Boolean): True
- Comment (String): Internal panel brightness

Não duplique uma PNLF existente. Confira o caminho ACPI real; a presença da SSDT não garante brilho funcional em qualquer painel. Não invente valores de backlight.

## 7. Instalação normal (macOS já instalado)

1. Monte a partição EFI de teste. Faça as alterações acima, salve o config.plist e execute ocvalidate da mesma versão do OpenCore. Se usar OC Snapshot no ProperTree, confira novamente a ordem e as entradas desativadas.
2. Inicialize o macOS alvo pela EFI de teste. Antes de instalar, restaure eventuais patches Xe antigos no volume System pelo método correspondente.
3. Confirme o AMFIAnchor com `ioreg -r -c AMFIAnchor -l`: InstallStatus deve ser 1 e LoadedAnchors deve conter o anchor oficial.
4. Abra o WhateverXe Graphics 0.4.5.pkg oficial. O instalador não altera EFI/SIP; o PKG não é notarizado/assinado, mas os payloads gráficos são assinados pela CA do injector. Não instale cópias de origem desconhecida.
5. Resolva erros de instalação antes de reiniciar; consulte /var/log/install.log. Reinicie com a mesma EFI de teste. Graphics instala em /Library e reconstrói AuxKC, sem patch no volume System.

## 8. Instalação limpa / Recovery (opcional)

Para instalação automática antes do Setup Assistant, a documentação Graphics 0.4.5 orienta:
- Use pendrive instalador macOS compatível e coloque AutoPkg-Assets.pkg correspondente em Library/Packages/ na partição do instalador (não na EFI).
- Adicione AutoPkgInstaller 1.0.4 em EFI/OC/Kexts e Kernel > Add (BundlePath AutoPkgInstaller.kext, ExecutablePath Contents/MacOS/AutoPkgInstaller, PlistPath Contents/Info.plist, Enabled True; confira os arquivos e dependências reais).
- Altere csr-active-config para Data **030A0000** (0xA03; XML Base64 AwoAAA==) e acrescente -autopkgbeta no Tahoe. Esse SIP permite carregamento de kexts não aprovadas; não presuma que voltar a 0x803 depois preserve a aprovação.
- Instale normalmente. Uma reinicialização adicional aplica Graphics antes do Setup Assistant. Não abra AutoPkg manualmente nem misture assets AutoPkg do OCLP e WEX.

O instalador USB inicial/Recovery **não tem aceleração completa garantida** por esse método; a E4 não implementa um modo Recovery acelerado. Para instalações existentes, use o PKG normal da seção 7.

## 9. Validação após reiniciar

```sh
kmutil showloaded | grep -Ei 'Lilu|WhateverXe|AMFIAnchor|AppleIntelTGL'
ioreg -r -c AMFIAnchor -l
system_profiler SPDisplaysDataType
```

Verifique resolução nativa, detecção Metal, brilho, saídas e estabilidade. O injector codeless pode não aparecer como kext executável carregada. Para confirmar computação e renderização básicas na GPU correta (requer Xcode Command Line Tools), baixe metal_probe.swift desta release:
```sh
xcrun swiftc -swift-version 5 metal_probe.swift -o metal_probe
./metal_probe --iterations 1
./metal_probe --iterations 100
```
Em sistemas multi-GPU, identifique a iGPU no IORegistry e use --registry-id com seu ID real. Procure compute-output-verified e render-pixels-verified. Pare se houver erro/travamento. Teste suspensão e retomada apenas depois de validar boot e vídeo, com dados salvos. PASS não comprova todos os recursos Metal, vídeo ou desempenho.

## 10. Recuperação de falhas e remoção

Se a EFI não iniciar, use a EFI de backup pelo menu UEFI. Para investigar, teste uma variável por vez; não force PCI IDs, DVMT ou patches de conectores sem evidência. Se necessário, desative WhateverXe em Kernel > Add na EFI de teste e restaure propriedades/argumentos anteriores. Para remover Graphics, use o uninstall.sh oficial correspondente à versão, conforme a documentação Graphics; ele remove os componentes em /Library e reconstrói AuxKC. Só restaure a configuração de segurança original após remover as dependências que exigem SIP reduzido. Não combine WhateverGreen com WhateverXe.

## Referências
- [README da base E4 — instalação e configuração](https://github.com/rodrigosalesf/WhateverXe-Enhanced/blob/c24d6d8bc8e3b98977eab4e146c8d26463a0d338/README.md)
- [WhateverXe Graphics 0.4.5 — instalação, AutoPkg e remoção](https://github.com/b00t0x/WhateverXe-Graphics/tree/v0.4.5)
- [AMFIAnchor — OpenCore](https://github.com/b00t0x/AMFIAnchor#install-with-opencore)
- [OpenCore](https://github.com/acidanthera/OpenCorePkg)

Este guia não substitui a configuração ACPI/SMBIOS específica de cada máquina. E4 é experimental; resultados de hardware ainda pendentes.
