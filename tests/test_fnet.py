from pipeline.fnet import aggregate_vacancia, parse_imoveis

# Fragmento no padrão do ANEXO 39-II: cabeçalho aparece 1x; cada imóvel é uma célula com
# "Área (m2)" seguida de 3 percentuais (vacância, inadimplência, % das receitas do FII).
SAMPLE = """
<table>
<tr><td>1.1.2.1.1</td><td>Relação de Imóveis</td><td>% de Vacância</td>
    <td>% de Inadimplência</td><td>% em relação às receitas do FII</td></tr>
<tr><td>Galpão A, Área (m2): 1.000</td><td>0,0000%</td><td>0,0000%</td><td>50,0000%</td>
    <td>Logística</td></tr>
</table>
<table>
<tr><td>Galpão B, Área (m2): 2.000</td><td>10,0000%</td><td>2,0000%</td><td>50,0000%</td>
    <td>Varejo</td></tr>
</table>
"""


def test_parse_imoveis_pega_todos_mesmo_sem_cabecalho_repetido():
    imoveis = parse_imoveis(SAMPLE)
    assert len(imoveis) == 2  # apesar do cabeçalho aparecer só na 1ª tabela
    assert imoveis[0]["vacancia"] == 0.0
    assert imoveis[1]["vacancia"] == 0.10
    assert imoveis[1]["inadimplencia"] == 0.02


def test_aggregate_vacancia_pondera_pela_receita():
    agg = aggregate_vacancia(parse_imoveis(SAMPLE))
    # pesos iguais (50%/50%): vacância = (0 + 10)/2 = 5%; inadimplência = (0 + 2)/2 = 1%
    assert agg["vacancia"] == 0.05
    assert agg["inadimplencia"] == 0.01
    assert agg["n_imoveis"] == 2


def test_aggregate_vacancia_vazio():
    agg = aggregate_vacancia([])
    assert agg["n_imoveis"] == 0 and agg["vacancia"] is None


# Alguns administradores preenchem a coluna de vacância com ocupação/participação (100%);
# o agregado fica implausível e o fetch_vacancia (camada de rede) corta como N/A (> 40%).
IMPLAUSIVEL = """
<table>
<tr><td>X, Área (m2): 1</td><td>% de Vacância</td><td>% de Inadimplência</td>
    <td>% em relação às receitas do FII</td></tr>
<tr><td>Loja 1, Área (m2): 1</td><td>100,0000%</td><td>0,0000%</td><td>50,0000%</td></tr>
<tr><td>Loja 2, Área (m2): 1</td><td>100,0000%</td><td>0,0000%</td><td>50,0000%</td></tr>
</table>
"""


def test_aggregate_vacancia_detecta_coluna_de_ocupacao():
    agg = aggregate_vacancia(parse_imoveis(IMPLAUSIVEL))
    assert agg["vacancia"] == 1.0  # 100% — implausível; o guard (>0,40) marca N/A no fetch
