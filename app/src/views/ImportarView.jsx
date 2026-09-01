import { useEffect, useRef, useState } from "react";
import { api, tokenSalvo } from "../lib/api";
import { brl } from "../lib/format";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8090";

const ORIGENS = {
  "banco-mestre": {
    titulo: "Pacote do banco mestre",
    quando: "Uma vez por mês, quando o banco mestre for regerado",
    extensao: ".ppg",
    ajuda:
      "Gere o arquivo no computador do escritório com o atalho " +
      "\"Preparar pacote do banco mestre\" e envie aqui o arquivo .ppg. " +
      "Ele é a fonte mais completa: tem o CNPJ real e o histórico inteiro, " +
      "e sobrepõe o que veio dos relatórios diários.",
  },
  "relatorio-vendas": {
    titulo: "Relatório de vendas do ERP",
    quando: "Todo dia",
    extensao: ".csv",
    ajuda:
      "Exporte do ERP o relatório \"Pedidos com Produtos (Detalhado)\" em CSV e " +
      "envie aqui. Os pedidos são somados ao histórico de cada cliente. " +
      "Enviar o mesmo arquivo duas vezes não conta em dobro.",
  },
};

// Envio com barra de progresso. O fetch do lib/api não serve aqui: ele manda
// JSON e não reporta progresso, e um arquivo de alguns MB numa internet de
// loja demora o suficiente para o gerente achar que travou.
function enviarArquivo(caminho, arquivo, aoProgresso) {
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
    req.onerror = () => reject(new Error("Sem conexão com o servidor. Verifique sua internet."));
    req.ontimeout = () => reject(new Error("O servidor demorou demais para responder."));
    // Importação mexe na carteira inteira e é mais lenta que uma tela comum.
    req.timeout = 180_000;
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    req.send(corpo);
  });
}

function Numero({ rotulo, valor, destaque, ajuda }) {
  return (
    <div className={"previa-item" + (destaque ? " destaque" : "")}>
      <span>{rotulo}</span>
      <b>{valor}</b>
      {ajuda && <small className="faint">{ajuda}</small>}
    </div>
  );
}

// Importação da carteira: escolhe a origem, envia, LÊ A PRÉVIA e só então
// confirma. A prévia roda a importação inteira no servidor e desfaz — é o
// mesmo código da gravação, então o que ela mostra é o que vai acontecer.
export default function ImportarView() {
  const [origem, setOrigem] = useState("relatorio-vendas");
  const [arquivo, setArquivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [progresso, setProgresso] = useState(0);
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState("");
  const [concluido, setConcluido] = useState(null);
  const [historico, setHistorico] = useState([]);
  const entradaRef = useRef(null);

  const config = ORIGENS[origem];

  function carregarHistorico() {
    api.get("/api/importacao/historico").then(setHistorico).catch(() => setHistorico([]));
  }
  useEffect(carregarHistorico, []);

  function escolher(novo) {
    setOrigem(novo);
    setArquivo(null);
    setPrevia(null);
    setConcluido(null);
    setErro("");
    if (entradaRef.current) entradaRef.current.value = "";
  }

  async function analisar() {
    if (!arquivo) return;
    setOcupado("previa");
    setErro("");
    setPrevia(null);
    setConcluido(null);
    setProgresso(0);
    try {
      const r = await enviarArquivo(`/api/importacao/${origem}`, arquivo, setProgresso);
      setPrevia(r.resumo);
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
    }
  }

  async function confirmar() {
    setOcupado("gravar");
    setErro("");
    setProgresso(0);
    try {
      const r = await enviarArquivo(`/api/importacao/${origem}?confirmar=true`, arquivo, setProgresso);
      setConcluido(r.resumo);
      setPrevia(null);
      setArquivo(null);
      if (entradaRef.current) entradaRef.current.value = "";
      carregarHistorico();
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
    }
  }

  const resumo = previa || concluido;
  const ehRelatorio = origem === "relatorio-vendas";

  return (
    <div className="importar">
      <div className="importar-origens">
        {Object.entries(ORIGENS).map(([chave, o]) => (
          <button
            key={chave}
            className={"importar-origem" + (origem === chave ? " on" : "")}
            onClick={() => escolher(chave)}
          >
            <b>{o.titulo}</b>
            <small className="faint">{o.quando}</small>
          </button>
        ))}
      </div>

      <p className="muted" style={{ fontSize: 13 }}>{config.ajuda}</p>

      <div className="importar-envio">
        <input
          ref={entradaRef}
          type="file"
          accept={config.extensao}
          onChange={(e) => { setArquivo(e.target.files?.[0] || null); setPrevia(null); setConcluido(null); }}
        />
        <button className="btn btn-primary" disabled={!arquivo || Boolean(ocupado)} onClick={analisar}>
          {ocupado === "previa" ? "Analisando…" : "Ver o que vai mudar"}
        </button>
      </div>

      {ocupado && progresso > 0 && progresso < 100 && (
        <div className="importar-progresso"><div style={{ width: `${progresso}%` }} /></div>
      )}
      {ocupado === "gravar" && progresso >= 100 && (
        <p className="muted" style={{ fontSize: 13 }}>Gravando… a carteira inteira é recalculada, pode levar alguns segundos.</p>
      )}

      {erro && <div className="login-erro">{erro}</div>}

      {resumo && (
        <div className={"importar-previa" + (concluido ? " concluida" : "")}>
          <h4>{concluido ? "Importação concluída" : "O que vai mudar"}</h4>

          {ehRelatorio ? (
            <div className="previa-grade">
              <Numero rotulo="Pedidos no arquivo" valor={resumo.pedidosNoArquivo} />
              <Numero
                rotulo="Pedidos novos" valor={resumo.pedidosNovos} destaque
                ajuda={resumo.pedidosJaImportados > 0 ? `${resumo.pedidosJaImportados} já tinham entrado antes` : null}
              />
              <Numero rotulo="Clientes atualizados" valor={resumo.clientesAtualizados} destaque />
              <Numero rotulo="Faturamento somado" valor={brl(resumo.faturamento)} destaque />
              <Numero
                rotulo="Balcão e pessoa física" valor={resumo.semDepara}
                ajuda="não entram na carteira de visita"
              />
              <Numero
                rotulo="Empresas fora da carteira" valor={resumo.cnpjForaDaCarteira}
                ajuda={resumo.cnpjForaDaCarteira > 0 ? "compram, mas ainda não são clientes" : null}
              />
              <Numero rotulo="Mudaram de faixa" valor={resumo.mudouFaixa} />
              <Numero rotulo="Saíram de risco" valor={resumo.saiuDeRisco} />
              {resumo.periodoInicio && (
                <Numero
                  rotulo="Período do arquivo"
                  valor={`${resumo.periodoInicio.split("-").reverse().join("/")} a ${resumo.periodoFim.split("-").reverse().join("/")}`}
                />
              )}
            </div>
          ) : (
            <div className="previa-grade">
              <Numero rotulo="Clientes atualizados" valor={resumo.atualizados} destaque />
              <Numero rotulo="Recência corrigida" valor={resumo.recenciaCorrigida} destaque
                ajuda="tinham compra mais nova do que a base sabia" />
              <Numero rotulo="Mudaram de faixa" valor={resumo.mudouFaixa} />
              <Numero rotulo="Saíram de risco" valor={resumo.saiuDeRisco} />
              <Numero rotulo="Entraram em risco" valor={resumo.entrouEmRisco} />
              <Numero rotulo="Histórico por produto" valor={(resumo.historicoLinhas || 0).toLocaleString("pt-BR")} />
              <Numero rotulo="Códigos do ERP" valor={resumo.deparaNovos + resumo.deparaAtualizados}
                ajuda="é o que faz o relatório diário funcionar" />
              <Numero rotulo="Sem venda no período" valor={resumo.semVendaNoPeriodo} />
            </div>
          )}

          {resumo.saiuDeRiscoNomes?.length > 0 && (
            <div className="previa-lista">
              <span className="filtro-titulo">Deixam de aparecer como "reativar já"</span>
              <ul>{resumo.saiuDeRiscoNomes.map((n) => <li key={n}>{n}</li>)}</ul>
            </div>
          )}

          {resumo.mudouFaixaExemplos?.length > 0 && (
            <div className="previa-lista">
              <span className="filtro-titulo">Mudanças de faixa</span>
              <ul>
                {resumo.mudouFaixaExemplos.map((m) => (
                  <li key={m.nome}>{m.de} → <b>{m.para}</b> · {m.nome}</li>
                ))}
              </ul>
            </div>
          )}

          {resumo.nomesForaDaCarteira?.length > 0 && (
            <div className="previa-lista">
              <span className="filtro-titulo">Compram mas não estão na carteira</span>
              <p className="muted" style={{ fontSize: 12 }}>
                Não são criadas automaticamente — precisam de endereço e localização antes.
              </p>
              <ul>{resumo.nomesForaDaCarteira.map((n, i) => <li key={n + i}>{n}</li>)}</ul>
            </div>
          )}

          {previa && (
            <div className="importar-confirmar">
              <button className="btn btn-primary" disabled={Boolean(ocupado)} onClick={confirmar}>
                {ocupado === "gravar" ? "Gravando…" : "Confirmar e gravar"}
              </button>
              <button className="btn btn-ghost" disabled={Boolean(ocupado)} onClick={() => setPrevia(null)}>
                Cancelar
              </button>
              <span className="faint" style={{ fontSize: 12 }}>Nada foi gravado ainda.</span>
            </div>
          )}
        </div>
      )}

      {historico.length > 0 && (
        <div className="importar-historico">
          <span className="filtro-titulo">Importações anteriores</span>
          <ul>
            {historico.map((h) => (
              <li key={h.id}>
                <b>{ORIGENS[h.tipo]?.titulo || h.tipo}</b>
                <span className="faint">
                  {" · "}
                  {new Date(h.criadoEm + "Z").toLocaleString("pt-BR", {
                    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
                  })}
                  {h.usuario ? ` · ${h.usuario}` : ""}
                  {h.arquivo ? ` · ${h.arquivo}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
