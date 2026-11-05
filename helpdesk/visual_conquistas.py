"""Catálogo fechado de símbolos e cores, sem classes ou arquivos enviados pelo usuário."""
ICONES = {
    'foguete': {'nome': 'Foguete', 'simbolo': 'rocket-takeoff-fill', 'cor': 'violeta', 'chamada': 'Pronto para decolar'},
    'trofeu': {'nome': 'Troféu', 'simbolo': 'trophy-fill', 'cor': 'ouro', 'chamada': 'Cada solução é uma vitória'},
    'cronometro': {'nome': 'Cronômetro', 'simbolo': 'stopwatch-fill', 'cor': 'turquesa', 'chamada': 'No ritmo certo'},
    'equipe': {'nome': 'Equipe', 'simbolo': 'people-fill', 'cor': 'azul', 'chamada': 'Juntos, vamos mais longe'},
    'estrela': {'nome': 'Estrela', 'simbolo': 'star-fill', 'cor': 'ouro', 'chamada': 'Seu trabalho faz a diferença'},
    'raio': {'nome': 'Raio', 'simbolo': 'lightning-charge-fill', 'cor': 'laranja', 'chamada': 'Energia para resolver'},
    'escudo': {'nome': 'Escudo', 'simbolo': 'shield-check', 'cor': 'turquesa', 'chamada': 'Confiança em cada entrega'},
    'alvo': {'nome': 'Alvo', 'simbolo': 'bullseye', 'cor': 'violeta', 'chamada': 'Um passo mais perto da meta'},
}
for codigo, dados in ICONES.items():
    dados['arquivo'] = f'helpdesk/conquistas/{codigo}.svg'

OPCOES_ICONES = [(codigo, dados['nome']) for codigo, dados in ICONES.items()]


def visual(icone):
    return ICONES.get(icone, ICONES['trofeu'])
