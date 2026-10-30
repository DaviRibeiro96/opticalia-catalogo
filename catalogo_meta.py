"""Catalogo da Meta (WhatsApp, Instagram e anuncios) gerado a partir do SITE NO AR.
O site manda: o que esta ativo na categoria, preco, preco antigo, estoque e foto de capa vem da propria pagina da categoria
(o mesmo POST /categoria_load.php que a categoria usa). O cadastro da Marchon so completa o que o site nao mostra:
EAN, modelo (agrupa as cores), cor, material, formato, publico e medidas. Toda compra leva para o site (sem carrinho no WhatsApp).

Roda no GitHub (repositorio opticalia-catalogo, de hora em hora): la ele le o complemento de dados_catalogo.json,
que e exportado daqui SEM custo nem margem (so o que ja e publico no site).

Uso no PC:     python ferramentas/catalogo_meta.py                       -> catalogo_meta/catalogo_opticalia.csv (teste)
               python ferramentas/catalogo_meta.py --exportar <pasta>    -> <pasta>/dados_catalogo.json + copia deste script
No GitHub:     python catalogo_meta.py --dados dados_catalogo.json --saida docs
"""
import csv, html, json, os, re, shutil, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://www.opticalia.com.br'
CATEGORIAS = {833: 'grau', 834: 'sol', 835: 'lentes'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
UTM = 'utm_source=meta&utm_medium=catalogo&utm_campaign=catalogo_opticalia'
MIN_PRODUTOS = 300   # abaixo disso o site deve ter falhado: nao sobrescreve o feed (a Meta apagaria os produtos)

# categoria do Google, que a Meta usa para entender o produto
GOOGLE = {'sol': 'Apparel & Accessories > Clothing Accessories > Sunglasses',
          'grau': 'Health & Beauty > Personal Care > Vision Care > Eyeglasses',
          'lentes': 'Health & Beauty > Personal Care > Vision Care > Contact Lenses'}
TIPO = {'sol': 'Óculos de Sol', 'grau': 'Óculos de Grau', 'lentes': 'Lentes de Contato'}
GENERO = {'Masculino': 'male', 'Feminino': 'female', 'Unissex': 'unisex', 'Infantil': 'unisex'}
COLUNAS = ['id', 'title', 'description', 'availability', 'condition', 'price', 'sale_price', 'link', 'image_link',
           'additional_image_link', 'brand', 'google_product_category', 'product_type', 'item_group_id', 'gtin', 'mpn',
           'color', 'material', 'gender', 'age_group', 'inventory', 'custom_label_0', 'custom_label_1', 'custom_label_2', 'internal_label']
# o que vai para o GitHub (publico): nada de custo, margem ou estoque do fornecedor
CAMPOS_PUBLICOS = ['ean', 'sku', 'marca', 'modelo', 'cor', 'cor_lente', 'material', 'formato', 'sexo', 'lente_mm', 'ponte_mm', 'haste_mm', 'best_seller']


def arg(nome, padrao=None):
    return sys.argv[sys.argv.index(nome) + 1] if nome in sys.argv else padrao


def dados_locais():
    """Complemento de cada produto, montado dos arquivos do cadastro (so os campos publicos)."""
    ids = json.load(open(os.path.join(RAIZ, 'cadastro', 'marchon', 'ids.json'), encoding='utf-8'))
    cat = json.load(open(os.path.join(RAIZ, 'cadastro', 'marchon', 'catalogo.json'), encoding='utf-8'))['produtos']
    por_sku = {p['sku']: p for p in cat}
    fotos = json.load(open(os.path.join(RAIZ, 'cadastro', 'marchon', 'fotos_visual.json'), encoding='utf-8'))
    site = json.load(open(os.path.join(RAIZ, 'dados', 'produtos_site.json'), encoding='utf-8'))
    prod = {pid: {'marca': v.get('marca', '')} for pid, v in site.items()}
    for sku, pid in ids.items():
        m = por_sku.get(sku)
        if m:
            prod[str(pid)] = {k: m.get(k) for k in CAMPOS_PUBLICOS if m.get(k) not in (None, '', False)}
    for pid, lista in fotos.items():
        prod.setdefault(pid, {})['fotos'] = lista
    return {'gerado': datetime.now().isoformat(timespec='seconds'), 'produtos': prod}


def post(dados):
    req = urllib.request.Request(SITE + '/categoria_load.php', data=urllib.parse.urlencode(dados).encode(),
                                 headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest', 'Referer': SITE + '/'})
    for tentativa in range(3):
        try:
            return urllib.request.urlopen(req, timeout=90).read().decode('utf-8', 'replace')
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(10)


def reais(t):
    m = re.search(r'R\$\s*([\d.]+,\d{2})', t or '')
    return float(m.group(1).replace('.', '').replace(',', '.')) if m else None


def cartoes(idc):
    """Todos os cartoes ativos da categoria: {id: dados do cartao}."""
    h = post({'numero_pagina': 1, 'idc': idc, 'ordenar': '', 'itens': 2000, 'marca': '', 'regra_contador_produto': 'true'})
    h = re.sub(r'<style.*?</style>', '', h, flags=re.S)
    achados = {}
    for p in re.split(r'<div class="produto[ "][^>]*?data-prod="', h)[1:]:
        pid = p[:p.index('"')]
        link = re.search(r'<a href="(https://www\.opticalia\.com\.br/[^"]+)"', p)
        nome = re.search(r'class="nome-prod-desktop">\s*(.*?)\s*</h3>', p, re.S)
        imgs = re.findall(r'<img src="(https://www\.opticalia\.com\.br/uploads/[^"]+)"', p)
        de = re.search(r'class="preco-de">(.*?)</span>', p, re.S)
        por = re.search(r'class="preco-por">(.*?)</span>', p, re.S)
        estoque = sum(int(x) for x in re.findall(r"data-estoque='(-?\d+)'", p) if int(x) > 0)
        if not estoque:
            m = re.search(r'data_estoque="(-?\d+)"', p)
            estoque = max(int(m.group(1)), 0) if m else 0
        if not (link and nome and por):
            continue
        achados[pid] = {'link': link.group(1), 'nome': html.unescape(re.sub(r'\s+', ' ', nome.group(1))).strip(),
                        'imgs': list(dict.fromkeys(imgs)), 'por': reais(por.group(1)),
                        'de': reais(de.group(1)) if de else None, 'estoque': estoque}
    return achados


def descricao(tipo, nome, marca, m):
    """Texto limpo para o catalogo (a descricao do site tem CSS e botoes dentro)."""
    frases = ['%s %s %s.' % (TIPO[tipo], marca, nome) if marca and marca.lower() not in nome.lower() else '%s %s.' % (TIPO[tipo], nome)]
    det = []
    if m.get('formato'):
        det.append('formato %s' % m['formato'].lower())
    if m.get('material'):
        det.append(m['material'].lower())
    if m.get('cor'):
        det.append('cor %s' % m['cor'].lower())
    if m.get('cor_lente') and tipo == 'sol':
        det.append('lente %s' % m['cor_lente'].lower())
    if det:
        frases.append(', '.join(det).capitalize() + '.')
    med = [m.get(k) for k in ('lente_mm', 'ponte_mm', 'haste_mm')]
    if all(med):
        frases.append('Medidas: lente %s mm, ponte %s mm, haste %s mm.' % tuple(med))
    if tipo == 'grau':
        frases.append('Armação original com garantia. As lentes de grau são feitas em uma loja Opticalia, com a sua receita.')
    elif tipo == 'sol':
        frases.append('Óculos original com garantia e proteção UV.')
    frases.append('Compre no site da Opticalia Brasil: pagamento em até 6x sem juros ou no Pix e troca fácil.')
    return ' '.join(frases)


def gerar(comp):
    linhas, vistos = [], set()
    rel = {'gerado': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'por_categoria': {}, 'sem_complemento': [],
           'esgotados': 0, 'promocao': 0}
    for idc, tipo in CATEGORIAS.items():
        cards = cartoes(idc)
        rel['por_categoria'][tipo] = len(cards)
        for pid, c in cards.items():
            if pid in vistos:
                continue
            vistos.add(pid)
            m = comp.get(pid, {})
            if not m.get('ean'):
                rel['sem_complemento'].append(pid)
            marca = m.get('marca') or ''
            preco, antigo = c['por'], c['de']
            cheio, promo = (antigo, preco) if antigo and antigo > preco else (preco, None)
            rel['promocao'] += bool(promo)
            disp = 'in stock' if c['estoque'] > 0 else 'out of stock'
            rel['esgotados'] += disp != 'in stock'
            capa = c['imgs'][0] if c['imgs'] else ''
            extras = [SITE + f for f in m.get('fotos', [])] + c['imgs'][1:]
            extras = [u for u in dict.fromkeys(extras) if u != capa][:10]
            linhas.append({
                'id': pid, 'title': c['nome'][:150], 'description': descricao(tipo, c['nome'], marca, m),
                'availability': disp, 'condition': 'new', 'price': '%.2f BRL' % cheio,
                'sale_price': '%.2f BRL' % promo if promo else '', 'link': c['link'] + ('&' if '?' in c['link'] else '?') + UTM,
                'image_link': capa, 'additional_image_link': ','.join(extras), 'brand': marca or 'Opticalia',
                'google_product_category': GOOGLE[tipo], 'product_type': TIPO[tipo] + (' > ' + marca if marca else ''),
                'item_group_id': ('%s %s' % (marca, m['modelo'])).strip() if m.get('modelo') else '',
                'gtin': m.get('ean', ''), 'mpn': m.get('sku', ''), 'color': m.get('cor', ''), 'material': m.get('material', ''),
                'gender': GENERO.get(m.get('sexo'), 'unisex'), 'age_group': 'kids' if m.get('sexo') == 'Infantil' else 'adult',
                'inventory': c['estoque'], 'custom_label_0': tipo, 'custom_label_1': 'promocao' if promo else '',
                'custom_label_2': 'mais_vendido' if m.get('best_seller') else '',
                # rotulo interno: nao passa por analise da Meta e serve de filtro de conjunto na hora
                'internal_label': "['mais_vendido']" if m.get('best_seller') else ''})
    rel['total'] = len(linhas)
    return linhas, rel


def exportar(pasta):
    os.makedirs(pasta, exist_ok=True)
    json.dump(dados_locais(), open(os.path.join(pasta, 'dados_catalogo.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    shutil.copyfile(os.path.abspath(__file__), os.path.join(pasta, 'catalogo_meta.py'))
    print('exportado para', pasta)


def main():
    if '--exportar' in sys.argv:
        return exportar(arg('--exportar'))
    arq_dados = arg('--dados')
    comp = (json.load(open(arq_dados, encoding='utf-8')) if arq_dados else dados_locais())['produtos']
    saida = arg('--saida', os.path.join(RAIZ, 'catalogo_meta'))
    linhas, rel = gerar(comp)
    os.makedirs(saida, exist_ok=True)
    print('produtos: %d %s | esgotados %d | promocao %d | sem complemento %d' % (
        rel['total'], rel['por_categoria'], rel['esgotados'], rel['promocao'], len(rel['sem_complemento'])))
    if rel['total'] < MIN_PRODUTOS:
        sys.exit('ERRO: so %d produtos lidos do site; o feed anterior foi mantido.' % rel['total'])
    arq = os.path.join(saida, 'catalogo_opticalia.csv')
    with open(arq + '.tmp', 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        # mais vendidos (marcados pela Marchon) primeiro: a ordem do arquivo costuma ser a ordem do catalogo
        w.writerows(sorted(linhas, key=lambda r: (r['custom_label_2'] != 'mais_vendido', r['availability'] != 'in stock', int(r['id']))))
    os.replace(arq + '.tmp', arq)
    json.dump(rel, open(os.path.join(saida, 'relatorio.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('ok:', arq)


if __name__ == '__main__':
    main()
