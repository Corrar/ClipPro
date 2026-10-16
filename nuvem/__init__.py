"""Codigo compartilhado da nuvem do ClipPro (RULINGS §28, §29.3).

Usado pelo worker (worker/nuvem.py) e pelas funcoes da Vercel (api/). So
biblioteca padrao: as funcoes da Vercel sobem sem instalar nada, e o worker
nao ganha dependencia nova (CLAUDE.md §4).

Os .sql em nuvem/supabase/ sao as migracoes do banco; rodam no SQL Editor do
Supabase, em ordem.
"""
