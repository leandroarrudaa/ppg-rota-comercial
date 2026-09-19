// ============================================================
// Filtro de potencial ouro + cliente novo/antigo, compartilhado pelas telas
// (Mapa, Plano de Visitas, Plano de Contato, Rota do Dia).
//
// A nota (0-100) vem do servidor em `notaPotencial`, já calculada — ver
// backend/app/services/potencial.py. Nulo = já é ouro ou está inativo.
// ============================================================
import { useCallback, useState } from "react";

export const ORIGENS = [
  { id: "todos", rotulo: "Todos" },
  { id: "antigo", rotulo: "Antigos" },
  { id: "novo", rotulo: "Novos" },
];

export const NOTA_MIN_PADRAO = 70;
export const FILTRO_POTENCIAL_PADRAO = { origem: "todos", soPotencial: false, notaMin: NOTA_MIN_PADRAO };

// mesma chave nas telas: a escolha vale para todas, sem precisar repassar por props
const CHAVE = "ppg_filtro_potencial";

function lerSalvo() {
  try {
    const salvo = JSON.parse(localStorage.getItem(CHAVE));
    return salvo ? { ...FILTRO_POTENCIAL_PADRAO, ...salvo } : FILTRO_POTENCIAL_PADRAO;
  } catch {
    return FILTRO_POTENCIAL_PADRAO;
  }
}

export function useFiltroPotencial() {
  const [filtro, setFiltro] = useState(lerSalvo);
  const mudar = useCallback((parcial) => {
    setFiltro((atual) => {
      const novo = { ...atual, ...parcial };
      try { localStorage.setItem(CHAVE, JSON.stringify(novo)); } catch { /* sem armazenamento: só não lembra */ }
      return novo;
    });
  }, []);
  return [filtro, mudar];
}

export function passaFiltroPotencial(c, f) {
  if (f.origem !== "todos" && c.origem !== f.origem) return false;
  if (f.soPotencial && !(c.notaPotencial != null && c.notaPotencial >= f.notaMin)) return false;
  return true;
}

// Com "só potencial" ligado, a nota também ordena a rota: quem tem mais potencial
// sobe na fila (ver valorEstrategico em rota.js). Sem o filtro, nada muda no plano.
export function aplicarFiltroPotencial(clientes, f) {
  const lista = clientes.filter((c) => passaFiltroPotencial(c, f));
  if (!f.soPotencial) return lista;
  return lista.map((c) => ({ ...c, bonusPotencial: (c.notaPotencial || 0) * 0.6 }));
}

export const COR_CLIENTE_NOVO = "#7b5cf0";
