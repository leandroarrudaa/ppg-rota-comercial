// ============================================================
// Motor de recomendação de ação para o vendedor.
// Usa faixa + cadência + recência (sem precisar do detalhe de produto).
// Quando houver histórico de produtos, dá pra enriquecer com "ofertar X".
// ============================================================

export function recomendar(c) {
  const cad = c.cadencia;
  const rec = c.recencia;
  // recompra atrasada: passou bem do intervalo médio dele
  const atrasado = cad && rec != null && rec > cad * 1.4;
  const diasAtraso = atrasado ? Math.round(rec - cad) : 0;

  // 1) conta grande que esfriou (alerta máximo)
  if (c.emRisco) {
    return {
      tag: "Reativar",
      cor: "var(--risk)",
      titulo: "Conta grande parada — reativar já",
      texto:
        cad && rec != null
          ? `Comprava a cada ${cad} dias e está há ${rec} dias sem comprar. Ligar com prioridade, entender o que mudou e trazer de volta com oferta de retorno.`
          : `Conta de alto valor que esfriou. Contato urgente para reativar o relacionamento.`,
    };
  }

  // 2) Ouro
  if (c.faixa === "Ouro") {
    if (atrasado) {
      return {
        tag: "Recompra atrasada",
        cor: "var(--gold-deep)",
        titulo: "Cliente-chave em atraso de recompra",
        texto: `Compra a cada ${cad} dias, mas já se passaram ${rec}. Está ~${diasAtraso} dias atrasado — ligar e fechar a reposição.`,
      };
    }
    return {
      tag: "Aprofundar",
      cor: "var(--gold-deep)",
      titulo: "Conta-chave fiel — expandir",
      texto: `Cliente Ouro ativo. Fortalecer relacionamento, apresentar linha completa/lançamentos e ampliar o mix de compra.`,
    };
  }

  // 3) Prata
  if (c.faixa === "Prata") {
    if (atrasado) {
      return {
        tag: "Resgatar",
        cor: "var(--silver-deep)",
        titulo: "Esfriando — resgatar ritmo",
        texto: `Vinha comprando a cada ${cad} dias e está há ${rec}. Reaproximar antes de virar inativo.`,
      };
    }
    return {
      tag: "Fazer subir",
      cor: "var(--silver-deep)",
      titulo: "Potencial de subir de faixa",
      texto: `Bom cliente com espaço pra crescer. Aumentar frequência e ticket: combos, recompra programada, novos itens.`,
    };
  }

  // 4) Bronze
  return {
    tag: "Desenvolver",
    cor: "var(--bronze-deep)",
    titulo: "Desenvolver o cliente",
    texto: `Baixo volume hoje. Entender a necessidade, apresentar o portfólio e estimular a primeira recompra relevante.`,
  };
}

// Script de REAPROXIMAÇÃO para o Plano de Contato (clientes adormecidos).
// O objetivo do contato é reabrir relacionamento e AGENDAR uma visita.
export function scriptContato(c) {
  const meses = c.recencia != null ? Math.round(c.recencia / 30) : null;
  const tempo = meses ? (meses >= 12 ? `${(meses / 12).toFixed(1).replace(".", ",")} anos` : `${meses} meses`) : "um tempo";
  const valorHist = c.fat >= 20000 ? "uma conta importante" : c.fat >= 5000 ? "um bom cliente" : "um cliente";

  let prioridade = "Baixa";
  if (c.emRisco || c.fat >= 30000) prioridade = "Alta";
  else if (c.faixa !== "Bronze" || c.fat >= 8000) prioridade = "Média";

  return {
    prioridade,
    objetivo: "Reabrir relacionamento e agendar visita",
    script:
      `Sem comprar há ~${tempo}. Já foi ${valorHist} (R$ ${(c.fat || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} no histórico). ` +
      `Ligar/WhatsApp: relembrar a Fratelli, entender o momento atual da empresa e propor uma visita para reapresentar o portfólio.`,
  };
}
