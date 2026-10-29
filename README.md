# Catálogo Opticalia Brasil para a Meta

Feed de produtos do WhatsApp, do Instagram e dos anúncios, gerado de hora em hora a partir do site **www.opticalia.com.br**.

- Endereço do feed: `https://<usuario>.github.io/opticalia-catalogo/catalogo_opticalia.csv`
- O site é a fonte de verdade. O catálogo só acompanha o site.
- `dados_catalogo.json` traz o que o site não mostra: EAN, modelo, cor, material e medidas. Não tem custo nem margem.
- O arquivo é atualizado pela pasta Opticalia-Site com `python ferramentas/catalogo_meta.py --exportar catalogo_meta/github`, depois commit e push.
