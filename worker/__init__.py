"""Worker da nuvem do ClipPro (fase N-1, RULINGS §27).

Pega um trabalho de uma fila, roda o MESMO motor do CLI e do painel e entrega
os clipes num deposito. No beta fechado (§27, G3) ele roda no PC do operador
e busca os trabalhos por conexao de saida -- nenhuma porta aberta.

Regra da casa herdada do painel: o worker NAO duplica regra de estagio. Ele
chama motor.montar_estagios/rodar_estagios, como ui/jobs.py.
"""
