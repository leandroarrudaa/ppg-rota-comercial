// Gera e baixa um CSV a partir de uma lista de objetos — usado pelos
// relatórios que o escritório abre no Excel (ex: apuração de comissão).
function escaparCampo(valor) {
  const texto = valor == null ? "" : String(valor);
  return /[;"\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

// colunas: [{ rotulo, valor(linha) }]
export function baixarCsv(nomeArquivo, colunas, linhas) {
  const cabecalho = colunas.map((c) => c.rotulo).join(";");
  const corpo = linhas.map((linha) => colunas.map((c) => escaparCampo(c.valor(linha))).join(";")).join("\n");
  // BOM no início — sem isso o Excel abre acentuação quebrada
  const conteudo = "﻿" + cabecalho + "\n" + corpo;
  const blob = new Blob([conteudo], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  a.click();
  URL.revokeObjectURL(url);
}
