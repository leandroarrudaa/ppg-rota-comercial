import { tokenSalvo } from "./api";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8090";

// Envio com barra de progresso. O fetch do lib/api não serve aqui: ele manda
// JSON e não reporta progresso, e um arquivo de alguns MB numa internet de
// loja demora o suficiente para o gerente achar que travou.
export function enviarArquivo(caminho, arquivo, aoProgresso) {
  return new Promise((resolve, reject) => {
    const req = new XMLHttpRequest();
    req.open("POST", `${BASE}${caminho}`);
    req.setRequestHeader("Authorization", `Bearer ${tokenSalvo()}`);
    req.upload.onprogress = (e) => {
      if (e.lengthComputable) aoProgresso(Math.round((e.loaded / e.total) * 100));
    };
    req.onload = () => {
      let corpo = null;
      try { corpo = JSON.parse(req.responseText); } catch { /* resposta sem JSON */ }
      if (req.status >= 200 && req.status < 300) return resolve(corpo);
      reject(new Error(corpo?.detail || "Não foi possível processar o arquivo."));
    };
    // Numa importação, "conexão perdida" quase nunca é internet do usuário: é
    // o servidor tendo derrubado a requisição no meio de uma gravação grande.
    // Dizer "verifique sua internet" mandava investigar o lugar errado.
    req.onerror = () => reject(new Error(
      "A conexão caiu durante o envio. Nada foi gravado pela metade — a importação " +
      "é tudo-ou-nada. Confira em \"Importações anteriores\" logo abaixo se ela entrou; " +
      "se não entrou, tente de novo."
    ));
    req.ontimeout = () => reject(new Error(
      "O servidor demorou demais para responder. Nada foi gravado pela metade. " +
      "Confira em \"Importações anteriores\" se ela entrou antes de tentar de novo."
    ));
    // A primeira importação do banco mestre grava dezenas de milhares de linhas
    // num banco que fica longe do servidor. Três minutos não bastavam.
    req.timeout = 900_000;
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    req.send(corpo);
  });
}
