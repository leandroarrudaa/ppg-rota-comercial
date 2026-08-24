// Guarda a seleção/rota da Rota do Dia no localStorage, por vendedor.
//
// Sem isso, sair da tela por engano (trocar de aba, fechar o navegador,
// reiniciar o celular) fazia perder a seleção inteira e recomeçar do zero —
// a queixa mais comum do time em campo.
//
// A Rota do Dia não recebe a carteira inteira como prop (ela busca só o que
// está visível no mapa ou bate com a busca), então não dá pra só guardar os
// IDs e resolver contra uma lista já carregada — guardamos os clientes
// selecionados inteiros. A troca é um retrato levemente desatualizado se
// algo mudar no cliente em outra tela durante o dia (aceita visita, telefone
// etc.); aceitável porque só restaura dentro do mesmo dia (ver mesmoDiaLocal)
// e porque funciona mesmo sem internet no momento de reabrir o app — o que
// importa mais em campo do que estar 100% em dia.
const VERSAO = 1;

function chave(vendedorId) {
  return `ppg_rota_dia_v${VERSAO}_${vendedorId}`;
}

export function salvarRota(vendedorId, { clientes, selecionadosIds, modo, rotaOrdemIds, rotaEstrada }) {
  try {
    localStorage.setItem(chave(vendedorId), JSON.stringify({
      clientes, selecionadosIds, modo, rotaOrdemIds, rotaEstrada, salvoEm: Date.now(),
    }));
  } catch {
    // localStorage pode falhar (modo privado do navegador, cota cheia) —
    // perder a persistência não pode derrubar o app, só volta a valer sem ela.
  }
}

export function limparRota(vendedorId) {
  try {
    localStorage.removeItem(chave(vendedorId));
  } catch {
    // ver nota acima
  }
}

function mesmoDiaLocal(timestamp) {
  const a = new Date(timestamp);
  const b = new Date();
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// Devolve { clientes: cliente[], selecionadosIds, modo, rotaOrdemIds, rotaEstrada }
// ou null se não houver nada válido pra restaurar.
export function carregarRota(vendedorId) {
  try {
    const bruto = localStorage.getItem(chave(vendedorId));
    if (!bruto) return null;
    const dados = JSON.parse(bruto);
    // rota salva num dia anterior é plano de um dia de trabalho já encerrado
    // — não vale a pena restaurar sozinho, é mais confuso que ajudar.
    if (!dados.salvoEm || !mesmoDiaLocal(dados.salvoEm)) return null;
    if (!Array.isArray(dados.clientes) || !Array.isArray(dados.selecionadosIds)) return null;
    if (dados.selecionadosIds.length === 0) return null;
    return dados;
  } catch {
    return null;
  }
}
