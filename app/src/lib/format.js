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

// Datas puras (YYYY-MM-DD, sem hora — ex.: retornoData) vindas da API. O
// construtor Date() interpreta uma string só-de-data como meia-noite UTC;
// exibir isso com toLocaleDateString sem corrigir mostra o dia ANTERIOR pra
// quem está no Brasil (UTC-3 vira 21h do dia de antes). Monta o texto a
// partir dos componentes, sem passar pelo fuso do navegador.
export function dataTexto(isoData) {
  if (!isoData) return "—";
  const [ano, mes, dia] = isoData.split("-");
  return `${dia}/${mes}/${ano}`;
}

// Datas com hora (ISO sem sufixo de fuso — ex.: inicio/fim de visita) vindas
// da API: são UTC ingênuo. Sem marcar isso, o navegador as interpreta como
// já sendo hora local e erra o horário exibido (e, perto da virada do dia,
// o próprio dia).
export function dataHoraUtc(iso) {
  if (!iso) return null;
  const comFuso = /[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z";
  return new Date(comFuso);
}

// Date -> "YYYY-MM-DD" usando os componentes LOCAIS (não UTC) — o formato que
// <input type="date"> espera e que a API de relatórios recebe como período.
export function isoLocal(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dia}`;
}

// minutos -> "1h05" / "42 min"
export function duracaoTexto(min) {
  if (min == null) return "—";
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m} min`;
}

// "há X dias" -> texto amigável
export function recenciaTexto(dias) {
  if (dias == null) return "—";
  if (dias <= 0) return "hoje";
  if (dias < 30) return `há ${dias} dias`;
  if (dias < 365) return `há ${Math.round(dias / 30)} meses`;
  return `há ${(dias / 365).toFixed(1).replace(".", ",")} anos`;
}
