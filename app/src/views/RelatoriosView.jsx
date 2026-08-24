import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { gerarPdfRelatorio } from "../lib/pdf";
import { dataHoraUtc, dataTexto, duracaoTexto, isoLocal } from "../lib/format";

const PRESETS = [
  { chave: "hoje", rotulo: "Hoje" },
  { chave: "ontem", rotulo: "Ontem" },
  { chave: "semana", rotulo: "Esta semana" },
  { chave: "mes", rotulo: "Este mês" },
];

// Constrói a data a partir dos componentes (ano, mês, dia) — evita o
// construtor Date(stringSóDeData), que interpreta como meia-noite UTC e
// mostra o dia anterior pra quem está no Brasil (ver lib/format.js).
function dataDeChaveLocal(chaveDia) {
  const [y, m, d] = chaveDia.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function limitesDoPreset(chave) {
  const hoje = new Date();
  if (chave === "hoje") return [hoje, hoje];
  if (chave === "ontem") {
    const ontem = new Date(hoje);
    ontem.setDate(ontem.getDate() - 1);
    return [ontem, ontem];
  }
  if (chave === "semana") {
    const diaSemana = hoje.getDay(); // 0 = domingo
    const seg = new Date(hoje);
    seg.setDate(seg.getDate() - (diaSemana === 0 ? 6 : diaSemana - 1));
    return [seg, hoje];
  }
  // "mes"
  const dia1 = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  return [dia1, hoje];
}

export default function RelatoriosView({ usuario }) {
  const ehAdmin = usuario.papel === "admin";
  const [presetAtivo, setPresetAtivo] = useState("semana");
  const [inicioStr, setInicioStr] = useState(() => isoLocal(limitesDoPreset("semana")[0]));
  const [fimStr, setFimStr] = useState(() => isoLocal(limitesDoPreset("semana")[1]));
  const [vendedorId, setVendedorId] = useState("");
  const [vendedores, setVendedores] = useState(null);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [gerandoPdf, setGerandoPdf] = useState(false);

  useEffect(() => {
    if (!ehAdmin) return;
    api.get("/api/auth/usuarios").then(setVendedores).catch(() => setVendedores([]));
  }, [ehAdmin]);

  useEffect(() => {
    if (!inicioStr || !fimStr) return;
    setCarregando(true);
    setErro("");
    const params = new URLSearchParams({ inicio: inicioStr, fim: fimStr });
    if (ehAdmin && vendedorId) params.set("vendedorId", vendedorId);
    api.get(`/api/relatorios/visitas?${params}`)
      .then(setDados)
      .catch((e) => { setDados(null); setErro(e.message); })
      .finally(() => setCarregando(false));
  }, [inicioStr, fimStr, vendedorId, ehAdmin]);

  function aplicarPreset(chave) {
    const [ini, fim] = limitesDoPreset(chave);
    setPresetAtivo(chave);
    setInicioStr(isoLocal(ini));
    setFimStr(isoLocal(fim));
  }

  // Agrupa por dia de calendário LOCAL do instante de início (não a data UTC
  // ingênua que vem da API) — dataHoraUtc marca o fuso certo antes de ler os
  // componentes locais, senão uma visita perto da meia-noite cai no dia errado.
  const grupos = useMemo(() => {
    if (!dados) return [];
    const porDia = new Map();
    for (const v of dados.visitas) {
      const chave = isoLocal(dataHoraUtc(v.inicio));
      if (!porDia.has(chave)) porDia.set(chave, []);
      porDia.get(chave).push(v);
    }
    return [...porDia.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [dados]);

  const nomeVendedorFiltrado = ehAdmin && vendedorId
    ? vendedores?.find((v) => String(v.id) === vendedorId)?.nome
    : null;

  function baixarPdf() {
    if (!dados) return;
    setGerandoPdf(true);
    const tituloPeriodo = `${dataTexto(inicioStr)} a ${dataTexto(fimStr)}`
      + (nomeVendedorFiltrado ? ` · ${nomeVendedorFiltrado}` : "");
    gerarPdfRelatorio({ tituloPeriodo, resumo: dados.resumo, visitas: dados.visitas })
      .finally(() => setGerandoPdf(false));
  }

  return (
    <div className="mapa-layout contato-layout">
      <aside className="painel painel-largo">
        <div className="painel-head">
          <h3>Relatórios</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            {ehAdmin ? "O que o time fez, por período" : "Suas visitas, por período"}
          </p>
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Período</span>
          <div className="periodo-btns">
            {PRESETS.map((p) => (
              <button
                key={p.chave}
                className={"dia-btn" + (presetAtivo === p.chave ? " on" : "")}
                onClick={() => aplicarPreset(p.chave)}
              >
                {p.rotulo}
              </button>
            ))}
          </div>
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Personalizado</span>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input" type="date" value={inicioStr}
              onChange={(e) => { setInicioStr(e.target.value); setPresetAtivo(null); }}
            />
            <input
              className="input" type="date" value={fimStr}
              onChange={(e) => { setFimStr(e.target.value); setPresetAtivo(null); }}
            />
          </div>
        </div>

        {ehAdmin && (
          <div className="filtro-grupo">
            <span className="filtro-titulo">Vendedor</span>
            <select className="input" value={vendedorId} onChange={(e) => setVendedorId(e.target.value)}>
              <option value="">Todo o time</option>
              {(vendedores || []).map((v) => (
                <option key={v.id} value={v.id}>{v.nome}</option>
              ))}
            </select>
          </div>
        )}

        <div className="resumo">
          <div className="resumo-item"><span>Visitas</span><b>{dados ? dados.resumo.totalVisitas : "—"}</b></div>
          <div className="resumo-item"><span>Clientes únicos</span><b>{dados ? dados.resumo.clientesUnicos : "—"}</b></div>
          <div className="resumo-item"><span>Duração média</span><b>{dados ? duracaoTexto(dados.resumo.duracaoMediaMin) : "—"}</b></div>
          <div className="resumo-item"><span>Promessas feitas</span><b>{dados ? dados.resumo.promessasFeitas : "—"}</b></div>
          <div className="resumo-item destaque"><span>Retornos agendados</span><b>{dados ? dados.resumo.retornosAgendados : "—"}</b></div>
        </div>

        <button
          className="btn btn-primary"
          style={{ width: "100%", justifyContent: "center" }}
          disabled={!dados || dados.visitas.length === 0 || gerandoPdf}
          onClick={baixarPdf}
        >
          {gerandoPdf ? "Gerando…" : "Baixar PDF do período"}
        </button>
      </aside>

      <div className="contato-lista-wrap">
        {erro && <div className="login-erro" style={{ maxWidth: 800, margin: "0 auto 16px" }}>{erro}</div>}
        {carregando ? (
          <p className="muted" style={{ textAlign: "center" }}>Carregando…</p>
        ) : !dados || dados.visitas.length === 0 ? (
          <div className="vazio">
            <p>Nenhuma visita finalizada nesse período.</p>
          </div>
        ) : (
          <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", flexDirection: "column", gap: 22 }}>
            {grupos.map(([chaveDia, visitasDoDia]) => (
              <div key={chaveDia}>
                <h4 className="relatorio-dia-titulo">
                  {dataDeChaveLocal(chaveDia).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}
                  <span className="faint" style={{ fontWeight: 500, marginLeft: 8 }}>
                    {visitasDoDia.length} visita{visitasDoDia.length > 1 ? "s" : ""}
                  </span>
                </h4>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {visitasDoDia.map((v) => (
                    <div key={v.id} className="cliente-card relatorio-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
                        <b>{v.clienteNome}</b>
                        <span className="faint" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                          {dataHoraUtc(v.inicio).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                          {" · "}{duracaoTexto(v.duracaoMin)}
                        </span>
                      </div>
                      <p className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                        {v.clienteCidade || "sem cidade"}{ehAdmin ? ` · ${v.vendedorNome}` : ""}
                      </p>
                      {v.observacao && <p style={{ fontSize: 13, marginTop: 8 }}>{v.observacao}</p>}
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                        {v.retornoData && (
                          <span className="chip chip-gold">Retorno {dataTexto(v.retornoData)}</span>
                        )}
                        {v.promessas.map((p) => (
                          <span key={p.id} className="chip chip-motivo" title={p.texto}>
                            🎁 {p.cumprida ? "cumprida" : "pendente"}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
