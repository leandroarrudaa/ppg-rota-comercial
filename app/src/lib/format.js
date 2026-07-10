export const FAIXAS = ["Ouro", "Prata", "Bronze"];

export const FAIXA_COR = {
  Ouro: "#c9a227",
  Prata: "#8e949b",
  Bronze: "#b4793f",
};

export const FAIXA_CHIP = {
  Ouro: "chip-gold",
  Prata: "chip-silver",
  Bronze: "chip-bronze",
};

export const FAIXA_DOT = {
  Ouro: "dot-gold",
  Prata: "dot-silver",
  Bronze: "dot-bronze",
};

export function brl(v) {
  return (v || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  });
}

export function num(v) {
  return (v || 0).toLocaleString("pt-BR");
}

export function telefoneFmt(t) {
  if (!t) return null;
  const d = String(t).replace(/\D/g, "");
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return t;
}

// "há X dias" -> texto amigável
export function recenciaTexto(dias) {
  if (dias == null) return "—";
  if (dias <= 0) return "hoje";
  if (dias < 30) return `há ${dias} dias`;
  if (dias < 365) return `há ${Math.round(dias / 30)} meses`;
  return `há ${(dias / 365).toFixed(1).replace(".", ",")} anos`;
}
